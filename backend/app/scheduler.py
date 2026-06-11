"""Auto-refresh loop: keeps data current for the whole tournament.

- During a live window (a match in play, or kickoff within 10 min):
  refresh matches every 60s.
- Otherwise: refresh every 10 min (and sleep up to 30 min when the next
  kickoff is far away).
- When new FINISHED matches are detected: invalidate the simulation cache
  and precompute a fresh tournament simulation so the UI stays instant.
"""
import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import cache, service
from .engine import ml_ensemble

log = logging.getLogger("scheduler")

_state = {"finished_ids": set(), "running": False, "retraining": False}

BACKEND_DIR = Path(__file__).resolve().parents[1]
RETRAIN_HOUR_UTC = 3          # nightly, after the day's matches are done
RETRAIN_KEY = "ml:last_retrain_date"


def _retrain_blocking() -> bool:
    """Re-download the upstream dataset (refreshed with new internationals,
    incl. WC results) and retrain all models. Old artifacts stay in place if
    anything fails."""
    data_cache = BACKEND_DIR / "ml" / "data" / "results.csv"
    data_cache.unlink(missing_ok=True)        # force fresh download
    r = subprocess.run([sys.executable, "-m", "ml.train"],
                       cwd=BACKEND_DIR, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        log.error("retrain failed:\n%s", r.stdout[-2000:] + r.stderr[-2000:])
        return False
    log.info("retrain OK:\n%s", "\n".join(r.stdout.splitlines()[-8:]))
    return True


async def maybe_retrain(force: bool = False) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last, _ = cache.get_stale(RETRAIN_KEY)
    due = force or (datetime.now(timezone.utc).hour == RETRAIN_HOUR_UTC and last != today)
    if not due or _state["retraining"]:
        return False
    _state["retraining"] = True
    try:
        ok = await asyncio.to_thread(_retrain_blocking)
        if ok:
            cache.put(RETRAIN_KEY, today)
            ml_ensemble.reload()
            cache.invalidate("sim:")
            await service.run_simulation(force=True)
        return ok
    finally:
        _state["retraining"] = False


def _next_kickoff_s(matches) -> float | None:
    now = datetime.now(timezone.utc)
    future = [
        (datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")) - now).total_seconds()
        for m in matches
        if m["status"] in ("TIMED", "SCHEDULED")
    ]
    return min(future) if future else None


async def _tick() -> float:
    """One refresh pass. Returns seconds to sleep until the next pass."""
    matches = await service.get_matches(force=True)

    finished = {m["id"] for m in matches if m["status"] == "FINISHED"}
    new_finished = finished - _state["finished_ids"]
    if new_finished:
        log.info("New finished matches: %s — recomputing simulation", sorted(new_finished))
        cache.invalidate("fd:/competitions/WC/standings")
        service.record_corner_stats(matches)
        service.record_match_log(matches)
        await service.run_simulation(force=True)
    elif not _state["finished_ids"] and not await service.latest_simulation():
        await service.run_simulation()       # first boot: warm the cache
    _state["finished_ids"] = finished

    live = any(m["status"] in service.LIVE_STATUSES for m in matches)
    if live:
        try:
            await service.snapshot_live()    # win-prob timeline points
        except Exception:
            log.exception("snapshot_live failed")
    else:
        await maybe_retrain()       # nightly model refresh, never during a match
    nk = _next_kickoff_s(matches)
    if live or (nk is not None and nk < 600):
        return 60.0
    if nk is None:
        return 1800.0
    return min(max(nk - 300, 600.0), 1800.0)


async def run() -> None:
    if _state["running"]:
        return
    _state["running"] = True
    while True:
        try:
            delay = await _tick()
        except Exception:
            log.exception("scheduler tick failed; retrying in 120s")
            delay = 120.0
        await asyncio.sleep(delay)
