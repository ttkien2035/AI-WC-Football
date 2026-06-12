"""Period-level predictions on top of the goal model:

- halves: HT result/scores, 2nd-half scores, HT/FT 9-way combinations
- corners: per-half expectations + over/under probabilities (Poisson)
- knockout: extra-time / penalties probabilities and "win via" breakdown

No historical international HT/corner dataset exists in our training data, so
these are parametric models (documented constants from large-sample football
averages) — corners get team-specific calibration from in-tournament
LiveScore stats as games accumulate.
"""
import math

import numpy as np

from ..config import settings
from .match_model import score_matrix, top_scorelines, matrix_outcomes, elo_expected

WDL = ("home", "draw", "away")


def _wdl(m: np.ndarray) -> dict:
    hi, ai = np.indices(m.shape)
    return {"home": float(m[hi > ai].sum()), "draw": float(np.trace(m)),
            "away": float(m[hi < ai].sum())}


def halves(lam_h: float, lam_a: float, minute: int | None = None,
           goals_h: int = 0, goals_a: int = 0,
           ht_h: int | None = None, ht_a: int | None = None) -> dict:
    """Half-by-half predictions. In-play: conditions on the known state —
    before HT predicts rest-of-H1 + H2; after HT predicts rest-of-H2 only."""
    s1 = settings.h1_goal_share
    l1 = (lam_h * s1, lam_a * s1)
    l2 = (lam_h * (1 - s1), lam_a * (1 - s1))

    out: dict = {}
    if minute is None or minute <= 0:
        m1 = score_matrix(*l1)
        m2 = score_matrix(*l2)
        out["h1"] = {"probs": _wdl(m1), "top_scores": top_scorelines(m1, 3),
                     "lambdas": [round(x, 3) for x in l1]}
        out["h2"] = {"probs": _wdl(m2), "top_scores": top_scorelines(m2, 3),
                     "lambdas": [round(x, 3) for x in l2]}
        # HT/FT: P(ht outcome & ft outcome) — halves independent Poisson
        htft = {}
        hi, ai = np.indices(m1.shape)
        for ht_k, ht_mask in (("home", hi > ai), ("draw", hi == ai), ("away", hi < ai)):
            p_ht_cells = m1 * ht_mask
            # final outcome = h1 score + h2 score; iterate h1 cells (small grid)
            acc = {"home": 0.0, "draw": 0.0, "away": 0.0}
            for h1h in range(m1.shape[0]):
                for h1a in range(m1.shape[1]):
                    p = p_ht_cells[h1h, h1a]
                    if p < 1e-7:
                        continue
                    fh, fa = np.indices(m2.shape)
                    fh = fh + h1h
                    fa = fa + h1a
                    acc["home"] += p * float(m2[fh > fa].sum())
                    acc["draw"] += p * float(m2[fh == fa].sum())
                    acc["away"] += p * float(m2[fh < fa].sum())
            for ft_k in WDL:
                htft[f"{ht_k}/{ft_k}"] = round(acc[ft_k], 4)
        out["htft"] = htft
        return out

    # ---- in-play ----
    if minute < 45:
        rem1_frac = (45 - minute) / 45.0
        m1r = score_matrix(l1[0] * rem1_frac, l1[1] * rem1_frac)
        out["h1"] = {
            "note": f"remaining H1 from {minute}', current {goals_h}-{goals_a}",
            "top_scores": top_scorelines(m1r, 3, shift=(goals_h, goals_a)),
            "lambdas": [round(l1[0] * rem1_frac, 3), round(l1[1] * rem1_frac, 3)],
        }
        m2 = score_matrix(*l2)
        out["h2"] = {"probs": _wdl(m2), "top_scores": top_scorelines(m2, 3),
                     "lambdas": [round(x, 3) for x in l2]}
    else:
        rem2_frac = max(90 - minute, 0) / 45.0
        m2r = score_matrix(max(l2[0] * rem2_frac, 1e-6), max(l2[1] * rem2_frac, 1e-6))
        h2h_so_far = goals_h - (ht_h or 0)
        h2a_so_far = goals_a - (ht_a or 0)
        out["h1"] = ({"final": {"home": ht_h, "away": ht_a}}
                     if ht_h is not None else {"final": "unknown"})
        out["h2"] = {
            "note": f"remaining H2 from {minute}'",
            "top_scores": top_scorelines(m2r, 3, shift=(max(h2h_so_far, 0), max(h2a_so_far, 0))),
            "lambdas": [round(l2[0] * rem2_frac, 3), round(l2[1] * rem2_frac, 3)],
        }
    return out


def _pois_cdf(lam: float, k: int) -> float:
    return math.fsum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def _nb_cdf(mu: float, k: int, ratio: float | None = None) -> float:
    """Negative-binomial CDF with variance = ratio * mean. Corners are ~2x
    overdispersed vs Poisson (fitted on 9k club matches) — plain Poisson is
    overconfident on O/U lines."""
    ratio = ratio or settings.corners_dispersion
    if ratio <= 1.0 or mu <= 0:
        return _pois_cdf(max(mu, 1e-6), k)
    r = mu / (ratio - 1.0)
    p = r / (r + mu)
    # CDF via the regularized incomplete beta; iterate pmf for small k instead
    total, pmf = 0.0, p ** r
    for i in range(k + 1):
        if i > 0:
            pmf *= (r + i - 1) / i * (1 - p)
        total += pmf
    return min(total, 1.0)


def corners(lam_h: float, lam_a: float, elo_h: float, elo_a: float,
            team_rates: tuple[dict | None, dict | None] = (None, None),
            minute: int | None = None,
            corners_so_far: dict | None = None,
            score_diff: int = 0) -> dict:
    """Poisson corners model. Total scales with attack intensity; home share
    follows an Elo-based dominance proxy; per-half split from config.
    team_rates: in-tournament per-team averages (LiveScore) blended in."""
    intensity = ((lam_h + lam_a) / settings.goals_mu) ** 0.7
    total = settings.corners_base * intensity
    we = elo_expected(elo_h, elo_a)            # dominance proxy
    share_h = 0.35 + 0.30 * we                 # 0.35..0.65
    c_h, c_a = total * share_h, total * (1 - share_h)

    # blend in observed tournament rates once a team has played
    for i, (rate, base) in enumerate(zip(team_rates, (c_h, c_a))):
        if rate and rate.get("games"):
            w = rate["games"] / (rate["games"] + 2.0)
            blended = (1 - w) * base + w * rate["for_avg"]
            if i == 0:
                c_h = blended
            else:
                c_a = blended
    total = c_h + c_a

    s1 = settings.corners_h1_share
    res = {
        "expected": {"home": round(c_h, 2), "away": round(c_a, 2),
                     "total": round(total, 2),
                     "h1": round(total * s1, 2), "h2": round(total * (1 - s1), 2)},
        "over": {},
        "team_data": {"home_games": (team_rates[0] or {}).get("games", 0),
                      "away_games": (team_rates[1] or {}).get("games", 0)},
    }
    for line in (3.5, 4.5):
        res["over"][f"h1_{line}"] = round(1 - _nb_cdf(total * s1, int(line)), 4)
    for line in (8.5, 9.5, 10.5):
        res["over"][f"ft_{line}"] = round(1 - _nb_cdf(total, int(line)), 4)

    if minute is not None and corners_so_far:
        rem = max(90 - minute, 0) / 90.0
        so_far = (corners_so_far.get("home") or 0) + (corners_so_far.get("away") or 0)
        exp_rem = total * rem
        # game state (WC-2006 match-status research): trailing side pushes
        # late -> corner rate rises in the final phase
        if minute >= 70 and score_diff:
            exp_rem *= 1.10
        res["in_play"] = {
            "so_far": corners_so_far, "expected_remaining": round(exp_rem, 2),
            "projected_total": round(so_far + exp_rem, 2),
            "over_ft": {str(l): round(1 - _nb_cdf(exp_rem, max(int(l) - so_far, -1)), 4)
                        for l in (8.5, 9.5, 10.5)},
        }
    return res


def knockout(lam_h: float, lam_a: float, elo_h: float, elo_a: float) -> dict:
    """Extra time & penalties breakdown for a knockout tie."""
    m90 = score_matrix(lam_h, lam_a)
    p90 = _wdl(m90)
    p_et = p90["draw"]

    et_scale = (30.0 / 90.0) * settings.et_intensity
    met = score_matrix(max(lam_h * et_scale, 1e-6), max(lam_a * et_scale, 1e-6))
    pet = _wdl(met)
    p_pens = p_et * pet["draw"]

    we = elo_expected(elo_h, elo_a)
    pen_h = 0.5 + (we - 0.5) * settings.pens_elo_tilt

    win_h = p90["home"] + p_et * pet["home"] + p_pens * pen_h
    win_a = p90["away"] + p_et * pet["away"] + p_pens * (1 - pen_h)
    return {
        "regulation": {k: round(v, 4) for k, v in p90.items()},
        "p_extra_time": round(p_et, 4),
        "p_penalties": round(p_pens, 4),
        "extra_time_probs": {k: round(p_et * v, 4) for k, v in pet.items()},
        "pens_win": {"home": round(pen_h, 4), "away": round(1 - pen_h, 4)},
        "advance": {"home": round(win_h, 4), "away": round(win_a, 4)},
        "win_via": {
            "home": {"regulation": round(p90["home"], 4),
                     "extra_time": round(p_et * pet["home"], 4),
                     "penalties": round(p_pens * pen_h, 4)},
            "away": {"regulation": round(p90["away"], 4),
                     "extra_time": round(p_et * pet["away"], 4),
                     "penalties": round(p_pens * (1 - pen_h), 4)},
        },
    }
