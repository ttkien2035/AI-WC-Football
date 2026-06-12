"""Location-based expected-goals (xG) proxy from LiveScore shot coordinates.

National-team matches have no commercial xG feed, but LiveScore's shotsMap
gives per-shot pitch coordinates. We turn each shot into an xG estimate with
a transparent distance+angle logistic (coefficients fitted to open-data
anchor points — see ml note). This is a LOCATION-ONLY proxy: it ignores
defender pressure, keeper position, body part and assist type, so treat it as
a 'shot quality' signal, not a calibrated commercial xG.

Coordinates: x,y in 0..100 (x = attacking progress, 100 = opponent goal line;
y = width, 50 = centre). Pitch 105x68 m, goal mouth 7.32 m.
"""
import math

PITCH_L, PITCH_W, GOAL_HALF = 105.0, 68.0, 7.32 / 2
# fitted on open-data anchor shots (penalty 0.76 ... 30m 0.01)
_B0, _B_DIST, _B_ANGLE = -0.0251, -0.1497, 0.4615


def shot_xg(x: float, y: float) -> float:
    """xG for a shot taken at pitch %-coordinates (x, y)."""
    dx = (100 - x) / 100 * PITCH_L
    dy = (y - 50) / 100 * PITCH_W
    dist = math.hypot(dx, dy)
    denom = dx * dx + dy * dy - GOAL_HALF ** 2
    angle = math.atan2(GOAL_HALF * dx, denom) if denom else math.pi / 2
    if angle < 0:
        angle += math.pi
    return round(1 / (1 + math.exp(-(_B0 + _B_DIST * dist + _B_ANGLE * angle))), 4)


def team_xg(shots: list[dict]) -> dict:
    """Aggregate a list of {x, y, ...} shots into team xG + shot quality."""
    xgs = []
    for s in shots:
        try:
            xgs.append(shot_xg(float(s["x"]), float(s["y"])))
        except (KeyError, ValueError, TypeError):
            continue
    n = len(xgs)
    return {
        "xg": round(sum(xgs), 3),
        "shots": n,
        "xg_per_shot": round(sum(xgs) / n, 3) if n else 0.0,
        "big_chances": sum(1 for v in xgs if v >= 0.30),   # high-quality looks
        "best": round(max(xgs), 3) if xgs else 0.0,
    }
