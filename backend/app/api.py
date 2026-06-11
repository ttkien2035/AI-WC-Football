"""JSON API consumed by the React frontend."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from . import evaluation, service
from .config import settings
from .engine import ml_ensemble
from .static_data import MATCH_SCHEDULE, R32, R16, QF, SF, TEAMS

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/teams")
async def teams():
    return await service.get_teams()


@router.get("/groups")
async def groups():
    t = await service.get_teams()
    sim = await service.latest_simulation()
    sim_teams = (sim or {}).get("teams", {})
    out: dict[str, list] = {}
    for tla, row in t.items():
        row = dict(row)
        row["sim"] = sim_teams.get(tla)
        out.setdefault(row["group"], []).append(row)
    for g in out:
        out[g].sort(key=lambda r: r["position"])
    return {"groups": dict(sorted(out.items())),
            "sim_meta": {k: sim[k] for k in ("runs", "computed_at", "fingerprint")}
            if sim else None}


@router.get("/matches")
async def matches(stage: str | None = None, group: str | None = None):
    ms = await service.get_matches()
    if stage:
        ms = [m for m in ms if m["stage"] == stage]
    if group:
        ms = [m for m in ms if (m["group"] or "").endswith(group.upper())]
    return {"matches": ms}


@router.get("/live")
async def live():
    ms = await service.get_matches()
    return {
        "live": [m for m in ms if m["status"] in service.LIVE_STATUSES],
        "today": [m for m in ms if m["utcDate"][:10] ==
                  datetime.now(timezone.utc).strftime("%Y-%m-%d")],
    }


@router.get("/live/{match_id}/timeline")
async def live_timeline(match_id: int):
    return {"match_id": match_id, "points": service.timeline(match_id)}


@router.get("/match/{home}/{away}/analysis")
async def match_analysis(home: str, away: str):
    try:
        return await service.analysis(home.upper(), away.upper())
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/match/{home}/{away}/predict")
async def predict(home: str, away: str,
                  minute: int | None = Query(default=None, ge=0, le=120),
                  hg: int = Query(default=0, ge=0),
                  ag: int = Query(default=0, ge=0)):
    try:
        return await service.predict(home.upper(), away.upper(), minute, hg, ag)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/simulate")
async def simulate(runs: int = Query(default=settings.n_sims_tournament,
                                     ge=1000, le=200_000),
                   force: bool = False):
    return await service.run_simulation(runs=runs, force=force)


@router.get("/bracket")
async def bracket():
    sim = await service.latest_simulation() or await service.run_simulation()
    ms = await service.get_matches()
    real = {m["stage"]: [] for m in ms}
    for m in ms:
        if m["stage"] != "GROUP_STAGE":
            real[m["stage"]].append(m)
    return {
        "routing": {"r32": {m: R32[m] for m in sorted(R32)},
                    "r16": {m: R16[m] for m in sorted(R16)},
                    "qf": {m: QF[m] for m in sorted(QF)},
                    "sf": {m: SF[m] for m in sorted(SF)},
                    "final": {104: ["W101", "W102"]}},
        "sim": sim.get("bracket"),
        "real": {k: v for k, v in real.items() if k != "GROUP_STAGE"},
        "schedule": {m: {"date": d, "city": c} for m, (d, c) in MATCH_SCHEDULE.items()},
        "meta": {k: sim.get(k) for k in ("runs", "computed_at", "fingerprint")},
    }


@router.get("/odds")
async def odds(limit: int = Query(default=24, ge=1, le=104)):
    return await service.odds_board(limit=limit)


@router.get("/sources/status")
async def sources():
    return await service.sources_status()


# ── ML pipeline ─────────────────────────────────────────────
@router.get("/ml/status")
async def ml_status():
    from . import cache
    from .scheduler import RETRAIN_KEY, _state
    matches = await service.get_matches()
    finished = service._finished_tuple(matches)
    last_retrain, _ = cache.get_stale(RETRAIN_KEY)
    return {
        "available": ml_ensemble.available(),
        "report": ml_ensemble.report(),
        "last_retrain": last_retrain,
        "retraining_now": _state["retraining"],
        "online_updates_applied": len(finished),
        "ratings": ml_ensemble.current_ratings(finished),
    }


@router.post("/ml/retrain")
async def ml_retrain():
    from . import scheduler
    ok = await scheduler.maybe_retrain(force=True)
    if ok:
        evaluation.reload()
    return {"ok": ok}


# ── Evaluation (grade the model on real past matches) ───────
@router.get("/evaluate/summary")
async def evaluate_summary():
    return evaluation.summary()


@router.get("/evaluate/h2h/{home}/{away}")
async def evaluate_h2h(home: str, away: str, n: int = Query(default=10, ge=1, le=50)):
    return evaluation.h2h(home.upper(), away.upper(), n)


@router.get("/evaluate/team/{tla}")
async def evaluate_team(tla: str, n: int = Query(default=12, ge=1, le=50)):
    return evaluation.team_recent(tla.upper(), n)


@router.post("/refresh")
async def refresh():
    await service.get_matches(force=True)
    sim = await service.run_simulation(force=True)
    return {"ok": True, "sim_computed_at": sim["computed_at"]}


@router.get("/meta/static")
async def meta_static():
    return {"teams": TEAMS}
