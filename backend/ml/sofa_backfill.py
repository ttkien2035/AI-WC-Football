"""Sofascore corpus for prototypes (2) xG-form vs shot-form and (3) box-entry /
big-chance -> totals & corners. ONE /matches/get-statistics call per match yields
xG, big chances, final-third entries, touches-in-box, corners, shots, SoT,
possession — so the whole corpus costs ~1 quota unit per match.

Snowball crawl: start from a seed national team, read its last matches (national
teams only play internationals), enqueue opponents, repeat. Bounded by MAX_TEAMS
/ MAX_MATCHES so it never blows the RapidAPI monthly pool. Everything is cached
on disk by rapid_client, so re-runs cost zero quota.

Run:  python -m ml.sofa_backfill            # default budget
      python -m ml.sofa_backfill 200        # cap matches
"""
from __future__ import annotations

import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ml.rapid_client import sofa

OUT = Path(__file__).parent / "data" / "espn" / "sofa_team_match.csv"  # (gitignored data dir)
SEEDS = [4711, 4724, 4798, 4493, 4502]   # Germany, USA, Brazil, France, Spain-ish seeds
MAX_TEAMS = 48
MAX_MATCHES = 280

STAT_MAP = {
    "Expected goals": "xg", "Big chances": "big_ch", "Big chances scored": "big_ch_sc",
    "Final third entries": "f3_entries", "Touches in penalty area": "box_touch",
    "Corner kicks": "corners", "Total shots": "shots", "Shots on target": "sot",
    "Ball possession": "poss",
}


def _date(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def collect_matches() -> dict:
    """BFS over national teams -> {match_id: metadata}."""
    seen_team, q = set(), deque(SEEDS)
    matches = {}
    while q and len(seen_team) < MAX_TEAMS and len(matches) < MAX_MATCHES * 2:
        tid = q.popleft()
        if tid in seen_team:
            continue
        seen_team.add(tid)
        d = sofa("/teams/get-last-matches", {"teamId": str(tid), "pageIndex": "0"}, verbose=False)
        for e in (d or {}).get("events", []):
            if e.get("status", {}).get("type") != "finished":
                continue
            h, a = e.get("homeTeam", {}), e.get("awayTeam", {})
            hs, as_ = e.get("homeScore", {}).get("current"), e.get("awayScore", {}).get("current")
            if hs is None or as_ is None:
                continue
            mid = str(e.get("id"))
            matches.setdefault(mid, {
                "event_id": mid, "date": _date(e.get("startTimestamp")),
                "home": h.get("name"), "away": a.get("name"),
                "home_id": h.get("id"), "away_id": a.get("id"),
                "hs": int(hs), "as": int(as_),
                "tournament": e.get("tournament", {}).get("name"),
            })
            for oid in (h.get("id"), a.get("id")):
                if oid and oid not in seen_team:
                    q.append(oid)
        print(f"  teams visited {len(seen_team)} | matches found {len(matches)}", flush=True)
    return matches


def fetch_stats(matches: dict) -> pd.DataFrame:
    rows = []
    ids = sorted(matches, key=lambda m: matches[m]["date"], reverse=True)[:MAX_MATCHES]
    for i, mid in enumerate(ids):
        meta = matches[mid]
        st = sofa("/matches/get-statistics", {"matchId": mid}, verbose=False)
        if not st or not st.get("statistics"):
            continue
        period = next((p for p in st["statistics"] if p.get("period") == "ALL"),
                      st["statistics"][0])
        vals = {}
        for g in period.get("groups", []):
            for it in g.get("statisticsItems", []):
                key = STAT_MAP.get(it.get("name"))
                if key and it.get("homeValue") is not None:
                    vals[key] = (it.get("homeValue"), it.get("awayValue"))
        if "xg" not in vals:           # no real stats for this match
            continue
        for side, opp, sign in (("home", "away", 0), ("away", "home", 1)):
            row = {"event_id": mid, "date": meta["date"], "tournament": meta["tournament"],
                   "team": meta[side], "opp": meta[opp], "is_home": 1 - sign,
                   "goals_for": meta["hs"] if side == "home" else meta["as"],
                   "goals_against": meta["as"] if side == "home" else meta["hs"]}
            for key, (hv, av) in vals.items():
                row[key] = hv if side == "home" else av
            rows.append(row)
        if (i + 1) % 50 == 0:
            print(f"  stats {i+1}/{len(ids)} ({len(rows)} rows)", flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    global MAX_MATCHES
    if len(sys.argv) > 1:
        MAX_MATCHES = int(sys.argv[1])
    print(f"collecting matches (<= {MAX_TEAMS} teams, <= {MAX_MATCHES} matches)...")
    matches = collect_matches()
    print(f"unique finished internationals found: {len(matches)}")
    df = fetch_stats(matches)
    if df.empty:
        print("no rows"); return
    df = df.sort_values(["date", "event_id"]).reset_index(drop=True)
    OUT.write_text(df.to_csv(index=False))
    print(f"\nwrote {OUT}: {df.event_id.nunique()} matches, {len(df)} team-rows")
    print("fields:", [c for c in df.columns if c in STAT_MAP.values()])
    print("xG present:", int(df["xg"].notna().sum()), "| corners present:",
          int(df["corners"].notna().sum()) if "corners" in df else 0)


if __name__ == "__main__":
    main()
