"""Train the multi-model ensemble and export serving artifacts.

Usage:  cd backend && .venv/bin/python -m ml.train

Temporal split: train <=2021 | validate 2022-2024 | test 2025+.
Exports to app/data/models/: dc_params.json, logreg.joblib, xgb.json,
xgb_calib.joblib, goal_rates.json, ensemble.json, team_state.json, report.json
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .data import (DATASET_NAMES, FEATURES, build_features, load_results)
from . import models as M

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models"
TRAIN_END, VALID_END = "2022-01-01", "2025-01-01"


def heuristic_baseline(df: pd.DataFrame) -> np.ndarray:
    """Current production heuristic: elo supremacy / 333 split of mu=2.6."""
    probs = np.empty((len(df), 3))
    ks = np.arange(M.MAX_G + 1)
    fact = np.cumprod(np.concatenate([[1.0], np.maximum(ks[1:], 1)]))
    for i, ed in enumerate(df["elo_diff"].to_numpy()):
        sup = ed / 333.0
        lh, la = max(0.15, (2.6 + sup) / 2), max(0.15, (2.6 - sup) / 2)
        ph = np.exp(-lh) * lh ** ks / fact
        pa = np.exp(-la) * la ** ks / fact
        m = np.outer(ph, pa)
        m /= m.sum()
        hi, ai = np.indices(m.shape)
        probs[i] = [m[hi > ai].sum(), np.trace(m), m[hi < ai].sum()]
    return probs


def main() -> None:
    print("Loading results ...")
    df = load_results()
    print(f"  {len(df):,} matches {df['date'].min().date()} → {df['date'].max().date()}")

    print("Building chronological features (Elo, pi-ratings, form) ...")
    feat, state = build_features(df)
    feat["tournament"] = df["tournament"].to_numpy()

    train = feat[feat["date"] < TRAIN_END]
    valid = feat[(feat["date"] >= TRAIN_END) & (feat["date"] < VALID_END)]
    test = feat[feat["date"] >= VALID_END]
    print(f"  train {len(train):,} | valid {len(valid):,} | test {len(test):,}")

    print("Fitting M1 Dixon-Coles ...")
    dc = M.fit_dixon_coles(feat[feat["date"] < TRAIN_END])
    print(f"  teams={len(dc['att'])} rho={dc['rho']:+.2f} home_adv={dc['home_adv']:.3f}")

    print("Fitting M2 logistic regression ...")
    lr = M.fit_logreg(train)

    print("Fitting M3 XGBoost (+isotonic) ...")
    xgb, calibs = M.fit_xgb(train, valid)

    print("Fitting M4 Poisson goal rates ...")
    rates = M.fit_goal_rates(train)
    print(f"  lambda = exp({rates['a']:.3f} + {rates['b']:.4f} * elo_diff/100)")

    print("Optimizing ensemble weights on validation (RPS) ...")
    val_probs = {
        "dc": M.dc_predict_frame(dc, valid),
        "lr": lr.predict_proba(valid[FEATURES]),
        "xgb": M.xgb_predict(xgb, calibs, valid),
    }
    y_val = valid["outcome"].to_numpy()
    weights, val_rps = M.fit_ensemble_weights(
        val_probs, y_val, floors={"lr": 0.25, "xgb": 0.25})
    print(f"  weights={weights}  val RPS={val_rps:.4f}")

    # ---- evaluation on held-out test ----
    y = test["outcome"].to_numpy()
    sets = {
        "heuristic (current)": heuristic_baseline(test),
        "M1 dixon-coles": M.dc_predict_frame(dc, test),
        "M2 logreg": lr.predict_proba(test[FEATURES]),
        "M3 xgboost": M.xgb_predict(xgb, calibs, test),
    }
    num = np.zeros((len(test), 3)); den = np.zeros((len(test), 1))
    for nm, w in weights.items():
        p = {"dc": sets["M1 dixon-coles"], "lr": sets["M2 logreg"],
             "xgb": sets["M3 xgboost"]}[nm]
        ok = ~np.isnan(p[:, 0])
        num[ok] += w * p[ok]; den[ok] += w
    den[den == 0] = 1
    sets["ENSEMBLE"] = num / den

    report = {"split": {"train": len(train), "valid": len(valid), "test": len(test)},
              "weights": weights, "test_metrics": {}}
    print(f"\n{'model':<22} {'RPS':>8} {'logloss':>9} {'accuracy':>9}   (test: 2025+, n={len(test)})")
    for nm, p in sets.items():
        ok = ~np.isnan(p[:, 0])
        r = M.rps(p[ok], y[ok]); ll = M.log_loss3(p[ok], y[ok])
        acc = float((p[ok].argmax(1) == y[ok]).mean())
        report["test_metrics"][nm] = {"rps": round(r, 4), "logloss": round(ll, 4),
                                      "acc": round(acc, 4), "n": int(ok.sum())}
        print(f"{nm:<22} {r:>8.4f} {ll:>9.4f} {acc:>9.3f}")

    # ---- export ----
    OUT.mkdir(parents=True, exist_ok=True)
    # DC params restricted to teams seen (small file: only ~250 teams anyway)
    json.dump(dc, open(OUT / "dc_params.json", "w"))
    joblib.dump(lr, OUT / "logreg.joblib")
    xgb.save_model(OUT / "xgb.json")
    joblib.dump(calibs, OUT / "xgb_calib.joblib")
    json.dump(rates, open(OUT / "goal_rates.json", "w"))
    json.dump({"weights": weights, "features": FEATURES}, open(OUT / "ensemble.json", "w"))
    # serving state for the 48 WC teams, keyed by TLA
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.static_data import TEAMS
    team_state = {}
    for tla, meta in TEAMS.items():
        name = DATASET_NAMES.get(tla, meta["name"])
        if name not in state:
            print(f"  WARNING: no dataset state for {tla} ({name})")
            continue
        team_state[tla] = {**state[name], "dataset_name": name}
    json.dump(team_state, open(OUT / "team_state.json", "w"))
    json.dump(report, open(OUT / "report.json", "w"), indent=1)
    # per-match evaluation set (2018+): pre-match features + actual results,
    # used by /api/evaluate/* to grade the model on past H2H meetings
    ev = feat[feat["date"] >= "2018-01-01"][
        ["date", "home", "away", *FEATURES, "gh", "ga", "outcome", "tournament"]]
    ev.to_csv(OUT / "eval_features.csv", index=False)
    print(f"  eval set: {len(ev):,} matches (2018+)")
    print(f"\nArtifacts → {OUT}  ({len(team_state)}/48 teams mapped)")


if __name__ == "__main__":
    main()
