"""Open-Meteo forecast for venue conditions (free, no API key).

Gives the venue heat factor REAL numbers (temperature / humidity / wind at
kickoff) instead of the static hot-city + afternoon-window heuristic. The
forecast horizon is ~16 days; outside it (or on any error) we return None
and engine/venue.py falls back to the static table — never breaks predict.

Cached per (city, kickoff-hour): forecasts barely move hour-to-hour, so a
generous TTL keeps us a polite citizen of a free API.
"""
from datetime import datetime, timezone

import httpx

from .. import cache
from ..config import settings
from ..venue_data import CITY_COORDS

_URL = "https://api.open-meteo.com/v1/forecast"


async def kickoff_conditions(city: str | None, kickoff_utc: str | None) -> dict | None:
    """{temp_c, apparent_c, humidity, wind_kmh, precip_mm} at kickoff, or None."""
    if not settings.weather_enabled or not city or not kickoff_utc:
        return None
    coords = CITY_COORDS.get(city)
    if not coords:
        return None
    try:
        ko = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    horizon = (ko - datetime.now(timezone.utc)).days
    if horizon < 0 or horizon > 15:        # past or beyond forecast horizon
        return None

    hour_iso = ko.strftime("%Y-%m-%dT%H:00")
    key = f"weather:{city}:{hour_iso}"
    hit = cache.get(key, settings.ttl_weather)
    if hit is not None:
        return hit or None                 # cached {} = known-unavailable

    out = None
    try:
        async with httpx.AsyncClient(timeout=settings.weather_timeout_s) as cl:
            r = await cl.get(_URL, params={
                "latitude": coords[0], "longitude": coords[1],
                "hourly": "temperature_2m,apparent_temperature,"
                          "relative_humidity_2m,wind_speed_10m,precipitation",
                "start_date": ko.strftime("%Y-%m-%d"),
                "end_date": ko.strftime("%Y-%m-%d"),
                "timezone": "UTC",
            })
            r.raise_for_status()
            h = r.json()["hourly"]
            i = h["time"].index(hour_iso)
            out = {
                "temp_c": h["temperature_2m"][i],
                "apparent_c": h["apparent_temperature"][i],
                "humidity": h["relative_humidity_2m"][i],
                "wind_kmh": h["wind_speed_10m"][i],
                "precip_mm": h["precipitation"][i],
            }
    except Exception:
        out = None
    cache.put(key, out or {})              # cache misses too (avoid hammering)
    return out
