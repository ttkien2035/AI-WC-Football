"""Tiny SQLite TTL cache so free-tier APIs are never hammered.

The DB also persists the app's own tournament data (match log, corner stats),
so in Docker it lives on a volume: set CACHE_DIR=/data.
"""
import json
import os
import sqlite3
import time
import threading
from pathlib import Path
from .config import DATA_DIR

_CACHE_DIR = Path(os.environ.get("CACHE_DIR", DATA_DIR))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_DB = _CACHE_DIR / "cache.sqlite"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(_DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts REAL)"
    )
    return c


def get(key: str, ttl: float):
    with _lock, _conn() as c:
        row = c.execute("SELECT v, ts FROM cache WHERE k=?", (key,)).fetchone()
    if row and time.time() - row[1] < ttl:
        return json.loads(row[0])
    return None


def get_stale(key: str):
    """Return the cached value regardless of age (fallback when source is down)."""
    with _lock, _conn() as c:
        row = c.execute("SELECT v, ts FROM cache WHERE k=?", (key,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def put(key: str, value) -> None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (key, json.dumps(value), time.time()),
        )


def invalidate(prefix: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM cache WHERE k LIKE ?", (prefix + "%",))


def age(key: str):
    with _lock, _conn() as c:
        row = c.execute("SELECT ts FROM cache WHERE k=?", (key,)).fetchone()
    return time.time() - row[0] if row else None
