"""
Shared utilities for football match prediction models.
"""
import math

# ── Model constants ──────────────────────────────────────────
HOME_ADVANTAGE_FACTOR = 1.10
N_SIMS                = 100_000
RATE_LIMIT_DELAY      = 7        # seconds; free tier allows ~10 req/min
GAMMA_SHAPE           = 25.0     # CV = 1/sqrt(25) = 20% lambda uncertainty
POISSON_BLEND         = 0.75
ELO_BLEND             = 0.25
FORM_IMPACT           = 0.05
MAX_GOALS             = 8
FORM_WEIGHTS          = (0.30, 0.25, 0.20, 0.15, 0.10)
FORM_MAP              = {1: "W", 0.5: "D", 0: "L"}

# ── Shared functions ─────────────────────────────────────────
def poisson_prob(lam, k):
    return math.exp(-lam) * lam**k / math.factorial(k)

def form_score(form, weights=FORM_WEIGHTS):
    return sum(f * w for f, w in zip(form, weights))
