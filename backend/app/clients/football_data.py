"""football-data.org v4 client (free tier, 10 req/min) with TTL cache + stale fallback."""
import httpx
from .. import cache
from ..config import settings

COMP = "WC"


async def _get(path: str, ttl: int, params: dict | None = None):
    key = f"fd:{path}:{params}"
    hit = cache.get(key, ttl)
    if hit is not None:
        return hit
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = None
            # key pool: rotate to the next key on a 429 (per-key 10 req/min)
            for api_key in settings.football_keys() or [""]:
                r = await client.get(
                    f"{settings.fd_base}{path}",
                    headers={"X-Auth-Token": api_key},
                    params=params,
                )
                if r.status_code != 429:
                    break
            r.raise_for_status()
            data = r.json()
            cache.put(key, data)
            return data
    except (httpx.HTTPError, ValueError):
        stale, _ = cache.get_stale(key)
        if stale is not None:
            return stale
        raise


async def standings():
    return await _get(f"/competitions/{COMP}/standings", settings.ttl_standings)


async def matches(force: bool = False):
    if force:
        cache.invalidate(f"fd:/competitions/{COMP}/matches")
    return await _get(f"/competitions/{COMP}/matches", settings.ttl_matches)


def simplify_match(m: dict) -> dict:
    ft = m["score"]["fullTime"]
    return {
        "id": m["id"],
        "utcDate": m["utcDate"],
        "status": m["status"],            # TIMED/SCHEDULED/IN_PLAY/PAUSED/FINISHED
        "stage": m["stage"],              # GROUP_STAGE/LAST_32/.../FINAL
        "group": m.get("group"),
        "matchday": m.get("matchday"),
        "venue": m.get("venue"),
        "home": {"id": m["homeTeam"]["id"], "name": m["homeTeam"]["name"],
                 "tla": m["homeTeam"]["tla"], "crest": m["homeTeam"]["crest"]},
        "away": {"id": m["awayTeam"]["id"], "name": m["awayTeam"]["name"],
                 "tla": m["awayTeam"]["tla"], "crest": m["awayTeam"]["crest"]},
        "score": {"home": ft["home"], "away": ft["away"],
                  "winner": m["score"].get("winner"),
                  "duration": m["score"].get("duration")},
    }


async def all_matches_simple(force: bool = False) -> list[dict]:
    data = await matches(force=force)
    return [simplify_match(m) for m in data.get("matches", [])]


async def team_squad(team_id: int) -> list[dict]:
    """Full registered squad from fd.org (free tier includes it). Cached 7d."""
    data = await _get(f"/teams/{team_id}", 7 * 86_400)
    return [
        {"name": p.get("name"), "position": p.get("position"),
         "nationality": p.get("nationality"), "dob": p.get("dateOfBirth")}
        for p in data.get("squad", [])
    ]


async def teams_from_standings() -> dict[str, dict]:
    """{TLA: {id, name, tla, crest, group, played, won, draw, lost, gf, ga, points}}"""
    data = await standings()
    out = {}
    for block in data.get("standings", []):
        group = (block.get("group") or "").replace("Group ", "")
        for row in block.get("table", []):
            t = row["team"]
            out[t["tla"]] = {
                "id": t["id"], "name": t["name"], "tla": t["tla"],
                "crest": t.get("crest"), "group": group,
                "position": row["position"], "played": row["playedGames"],
                "won": row["won"], "draw": row["draw"], "lost": row["lost"],
                "gf": row["goalsFor"], "ga": row["goalsAgainst"],
                "gd": row["goalDifference"], "points": row["points"],
                "form": row.get("form"),
            }
    return out
