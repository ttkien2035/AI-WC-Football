"""Observed playing style from the tournament's own match data.

The curated style tags in team_profiles are expert priors. Every finished
WC match leaves a stats record (LiveScore: possession, shots, crosses,
fouls, xG) in the match log, so from the first final whistle each team has
MEASURED style metrics. This module aggregates them and uses them to
confirm or veto the curated tags:

- a tag the data confirms is kept (and trusted more downstream);
- a tag the data clearly contradicts is dropped once confidence allows
  (n >= 2 matches) — e.g. a curated "possession" team averaging 40% ball;
- strong observed signals ADD tags the curators missed.

Confidence grows with matches played: conf = n / (n + 2). All thresholds
are conservative and documented; the layer is OFF-switchable and feeds the
style factors that the pipeline factor-scorecard audits on real results.
"""
from .. import cache
from ..team_profiles import PROFILES

# observed-metric thresholds (per-game averages)
POSSESSION_HI = 56.0   # -> "possession"
POSSESSION_LO = 44.0   # -> counter-ish profile, vetoes "possession"
CROSSES_HI = 14.0      # -> "wing_play"
FOULS_HI = 14.0        # -> "physical" (duel/press intensity proxy)
XGA_LO = 0.85          # with low possession -> "low_block" holds up


def observed(tla: str) -> dict | None:
    """Per-game observed metrics for a team from the match log, or None."""
    rows = []
    for k in cache.keys("matchlog:"):
        e, _ = cache.get_stale(k)
        if not e or tla not in (e.get("home"), e.get("away")):
            continue
        side = "home" if e["home"] == tla else "away"
        opp = "away" if side == "home" else "home"
        st = e.get("stats") or {}

        def v(field, who):
            d = st.get(field) or {}
            return d.get(who)

        if v("possession", side) is None:
            continue
        rows.append({
            "possession": v("possession", side),
            "shots": (v("shots_on", side) or 0) + (v("shots_off", side) or 0)
                     + (v("shots_blocked", side) or 0),
            "crosses": v("crosses", side) or 0,
            "fouls": v("fouls", side) or 0,
            "xg_for": v("xg", side) or 0.0,
            "xg_against": v("xg", opp) or 0.0,
        })
    if not rows:
        return None
    n = len(rows)
    agg = {k: round(sum(r[k] for r in rows) / n, 2) for k in rows[0]}
    return {"n": n, "confidence": round(n / (n + 2), 2), **agg}


def effective_tags(tla: str) -> tuple[set, dict]:
    """(style tags after observed confirm/veto/add, audit info)."""
    curated = set((PROFILES.get(tla) or {}).get("style") or [])
    obs = observed(tla)
    info = {"curated": sorted(curated), "observed": obs,
            "dropped": [], "added": []}
    if not obs:
        return curated, info
    tags = set(curated)
    veto_ready = obs["n"] >= 2          # don't veto an expert tag on one game

    if obs["possession"] >= POSSESSION_HI and "possession" not in tags:
        tags.add("possession"); info["added"].append("possession")
    if veto_ready and obs["possession"] <= POSSESSION_LO and "possession" in tags:
        tags.discard("possession"); info["dropped"].append("possession")

    if obs["crosses"] >= CROSSES_HI and "wing_play" not in tags:
        tags.add("wing_play"); info["added"].append("wing_play")

    if obs["fouls"] >= FOULS_HI and "physical" not in tags:
        tags.add("physical"); info["added"].append("physical")

    if (obs["possession"] <= POSSESSION_LO and obs["xg_against"] <= XGA_LO
            and "low_block" not in tags):
        tags.add("low_block"); info["added"].append("low_block")

    return tags, info
