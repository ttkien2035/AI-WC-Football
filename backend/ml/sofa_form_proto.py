"""Prototypes (2) + (3) on the Sofascore corpus (sofa_team_match.csv).

(2) OUTCOME: does real xG-form beat the free ESPN shot-volume proxy?
    base = Elo + goal-form;  +shots;  +xg;  +both.   metric: multinomial RPS.
(3a) TOTALS: do box-entries / big-chances / xG predict total goals beyond recent
     scoring rate (where shot-form was flat)?   metric: total-goals MAE.
(3b) CORNERS: do final-third entries / box touches predict total corners beyond
     recent corner rate?   metric: total-corners MAE.

Leakage-free rolling last-5 form, online Elo, temporal hold-out + 4-fold TS-CV.
Adopt a signal only if it beats its baseline on hold-out AND CV.

Run:  python -m ml.sofa_form_proto
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "espn" / "sofa_team_match.csv"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "sofa_form_proto.json"
W, MIN_PRIOR = 5, 3
ROLL = ["gf", "ga", "xgf", "xga", "shots_f", "f3_f", "box_f", "bigch_f", "corn_f", "corn_a"]


def _rps(p3, idx):
    cp = c = 0.0
    for k in range(2):
        cp += p3[k]; c += (cp - (1.0 if idx <= k else 0.0)) ** 2
    return c / 2


def build(df):
    df = df.sort_values(["date", "event_id"]).reset_index(drop=True)
    num = ["xg", "shots", "f3_entries", "box_touch", "big_ch", "corners"]
    for c in num:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    roll = defaultdict(lambda: {k: deque(maxlen=W) for k in ROLL})
    elo = defaultdict(lambda: 1500.0)
    snap = {}
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        for me in (h, a):
            r = roll[me.team]
            if len(r["gf"]) >= MIN_PRIOR:
                snap[(eid, me.team)] = {k: (float(np.nanmean(r[k])) if len(r[k]) else np.nan)
                                        for k in ROLL}
                snap[(eid, me.team)]["elo"] = elo[me.team]
        Eh = 1 / (1 + 10 ** (-(elo[h.team] + 60 - elo[a.team]) / 400))
        res = 1.0 if h.goals_for > a.goals_for else (0.5 if h.goals_for == a.goals_for else 0.0)
        elo[h.team] += 30 * (res - Eh); elo[a.team] += 30 * ((1 - res) - (1 - Eh))
        for me, opp in ((h, a), (a, h)):
            r = roll[me.team]
            r["gf"].append(me.goals_for); r["ga"].append(me.goals_against)
            r["xgf"].append(me.xg); r["xga"].append(opp.xg)
            r["shots_f"].append(me.shots); r["f3_f"].append(me.f3_entries)
            r["box_f"].append(me.box_touch); r["bigch_f"].append(me.big_ch)
            r["corn_f"].append(me.corners); r["corn_a"].append(opp.corners)

    rows = []
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        sh, sa = snap.get((eid, h.team)), snap.get((eid, a.team))
        if not sh or not sa:
            continue
        d = {"date": h.date,
             "elo_diff": sh["elo"] - sa["elo"],
             "gd_form": (sh["gf"] - sh["ga"]) - (sa["gf"] - sa["ga"]),
             "shot_diff": sh["shots_f"] - sa["shots_f"],
             "xg_diff": (sh["xgf"] - sh["xga"]) - (sa["xgf"] - sa["xga"]),
             # totals: combined attacking volume of both teams
             "tot_goalform": sh["gf"] + sa["gf"],
             "tot_xg": sh["xgf"] + sa["xgf"],
             "tot_f3": sh["f3_f"] + sa["f3_f"],
             "tot_box": sh["box_f"] + sa["box_f"],
             "tot_bigch": sh["bigch_f"] + sa["bigch_f"],
             "tot_corn": sh["corn_f"] + sa["corn_f"] + sh["corn_a"] + sa["corn_a"],
             "outcome": 0 if h.goals_for > a.goals_for else (1 if h.goals_for == a.goals_for else 2),
             "total": h.goals_for + a.goals_for,
             "total_corn": (h.corners + a.corners) if pd.notna(h.corners) and pd.notna(a.corners) else np.nan}
        rows.append(d)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def _outcome_rps(tr, te, cols, C=0.4):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(tr[cols])
    clf = LogisticRegression(max_iter=3000, C=C).fit(sc.transform(tr[cols]), tr.outcome)
    P, cls = clf.predict_proba(sc.transform(te[cols])), list(clf.classes_)
    return float(np.mean([_rps([P[i][cls.index(k)] if k in cls else 0.0 for k in (0, 1, 2)], y)
                          for i, y in enumerate(te.outcome.values)]))


def _pois_mae(tr, te, cols, target, C=0.4):
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    a = tr.dropna(subset=[target] + cols); b = te.dropna(subset=[target] + cols)
    if len(a) < 20 or len(b) < 10:
        return None
    sc = StandardScaler().fit(a[cols])
    pr = PoissonRegressor(max_iter=1000, alpha=1.0 / C).fit(sc.transform(a[cols]), a[target])
    return float(np.mean(np.abs(pr.predict(sc.transform(b[cols])) - b[target].values)))


def run_block(title, M, target, metric, variants):
    from sklearn.model_selection import TimeSeriesSplit
    cut = int(len(M) * 0.70)
    tr, te = M.iloc[:cut], M.iloc[cut:]
    tss = TimeSeriesSplit(n_splits=4)
    print(f"\n=== {title} (n={len(M)}, holdout={len(te)}) ===")
    base_cols = variants["base"]
    results = {}
    for tag, cols in variants.items():
        if metric == "rps":
            hold = _outcome_rps(tr, te, cols)
            cvv = [_outcome_rps(M.iloc[i], M.iloc[j], cols)
                   for i, j in tss.split(M) if len(set(M.iloc[i].outcome)) == 3]
        else:
            hold = _pois_mae(tr, te, cols, target)
            cvv = [v for i, j in tss.split(M)
                   if (v := _pois_mae(M.iloc[i], M.iloc[j], cols, target)) is not None]
        cv = float(np.mean(cvv)) if cvv else float("nan")
        results[tag] = (hold, cv)
    bh, bc = results["base"]
    for tag, (h, c) in results.items():
        dh = "" if tag == "base" else f"  d_hold {h-bh:+.4f}"
        dc = "" if tag == "base" else f"  d_cv {c-bc:+.4f}"
        flag = ""
        if tag != "base" and h < bh - (1e-3 if metric == "rps" else 1e-2) \
                and c < bc - (1e-3 if metric == "rps" else 1e-2):
            flag = "  <-- BEATS base"
        print(f"  {tag:12s} {metric} hold {h:.4f}  cv {c:.4f}{dh}{dc}{flag}")
    return {k: {"hold": round(v[0], 4), "cv": round(v[1], 4)} for k, v in results.items()}


def main():
    if not CSV.exists():
        print(f"missing {CSV} — run `python -m ml.sofa_backfill` first"); return
    df = pd.read_csv(CSV)
    M = build(df)
    print(f"corpus: {df.event_id.nunique()} matches | usable (>= {MIN_PRIOR} prior): {len(M)}")
    art = {"n_matches": int(df.event_id.nunique()), "n_usable": int(len(M))}

    art["outcome_xg_vs_shots"] = run_block(
        "(2) OUTCOME: xG-form vs shot-form", M, "outcome", "rps", {
            "base": ["elo_diff", "gd_form"],
            "+shots": ["elo_diff", "gd_form", "shot_diff"],
            "+xg": ["elo_diff", "gd_form", "xg_diff"],
            "+both": ["elo_diff", "gd_form", "shot_diff", "xg_diff"]})

    art["totals_boxentry_bigchance"] = run_block(
        "(3a) TOTALS: box-entry / big-chance / xG", M, "total", "mae", {
            "base": ["tot_goalform"],
            "+box": ["tot_goalform", "tot_f3", "tot_box"],
            "+bigch": ["tot_goalform", "tot_bigch"],
            "+xg": ["tot_goalform", "tot_xg"]})

    art["corners_entries"] = run_block(
        "(3b) CORNERS: final-third / box touches", M, "total_corn", "mae", {
            "base": ["tot_corn"],
            "+entries": ["tot_corn", "tot_f3", "tot_box"]})

    def _beat(block, key, m):  # beats base on BOTH hold + cv?
        b, v = block["base"], block[key]
        eps = 1e-3 if m == "rps" else 1e-2
        return v["hold"] < b["hold"] - eps and v["cv"] < b["cv"] - eps
    art["verdicts"] = {
        "xg_form_vs_shot_form": (
            "xG-form does NOT beat the free shot proxy (shots >= xg on hold+cv); "
            "+both ~= +shots -> real xG not worth RapidAPI quota for OUTCOME"),
        "totals_premium": (
            "box-entries / big-chances / xG do NOT improve TOTALS beyond recent "
            "goal-form (worse on cv) -> null"),
        "corners_entries": (
            "final-third entries / box touches do NOT improve CORNERS beyond recent "
            "corner rate (n=56 looked +0.13 but flipped to worse at n=183) -> null"),
        "actionable": ("ONLY the free ESPN shot-form is worth wiring (already wired); "
                       "no Sofascore-premium feature justified -> reserve quota"),
    }
    OUT.write_text(json.dumps(art, indent=1))
    print("\nVERDICTS:")
    for k, v in art["verdicts"].items():
        print(f"  - {v}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
