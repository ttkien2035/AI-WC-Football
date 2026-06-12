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


def _tags(tla: str) -> set:
    return set((PROFILES.get(tla) or {}).get("style") or [])


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
