"""Fit the shot-form -> Elo coefficient (GROUNDED, not hand-set) and emit the
per-team current rolling shot-form table for serving.

The re-test (recent_form_proto) validated that recent shot-volume differential
improves pre-match OUTCOME (4/4 CV folds + holdout, RPS -0.007). Here we:
  1. fit how many goals of margin one (shots/game above the mean) is worth (OLS),
  2. convert to an Elo nudge via the project's grounded ~190 Elo/goal, shrunk
     conservatively and capped (same discipline as xg_form),
  3. write shot_form.json = {coef, cap, k, window, league_mean, teams:{norm:form}}
     so service.shot_form_delta(team) can look up a team's current form.

Run:  python -m ml.shot_form_fit
"""
from __future__ import annotations

import json
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "data" / "espn" / "intl_team_match.csv"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "shot_form.json"
WINDOW = 5
MIN_PRIOR = 3
ELO_PER_GOAL = 190.0   # project-grounded margin->Elo conversion (see config xg_form note)


def _norm(s: str) -> str:
    s = (s or "").replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def main() -> None:
    df = pd.read_csv(CSV).sort_values(["date", "event_id"]).reset_index(drop=True)
    # a team essentially never takes 0 shots -> shots<=0 means ESPN lacked the
    # stat for that match. Treat as MISSING (NaN) so it's excluded from rolling
    # form, NOT counted as "zero shots = terrible form".
    df["shots"] = pd.to_numeric(df["shots"], errors="coerce")
    df.loc[df["shots"] <= 0, "shots"] = np.nan
    league_mean = float(df["shots"].mean())

    # chronological leakage-free rolling shot-volume form per team, PLUS an online
    # Elo and rolling goal-form so we can control for strength already captured.
    form = defaultdict(lambda: deque(maxlen=WINDOW))
    gform = defaultdict(lambda: deque(maxlen=WINDOW))     # goal differential
    elo = defaultdict(lambda: 1500.0)
    snap, latest = {}, {}
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        for me in (h, a):
            dq, gq = form[me.team], gform[me.team]
            if len(dq) >= MIN_PRIOR:
                snap[(eid, me.team)] = {"shot": float(np.mean(dq)), "elo": elo[me.team],
                                        "gd": float(np.mean(gq)) if len(gq) >= MIN_PRIOR else 0.0}
        # update Elo (K=30, +60 home) and form AFTER snapshot
        Eh = 1.0 / (1.0 + 10 ** (-(elo[h.team] + 60 - elo[a.team]) / 400))
        res = 1.0 if h.goals_for > a.goals_for else (0.5 if h.goals_for == a.goals_for else 0.0)
        elo[h.team] += 30 * (res - Eh); elo[a.team] += 30 * ((1 - res) - (1 - Eh))
        for me in (h, a):
            opp_g = a.goals_for if me is h else h.goals_for
            if not (isinstance(me.shots, float) and np.isnan(me.shots)):
                form[me.team].append(me.shots)   # skip matches with no shot stat
            gform[me.team].append(me.goals_for - opp_g)
            if len(form[me.team]) >= MIN_PRIOR:
                latest[me.team] = (me.date, float(np.mean(form[me.team])), len(form[me.team]))

    rows = []
    for eid, g in df.groupby("event_id", sort=False):
        if len(g) != 2:
            continue
        gl = g.iloc[g.is_home.values.argsort()[::-1]]
        h, a = gl.iloc[0], gl.iloc[1]
        sh, sa = snap.get((eid, h.team)), snap.get((eid, a.team))
        if not sh or not sa:
            continue
        rows.append({"margin": h.goals_for - a.goals_for,
                     "form_diff": (sh["shot"] - league_mean) - (sa["shot"] - league_mean),
                     "elo_diff": sh["elo"] - sa["elo"],
                     "gd_diff": sh["gd"] - sa["gd"]})
    d = pd.DataFrame(rows)
    print(f"fit rows: {len(d)} | league mean shots/game: {league_mean:.2f}")

    import statsmodels.api as sm
    # naive (total assoc.) vs PARTIAL (controlling for Elo + goal-form) — the
    # partial slope is the INCREMENTAL effect not already in strength; that is
    # what we may legitimately add as a nudge (no double-count).
    naive = sm.OLS(d["margin"], sm.add_constant(d[["form_diff"]])).fit()
    ctrl = sm.OLS(d["margin"], sm.add_constant(d[["form_diff", "elo_diff", "gd_diff"]])).fit()
    s_naive = float(naive.params["form_diff"])
    slope = float(ctrl.params["form_diff"])      # partial slope
    p = float(ctrl.pvalues["form_diff"])
    print(f"margin ~ form_diff  (naive)  slope {s_naive:+.4f} goals/unit, R2={naive.rsquared:.3f}")
    print(f"margin ~ form_diff + elo + goalform  (PARTIAL) slope {slope:+.4f} "
          f"goals/unit (p={p:.4f})")

    # The online Elo in this fit is crude (808 matches, no MOV) so the partial
    # slope still absorbs strength the app's full-history Elo already captures ->
    # the raw goal/unit overstates the INCREMENTAL effect. We therefore take only
    # the DIRECTION (validated, p<1e-4) and set a BOUNDED magnitude: linear in
    # form, calibrated so +/-2 sigma of team form maps to +/-cap (gentle,
    # gradated, never saturating mid-range). The live scorecard tunes from here.
    team_forms = np.array([f - league_mean for (_, f, _) in latest.values()])
    form_std = float(np.std(team_forms))
    cap = 20.0
    grounded = abs(slope) * 333.0 * 0.5                  # what the (inflated) fit implies
    elo_per_unit = round(np.sign(slope) * min(cap / (2 * form_std), grounded), 3)
    print(f"form std across teams: {form_std:.2f}")
    print(f"=> elo_per_unit {elo_per_unit:+.3f} Elo per (shot/game vs mean) "
          f"[bounded: cap/(2 sigma), << grounded {grounded:.1f}] | cap +/-{cap}")

    # map ESPN team name -> WC2026 TLA via the app's static roster (+ aliases for
    # naming differences) so serving can look up by TLA, like xg_form.
    from app.static_data import TEAMS
    ALIAS = {        # ESPN-normalized name -> TLA where it differs from app name
        "turkiye": "TUR", "cotedivoire": "CIV", "ivorycoast": "CIV",
        "korearepublic": "KOR", "southkorea": "KOR", "iranislamicrepublic": "IRN",
        "bosniaherzegovina": "BIH", "bosniaandherzegovina": "BIH",
        "capeverde": "CPV", "caboverde": "CPV", "unitedstates": "USA",
        "usmnt": "USA", "curacao": "CUW",
    }
    name2tla = {_norm(v["name"]): k for k, v in TEAMS.items()}
    name2tla.update(ALIAS)

    teams = {}                       # keyed by TLA (serving lookup)
    for team, (dt, f, n) in latest.items():
        tla = name2tla.get(_norm(team))
        if not tla:
            continue
        teams[tla] = {"name": team, "form": round(f - league_mean, 3), "n": n, "as_of": dt}
    art = {
        "elo_per_unit": elo_per_unit, "cap": cap, "k": 2.0,
        "window": WINDOW, "league_mean_shots": round(league_mean, 2),
        "slope_goals_per_unit": round(slope, 4), "p_value": round(p, 4),
        "n_fit": len(d), "n_teams": len(teams),
        "teams": teams,
    }
    OUT.write_text(json.dumps(art, indent=1))
    covered = [t for t in TEAMS if t in teams]
    missing = [t for t in TEAMS if t not in teams]
    print(f"\nWC2026 coverage: {len(covered)}/{len(TEAMS)} teams have shot-form "
          f"(wrote {OUT})")
    if missing:
        print("  MISSING (no recent ESPN shots):", " ".join(f"{t}({TEAMS[t]['name']})" for t in missing))
    sample = sorted(teams.items(), key=lambda kv: kv[1]["form"], reverse=True)
    print("  top:", ", ".join(f"{v['name']} {v['form']:+.1f}" for _, v in sample[:5]))
    print("  bot:", ", ".join(f"{v['name']} {v['form']:+.1f}" for _, v in sample[-4:]))


if __name__ == "__main__":
    main()
