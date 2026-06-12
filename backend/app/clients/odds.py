"""The Odds API client — market odds for WC matches.

Quota budget (free tier ~500 credits/month; 1 credit = 1 market x 1 region):
- bulk featured call (h2h+totals+spreads, all events): 3 credits, TTL 8h
- per-event extras (btts + corners totals): 2 credits/event, only for matches
  kicking off within EXTRA_WINDOW_H hours, capped at EXTRA_MAX_EVENTS, TTL 12h
Remaining quota (from response headers) is surfaced in /api/sources/status.
"""
import httpx

from .. import cache
from ..config import settings
from ..static_data import TEAMS, ODDS_NAME_TO_TLA

_BULK_KEY = "odds:wc:featured"
_QUOTA_KEY = "odds:quota"
SPORT = "soccer_fifa_world_cup"
FEATURED = "h2h,totals,spreads"
EXTRAS = "btts,alternate_totals_corners"
EXTRA_WINDOW_H = 36
EXTRA_MAX_EVENTS = 6
TTL_BULK = 8 * 3600
TTL_EXTRA = 12 * 3600

_NAME_TO_TLA = {t["name"].lower(): tla for tla, t in TEAMS.items()}
_NAME_TO_TLA.update(ODDS_NAME_TO_TLA)


def _tla(name: str) -> str | None:
    return _NAME_TO_TLA.get((name or "").strip().lower())


KEY_COOLDOWN_S = 24 * 3600   # monthly quota: re-probe exhausted keys daily


def _available_keys() -> list[tuple[int, str]]:
    keys = settings.odds_keys()
    fresh = []
    import time
    for i, k in enumerate(keys):
        ts, _ = cache.get_stale(f"odds:cooldown:{i}")
        if ts and time.time() - float(ts) < KEY_COOLDOWN_S:
            continue
        fresh.append((i, k))
    return fresh or list(enumerate(keys))


def _mark_exhausted(idx: int) -> None:
    import logging, time
    logging.getLogger("odds").warning(
        "odds key #%d quota-exhausted — cooling down 24h", idx)
    cache.put(f"odds:cooldown:{idx}", time.time())


def _is_quota_error(r: httpx.Response) -> bool:
    if r.status_code == 429:
        return True
    if r.status_code in (401, 403) and any(
            w in r.text.lower() for w in ("quota", "usage", "credit")):
        return True
    return False


def _track_quota(r: httpx.Response, idx: int) -> None:
    rem = r.headers.get("x-requests-remaining")
    used = r.headers.get("x-requests-used")
    if rem is not None:
        cache.put(_QUOTA_KEY, {"remaining": rem, "used": used, "key_index": idx})


async def _api_get(path: str, params: dict):
    """GET with key-pool failover: a key hitting its monthly quota cools down
    24h and the request retries with the next key."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=15) as client:
        for idx, key in _available_keys():
            r = await client.get(f"{settings.odds_base}{path}",
                                 params={"apiKey": key, **params})
            if _is_quota_error(r):
                _mark_exhausted(idx)
                last_exc = httpx.HTTPStatusError(
                    "quota", request=r.request, response=r)
                continue
            r.raise_for_status()
            _track_quota(r, idx)
            return r.json()
    raise last_exc or httpx.HTTPError("no odds API keys available")


def _avg_price(events_outcomes: list[float]) -> float | None:
    vals = [v for v in events_outcomes if v]
    return round(sum(vals) / len(vals), 3) if vals else None


def _parse_event(ev: dict) -> dict | None:
    ht, at = _tla(ev.get("home_team", "")), _tla(ev.get("away_team", ""))
    if not ht or not at:
        return None
    acc: dict = {"h2h": {"home": [], "draw": [], "away": []},
                 "totals": {}, "spreads": {}}
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            outs = {o["name"]: o for o in mk.get("outcomes", [])}
            if mk["key"] == "h2h":
                h = outs.get(ev["home_team"], {}).get("price")
                a = outs.get(ev["away_team"], {}).get("price")
                d = outs.get("Draw", {}).get("price")
                if h and a and d:
                    acc["h2h"]["home"].append(h)
                    acc["h2h"]["draw"].append(d)
                    acc["h2h"]["away"].append(a)
            elif mk["key"] in ("totals", "spreads"):
                for o in mk.get("outcomes", []):
                    pt = o.get("point")
                    if pt is None:
                        continue
                    slot = acc[mk["key"]].setdefault(pt, {})
                    name = o["name"] if mk["key"] == "totals" else (
                        "home" if o["name"] == ev["home_team"] else "away")
                    slot.setdefault(name, []).append(o["price"])

    def best_line(d):
        # the line quoted by most bookmakers
        if not d:
            return None
        pt = max(d, key=lambda p: sum(len(v) for v in d[p].values()))
        return {"point": pt, **{k.lower(): _avg_price(v) for k, v in d[pt].items()}}

    h2h = {k: _avg_price(v) for k, v in acc["h2h"].items()}
    return {
        "id": ev.get("id"), "commence": ev.get("commence_time"),
        "home_tla": ht, "away_tla": at,
        "h2h": h2h if h2h["home"] else None,
        "totals": best_line(acc["totals"]),
        "spreads": best_line(acc["spreads"]),
    }


async def board() -> tuple[list[dict], str]:
    """All upcoming WC events with featured markets. ([], 'disabled') w/o key."""
    if not settings.odds_keys():
        return [], "disabled"
    hit = cache.get(_BULK_KEY, TTL_BULK)
    if hit is not None:
        return hit, "live"
    try:
        events = await _api_get(f"/sports/{SPORT}/odds",
                                {"regions": "eu", "markets": FEATURED,
                                 "oddsFormat": "decimal"})
    except (httpx.HTTPError, ValueError) as e:
        stale, _ = cache.get_stale(_BULK_KEY)
        return (stale, "stale") if stale else ([], f"error: {e}")
    parsed = [p for p in (_parse_event(ev) for ev in events) if p]
    cache.put(_BULK_KEY, parsed)
    return parsed, "live"


async def event_extras(event_id: str) -> dict | None:
    """btts + corners totals for one event (2 credits) — call sparingly."""
    key = f"odds:extra:{event_id}"
    hit = cache.get(key, TTL_EXTRA)
    if hit is not None:
        return hit
    try:
        ev = await _api_get(f"/sports/{SPORT}/events/{event_id}/odds",
                            {"regions": "eu", "markets": EXTRAS,
                             "oddsFormat": "decimal"})
    except (httpx.HTTPError, ValueError):
        return None
    out: dict = {"btts": None, "corners_totals": None}
    acc_btts: dict[str, list] = {"Yes": [], "No": []}
    acc_corners: dict[float, dict[str, list]] = {}
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] == "btts":
                for o in mk.get("outcomes", []):
                    acc_btts.setdefault(o["name"], []).append(o["price"])
            elif mk["key"] == "alternate_totals_corners":
                for o in mk.get("outcomes", []):
                    pt = o.get("point")
                    if pt is None:
                        continue
                    acc_corners.setdefault(pt, {}).setdefault(o["name"], []).append(o["price"])
    if acc_btts["Yes"]:
        out["btts"] = {"yes": _avg_price(acc_btts["Yes"]), "no": _avg_price(acc_btts["No"])}
    if acc_corners:
        out["corners_totals"] = [
            {"point": pt, "over": _avg_price(v.get("Over", [])),
             "under": _avg_price(v.get("Under", []))}
            for pt, v in sorted(acc_corners.items())
        ]
    cache.put(key, out)
    return out


def cached_extras(event_id: str) -> dict | None:
    """Per-event extras ONLY if already cached — never spends quota (used by
    the hot predict path)."""
    return cache.get(f"odds:extra:{event_id}", TTL_EXTRA)


def quota() -> dict | None:
    q, _ = cache.get_stale(_QUOTA_KEY)
    return q


def _devig(h: float, d: float, a: float) -> dict:
    ph, pd, pa = 1 / h, 1 / d, 1 / a
    s = ph + pd + pa
    return {"home": ph / s, "draw": pd / s, "away": pa / s}


async def market_probs() -> tuple[dict, str]:
    """Vig-removed W/D/L per pair — feeds the prediction blend.
    {frozenset({tla1,tla2}): {home_tla, probs{home,draw,away}}}"""
    events, source = await board()
    out = {}
    for ev in events:
        if not ev.get("h2h"):
            continue
        h2h = ev["h2h"]
        out[frozenset({ev["home_tla"], ev["away_tla"]})] = {
            "home_tla": ev["home_tla"],
            "probs": _devig(h2h["home"], h2h["draw"], h2h["away"]),
        }
    return out, source
