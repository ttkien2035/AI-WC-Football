"""Phase C: fit the minute-simulator's SCORE-STATE response from real data —
CONTROLLING FOR TEAM STRENGTH (the naive rate-by-state is confounded: strong
teams both lead and keep scoring, so leading teams *look* like they score more
when raw — that's selection, not the causal Dixon-Robinson ease-off).

We isolate the causal effect with a Poisson GLM on team-minute observations:
  goal_in_minute ~ state dummies,  offset = log(team's expected rate / minute)
where the offset (team's match xG spread over the game) absorbs team quality.
exp(state coef) is then the WITHIN-match scoring multiplier when leading /
trailing vs level, free of the strength confound.

314 cached international matches (StatsBomb, no re-download).
Writes app/data/models/sim_fit.json; serving (engine/match_sim) reads it.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "sim_fit.json"


def goals_of(events: list) -> list[tuple[int, str]]:
    """(minute, scoring_team) for every goal — shots that scored + own goals."""
    out = []
    for e in events:
        typ = (e.get("type") or {}).get("name")
        tm = (e.get("team") or {}).get("name")
        mn = e.get("minute")
        if mn is None or not tm:
            continue
        if typ == "Shot" and ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
            out.append((mn, tm))
        elif typ == "Own Goal Against":      # credited to the beneficiary team
            out.append((mn, tm))
    return out


def main() -> None:
    tm_xg = {}                            # (match_id, team) -> match xG (strength)
    tmcsv = CACHE / "team_match.csv"
    if tmcsv.exists():
        df = pd.read_csv(tmcsv)
        for r in df.itertuples(index=False):
            tm_xg[(r.match_id, r.team)] = max(float(r.xg), 0.3)

    raw_goals, raw_expo = defaultdict(float), defaultdict(float)
    rows = []                             # team-minute obs for the controlled GLM
    n_matches = 0

    for f in sorted(CACHE.glob("ev_*.json")):
        mid = int(f.stem.split("_")[1])
        try:
            ev = json.loads(f.read_text())
        except Exception:
            continue
        allteams = list({(e.get("team") or {}).get("name") for e in ev
                         if (e.get("team") or {}).get("name")})
        if len(allteams) < 2:
            continue
        a, b = allteams[0], allteams[1]
        by_min = defaultdict(lambda: defaultdict(int))
        for mn, tm in goals_of(ev):
            if tm in (a, b):
                by_min[mn][tm] += 1
        n_matches += 1
        # expected goals/minute for each team (strength control via offset)
        exp_rate = {t: tm_xg.get((mid, t), 1.3) / 96.0 for t in (a, b)}
        sa = sb = 0
        for m in range(0, 96):
            for tm, s_me, s_op in ((a, sa, sb), (b, sb, sa)):
                diff = s_me - s_op
                bucket = "lead2" if diff >= 2 else "lead1" if diff == 1 else \
                         "level" if diff == 0 else "trail1" if diff == -1 else "trail2"
                g = by_min[m][tm]
                raw_expo[bucket] += 1
                raw_goals[bucket] += g
                rows.append((g, bucket, math.log(exp_rate[tm])))
            sa += by_min[m][a]
            sb += by_min[m][b]

    # --- naive (confounded) rate-by-state, for contrast ---
    naive = {k: round((raw_goals[k] / raw_expo[k]) / (raw_goals["level"] / raw_expo["level"]), 3)
             for k in raw_expo}
    print(f"matches: {n_matches}")
    print("NAIVE rate vs level (CONFOUNDED by strength):",
          {k: naive[k] for k in ("lead2", "lead1", "trail1", "trail2")})

    # --- strength-controlled Poisson GLM ---
    d = pd.DataFrame(rows, columns=["goal", "state", "offset"])
    dummies = pd.get_dummies(d["state"]).astype(float)
    order = ["lead2", "lead1", "trail1", "trail2"]   # 'level' = reference
    X = sm.add_constant(dummies[order])
    glm = sm.GLM(d["goal"], X, family=sm.families.Poisson(), offset=d["offset"]).fit()
    print("\n=== STRENGTH-CONTROLLED multiplier vs level (causal) ===")
    mult = {}
    for k in order:
        mult[k] = round(float(np.exp(glm.params[k])), 3)
        print(f"  {k:7s} x{mult[k]:.3f}   p={glm.pvalues[k]:.3f}")

    # serving multipliers: gate by significance; the LEADING side is capped at
    # <=1.0 (its positive estimate is confound-suspect — a team 2-up is having
    # an exceptional game beyond its season xG, so we don't let the sim boost
    # leaders). TRAILING push is significant + mechanistically clean -> adopt.
    P = 0.05
    serving = {}
    for k in order:
        v, sig = mult[k], glm.pvalues[k] < P
        if k.startswith("lead"):
            serving[k] = round(min(1.0, v) if sig else 1.0, 3)   # no boost when leading
        else:
            serving[k] = round(v if sig else 1.0, 3)             # adopt push if significant
    print(f"\nhand-set sim_state_effect = 0.12 (lead x0.88 / trail x1.12)")
    print(f"SERVING (data-gated): {serving}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "n_matches": n_matches,
        "naive_mult_confounded": {k: naive[k] for k in order},
        "controlled_mult": mult,
        "controlled_p": {k: round(float(glm.pvalues[k]), 4) for k in order},
        "serving_mult": serving,
        "note": "raw rate-by-state is confounded (strong teams lead+score); these "
                "are strength-controlled (Poisson offset on team xG). Leading side "
                "capped <=1.0 (residual momentum confound); trailing push adopted "
                "where significant.",
    }, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
