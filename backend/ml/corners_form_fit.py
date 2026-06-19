"""Pre-match CORNERS study + prior fit (measure-first, user-priority target).

Question: does each team's RECENT corner for/against rate (from open ESPN
internationals) predict a match's total corners better than the generic base
the production model falls back to pre-tournament? If yes, seed a per-team
corner-form prior (like shot_form) so the corners model has team-specific data
from match 1 instead of only base x lambda-intensity.

Compares, leakage-free (rolling last-5, temporal hold-out + 4-fold TS-CV):
  A flat   : rolling league-mean total corners (≈ production's pre-match base)
  B rate   : (home corners-for ⊕ away corners-against) + (away cf ⊕ home ca)
  C rate+× : B plus recent crossing volume
metrics: total-corners MAE + O/U hit-rate at line 9.5.

Emits corner_form.json {team: {cf, ca, n}} for serving when B/C beats A.

Run:  python -m ml.corners_form_fit
"""
from __future__ import annotations

import json
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "espn" / "intl_team_match.csv"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "corner_form.json"
W, MIN_PRIOR, LINE = 5, 3, 9.5


def _norm(s: str) -> str:
    s = (s or "").replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def build():
    df = pd.read_csv(CSV).sort_values(["date", "event_id"]).reset_index(drop=True)
    for c in ("corners", "crosses"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    # rolling for/against corner + cross rates per team, leakage-free
    cf = defaultdict(lambda: deque(maxlen=W))   # corners won
    ca = defaultdict(lambda: deque(maxlen=W))   # corners conceded
    cx = defaultdict(lambda: deque(maxlen=W))   # crosses
    snap, latest = {}, {}
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        for me in (h, a):
            if len(cf[me.team]) >= MIN_PRIOR:
                snap[(eid, me.team)] = (float(np.nanmean(cf[me.team])),
                                        float(np.nanmean(ca[me.team])),
                                        float(np.nanmean(cx[me.team])) if len(cx[me.team]) else np.nan)
        for me, opp in ((h, a), (a, h)):
            if pd.notna(me.corners):
                cf[me.team].append(me.corners); ca[opp.team].append(me.corners)
            if pd.notna(me.crosses):
                cx[me.team].append(me.crosses)
            if len(cf[me.team]) >= MIN_PRIOR:
                latest[me.team] = (me.date, float(np.nanmean(cf[me.team])),
                                   float(np.nanmean(ca[me.team])), len(cf[me.team]))
    rows = []
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        sh, sa = snap.get((eid, h.team)), snap.get((eid, a.team))
        if not sh or not sa or pd.isna(h.corners) or pd.isna(a.corners):
            continue
        rows.append({"hcf": sh[0], "hca": sh[1], "hcx": sh[2],
                     "acf": sa[0], "aca": sa[1], "acx": sa[2],
                     "total": float(h.corners + a.corners)})
    return pd.DataFrame(rows).dropna(subset=["hcf", "hca", "acf", "aca"]).reset_index(drop=True), latest


def _mae_hit(pred, act):
    mae = float(np.mean(np.abs(pred - act)))
    hit = float(np.mean([(p > LINE) == (a > LINE) for p, a in zip(pred, act) if a != LINE]))
    return mae, hit


def main():
    if not CSV.exists():
        print(f"missing {CSV}"); return
    M, latest = build()
    print(f"usable matches (>= {MIN_PRIOR} prior both teams): {len(M)} | mean total {M.total.mean():.2f}")
    from sklearn.linear_model import PoissonRegressor
    from sklearn.model_selection import TimeSeriesSplit

    cut = int(len(M) * 0.70)
    tr, te = M.iloc[:cut], M.iloc[cut:]
    mu = tr.total.mean()

    def predict(model, d):
        if model == "A":                       # flat league mean
            return np.full(len(d), mu)
        # mechanism blend: each side = mean(own corners-for, opp corners-against)
        ph = 0.5 * d.hcf + 0.5 * d.aca
        pa = 0.5 * d.acf + 0.5 * d.hca
        return (ph + pa).values

    def fit_pois(cols):
        pr = PoissonRegressor(max_iter=900, alpha=0.5).fit(tr[cols], tr.total)
        return pr

    # evaluate hold-out
    print(f"\n{'model':10} {'MAE':>6} {'O/U hit@9.5':>12}")
    res = {}
    for tag, fn in (("A flat", lambda d: predict("A", d)),
                    ("B rate", lambda d: predict("B", d))):
        mae, hit = _mae_hit(fn(te), te.total.values)
        res[tag] = (mae, hit)
        print(f"{tag:10} {mae:>6.2f} {hit*100:>11.0f}%")
    for tag, cols in (("B rate(fit)", ["hcf", "hca", "acf", "aca"]),
                      ("C rate+×", ["hcf", "hca", "acf", "aca", "hcx", "acx"])):
        d_tr = tr.dropna(subset=cols); d_te = te.dropna(subset=cols)
        pr = PoissonRegressor(max_iter=900, alpha=0.5).fit(d_tr[cols], d_tr.total)
        mae, hit = _mae_hit(pr.predict(d_te[cols]), d_te.total.values)
        print(f"{tag:10} {mae:>6.2f} {hit*100:>11.0f}%  (n_te {len(d_te)})")

    # 4-fold TS-CV for the A vs B headline (stability)
    tss = TimeSeriesSplit(n_splits=4)
    aA = aB = hA = hB = k = 0
    for i, j in tss.split(M):
        a_te = M.iloc[j]
        mu_i = M.iloc[i].total.mean()
        mA, h_A = _mae_hit(np.full(len(a_te), mu_i), a_te.total.values)
        mB, h_B = _mae_hit(predict("B", a_te), a_te.total.values)
        aA += mA; aB += mB; hA += h_A; hB += h_B; k += 1
    print(f"\n4-fold TS-CV: A flat MAE {aA/k:.2f} hit {hA/k*100:.0f}%  |  "
          f"B rate MAE {aB/k:.2f} hit {hB/k*100:.0f}%")

    # correlation: does rolling corner-rate sum track actual total?
    rate_sum = (0.5*(M.hcf+M.aca) + 0.5*(M.acf+M.hca))
    c = np.corrcoef(rate_sum, M.total)[0, 1]
    print(f"corr(team corner-rate model, actual total) = {c:+.2f}")

    # emit per-team corner-form table (for serving) keyed by WC TLA
    from app.static_data import TEAMS
    ALIAS = {"turkiye": "TUR", "cotedivoire": "CIV", "ivorycoast": "CIV",
             "korearepublic": "KOR", "southkorea": "KOR", "iranislamicrepublic": "IRN",
             "bosniaherzegovina": "BIH", "bosniaandherzegovina": "BIH",
             "capeverde": "CPV", "caboverde": "CPV", "unitedstates": "USA", "curacao": "CUW",
             "uruguay": "URY"}
    name2tla = {_norm(v["name"]): k for k, v in TEAMS.items()}
    name2tla.update(ALIAS)
    teams = {}
    for team, (dt, cfv, cav, n) in latest.items():
        tla = name2tla.get(_norm(team))
        if tla:
            teams[tla] = {"name": team, "cf": round(cfv, 2), "ca": round(cav, 2),
                          "n": n, "as_of": dt}
    art = {"window": W, "line": LINE, "league_mean_total": round(float(mu), 2),
           "model": "0.5*(cf+opp_ca) per side", "n_fit": len(M),
           "corr_model_actual": round(float(c), 3), "n_teams": len(teams), "teams": teams}
    OUT.write_text(json.dumps(art, indent=1))
    covered = sum(1 for t in TEAMS if t in teams)
    print(f"\nWC2026 coverage: {covered}/{len(TEAMS)} teams (wrote {OUT})")


if __name__ == "__main__":
    main()
