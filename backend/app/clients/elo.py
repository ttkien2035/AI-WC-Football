"""World Football Elo ratings (eloratings.net).

The site is a thin SPA over TSV datafiles. We try the live TSV; any failure
falls back to the bundled static snapshot in static_data.TEAMS. Either way the
result is {TLA: elo} for the 48 WC teams, cached for a day.
"""
import re
import httpx
from .. import cache
from ..config import settings
from ..static_data import TEAMS, ELO_CODE_TO_TLA

_KEY = "elo:ratings"


def _static() -> dict[str, float]:
    return {tla: float(t["elo"]) for tla, t in TEAMS.items()}


def _parse_tsv(text: str) -> dict[str, float]:
    """Rows contain a team code and a 4-digit rating; layout is positional but
    we match defensively: code field + first plausible rating field."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        fields = line.split("\t")
        code = next((f for f in fields if f in ELO_CODE_TO_TLA), None)
        if not code:
            continue
        rating = next(
            (float(f) for f in fields if re.fullmatch(r"[12]\d{3}", f.strip())),
            None,
        )
        if rating:
            out[ELO_CODE_TO_TLA[code]] = rating
    return out


async def ratings() -> tuple[dict[str, float], str]:
    """Returns ({TLA: elo}, source) where source is 'live' or 'static'."""
    hit = cache.get(_KEY, settings.ttl_elo)
    if hit is not None:
        return hit["ratings"], hit["source"]

    merged, source = _static(), "static"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(f"{settings.elo_base}/World.tsv")
            r.raise_for_status()
            live = _parse_tsv(r.text)
        if len(live) >= 30:  # sanity: most of the 48 teams matched
            merged.update(live)
            source = "live"
    except (httpx.HTTPError, ValueError):
        pass

    cache.put(_KEY, {"ratings": merged, "source": source})
    return merged, source
