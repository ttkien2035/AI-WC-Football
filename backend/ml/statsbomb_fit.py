"""Scientific corner-determinant fit from StatsBomb open event data.

WHY: the serving corner model used HAND-SET coefficients (crosses->corners
0.28, style bumps 0.8/0.5, manager +-0.4). football-data.co.uk has corners
but NOT crosses, so those couldn't be fit. StatsBomb open-data has full
events (crosses, shots, xG, pressures) for 6 modern men's national-team
tournaments — enough to MEASURE how crossing volume / possession / shots /
pressing actually relate to corners, and replace the assumptions.

Pipeline:
  1. download matches + events for the chosen tournaments (cached to disk),
  2. aggregate per team per match: corners for/against, crosses, shots, xG,
     passes, pressures, possession (pass share),
  3. correlation table + Poisson regression corners_for ~ mechanism features,
  4. write app/data/models/corners_fit.json (coefficients + the cross->corner
     elasticity the serving model will use instead of the guessed 0.28).

Run:  python -m ml.statsbomb_fit
"""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "corners_fit.json"
TEAM_CSV = CACHE / "team_match.csv"

# modern men's national-team tournaments with full event data
COMPS = [(43, 106, "WC2022"), (43, 3, "WC2018"), (55, 282, "Euro2024"),
         (55, 43, "Euro2020"), (223, 282, "Copa2024"), (1267, 107, "AFCON2023")]
UA = "Mozilla/5.0 (research; football-prediction)"


def _get(url: str, dst: Path) -> dict | list | None:
    if dst.exists():
        try:
            return json.loads(dst.read_text())
        except Exception:
            dst.unlink(missing_ok=True)
    r = subprocess.run(["curl", "-s", "--max-time", "60", "-H", f"User-Agent: {UA}", url],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(r.stdout)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def aggregate_match(events: list, home: str, away: str) -> dict | None:
    """Per-team aggregates from one match's events."""
    agg = {t: defaultdict(float) for t in (home, away)}
    for e in events:
        tm = (e.get("team") or {}).get("name")
        if tm not in agg:
            continue
        typ = (e.get("type") or {}).get("name")
        a = agg[tm]
        if typ == "Pass":
            a["passes"] += 1
            p = e.get("pass") or {}
            if (p.get("type") or {}).get("name") == "Corner":
                a["corners"] += 1
            if p.get("cross"):
                a["crosses"] += 1
        elif typ == "Shot":
            a["shots"] += 1
            a["xg"] += (e.get("shot") or {}).get("statsbomb_xg") or 0.0
            if ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
                a["goals"] += 1
        elif typ == "Pressure":
            a["pressures"] += 1
    tot_pass = agg[home]["passes"] + agg[away]["passes"]
    if tot_pass < 200:                 # malformed / incomplete event file
        return None
    rows = {}
    for tm, opp in ((home, away), (away, home)):
        a, o = agg[tm], agg[opp]
        rows[tm] = {
            "corners_for": a["corners"], "corners_against": o["corners"],
            "crosses": a["crosses"], "shots": a["shots"], "xg": round(a["xg"], 3),
            "passes": a["passes"], "pressures": a["pressures"],
            "goals_for": a["goals"], "goals_against": o["goals"],
            "possession": round(a["passes"] / tot_pass, 3),
        }
    return rows


def build() -> pd.DataFrame:
    if TEAM_CSV.exists():
        return pd.read_csv(TEAM_CSV)
    recs = []
    for cid, sid, label in COMPS:
        matches = _get(f"{RAW}/matches/{cid}/{sid}.json", CACHE / f"matches_{cid}_{sid}.json")
        if not matches:
            print(f"  {label}: matches unavailable"); continue
        n = 0
        for m in matches:
            mid = m["match_id"]
            home, away = m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]
            ev = _get(f"{RAW}/events/{mid}.json", CACHE / f"ev_{mid}.json")
            if not ev:
                continue
            rows = aggregate_match(ev, home, away)
            if not rows:
                continue
            for tm, r in rows.items():
                recs.append({"comp": label, "match_id": mid, "team": tm, **r})
            n += 1
        print(f"  {label}: {n} matches aggregated")
    df = pd.DataFrame(recs)
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_csv(TEAM_CSV, index=False)
    return df


def fit(df: pd.DataFrame) -> dict:
    import statsmodels.api as sm
    print(f"\nteam-match rows: {len(df)} | corners/team mean {df.corners_for.mean():.2f} "
          f"(total/game {2*df.corners_for.mean():.2f})")
    feats = ["crosses", "possession", "shots", "xg", "pressures"]
    print("\n=== univariate correlation with corners_for ===")
    for f in feats:
        print(f"  {f:11s} r = {df['corners_for'].corr(df[f]):+.3f}")
    print(f"  {'opp_poss':11s} r = {df['corners_for'].corr(1 - df['possession']):+.3f}  (opponent sitting back)")

    # Poisson GLM: corners_for ~ crosses + possession + shots (the mechanism)
    X = df[["crosses", "possession", "shots"]].copy()
    X = sm.add_constant(X)
    model = sm.GLM(df["corners_for"], X, family=sm.families.Poisson()).fit()
    print("\n=== Poisson regression corners_for ~ crosses + possession + shots ===")
    print(model.summary().tables[1])

    # the key elasticity the serving model needs: d(corners)/d(cross), measured
    # as a simple ratio AND the regression marginal at the mean
    cross_ratio = float((df["corners_for"].sum()) / (df["crosses"].sum()))
    beta_cross = float(model.params["crosses"])
    marg_cross = beta_cross * df["corners_for"].mean()   # Poisson marginal effect
    print(f"\ncorners/crosses raw ratio = {cross_ratio:.3f}  (was hand-set 0.28)")
    print(f"Poisson marginal d(corner)/d(cross) at mean = {marg_cross:.3f}")
    return {
        "n_rows": int(len(df)),
        "corners_per_team_mean": round(float(df.corners_for.mean()), 3),
        "corners_total_mean": round(float(2 * df.corners_for.mean()), 3),
        "corr": {f: round(float(df["corners_for"].corr(df[f])), 3) for f in feats},
        "cross_to_corner_ratio": round(cross_ratio, 3),
        "poisson": {"const": round(float(model.params["const"]), 4),
                    "crosses": round(beta_cross, 4),
                    "possession": round(float(model.params["possession"]), 4),
                    "shots": round(float(model.params["shots"]), 4)},
        "comps": [c[2] for c in COMPS],
    }


def main() -> None:
    df = build()
    if df.empty:
        print("no data"); return
    result = fit(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
