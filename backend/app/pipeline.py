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
from .config import settings
from .engine import match_model, meta_weights, ml_ensemble


def _over25(m) -> float:
    import numpy as np
    hi, ai = np.indices(m.shape)
    return float(m[hi + ai > 2].sum())


def _factor_counterfactuals(pred: dict) -> dict:
    """Per-factor counterfactual predictions, computed AT SNAPSHOT TIME so the
    scorecard can later grade each factor against the actual result without
    hindsight re-prediction. Total-goals factors (style/context/venue) are
    measured on the O/U channel (divide the multiplier back out of lambda);
    the seeding prior is measured on the W/D/L channel via the fitted goal
    rates (lambda' = lambda * exp(-/+ b*(dh-da)/100)). Each counterfactual is
    model-channel-only (pre market/heads blend) — an isolated, fair A/B."""
    comp = pred.get("components") or {}
    lam = pred.get("lambdas") or {}
    lh, la = lam.get("home"), lam.get("away")
    if not lh or not la:
        return {}
    rho = ml_ensemble.dc_rho()
    m_with = match_model.score_matrix(lh, la, rho=rho)
    ov_with = round(_over25(m_with), 4)
    out = {}
    for name, f in (("style", (comp.get("style") or {}).get("total_factor")),
                    ("context", (comp.get("context") or {}).get("factor")),
                    ("venue", (comp.get("venue") or {}).get("factor"))):
        if f and abs(f - 1.0) > 1e-3:
            m_cf = match_model.score_matrix(lh / f, la / f, rho=rho)
            out[name] = {"factor": f, "over25_with": ov_with,
                         "over25_without": round(_over25(m_cf), 4)}
    arts = ml_ensemble._artifacts()

    def _sup_cf(dh: float, da: float) -> dict | None:
        """Counterfactual W/D/L removing an Elo-equivalent (dh, da) nudge."""
        if not (arts and arts.get("rates") and (dh or da)):
            return None
        shift = arts["rates"]["b"] * (dh - da) / 100.0
        m_cf = match_model.score_matrix(lh * math.exp(-shift),
                                        la * math.exp(shift), rho=rho)
        return {"delta": {"home": dh, "away": da},
                "probs_with": match_model.matrix_outcomes(m_with),
                "probs_without": match_model.matrix_outcomes(m_cf)}

    seed = comp.get("seed") or {}
    pd_ = seed.get("prior_delta") or {}
    cf = _sup_cf(pd_.get("home", 0.0), pd_.get("away", 0.0))
    if cf:
        out["prior"] = cf
    xf = seed.get("xg_form_delta") or {}
    cf = _sup_cf(xf.get("home", 0.0), xf.get("away", 0.0))
    if cf:
        out["xg_form"] = cf
    sf = seed.get("shot_form_delta") or {}
    cf = _sup_cf(sf.get("home", 0.0), sf.get("away", 0.0))
    if cf:
        out["shot_form"] = cf
    sup = (comp.get("style") or {}).get("supremacy") or {}
    cf = _sup_cf(sup.get("home", 0.0), sup.get("away", 0.0))
    if cf:
        cf["reason"] = (comp.get("style") or {}).get("supremacy_reason")
        out["style_sup"] = cf
    return out

PREMATCH_WINDOW_H = 12       # keep a provisional snapshot once kickoff is within 12h
LOCK_LEAD_MIN = 90           # eligible to LOCK from 90 min out (official XIs post this early)
LOCK_DEADLINE_MIN = 20       # but lock no later than 20 min before KO even if no XI posted


async def record_prematch(matches: list[dict] | None = None) -> int:
    """Persist pre-kickoff predictions (scheduler calls this every tick).

    A provisional snapshot is taken when kickoff first comes within 12h, but the
    GRADED prediction is re-run and LOCKED the moment the OFFICIAL line-up is out
    (LiveScore posts the confirmed XI ~1h before KO). Locking on the real XI means
    the verdict already reflects who actually starts — injuries/suspensions/rotation
    are absorbed via the absence penalty — instead of the 12h-out guess. If no XI
    ever posts, a 20-min safety deadline locks the best available call. Once locked
    it is never overwritten; `lineup_aware` records whether the lock saw the XI."""
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
        if existing and existing.get("locked"):
            continue                              # frozen — never re-touched
        lineups_confirmed = bool(m.get("lineups"))
        # LOCK the moment the official XI is out (inside the 90-min window); if it
        # never posts, lock by the 20-min safety deadline.
        should_lock = until <= LOCK_LEAD_MIN * 60 and (
            lineups_confirmed or until <= LOCK_DEADLINE_MIN * 60)
        if existing and not should_lock:
            continue                              # hold provisional; wait for the official XI
        try:
            pred = await service.predict(h, a)    # fresh: official XI + settled odds at lock
        except Exception:
            continue
        comp = pred.get("components") or {}
        cache.put(key, {
            "probs": pred["probs"],
            "lambdas": pred["lambdas"],
            "top_score": pred["scorelines"][0] if pred["scorelines"] else None,
            "over25": pred.get("over25"),
            "btts": pred.get("btts"),
            "corners_expected": (pred.get("corners") or {}).get("expected"),
            "market_lines": pred.get("market_lines"),
            "absence": pred.get("absence_penalty"),
            "lineup_aware": lineups_confirmed,
            "locked": should_lock,                # locked on the official XI (or deadline)
            # factor scorecard + meta-calibration inputs (graded post-match):
            "factors": _factor_counterfactuals(pred),
            "scenarios": (pred.get("simulation") or {}).get("scenarios"),
            "components": {k: comp.get(k) for k in ("ml", "market", "poisson")
                           if comp.get(k)},
            "weights": comp.get("weights"),
            "ts": now.isoformat(timespec="seconds"),
        })
        n += 1
    return n


def _corners_ou_verdict(pm: dict | None, c_exp: float | None,
                        c_total: int | None, corners: dict | None) -> dict:
    """Grade corners as Over/Under at the line — the model's pick (Tài/Xỉu)
    vs what actually happened, which is checkable, unlike 'expected ~10.04'."""
    ml_c = ((pm or {}).get("market_lines") or {}).get("corners")
    if ml_c and ml_c.get("over") is not None:
        line, p_over = float(ml_c["line"]), float(ml_c["over"])
        src = ml_c.get("source", "market")
    elif c_exp is not None:
        # old snapshots: derive at default 9.5 from the stored expectation
        from .engine.periods import corners_at_line
        line, src = 9.5, "default"
        p_over = corners_at_line(float(c_exp), line)["over"]
    else:
        return {"pred": c_exp, "actual": c_total, "detail": corners}
    pick = "over" if p_over >= 0.5 else "under"
    out = {"line": line, "p_over": round(p_over, 4), "pick": pick,
           "expected_total": c_exp, "actual_total": c_total,
           "detail": corners, "line_source": src}
    if c_total is not None:
        actual = "over" if c_total > line else ("push" if c_total == line else "under")
        out["actual"] = actual
        out["hit"] = (actual == "push") or (pick == actual)
    return out


def _goals_ou_verdict(pm: dict | None, total_goals: int | None) -> dict:
    """Grade total-goals Over/Under at the MARKET's Asian line (e.g. 2.75), not a
    fixed 2.5 — the model's Tài/Xỉu pick vs the actual total. Falls back to the
    trained 2.5 head only when no market goals line was captured pre-match."""
    ml_g = ((pm or {}).get("market_lines") or {}).get("goals")
    if ml_g and ml_g.get("over") is not None:
        line, p_over = float(ml_g["line"]), float(ml_g["over"])
        src = ml_g.get("source", "market")
    else:                                   # old/snapshot-less: trained 2.5 head
        p25 = (pm or {}).get("over25")
        if p25 is None:
            return {"pred_p": None, "actual": (total_goals or 0) > 2}
        line, p_over, src = 2.5, float(p25), "default"
    pick = "over" if p_over >= 0.5 else "under"
    out = {"line": line, "p_over": round(p_over, 4), "pick": pick, "line_source": src}
    if total_goals is not None:
        actual = "over" if total_goals > line else ("push" if total_goals == line else "under")
        out["actual_total"] = total_goals
        out["actual"] = actual
        out["hit"] = (actual == "push") or (pick == actual)
    return out


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


async def review(limit: int = 104, light: bool = False) -> dict:    # default: whole tournament
    # light=True (public /evaluate/tournament): skip the per-match elo_shift
    # (O(n²) Elo recompute) + h2h/narrative/improve, none of which the public
    # endpoint returns — cuts the call from ~1.3s to ~0.2s.
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
        cp = 0.0
        rps = 0.0
        for k in order[:2]:
            cp += probs[k]
            co = 1.0 if order.index(actual) <= order.index(k) else 0.0
            rps += (cp - co) ** 2
        rps_sum += rps / 2
        ll_sum += -math.log(max(p_actual, 1e-12))

        # Elo shift the online update applied for this match
        entry = (h, a, gh, ga)
        idx = all_t.index(entry) if entry in all_t else None
        elo_shift = None
        if idx is not None and not light:
            before = ml_ensemble.elo_by_tla(all_t[:idx]) or {}
            after = ml_ensemble.elo_by_tla(all_t[:idx + 1]) or {}
            if h in before and h in after and a in before and a in after:
                elo_shift = {"home": round(after[h] - before[h], 1),
                             "away": round(after[a] - before[a], 1)}

        # ---- predicted vs actual factor comparison + cause analysis ----
        log_e, _ = cache.get_stale(f"matchlog:{m['id']}")
        log_e = log_e or {}
        corners = m.get("corners") or log_e.get("corners")
        c_total = (corners["home"] + corners["away"]) \
            if corners and corners.get("home") is not None else None
        total_goals = gh + ga
        lam = (pm or {}).get("lambdas") or {}
        exp_goals = (lam.get("home", 0) + lam.get("away", 0)) or None
        top = (pm or {}).get("top_score")
        c_exp = ((pm or {}).get("corners_expected") or {}).get("total")
        stats = m.get("stats") or log_e.get("stats")

        compare = {
            "winner": {"pred": pick, "actual": actual, "hit": correct},
            "score": {"pred": f"{top['home']}-{top['away']}" if top else None,
                      "actual": f"{gh}-{ga}",
                      "hit": bool(top and top["home"] == gh and top["away"] == ga)},
            "total_goals": {"pred_xg": round(exp_goals, 2) if exp_goals else None,
                            "actual": total_goals},
            "over25": {"pred_p": (pm or {}).get("over25"),
                       "actual": total_goals > 2},
            "goals": _goals_ou_verdict(pm, total_goals),
            "btts": {"pred_p": (pm or {}).get("btts"),
                     "actual": gh > 0 and ga > 0},
            "corners": _corners_ou_verdict(pm, c_exp, c_total, corners),
        }

        ht = m.get("ht_score") or log_e.get("ht_score")
        notes, improve = [], None
        if not light:        # narrative + h2h skipped on the fast public path
            if compare["score"]["hit"]:
                notes.append({"key": "n_exact_score", "params": {}})
            elif correct:
                notes.append({"key": "n_winner_hit", "params": {"p": round(probs[pick], 2)}})
            else:
                notes.append({"key": "n_winner_miss",
                              "params": {"pred": pick, "p_actual": round(p_actual, 2)}})
            if exp_goals is not None and abs(total_goals - exp_goals) >= 1.5:
                notes.append({"key": "n_goals_off",
                              "params": {"xg": round(exp_goals, 1), "actual": total_goals}})
            if c_exp is not None and c_total is not None and abs(c_total - c_exp) >= 4:
                notes.append({"key": "n_corners_off",
                              "params": {"pred": round(c_exp, 1), "actual": c_total}})
            if (pm or {}).get("absence"):
                notes.append({"key": "n_absence", "params": {}})
            rc = m.get("red_cards") or {}
            if (rc.get("home") or 0) + (rc.get("away") or 0) > 0 or \
                    ((stats or {}).get("reds") and ((stats["reds"].get("home") or 0)
                                                    + (stats["reds"].get("away") or 0)) > 0):
                notes.append({"key": "n_red_cards", "params": {}})
            if ht and ht.get("home") is not None and (
                    ("home" if ht["home"] > ht["away"] else
                     "draw" if ht["home"] == ht["away"] else "away") != actual):
                notes.append({"key": "n_ht_swing", "params": {}})

            # ---- match-specific narrative: history + style + manager + context ----
            from .engine.style_adjust import MANAGER_NOTES, _tags
            try:
                hh = evaluation.h2h(h, a, n=6)
                if hh.get("summary"):
                    notes.append({"key": "n_h2h", "params": {
                        "c": hh["summary"]["correct"], "n": hh["summary"]["n"]}})
            except Exception:
                pass
            th, ta = _tags(h), _tags(a)
            if th and ta:
                both_def = bool(th & {"low_block", "counter"}) and bool(ta & {"low_block", "counter"})
                if both_def and total_goals >= 3:
                    notes.append({"key": "n_style_open_surprise", "params": {}})
                elif both_def:
                    notes.append({"key": "n_style_cagey", "params": {}})
            mgr = [MANAGER_NOTES[t] for t in (h, a) if t in MANAGER_NOTES]
            if mgr:
                notes.append({"key": "n_manager", "params": {"note": " · ".join(mgr)}})

            # ---- improvement suggestion keyed to the dominant miss ----
            if not correct and m["stage"] == "GROUP_STAGE":
                improve = "imp_motivation" if p_actual < 0.3 else "imp_winner"
            elif exp_goals is not None and abs(total_goals - exp_goals) >= 2:
                improve = "imp_goals"
            elif c_exp is not None and c_total is not None and abs(c_total - c_exp) >= 4:
                improve = "imp_corners"
            elif not correct:
                improve = "imp_winner"

        rows.append({
            "match_id": m["id"], "date": m["utcDate"], "stage": m["stage"],
            "home": m["home"], "away": m["away"],
            "score": {"home": gh, "away": ga}, "ht_score": ht,
            "probs": {k: round(v, 4) for k, v in probs.items()},
            "probs_source": src,
            "prematch_ts": (pm or {}).get("ts"),   # when the pre-match snapshot was locked
            "lineup_aware": (pm or {}).get("lineup_aware"),  # locked with the official XI?
            "predicted": pick, "actual": actual, "correct": correct,
            "p_actual": round(p_actual, 4),
            "tag": _surprise_tag(correct, p_actual, probs[pick]),
            "factors": {
                "red_cards": m.get("red_cards"),
                "corners": corners,
                "ht_swing": any(x["key"] == "n_ht_swing" for x in notes),
                "absence": (pm or {}).get("absence"),
                "lineup_aware": (pm or {}).get("lineup_aware"),
            },
            "compare": compare,
            "notes": notes,
            "improve": improve,
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


def _rps(probs: dict, actual: str) -> float:
    order = ("home", "draw", "away")
    cp = rps = 0.0
    for k in order[:2]:
        cp += probs.get(k, 0.0)
        rps += (cp - (1.0 if order.index(actual) <= order.index(k) else 0.0)) ** 2
    return rps / 2


def factor_scorecard(matches: list[dict]) -> dict:
    """Grade every bounded factor against actual results, using the
    counterfactuals captured pre-kickoff. with/without are model-channel
    Brier (O/U factors) or RPS (seeding prior) — lower is better, so
    delta < 0 means the factor IS helping. n counts only matches where the
    factor actually fired."""
    agg = {k: {"n": 0, "with": 0.0, "without": 0.0}
           for k in ("style", "context", "venue", "prior", "style_sup", "xg_form", "shot_form")}
    for m in matches:
        if m["status"] != "FINISHED" or m["score"]["home"] is None:
            continue
        pm, _ = cache.get_stale(f"prematch:{m['id']}")
        fac = (pm or {}).get("factors")
        if not fac:
            continue
        gh, ga = m["score"]["home"], m["score"]["away"]
        over = 1.0 if gh + ga > 2 else 0.0
        actual = "home" if gh > ga else ("draw" if gh == ga else "away")
        for k in ("style", "context", "venue"):
            f = fac.get(k)
            if f:
                agg[k]["n"] += 1
                agg[k]["with"] += (f["over25_with"] - over) ** 2
                agg[k]["without"] += (f["over25_without"] - over) ** 2
        for k in ("prior", "style_sup", "xg_form", "shot_form"):
            if fac.get(k):
                p = fac[k]
                agg[k]["n"] += 1
                agg[k]["with"] += _rps(p["probs_with"], actual)
                agg[k]["without"] += _rps(p["probs_without"], actual)
    out = {}
    for k, a in agg.items():
        n = a["n"]
        row = {"n": n, "metric": "rps" if k in ("prior", "style_sup", "xg_form", "shot_form") else "brier"}
        if n:
            w, wo = a["with"] / n, a["without"] / n
            row.update({"with": round(w, 4), "without": round(wo, 4),
                        "delta": round(w - wo, 4)})
            row["verdict"] = ("insufficient" if n < 5 else
                              "helping" if w < wo - 1e-4 else
                              "hurting" if w > wo + 1e-4 else "neutral")
        else:
            row["verdict"] = "no_data"
        out[k] = row
    return out


def sim_timing_scorecard(matches: list[dict]) -> dict:
    """Grade the minute-simulator's SCENARIO probabilities against what
    actually happened (goal minutes from the match-log incidents). This is
    where the style-conditioned simulation proves itself: late goals,
    comebacks and clean sheets are timing/state properties the closed-form
    matrix cannot express."""
    keys = ("ht_flip", "late_goal_80plus", "home_comeback",
            "clean_sheet_home", "clean_sheet_away")
    agg = {k: {"n": 0, "p_sum": 0.0, "hits": 0, "brier": 0.0} for k in keys}
    for m in matches:
        if m["status"] != "FINISHED" or m["score"]["home"] is None:
            continue
        pm, _ = cache.get_stale(f"prematch:{m['id']}")
        sc = (pm or {}).get("scenarios")
        if not sc:
            continue
        gh, ga = m["score"]["home"], m["score"]["away"]
        log_e, _ = cache.get_stale(f"matchlog:{m['id']}")
        inc = (log_e or {}).get("incidents") or m.get("incidents") or []
        goals = sorted((i for i in inc if i.get("type") == "goal"
                        and i.get("minute") is not None),
                       key=lambda i: i["minute"])
        # timing facts need the incident list to be complete
        timing_ok = len(goals) == gh + ga
        lead, led_away = 0, False
        for g in goals:
            lead += 1 if g.get("side") == "home" else -1
            led_away |= lead < 0
        ht = (log_e or {}).get("ht_score") or m.get("ht_score") or {}
        ht_known = ht.get("home") is not None
        _cls = lambda x, y: "h" if x > y else ("d" if x == y else "a")
        actuals = {
            "ht_flip": (_cls(ht["home"], ht["away"]) != _cls(gh, ga)
                        if ht_known else None),
            "late_goal_80plus": (any(g["minute"] >= 80 for g in goals)
                                 if timing_ok else None),
            "home_comeback": (led_away and gh > ga) if timing_ok else None,
            "clean_sheet_home": ga == 0,
            "clean_sheet_away": gh == 0,
        }
        for k in keys:
            p, actual = sc.get(k), actuals[k]
            if p is None or actual is None:
                continue
            a = agg[k]
            a["n"] += 1
            a["p_sum"] += p
            a["hits"] += int(actual)
            a["brier"] += (p - float(actual)) ** 2
    return {k: ({"n": a["n"],
                 "pred_mean": round(a["p_sum"] / a["n"], 3),
                 "actual_rate": round(a["hits"] / a["n"], 3),
                 "brier": round(a["brier"] / a["n"], 4)}
                if a["n"] else {"n": 0})
            for k, a in agg.items()}


def corners_scorecard(matches: list[dict]) -> dict:
    """Aggregate corners O/U calibration: pre-kickoff P(over) at the line vs
    the actual total. Brier + hit-rate + mean predicted/actual total, so the
    A/B effect of the corners enhancements (concede-rate, crosses, style) is
    measurable on real results — corners are noisy, this proves any gain."""
    n = hits = graded = 0
    brier = 0.0
    pred_tot = act_tot = tot_n = 0.0
    for m in matches:
        if m["status"] != "FINISHED" or m["score"]["home"] is None:
            continue
        pm, _ = cache.get_stale(f"prematch:{m['id']}")
        log_e, _ = cache.get_stale(f"matchlog:{m['id']}")
        corners = m.get("corners") or (log_e or {}).get("corners")
        c_total = (corners["home"] + corners["away"]) \
            if corners and corners.get("home") is not None else None
        if c_total is None:
            continue
        v = _corners_ou_verdict(pm, ((pm or {}).get("corners_expected") or {}).get("total"),
                                c_total, corners)
        if v.get("expected_total") is not None:
            tot_n += 1
            pred_tot += v["expected_total"]
            act_tot += c_total
        if v.get("p_over") is None or v.get("actual") == "push":
            continue
        n += 1
        over = 1.0 if c_total > v["line"] else 0.0
        brier += (v["p_over"] - over) ** 2
        hits += int(v.get("hit", False))
        graded += 1
    obs = service.observed_corner_mean()
    return {
        "n": n,
        "brier": round(brier / n, 4) if n else None,
        "hit_rate": round(hits / graded, 3) if graded else None,
        "pred_mean_total": round(pred_tot / tot_n, 2) if tot_n else None,
        "actual_mean_total": round(act_tot / tot_n, 2) if tot_n else None,
        # self-learning transparency: how the base has adapted to WC corners
        "club_base": settings.corners_base,
        "observed_mean": round(obs[0], 2) if obs else None,
        "adaptive_base": service.adaptive_corners_base(),
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
        "factor_scorecard": factor_scorecard(matches),
        "corners_scorecard": corners_scorecard(matches),
        "sim_timing": sim_timing_scorecard(matches),
        "meta_weights": meta_weights.recompute_if_stale(matches),
        "sources": await service.sources_status(),
    }
