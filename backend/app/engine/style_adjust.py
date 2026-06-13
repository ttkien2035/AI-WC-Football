"""Tactical style-interaction adjustments (coach/playing-style layer).

Honest scope: the MEASURABLE part of a coach's style already lives in the
model via rolling attack/defence form features (the O/U head learned it from
49k matches). What that misses is the MATCHUP texture — how two styles
interact — which mostly shapes scoreline distribution and corners rather
than the winner. Literature gives reliable DIRECTIONS (parking-the-bus DML
study, coach tactical-impact work) but not magnitudes for internationals,
so factors here are small, bounded, env-toggleable, and auditable
in-tournament through the pipeline review (predicted xG vs actual goals).
"""
from ..config import settings
from ..team_profiles import PROFILES

DEFENSIVE = {"low_block", "counter"}
ATTACKING = {"possession", "high_press"}

# Manager tactical identities that MODIFY the team's effective style
# (curated, notable benches only; audited like every other style effect).
# pragmatic: tilts toward containment when not the favourite;
# proactive: adds pressing intent regardless of opponent.
MANAGER_STYLE = {
    "FRA": "pragmatic", "MAR": "pragmatic", "MEX": "pragmatic",
    "CRO": "pragmatic", "UZB": "pragmatic", "ENG": "pragmatic",
    "ESP": "proactive", "GER": "proactive", "AUT": "proactive",
    "USA": "proactive", "CAN": "proactive", "URY": "proactive",
}


def _tags(tla: str, is_favourite: bool | None = None) -> set:
    """Effective style tags: curated, confirmed/vetoed/extended by observed
    in-tournament data (engine/observed_style), then the manager identity."""
    from .observed_style import effective_tags
    tags, _ = effective_tags(tla)
    m = MANAGER_STYLE.get(tla)
    if m == "pragmatic" and is_favourite is False:
        tags.add("low_block")          # pragmatic bench, not favoured -> contain
    if m == "proactive":
        tags.add("high_press")
    return tags


def total_goals_factor(home_tla: str, away_tla: str) -> tuple[float, str | None]:
    """(lambda multiplier, reason key) from the style matchup."""
    if not settings.style_adjust_enabled:
        return 1.0, None
    th, ta = _tags(home_tla), _tags(away_tla)
    h_def, a_def = bool(th & DEFENSIVE), bool(ta & DEFENSIVE)
    h_att, a_att = bool(th & ATTACKING), bool(ta & ATTACKING)
    if h_def and a_def:
        return 1.0 - settings.style_total_max, "both_defensive"       # stalemate
    if h_att and a_att:
        return 1.0 + settings.style_total_max * 0.7, "both_attacking"  # open game
    if (h_att and a_def and "low_block" in ta) or (a_att and h_def and "low_block" in th):
        return 1.0 - settings.style_total_max * 0.5, "block_vs_attack"  # bus parked
    return 1.0, None


def corners_share_bump(home_tla: str, away_tla: str) -> tuple[float, float]:
    """Additive share adjustment per side: wing-play/possession sides earn
    more corners; a low-block opponent concedes more (corner-determinant
    research: crossing volume + deep blocks)."""
    if not settings.style_adjust_enabled:
        return 0.0, 0.0
    th, ta = _tags(home_tla), _tags(away_tla)

    def earn(own: set, opp: set) -> float:
        b = 0.0
        if "wing_play" in own:
            b += 0.03
        if "possession" in own:
            b += 0.02
        if "low_block" in opp:
            b += 0.02
        if "counter" in own:
            b -= 0.03
        return b

    return earn(th, ta), earn(ta, th)


def corners_total_factor(home_tla: str, away_tla: str) -> tuple[float, str | None]:
    """Multiplier on TOTAL corners from the style matchup (the share bump only
    redistributes; this changes the count). Wing-play/possession sides cross
    more -> more corners; deep blocks under pressure concede more; two
    low-block/counter sides starve the game of corners. Bounded by config."""
    if not (settings.style_adjust_enabled and settings.corners_style_enabled):
        return 1.0, None
    th, ta = _tags(home_tla), _tags(away_tla)
    WIDE = {"wing_play", "possession"}
    LOW = {"low_block", "counter"}
    cap = settings.corners_style_max
    f, reason = 1.0, None
    h_wide, a_wide = bool(th & WIDE), bool(ta & WIDE)
    h_low, a_low = bool(th & LOW), bool(ta & LOW)
    if h_wide and a_wide:
        f, reason = 1.0 + cap, "both_wide"                 # crossfest
    elif h_low and a_low:
        f, reason = 1.0 - cap, "both_low"                  # starved
    elif (h_wide and a_low) or (a_wide and h_low):
        f, reason = 1.0 + cap * 0.6, "wide_vs_block"       # forced corners
    return f, reason


# Style cold-start corner priors (per game) before a team has tournament data.
def corner_prior(tla: str) -> tuple[float, float]:
    """(for_base, against_base) per game seeded from style tags, replacing the
    flat 5.2 until observed rates take over."""
    tags = _tags(tla)
    base = 5.2
    fr = base + (0.8 if "wing_play" in tags else 0.0) + (0.5 if "possession" in tags else 0.0) \
        - (0.5 if "counter" in tags else 0.0)
    ag = base + (0.8 if "low_block" in tags else 0.0) + (0.4 if "counter" in tags else 0.0) \
        - (0.4 if "high_press" in tags else 0.0)
    return round(fr, 2), round(ag, 2)


def supremacy_elo_delta(home_tla: str, away_tla: str,
                        elo_h: float, elo_a: float) -> dict:
    """Style-matchup W/D/L adjustment expressed as Elo-equivalent deltas
    (reuses the absence/prior plumbing). Literature directions, small caps:

    1. counter/low-block underdog vs possession favourite: transitions into
       the space the favourite leaves -> underdog gets a bounded bump;
    2. high-press side vs a low-possession/direct opponent whose build-up
       feeds the press -> press side gets a bounded bump;
    3. two possession teams: no supremacy edge, slight draw tilt (fewer
       transitions either way).

    Returns {home, away, draw_bump, reason}; all zeros when disabled.
    """
    out = {"home": 0.0, "away": 0.0, "draw_bump": 0.0, "reason": None}
    if not (settings.style_adjust_enabled and settings.style_sup_enabled):
        return out
    gap = elo_h - elo_a
    fav_h = gap >= 0
    th = _tags(home_tla, is_favourite=fav_h)
    ta = _tags(away_tla, is_favourite=not fav_h)
    cap = settings.style_sup_max_elo

    # 1) counter underdog vs possession favourite (needs a real gap)
    if abs(gap) >= 60:
        dog, fav = (away_tla, home_tla) if fav_h else (home_tla, away_tla)
        td, tf = (ta, th) if fav_h else (th, ta)
        if (td & DEFENSIVE) and ("possession" in tf):
            key = "away" if dog == away_tla else "home"
            out[key] += cap
            out["reason"] = "counter_vs_possession"
    # 2) press vs pressable build-up
    if "high_press" in th and ("direct" in ta or "low_block" in ta):
        out["home"] += cap * 0.6
        out["reason"] = out["reason"] or "press_vs_buildup"
    if "high_press" in ta and ("direct" in th or "low_block" in th):
        out["away"] += cap * 0.6
        out["reason"] = out["reason"] or "press_vs_buildup"
    # 3) possession mirror -> slight draw tilt
    if "possession" in th and "possession" in ta:
        out["draw_bump"] = settings.style_sup_draw_bump
        out["reason"] = out["reason"] or "possession_mirror"
    return out


def sim_modifiers(home_tla: str, away_tla: str,
                  elo_h: float, elo_a: float) -> dict | None:
    """Per-side style traits for the minute simulator's state response.
    {side: {"counter": bool, "low_block": bool, "high_press": bool}}"""
    if not (settings.style_adjust_enabled and settings.style_sim_enabled):
        return None
    fav_h = elo_h >= elo_a
    out = {}
    for side, tla, fav in (("home", home_tla, fav_h), ("away", away_tla, not fav_h)):
        tags = _tags(tla, is_favourite=fav)
        out[side] = {"counter": "counter" in tags,
                     "low_block": "low_block" in tags,
                     "high_press": "high_press" in tags}
    return out


# One-line tactical identities for notable coaches (analysis panel + chatbot)
MANAGER_NOTES = {
    "ARG": "Scaloni: flexible 4-3-3/4-4-2, midfield control around Messi's free role",
    "BRA": "Ancelotti: pragmatic possession, fast wide transitions through Vinicius",
    "ESP": "de la Fuente: positional possession, high press, width from Yamal/Williams",
    "FRA": "Deschamps: low-risk block + devastating transitions through Mbappe",
    "ENG": "Tuchel: structured 4-2-3-1, set-piece emphasis, control over chaos",
    "GER": "Nagelsmann: aggressive high line, fluid front four, press-and-possess",
    "POR": "Martinez: patient possession, overloads wide, slow-fast rhythm changes",
    "NED": "Koeman: classic Dutch 4-3-3, build from the back",
    "URY": "Bielsa: man-to-man press all over the pitch, vertical attacks — high tempo both ways",
    "AUT": "Rangnick: gegenpressing 4-2-2-2, forces turnovers high",
    "MEX": "Aguirre: pragmatic, compact mid-block, quick wide breaks",
    "USA": "Pochettino: energetic press, full-back overlaps",
    "JPN": "Moriyasu: 3-4-2-1 with wing-back width, rapid counters",
    "CAN": "Marsch: vertical chaos pressing, direct to David/Davies",
    "MAR": "Regragui: world-class defensive block + Hakimi's right-side surges",
    "CRO": "Dalic: midfield-first control, tournament pragmatism",
    "UZB": "Cannavaro: Italian defensive organization, counter through Khusanov's line",
    "SWE": "Potter: structured build-up, dual-striker box presence (Isak/Gyokeres)",
}
