"""Grade the model against real past matches (H2H pairs, per-team history).

Reads eval_features.csv (exported by ml/train.py: pre-match features as they
were known BEFORE each match since 2018) and predicts each one with the
CURRENT ensemble — honest as-of backtesting, no information leakage.
"""
import csv
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .engine import ml_ensemble

MODELS_DIR = Path(__file__).resolve().parent / "data" / "models"
FEATURES = ["elo_diff", "pi_diff", "form5_diff", "gf5_diff", "ga5_diff",
            "neutral", "importance"]
OUTCOME_NAMES = ("home", "draw", "away")


@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    path = MODELS_DIR / "eval_features.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _name_of() -> dict[str, str]:
    """TLA -> dataset team name (from training artifacts)."""
    try:
        state = json.load(open(MODELS_DIR / "team_state.json"))
        return {tla: v["dataset_name"] for tla, v in state.items()}
    except Exception:
        return {}


def _grade(rows: list[dict]) -> dict:
    """Predict each row with the current ensemble; return per-match verdicts
    + aggregate accuracy/RPS."""
    if not rows:
        return {"matches": [], "summary": None}
    X = np.array([[float(r[f]) for f in FEATURES] for r in rows])
    probs = ml_ensemble.predict_matrix(X)
    if probs is None:
        return {"matches": [], "summary": None, "error": "ML artifacts missing"}

    out, n_correct, rps_sum = [], 0, 0.0
    for r, p in zip(rows, probs):
        actual = int(r["outcome"])
        pick = int(np.argmax(p))
        correct = pick == actual
        n_correct += correct
        onehot = np.eye(3)[actual]
        cp, co = np.cumsum(p)[:2], np.cumsum(onehot)[:2]
        rps_sum += float(np.sum((cp - co) ** 2) / 2)
        out.append({
            "date": r["date"][:10], "tournament": r["tournament"],
            "home": r["home"], "away": r["away"],
            "score": f"{int(float(r['gh']))}-{int(float(r['ga']))}",
            "probs": {k: round(float(v), 3) for k, v in zip(OUTCOME_NAMES, p)},
            "predicted": OUTCOME_NAMES[pick],
            "actual": OUTCOME_NAMES[actual],
            "correct": bool(correct),
        })
    n = len(out)
    return {
        "matches": out,
        "summary": {"n": n, "accuracy": round(n_correct / n, 4),
                    "rps": round(rps_sum / n, 4)},
    }


def h2h(home_tla: str, away_tla: str, n: int = 10) -> dict:
    names = _name_of()
    h, a = names.get(home_tla), names.get(away_tla)
    if not h or not a:
        return {"matches": [], "summary": None, "error": "unknown team"}
    rows = [r for r in _rows() if {r["home"], r["away"]} == {h, a}]
    rows.sort(key=lambda r: r["date"], reverse=True)
    res = _grade(rows[:n])
    res["pair"] = {"home": home_tla, "away": away_tla}
    return res


def team_recent(tla: str, n: int = 12) -> dict:
    name = _name_of().get(tla)
    if not name:
        return {"matches": [], "summary": None, "error": "unknown team"}
    rows = [r for r in _rows() if name in (r["home"], r["away"])]
    rows.sort(key=lambda r: r["date"], reverse=True)
    res = _grade(rows[:n])
    res["team"] = tla
    return res


def summary() -> dict:
    rep = ml_ensemble.report()
    return {
        "backtest": rep,
        "eval_set_size": len(_rows()),
        "note": "backtest = held-out 2025+ test; eval set = all matches 2018+ "
                "graded with the current model (as-of features, no leakage)",
    }


def reload() -> None:
    _rows.cache_clear()
    _name_of.cache_clear()
