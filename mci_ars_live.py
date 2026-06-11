"""
MCI vs ARS Live Prediction Model
Poisson + ELO + Form + Monte Carlo Simulation
Data: football-data.org (free tier)
"""

import math
import sys
import os
import time
from itertools import product

try:
    import requests
except ImportError:
    sys.exit("Run: pip install requests")

try:
    import numpy as np
except ImportError:
    sys.exit("Run: pip install numpy")

from prediction_utils import (
    HOME_ADVANTAGE_FACTOR, N_SIMS, RATE_LIMIT_DELAY, GAMMA_SHAPE,
    POISSON_BLEND, ELO_BLEND, FORM_IMPACT, MAX_GOALS, FORM_MAP,
    poisson_prob, form_score,
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
API_KEY  = os.environ.get("FOOTBALL_API_KEY", "YOUR_API_KEY_HERE")
BASE     = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}
TEAM_IDS = {"MCI": 65, "ARS": 57}
COMP     = "PL"

# ─────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────
def get(path, params=None):
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=10)
    if r.status_code == 403:
        sys.exit("ERROR: Invalid API key.")
    if r.status_code == 429:
        sys.exit("ERROR: Rate limit hit. Wait a minute and retry.")
    if r.status_code == 400:
        sys.exit(f"ERROR: Bad request — check query parameters ({path}).")
    if r.status_code in (500, 503):
        print(f"  Warning: server error {r.status_code}, retrying once ...")
        time.sleep(RATE_LIMIT_DELAY * 2)
        r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_live_match(home_id, away_id):
    data = get(f"/competitions/{COMP}/matches", {"status": "LIVE,IN_PLAY,PAUSED"})
    for m in data.get("matches", []):
        h, a = m["homeTeam"]["id"], m["awayTeam"]["id"]
        if {h, a} == {home_id, away_id}:
            return m
    return None

def fetch_standings():
    data = get(f"/competitions/{COMP}/standings")
    return {
        e["team"]["id"]: {
            "played": e["playedGames"], "won": e["won"],
            "drawn": e["draw"],         "lost": e["lost"],
            "goals_for": e["goalsFor"], "goals_against": e["goalsAgainst"],
        }
        for e in data["standings"][0]["table"]
    }

def fetch_form(team_id, n=5):
    data = get(f"/teams/{team_id}/matches",
               {"competitions": COMP, "status": "FINISHED", "limit": n})
    matches = sorted(data["matches"], key=lambda m: m["utcDate"], reverse=True)[:n]
    form = []
    for m in matches:
        hg = m["score"]["fullTime"]["home"]
        ag = m["score"]["fullTime"]["away"]
        if hg is None or ag is None:
            continue
        if m["homeTeam"]["id"] == team_id:
            gf, ga = hg, ag
        else:
            gf, ga = ag, hg
        form.append(1 if gf > ga else (0.5 if gf == ga else 0))
    return form[:n]

def fetch_h2h(home_id, away_id, limit=10):
    data = get(f"/teams/{home_id}/matches",
               {"competitions": COMP, "status": "FINISHED", "limit": limit})
    h2h = []
    for m in sorted(data["matches"], key=lambda x: x["utcDate"], reverse=True):
        h, a = m["homeTeam"]["id"], m["awayTeam"]["id"]
        if {h, a} != {home_id, away_id}:
            continue
        hg = m["score"]["fullTime"]["home"]
        ag = m["score"]["fullTime"]["away"]
        if hg is None or ag is None:
            continue
        h2h.append((hg, ag) if h == home_id else (ag, hg))
        if len(h2h) >= limit:
            break
    return h2h

# ─────────────────────────────────────────────
# POISSON (analytical baseline)
# ─────────────────────────────────────────────
def analytical_probs(lam_h, lam_a, max_g=MAX_GOALS):
    pm = {(h, a): poisson_prob(lam_h, h) * poisson_prob(lam_a, a)
          for h, a in product(range(max_g + 1), repeat=2)}
    hw  = sum(p for (h, a), p in pm.items() if h > a)
    dr  = sum(p for (h, a), p in pm.items() if h == a)
    aw  = sum(p for (h, a), p in pm.items() if h < a)
    top = sorted(pm.items(), key=lambda x: x[1], reverse=True)[:5]
    o25 = sum(p for (h, a), p in pm.items() if h + a > 2)
    btts = (1 - poisson_prob(lam_h, 0)) * (1 - poisson_prob(lam_a, 0))
    return hw, dr, aw, top, o25, btts

# ─────────────────────────────────────────────
# MONTE CARLO SIMULATION
# ─────────────────────────────────────────────
def monte_carlo(lam_h, lam_a, minute=0, score_h=0, score_a=0, n=N_SIMS):
    """
    Simulate n matches from current state.

    Lambda uncertainty: sample each game's λ from Gamma(shape=25, scale=λ/25)
      → mean = λ, CV = 20%  (accounts for good/bad day variance)

    In-play: scale λ by remaining fraction of 90 minutes.
    Minute-by-minute: each remaining minute is an independent Poisson trial.
    """
    rng = np.random.default_rng()
    remaining_frac = max(90 - minute, 1) / 90

    # ── Lambda uncertainty via Gamma prior ──
    lam_h_samples = rng.gamma(shape=GAMMA_SHAPE, scale=lam_h / GAMMA_SHAPE, size=n)
    lam_a_samples = rng.gamma(shape=GAMMA_SHAPE, scale=lam_a / GAMMA_SHAPE, size=n)

    # Scale to remaining time
    lam_h_rem = lam_h_samples * remaining_frac
    lam_a_rem = lam_a_samples * remaining_frac

    # ── Minute-by-minute simulation ──
    remaining_mins = max(90 - minute, 1)
    goals_h = np.zeros(n, dtype=int)
    goals_a = np.zeros(n, dtype=int)

    per_min_h = lam_h_rem / remaining_mins
    per_min_a = lam_a_rem / remaining_mins

    for _ in range(remaining_mins):
        goals_h += rng.poisson(per_min_h)
        goals_a += rng.poisson(per_min_a)

    # Add current score
    final_h = goals_h + score_h
    final_a = goals_a + score_a

    # ── Aggregate results ──
    hw  = np.mean(final_h > final_a)
    dr  = np.mean(final_h == final_a)
    aw  = np.mean(final_h < final_a)
    o25 = np.mean(final_h + final_a > 2)
    btts = np.mean((final_h > 0) & (final_a > 0))

    # Scoreline distribution
    scores, counts = np.unique(np.stack([final_h, final_a], axis=1), axis=0, return_counts=True)
    top5 = sorted(zip(map(tuple, scores.tolist()), (counts / n).tolist()),
                  key=lambda x: x[1], reverse=True)[:5]

    # ── Confidence intervals (bootstrapped, 95%) ──
    batch = 200
    batch_size = n // batch
    hw_b = np.array([np.mean(final_h[i*batch_size:(i+1)*batch_size] >
                              final_a[i*batch_size:(i+1)*batch_size]) for i in range(batch)])
    aw_b = np.array([np.mean(final_h[i*batch_size:(i+1)*batch_size] <
                              final_a[i*batch_size:(i+1)*batch_size]) for i in range(batch)])
    dr_b = 1 - hw_b - aw_b

    ci = {
        "hw": (np.percentile(hw_b, 2.5), np.percentile(hw_b, 97.5)),
        "dr": (np.percentile(dr_b, 2.5), np.percentile(dr_b, 97.5)),
        "aw": (np.percentile(aw_b, 2.5), np.percentile(aw_b, 97.5)),
    }

    return hw, dr, aw, top5, o25, btts, ci

# ─────────────────────────────────────────────
# SUPPORTING CALCULATIONS
# ─────────────────────────────────────────────
def elo_from_table(entry):
    pts    = entry["won"] * 3 + entry["drawn"]
    played = max(entry["played"], 1)
    return 1500 + (pts / played - 1.5) * 120

def elo_expected(elo_a, elo_b, home_bonus=50):
    return 1 / (1 + 10 ** ((elo_b - elo_a - home_bonus) / 400))

def in_play_lambda(base_lam, minute, goals_so_far):
    remaining = max(90 - minute, 1) / 90
    return round(max(base_lam * remaining - goals_so_far * remaining, 0.05), 3)

# ─────────────────────────────────────────────
# OUTPUT HELPERS
# ─────────────────────────────────────────────
def bar(p, width=36):
    return '#' * int(p * width)

def ci_str(lo, hi):
    return f"[{lo*100:.1f}% – {hi*100:.1f}%]"

def section(title):
    print(f"\n  ---- {title} {'-'*max(0, 46 - len(title))}")

# ─────────────────────────────────────────────
# MAIN PREDICT
# ─────────────────────────────────────────────
def predict(home="MCI", away="ARS", override_minute=None, override_home=None,
            override_away=None, n_sims=N_SIMS):
    home_id = TEAM_IDS[home]
    away_id = TEAM_IDS[away]

    print("Fetching live data from football-data.org ...")
    standings = fetch_standings()
    home_st   = standings.get(home_id, {})
    away_st   = standings.get(away_id, {})
    form_h    = fetch_form(home_id)
    form_a    = fetch_form(away_id)
    h2h       = fetch_h2h(home_id, away_id)

    # League average goals/team/game
    all_gf = sum(v["goals_for"] for v in standings.values())
    all_gp = sum(v["played"]    for v in standings.values())
    lg_avg = all_gf / max(all_gp, 1)

    # Attack/defence strength → pre-match λ
    home_att = (home_st["goals_for"]     / max(home_st["played"], 1)) / lg_avg
    home_def = (home_st["goals_against"] / max(home_st["played"], 1)) / lg_avg
    away_att = (away_st["goals_for"]     / max(away_st["played"], 1)) / lg_avg
    away_def = (away_st["goals_against"] / max(away_st["played"], 1)) / lg_avg

    lam_h = round(home_att * away_def * lg_avg * HOME_ADVANTAGE_FACTOR, 3)
    lam_a = round(away_att * home_def * lg_avg, 3)

    # ELO + form blend
    elo_h      = elo_from_table(home_st)
    elo_a      = elo_from_table(away_st)
    elo_win    = elo_expected(elo_h, elo_a)
    fs_h       = form_score(form_h) if form_h else 0.7
    fs_a       = form_score(form_a) if form_a else 0.7
    form_delta = (fs_h - fs_a) * FORM_IMPACT

    # Analytical Poisson (pre-match)
    hw_p, dr_p, aw_p, top5_p, o25_p, btts_p = analytical_probs(lam_h, lam_a)
    hw_p = min(max(hw_p * POISSON_BLEND + elo_win * ELO_BLEND + form_delta, 0), 1)
    aw_p = min(max(aw_p * POISSON_BLEND + (1 - elo_win) * ELO_BLEND - form_delta, 0), 1)
    dr_p = max(0, 1 - hw_p - aw_p)
    _tot = hw_p + dr_p + aw_p
    hw_p /= _tot; dr_p /= _tot; aw_p /= _tot

    # ── Live match ──────────────────────────
    live    = fetch_live_match(home_id, away_id)
    minute  = 0
    hg_now  = 0
    ag_now  = 0
    is_live = False

    if override_minute is not None or override_home is not None:
        live      = {"score": {"fullTime": {}, "halfTime": {}}, "override": True}
        is_live   = True
        minute    = override_minute if override_minute is not None else 0
        hg_now    = override_home   if override_home   is not None else 0
        ag_now    = override_away   if override_away   is not None else 0
        lam_h_rem = in_play_lambda(lam_h, minute, hg_now)
        lam_a_rem = in_play_lambda(lam_a, minute, ag_now)
    elif live:
        is_live = True
        raw_min = live.get("minute")
        if raw_min is None:
            print("  Warning: match minute not available from API (free-tier limitation).")
            print("  Supply --minute <0-90> to enable live remaining-time prediction.")
            print("  Falling back to pre-match λ for remaining time.")
            minute = 0
        else:
            try:
                minute = int(raw_min)
            except (ValueError, TypeError):
                minute = 0
        score  = live["score"]["fullTime"]
        hg_now = score.get("home") or 0
        ag_now = score.get("away") or 0

        # Recalculate remaining λ
        lam_h_rem = in_play_lambda(lam_h, minute, hg_now)
        lam_a_rem = in_play_lambda(lam_a, minute, ag_now)

        # Analytical in-play
        hw_p, dr_p, aw_p, top5_p, o25_p, btts_p = analytical_probs(lam_h_rem, lam_a_rem)
    else:
        lam_h_rem, lam_a_rem = lam_h, lam_a

    # ── Monte Carlo ──────────────────────────
    # Pass already-scaled remaining lambdas with minute=0 to avoid double-scaling
    print(f"Running Monte Carlo simulation ({n_sims:,} iterations) ...")
    t0 = time.time()
    hw_mc, dr_mc, aw_mc, top5_mc, o25_mc, btts_mc, ci = monte_carlo(
        lam_h_rem, lam_a_rem, minute=0, score_h=hg_now, score_a=ag_now, n=n_sims
    )
    elapsed = time.time() - t0

    # ─────────────────────────────────────────
    # PRINT RESULTS
    # ─────────────────────────────────────────
    print()
    print("=" * 58)
    print(f"  MATCH PREDICTION: {home} vs {away}  (Home: {home})")
    print(f"  Source: football-data.org  |  MC: {n_sims:,} sims")
    print("=" * 58)

    if is_live:
        if live.get("override"):
            ht_str = "(manual override)"
        else:
            ht = live["score"].get("halfTime", {})
            ht_h = (ht.get("home") or 0) if ht else 0
            ht_a = (ht.get("away") or 0) if ht else 0
            ht_str = f"Half-time {ht_h}-{ht_a}"
        print(f"\n  LIVE: {minute}' | Score: {home} {hg_now}-{ag_now} {away}")
        print(f"  {ht_str}  |  Remaining xG -> {home}: {lam_h_rem}  {away}: {lam_a_rem}")
    else:
        print(f"\n  [Pre-match]  xG -> {home}: {lam_h}  |  {away}: {lam_a}")

    # ── Side-by-side comparison ──────────────
    section("WIN PROBABILITIES")
    print(f"  {'Outcome':<12} {'Poisson':>8}  {'Monte Carlo':>12}  {'95% CI':>20}")
    print(f"  {'-'*56}")
    for label, p_val, mc_val, ci_key in [
        (f"{home} Win", hw_p, hw_mc, "hw"),
        ("Draw",        dr_p, dr_mc, "dr"),
        (f"{away} Win", aw_p, aw_mc, "aw"),
    ]:
        lo, hi = ci[ci_key]
        print(f"  {label:<12} {p_val*100:>7.1f}%  {mc_val*100:>11.1f}%  "
              f"  {ci_str(lo, hi):>20}")

    # ── MC bar chart ──────────────────────────
    print()
    print(f"    {home} Win  {hw_mc*100:5.1f}%  {bar(hw_mc)}")
    print(f"    Draw      {dr_mc*100:5.1f}%  {bar(dr_mc)}")
    print(f"    {away} Win  {aw_mc*100:5.1f}%  {bar(aw_mc)}")

    # ── Scorelines comparison ─────────────────
    section("TOP 5 SCORELINES")
    print(f"  {'Score':<8} {'Poisson':>8}  {'Monte Carlo':>12}")
    print(f"  {'-'*32}")
    mc_dict   = dict(top5_mc)
    p_dict    = dict(top5_p)
    top_union = sorted(set(p_dict.keys()) | set(mc_dict.keys()),
                       key=lambda s: mc_dict.get(s, 0), reverse=True)[:5]
    for s in top_union:
        tag = "W" if s[0] > s[1] else ("D" if s[0] == s[1] else "L")
        pv  = p_dict.get(s,  0)
        mv  = mc_dict.get(s, 0)
        print(f"  {s[0]}-{s[1]} [{tag}]  {pv*100:>7.1f}%  {mv*100:>11.1f}%")

    # ── H2H ──────────────────────────────────
    if h2h:
        home_wins    = sum(1 for hg, ag in h2h if hg > ag)
        draws_h2h    = sum(1 for hg, ag in h2h if hg == ag)
        away_win_h2h = sum(1 for hg, ag in h2h if hg < ag)
        section(f"HEAD-TO-HEAD  (last {len(h2h)} PL meetings)")
        print(f"  {home}: {home_wins}W  |  Draw: {draws_h2h}  |  {away}: {away_win_h2h}W")
        print(f"  Goals: {home} {sum(x for x,_ in h2h)} - {sum(y for _,y in h2h)} {away}")

    # ── Form ─────────────────────────────────
    section("FORM (last 5)")
    print(f"  {home}: {' '.join(FORM_MAP[x] for x in form_h)}  (score: {fs_h:.2f})")
    print(f"  {away}: {' '.join(FORM_MAP[x] for x in form_a)}  (score: {fs_a:.2f})")

    # ── Season stats ─────────────────────────
    section("SEASON STATS")
    for label, st in ((home, home_st), (away, away_st)):
        gd  = st["goals_for"] - st["goals_against"]
        pts = st["won"] * 3 + st["drawn"]
        print(f"  {label}: P{st['played']} W{st['won']} D{st['drawn']} "
              f"L{st['lost']} GD{gd:+} Pts{pts}")

    # ── Verdict ───────────────────────────────
    section("VERDICT  (Monte Carlo)")
    top_mc = top5_mc[0][0]
    if hw_mc > aw_mc and hw_mc > dr_mc:
        fav, prob = home, hw_mc
    elif aw_mc > hw_mc and aw_mc > dr_mc:
        fav, prob = away, aw_mc
    else:
        fav, prob = "Draw", dr_mc
    print(f"  Predicted outcome  : {fav} ({prob*100:.1f}%)")
    print(f"  Most likely score  : {top_mc[0]}-{top_mc[1]}")
    print(f"  Over 2.5 goals     : {o25_mc*100:.1f}%")
    print(f"  Both teams score   : {btts_mc*100:.1f}%")
    print(f"  MC simulation time : {elapsed:.2f}s  ({n_sims:,} iterations)")
    print("=" * 58)
    print("  * Poisson + xG + ELO + Form + Monte Carlo")
    print("  * MC: Gamma(lambda uncertainty, CV=20%) + minute-by-minute")
    if is_live:
        print("  * In-play: remaining-time lambda scaling applied")
    print("=" * 58)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--minute",      type=int, default=None)
    parser.add_argument("--home-goals",  type=int, default=None)
    parser.add_argument("--away-goals",  type=int, default=None)
    parser.add_argument("--simulations", type=int, default=N_SIMS,
                        help=f"Monte Carlo simulation count (default: {N_SIMS})")
    args = parser.parse_args()

    if args.minute is not None and not (0 <= args.minute <= 120):
        parser.error("--minute must be between 0 and 120")
    if args.home_goals is not None and args.home_goals < 0:
        parser.error("--home-goals must be >= 0")
    if args.away_goals is not None and args.away_goals < 0:
        parser.error("--away-goals must be >= 0")
    if args.simulations < 1000:
        print(f"  Warning: --simulations {args.simulations} is very low; results may be unreliable.")

    if API_KEY == "YOUR_API_KEY_HERE":
        print("\nERROR: No API key set.")
        print("  set FOOTBALL_API_KEY=your_key   (CMD)")
        print("  $env:FOOTBALL_API_KEY='key'     (PowerShell)")
        sys.exit(1)
    predict("MCI", "ARS",
            override_minute=args.minute,
            override_home=args.home_goals,
            override_away=args.away_goals,
            n_sims=args.simulations)
