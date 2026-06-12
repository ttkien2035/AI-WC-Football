"""Anonymous usage analytics (admin dashboard charts).

Privacy: no PII — the visitor id is a random UUID the browser generates and
keeps in localStorage; we store only that hash, an event type from a fixed
whitelist, and a small payload (e.g. which matchup was predicted).
"""
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from .cache import _CACHE_DIR

_DB = _CACHE_DIR / "cache.sqlite"
_lock = threading.Lock()

EVENT_TYPES = {"visit", "tab", "predict", "lang", "live_view", "odds_view", "chat"}
_MAX_STR = 64


def _conn():
    c = sqlite3.connect(_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, day TEXT, visitor TEXT, type TEXT, data TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_day ON events(day)")
    return c


def record(visitor: str, ev_type: str, data: dict | None) -> bool:
    if ev_type not in EVENT_TYPES or not visitor:
        return False
    visitor = str(visitor)[:_MAX_STR]
    clean = {k[:24]: str(v)[:_MAX_STR] for k, v in (data or {}).items()} if data else {}
    now = datetime.now(timezone.utc)
    with _lock, _conn() as c:
        c.execute("INSERT INTO events (ts, day, visitor, type, data) VALUES (?,?,?,?,?)",
                  (time.time(), now.strftime("%Y-%m-%d"), visitor, ev_type,
                   json.dumps(clean)))
    return True


def summary(days: int = 14) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    with _lock, _conn() as c:
        daily = c.execute("""
            SELECT day, COUNT(DISTINCT visitor), COUNT(*) FROM events
            GROUP BY day ORDER BY day DESC LIMIT ?""", (days,)).fetchall()
        tabs = c.execute("""
            SELECT json_extract(data,'$.tab'), COUNT(*) FROM events
            WHERE type='tab' GROUP BY 1 ORDER BY 2 DESC LIMIT 12""").fetchall()
        matchups = c.execute("""
            SELECT json_extract(data,'$.pair'), COUNT(*) FROM events
            WHERE type='predict' GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall()
        langs = c.execute("""
            SELECT json_extract(data,'$.lang'), COUNT(DISTINCT visitor) FROM events
            WHERE type IN ('visit','lang') GROUP BY 1""").fetchall()
        totals = c.execute(
            "SELECT COUNT(DISTINCT visitor), COUNT(*) FROM events").fetchone()
        # hourly activity over the last 7 days (UTC) — reveals peak times
        hourly = dict(c.execute("""
            SELECT CAST(strftime('%H', ts, 'unixepoch') AS INT), COUNT(*)
            FROM events WHERE ts > ? GROUP BY 1""",
            (time.time() - 7 * 86400,)).fetchall())
        # feature reach: distinct visitors who used each feature
        feat = dict(c.execute("""
            SELECT type, COUNT(DISTINCT visitor) FROM events GROUP BY type""").fetchall())
        # retention: visitors seen on >= 2 distinct days
        returning = c.execute("""
            SELECT COUNT(*) FROM (SELECT visitor FROM events
            GROUP BY visitor HAVING COUNT(DISTINCT day) >= 2)""").fetchone()[0]
        v_today = c.execute(
            "SELECT COUNT(DISTINCT visitor) FROM events WHERE day=?", (today,)).fetchone()[0]
        v_yday = c.execute(
            "SELECT COUNT(DISTINCT visitor) FROM events WHERE day=?", (yday,)).fetchone()[0]

    tv, te = totals[0] or 0, totals[1] or 0
    return {
        "kpis": {
            "visitors": tv, "events": te,
            "events_per_visitor": round(te / tv, 1) if tv else 0,
            "active_today": v_today, "active_yesterday": v_yday,
            "returning": returning,
            "returning_pct": round(100 * returning / tv) if tv else 0,
        },
        "daily": [{"date": d, "visitors": v, "events": e}
                  for d, v, e in reversed(daily)],
        "hourly": [{"hour": h, "n": hourly.get(h, 0)} for h in range(24)],
        "features": [{"feature": k, "visitors": v}
                     for k, v in sorted(feat.items(), key=lambda x: -x[1])],
        "tabs": [{"tab": t or "?", "n": n} for t, n in tabs],
        "matchups": [{"pair": p or "?", "n": n} for p, n in matchups],
        "langs": [{"lang": l or "?", "n": n} for l, n in langs],
        "totals": {"visitors": tv, "events": te},
    }
