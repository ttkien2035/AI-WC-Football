"""Meta-calibration of the pre-match W/D/L blend weights.

The headline probability is a convex blend of three components — trained ML
ensemble, market odds, Poisson/Elo matrix — whose weights were hand-set.
This module LEARNS them from the tournament itself: every pre-match snapshot
stores the three component probability vectors (pipeline.record_prematch),
so once matches finish we can ask "which blend would have scored the best
RPS?" and move the served weights toward that optimum.

Safeguards (small-sample honesty):
- shrinkage toward the configured hand weights with strength k/(k+n):
  at n=8 finished samples the fit only carries 50% — early-tournament noise
  cannot yank the blend around;
- activates only at n >= meta_weights_min_n, OFF via META_WEIGHTS_ENABLED;
- grid-searched on the simplex (5% steps) — no optimizer dependencies, and
  the result is audited in the admin pipeline (in-sample RPS vs hand RPS).
"""
from datetime import datetime, timezone

from .. import cache
from ..config import settings

_KEY = "meta:weights"
_TTL = 12 * 3600.0


def _rps(p: dict, actual: str) -> float:
    order = ("home", "draw", "away")
    cp = rps = 0.0
    for k in order[:2]:
        cp += p.get(k, 0.0)
        rps += (cp - (1.0 if order.index(actual) <= order.index(k) else 0.0)) ** 2
    return rps / 2


def _blend_rps(samples: list[dict], w_m: float, w_ml: float, w_p: float) -> float:
    tot = 0.0
    for s in samples:
        p = {k: w_m * s["market"][k] + w_ml * s["ml"][k] + w_p * s["poisson"][k]
             for k in ("home", "draw", "away")}
        z = sum(p.values()) or 1.0
        tot += _rps({k: v / z for k, v in p.items()}, s["actual"])
    return tot / len(samples)


def _collect(matches: list[dict]) -> list[dict]:
    """Finished matches whose snapshot carried all three component vectors."""
    out = []
    for m in matches:
        if m["status"] != "FINISHED" or m["score"]["home"] is None:
            continue
        pm, _ = cache.get_stale(f"prematch:{m['id']}")
        comp = (pm or {}).get("components") or {}
        if all(comp.get(k) for k in ("ml", "market", "poisson")):
            gh, ga = m["score"]["home"], m["score"]["away"]
            out.append({**{k: comp[k] for k in ("ml", "market", "poisson")},
                        "actual": "home" if gh > ga else
                                  ("draw" if gh == ga else "away")})
    return out


def recompute_if_stale(matches: list[dict]) -> dict:
    """Fit (cached 12h) and return the meta-weights report for the pipeline."""
    hit = cache.get(_KEY, _TTL)
    if hit is not None:
        return hit
    report = _recompute(matches)
    cache.put(_KEY, report)
    return report


def _recompute(matches: list[dict]) -> dict:
    hand = {"market": settings.ml_w_market, "ml": settings.ml_w_ml,
            "poisson": settings.ml_w_poisson}
    base = {"enabled": settings.meta_weights_enabled, "hand": hand,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    samples = _collect(matches)
    n = len(samples)
    if n < settings.meta_weights_min_n:
        return {**base, "n": n, "active": False, "reason": "insufficient_samples"}

    best, best_rps = None, float("inf")
    steps = [i / 20 for i in range(21)]            # 0.00 .. 1.00, 5% grid
    for w_m in steps:
        for w_ml in steps:
            w_p = 1.0 - w_m - w_ml
            if w_p < -1e-9:
                continue
            r = _blend_rps(samples, w_m, w_ml, max(w_p, 0.0))
            if r < best_rps:
                best_rps, best = r, (w_m, w_ml, max(w_p, 0.0))

    k = settings.meta_weights_k
    lam = n / (n + k)                              # how much the fit carries
    fitted = {"market": best[0], "ml": best[1], "poisson": best[2]}
    served = {key: round(lam * fitted[key] + (1 - lam) * hand[key], 3)
              for key in hand}
    hand_rps = _blend_rps(samples, hand["market"], hand["ml"], hand["poisson"])
    return {**base, "n": n, "active": settings.meta_weights_enabled,
            "fitted": fitted, "served": served, "shrink_lambda": round(lam, 2),
            "rps_hand": round(hand_rps, 4), "rps_fitted": round(best_rps, 4)}


def current() -> dict | None:
    """Served weights for match_model.predict_match (None -> hand weights)."""
    if not settings.meta_weights_enabled:
        return None
    hit, _ = cache.get_stale(_KEY)
    if hit and hit.get("active") and hit.get("served"):
        return hit["served"]
    return None
