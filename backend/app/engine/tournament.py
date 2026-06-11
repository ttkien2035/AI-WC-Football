"""Full WC-2026 tournament Monte Carlo, vectorized with numpy.

Pipeline per simulation batch (all sims at once):
  1. Group stage: real scores for FINISHED matches, in-play partials for live
     ones, Poisson draws (Elo-split lambdas) for the rest.
  2. Group tables via one-hot matmul; ranking score = pts > GD > GF > noise
     (noise approximates the remaining FIFA tiebreakers / drawing of lots).
  3. Best 8 of the 12 third-placed teams; slot assignment solved by
     backtracking once per unique qualified-set (<=495 scenarios, cached).
  4. Knockouts follow the official routing (matches 73..104); ties go to an
     Elo-tilted penalty shootout. Real knockout results force sim winners.
"""
from functools import lru_cache

import numpy as np

from ..config import settings, HOST_TLAS
from ..static_data import R32, R16, QF, SF

GROUP_LETTERS = "ABCDEFGHIJKL"
THIRD_SLOTS = {74: "ABCDF", 77: "CDFGH", 79: "CEFHI", 80: "EHIJK",
               81: "BEFIJ", 82: "AEHIJ", 85: "EFGIJ", 87: "DEIJL"}
THIRD_SLOT_ORDER = sorted(THIRD_SLOTS)          # [74, 77, 79, 80, 81, 82, 85, 87]
R32_ORDER = sorted(R32)                          # [73..88]
R16_ORDER = sorted(R16)
QF_ORDER = sorted(QF)
SF_ORDER = sorted(SF)


@lru_cache(maxsize=512)
def _assign_thirds(qualified_mask: int) -> tuple[int, ...]:
    """Map the 8 third-place slots to qualified group indices (bitmask input).
    Backtracking over the FIFA allowed-sets; falls back to unconstrained
    greedy if no perfect matching exists (shouldn't happen by design)."""
    qualified = [g for g in range(12) if qualified_mask >> g & 1]
    allowed = {
        m: [g for g in qualified if GROUP_LETTERS[g] in THIRD_SLOTS[m]]
        for m in THIRD_SLOT_ORDER
    }
    slots = sorted(THIRD_SLOT_ORDER, key=lambda m: len(allowed[m]))

    assignment: dict[int, int] = {}

    def bt(i: int, used: set) -> bool:
        if i == len(slots):
            return True
        m = slots[i]
        for g in allowed[m]:
            if g not in used:
                assignment[m] = g
                if bt(i + 1, used | {g}):
                    return True
        return False

    if not bt(0, set()):
        remaining = [g for g in qualified]
        assignment = {}
        for m in THIRD_SLOT_ORDER:
            pick = next((g for g in allowed[m] if g in remaining), remaining[0])
            assignment[m] = pick
            remaining.remove(pick)
    return tuple(assignment[m] for m in THIRD_SLOT_ORDER)


_goal_coefs: dict | None = None   # fitted {a, b} from ml/train.py, set by simulate()


def _lambdas(elo_h: np.ndarray, elo_a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if _goal_coefs:
        ed = elo_h - elo_a
        lam_h = np.maximum(0.15, np.exp(_goal_coefs["a"] + _goal_coefs["b"] * ed / 100.0))
        lam_a = np.maximum(0.15, np.exp(_goal_coefs["a"] - _goal_coefs["b"] * ed / 100.0))
        return lam_h, lam_a
    sup = (elo_h - elo_a) / settings.elo_sup_scale
    lam_h = np.maximum(0.15, (settings.goals_mu + sup) / 2.0)
    lam_a = np.maximum(0.15, (settings.goals_mu - sup) / 2.0)
    return lam_h, lam_a


def _ko_round(rng, elo, h_idx, a_idx, pen_tilt: float = 0.4):
    """Winners of one knockout round. h_idx/a_idx: (n, m) team indices."""
    eh, ea = elo[h_idx], elo[a_idx]
    lam_h, lam_a = _lambdas(eh, ea)
    gh = rng.poisson(lam_h)
    ga = rng.poisson(lam_a)
    we = 1.0 / (1.0 + 10 ** ((ea - eh) / 400.0))
    pen_h = rng.random(h_idx.shape) < (0.5 + (we - 0.5) * pen_tilt)
    win_h = (gh > ga) | ((gh == ga) & pen_h)
    return np.where(win_h, h_idx, a_idx)


def _force_real(winners, h_idx, a_idx, real_results, idx_of):
    """Overwrite simulated winners where a real KO result exists for the pair."""
    for res in real_results:
        h, a, w = idx_of.get(res["home"]), idx_of.get(res["away"]), idx_of.get(res["winner"])
        if h is None or a is None or w is None:
            continue
        mask = ((h_idx == h) & (a_idx == a)) | ((h_idx == a) & (a_idx == h))
        winners[mask] = w
    return winners


def simulate(
    *,
    n: int,
    elo_by_tla: dict[str, float],
    groups: dict[str, list[str]],          # "A" -> [4 TLAs]
    group_matches: list[dict],             # simplified fd matches, GROUP_STAGE
    real_ko: list[dict] | None = None,     # [{"home","away","winner","stage"}]
    seed: int | None = None,
    goal_coefs: dict | None = None,        # fitted Poisson rates (ML pipeline)
) -> dict:
    global _goal_coefs
    _goal_coefs = goal_coefs
    rng = np.random.default_rng(seed)
    tlas = [t for g in GROUP_LETTERS for t in groups[g]]
    idx_of = {t: i for i, t in enumerate(tlas)}
    elo = np.array(
        [elo_by_tla[t] + (settings.host_elo_bonus if t in HOST_TLAS else 0.0) for t in tlas]
    )
    group_idx = np.array([[idx_of[t] for t in groups[g]] for g in GROUP_LETTERS])  # (12,4)

    # ── 1. group-stage goals ────────────────────────────────────────────
    gm = [m for m in group_matches if m["home"]["tla"] in idx_of and m["away"]["tla"] in idx_of]
    n_gm = len(gm)
    hi = np.array([idx_of[m["home"]["tla"]] for m in gm])
    ai = np.array([idx_of[m["away"]["tla"]] for m in gm])

    gh = np.empty((n, n_gm), dtype=np.int64)
    ga = np.empty((n, n_gm), dtype=np.int64)
    lam_h_all, lam_a_all = _lambdas(elo[hi], elo[ai])
    for j, m in enumerate(gm):
        sh, sa = m["score"]["home"] or 0, m["score"]["away"] or 0
        if m["status"] == "FINISHED":
            gh[:, j], ga[:, j] = sh, sa
        elif m["status"] in ("IN_PLAY", "PAUSED"):
            rem = m.get("remaining_frac", 0.5)   # estimated by caller from kickoff time
            gh[:, j] = sh + rng.poisson(lam_h_all[j] * rem, n)
            ga[:, j] = sa + rng.poisson(lam_a_all[j] * rem, n)
        else:
            gh[:, j] = rng.poisson(lam_h_all[j], n)
            ga[:, j] = rng.poisson(lam_a_all[j], n)

    # ── 2. group tables ────────────────────────────────────────────────
    H = np.zeros((n_gm, 48)); H[np.arange(n_gm), hi] = 1.0
    A = np.zeros((n_gm, 48)); A[np.arange(n_gm), ai] = 1.0
    ph = 3.0 * (gh > ga) + 1.0 * (gh == ga)
    pa = 3.0 * (ga > gh) + 1.0 * (gh == ga)
    pts = ph @ H + pa @ A                                  # (n,48)
    gf = gh @ H + ga @ A
    g_against = ga @ H + gh @ A
    score = pts * 1e6 + (gf - g_against) * 1e3 + gf + rng.random((n, 48)) * 0.9

    gs = score[:, group_idx.ravel()].reshape(n, 12, 4)
    order = np.argsort(-gs, axis=2)
    gi_b = np.broadcast_to(group_idx, (n, 12, 4))
    ranked = np.take_along_axis(gi_b, order, axis=2)       # (n,12,4) team idx by rank
    first, second, third = ranked[:, :, 0], ranked[:, :, 1], ranked[:, :, 2]
    third_scores = np.take_along_axis(gs, order, axis=2)[:, :, 2]   # (n,12)

    # ── 3. best thirds + slot assignment ───────────────────────────────
    thr = np.partition(third_scores, 4, axis=1)[:, 4]      # 8th-largest boundary
    qual = third_scores >= thr[:, None]                    # (n,12), exactly 8 True
    masks = (qual @ (1 << np.arange(12))).astype(np.int64)
    uniq, inv = np.unique(masks, return_inverse=True)
    tbl = np.array([_assign_thirds(int(m)) for m in uniq])  # (u,8) group idx per slot
    slot_groups = tbl[inv]                                  # (n,8)
    third_for_slot = np.take_along_axis(third, slot_groups, axis=1)  # (n,8)

    # ── 4. knockout ────────────────────────────────────────────────────
    def slot_team(slot: str, match_no: int) -> np.ndarray:
        if slot.startswith("3:"):
            return third_for_slot[:, THIRD_SLOT_ORDER.index(match_no)]
        rank, g = slot[0], GROUP_LETTERS.index(slot[1])
        return (first if rank == "1" else second)[:, g]

    r32_h = np.stack([slot_team(R32[m][0], m) for m in R32_ORDER], axis=1)
    r32_a = np.stack([slot_team(R32[m][1], m) for m in R32_ORDER], axis=1)

    real_ko = real_ko or []
    by_stage = lambda s: [r for r in real_ko if r["stage"] == s and r.get("winner")]

    w32 = _force_real(_ko_round(rng, elo, r32_h, r32_a), r32_h, r32_a,
                      by_stage("LAST_32"), idx_of)
    pos32 = {m: j for j, m in enumerate(R32_ORDER)}

    r16_h = np.stack([w32[:, pos32[R16[m][0]]] for m in R16_ORDER], axis=1)
    r16_a = np.stack([w32[:, pos32[R16[m][1]]] for m in R16_ORDER], axis=1)
    w16 = _force_real(_ko_round(rng, elo, r16_h, r16_a), r16_h, r16_a,
                      by_stage("LAST_16"), idx_of)
    pos16 = {m: j for j, m in enumerate(R16_ORDER)}

    qf_h = np.stack([w16[:, pos16[QF[m][0]]] for m in QF_ORDER], axis=1)
    qf_a = np.stack([w16[:, pos16[QF[m][1]]] for m in QF_ORDER], axis=1)
    wqf = _force_real(_ko_round(rng, elo, qf_h, qf_a), qf_h, qf_a,
                      by_stage("QUARTER_FINALS"), idx_of)
    posqf = {m: j for j, m in enumerate(QF_ORDER)}

    sf_h = np.stack([wqf[:, posqf[SF[m][0]]] for m in SF_ORDER], axis=1)
    sf_a = np.stack([wqf[:, posqf[SF[m][1]]] for m in SF_ORDER], axis=1)
    wsf = _force_real(_ko_round(rng, elo, sf_h, sf_a), sf_h, sf_a,
                      by_stage("SEMI_FINALS"), idx_of)

    f_h, f_a = wsf[:, 0], wsf[:, 1]
    champ = _force_real(_ko_round(rng, elo, f_h[:, None], f_a[:, None]),
                        f_h[:, None], f_a[:, None], by_stage("FINAL"), idx_of)[:, 0]

    # ── 5. aggregate ───────────────────────────────────────────────────
    def freq(arr) -> np.ndarray:
        return np.bincount(arr.ravel(), minlength=48) / n

    p_win_group = freq(first)
    p_r32 = freq(np.concatenate([r32_h, r32_a], axis=1))
    p_r16 = freq(np.concatenate([r16_h, r16_a], axis=1))
    p_qf = freq(np.concatenate([qf_h, qf_a], axis=1))
    p_sf = freq(np.concatenate([sf_h, sf_a], axis=1))
    p_final = freq(np.stack([f_h, f_a], axis=1))
    p_champ = freq(champ)

    def top_k(arr2d, k=4):
        c = np.bincount(arr2d.ravel(), minlength=48) / arr2d.shape[0]
        top = np.argsort(-c)[:k]
        return [{"tla": tlas[i], "p": round(float(c[i]), 4)} for i in top if c[i] > 0]

    bracket = {}
    rounds = [
        (R32_ORDER, r32_h, r32_a, w32),
        (R16_ORDER, r16_h, r16_a, w16),
        (QF_ORDER, qf_h, qf_a, wqf),
        (SF_ORDER, sf_h, sf_a, wsf),
        ([104], f_h[:, None], f_a[:, None], champ[:, None]),
    ]
    for order_, hh, aa, ww in rounds:
        for j, mno in enumerate(order_):
            bracket[mno] = {
                "home_top": top_k(hh[:, j:j + 1]),
                "away_top": top_k(aa[:, j:j + 1]),
                "winner_top": top_k(ww[:, j:j + 1]),
            }

    teams_out = {
        t: {
            "win_group": round(float(p_win_group[i]), 4),
            "r32": round(float(p_r32[i]), 4),
            "r16": round(float(p_r16[i]), 4),
            "qf": round(float(p_qf[i]), 4),
            "sf": round(float(p_sf[i]), 4),
            "final": round(float(p_final[i]), 4),
            "champion": round(float(p_champ[i]), 4),
        }
        for t, i in idx_of.items()
    }
    return {"runs": n, "teams": teams_out, "bracket": bracket}
