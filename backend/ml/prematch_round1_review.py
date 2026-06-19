"""Holistic PRE-MATCH accuracy review (WC2026 MD1) — measure-first.

Pulls the locked pre-match snapshots + actual results from prod and diagnoses
every pre-match target so we can see WHERE accuracy leaks and which bounded
factor actually helps vs hurts on REAL results:
  - W/D/L: accuracy, RPS, reliability (are stated probs calibrated?)
  - O/U goals at the Asian line, BTTS, exact-score top-1
  - factor scorecard (with/without delta + verdict) for every bounded factor
  - meta-weights: which W/D/L blend would have scored best

Run:  python -m ml.prematch_round1_review
      CORNERS_BASE_URL=http://localhost ADMIN_TOKEN=... python -m ml.prematch_round1_review
"""
from __future__ import annotations

import json
import os
import statistics as st
import urllib.request

BASE = os.environ.get("CORNERS_BASE_URL", "http://42.96.56.55")
TOKEN = os.environ.get("ADMIN_TOKEN", "ttkien2035")
ORDER = ("home", "draw", "away")


def _get(path: str):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(BASE + path, headers={"X-Admin-Token": TOKEN}), timeout=60))


def _rps(p: dict, actual: str) -> float:
    cp = r = 0.0
    for k in ORDER[:2]:
        cp += p.get(k, 0.0)
        r += (cp - (1.0 if ORDER.index(actual) <= ORDER.index(k) else 0.0)) ** 2
    return r / 2


def main() -> None:
    rev = _get("/api/pipeline/review")["matches"]
    status = _get("/api/pipeline/status")

    rows = [m for m in rev if m.get("score", {}).get("home") is not None]
    n = len(rows)
    print(f"=== PRE-MATCH accuracy — WC2026 MD1 ({n} finished) ===\n")

    # ---- W/D/L ----
    correct = sum(1 for m in rows if m["correct"])
    rps = st.mean([_rps(m["probs"], m["actual"]) for m in rows])
    # reliability: bucket by stated P(pick), compare to realized hit-rate
    print(f"[W/D/L] acc {correct}/{n} = {correct/n*100:.0f}%  | mean RPS {rps:.4f}"
          f"  (train backtest ~0.16)")
    buckets = {}
    for m in rows:
        p = m["probs"][m["predicted"]]
        b = "55-100%" if p >= 0.55 else ("45-55%" if p >= 0.45 else "0-45%")
        buckets.setdefault(b, []).append(1 if m["correct"] else 0)
    for b in ("55-100%", "45-55%", "0-45%"):
        if b in buckets:
            v = buckets[b]
            print(f"    pick prob {b:8}: n {len(v):2}  hit {sum(v)/len(v)*100:.0f}% "
                  f"(want ~{b})")
    # outcome distribution: are draws under/over-predicted?
    pred_dist = {k: sum(1 for m in rows if m["predicted"] == k) for k in ORDER}
    act_dist = {k: sum(1 for m in rows if m["actual"] == k) for k in ORDER}
    print(f"    argmax-pick dist {pred_dist} vs actual {act_dist}")
    # PROBABILITY calibration: mean stated prob per class vs realized frequency
    # (this decides if draws are truly under-priced or just argmax-suppressed)
    print("    mean stated P vs actual freq:")
    for k in ORDER:
        mean_p = st.mean([m["probs"][k] for m in rows])
        freq = act_dist[k] / n
        print(f"      {k:5}: mean P {mean_p*100:4.1f}%  vs actual {freq*100:4.1f}%"
              f"  ({'under-priced' if mean_p < freq - 0.03 else 'over-priced' if mean_p > freq + 0.03 else 'ok'})")
    drawn = [m for m in rows if m["actual"] == "draw"]
    if drawn:
        print(f"    on the {len(drawn)} DRAWN matches: mean P(draw) assigned "
              f"{st.mean([m['probs']['draw'] for m in drawn])*100:.1f}%  "
              f"(max P(draw) any match {max(m['probs']['draw'] for m in rows)*100:.1f}%)")

    # ---- O/U goals (Asian line) ----
    g = [(m["compare"]["goals"]) for m in rows if (m.get("compare") or {}).get("goals", {}).get("hit") is not None]
    if g:
        gh = sum(1 for x in g if x["hit"])
        bias = st.mean([(x.get("p_over", 0.5) - (1 if x["actual"] == "over" else 0)) for x in g])
        print(f"\n[O/U goals] hit {gh}/{len(g)} = {gh/len(g)*100:.0f}%  | P(over) bias {bias:+.3f}")

    # ---- BTTS + exact score ----
    btts = [m["compare"]["btts"] for m in rows if (m.get("compare") or {}).get("btts")]
    if btts:
        bh = sum(1 for x in btts if (x["pred_p"] or 0) >= 0.5) == 0  # placeholder
    sc = [m["compare"]["score"] for m in rows if (m.get("compare") or {}).get("score")]
    if sc:
        exact = sum(1 for x in sc if x.get("hit"))
        print(f"[Score] exact top-1 {exact}/{len(sc)} = {exact/len(sc)*100:.0f}%")

    # ---- factor scorecard (the key help/hurt diagnostic) ----
    fs = status.get("factor_scorecard") or {}
    print("\n[Factor scorecard] with vs without on REAL results (delta<0 = factor HELPS):")
    print(f"    {'factor':10} {'n':>3} {'metric':>6} {'with':>8} {'without':>8} {'delta':>8}  verdict")
    for k, v in fs.items():
        if not v.get("n"):
            continue
        print(f"    {k:10} {v['n']:>3} {v.get('metric',''):>6} "
              f"{v.get('with','-'):>8} {v.get('without','-'):>8} {v.get('delta','-'):>8}  {v.get('verdict','')}")

    # ---- meta-weights ----
    mw = status.get("meta_weights") or {}
    print(f"\n[Meta-weights] {json.dumps(mw, ensure_ascii=False)[:400]}")


if __name__ == "__main__":
    main()
