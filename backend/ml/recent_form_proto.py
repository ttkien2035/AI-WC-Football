"""RE-TEST (measure-first, pre-match): do recent-form EVENT aggregates
(shots, shots-on-target, possession, crosses, defensive actions) — backfilled
for the WC2026 cycle from ESPN — add PRE-MATCH predictive value BEYOND a
strength + scoring-rate baseline?

This is the decision gate for the batch-backfill idea: the static passing-network
STYLE embedding was already shown to add no value (style_embed_proto, LOTO null).
Here we test a DIFFERENT thing — *recent-form* event signal on real recent
internationals (the population we actually serve).

Baseline  = elo_diff (online, pre-match) + rolling goal-form (last 5).   [result-only]
Full      = baseline + rolling event-form (last 5).                      [+ ESPN events]

Temporal split (train = earlier 70%, test = later 30%) — predict future from past.
Metrics:  OUTCOME multinomial RPS, TOTAL-goals MAE.  Adopt only if Full beats Base.

Run:  python -m ml.recent_form_proto
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "espn" / "intl_team_match.csv"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "recent_form_proto.json"

EVENT_COLS = ["shots", "sot", "poss", "crosses", "shot_acc", "def_act", "long_balls"]
WINDOW = 5
MIN_PRIOR = 3


def _rps(p3, actual_idx):
    cp = c = 0.0
    for k in range(2):
        cp += p3[k]
        c += (cp - (1.0 if actual_idx <= k else 0.0)) ** 2
    return c / 2


def build_match_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological pass: snapshot leakage-free pre-match Elo + rolling form per
    team, then join the two team-rows of each match into one match row."""
    df = df.sort_values(["date", "event_id"]).reset_index(drop=True)
    # derived per-row event signals
    df["shot_acc"] = np.where(df["shots"] > 0, df["sot"] / df["shots"], 0.0)
    df["def_act"] = df.get("tackles", 0).fillna(0) + df.get("intercept", 0).fillna(0) \
        + df.get("clearance", 0).fillna(0)
    for c in EVENT_COLS:
        if c not in df:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    elo = defaultdict(lambda: 1500.0)
    formG = defaultdict(lambda: deque(maxlen=WINDOW))   # goals for/against tuples
    formE = defaultdict(lambda: {c: deque(maxlen=WINDOW) for c in EVENT_COLS})
    snaps = {}   # (event_id, team) -> snapshot dict

    # iterate match by match in time order so Elo updates use only the past
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        rows = {r.is_home: r for r in g.itertuples(index=False)}
        if 1 not in rows or 0 not in rows:
            rows = {i: r for i, r in enumerate(g.itertuples(index=False))}
            h, a = rows[0], rows[1]
        else:
            h, a = rows[1], rows[0]
        for me, opp in ((h, a), (a, h)):
            t = me.team
            gf = [x[0] for x in formG[t]]
            ga = [x[1] for x in formG[t]]
            snap = {
                "elo": elo[t],
                "gf": float(np.mean(gf)) if len(gf) >= MIN_PRIOR else np.nan,
                "ga": float(np.mean(ga)) if len(ga) >= MIN_PRIOR else np.nan,
            }
            for c in EVENT_COLS:
                dq = formE[t][c]
                snap[c] = float(np.mean(dq)) if len(dq) >= MIN_PRIOR else np.nan
            snaps[(eid, t)] = snap
        # update Elo on result (K=30, no MOV — pure strength)
        Eh = 1.0 / (1.0 + 10 ** (-(elo[h.team] + 60 - elo[a.team]) / 400))  # +60 home edge
        res = 1.0 if h.goals_for > a.goals_for else (0.5 if h.goals_for == a.goals_for else 0.0)
        elo[h.team] += 30 * (res - Eh)
        elo[a.team] += 30 * ((1 - res) - (1 - Eh))
        # update form deques AFTER snapshot
        for me in (h, a):
            t = me.team
            formG[t].append((me.goals_for, me.goals_against))
            for c in EVENT_COLS:
                formE[t][c].append(getattr(me, c))

    # assemble match rows
    out = []
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]  # home first
        h, a = gl.iloc[0], gl.iloc[1]
        sh, sa = snaps.get((eid, h.team)), snaps.get((eid, a.team))
        if not sh or not sa:
            continue
        row = {"event_id": eid, "date": h.date, "league": h.league,
               "elo_diff": sh["elo"] - sa["elo"],
               "h_gf": sh["gf"], "h_ga": sh["ga"], "a_gf": sa["gf"], "a_ga": sa["ga"]}
        for c in EVENT_COLS:
            row[f"h_{c}"], row[f"a_{c}"] = sh[c], sa[c]
        # parsimonious DIFF features (home - away) — 1 param each, less overfit
        for c in EVENT_COLS:
            row[f"d_{c}"] = sh[c] - sa[c]
        row["d_goalform"] = (sh["gf"] - sh["ga"]) - (sa["gf"] - sa["ga"])
        row["outcome"] = 0 if h.goals_for > a.goals_for else (1 if h.goals_for == a.goals_for else 2)
        row["total"] = h.goals_for + a.goals_for
        out.append(row)
    return pd.DataFrame(out).dropna().sort_values("date").reset_index(drop=True)


def main() -> None:
    if not CSV.exists():
        print(f"missing {CSV} — run `python -m ml.espn_backfill` first")
        return
    raw = pd.read_csv(CSV)
    M = build_match_frame(raw)
    print(f"usable matches (>= {MIN_PRIOR} prior games both teams): {len(M)}")
    if len(M) < 120:
        print("sample too small for a trustworthy split — interpret with caution")

    from sklearn.linear_model import LogisticRegression, PoissonRegressor
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler

    # three feature sets: result-only baseline; baseline + lean event-diffs (3);
    # baseline + full event form (14). Lean+regularized guards against false-null
    # from over-parameterization on a modest sample.
    base_cols = ["elo_diff", "h_gf", "h_ga", "a_gf", "a_ga"]
    lean_cols = base_cols + ["d_shots", "d_sot", "d_poss"]
    full_cols = base_cols + [f"{s}_{c}" for c in EVENT_COLS for s in ("h", "a")]
    sets = {"base": base_cols, "lean+events": lean_cols, "full+events": full_cols}

    def evaluate(tr, te, cols, C):
        sc = StandardScaler().fit(tr[cols])
        Xtr, Xte = sc.transform(tr[cols]), sc.transform(te[cols])
        clf = LogisticRegression(max_iter=3000, C=C).fit(Xtr, tr.outcome)
        P, cls = clf.predict_proba(Xte), list(clf.classes_)
        rps = [_rps([P[i][cls.index(k)] if k in cls else 0.0 for k in (0, 1, 2)], yo)
               for i, yo in enumerate(te.outcome.values)]
        pr = PoissonRegressor(max_iter=1000, alpha=1.0 / C).fit(Xtr, tr.total)
        mae = np.abs(pr.predict(Xte) - te.total.values)
        return float(np.mean(rps)), float(np.mean(mae))

    # (1) single temporal hold-out
    cut = int(len(M) * 0.70)
    tr, te = M.iloc[:cut], M.iloc[cut:]
    print(f"\n--- temporal hold-out: train {len(tr)} (..{tr.date.max()}) | test {len(te)} ---")
    hold = {tag: evaluate(tr, te, cols, C=0.5) for tag, cols in sets.items()}

    # (2) time-series CV (4 expanding folds) for a stable estimate; strong reg (C=0.25)
    tss = TimeSeriesSplit(n_splits=4)
    cv = {tag: [[], []] for tag in sets}
    for tri, tei in tss.split(M):
        a, b = M.iloc[tri], M.iloc[tei]
        if len(set(a.outcome)) < 3 or len(b) < 20:
            continue
        for tag, cols in sets.items():
            r, m = evaluate(a, b, cols, C=0.25)
            cv[tag][0].append(r); cv[tag][1].append(m)

    def fmt(b, x):
        return f"{x:.4f} ({'BETTER' if x < b else 'WORSE '} {x-b:+.4f})"
    b_h = hold["base"]; b_cv = (np.mean(cv["base"][0]), np.mean(cv["base"][1]))
    print(f"\n{'set':14s}  {'RPS holdout':>22s}  {'RPS cv':>22s}  {'MAE cv':>22s}")
    summary = {}
    for tag in sets:
        h_r, h_m = hold[tag]
        c_r, c_m = float(np.mean(cv[tag][0])), float(np.mean(cv[tag][1]))
        summary[tag] = {"rps_holdout": round(h_r, 4), "mae_holdout": round(h_m, 4),
                        "rps_cv": round(c_r, 4), "mae_cv": round(c_m, 4)}
        print(f"{tag:14s}  {fmt(b_h[0], h_r):>22s}  {fmt(b_cv[0], c_r):>22s}  {fmt(b_cv[1], c_m):>22s}")

    # adopt only if an event set beats base on BOTH the holdout AND the CV mean
    def beats(tag):
        s = summary[tag]
        return ((s["rps_cv"] < b_cv[0] - 1e-3 and s["rps_holdout"] < b_h[0] - 1e-3)
                or (s["mae_cv"] < b_cv[1] - 1e-2 and s["mae_holdout"] < b_h[1] - 1e-2))
    winners = [t for t in ("lean+events", "full+events") if beats(t)]
    verdict = (f"recent-form EVENTS add pre-match value ({', '.join(winners)}) -> wire in"
               if winners else
               "NO incremental value beyond strength+goal-form (robust across holdout + 4-fold CV)")
    print(f"\nVERDICT: {verdict}")

    # robustness: per-fold lean-vs-base RPS delta (is it consistent, not 1-fold luck?)
    deltas = [r - b for r, b in zip(cv["lean+events"][0], cv["base"][0])]
    print(f"\nper-fold RPS delta (lean - base): "
          + "  ".join(f"{d:+.4f}" for d in deltas)
          + f"   [{sum(1 for d in deltas if d < 0)}/{len(deltas)} folds improve]")
    # which feature drives it: standardized logistic coefs on full data (lean set)
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(M[lean_cols])
    clf = LogisticRegression(max_iter=3000, C=0.25).fit(sc.transform(M[lean_cols]), M.outcome)
    # coef magnitude for home-win (class 0) — bigger |coef| = more influence
    coefs = dict(zip(lean_cols, clf.coef_[list(clf.classes_).index(0)]))
    print("lean-set standardized coefs (home-win):")
    for c in ["d_shots", "d_sot", "d_poss"]:
        print(f"   {c:10s} {coefs[c]:+.3f}")
    OUT.write_text(json.dumps({
        "n_matches_usable": int(len(M)), "n_test_holdout": int(len(te)),
        "baseline_rps_cv": round(float(b_cv[0]), 4), "baseline_mae_cv": round(float(b_cv[1]), 4),
        "sets": summary, "verdict": verdict,
    }, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
