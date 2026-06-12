"""LiveScore.com connector (UNOFFICIAL — no public API exists).

Uses the JSON endpoints that power livescore.com's own frontend. They may
change or break at any time, so every call is best-effort: failures return
None/{} and the app keeps working from football-data.org alone. Intended for
personal localhost use; do not hammer (TTL-cached, scheduler-paced).

What it adds over fd.org free tier: real live MINUTE, half-time scores, and
in-match statistics (corners) used to calibrate the corners model.
"""
import re
from datetime import datetime, timezone

import httpx

from .. import cache
from ..static_data import TEAMS, ODDS_NAME_TO_TLA

BASE = "https://prod-public-api.livescore.com/v1/api/app"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_NAME_TO_TLA = {t["name"].lower(): tla for tla, t in TEAMS.items()}
_NAME_TO_TLA.update(ODDS_NAME_TO_TLA)
_NAME_TO_TLA.update({
    "korea republic": "KOR", "curaçao": "CUW", "côte d'ivoire": "CIV",
    "bosnia & herzegovina": "BIH", "usa": "USA", "ir iran": "IRN",
    "congo dr": "COD", "cabo verde": "CPV", "türkiye": "TUR",
})


def tla_for(name: str | None) -> str | None:
    return _NAME_TO_TLA.get((name or "").strip().lower())


async def _get(path: str, ttl: int):
    key = f"ls:{path}"
    hit = cache.get(key, ttl)
    if hit is not None:
        return hit
    try:
        async with httpx.AsyncClient(timeout=12, headers=UA) as client:
            r = await client.get(f"{BASE}/{path}", params={"countryCode": "VN", "locale": "en"})
            r.raise_for_status()
            data = r.json()
        cache.put(key, data)
        return data
    except (httpx.HTTPError, ValueError):
        stale, _ = cache.get_stale(key)
        return stale  # may be None — callers handle


def _minute(eps: str | None) -> int | None:
    """Eps examples: NS, 12', 45+2', HT, 67', FT, AET, Postp."""
    if not eps:
        return None
    if eps == "HT":
        return 45
    m = re.match(r"(\d+)(?:\+\d+)?'", eps)
    return int(m.group(1)) if m else None


def _event(ev: dict) -> dict:
    t1 = (ev.get("T1") or [{}])[0].get("Nm")
    t2 = (ev.get("T2") or [{}])[0].get("Nm")
    eps = ev.get("Eps")
    return {
        "eid": ev.get("Eid"),
        "home_name": t1, "away_name": t2,
        "home_tla": tla_for(t1), "away_tla": tla_for(t2),
        "status": eps,
        "minute": _minute(eps),
        "score": {"home": _int(ev.get("Tr1")), "away": _int(ev.get("Tr2"))},
        "ht_score": {"home": _int(ev.get("Trh1")), "away": _int(ev.get("Trh2"))},
        "live": bool(eps) and eps not in ("NS", "FT", "AET", "AP", "Postp", "Canc", "Aband"),
        "finished": eps in ("FT", "AET", "AP"),
    }


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def _wc_events_on(day: str, ttl: int) -> list[dict]:
    data = await _get(f"date/soccer/{day}/0", ttl=ttl)
    if not data:
        return []
    out = []
    for stage in data.get("Stages", []):
        label = f"{stage.get('Cnm', '')} {stage.get('Snm', '')}"
        if "world cup" not in label.lower():
            continue
        out.extend(_event(ev) for ev in stage.get("Events", []))
    return [e for e in out if e["home_tla"] and e["away_tla"]]


async def wc_events_today() -> list[dict]:
    """WC events for today AND yesterday (UTC) — the overlap keeps incidents/
    corners available for finished matches across the midnight boundary."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    today = await _wc_events_on(now.strftime("%Y%m%d"), ttl=30)
    yday = await _wc_events_on((now - timedelta(days=1)).strftime("%Y%m%d"), ttl=600)
    seen = {e["eid"] for e in today}
    return today + [e for e in yday if e["eid"] not in seen]


# LiveScore incident-type codes (community-documented; unknown codes ignored)
_IT_GOAL = {36, 37, 38, 39}          # goal / own goal / penalty goal
_IT_OWN_GOAL = {37}
_IT_PEN_GOAL = {38, 39}
_IT_YELLOW = {43}
_IT_RED = {44, 45, 46}               # second yellow / straight red variants


def _player_name(obj: dict) -> str | None:
    """Only string fields count — in live incident payloads `Nm` is the TEAM
    number (1=home, 2=away), not a name (verified vs MEX-RSA opener)."""
    for k in ("Pn", "Nm", "Name"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip() and not v.strip().isdigit():
            return v
    fn, ln = obj.get("Fn"), obj.get("Ln")
    if fn or ln:
        return " ".join(str(x) for x in (fn, ln) if x)
    return None


def _side_of(obj: dict, default: str = "?") -> str:
    """Side from Tnb or numeric Nm (both use 1=home, 2=away)."""
    for k in ("Tnb", "Nm"):
        v = obj.get(k)
        if v in (1, 2, "1", "2"):
            return "home" if int(v) == 1 else "away"
    return default


def _walk_incidents(node, side: str, out: list) -> None:
    """Incident payloads nest (e.g. goal + assist inside one entry) — walk
    every dict that carries an IT code."""
    if isinstance(node, list):
        for x in node:
            _walk_incidents(x, side, out)
        return
    if not isinstance(node, dict):
        return
    side = _side_of(node, default=side)
    it = node.get("IT")
    minute = node.get("Min")
    if isinstance(it, int):
        kind = ("goal" if it in _IT_GOAL else
                "red" if it in _IT_RED else
                "yellow" if it in _IT_YELLOW else None)
        if kind:
            minute_ex = node.get("MinEx")
            out.append({
                "minute": minute if isinstance(minute, int) else None,
                "minute_ex": minute_ex if isinstance(minute_ex, int) else None,
                "type": kind,
                "own_goal": it in _IT_OWN_GOAL,
                "penalty": it in _IT_PEN_GOAL,
                "player": _player_name(node),
                "side": side,
            })
    for v in node.values():
        if isinstance(v, (list, dict)):
            _walk_incidents(v, side, out)


async def incidents(eid) -> list[dict]:
    """[{minute, type: goal|yellow|red, player, side: home|away}] — best-effort.
    LiveScore shape: {"Incs": {"<period>": [..]}} with team via Nm/Tnb keys;
    we also accept side-split payloads (IncsH/IncsA, T1/T2)."""
    data = await _get(f"incidents/soccer/{eid}", ttl=30)
    if not data or not isinstance(data, dict):
        return []
    out: list[dict] = []
    incs = data.get("Incs")
    if isinstance(incs, dict):
        for period in incs.values():
            for entry in (period if isinstance(period, list) else []):
                _walk_incidents(entry, _side_of(entry), out)
    else:  # alternate shapes
        for key, side in (("IncsH", "home"), ("IncsA", "away"),
                          ("T1", "home"), ("T2", "away")):
            if key in data:
                _walk_incidents(data[key], side, out)
    out.sort(key=lambda x: (x["minute"] is None, x["minute"]))
    return out


def _formation(players: list[dict]) -> str | None:
    """Derive e.g. '4-2-3-1' from Fp 'row:col' pitch coordinates (row 1 = GK)."""
    rows: dict[int, int] = {}
    for p in players:
        fp = p.get("fp") or ""
        if ":" in fp:
            row = int(fp.split(":")[0])
            if row > 1:
                rows[row] = rows.get(row, 0) + 1
    if not rows or sum(rows.values()) < 7:
        return None
    return "-".join(str(rows[r]) for r in sorted(rows))


async def lineups(eid) -> dict | None:
    """{home: {formation, players: [{name, pos, shirt}]}, away: {...}} or None."""
    data = await _get(f"lineups/soccer/{eid}", ttl=900)
    if not data or not isinstance(data, dict):
        return None
    out = {}
    for block in data.get("Lu", []):
        side = "home" if block.get("Tnb") == 1 else "away"
        players = []
        for p in block.get("Ps", []):
            name = _player_name(p)
            if not name:
                continue
            players.append({"name": name, "pos": p.get("Pon"),
                            "shirt": p.get("Snu"), "fp": p.get("Fp")})
        starters = [p for p in players if p.get("fp")]
        out[side] = {
            "formation": _formation(players),
            "players": starters if starters else players[:11],
        }
    return out if out else None


# Real shape (verified vs MEX-RSA opener FT): Stat = [{Tnb:1, Cos: corners,
# Crs: crosses, Ycs/Rcs: cards, Pss: possession, Shon: shots on target, ...}]
_STAT_FIELDS = {"corners": "Cos", "crosses": "Crs", "possession": "Pss",
                "shots_on": "Shon", "yellows": "Ycs", "reds": "Rcs",
                "fouls": "Fls", "offsides": "Ofs"}


def _parse_stats(stats: dict) -> dict | None:
    blocks = stats.get("Stat") or stats.get("Stats") or []
    if isinstance(blocks, dict):
        blocks = [blocks]
    sides = {}
    for b in blocks:
        if not isinstance(b, dict):
            continue
        side = _side_of(b, default="")
        if side:
            sides[side] = b
    if not sides:
        return None
    out = {}
    for name, key in _STAT_FIELDS.items():
        h = _int((sides.get("home") or {}).get(key))
        a = _int((sides.get("away") or {}).get(key))
        if h is not None or a is not None:
            out[name] = {"home": h, "away": a}
    return out or None


async def match_stats(eid) -> dict | None:
    data = await _get(f"statistics/soccer/{eid}", ttl=60)
    return _parse_stats(data) if data else None


async def enrichment() -> dict[frozenset, dict]:
    """{frozenset({tla,tla}): {minute, score, ht_score, corners, incidents,
    red_cards, lineups, live}}"""
    out = {}
    for ev in await wc_events_today():
        entry = dict(ev)
        if ev["live"] or ev["finished"]:
            stats = await match_stats(ev["eid"])
            entry["stats"] = stats
            entry["corners"] = (stats or {}).get("corners")
            incs = await incidents(ev["eid"])
            entry["incidents"] = incs
            entry["red_cards"] = {
                "home": sum(1 for i in incs if i["type"] == "red" and i["side"] == "home"),
                "away": sum(1 for i in incs if i["type"] == "red" and i["side"] == "away"),
            }
        entry["lineups"] = await lineups(ev["eid"])   # None until announced
        out[frozenset({ev["home_tla"], ev["away_tla"]})] = entry
    return out


async def status() -> dict:
    try:
        evs = await wc_events_today()
        return {"ok": True, "source": "unofficial endpoint",
                "wc_events_today": len(evs),
                "live_now": sum(e["live"] for e in evs)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
