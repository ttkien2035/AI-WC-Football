"""Supervised corners model — trained on club data, transferred to internationals.

Research grounding (see plan): corners are driven by ① attacking/crossing
volume ② possession dominance ③ opponent low-block (concedes corners)
④ team strength gap ⑤ each team's recent corners earned/conceded.
No public per-match corner history exists for internationals, so we train on
football-data.co.uk club CSVs (HC/AC corners, HS/AS shots, B365 1X2 odds) with
ONLY features that are also computable for national teams at serving time:

  p_home, p_draw, p_away  (de-vig odds  -> app's blended probs at serving)
  cf6/ca6 per team        (rolling corners for/against -> tournament matchlog,
                           cold-start prior from style tags)
  sf6 per team            (rolling shots -> mapped from app's xG via fitted k)

Model: XGBRegressor (Poisson objective) for total corners + Ridge for the home
share; NB dispersion fitted from residuals for O/U line probabilities.
"""
import json
from collections import defaultdict, deque
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data" / "corners"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models"
BASE = "https://www.football-data.co.uk/mmz4281"
LEAGUES = ["E0", "SP1", "I1", "D1", "F1"]
SEASONS = ["2021", "2122", "2223", "2324", "2425"]   # 5 seasons x 5 leagues
HOLDOUT_SEASON = "2425"

CFEATURES = ["p_home", "p_draw", "p_away",
             "cf6_h", "ca6_h", "cf6_a", "ca6_a",
             "sf6_h", "sf6_a", "strength_gap"]


def download() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for season in SEASONS:
        for lg in LEAGUES:
            f = DATA_DIR / f"{season}_{lg}.csv"
            if not f.exists():
                import urllib.request
                urllib.request.urlretrieve(f"{BASE}/{season}/{lg}.csv", f)
            try:
                df = pd.read_csv(f, usecols=lambda c: c in (
                    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
                    "HS", "AS", "HC", "AC", "B365H", "B365D", "B365A"),
                    encoding="latin-1", on_bad_lines="skip")
            except Exception:
                continue
            df["season"], df["league"] = season, lg
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["HC", "AC", "B365H", "B365D", "B365A", "HS", "AS"])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological rolling features per (league, team)."""
    cf = defaultdict(lambda: deque(maxlen=6))   # corners for
    ca = defaultdict(lambda: deque(maxlen=6))   # corners against
    sf = defaultdict(lambda: deque(maxlen=6))   # shots for

    def avg(q, default):
        return float(np.mean(q)) if q else default

    rows = []
    for r in df.itertuples(index=False):
        kh, ka = (r.league, r.HomeTeam), (r.league, r.AwayTeam)
        inv_h, inv_d, inv_a = 1 / r.B365H, 1 / r.B365D, 1 / r.B365A
        s = inv_h + inv_d + inv_a
        ph, pd_, pa = inv_h / s, inv_d / s, inv_a / s
        rows.append({
            "p_home": ph, "p_draw": pd_, "p_away": pa,
            "strength_gap": abs(ph - pa),
            "cf6_h": avg(cf[kh], 5.2), "ca6_h": avg(ca[kh], 5.2),
            "cf6_a": avg(cf[ka], 5.2), "ca6_a": avg(ca[ka], 5.2),
            "sf6_h": avg(sf[kh], 12.5), "sf6_a": avg(sf[ka], 12.5),
            "total": r.HC + r.AC, "hc": r.HC,
            "season": r.season,
        })
        cf[kh].append(r.HC); ca[kh].append(r.AC); sf[kh].append(r.HS)
        cf[ka].append(r.AC); ca[ka].append(r.HC); sf[ka].append(r.AS)
    return pd.DataFrame(rows)


def nb_over(mu: np.ndarray, line: float, ratio: float) -> np.ndarray:
    """P(total > line) under negative binomial with var = ratio * mean."""
    from scipy.stats import nbinom
    mu = np.maximum(mu, 0.1)
    r = mu / (ratio - 1.0)
    p = r / (r + mu)
    return 1.0 - nbinom.cdf(int(line), r, p)


def train() -> dict:
    df = build(download())
    train_df = df[df["season"] != HOLDOUT_SEASON]
    hold = df[df["season"] == HOLDOUT_SEASON]
    print(f"corners: train {len(train_df):,} | holdout {len(hold):,} (season {HOLDOUT_SEASON})")

    from xgboost import XGBRegressor
    from sklearn.linear_model import Ridge
    xgb = XGBRegressor(objective="count:poisson", tree_method="hist",
                       n_estimators=400, learning_rate=0.05, max_depth=4,
                       subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0)
    xgb.fit(train_df[CFEATURES], train_df["total"])

    share = Ridge(alpha=1.0)
    share_y = train_df["hc"] / train_df["total"].clip(lower=1)
    share.fit(train_df[CFEATURES], share_y)

    resid_mu = xgb.predict(train_df[CFEATURES])
    ratio = float(np.var(train_df["total"] - resid_mu) / np.mean(resid_mu))
    ratio = max(1.05, 1.0 + ratio)          # var/mean of NB around fitted mean
    # shots-per-implied-strength mapping for serving (shots ~ a + b * p_side)
    from numpy.polynomial import polynomial as P
    b_sh, a_sh = np.polyfit(train_df["p_home"], train_df["sf6_h"], 1)

    # ---- holdout evaluation vs baselines ----
    mu_h = xgb.predict(hold[CFEATURES])
    tot = hold["total"].to_numpy()
    base_mu = np.full(len(hold), train_df["total"].mean())
    print(f"  fitted NB var/mean ratio: {ratio:.2f} | mean total: {train_df['total'].mean():.2f}")
    report = {}
    for line in (8.5, 9.5, 10.5):
        y = (tot > line).astype(float)
        p_model = nb_over(mu_h, line, ratio)
        p_base = nb_over(base_mu, line, ratio)
        bm = float(np.mean((p_model - y) ** 2))
        bb = float(np.mean((p_base - y) ** 2))
        report[str(line)] = {"model_brier": round(bm, 4), "baseline_brier": round(bb, 4)}
        print(f"  O/U {line}: model Brier {bm:.4f} vs constant-mean {bb:.4f} "
              f"{'✓' if bm < bb else '✗'}")
    mae = float(np.mean(np.abs(mu_h - tot)))
    print(f"  MAE total corners: {mae:.2f}")
    report["mae"] = round(mae, 3)

    OUT.mkdir(parents=True, exist_ok=True)
    xgb.save_model(OUT / "corners_xgb.json")
    joblib.dump(share, OUT / "corners_share.joblib")
    json.dump({"features": CFEATURES, "dispersion_ratio": round(ratio, 3),
               "mean_total": round(float(train_df["total"].mean()), 3),
               "shots_map": {"a": round(float(a_sh), 3), "b": round(float(b_sh), 3)},
               "holdout": report},
              open(OUT / "corners_model.json", "w"))
    print(f"  artifacts -> {OUT}/corners_*")
    return report


if __name__ == "__main__":
    train()
