"""Per-match prediction: Elo-driven Poisson goals, blended with market odds,
Elo win expectancy and form. Generalized from the repo's original
prediction_utils.py / mci_ars_predictor.py math.
"""
import math
import numpy as np

from ..config import settings, HOST_TLAS

FORM_WEIGHTS = (0.30, 0.25, 0.20, 0.15, 0.10)   # most recent first
_FORM_VAL = {"W": 1.0, "D": 0.5, "L": 0.0}


def form_score(results: list[str]) -> float | None:
    """results: most-recent-first list of W/D/L. Normalized by weights used,
    so a 3-game list isn't penalized vs a 5-game list."""
    pairs = [(_FORM_VAL[r], w) for r, w in zip(results, FORM_WEIGHTS) if r in _FORM_VAL]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def elo_expected(elo_h: float, elo_a: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_a - elo_h) / 400.0))


def effective_elo(tla: str, elo: float) -> float:
    return elo + (settings.host_elo_bonus if tla in HOST_TLAS else 0.0)


def lambdas_from_elo(elo_h: float, elo_a: float, mu: float | None = None) -> tuple[float, float]:
    """Split a total-goals prior into team lambdas via Elo supremacy."""
    mu = mu or settings.goals_mu
    sup = (elo_h - elo_a) / settings.elo_sup_scale
    lam_h = max(0.15, (mu + sup) / 2.0)
    lam_a = max(0.15, (mu - sup) / 2.0)
    return lam_h, lam_a


def attack_defence_lambda(home: dict, away: dict, lg_avg_per_team: float) -> tuple[float, float] | None:
    """Classic attack/defence-strength lambdas from in-tournament stats.
    Returns None when either side hasn't played yet."""
    if not home.get("played") or not away.get("played") or lg_avg_per_team <= 0:
        return None
    h_att = (home["gf"] / home["played"]) / lg_avg_per_team
    h_def = (home["ga"] / home["played"]) / lg_avg_per_team
    a_att = (away["gf"] / away["played"]) / lg_avg_per_team
    a_def = (away["ga"] / away["played"]) / lg_avg_per_team
    lam_h = h_att * a_def * lg_avg_per_team
    lam_a = a_att * h_def * lg_avg_per_team
    return max(0.15, lam_h), max(0.15, lam_a)


def score_matrix(lam_h: float, lam_a: float, max_g: int | None = None,
                 rho: float = 0.0) -> np.ndarray:
    """(max_g+1, max_g+1) matrix of P(home=h, away=a), renormalized so the
    truncated tail doesn't leak probability.

    rho != 0 applies the Dixon-Coles tau correction to the four low-score
    cells (0-0, 1-0, 0-1, 1-1) — independent Poisson systematically
    underestimates low-scoring draws; rho is fitted in ml/train.py."""
    max_g = max_g or settings.max_goals
    ks = np.arange(max_g + 1)
    log_fact = np.cumsum(np.log(np.maximum(ks, 1)))
    ph = np.exp(-lam_h + ks * math.log(lam_h) - log_fact)
    pa = np.exp(-lam_a + ks * math.log(lam_a) - log_fact)
    m = np.outer(ph, pa)
    if rho:
        m[0, 0] *= max(1 - lam_h * lam_a * rho, 1e-9)
        m[0, 1] *= max(1 + lam_h * rho, 1e-9)
        m[1, 0] *= max(1 + lam_a * rho, 1e-9)
        m[1, 1] *= max(1 - rho, 1e-9)
    return m / m.sum()


def matrix_outcomes(m: np.ndarray) -> dict:
    h_idx, a_idx = np.indices(m.shape)
    return {
        "home": float(m[h_idx > a_idx].sum()),
        "draw": float(np.trace(m)),
        "away": float(m[h_idx < a_idx].sum()),
        "over25": float(m[h_idx + a_idx > 2].sum()),
        "btts": float(m[1:, 1:].sum()),
    }


def top_scorelines(m: np.ndarray, k: int = 5, shift: tuple[int, int] = (0, 0)) -> list[dict]:
    flat = np.argsort(m, axis=None)[::-1][:k]
    out = []
    for f in flat:
        h, a = divmod(int(f), m.shape[1])
        out.append({"home": h + shift[0], "away": a + shift[1], "p": float(m[h, a])})
    return out


def predict_match(
    *,
    home_tla: str,
    away_tla: str,
    elo_h: float,
    elo_a: float,
    home_stats: dict | None = None,
    away_stats: dict | None = None,
    lg_avg_per_team: float = 0.0,
    market: dict | None = None,        # {"home":p,"draw":p,"away":p} vig-removed
    form_h: list[str] | None = None,   # ["W","D",...] most recent first
    form_a: list[str] | None = None,
    minute: int | None = None,         # in-play
    goals_h: int = 0,
    goals_a: int = 0,
    ml_probs: dict | None = None,      # trained ensemble W/D/L (engine/ml_ensemble)
    lam_override: tuple[float, float] | None = None,  # fitted goal rates
    red_cards: tuple[int, int] = (0, 0),  # sent-off counts (home, away), in-play
    stage: str | None = None,             # GROUP_STAGE / LAST_32 / ... (KO caginess)
    rho: float = 0.0,                     # Dixon-Coles low-score correction
) -> dict:
    eh = effective_elo(home_tla, elo_h)
    ea = effective_elo(away_tla, elo_a)

    # --- expected goals: fitted Poisson rates when available, else Elo split;
    # then blended with in-tournament attack/defence
    lam_h, lam_a = lam_override if lam_override else lambdas_from_elo(eh, ea)
    ad = attack_defence_lambda(home_stats or {}, away_stats or {}, lg_avg_per_team)
    if ad:
        played = min(home_stats.get("played", 0), away_stats.get("played", 0))
        w_ad = played / (played + 3.0)          # 3 games -> 50/50 with Elo
        lam_h = (1 - w_ad) * lam_h + w_ad * ad[0]
        lam_a = (1 - w_ad) * lam_a + w_ad * ad[1]

    # knockout caginess: per-90 goal rate drops vs group stage (fitted 0.955)
    if stage and stage != "GROUP_STAGE":
        lam_h *= settings.ko_goal_factor
        lam_a *= settings.ko_goal_factor

    in_play = minute is not None
    if in_play:
        remaining = max(90 - minute, 0) / 90.0
        lam_h_rem, lam_a_rem = lam_h * remaining, lam_a * remaining
        # Red-card effect on remaining scoring rates (WC/Euro betting-data
        # studies: sanctioned team ~x0.67, opponent ~x1.25 per man down)
        rh, ra = red_cards
        if rh or ra:
            lam_h_rem *= (0.67 ** rh) * (1.25 ** ra)
            lam_a_rem *= (0.67 ** ra) * (1.25 ** rh)
        m = score_matrix(max(lam_h_rem, 1e-6), max(lam_a_rem, 1e-6))
        # final scoreline = current score + remaining goals
        shift = (goals_h, goals_a)
        h_idx, a_idx = np.indices(m.shape)
        fh, fa = h_idx + goals_h, a_idx + goals_a
        poisson_probs = {
            "home": float(m[fh > fa].sum()),
            "draw": float(m[fh == fa].sum()),
            "away": float(m[fh < fa].sum()),
            "over25": float(m[fh + fa > 2].sum()),
            "btts": float(m[(fh > 0) & (fa > 0)].sum()),
        }
        scorelines = top_scorelines(m, shift=shift)
    else:
        m = score_matrix(lam_h, lam_a, rho=rho)
        poisson_probs = matrix_outcomes(m)
        scorelines = top_scorelines(m)
        shift = (0, 0)

    # --- Elo W/D/L: expectancy split using the Poisson draw rate
    we = elo_expected(eh, ea)
    d = poisson_probs["draw"]
    elo_probs = {"home": (1 - d) * we, "draw": d, "away": (1 - d) * (1 - we)}

    # --- form delta
    fs_h, fs_a = form_score(form_h or []), form_score(form_a or [])
    form_delta = ((fs_h - fs_a) if fs_h is not None and fs_a is not None else 0.0)

    # --- blend (market only meaningful pre-match; in-play the current score
    # dominates and Elo already drives the remaining-goal rates, so the
    # in-play Poisson is used alone)
    use_market = market is not None and not in_play
    use_ml = ml_probs is not None and not in_play
    w_ml = 0.0
    if in_play:
        w_m, w_p, w_e, w_f = 0.0, 1.0, 0.0, 0.0
    elif use_ml and use_market:
        w_m, w_ml, w_p, w_e, w_f = (settings.ml_w_market, settings.ml_w_ml,
                                    settings.ml_w_poisson, 0.0, settings.ml_w_form)
    elif use_ml:
        w_m, w_ml, w_p, w_e, w_f = (0.0, settings.ml_only_w_ml, settings.ml_only_w_poisson,
                                    settings.ml_only_w_elo, settings.ml_only_w_form)
    elif use_market:
        w_m, w_p, w_e, w_f = (settings.w_market, settings.w_poisson_with_market,
                              settings.w_elo_with_market, settings.w_form_with_market)
    else:
        w_m, w_p, w_e, w_f = 0.0, settings.w_poisson, settings.w_elo, settings.w_form

    blended = {}
    for k in ("home", "draw", "away"):
        v = w_p * poisson_probs[k] + w_e * elo_probs[k]
        if use_market:
            v += w_m * market[k]
        if use_ml:
            v += w_ml * ml_probs[k]
        blended[k] = v
    blended["home"] += w_f * form_delta
    blended["away"] -= w_f * form_delta
    blended = {k: max(v, 1e-4) for k, v in blended.items()}
    s = sum(blended.values())
    blended = {k: v / s for k, v in blended.items()}

    return {
        "home": home_tla, "away": away_tla,
        "in_play": in_play,
        "red_cards": {"home": red_cards[0], "away": red_cards[1]} if any(red_cards) else None,
        "minute": minute, "score": {"home": goals_h, "away": goals_a} if in_play else None,
        "lambdas": {"home": round(lam_h, 3), "away": round(lam_a, 3),
                    **({"home_remaining": round(lam_h_rem, 3),
                        "away_remaining": round(lam_a_rem, 3)} if in_play else {})},
        "probs": {k: round(v, 4) for k, v in blended.items()},
        "components": {
            "poisson": {k: round(poisson_probs[k], 4) for k in ("home", "draw", "away")},
            "elo": {k: round(v, 4) for k, v in elo_probs.items()},
            "market": ({k: round(market[k], 4) for k in ("home", "draw", "away")}
                       if market else None),
            "ml": ({k: round(ml_probs[k], 4) for k in ("home", "draw", "away")}
                   if ml_probs else None),
            "form": {"home": fs_h, "away": fs_a, "delta": round(form_delta, 3)},
            "weights": {"market": w_m if use_market else 0, "ml": w_ml,
                        "poisson": w_p, "elo": w_e, "form": w_f},
        },
        "over25": round(poisson_probs["over25"], 4),
        "btts": round(poisson_probs["btts"], 4),
        "scorelines": scorelines,
        "elo": {"home": eh, "away": ea, "expectancy": round(we, 4)},
    }
