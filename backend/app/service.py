"""Orchestration: merge data sources, estimate live minutes, cache simulations."""
import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone

from . import cache
from .clients import football_data as fd
from .clients import elo as elo_client
from .clients import livescore
from .clients import odds as odds_client
from .config import settings
from .engine import (match_model, match_sim, ml_ensemble, periods,
                     style_adjust, tournament)
from .static_data import TEAMS

LIVE_STATUSES = ("IN_PLAY", "PAUSED", "LIVE")


def estimate_minute(utc_date: str, status: str) -> int | None:
    """fd.org free tier has no live minute; estimate from kickoff time
    (15' half-time assumed). Only meaningful for IN_PLAY/PAUSED."""
    if status not in LIVE_STATUSES:
        return None
    kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - kickoff).total_seconds() / 60.0
    if elapsed <= 0:
        return 0
    if elapsed > 45:
        elapsed -= 15  # half-time break
    return int(max(0, min(90, elapsed)))


async def get_teams() -> dict[str, dict]:
    """Standings merged with static metadata + live Elo."""
    table = await fd.teams_from_standings()
    ratings, elo_source = await elo_client.ratings()
    for tla, t in table.items():
        meta = TEAMS.get(tla, {})
        t["elo"] = ratings.get(tla, meta.get("elo", 1700))
        t["fifa_rank"] = meta.get("fifa")
        t["pot"] = meta.get("pot")
    return table


async def get_matches(force: bool = False) -> list[dict]:
    ms = await fd.all_matches_simple(force=force)
    try:
        ls = await livescore.enrichment()
    except Exception:
        ls = {}
    for m in ms:
        minute = estimate_minute(m["utcDate"], m["status"])
        m["minute_estimate"] = minute

        # LiveScore enrichment: real minute, fresher score, HT score, corners
        e = ls.get(frozenset({m["home"]["tla"], m["away"]["tla"]})) if ls else None
        if e:
            flipped = e["home_tla"] != m["home"]["tla"]

            def _flip(d):
                return ({"home": d["away"], "away": d["home"]} if flipped else d) if d else d

            if e.get("lineups"):
                lu = e["lineups"]
                m["lineups"] = ({"home": lu.get("away"), "away": lu.get("home")}
                                if flipped else lu)
            if e.get("venue"):
                m["venue"] = e["venue"]
        if e and (e["live"] or e["finished"]):
            if e["minute"] is not None:
                m["minute_estimate"] = minute = e["minute"]
                m["minute_source"] = "livescore"
            sc = e["score"]
            if sc["home"] is not None:
                m["score_live"] = _flip(sc)
                if m["status"] not in ("FINISHED",) and e["live"]:
                    m["status"] = "IN_PLAY"
                    m["score"] = {**m["score"], **m["score_live"]}
            ht = e["ht_score"]
            if ht["home"] is not None:
                m["ht_score"] = _flip(ht)
            if e.get("corners"):
                m["corners"] = _flip(e["corners"])
            if e.get("stats"):
                # keep aggregated stats (incl. xg); drop bulky raw _shotmap
                m["stats"] = {k: _flip(v) for k, v in e["stats"].items()
                              if not k.startswith("_")}
            if e.get("red_cards"):
                m["red_cards"] = _flip(e["red_cards"])
            if e.get("incidents"):
                m["incidents"] = [
                    {**i, "side": ({"home": "away", "away": "home"}.get(i["side"], i["side"])
                                   if flipped else i["side"])}
                    for i in e["incidents"]
                ]

        if minute is not None:
            m["remaining_frac"] = max(90 - minute, 0) / 90.0
    return ms


def record_match_log(matches: list[dict]) -> None:
    """Persist the app's own structured record of every finished match
    (result, HT, corners, incidents, stats). Runs every scheduler tick and
    MERGES: never overwrite a captured value with null (live enrichment for a
    match disappears after the day boundary — keep what we caught)."""
    for m in matches:
        if m["status"] != "FINISHED" or not m["home"]["tla"]:
            continue
        key = f"matchlog:{m['id']}"
        old, _ = cache.get_stale(key)
        old = old or {}
        fresh = {
            "id": m["id"], "date": m["utcDate"], "stage": m["stage"],
            "group": m.get("group"),
            "home": m["home"]["tla"], "away": m["away"]["tla"],
            "home_name": m["home"]["name"], "away_name": m["away"]["name"],
            "home_crest": m["home"]["crest"], "away_crest": m["away"]["crest"],
            "score": m["score"], "ht_score": m.get("ht_score"),
            "corners": m.get("corners"), "stats": m.get("stats"),
            "incidents": m.get("incidents"),
        }
        merged = dict(old)
        for k, v in fresh.items():
            keep_old = (v is None or (k == "score" and v.get("home") is None)
                        or (k == "incidents" and not v))
            if not (keep_old and old.get(k) is not None):
                merged[k] = v
        cache.put(key, merged)


async def recent_results(n: int = 10) -> list[dict]:
    """Finished matches, newest first, enriched from the persisted match log
    (incidents/corners survive even after live enrichment expires)."""
    matches = await get_matches()
    done = [m for m in matches if m["status"] == "FINISHED" and m["home"]["tla"]]
    done.sort(key=lambda m: m["utcDate"], reverse=True)
    out = []
    for m in done[:n]:
        log_entry, _ = cache.get_stale(f"matchlog:{m['id']}")
        log_entry = log_entry or {}
        out.append({
            "id": m["id"], "date": m["utcDate"], "stage": m["stage"],
            "group": m.get("group"), "home": m["home"], "away": m["away"],
            "score": m["score"] if m["score"]["home"] is not None else log_entry.get("score"),
            "ht_score": m.get("ht_score") or log_entry.get("ht_score"),
            "corners": m.get("corners") or log_entry.get("corners"),
            "stats": m.get("stats") or log_entry.get("stats"),
            "incidents": m.get("incidents") or log_entry.get("incidents") or [],
        })
    return out


def record_corner_stats(matches: list[dict]) -> None:
    """Persist per-team corner counts (+ crosses, a documented corner driver)
    from finished matches so the corners model learns team rates in-tournament."""
    for m in matches:
        if m["status"] != "FINISHED" or not m.get("corners"):
            continue
        stats = m.get("stats") or {}
        crs = stats.get("crosses") or {}
        for side, opp in (("home", "away"), ("away", "home")):
            tla = m[side]["tla"]
            if not tla or m["corners"][side] is None:
                continue
            key = f"teamstats:corners:{tla}"
            hist, _ = cache.get_stale(key)
            hist = hist or {}
            hist[str(m["id"])] = {"for": m["corners"][side],
                                  "against": m["corners"][opp],
                                  "crosses": crs.get(side)}
            cache.put(key, hist)


def observed_corner_mean() -> tuple[float, int] | None:
    """Tournament-wide mean TOTAL corners per finished match (self-learning
    signal): the club-fitted base over-predicts WC corners, so we measure the
    real level as matches accumulate."""
    totals = []
    for key in cache.keys("matchlog:"):
        e, _ = cache.get_stale(key)
        c = (e or {}).get("corners") or {}
        if c.get("home") is not None and c.get("away") is not None:
            totals.append(c["home"] + c["away"])
    return (sum(totals) / len(totals), len(totals)) if totals else None


def adaptive_corners_base() -> float:
    """Club-fitted base shrunk toward the observed in-tournament mean, weight
    n/(n+K) — adapts the corner level to WC reality after every match while a
    handful of games can't yank it around. OFF -> static club base."""
    if not settings.corners_adapt_enabled:
        return settings.corners_base
    obs = observed_corner_mean()
    if not obs:
        return settings.corners_base
    mean, n = obs
    w = n / (n + settings.corners_adapt_k)
    return round((1 - w) * settings.corners_base + w * mean, 3)


def corner_rates(tla: str) -> dict | None:
    """Per-team in-tournament corner profile: earned, conceded, and crosses
    per game (the concede rate feeds the OPPONENT's expected corners)."""
    hist, _ = cache.get_stale(f"teamstats:corners:{tla}")
    if not hist:
        return None
    fors = [v["for"] for v in hist.values() if v.get("for") is not None]
    against = [v["against"] for v in hist.values() if v.get("against") is not None]
    crosses = [v["crosses"] for v in hist.values() if v.get("crosses") is not None]
    if not fors:
        return None
    out = {"games": len(fors), "for_avg": sum(fors) / len(fors)}
    if against:
        out["against_avg"] = sum(against) / len(against)
    if crosses:
        out["cross_avg"] = sum(crosses) / len(crosses)
    return out


def _fingerprint(matches: list[dict], runs: int) -> str:
    sig = [
        (m["id"], m["status"], m["score"]["home"], m["score"]["away"],
         m["home"]["tla"], m["away"]["tla"])
        for m in matches
    ]
    raw = json.dumps([runs, sorted(sig)], default=str)
    return hashlib.sha1(raw.encode()).hexdigest()


def _finished_tuple(matches: list[dict]) -> tuple:
    """Chronological (home_tla, away_tla, gh, ga) of FINISHED matches — feeds
    the ML online rating update."""
    done = [m for m in matches if m["status"] == "FINISHED"
            and m["home"]["tla"] and m["away"]["tla"]
            and m["score"]["home"] is not None]
    done.sort(key=lambda m: m["utcDate"])
    return tuple((m["home"]["tla"], m["away"]["tla"],
                  m["score"]["home"], m["score"]["away"]) for m in done)


def _real_ko(matches: list[dict]) -> list[dict]:
    out = []
    for m in matches:
        if m["stage"] == "GROUP_STAGE" or not m["home"]["tla"] or not m["away"]["tla"]:
            continue
        winner = None
        if m["status"] == "FINISHED":
            w = m["score"].get("winner")
            winner = m["home"]["tla"] if w == "HOME_TEAM" else (
                m["away"]["tla"] if w == "AWAY_TEAM" else None)
        out.append({"stage": m["stage"], "home": m["home"]["tla"],
                    "away": m["away"]["tla"], "winner": winner})
    return out


def _sim_elo_map(teams: dict, finished: tuple) -> tuple[dict, dict | None]:
    """One strength source for the tournament MC, consistent with predict():
    the ML pipeline's online-updated Elo when available (else live ratings),
    PLUS the seeding/squad prior delta each team gets in per-match predict.
    Venue/context can't be applied to simulated future fixtures (knockout
    venues depend on the simulated bracket; context depends on simulated
    standings) — the per-match engine layers those on top at view time."""
    from .engine import strength_prior
    ml_elo = ml_ensemble.elo_by_tla(finished)
    if ml_elo and all(t in ml_elo for t in teams):
        elo_map, goal_coefs = dict(ml_elo), ml_ensemble._artifacts()["rates"]
    else:
        elo_map, goal_coefs = {t: v["elo"] for t, v in teams.items()}, None
    for t, v in teams.items():
        # delta computed exactly as predict() does (live elo + played decay),
        # transferred additively (both systems share the Elo points scale)
        elo_map[t] = elo_map[t] + strength_prior.pot_shrink_delta(
            t, v["elo"], v.get("played", 0))
    return elo_map, goal_coefs


async def run_simulation(runs: int | None = None, force: bool = False) -> dict:
    runs = runs or settings.n_sims_tournament
    teams = await get_teams()
    matches = await get_matches()
    key = f"sim:{_fingerprint(matches, runs)}"
    if not force:
        hit = cache.get(key, ttl=12 * 3600)
        if hit is not None:
            return hit

    groups: dict[str, list[str]] = {}
    for tla, t in teams.items():
        groups.setdefault(t["group"], []).append(tla)
    for g in groups:
        groups[g].sort(key=lambda t: teams[t]["position"])

    # One strength source shared with predict() (ML elo or live + prior deltas)
    finished = _finished_tuple(matches)
    elo_map, goal_coefs = _sim_elo_map(teams, finished)

    t0 = time.time()
    result = tournament.simulate(
        n=runs,
        elo_by_tla=elo_map,
        groups=groups,
        group_matches=[m for m in matches if m["stage"] == "GROUP_STAGE"],
        real_ko=_real_ko(matches),
        goal_coefs=goal_coefs,
    )
    result["ml"] = goal_coefs is not None
    result["elapsed_s"] = round(time.time() - t0, 2)
    result["computed_at"] = datetime.now(timezone.utc).isoformat()
    result["fingerprint"] = key.split(":", 1)[1][:12]
    cache.put(key, result)
    cache.put("sim:latest_key", key)
    return result


async def simulate_what_if(home: str, away: str, gh: int, ga: int,
                           runs: int = 20_000) -> dict:
    """Hypothetical-scenario sim: force one fixture's result and re-run the
    tournament; returns probability deltas vs the current simulation.
    Compute-only — never touches the cached main simulation."""
    teams = await get_teams()
    matches = await get_matches()
    fixture = next((m for m in matches
                    if {m["home"]["tla"], m["away"]["tla"]} == {home, away}
                    and m["stage"] == "GROUP_STAGE"), None)
    if fixture is None:
        raise ValueError(f"no group fixture {home} vs {away}")

    forced = []
    for m in matches:
        if m["id"] == fixture["id"]:
            m = {**m, "status": "FINISHED"}
            flip = m["home"]["tla"] != home
            m["score"] = {**m["score"],
                          "home": ga if flip else gh, "away": gh if flip else ga}
        forced.append(m)

    groups: dict[str, list[str]] = {}
    for tla, t in teams.items():
        groups.setdefault(t["group"], []).append(tla)
    for g in groups:
        groups[g].sort(key=lambda t: teams[t]["position"])

    finished = _finished_tuple(matches)
    elo_map, goal_coefs = _sim_elo_map(teams, finished)

    hypo = tournament.simulate(
        n=runs, elo_by_tla=elo_map, groups=groups,
        group_matches=[m for m in forced if m["stage"] == "GROUP_STAGE"],
        real_ko=_real_ko(forced), goal_coefs=goal_coefs)

    base = await latest_simulation() or await run_simulation()
    out = {"scenario": f"{home} {gh}-{ga} {away}", "runs": runs, "deltas": {}}
    movers = []
    for t, hv in hypo["teams"].items():
        bv = base["teams"].get(t, {})
        d_champ = round(hv["champion"] - bv.get("champion", 0), 4)
        d_r32 = round(hv["r32"] - bv.get("r32", 0), 4)
        if t in (home, away) or abs(d_champ) > 0.005 or abs(d_r32) > 0.02:
            movers.append({"tla": t, "champion": hv["champion"], "d_champion": d_champ,
                           "advance_r32": hv["r32"], "d_r32": d_r32})
    movers.sort(key=lambda x: -(abs(x["d_r32"]) + abs(x["d_champion"])))
    out["deltas"] = movers[:8]
    return out


async def latest_simulation() -> dict | None:
    key = cache.get("sim:latest_key", ttl=7 * 86_400)
    if key:
        hit, _ = cache.get_stale(key)
        if hit:
            return hit
    return None


async def predict(home: str, away: str, minute: int | None = None,
                  hg: int = 0, ag: int = 0) -> dict:
    from .static_data import canon_tla
    home, away = canon_tla(home), canon_tla(away)   # tolerate feed TLA variants
    # independent data sources fetched CONCURRENTLY (each is internally cached;
    # the gather collapses the cold-path serial waits — odds API ~1.2s, matches,
    # standings — into one round-trip instead of summing them).
    teams, matches, market_res, board_res = await asyncio.gather(
        get_teams(), get_matches(), odds_client.market_probs(), odds_client.board())
    if home not in teams or away not in teams:
        raise ValueError(f"Unknown team TLA: {home if home not in teams else away}")
    market_map, _ = market_res
    board_events, _ = board_res

    # fixture context between the two teams: live state, HT score, corners, stage
    fixture = next((m for m in matches
                    if {m["home"]["tla"], m["away"]["tla"]} == {home, away}), None)
    ht_h = ht_a = None
    corners_now = None
    stage = fixture["stage"] if fixture else None
    if fixture:
        flipped = fixture["home"]["tla"] != home

        def _orient(d):
            if not d or d.get("home") is None:
                return None
            return {"home": d["away"], "away": d["home"]} if flipped else d

        if minute is None and fixture["status"] in LIVE_STATUSES:
            minute = fixture["minute_estimate"] or 0
            sc = _orient(fixture["score"])
            if sc:
                hg, ag = sc["home"] or 0, sc["away"] or 0
        ht = _orient(fixture.get("ht_score"))
        if ht:
            ht_h, ht_a = ht["home"], ht["away"]
        corners_now = _orient(fixture.get("corners"))

    market = None
    entry = market_map.get(frozenset({home, away}))
    if entry:
        p = entry["probs"]
        market = p if entry["home_tla"] == home else \
            {"home": p["away"], "draw": p["draw"], "away": p["home"]}

    # league avg goals per team per game from current tournament
    played_total = sum(t["played"] for t in teams.values())
    gf_total = sum(t["gf"] for t in teams.values())
    lg_avg = (gf_total / played_total) if played_total else 0.0

    def _form(t):
        f = teams[t].get("form")
        return list(reversed(f.split(","))) if f else None

    # key-player absence penalty (only when an XI is announced) + red cards
    from . import team_profiles
    lu = (fixture or {}).get("lineups") or {}
    pen_h, kp_h = team_profiles.absence_penalty(home, (lu.get("home") or {}).get("players"))
    pen_a, kp_a = team_profiles.absence_penalty(away, (lu.get("away") or {}).get("players"))
    # pot-tier prior: bounded Elo shrink toward the official draw-pot baseline,
    # fading as the team plays — one delta folded into BOTH the ML path
    # (elo_adjust) and the heuristic path (elo_h/elo_a) for consistency.
    from .engine import strength_prior
    seed_d_h = strength_prior.pot_shrink_delta(home, teams[home]["elo"], teams[home]["played"])
    seed_d_a = strength_prior.pot_shrink_delta(away, teams[away]["elo"], teams[away]["played"])
    # style-matchup W/D/L nudge (Elo-equivalent; counter-vs-possession,
    # press-vs-buildup, possession-mirror draw tilt) — bounded & audited
    from .engine import style_adjust as _sa
    sup = _sa.supremacy_elo_delta(
        home, away,
        teams[home]["elo"] - pen_h + seed_d_h,
        teams[away]["elo"] - pen_a + seed_d_a)
    elo_adjust = (-pen_h + seed_d_h + sup["home"],
                  -pen_a + seed_d_a + sup["away"])
    rc = (fixture or {}).get("red_cards") or {}
    red_cards = (rc.get("home", 0), rc.get("away", 0))

    finished = _finished_tuple(matches)
    ml_probs = ml_ensemble.predict_wdl(home, away, finished, elo_adjust=elo_adjust)
    lam_override = ml_ensemble.goal_lambdas(home, away, finished, elo_adjust=elo_adjust)
    from .engine import style_adjust, context as ctx_engine, venue as venue_engine
    from .static_data import MATCH_SCHEDULE
    sf, sf_reason = style_adjust.total_goals_factor(home, away)
    # venue conditions (altitude / heat) — total-goals λ multiplier
    v_str = (fixture or {}).get("venue")
    v_city = None
    if fixture and fixture.get("id") in MATCH_SCHEDULE:
        v_city = MATCH_SCHEDULE[fixture["id"]][1]
    # real kickoff forecast (Open-Meteo) — None falls back to the static table
    from .clients import weather as weather_client
    from .venue_data import resolve_venue
    _v_prof = resolve_venue(v_str, v_city)
    wx = await weather_client.kickoff_conditions(
        _v_prof["city"] if _v_prof else None, (fixture or {}).get("utcDate"))
    ven = venue_engine.conditions_factor(
        v_str, (fixture or {}).get("utcDate"), v_city, weather=wx)
    sim_cache = await latest_simulation()
    ctx = ctx_engine.match_context(
        home, away, stage, fixture.get("group") if fixture else None,
        teams, matches, sim_cache,
        match_model.effective_elo(home, teams[home]["elo"] + seed_d_h),
        match_model.effective_elo(away, teams[away]["elo"] + seed_d_a))

    pred = match_model.predict_match(
        home_tla=home, away_tla=away,
        elo_h=teams[home]["elo"] - pen_h + seed_d_h + sup["home"],
        elo_a=teams[away]["elo"] - pen_a + seed_d_a + sup["away"],
        home_stats=teams[home], away_stats=teams[away],
        lg_avg_per_team=lg_avg,
        market=market,
        form_h=_form(home), form_a=_form(away),
        minute=minute, goals_h=hg, goals_a=ag,
        ml_probs=ml_probs, lam_override=lam_override,
        red_cards=red_cards,
        stage=stage, rho=ml_ensemble.dc_rho(),
        style_factor=sf,
        context_factor=ctx["factor"] * ven["factor"],  # venue folded into λ
        draw_bump=ctx.get("draw_bump", 0.0) + sup.get("draw_bump", 0.0),
    )
    if pen_h or pen_a:
        pred["absence_penalty"] = {"home": {"elo": -pen_h, "players": kp_h},
                                   "away": {"elo": -pen_a, "players": kp_a}}

    # ---- trained O/U & BTTS heads blended with the (tau) matrix values ----
    if minute is None:           # pre-match only; in-play stays score-conditioned
        mk = ml_ensemble.predict_markets(home, away, finished, elo_adjust=elo_adjust)
        if mk:
            # head is isotonic-calibrated (holdout O/U bias +0.4pp) while the
            # Poisson matrix over-predicts Over ~+8.5pp -> lean hard on the head
            # (Lever 1, measured: removes the residual +2pp blend bias).
            w_o = settings.ou_head_weight
            w_b = settings.btts_head_weight
            pred["over25"] = round(w_o * mk["over25"] + (1 - w_o) * pred["over25"], 4)
            pred["btts"] = round(w_b * mk["btts"] + (1 - w_b) * pred["btts"], 4)
            pred["components"]["markets_head"] = {
                "over25": round(mk["over25"], 4), "btts": round(mk["btts"], 4)}

    # ---- reconcile scorelines with the headline marginals (consistency) ----
    # Tilt the score matrix to match the final W/D/L + Over2.5 + BTTS so the
    # scoreline list can't contradict the percentages shown above.
    if minute is None:
        # Lever 2: the Poisson total over-inflates in mismatches (convexity) ->
        # a fitted total-goals scale calibrates the Asian-line shape across ALL
        # lines (holdout: main O/U lines within ±0.5pp at 0.94). The displayed
        # xG (lambdas) is unchanged; only the reconciled O/U/scoreline matrix
        # uses the calibrated total. Marginals still pinned by reconcile.
        s = settings.ou_total_scale
        lh0, la0 = pred["lambdas"]["home"] * s, pred["lambdas"]["away"] * s
        m_rec = match_model.reconcile_matrix(
            match_model.score_matrix(lh0, la0, rho=ml_ensemble.dc_rho()),
            pred["probs"], pred["over25"], pred["btts"])
        pred["scorelines"] = match_model.top_scorelines(m_rec)
        pred["_recon_matrix"] = m_rec    # reused for consistent market lines

    pred["components"]["style"] = {
        "total_factor": sf, "reason": sf_reason,
        "supremacy": {k: sup[k] for k in ("home", "away", "draw_bump")}
        if sup.get("reason") else None,
        "supremacy_reason": sup.get("reason"),
    }
    pred["components"]["context"] = {
        "factor": round(ctx["factor"], 3),
        "stakes": ctx.get("stakes"), "seeding": ctx.get("seeding"),
        "lockdown_underdog": ctx.get("lockdown_underdog"),
        "notes": ctx.get("notes", []) + ven.get("notes", []),
    }
    pred["components"]["venue"] = {"factor": ven["factor"], "venue": ven["venue"],
                                   "weather": ven.get("weather")}
    # real-fixture status so the UI can label market absence correctly
    # (bookmakers pull prices at kickoff; hypothetical pairs never have any)
    pred["fixture_status"] = fixture["status"] if fixture else None
    from .static_data import pot_of, group_difficulty
    pred["components"]["seed"] = {
        "home_pot": pot_of(home), "away_pot": pot_of(away),
        "prior_delta": {"home": seed_d_h, "away": seed_d_a},
        "group_difficulty": {"home": group_difficulty(home),
                             "away": group_difficulty(away)},
    }

    # ---- period-level extensions ----
    lam_h, lam_a = pred["lambdas"]["home"], pred["lambdas"]["away"]
    eh, ea = pred["elo"]["home"], pred["elo"]["away"]
    pred["halves"] = periods.halves(lam_h, lam_a, minute=minute,
                                    goals_h=hg, goals_a=ag, ht_h=ht_h, ht_a=ht_a)
    c_total_factor, c_total_reason = style_adjust.corners_total_factor(home, away)
    pred["corners"] = periods.corners(
        lam_h, lam_a, eh, ea,
        team_rates=(corner_rates(home), corner_rates(away)),
        minute=minute, corners_so_far=corners_now,
        score_diff=abs(hg - ag) if minute is not None else 0,
        share_bump=style_adjust.corners_share_bump(home, away),
        total_factor=c_total_factor,
        priors=(style_adjust.corner_prior(home), style_adjust.corner_prior(away)),
        base=adaptive_corners_base())
    if c_total_reason:
        pred["corners"]["style_total"] = {"factor": c_total_factor,
                                          "reason": c_total_reason}
    pred["stage"] = stage
    pred["is_knockout"] = bool(stage and stage != "GROUP_STAGE")
    pred["knockout"] = periods.knockout(lam_h, lam_a, eh, ea)

    # ---- Dixon-Robinson minute-by-minute scenario simulation ----
    # (validated equal to the matrix on W/D/L RPS, so headline stays from the
    # blend above; the sim adds the scenario timeline the matrix can't give)
    sim_style = style_adjust.sim_modifiers(home, away, eh, ea)
    if minute is None:
        sim = match_sim.simulate(lam_h, lam_a, n=settings.sim_runs,
                                  lam_cv=settings.sim_lambda_cv, style=sim_style)
    else:
        sim = match_sim.simulate(lam_h, lam_a, n=settings.sim_runs,
                                  start_min=minute, score=(hg, ag),
                                  reds=red_cards, style=sim_style)
    pred["simulation"] = {
        "probs": sim["probs"], "scorelines": sim["scorelines"],
        "exp_goals": sim["exp_goals"], "scenarios": sim["scenarios"],
        "from": sim["from"], "runs": sim["n"],
    }
    # pre-match volatility: P(final W/D/L class != half-time class) from the
    # minute sim. High-volatility fixtures (typically ~0.35 lopsided .. 0.43
    # coin-flip) deserve a softer read of the headline pick — surfaced in the
    # UI/chatbot and calibration-graded by the pipeline sim-timing scorecard.
    flip = sim["scenarios"].get("ht_flip")
    if minute is None and flip is not None:
        pred["volatility"] = {
            "ht_flip": flip,
            "level": ("high" if flip >= 0.42 else
                      "medium" if flip >= 0.38 else "low"),
        }

    # ---- Asian-line O/U: model % at the MARKET's actual lines ------------
    goals_line, goals_prices, corners_line, corners_prices = 2.5, None, 9.5, None
    try:
        ev = next((e for e in board_events
                   if {e["home_tla"], e["away_tla"]} == {home, away}), None)
        if ev:
            if ev.get("totals") and ev["totals"].get("point") is not None:
                goals_line = float(ev["totals"]["point"])
                goals_prices = {"over": ev["totals"].get("over"),
                                "under": ev["totals"].get("under")}
            extras = odds_client.cached_extras(ev["id"]) if ev.get("id") else None
            ct = (extras or {}).get("corners_totals") or []
            if ct:
                # the line quoted closest to even money
                best = min(ct, key=lambda c: abs((c.get("over") or 2) - (c.get("under") or 2)))
                corners_line = float(best["point"])
                corners_prices = {"over": best.get("over"), "under": best.get("under")}
    except Exception:
        pass

    # read goal O/U at any line from the SAME reconciled matrix (consistency)
    m_full = pred.pop("_recon_matrix", None)
    if m_full is None:
        m_full = match_model.score_matrix(lam_h, lam_a, rho=ml_ensemble.dc_rho())
    g_ou = match_model.prob_at_line(m_full, goals_line)
    if abs(goals_line - 2.5) < 1e-9:        # at 2.5 the trained head value is canonical
        g_ou = {"over": pred["over25"], "under": round(1 - pred["over25"], 4), "push": 0.0}
    c_mu = pred["corners"]["expected"]["total"]

    def _conf(p: float) -> str:
        """How decisive the O/U lean is — honest about coin-flip fixtures."""
        edge = abs(p - 0.5)
        return "toss_up" if edge < 0.06 else ("lean" if edge < 0.15 else "clear")

    goals_ou = {"line": goals_line, **g_ou, "market": goals_prices,
                "source": "market" if goals_prices else "default",
                "pick": "over" if g_ou["over"] >= 0.5 else "under",
                "confidence": _conf(g_ou["over"])}
    corners_ou = {"line": corners_line, **periods.corners_at_line(c_mu, corners_line),
                  "market": corners_prices,
                  "source": "market" if corners_prices else "default"}
    corners_ou["pick"] = "over" if corners_ou["over"] >= 0.5 else "under"
    corners_ou["confidence"] = _conf(corners_ou["over"])
    pred["market_lines"] = {"goals": goals_ou, "corners": corners_ou}
    return pred


def _fair(p: float | None) -> float | None:
    return round(1.0 / p, 2) if p and p > 0.01 else None


async def odds_board(limit: int = 24) -> dict:
    """Market odds (when key present) + model fair odds for upcoming matches."""
    teams = await get_teams()
    matches = await get_matches()
    finished = _finished_tuple(matches)
    upcoming = sorted(
        (m for m in matches
         if m["status"] in ("TIMED", "SCHEDULED") and m["home"]["tla"] and m["away"]["tla"]),
        key=lambda m: m["utcDate"])[:limit]

    market_events, source = await odds_client.board()
    by_pair = {frozenset({e["home_tla"], e["away_tla"]}): e for e in market_events}

    now = datetime.now(timezone.utc)
    extras_budget = 6
    rows = []
    for m in upcoming:
        h, a = m["home"]["tla"], m["away"]["tla"]
        ev = by_pair.get(frozenset({h, a}))
        flipped = bool(ev and ev["home_tla"] != h)

        # model fair odds
        probs = ml_ensemble.predict_wdl(h, a, finished)
        if probs is None:
            eh = match_model.effective_elo(h, teams[h]["elo"])
            ea = match_model.effective_elo(a, teams[a]["elo"])
            mtx = match_model.score_matrix(*match_model.lambdas_from_elo(eh, ea),
                                           rho=ml_ensemble.dc_rho())
            o = match_model.matrix_outcomes(mtx)
            probs = {k: o[k] for k in ("home", "draw", "away")}
        lam = ml_ensemble.goal_lambdas(h, a, finished)
        if lam is None:
            eh = match_model.effective_elo(h, teams[h]["elo"])
            ea = match_model.effective_elo(a, teams[a]["elo"])
            lam = match_model.lambdas_from_elo(eh, ea)
        o = match_model.matrix_outcomes(match_model.score_matrix(*lam, rho=ml_ensemble.dc_rho()))
        cor = periods.corners(
            lam[0], lam[1], teams[h]["elo"], teams[a]["elo"],
            team_rates=(corner_rates(h), corner_rates(a)),
            share_bump=style_adjust.corners_share_bump(h, a),
            total_factor=style_adjust.corners_total_factor(h, a)[0],
            priors=(style_adjust.corner_prior(h), style_adjust.corner_prior(a)),
            base=adaptive_corners_base())

        row = {
            "match_id": m["id"], "utcDate": m["utcDate"], "stage": m["stage"],
            "group": m["group"],
            "home": m["home"], "away": m["away"],
            "fair": {
                "h2h": {k: _fair(v) for k, v in probs.items()},
                "probs": {k: round(v, 4) for k, v in probs.items()},
                "over25": _fair(o["over25"]), "under25": _fair(1 - o["over25"]),
                "btts_yes": _fair(o["btts"]),
                "corners_over_95": _fair(cor["over"]["ft_9.5"]),
                "expected_corners": cor["expected"]["total"],
            },
            "market": None,
        }
        if ev:
            h2h = ev.get("h2h")
            if h2h and flipped:
                h2h = {"home": h2h["away"], "draw": h2h["draw"], "away": h2h["home"]}
            row["market"] = {"h2h": h2h, "totals": ev.get("totals"),
                             "spreads": ev.get("spreads"), "flipped": flipped}
            # value flags: model prob vs de-vig market prob
            if h2h and all(h2h.values()):
                mk = odds_client._devig(h2h["home"], h2h["draw"], h2h["away"])
                row["value"] = {k: round(probs[k] - mk[k], 4)
                                for k in ("home", "draw", "away")
                                if probs[k] - mk[k] > 0.03}
            kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            if extras_budget > 0 and (kickoff - now).total_seconds() < 36 * 3600:
                extras = await odds_client.event_extras(ev["id"])
                if extras:
                    row["market"].update(extras)
                extras_budget -= 1
        rows.append(row)

    return {"matches": rows, "source": source, "quota": odds_client.quota(),
            "ml": ml_ensemble.available()}


async def snapshot_live() -> int:
    """Record a win-prob timeline point for every live match (scheduler tick).
    Returns the number of snapshots written."""
    n = 0
    for m in await get_matches():
        if m["status"] not in LIVE_STATUSES:
            continue
        h, a = m["home"]["tla"], m["away"]["tla"]
        if not h or not a:
            continue
        try:
            pred = await predict(h, a)
        except Exception:
            continue
        key = f"timeline:{m['id']}"
        series, _ = cache.get_stale(key)
        series = series or []
        point = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "minute": pred.get("minute"),
            "score": pred.get("score"),
            "probs": pred["probs"],
        }
        # skip duplicate minute+score points to keep the series clean
        if not series or (series[-1]["minute"], series[-1]["score"]) != \
                (point["minute"], point["score"]):
            series.append(point)
            cache.put(key, series[-240:])
            n += 1
    return n


def timeline(match_id: int) -> list[dict]:
    series, _ = cache.get_stale(f"timeline:{match_id}")
    return series or []


async def analysis(home: str, away: str) -> dict:
    """Tactical analysis: curated profiles + live lineups + key-player
    availability + full squads. Style now FEEDS the prediction through three
    bounded, scorecard-audited channels (O/U factor, supremacy Elo nudge,
    sim state response), with tags confirmed/vetoed by observed tournament
    stats (engine/observed_style); absences/red cards remain Elo penalties."""
    from . import team_profiles
    from .engine import observed_style as _obs_style
    from .static_data import canon_tla
    home, away = canon_tla(home), canon_tla(away)   # tolerate feed TLA variants
    teams = await get_teams()
    if home not in teams or away not in teams:
        raise ValueError("unknown team")
    matches = await get_matches()
    fixture = next((m for m in matches
                    if {m["home"]["tla"], m["away"]["tla"]} == {home, away}), None)
    lu = (fixture or {}).get("lineups") or {}
    flipped = bool(fixture and fixture["home"]["tla"] != home)
    lu_h = lu.get("away" if flipped else "home")
    lu_a = lu.get("home" if flipped else "away")

    out = {}
    for tla, lu_side in ((home, lu_h), (away, lu_a)):
        prof = dict(team_profiles.PROFILES.get(tla, {}))
        pen, kps = team_profiles.absence_penalty(tla, (lu_side or {}).get("players"))
        try:
            squad = await fd.team_squad(teams[tla]["id"])
        except Exception:
            squad = []
        from .engine.style_adjust import MANAGER_NOTES
        out[tla] = {
            "profile": prof,
            "manager_note": MANAGER_NOTES.get(tla),
            "observed_style": _obs_style.observed(tla),
            "effective_style": sorted(_obs_style.effective_tags(tla)[0]),
            "lineup": lu_side,                       # None until announced
            "formation_live": (lu_side or {}).get("formation"),
            "key_players": kps,
            "absence_elo_penalty": -pen,
            "squad": squad,
            "elo": teams[tla]["elo"], "fifa_rank": teams[tla]["fifa_rank"],
        }
    return {"home": home, "away": away, "teams": out,
            "lineups_announced": bool(lu_h or lu_a),
            "stage": (fixture or {}).get("stage")}


async def sources_status() -> dict:
    out = {}
    try:
        ms = await get_matches()
        out["football_data"] = {
            "ok": True, "matches": len(ms),
            "finished": sum(m["status"] == "FINISHED" for m in ms),
            "live": sum(m["status"] in LIVE_STATUSES for m in ms),
            "cache_age_s": cache.age("fd:/competitions/WC/matches:None"),
        }
    except Exception as e:
        out["football_data"] = {"ok": False, "error": str(e)}
    _, elo_source = await elo_client.ratings()
    out["elo"] = {"ok": True, "source": elo_source}
    _, odds_source = await odds_client.market_probs()
    out["odds"] = {"ok": odds_source in ("live", "stale"), "source": odds_source}
    out["fifa_ranking"] = {"ok": True, "source": "static snapshot (Dec 2025)"}
    out["livescore"] = await livescore.status()
    rep = ml_ensemble.report()
    out["ml_ensemble"] = (
        {"ok": True, "test_rps": rep["test_metrics"]["ENSEMBLE"]["rps"],
         "vs_heuristic_rps": rep["test_metrics"]["heuristic (current)"]["rps"],
         "weights": rep["weights"]}
        if rep else {"ok": False, "source": "artifacts missing — run: python -m ml.train"}
    )
    return out
