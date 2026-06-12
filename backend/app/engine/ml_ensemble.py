"""Serving wrapper for the trained ML ensemble (see backend/ml/).

Loads artifacts once; degrades to None (callers fall back to the heuristic)
when artifacts or runtime deps are missing. Team ratings come from the
training-time team_state (same Elo scale the models were trained on) and are
updated online from finished WC matches so predictions sharpen during the
tournament.
"""
import json
import logging
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

# models were fitted on named DataFrames; we predict with plain arrays
warnings.filterwarnings("ignore", message="X does not have valid feature names")

from ..config import HOST_TLAS

log = logging.getLogger(__name__)
MODELS_DIR = Path(__file__).resolve().parents[1] / "data" / "models"

K_WC, ELO_HOME_ADV, IMPORTANCE_WC = 60.0, 60.0, 3
PI_LAM, PI_GAM = 0.06, 0.5    # pi-rating learning rates (same as training)


def _goal_mult(gd: int) -> float:
    gd = abs(gd)
    return 1.0 if gd <= 1 else (1.5 if gd == 2 else (11.0 + gd) / 8.0)


def reload() -> None:
    """Drop cached artifacts so the next call picks up freshly trained models."""
    _artifacts.cache_clear()


@lru_cache(maxsize=1)
def _artifacts():
    try:
        import joblib
        from xgboost import XGBClassifier
        lr = joblib.load(MODELS_DIR / "logreg.joblib")
        xgb = XGBClassifier()
        xgb.load_model(MODELS_DIR / "xgb.json")
        calibs = joblib.load(MODELS_DIR / "xgb_calib.joblib")
        ens = json.load(open(MODELS_DIR / "ensemble.json"))
        rates = json.load(open(MODELS_DIR / "goal_rates.json"))
        state = json.load(open(MODELS_DIR / "team_state.json"))
        report = json.load(open(MODELS_DIR / "report.json"))
        try:
            markets = joblib.load(MODELS_DIR / "markets.joblib")
        except Exception:
            markets = None     # pre-sprint artifacts
        return {"lr": lr, "xgb": xgb, "calibs": calibs, "weights": ens["weights"],
                "features": ens["features"], "rates": rates, "state": state,
                "report": report, "markets": markets,
                "market_weights": ens.get("market_weights", {})}
    except Exception as e:           # missing files, version mismatch, no xgboost
        log.warning("ML artifacts unavailable (%s) — falling back to heuristic", e)
        return None


def available() -> bool:
    return _artifacts() is not None


def dc_rho() -> float:
    """Fitted Dixon-Coles low-score correlation (0.0 when artifacts missing)."""
    a = _artifacts()
    if a is None:
        return 0.0
    try:
        return float(json.load(open(MODELS_DIR / "dc_params.json")).get("rho", 0.0))
    except Exception:
        return 0.0


def report() -> dict | None:
    a = _artifacts()
    return a["report"] if a else None


def _updated_state(finished: tuple) -> dict:
    """Apply finished WC matches (chronological) on top of the trained state:
    Elo (K=60, goal-diff multiplier) + pi-ratings + rolling form/goals.
    This is the per-match online learning step — every result sharpens the
    feature inputs without waiting for a full retrain."""
    a = _artifacts()
    state = {t: dict(v) for t, v in a["state"].items()}
    hist: dict[str, list] = {t: [] for t in state}
    for h_tla, a_tla, gh, ga in finished:
        if h_tla not in state or a_tla not in state:
            continue
        sh, sa = state[h_tla], state[a_tla]
        adv = ELO_HOME_ADV if h_tla in HOST_TLAS else 0.0
        we = 1.0 / (1.0 + 10 ** (-(sh["elo"] + adv - sa["elo"]) / 400.0))
        res = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        k = K_WC * _goal_mult(gh - ga)
        sh["elo"] += k * (res - we)
        sa["elo"] -= k * (res - we)

        # pi-rating update (same scheme as ml/data.py training walk)
        gd = gh - ga
        err = gd - (sh["pi_home"] - sa["pi_away"])
        psi = 2.0 * np.log10(1.0 + abs(err)) * np.sign(err) if err else 0.0
        sh["pi_home"] += PI_LAM * psi
        sh["pi_away"] += PI_LAM * PI_GAM * psi
        sa["pi_away"] -= PI_LAM * psi
        sa["pi_home"] -= PI_LAM * PI_GAM * psi

        hist[h_tla].append((3 if gh > ga else (1 if gh == ga else 0), gh, ga))
        hist[a_tla].append((3 if ga > gh else (1 if gh == ga else 0), ga, gh))
    for t, games in hist.items():
        if not games:
            continue
        s = state[t]
        # mix tournament games into the 5-game rolling stats
        n_new = len(games)
        w_old = max(5 - n_new, 0)
        tot = w_old + n_new
        s["form5_pts"] = (s["form5_pts"] * w_old + sum(g[0] for g in games)) / tot
        s["gf5"] = (s["gf5"] * w_old + sum(g[1] for g in games)) / tot
        s["ga5"] = (s["ga5"] * w_old + sum(g[2] for g in games)) / tot
    return state


def _features(sh: dict, sa: dict, neutral: bool) -> np.ndarray:
    adv = 0.0 if neutral else ELO_HOME_ADV
    return np.array([[
        sh["elo"] + adv - sa["elo"],
        sh["pi_home"] - sa["pi_away"],
        sh["form5_pts"] - sa["form5_pts"],
        sh["gf5"] - sa["gf5"],
        sh["ga5"] - sa["ga5"],
        int(neutral),
        IMPORTANCE_WC,
    ]])


def predict_wdl(home_tla: str, away_tla: str, finished: tuple = (),
                elo_adjust: tuple = (0.0, 0.0)) -> dict | None:
    """Ensemble P(home/draw/away). `finished` = tuple of (h,a,gh,ga) WC results.
    elo_adjust: additive Elo deltas (e.g. key-player absence penalties)."""
    a = _artifacts()
    if a is None:
        return None
    state = _updated_state(finished)
    if home_tla not in state or away_tla not in state:
        return None
    sh = {**state[home_tla], "elo": state[home_tla]["elo"] + elo_adjust[0]}
    sa = {**state[away_tla], "elo": state[away_tla]["elo"] + elo_adjust[1]}
    neutral = home_tla not in HOST_TLAS
    X = _features(sh, sa, neutral)

    plr = a["lr"].predict_proba(X)[0]
    raw = a["xgb"].predict_proba(X)[0]
    pxgb = np.array([a["calibs"][k].predict([raw[k]])[0] for k in range(3)])
    pxgb = np.clip(pxgb, 1e-4, None)
    pxgb /= pxgb.sum()

    w = a["weights"]
    p = w.get("lr", 0) * plr + w.get("xgb", 0) * pxgb
    p /= p.sum()
    return {"home": float(p[0]), "draw": float(p[1]), "away": float(p[2])}


def goal_lambdas(home_tla: str, away_tla: str, finished: tuple = (),
                 elo_adjust: tuple = (0.0, 0.0)) -> tuple[float, float] | None:
    """Fitted Poisson rates lambda = exp(a ± b·elo_diff/100) on the training
    Elo scale (replaces the hand-tuned elo_sup_scale heuristic)."""
    a = _artifacts()
    if a is None:
        return None
    state = _updated_state(finished)
    if home_tla not in state or away_tla not in state:
        return None
    adv = 0.0 if home_tla not in HOST_TLAS else ELO_HOME_ADV
    ed = (state[home_tla]["elo"] + elo_adjust[0] + adv
          - state[away_tla]["elo"] - elo_adjust[1])
    r = a["rates"]
    lh = float(np.exp(r["a"] + r["b"] * ed / 100.0))
    la = float(np.exp(r["a"] - r["b"] * ed / 100.0))
    return max(lh, 0.15), max(la, 0.15)


def predict_markets(home_tla: str, away_tla: str, finished: tuple = (),
                    elo_adjust: tuple = (0.0, 0.0)) -> dict | None:
    """Trained O/U 2.5 + BTTS head probabilities + their blend weights.
    Returns {"over25": p, "btts": p, "weights": {...}} or None."""
    a = _artifacts()
    if a is None or not a.get("markets"):
        return None
    state = _updated_state(finished)
    if home_tla not in state or away_tla not in state:
        return None
    sh = {**state[home_tla], "elo": state[home_tla]["elo"] + elo_adjust[0]}
    sa = {**state[away_tla], "elo": state[away_tla]["elo"] + elo_adjust[1]}
    neutral = home_tla not in HOST_TLAS
    adv = 0.0 if neutral else ELO_HOME_ADV
    # MARKET_FEATURES order: elo_sum, elo_diff, gf5_sum, ga5_sum,
    #                        gf5_min, ga5_max, neutral, importance
    X = np.array([[
        sh["elo"] + sa["elo"],
        sh["elo"] + adv - sa["elo"],
        sh["gf5"] + sa["gf5"], sh["ga5"] + sa["ga5"],
        min(sh["gf5"], sa["gf5"]), max(sh["ga5"], sa["ga5"]),
        int(neutral), IMPORTANCE_WC,
    ]])
    out = {"weights": a["market_weights"]}
    for target, head in a["markets"].items():
        plr = head["lr"].predict_proba(X)[:, 1]
        pxgb = head["iso"].predict(head["xgb"].predict_proba(X)[:, 1])
        out[target] = float(np.clip(0.5 * plr + 0.5 * pxgb, 1e-4, 1 - 1e-4)[0])
    return out


def predict_matrix(X: np.ndarray) -> np.ndarray | None:
    """Batch ensemble W/D/L for pre-built feature rows (evaluation service)."""
    a = _artifacts()
    if a is None or len(X) == 0:
        return None
    plr = a["lr"].predict_proba(X)
    raw = a["xgb"].predict_proba(X)
    pxgb = np.column_stack([a["calibs"][k].predict(raw[:, k]) for k in range(3)])
    pxgb = np.clip(pxgb, 1e-4, None)
    pxgb /= pxgb.sum(axis=1, keepdims=True)
    w = a["weights"]
    p = w.get("lr", 0) * plr + w.get("xgb", 0) * pxgb
    return p / p.sum(axis=1, keepdims=True)


def current_ratings(finished: tuple = ()) -> dict[str, dict] | None:
    """Online-updated ratings snapshot for the 48 teams (for /api/ml/status)."""
    a = _artifacts()
    if a is None:
        return None
    return {t: {k: round(v, 1) if isinstance(v, float) else v
                for k, v in s.items() if k != "dataset_name"}
            for t, s in _updated_state(finished).items()}


def elo_by_tla(finished: tuple = ()) -> dict[str, float] | None:
    """Training-scale Elo for the 48 teams (for the tournament MC)."""
    a = _artifacts()
    if a is None:
        return None
    return {t: v["elo"] for t, v in _updated_state(finished).items()}
