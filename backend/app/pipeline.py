"""AI/ML pipeline monitoring (admin-only).

- Pre-match prediction snapshots: the prediction as it stood BEFORE kickoff
  is persisted, so post-match review compares what the model actually said —
  never a hindsight re-prediction.
- review(): finished matches graded against those snapshots, with factors
  (red cards, HT swing, corners, key absences) and the Elo shift the online
  update applied.
- status(): data-collection counters, scheduler heartbeat, ML/retrain state,
  biggest in-tournament Elo movers.
"""
import math
from datetime import datetime, timedelta, timezone

from . import cache, service
from .engine import ml_ensemble

PREMATCH_WINDOW_H = 12       # snapshot anything kicking off within 12h
LINEUP_REFRESH_MIN = 100     # re-snapshot inside this window once XIs are out


async def record_prematch(matches: list[dict] | None = None) -> int:
    """Persist pre-kickoff predictions (scheduler calls this every tick)."""
    matches = matches if matches is not None else await service.get_matches()
    now = datetime.now(timezone.utc)
    n = 0
    for m in matches:
        if m["status"] not in ("TIMED", "SCHEDULED"):
            continue
        h, a = m["home"]["tla"], m["away"]["tla"]
        if not h or not a:
            continue
        ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
        until = (ko - now).total_seconds()
        if until < 0 or until > PREMATCH_WINDOW_H * 3600:
            continue
        key = f"prematch:{m['id']}"
        existing, _ = cache.get_stale(key)
        lineup_known = bool(m.get("lineups"))
        needs_lineup_refresh = (lineup_known and existing
                                and not existing.get("lineup_aware")
                                and until < LINEUP_REFRESH_MIN * 60)
        if existing and not needs_lineup_refresh:
            continue
        try:
            pred = await service.predict(h, a)
        except Exception:
            continue
        cache.put(key, {
            "probs": pred["probs"],
            "lambdas": pred["lambdas"],
            "top_score": pred["scorelines"][0] if pred["scorelines"] else None,
            "absence": pred.get("absence_penalty"),
            "lineup_aware": lineup_known,
            "ts": now.isoformat(timespec="seconds"),
        })
        n += 1
    return n


def _surprise_tag(correct: bool, p_actual: float, p_pick: float) -> str:
    if correct and p_pick >= 0.55:
        return "confident_hit"
    if correct:
        return "hit"
    if p_actual < 0.15:
        return "big_upset"
    if p_actual < 0.30:
        return "upset"
    return "near_miss"


async def review(limit: int = 30) -> dict:
    matches = await service.get_matches()
    finished = [m for m in matches
                if m["status"] == "FINISHED" and m["home"]["tla"]
                and m["score"]["home"] is not None]
    finished.sort(key=lambda m: m["utcDate"])
    all_t = service._finished_tuple(matches)

    rows = []
    n_correct, rps_sum, ll_sum = 0, 0.0, 0.0
    for i, m in enumerate(finished):
        h, a = m["home"]["tla"], m["away"]["tla"]
        gh, ga = m["score"]["home"], m["score"]["away"]
        actual = "home" if gh > ga else ("draw" if gh == ga else "away")

        pm, _ = cache.get_stale(f"prematch:{m['id']}")
        if pm:
            probs, src = pm["probs"], "prematch_snapshot"
        else:
            # leave-one-out as-of recompute: only matches finished BEFORE this one
            entry = (h, a, gh, ga)
            idx = all_t.index(entry) if entry in all_t else len(all_t)
            probs = ml_ensemble.predict_wdl(h, a, all_t[:idx]) or \
                {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
            src = "as_of_recompute"

        pick = max(probs, key=probs.get)
        p_actual = probs[actual]
        correct = pick == actual
        n_correct += correct
        order = ("home", "draw", "away")
        cp, co = 0.0, 0.0
        rps = 0.0
        for k in order[:2]:
            cp += probs[k]
            co += 1.0 if order.index(actual) <= order.index(k) else 0.0
            rps += (cp - co) ** 2
        rps_sum += rps / 2
        ll_sum += -math.log(max(p_actual, 1e-12))

        # Elo shift the online update applied for this match
        entry = (h, a, gh, ga)
        idx = all_t.index(entry) if entry in all_t else None
        elo_shift = None
        if idx is not None:
            before = ml_ensemble.elo_by_tla(all_t[:idx]) or {}
            after = ml_ensemble.elo_by_tla(all_t[:idx + 1]) or {}
            if h in before and h in after:
                elo_shift = {"home": round(after[h] - before[h], 1),
                             "away": round(after[a] - before[a], 1)}

        ht = m.get("ht_score")
        rows.append({
            "match_id": m["id"], "date": m["utcDate"], "stage": m["stage"],
            "home": m["home"], "away": m["away"],
            "score": {"home": gh, "away": ga}, "ht_score": ht,
            "probs": {k: round(v, 4) for k, v in probs.items()},
            "probs_source": src,
            "predicted": pick, "actual": actual, "correct": correct,
            "p_actual": round(p_actual, 4),
            "tag": _surprise_tag(correct, p_actual, probs[pick]),
            "factors": {
                "red_cards": m.get("red_cards"),
                "corners": m.get("corners"),
                "ht_swing": bool(ht and ht["home"] is not None and (
                    ("home" if ht["home"] > ht["away"] else
                     "draw" if ht["home"] == ht["away"] else "away") != actual)),
                "absence": (pm or {}).get("absence"),
                "lineup_aware": (pm or {}).get("lineup_aware"),
            },
            "elo_shift": elo_shift,
        })

    n = len(rows)
    return {
        "matches": list(reversed(rows)),          # newest first
        "summary": ({"n": n, "correct": n_correct,
                     "accuracy": round(n_correct / n, 4),
                     "rps": round(rps_sum / n, 4),
                     "logloss": round(ll_sum / n, 4)} if n else None),
    }


async def status() -> dict:
    matches = await service.get_matches()
    now = datetime.now(timezone.utc)
    finished = [m for m in matches if m["status"] == "FINISHED"]
    live = [m for m in matches if m["status"] in service.LIVE_STATUSES]

    last_tick, _ = cache.get_stale("scheduler:last_tick")
    next_retrain = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now.hour >= 3:
        next_retrain += timedelta(days=1)
    last_retrain, _ = cache.get_stale("ml:last_retrain_date")

    # biggest in-tournament Elo movers (trained base vs online-updated)
    movers = []
    base = ml_ensemble.elo_by_tla(()) or {}
    cur = ml_ensemble.elo_by_tla(service._finished_tuple(matches)) or {}
    for t in base:
        d = round(cur.get(t, base[t]) - base[t], 1)
        if d:
            movers.append({"tla": t, "delta": d, "elo": round(cur[t], 0)})
    movers.sort(key=lambda x: -abs(x["delta"]))

    rep = ml_ensemble.report()
    from .scheduler import _state
    return {
        "collection": {
            "matches_total": len(matches),
            "finished": len(finished),
            "live_now": len(live),
            "match_log": cache.count("matchlog:"),
            "prematch_snapshots": cache.count("prematch:"),
            "timeline_series": cache.count("timeline:"),
            "teams_with_corner_stats": cache.count("teamstats:corners:"),
        },
        "scheduler": {"last_tick": last_tick,
                      "live_mode": bool(live)},
        "ml": {
            "available": ml_ensemble.available(),
            "online_updates_applied": len(service._finished_tuple(matches)),
            "last_retrain": last_retrain,
            "retraining_now": _state["retraining"],
            "next_retrain_utc": next_retrain.isoformat(timespec="minutes"),
            "weights": (rep or {}).get("weights"),
            "test_rps": ((rep or {}).get("test_metrics", {})
                         .get("ENSEMBLE", {}).get("rps")),
        },
        "elo_movers": movers[:10],
        "sources": await service.sources_status(),
    }
