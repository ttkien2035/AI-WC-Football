"""BATCH BACKFILL (pre-match feature source probe).

Pulls recent INTERNATIONAL matches (WC2026 + qualifiers + Nations League +
friendlies + recent finals tournaments) from ESPN's open hidden API and caches
per-team match-level event aggregates (shots, shots-on-target, possession,
passes, crosses, long balls, tackles, interceptions, clearances, corners, ...).

Why ESPN: Sofascore (Cloudflare 403) and FotMob (token-gated) block programmatic
access from this environment; ESPN's site.api.espn.com is open and — crucially —
COVERS THE WC2026 CYCLE (qualifiers/friendlies/finals) that StatsBomb open data
does not. This is the coverage gap identified for pre-match enrichment.

Output: data/espn/raw/<league>_<month>.json (scoreboard cache),
        data/espn/sum/<event_id>.json (summary cache),
        data/espn/intl_team_match.csv (tidy, one row per team-match).

Run:  python -m ml.espn_backfill            # full crawl (cached; re-runs are cheap)
      python -m ml.espn_backfill --months 6 # only last N months
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent / "data" / "espn"
RAW = ROOT / "raw"
SUM = ROOT / "sum"
CSV = ROOT / "intl_team_match.csv"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
API = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# International competitions whose matches inform WC2026 team form.
LEAGUES = [
    "fifa.world",            # WC2026 finals (in progress)
    "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.concacaf",
    "fifa.worldq.afc", "fifa.worldq.caf", "fifa.worldq.ofc",
    "uefa.nations", "concacaf.nations",
    "fifa.friendly",
    "uefa.euro", "uefa.euroq", "conmebol.america",
    "caf.nations", "afc.asian", "concacaf.gold",
]

# stat fields we keep from the boxscore (ESPN name -> our column)
STAT_KEYS = {
    "totalShots": "shots", "shotsOnTarget": "sot", "wonCorners": "corners",
    "possessionPct": "poss", "totalPasses": "passes", "accuratePasses": "acc_passes",
    "totalCrosses": "crosses", "accurateCrosses": "acc_crosses",
    "totalLongBalls": "long_balls", "accurateLongBalls": "acc_long_balls",
    "blockedShots": "blocked", "saves": "saves", "foulsCommitted": "fouls",
    "offsides": "offsides", "totalTackles": "tackles", "interceptions": "intercept",
    "totalClearance": "clearance", "effectiveClearance": "eff_clearance",
}


def _get(url: str, timeout: int = 20):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))


def _months(n: int | None) -> list[str]:
    """YYYYMM strings from 2024-01 to 2026-06 (or last n of them)."""
    ms = [f"{y}{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)
          if not (y == 2024 and m < 1) and not (y == 2026 and m > 6)]
    return ms[-n:] if n else ms


def crawl_scoreboards(months: list[str]) -> list[dict]:
    """Return finished match stubs: {event_id, league, date, home, away, hs, as}."""
    RAW.mkdir(parents=True, exist_ok=True)
    stubs, seen = [], set()
    for lg in LEAGUES:
        for mo in months:
            cache = RAW / f"{lg}_{mo}.json"
            if cache.exists():
                evs = json.loads(cache.read_text()).get("events", [])
            else:
                try:
                    d = _get(f"{API}/{lg}/scoreboard?dates={mo}")
                except urllib.error.HTTPError:
                    cache.write_text(json.dumps({"events": []}))
                    continue
                except Exception:
                    continue
                evs = d.get("events", [])
                cache.write_text(json.dumps({"events": evs}))
            for e in evs:
                st = e.get("status", {}).get("type", {})
                if not st.get("completed"):
                    continue
                eid = str(e.get("id"))
                if eid in seen:
                    continue
                comp = (e.get("competitions") or [{}])[0]
                cs = comp.get("competitors") or []
                home = next((c for c in cs if c.get("homeAway") == "home"), None)
                away = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not (home and away):
                    continue
                try:
                    hs, as_ = int(home["score"]), int(away["score"])
                except (KeyError, ValueError, TypeError):
                    continue
                seen.add(eid)
                stubs.append({
                    "event_id": eid, "league": lg, "date": (e.get("date") or "")[:10],
                    "home": home["team"]["displayName"], "away": away["team"]["displayName"],
                    "home_id": home["team"]["id"], "away_id": away["team"]["id"],
                    "hs": hs, "as": as_,
                })
    return stubs


def fetch_summaries(stubs: list[dict]) -> pd.DataFrame:
    """For each match fetch boxscore stats; emit one row per TEAM-match."""
    SUM.mkdir(parents=True, exist_ok=True)
    rows, miss = [], 0
    for i, s in enumerate(stubs):
        eid = s["event_id"]
        cache = SUM / f"{eid}.json"
        if cache.exists():
            box = json.loads(cache.read_text())
        else:
            try:
                d = _get(f"{API}/{s['league']}/summary?event={eid}")
            except Exception:
                miss += 1
                continue
            box = d.get("boxscore", {})
            cache.write_text(json.dumps(box))
        teams = box.get("teams", [])
        if len(teams) != 2:
            miss += 1
            continue
        # map team id -> stat dict
        stat_by_id = {}
        for t in teams:
            tid = t.get("team", {}).get("id")
            sd = {}
            for st in t.get("statistics", []):
                key = STAT_KEYS.get(st.get("name"))
                if key is None:
                    continue
                try:
                    sd[key] = float(str(st.get("displayValue", "")).replace("%", ""))
                except ValueError:
                    pass
            stat_by_id[str(tid)] = sd
        for side, opp in (("home", "away"), ("away", "home")):
            sd = stat_by_id.get(str(s[f"{side}_id"]))
            if not sd:
                continue
            rows.append({
                "event_id": eid, "league": s["league"], "date": s["date"],
                "team": s[side], "opp": s[opp],
                "is_home": 1 if side == "home" else 0,
                "goals_for": s["hs"] if side == "home" else s["as"],
                "goals_against": s["as"] if side == "home" else s["hs"],
                **sd,
            })
        if (i + 1) % 100 == 0:
            print(f"  summaries {i+1}/{len(stubs)} (miss {miss})", flush=True)
    print(f"  summaries done: {len(rows)} team-rows, {miss} missing")
    return pd.DataFrame(rows)


def main() -> None:
    n = None
    if "--months" in sys.argv:
        n = int(sys.argv[sys.argv.index("--months") + 1])
    months = _months(n)
    print(f"crawling {len(LEAGUES)} leagues x {len(months)} months ({months[0]}..{months[-1]})")
    stubs = crawl_scoreboards(months)
    print(f"finished international matches: {len(stubs)}")
    df = fetch_summaries(stubs)
    if df.empty:
        print("no rows — abort")
        return
    df = df.sort_values(["date", "event_id"]).reset_index(drop=True)
    CSV.write_text(df.to_csv(index=False))
    cov = df.groupby("league").event_id.nunique().sort_values(ascending=False)
    print(f"\nwrote {CSV}  ({df.event_id.nunique()} matches, {len(df)} team-rows)")
    print("coverage by competition:")
    for lg, c in cov.items():
        print(f"   {lg:24s} {c}")


if __name__ == "__main__":
    main()
