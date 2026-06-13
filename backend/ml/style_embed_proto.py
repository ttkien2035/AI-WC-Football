"""PROTOTYPE (measurement only — not wired to production): does a passing-
network STYLE EMBEDDING carry predictive signal BEYOND raw team strength?

Builds, from cached StatsBomb events (314 intl matches), a per-team "style
fingerprint" of passing-network descriptors, then runs a leave-one-tournament-
out test: baseline (strength only) vs baseline + style, for
  (1) match OUTCOME  (multinomial RPS), and
  (2) total GOALS    (MAE).
If style cuts the metric -> there's graph/style signal worth wiring in; if not,
we record "no incremental value at this scale" (a valid scientific result).

Leakage control: fingerprints & strength are computed on the TRAIN tournaments
only; teams seen only in the held-out tournament fall back to the global mean.

Run:  python -m ml.style_embed_proto
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "style_embed_proto.json"

STYLE_COLS = ["mean_pass_len", "forward_ratio", "final_third_ratio",
              "cross_ratio", "long_ball_ratio", "press_rate", "possession"]


def team_style_rows() -> pd.DataFrame:
    """Per-team-match passing-network style descriptors + goals + tournament."""
    tm = pd.read_csv(CACHE / "team_match.csv")            # comp, match_id, team, goals_*
    meta = {(r.match_id, r.team): r for r in tm.itertuples(index=False)}
    rows = []
    for f in sorted(CACHE.glob("ev_*.json")):
        mid = int(f.stem.split("_")[1])
        try:
            ev = json.loads(f.read_text())
        except Exception:
            continue
        agg = defaultdict(lambda: defaultdict(float))
        for e in ev:
            tmn = (e.get("team") or {}).get("name")
            if not tmn:
                continue
            a = agg[tmn]
            typ = (e.get("type") or {}).get("name")
            if typ == "Pass":
                p = e.get("pass") or {}
                a["passes"] += 1
                a["len_sum"] += p.get("length") or 0.0
                if p.get("length", 0) >= 35:
                    a["long"] += 1
                if p.get("cross"):
                    a["cross"] += 1
                end = p.get("end_location") or e.get("location")
                start = e.get("location")
                if end and start and end[0] > start[0]:
                    a["fwd"] += 1
                if end and end[0] >= 80:                  # into final third (120-long pitch)
                    a["f3"] += 1
            elif typ == "Pressure":
                a["press"] += 1
        teams = [t for t in agg if (mid, t) in meta]
        if len(teams) != 2:
            continue
        tot_pass = sum(agg[t]["passes"] for t in teams)
        if tot_pass < 200:
            continue
        for t in teams:
            a, m = agg[t], meta[(mid, t)]
            p = a["passes"] or 1
            rows.append({
                "comp": m.comp, "match_id": mid, "team": t,
                "mean_pass_len": a["len_sum"] / p,
                "forward_ratio": a["fwd"] / p,
                "final_third_ratio": a["f3"] / p,
                "cross_ratio": a["cross"] / p,
                "long_ball_ratio": a["long"] / p,
                "press_rate": a["press"] / p,
                "possession": a["passes"] / tot_pass,
                "goals_for": m.goals_for, "goals_against": m.goals_against,
                "xgd": m.xg,        # this-match xG (used only to derive strength fingerprint)
            })
    return pd.DataFrame(rows)


def _rps(p3, actual_idx):
    cp = c = 0.0
    for k in range(2):
        cp += p3[k]
        c += (cp - (1.0 if actual_idx <= k else 0.0)) ** 2
    return c / 2


def main() -> None:
    df = team_style_rows()
    print(f"team-match style rows: {len(df)} | matches: {df.match_id.nunique()}")
    # match-level frame: home = first team, away = second (order arbitrary -> symmetric test)
    matches = []
    for mid, g in df.groupby("match_id"):
        if len(g) != 2:
            continue
        h, a = g.iloc[0], g.iloc[1]
        matches.append((h, a))

    from sklearn.linear_model import LogisticRegression, PoissonRegressor

    comps = df.comp.unique()
    base_rps, full_rps, base_mae, full_mae, n = [], [], [], [], 0
    for test_comp in comps:
        tr = df[df.comp != test_comp]
        # train fingerprints (leakage-free) + global fallback
        fp = tr.groupby("team")[STYLE_COLS].mean()
        strength = tr.assign(d=tr.goals_for - tr.goals_against).groupby("team")["d"].mean()
        gmean = tr[STYLE_COLS].mean()
        gstr = float(strength.mean())

        def feat(team):
            s = fp.loc[team] if team in fp.index else gmean
            return s.values, (float(strength[team]) if team in strength.index else gstr)

        # build train/test design
        def design(rows):
            Xb, Xf, yo, yg = [], [], [], []
            for h, a in rows:
                hs, hstr = feat(h.team)
                as_, astr = feat(a.team)
                str_diff = hstr - astr
                base = [str_diff]
                style = list(hs - as_) + [float(np.linalg.norm(hs - as_))]   # diff + distance
                Xb.append(base); Xf.append(base + style)
                yo.append(0 if h.goals_for > a.goals_for else (1 if h.goals_for == a.goals_for else 2))
                yg.append(h.goals_for + a.goals_for)
            return np.array(Xb), np.array(Xf), np.array(yo), np.array(yg)

        tr_rows = [(g.iloc[0], g.iloc[1]) for _, g in df[df.comp != test_comp].groupby("match_id") if len(g) == 2]
        te_rows = [(g.iloc[0], g.iloc[1]) for _, g in df[df.comp == test_comp].groupby("match_id") if len(g) == 2]
        Xtb, Xtf, ytro, ytrg = design(tr_rows)
        Xeb, Xef, yeo, yeg = design(te_rows)
        if len(set(ytro)) < 3 or len(te_rows) < 5:
            continue

        for Xtr, Xte, store in ((Xtb, Xeb, "base"), (Xtf, Xef, "full")):
            clf = LogisticRegression(max_iter=1000, C=1.0).fit(Xtr, ytro)
            P = clf.predict_proba(Xte)
            cls = list(clf.classes_)
            for i, yo in enumerate(yeo):
                p3 = [P[i][cls.index(k)] if k in cls else 0.0 for k in (0, 1, 2)]
                (base_rps if store == "base" else full_rps).append(_rps(p3, yo))
            pr = PoissonRegressor(max_iter=500).fit(Xtr, ytrg)
            pred = pr.predict(Xte)
            mae = np.abs(pred - yeg)
            (base_mae if store == "base" else full_mae).extend(mae)
        n += len(te_rows)

    b_rps, f_rps = np.mean(base_rps), np.mean(full_rps)
    b_mae, f_mae = np.mean(base_mae), np.mean(full_mae)
    print(f"\n=== leave-one-tournament-out ({n} test matches) ===")
    print(f"  OUTCOME  RPS : strength {b_rps:.4f}  ->  +style {f_rps:.4f}  "
          f"({'BETTER' if f_rps < b_rps else 'WORSE'} {f_rps-b_rps:+.4f})")
    print(f"  TOTAL    MAE : strength {b_mae:.4f}  ->  +style {f_mae:.4f}  "
          f"({'BETTER' if f_mae < b_mae else 'WORSE'} {f_mae-b_mae:+.4f})")
    verdict = ("style adds signal -> worth wiring in" if (f_rps < b_rps - 1e-3 or f_mae < b_mae - 1e-2)
               else "NO incremental value beyond strength at this scale")
    print(f"\nVERDICT: {verdict}")
    OUT.write_text(json.dumps({
        "n_test_matches": int(n), "outcome_rps_base": round(float(b_rps), 4),
        "outcome_rps_with_style": round(float(f_rps), 4),
        "total_mae_base": round(float(b_mae), 4),
        "total_mae_with_style": round(float(f_mae), 4),
        "verdict": verdict,
    }, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
