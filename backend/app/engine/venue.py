"""Venue-conditions λ factor for total goals (WC-2026-specific).

Altitude: ball travels faster + quicker fatigue → historically more goals.
Heat: open-roof stadium + hot kickoff → lower tempo, fewer late goals.
Roofed/AC stadiums neutralize heat.

Heat has two modes:
- weather: a real Open-Meteo forecast for the kickoff hour (passed in by
  service.predict) scales the cut linearly with APPARENT temperature from
  weather_heat_start_c (no cut) to weather_heat_full_c (full venue_heat_max).
- static fallback: hot-city flag + afternoon local kickoff window, as before
  (no forecast available: match beyond horizon, API down, weather disabled).

Bounded, env-tunable, audited via the pipeline like the style/context layers.
"""
from datetime import datetime, timezone

from ..config import settings
from ..venue_data import resolve_venue


def conditions_factor(venue_str: str | None, kickoff_utc: str | None,
                      city: str | None = None,
                      weather: dict | None = None) -> dict:
    """{factor, note, notes, venue, weather} — λ multiplier from altitude + heat."""
    out = {"factor": 1.0, "note": None, "venue": None, "weather": None}
    if not settings.venue_adjust_enabled:
        return out
    v = resolve_venue(venue_str, city)
    if not v:
        return out
    out["venue"] = {"stadium": v["stadium"], "city": v["city"],
                    "alt": v["alt"], "roof": v["roof"]}
    factor, notes = 1.0, []

    # altitude: +k per 1000 m above ~500 m (Mexico City ~+6%, Guadalajara ~+3%)
    if v["alt"] >= 1000:
        bump = min(settings.venue_alt_max, (v["alt"] - 500) / 1000 * 0.035)
        factor *= 1 + bump
        notes.append({"key": "ctx_altitude",
                      "params": {"city": v["city"], "alt": v["alt"]}})

    # heat — roofed/AC stadiums are always neutral
    if not v["roof"]:
        if weather and weather.get("apparent_c") is not None:
            # real forecast: linear ramp on apparent temperature
            t0, t1 = settings.weather_heat_start_c, settings.weather_heat_full_c
            app_c = weather["apparent_c"]
            if app_c > t0:
                frac = min(1.0, (app_c - t0) / max(t1 - t0, 0.1))
                factor *= 1 - settings.venue_heat_max * frac
                notes.append({"key": "ctx_heat_real",
                              "params": {"city": v["city"],
                                         "temp": round(weather["temp_c"]),
                                         "feels": round(app_c),
                                         "humidity": weather.get("humidity")}})
            out["weather"] = {k: weather.get(k) for k in
                              ("temp_c", "apparent_c", "humidity", "wind_kmh")}
        elif v["hot"] and kickoff_utc:
            # static fallback: hot city + open roof + afternoon local kickoff
            try:
                ko = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
                local_h = (ko.astimezone(timezone.utc).hour + v["tz"]) % 24
                if 12 <= local_h <= 17:
                    factor *= 1 - settings.venue_heat_max
                    notes.append({"key": "ctx_heat",
                                  "params": {"city": v["city"], "hour": local_h}})
            except Exception:
                pass

    out["factor"] = round(factor, 3)
    out["note"] = notes[0] if notes else None
    out["notes"] = notes
    return out
