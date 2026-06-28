"""Scientific study of KNOCKOUT-stage characteristics to improve pre-match KO
prediction. Knockout football differs from group/league: win-or-out caution,
no draw (→ extra time → penalties), underdog low-blocks for the shootout lottery,
caginess escalating by round. We validate the model's KO knobs (ko_goal_factor
0.955, ko_stage_factors, et_intensity, pens_elo_tilt) against StatsBomb data.

Sources: StatsBomb matches (tournament group + KO stages labelled) + cached
events (ev_*.json) to recover 90-MINUTE goals (match scores may include ET).

Run:  python -m ml.knockout_study
"""
from __future__ import annotations

import glob
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

CACHE = Path(__file__).parent / "data" / "statsbomb"
KO_STAGES = {"Round of 16", "Quarter-finals", "Semi-finals", "Final", "3rd Place Final"}
STAGE_ORDER = ["Round of 16", "Quarter-finals", "Semi-finals", "3rd Place Final", "Final"]


def _ninety_min_goals(mid: int):
    """Sum goals in periods 1-2 only (exclude ET) from cached events, else None."""
    f = CACHE / f"ev_{mid}.json"
    if not f.exists():
        return None
    try:
        ev = json.loads(f.read_text())
    except Exception:
        return None
    g = 0
    for e in ev:
        if (e.get("period") or 0) > 2:           # ET / shootout periods
            continue
        t = (e.get("type") or {}).get("name")
        sh = e.get("shot") or {}
        if t == "Shot" and (sh.get("outcome") or {}).get("name") == "Goal":
            g += 1
        elif t == "Own Goal Against":
            g += 1
    return g


def _ninety_min_corners(mid: int):
    """Count corner kicks (Pass type=Corner) in periods 1-2 from cached events."""
    f = CACHE / f"ev_{mid}.json"
    if not f.exists():
        return None
    try:
        ev = json.loads(f.read_text())
    except Exception:
        return None
    c = 0
    for e in ev:
        if (e.get("period") or 0) > 2:
            continue
        if (e.get("type") or {}).get("name") == "Pass" and \
                ((e.get("pass") or {}).get("type") or {}).get("name") == "Corner":
            c += 1
    return c


def main() -> None:
    matches = []
    for f in glob.glob(str(CACHE / "matches_*.json")):
        try:
            matches += json.loads(Path(f).read_text())
        except Exception:
            pass
    cat = {"group": [], "ko": [], "league": []}
    ko_by_stage = defaultdict(list)
    for m in matches:
        stage = (m.get("competition_stage") or {}).get("name")
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        row = {"mid": m["match_id"], "stage": stage, "hs": hs, "as": as_,
               "tot": hs + as_, "draw": hs == as_}
        if stage in KO_STAGES:
            cat["ko"].append(row); ko_by_stage[stage].append(row)
        elif stage == "Group Stage":
            cat["group"].append(row)
        elif stage == "Regular Season":
            cat["league"].append(row)

    print("=== KNOCKOUT vs GROUP — StatsBomb ===")
    for k in ("league", "group", "ko"):
        v = cat[k]
        print(f"  {k:6}: n {len(v):4}  goals/match {st.mean([r['tot'] for r in v]):.2f}"
              f"  draw-rate {sum(r['draw'] for r in v)/len(v)*100:.0f}%")

    g_grp = st.mean([r["tot"] for r in cat["group"]])
    g_ko = st.mean([r["tot"] for r in cat["ko"]])
    print(f"\n  KO/Group goal ratio = {g_ko/g_grp:.3f}  (model ko_goal_factor 0.955)")
    print(f"  KO draw-rate {sum(r['draw'] for r in cat['ko'])/len(cat['ko'])*100:.0f}%"
          f" — if ~0 the recorded score INCLUDES extra time (ET inflates KO goals)")

    # 90-minute goals (exclude ET) where events are cached
    n90 = [(r, _ninety_min_goals(r["mid"])) for r in cat["ko"]]
    n90 = [(r, g) for r, g in n90 if g is not None]
    if n90:
        ko90 = st.mean([g for _, g in n90])
        grp90 = []
        for r in cat["group"]:
            g = _ninety_min_goals(r["mid"])
            if g is not None:
                grp90.append(g)
        print(f"\n  [90-min, ET excluded, events available] KO n {len(n90)} goals {ko90:.2f}"
              f"  | Group n {len(grp90)} goals {st.mean(grp90):.2f}"
              + (f"  -> 90' ratio {ko90/st.mean(grp90):.3f}" if grp90 else ""))

    # ---- CORNERS: KO vs group (90-min, from events) ----
    def _corners(rows):
        cs = [_ninety_min_corners(r["mid"]) for r in rows]
        return [c for c in cs if c is not None]
    ko_c, grp_c = _corners(cat["ko"]), _corners(cat["group"])
    if ko_c and grp_c:
        print(f"\n=== CORNERS (90-min) KO vs group ===")
        print(f"  group corners/match {st.mean(grp_c):.2f} (n{len(grp_c)})  |  "
              f"KO {st.mean(ko_c):.2f} (n{len(ko_c)})  -> ratio {st.mean(ko_c)/st.mean(grp_c):.3f}")
        for s in STAGE_ORDER:
            v = _corners(ko_by_stage.get(s, []))
            if v:
                print(f"    {s:18} corners {st.mean(v):.2f} (n{len(v)})")

    print("\n=== caginess by stage (escalation? model ko_stage_factors) ===")
    print("  model: R32 0.97 R16 0.95 QF 0.93 SF 0.91 3rd 0.97 Final 0.90")
    for s in STAGE_ORDER:
        v = ko_by_stage.get(s, [])
        if v:
            g90 = [_ninety_min_goals(r["mid"]) for r in v]
            g90 = [g for g in g90 if g is not None]
            extra = f" | 90' {st.mean(g90):.2f} (n{len(g90)})" if g90 else ""
            print(f"  {s:18} n {len(v):2}  FT goals/match {st.mean([r['tot'] for r in v]):.2f}"
                  f"  draw {sum(r['draw'] for r in v)/len(v)*100:.0f}%{extra}")


if __name__ == "__main__":
    main()
