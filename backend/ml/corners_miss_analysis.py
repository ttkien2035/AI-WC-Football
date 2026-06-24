"""Deep corners-miss analysis (measure-first). For each match compute the
corner-rate model's expected total + residual (actual - expected), then separate:
  (a) PRE-MATCH factors that could predict the residual  -> improvable signal
  (b) IN-MATCH factors that explain the misses           -> irreducible variance

Runs on the Sofascore corpus (richest: xG, big chances, final-third entries,
touches-in-box, shots, possession + corners). Rolling last-5, leakage-free.

Run:  python -m ml.corners_miss_analysis
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "espn" / "sofa_team_match.csv"
W, MIN_PRIOR, LINE = 5, 3, 9.5
ROLL = ["corners", "shots", "xg", "big_ch", "f3_entries", "box_touch", "poss"]


def _corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 5:
        return 0.0
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main():
    df = pd.read_csv(CSV).sort_values(["date", "event_id"]).reset_index(drop=True)
    for c in ROLL:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")

    # rolling team tendencies (for) + corners-against, leakage-free
    roll = defaultdict(lambda: {k: deque(maxlen=W) for k in ROLL})
    ca = defaultdict(lambda: deque(maxlen=W))   # corners conceded
    snap = {}
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        for me in (h, a):
            if len(roll[me.team]["corners"]) >= MIN_PRIOR:
                s = {k: (float(np.nanmean(roll[me.team][k])) if len(roll[me.team][k]) else np.nan)
                     for k in ROLL}
                s["ca"] = float(np.nanmean(ca[me.team])) if len(ca[me.team]) >= MIN_PRIOR else np.nan
                snap[(eid, me.team)] = s
        for me, opp in ((h, a), (a, h)):
            for k in ROLL:
                if pd.notna(getattr(me, k)):
                    roll[me.team][k].append(getattr(me, k))
            if pd.notna(me.corners):
                ca[opp.team].append(me.corners)

    rows = []
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        sh, sa = snap.get((eid, h.team)), snap.get((eid, a.team))
        if not sh or not sa or pd.isna(h.corners) or pd.isna(a.corners):
            continue
        # corner-rate baseline expected (the wired model)
        exp = 0.5 * (sh["corners"] + sa["ca"]) + 0.5 * (sa["corners"] + sh["ca"])
        actual = float(h.corners + a.corners)
        rows.append({
            "exp": exp, "actual": actual, "resid": actual - exp, "abserr": abs(actual - exp),
            # PRE-MATCH matchup tendencies (candidate residual predictors)
            "tot_shots": sh["shots"] + sa["shots"], "tot_xg": sh["xg"] + sa["xg"],
            "tot_bigch": sh["big_ch"] + sa["big_ch"], "tot_f3": sh["f3_entries"] + sa["f3_entries"],
            "tot_box": sh["box_touch"] + sa["box_touch"],
            "poss_imb_tend": abs(sh["poss"] - sa["poss"]),
            "cornrate_sum": sh["corners"] + sa["corners"] + sh["ca"] + sa["ca"],
            # IN-MATCH actuals (explain misses, NOT usable pre-match)
            "m_margin": abs(h.goals_for - a.goals_for), "m_goals": h.goals_for + a.goals_for,
            "m_poss_gap": abs((h.poss or 50) - (a.poss or 50)),
            "m_shots": (h.shots or 0) + (a.shots or 0),
        })
    M = pd.DataFrame(rows).dropna(subset=["exp", "tot_shots", "tot_xg"]).reset_index(drop=True)
    n = len(M)
    print(f"=== corners deep-miss analysis (Sofascore, n={n}) ===")
    print(f"corner-rate model: MAE {M.abserr.mean():.2f}  bias(exp-act) {(-M.resid.mean()):+.2f}"
          f"  R²(exp,act) {_corr(M.exp, M.actual)**2:.3f}")

    print("\n[a] PRE-MATCH factor vs RESIDUAL (|corr| big => improvable signal):")
    for k in ("tot_shots", "tot_xg", "tot_bigch", "tot_f3", "tot_box", "poss_imb_tend", "cornrate_sum"):
        print(f"    corr(resid, {k:14}) = {_corr(M[k], M.resid):+.3f}")

    print("\n[b] IN-MATCH factor vs |error| (explains misses, NOT pre-match usable):")
    for k in ("m_margin", "m_goals", "m_poss_gap", "m_shots"):
        print(f"    corr(|err|, {k:12}) = {_corr(M[k], M.abserr):+.3f}")
    print(f"    corr(actual_corners, m_shots)   = {_corr(M.m_shots, M.actual):+.3f}")
    print(f"    corr(actual_corners, m_poss_gap)= {_corr(M.m_poss_gap, M.actual):+.3f}")

    # out-of-sample test: does adding the top pre-match factor beat corner-rate alone?
    from sklearn.linear_model import PoissonRegressor
    from sklearn.model_selection import TimeSeriesSplit
    tss = TimeSeriesSplit(n_splits=4)

    def cv(cols):
        maes, hits = [], []
        for i, j in tss.split(M):
            tr, te = M.iloc[i], M.iloc[j]
            if len(te) < 15:
                continue
            pr = PoissonRegressor(max_iter=900, alpha=1.0).fit(tr[cols], tr.actual)
            p = pr.predict(te[cols])
            maes.append(float(np.mean(np.abs(p - te.actual.values))))
            hits.append(float(np.mean([(pp > LINE) == (aa > LINE)
                                       for pp, aa in zip(p, te.actual.values) if aa != LINE])))
        return np.mean(maes), np.mean(hits)

    print("\n[c] out-of-sample (4-fold TS-CV) — add factor to corner-rate baseline:")
    base_cols = ["exp"]
    for tag, cols in (("corner-rate", base_cols),
                      ("+shots", base_cols + ["tot_shots"]),
                      ("+xg", base_cols + ["tot_xg"]),
                      ("+poss_imb", base_cols + ["poss_imb_tend"])):
        m2 = M.dropna(subset=cols)
        mae, hit = cv(cols) if not m2[cols].isna().any().any() else (float("nan"), float("nan"))
        print(f"    {tag:12} MAE {mae:.2f}  O/U hit {hit*100:.0f}%")

    # [d] SHRINKAGE sweep: residual ~ -0.25*cornrate_sum says recent rates OVER-state
    # (mean-reversion). exp_shrunk = mean + s*(exp-mean). s<1 should cut MAE.
    print("\n[d] shrink expected toward league mean — exp_s = mean + s*(exp-mean):")
    mean = M.actual.mean()
    print(f"    {'s':>5} {'MAE':>6} {'O/U hit@9.5':>12}")
    for s in (1.0, 0.7, 0.5, 0.3, 0.0):
        pred = mean + s * (M.exp - mean)
        mae = float(np.mean(np.abs(pred - M.actual)))
        hit = float(np.mean([(p > LINE) == (a > LINE)
                             for p, a in zip(pred, M.actual) if a != LINE]))
        flag = "  <-- flat base" if s == 0.0 else ""
        print(f"    {s:>5.1f} {mae:>6.2f} {hit*100:>11.0f}%{flag}")


if __name__ == "__main__":
    main()
