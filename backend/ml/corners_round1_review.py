"""Round-1 (WC-2026 group MD1) corners O/U review — measure-first.

Fetches live pre-match snapshots + actual results from prod, joins the OBJECTIVE
match factors that drive real corner counts (crosses, possession, goal margin,
total goals, red cards, shots), and asks scientifically:
  1. does the crossing mechanism (cross x 0.389) actually explain real corners?
  2. what objective factor drives the prediction error (over-pred in mismatches?)
  3. would a softer lambda-intensity exponent cut the error? (sweep + re-grade)

Run:  python -m ml.corners_round1_review
      CORNERS_BASE_URL=http://localhost ADMIN_TOKEN=... python -m ml.corners_round1_review
"""
from __future__ import annotations

import json
import os
import statistics as st
import urllib.request

from app.config import settings
from app.engine.periods import corners_at_line

BASE = os.environ.get("CORNERS_BASE_URL", "http://42.96.56.55")
TOKEN = os.environ.get("ADMIN_TOKEN", "ttkien2035")
MU = settings.goals_mu
CROSS_RATIO = settings.corners_cross_to_corner


def _get(path: str, admin: bool = False):
    h = {"X-Admin-Token": TOKEN} if admin else {}
    return json.load(urllib.request.urlopen(
        urllib.request.Request(BASE + path, headers=h), timeout=45))


def _corr(a, b):
    if len(a) < 3:
        return 0.0
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def _side(total, line):
    return "over" if total > line else ("push" if total == line else "under")


def main() -> None:
    rev = _get("/api/pipeline/review", admin=True)["matches"]
    results = {r["id"]: r for r in _get("/api/results?n=60")["results"]}

    rows = []
    for m in rev:
        c = (m.get("compare") or {})
        cor = c.get("corners") or {}
        if not (cor.get("pick") and cor.get("actual_total") is not None):
            continue
        r = results.get(m["match_id"], {})
        stats = r.get("stats") or {}
        crs = stats.get("crosses") or {}
        pss = stats.get("possession") or {}
        sh_on = stats.get("shots_on") or {}
        gh, ga = m["score"]["home"], m["score"]["away"]
        reds = m.get("factors", {}).get("red_cards") or {}
        cross_tot = (crs.get("home") or 0) + (crs.get("away") or 0)
        poss_gap = abs((pss.get("home") or 50) - (pss.get("away") or 50))
        rows.append({
            "m": f'{m["home"]["tla"]}-{m["away"]["tla"]}',
            "line": cor["line"], "pick": cor["pick"], "exp": cor.get("expected_total"),
            "act": float(cor["actual_total"]), "hit": cor.get("hit"),
            "xg": (c.get("total_goals") or {}).get("pred_xg"),     # lambda sum
            "margin": abs(gh - ga), "tot_goals": gh + ga,
            "cross_tot": cross_tot or None, "poss_gap": poss_gap,
            "reds": (reds.get("home") or 0) + (reds.get("away") or 0),
        })

    n = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    print(f"=== Corners O/U round-1 review ({n} gradable) ===")
    print(f"hit-rate: {hits}/{n} = {hits/n*100:.0f}%  |  mean exp {st.mean([r['exp'] for r in rows]):.2f}"
          f"  mean act {st.mean([r['act'] for r in rows]):.2f}"
          f"  bias(exp-act) {st.mean([r['exp']-r['act'] for r in rows]):+.2f}")

    # 1) crossing mechanism: do real corners track real crosses?
    cx = [(r["cross_tot"], r["act"]) for r in rows if r["cross_tot"]]
    if cx:
        print(f"\n[1] crossing mechanism — n={len(cx)} with cross data")
        print(f"    corr(actual_crosses, actual_corners) = {_corr([a for a,_ in cx],[b for _,b in cx]):+.2f}")
        print(f"    mean crosses {st.mean([a for a,_ in cx]):.1f} x ratio {CROSS_RATIO} "
              f"= implied {st.mean([a for a,_ in cx])*CROSS_RATIO:.1f} corners/team-ish")

    # 2) what drives the error?
    err = [r["exp"] - r["act"] for r in rows]
    print("\n[2] error (exp-act) correlation with objective factors:")
    for k in ("xg", "margin", "tot_goals", "poss_gap", "cross_tot", "reds"):
        pairs = [(r[k], e) for r, e in zip(rows, err) if r[k] is not None]
        if len(pairs) >= 3:
            print(f"    corr(error, {k:10}) = {_corr([a for a,_ in pairs],[b for _,b in pairs]):+.2f}")

    # 3) lambda-intensity exponent sweep — re-grade with the proper NB prob.
    # new_mean(p) = exp_current * (xg/MU)^(p-0.7); pick=over if P(over)>=0.5.
    print("\n[3] intensity-exponent sweep (current=0.70), re-graded with NB prob:")
    print(f"    {'exp':>5} {'hit-rate':>9} {'MAE':>6} {'bias':>6}")
    sweep = [r for r in rows if r["xg"]]
    for p in (0.70, 0.55, 0.40, 0.25, 0.10, 0.0):
        h2 = mae = bias = 0
        for r in sweep:
            ratio = (r["xg"] / MU)
            new_mean = r["exp"] * (ratio ** (p - 0.70)) if ratio > 0 else r["exp"]
            pover = corners_at_line(new_mean, r["line"])["over"]
            pick = "over" if pover >= 0.5 else "under"
            act_side = _side(r["act"], r["line"])
            h2 += (act_side == "push") or (pick == act_side)
            mae += abs(new_mean - r["act"]); bias += new_mean - r["act"]
        k = len(sweep)
        print(f"    {p:>5.2f} {h2}/{k} ={h2/k*100:>4.0f}% {mae/k:>6.2f} {bias/k:>+6.2f}")

    # 4) the misses, with objective context
    print("\n[4] MISSES — objective match factors:")
    print(f"    {'match':12} {'line':>4} {'pick':>5} {'exp':>5} {'act':>4} "
          f"{'margin':>6} {'goals':>5} {'cross':>5} {'poss_gap':>8} {'reds':>4}")
    for r in rows:
        if r["hit"]:
            continue
        print(f"    {r['m']:12} {r['line']:>4} {r['pick']:>5} {r['exp']:>5.1f} {int(r['act']):>4} "
              f"{r['margin']:>6} {r['tot_goals']:>5} {str(r['cross_tot'] or '-'):>5} "
              f"{r['poss_gap']:>8.0f} {r['reds']:>4}")


if __name__ == "__main__":
    main()
