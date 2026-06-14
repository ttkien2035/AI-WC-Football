"""B1 — enriched event-level dataset for the tactical corner/style research.

Pulls ALL modern (>=2003) MEN'S StatsBomb open competitions (club + national
team — women's excluded per scope), aggregates per team per match with the
corner MECHANISM features needed for B2 (wide play / overlaps / byline crosses
-> corners) and B3 (tactical counter-matchups). ~2.6k matches / ~5.2k rows.

Event JSONs cache under ml/data/statsbomb/ (gitignored); only the resulting
team_match_rich.csv + downstream fitted JSON artifacts are committed. Re-runs
skip cached files. Run:  python -m ml.statsbomb_dataset
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import pandas as pd

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = CACHE / "team_match_rich.csv"
UA = "Mozilla/5.0 (research; football-prediction)"

INTL = {43, 55, 223, 1267}      # WC, Euro, Copa, AFCON -> level=intl


def _curl(url: str, dst: Path):
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


def _seasons() -> list[tuple]:
    comps = _curl(f"{RAW}/competitions.json", CACHE / "competitions.json") or []
    yr = lambda s: int((re.findall(r"\d{4}", s) or [0])[-1])
    out = []
    for r in comps:
        if r.get("competition_gender") != "male" or r["competition_id"] == 1470:
            continue
        if yr(r["season_name"]) < 2003:
            continue
        out.append((r["competition_id"], r["season_id"],
                    f'{r["competition_name"]} {r["season_name"]}'.replace("/", "-")))
    return out


def _wide(loc):       # wide attacking channel (StatsBomb 120x80 pitch)
    return loc and loc[0] >= 80 and (loc[1] <= 18 or loc[1] >= 62)


def _in_box(loc):
    return loc and loc[0] >= 102 and 18 <= loc[1] <= 62


def aggregate(events: list, mid: int, comp: str, level: str) -> list[dict]:
    agg = defaultdict(lambda: defaultdict(float))
    for e in events:
        tm = (e.get("team") or {}).get("name")
        if not tm:
            continue
        a = agg[tm]
        typ = (e.get("type") or {}).get("name")
        if typ == "Pass":
            p = e.get("pass") or {}
            a["passes"] += 1
            start, end = e.get("location"), p.get("end_location")
            if (p.get("type") or {}).get("name") == "Corner":
                a["corners"] += 1
            if p.get("cross"):
                a["crosses"] += 1
                if start and start[0] >= 102:        # byline / deep cross
                    a["deep_cross"] += 1
            if (p.get("length") or 0) >= 35:
                a["long"] += 1
            if end and start and end[0] > start[0]:
                a["fwd"] += 1
            if _wide(end):
                a["wide_ft"] += 1                    # ball into wide final third
            if _in_box(end):
                a["box_entry"] += 1
        elif typ == "Shot":
            a["shots"] += 1
            a["xg"] += (e.get("shot") or {}).get("statsbomb_xg") or 0.0
            if _in_box(e.get("location")):       # shot from inside the box
                a["shots_in_box"] += 1           # LIVE-servable proxy via shotmap
            if ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
                a["goals"] += 1
        elif typ == "Pressure":
            a["pressures"] += 1
    teams = list(agg)
    if len(teams) != 2:
        return []
    tot_pass = sum(agg[t]["passes"] for t in teams)
    if tot_pass < 200:
        return []
    rows = []
    for t, opp in ((teams[0], teams[1]), (teams[1], teams[0])):
        a, o, p = agg[t], agg[opp], agg[t]["passes"] or 1
        rows.append({
            "comp": comp, "level": level, "match_id": mid, "team": t,
            "corners_for": a["corners"], "corners_against": o["corners"],
            "crosses": a["crosses"], "deep_cross": a["deep_cross"],
            "wide_ft": a["wide_ft"], "box_entry": a["box_entry"],
            "shots": a["shots"], "shots_in_box": a["shots_in_box"], "xg": round(a["xg"], 3),
            "fwd_ratio": round(a["fwd"] / p, 3), "long_ratio": round(a["long"] / p, 3),
            "pressures": a["pressures"], "passes": a["passes"],
            "possession": round(a["passes"] / tot_pass, 3),
            "goals_for": a["goals"], "goals_against": o["goals"],
        })
    return rows


def main() -> None:
    seasons = _seasons()
    print(f"men's modern seasons: {len(seasons)}")
    recs, done = [], 0
    for cid, sid, label in seasons:
        level = "intl" if cid in INTL else "club"
        matches = _curl(f"{RAW}/matches/{cid}/{sid}.json", CACHE / f"matches_{cid}_{sid}.json")
        if not matches:
            print(f"  SKIP {label} (no matches)"); continue
        n = 0
        for m in matches:
            mid = m["match_id"]
            ev = _curl(f"{RAW}/events/{mid}.json", CACHE / f"ev_{mid}.json")
            if not ev:
                continue
            r = aggregate(ev, mid, label, level)
            if r:
                recs.extend(r); n += 1
        done += n
        print(f"  {n:4d}  {label}  (cum {done})", flush=True)
    df = pd.DataFrame(recs)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}: {len(df)} team-match rows | "
          f"club={sum(df.level=='club')} intl={sum(df.level=='intl')}")
    print(f"corners/team mean: {df.corners_for.mean():.2f} "
          f"(club {df[df.level=='club'].corners_for.mean():.2f} / "
          f"intl {df[df.level=='intl'].corners_for.mean():.2f})")


if __name__ == "__main__":
    main()
