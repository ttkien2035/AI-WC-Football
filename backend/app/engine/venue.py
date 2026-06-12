"""Venue-conditions λ factor for total goals (WC-2026-specific).

Altitude: ball travels faster + quicker fatigue → historically more goals.
Heat: open-roof stadium + hot host city + afternoon (local) kickoff → lower
tempo, fewer late goals. Roofed/AC stadiums neutralize heat. Bounded,
env-tunable, audited via the pipeline like the style/context layers.
"""
from datetime import datetime, timezone

from ..config import settings
from ..venue_data import resolve_venue


def conditions_factor(venue_str: str | None, kickoff_utc: str | None,
                      city: str | None = None) -> dict:
    """{factor, note, venue} — λ multiplier from altitude + heat."""
    out = {"factor": 1.0, "note": None, "venue": None}
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

    # heat: hot city, open roof, afternoon local kickoff (12:00-17:00)
    if v["hot"] and not v["roof"] and kickoff_utc:
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
