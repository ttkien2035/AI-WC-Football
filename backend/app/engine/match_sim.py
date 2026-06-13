"""Dixon-Robinson minute-by-minute Monte Carlo match simulator.

The closed-form Poisson/Dixon-Coles matrix gives the final-score distribution
but no *scenarios* (timeline, comebacks, in-play conditionals) and treats
goal rates as constant & independent of the score. This engine simulates the
match minute by minute with:

  - a fitted per-minute intensity curve (goals rise + closing-minutes surge),
  - SCORE-STATE feedback (Dixon-Robinson 1998): the leading team eases off,
    the trailing team pushes — produces realistic scorelines (fewer blowouts)
    and lets us read off comeback / late-goal probabilities,
  - red-card multipliers, and
  - optional lambda-uncertainty (each sim draws its own λ from a Gamma prior)
    so pre-match scenario fans are honestly wide.

Same engine for pre-match (start_min=0, score 0-0, lam_cv>0) and in-play
(start from the real minute/score). Vectorized over N sims with numpy.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import settings

_INTENSITY = Path(__file__).resolve().parents[1] / "data" / "models" / "intensity.json"


@lru_cache(maxsize=1)
def _weights() -> np.ndarray:
    try:
        w = np.array(json.load(open(_INTENSITY))["weights"], dtype=float)
        if len(w) == 90:
            return w
    except Exception:
        pass
    # fallback: flat-ish rising curve summing to 1
    m = np.arange(90)
    w = 1.0 + 0.6 * (m / 89.0)
    return w / w.sum()


def reload() -> None:
    _weights.cache_clear()
    _state_table.cache_clear()


_SIMFIT = Path(__file__).resolve().parents[1] / "data" / "models" / "sim_fit.json"


@lru_cache(maxsize=1)
def _state_table() -> dict:
    """Score-state scoring multipliers, FITTED (strength-controlled Poisson on
    314 intl matches, ml/statsbomb_sim_fit.py): leading shows no significant
    ease-off (capped 1.0); trailing genuinely pushes (+0.35 at 1, +0.47 at 2).
    Falls back to the old symmetric hand-set effect if the artifact is absent."""
    try:
        m = json.loads(_SIMFIT.read_text())["serving_mult"]
        return {1: float(m["lead1"]), 2: float(m["lead2"]),
                -1: float(m["trail1"]), -2: float(m["trail2"])}
    except Exception:
        s = settings.sim_state_effect
        return {1: 1 - s, 2: 1 - 1.5 * s, -1: 1 + s, -2: 1 + 1.5 * s}


def _state_mult(lead: np.ndarray,
                style: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Per-sim scoring multipliers for (home, away) given home's current lead,
    from the fitted score-state table. Style conditioning (bounded, hand-set
    pending a per-style fit): a COUNTER team that leads keeps more threat; a
    side chasing INTO a LOW BLOCK has its push damped."""
    t = _state_table()
    # base multiplier per side by its own goal margin (level -> 1.0)
    def side_mult(margin: np.ndarray) -> np.ndarray:
        out = np.ones_like(margin, dtype=float)
        out = np.where(margin == 1, t[1], out)
        out = np.where(margin >= 2, t[2], out)
        out = np.where(margin == -1, t[-1], out)
        out = np.where(margin <= -2, t[-2], out)
        return out
    mh, ma = side_mult(lead), side_mult(-lead)
    if style:
        hold = settings.style_sim_lead_hold     # counter leader keeps threat
        damp = settings.style_sim_chase_damp     # chasing a low block is harder
        if style.get("home", {}).get("counter"):
            mh = np.where(lead > 0, mh + hold * (1 - mh), mh)
        if style.get("away", {}).get("counter"):
            ma = np.where(lead < 0, ma + hold * (1 - ma), ma)
        if style.get("away", {}).get("low_block"):
            mh = np.where(lead < 0, 1 + (mh - 1) * (1 - damp), mh)
        if style.get("home", {}).get("low_block"):
            ma = np.where(lead > 0, 1 + (ma - 1) * (1 - damp), ma)
    return mh, ma


def _style_minute_curve(w: np.ndarray, press: bool) -> np.ndarray:
    """High-press sides front-load scoring intensity and fade late (press
    drops with fatigue — measured sprint-demand literature). Mass-preserving
    tilt: early minutes up, final third down, renormalized."""
    if not press:
        return w
    shift = settings.style_sim_press_early
    m = np.arange(len(w))
    tilt = 1.0 + shift * (1 - 2 * m / (len(w) - 1))   # +shift at 0', -shift at 90'
    out = w * tilt
    return out * (w.sum() / out.sum())


def simulate(lam_h: float, lam_a: float, *, n: int = 20000,
             start_min: int = 0, score: tuple[int, int] = (0, 0),
             reds: tuple[int, int] = (0, 0), lam_cv: float = 0.0,
             style: dict | None = None,
             seed: int | None = None) -> dict:
    """Run N minute-by-minute sims from (start_min, score). Returns final-
    score distribution + scenario probabilities. `style` (optional, from
    style_adjust.sim_modifiers) conditions state response and timing."""
    rng = np.random.default_rng(seed)
    w = _weights()
    wh = _style_minute_curve(w, bool(style and style["home"].get("high_press")))
    wa = _style_minute_curve(w, bool(style and style["away"].get("high_press")))
    start_min = max(0, min(89, start_min))

    # base per-team λ, optionally with parameter uncertainty (Gamma, mean λ)
    if lam_cv and lam_cv > 0:
        k = 1.0 / (lam_cv ** 2)
        lh = rng.gamma(k, lam_h / k, n)
        la = rng.gamma(k, lam_a / k, n)
    else:
        lh = np.full(n, lam_h)
        la = np.full(n, lam_a)

    gh = np.full(n, score[0], dtype=int)
    ga = np.full(n, score[1], dtype=int)
    ht_h = np.where(start_min >= 45, score[0], 0)   # if we start after HT, HT known-ish
    ht_a = np.where(start_min >= 45, score[1], 0)
    led_home = np.zeros(n, dtype=bool)   # home ever led
    led_away = np.zeros(n, dtype=bool)
    late_goal = np.zeros(n, dtype=bool)  # any goal in 80'+

    rd = (0.67 ** reds[0]) * (1.25 ** reds[1])   # static red multiplier on home
    ra_ = (0.67 ** reds[1]) * (1.25 ** reds[0])

    for m in range(start_min, 90):
        lead = gh - ga
        mh, ma = _state_mult(lead, style)
        ih = lh * wh[m] * mh * rd
        ia = la * wa[m] * ma * ra_
        dh = rng.poisson(ih)
        da = rng.poisson(ia)
        gh = gh + dh
        ga = ga + da
        if m == 44:
            ht_h, ht_a = gh.copy(), ga.copy()
        if m >= 80:
            late_goal |= (dh > 0) | (da > 0)
        led_home |= gh > ga
        led_away |= ga > gh

    home = float(np.mean(gh > ga))
    draw = float(np.mean(gh == ga))
    away = float(np.mean(gh < ga))

    # top scorelines
    pairs, counts = np.unique(np.stack([gh, ga], 1), axis=0, return_counts=True)
    order = np.argsort(-counts)[:5]
    scorelines = [{"home": int(pairs[i][0]), "away": int(pairs[i][1]),
                   "p": round(float(counts[i] / n), 4)} for i in order]

    # scenario probabilities
    final_lead = gh - ga
    blew_lead = float(np.mean(led_home & (final_lead <= 0)))   # led then didn't win
    came_back = float(np.mean(led_away & (final_lead > 0)))    # trailed then won
    # volatility: final W/D/L class differs from the half-time class —
    # the "result flipped vs HT" flag the post-match review raises, but
    # PREDICTED pre-match (and graded by the sim-timing scorecard)
    ht_flip = float(np.mean(np.sign(ht_h - ht_a) != np.sign(final_lead)))
    return {
        "n": n,
        "probs": {"home": round(home, 4), "draw": round(draw, 4), "away": round(away, 4)},
        "scorelines": scorelines,
        "over25": round(float(np.mean(gh + ga > 2)), 4),
        "btts": round(float(np.mean((gh > 0) & (ga > 0))), 4),
        "exp_goals": {"home": round(float(gh.mean()), 2), "away": round(float(ga.mean()), 2)},
        "scenarios": {
            "ht_flip": round(ht_flip, 4),
            "late_goal_80plus": round(float(late_goal.mean()), 4),
            "home_blew_lead": round(blew_lead, 4),
            "home_comeback": round(came_back, 4),
            "clean_sheet_home": round(float(np.mean(ga == 0)), 4),
            "clean_sheet_away": round(float(np.mean(gh == 0)), 4),
        },
        "from": {"minute": start_min, "score": {"home": score[0], "away": score[1]}},
    }
