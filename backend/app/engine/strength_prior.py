"""Pot-tier strength prior (Feature: seeding).

The FIFA draw pots are an official, ranking-based strength stratification.
For teams with thin/stale international data the Elo seed is noisy, so we
shrink each team's Elo toward its pot-tier baseline with a weight that
decays as the team plays tournament matches (Bayesian-style):

    w     = w0 * k / (k + played)          (bounded by w0, env-tunable)
    delta = w * (tier_baseline - elo)      (added to the serving Elo)

At w0 = 0.15 and k = 2 a team that has not kicked a ball moves at most
15% of the way to its tier median; after 3 group games the pull is ~6%
and keeps fading. OFF-switchable via POT_PRIOR_ENABLED. The applied delta
is exposed in components.seed so the pipeline can audit it.

IMPORTANT: the prior tier is NOT the official draw pot. Pot 1 holds the
hosts by privilege (USA/MEX/CAN are FIFA 14/15/28) and Pot 4 holds strong
late playoff winners (TUR/SWE entered via placeholders) — using draw pots
would drag hosts up and playoff teams down by artifact. Instead teams are
re-tiered into rank-order quartiles of the 48 by FIFA ranking (the same
principle FIFA uses for non-host seeding), and the baseline is the median
static-seed Elo of each rank tier — a robust centre that doesn't chase
outliers. The official pot stays display-only (badge/chatbot).
"""
from statistics import median

from ..config import settings
from ..static_data import TEAMS

# rank-order quartiles: 12 best-FIFA-ranked teams -> tier 1, next 12 -> 2, ...
_BY_RANK = sorted(TEAMS, key=lambda t: TEAMS[t]["fifa"])
RANK_TIER = {t: i // 12 + 1 for i, t in enumerate(_BY_RANK)}
TIER_BASELINE = {
    tier: median(TEAMS[t]["elo"] for t in _BY_RANK if RANK_TIER[t] == tier)
    for tier in (1, 2, 3, 4)
}


def pot_shrink_delta(tla: str, elo: float, played: int) -> float:
    """Bounded Elo delta pulling `elo` toward the team's rank-tier baseline."""
    if not settings.pot_prior_enabled:
        return 0.0
    tier = RANK_TIER.get(tla)
    if tier is None:
        return 0.0
    k = settings.pot_prior_k
    w = settings.pot_prior_w0 * k / (k + max(0, played))
    return round(w * (TIER_BASELINE[tier] - elo), 1)
