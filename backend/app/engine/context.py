"""Match-context layer — the 'toan tính' (game-state calculation) tier.

Beyond raw team strength, teams behave differently depending on what's at
stake. Four scenario tiers, each producing a bounded lambda factor + a
human-readable note (i18n key), audited in-tournament via the pipeline:

  1. Group final-round STAKES — dead rubber (both settled) scores less;
     mutual-benefit results lower intensity. (NB: a blanket 'matchday-3'
     factor is wrong — WC 1998-2022 shows MD3 ~ MD1/2 in aggregate; only the
     per-team SETTLED scenario lowers goals.)
  2. Mutual-benefit (biscotto) — one result sends both through.
  3. Seeding incentive — a secured team may finish 2nd to dodge a stronger
     side in the next round (small nudge + narrative; teams often still try).
  4. Knockout — caution escalates by stage; a big underdog locks the game
     down to reach the ~⅓-chance penalty lottery.

All factors are bounded, env-tunable, and OFF when context_adjust_enabled
is false. Returns {factor, draw_bump, stakes, notes, ...} consumed by
service.predict and exposed in components.context.
"""
from itertools import product

from ..config import settings
from ..static_data import R32

GROUP_LETTERS = "ABCDEFGHIJKL"


def _result_points(gd: int) -> tuple[int, int]:
    return (3, 0) if gd > 0 else ((1, 1) if gd == 0 else (0, 3))


def _group_table(teams_in_group: list[dict]) -> dict[str, dict]:
    return {t["tla"]: {"pts": t["points"], "gd": t["gd"], "gf": t["gf"],
                       "played": t["played"]} for t in teams_in_group}


def _final_round_stakes(home: str, away: str, group_teams: list[dict],
                        remaining: list[dict]) -> dict | None:
    """Classify each team's stake before a final group game by enumerating
    the two simultaneous matches' outcomes (this game + the other pair).
    Only the top-2 (direct qualification) is treated as 'secured'; 3rd-place
    cross-group qualification is left as 'live'. Returns None if not a
    final-round group game (each side must have played 2 of 3)."""
    table = _group_table(group_teams)
    if home not in table or away not in table:
        return None
    if table[home]["played"] != 2 or table[away]["played"] != 2:
        return None
    others = [t for t in group_teams if t["tla"] not in (home, away)]
    if len(others) != 2:
        return None
    o1, o2 = others[0]["tla"], others[1]["tla"]

    # finishing positions of `team` across all 3x3 outcome combos
    def positions(team: str) -> set[int]:
        out = set()
        for (gd_this, gd_other) in product((1, 0, -1), repeat=2):
            pts = {k: v["pts"] for k, v in table.items()}
            ph, pa = _result_points(gd_this)
            pts[home] += ph
            pts[away] += pa
            po1, po2 = _result_points(gd_other)
            pts[o1] += po1
            pts[o2] += po2
            # rank by points (gd tiebreak approximated by current gd)
            order = sorted(table, key=lambda k: (pts[k], table[k]["gd"]), reverse=True)
            out.add(order.index(team) + 1)   # 1..4
        return out

    def classify(team: str, opp: str) -> str:
        pos = positions(team)
        if max(pos) <= 2:
            return "secured"           # top-2 in every scenario
        if min(pos) >= 3:
            # 3rd in every scenario — could still be a best-third, treat as live
            return "eliminated" if min(pos) == 4 else "live"
        # depends on result: must-win if only winning lifts to top-2
        win_pos = set()
        for gd_other in (1, 0, -1):
            pts = {k: v["pts"] for k, v in table.items()}
            ph, _ = _result_points(1)
            pts[team] += ph
            po1, po2 = _result_points(gd_other)
            pts[o1] += po1
            pts[o2] += po2
            order = sorted(table, key=lambda k: (pts[k], table[k]["gd"]), reverse=True)
            win_pos.add(order.index(team) + 1)
        return "must_win" if max(win_pos) <= 2 else "live"

    sh, sa = classify(home, away), classify(away, home)

    # mutual-benefit: does a draw keep BOTH out of the bottom (top-2)?
    draw_pts = {k: v["pts"] for k, v in table.items()}
    draw_pts[home] += 1
    draw_pts[away] += 1
    # true biscotto: a draw sends BOTH to top-2 regardless of the other match
    mutual = True
    for gd_other in (1, 0, -1):
        p = dict(draw_pts)
        po1, po2 = _result_points(gd_other)
        p[o1] += po1
        p[o2] += po2
        order = sorted(table, key=lambda k: (p[k], table[k]["gd"]), reverse=True)
        if not (order.index(home) + 1 <= 2 and order.index(away) + 1 <= 2):
            mutual = False
            break
    return {"home": sh, "away": sa, "mutual_benefit": mutual}


def group_context(home: str, away: str, group_letter: str,
                  teams: dict[str, dict], matches: list[dict]) -> dict:
    grp = [t for t in teams.values() if t["group"] == group_letter]
    stakes = _final_round_stakes(home, away, grp, matches)
    out = {"factor": 1.0, "draw_bump": 0.0, "notes": []}
    if not stakes:
        return out
    sh, sa = stakes["home"], stakes["away"]
    dead = {"secured", "eliminated"}
    out["stakes"] = {"home": sh, "away": sa}

    if sh in dead and sa in dead:
        out["factor"] = settings.context_dead_factor
        out["notes"].append({"key": "ctx_dead_rubber", "params": {}})
    elif sh in dead or sa in dead:
        out["factor"] = (1 + settings.context_dead_factor) / 2   # one side coasting
        out["notes"].append({"key": "ctx_one_dead",
                             "params": {"team": home if sh in dead else away}})
    elif sh == "must_win" and sa == "must_win":
        out["factor"] = settings.context_decider_factor
        out["notes"].append({"key": "ctx_decider", "params": {}})

    if stakes["mutual_benefit"]:
        out["factor"] = min(out["factor"], settings.context_dead_factor)
        out["draw_bump"] = 0.05
        out["notes"].append({"key": "ctx_mutual_benefit", "params": {}})
    return out


def seeding_incentive(secured_team: str, group_letter: str,
                      teams: dict[str, dict], sim: dict | None) -> dict | None:
    """For a team already secured in its final group game: would finishing
    2nd plausibly dodge a much stronger R32 opponent than finishing 1st?
    Uses bracket routing + each team's current Elo. Bounded + narrative."""
    if not sim:
        return None
    # R32 slot opponents for this group's winner vs runner-up
    win_slot = f"1{group_letter}"
    run_slot = f"2{group_letter}"
    elo = {t: v["elo"] for t, v in teams.items()}

    def opp_elo(slot: str) -> float | None:
        for _, (a, b) in R32.items():
            for own, other in ((a, b), (b, a)):
                if own == slot:
                    if other.startswith("3:"):
                        return None        # third-place slot: unknown opponent
                    rank, g = other[0], other[1]
                    cand = [t for t, v in teams.items() if v["group"] == g]
                    if not cand:
                        return None
                    cand.sort(key=lambda t: teams[t]["position"])
                    pick = cand[0] if rank == "1" else (cand[1] if len(cand) > 1 else cand[0])
                    return elo.get(pick)
        return None

    e_win, e_run = opp_elo(win_slot), opp_elo(run_slot)
    if e_win is None or e_run is None:
        return None
    # finishing 2nd is easier if the runner-up's opponent is much weaker
    if e_win - e_run >= settings.context_seeding_elo_gap:
        return {"prefer": "runner_up", "gap": round(e_win - e_run, 0)}
    return None


def knockout_context(home: str, away: str, stage: str,
                     elo_h: float, elo_a: float) -> dict:
    out = {"factor": settings.ko_stage_factors.get(stage, settings.ko_goal_factor),
           "draw_bump": 0.0, "notes": [], "lockdown_underdog": None}
    gap = abs(elo_h - elo_a)
    if gap >= settings.context_ko_underdog_gap:
        underdog = home if elo_h < elo_a else away
        out["factor"] *= settings.context_ko_lockdown_factor
        out["draw_bump"] = 0.04
        out["lockdown_underdog"] = underdog
        out["notes"].append({"key": "ctx_ko_lockdown",
                             "params": {"team": underdog,
                                        "pens_win": round(1 - settings.pens_elo_tilt, 2)}})
    else:
        out["notes"].append({"key": "ctx_ko_stage", "params": {"stage": stage}})
    return out


def match_context(home: str, away: str, stage: str | None, group: str | None,
                  teams: dict[str, dict], matches: list[dict],
                  sim: dict | None, elo_h: float, elo_a: float) -> dict:
    """Top-level: returns {factor, draw_bump, stakes?, seeding?, notes[]}."""
    base = {"factor": 1.0, "draw_bump": 0.0, "notes": []}
    if not settings.context_adjust_enabled:
        return base

    if stage and stage != "GROUP_STAGE":
        return knockout_context(home, away, stage, elo_h, elo_a)

    if group:
        letter = group[-1].upper()
        ctx = group_context(home, away, letter, teams, matches)
        # seeding incentive for whichever side is already secured
        for team in (home, away):
            st = (ctx.get("stakes") or {}).get("home" if team == home else "away")
            if st == "secured":
                seed = seeding_incentive(team, letter, teams, sim)
                if seed:
                    ctx["factor"] = min(ctx["factor"], settings.context_seeding_factor)
                    ctx["seeding"] = {"team": team, **seed}
                    ctx["notes"].append({"key": "ctx_seeding",
                                         "params": {"team": team}})
        return ctx
    return base
