"""Group-B prototype: is rolling xG-form a BETTER predictor of the next result
than rolling goals-form? If yes, in-tournament rating should update on xG (less
noisy) rather than raw goals. Measure-first.

Per competition-season, order each team's matches by date; build pre-match
rolling (last 5) mean xG-diff and goal-diff; test which better predicts the
current match margin/result. Big sample from club seasons + tournaments.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CACHE = Path(__file__).parent / "data" / "statsbomb"


def main() -> None:
    rich = pd.read_csv(CACHE / "team_match_rich.csv")
    # match_id -> date from the cached match lists
    date = {}
    for f in glob.glob(str(CACHE / "matches_*.json")):
        for m in json.loads(Path(f).read_text()):
            if m.get("match_date"):
                date[m["match_id"]] = m["match_date"]
    rich = rich[rich.match_id.isin(date)].copy()
    rich["date"] = rich.match_id.map(date)
    rich["xgd"] = rich.xg - rich.groupby("match_id")["xg"].transform("sum") + rich.xg  # placeholder
    # xG conceded = opponent xG in same match
    opp_xg = rich.groupby("match_id")["xg"].transform("sum") - rich.xg
    rich["xg_diff"] = rich.xg - opp_xg
    rich["goal_diff"] = rich.goals_for - rich.goals_against
    rich = rich.sort_values(["comp", "team", "date"])

    rows = []
    fx, fg = defaultdict(lambda: deque(maxlen=5)), defaultdict(lambda: deque(maxlen=5))
    for r in rich.itertuples():
        k = (r.comp, r.team)
        if len(fx[k]) >= 3:                       # need some prior history
            rows.append({"margin": r.goal_diff,
                         "form_xg": float(np.mean(fx[k])),
                         "form_goal": float(np.mean(fg[k]))})
        fx[k].append(r.xg_diff); fg[k].append(r.goal_diff)
    d = pd.DataFrame(rows)
    print(f"team-match obs with >=3 prior games: {len(d)}")
    print(f"corr(next margin, rolling xG-form)   = {d.margin.corr(d.form_xg):+.3f}")
    print(f"corr(next margin, rolling goal-form) = {d.margin.corr(d.form_goal):+.3f}")

    # head-to-head regression: include BOTH; which survives?
    X = sm.add_constant(d[["form_xg", "form_goal"]])
    g = sm.OLS(d["margin"], X).fit()
    print("\n=== margin ~ xG-form + goal-form (both in) ===")
    for c in ("form_xg", "form_goal"):
        print(f"  {c:10s} coef {g.params[c]:+.4f}  p={g.pvalues[c]:.3f}")
    print(f"  R2 {g.rsquared:.4f}")
    # solo R2 each
    rx = sm.OLS(d["margin"], sm.add_constant(d[["form_xg"]])).fit().rsquared
    rg = sm.OLS(d["margin"], sm.add_constant(d[["form_goal"]])).fit().rsquared
    print(f"  solo R2: xG-form {rx:.4f} vs goal-form {rg:.4f}")
    better = "xG-form better -> update on xG" if (g.pvalues["form_xg"] < 0.05 and
             (g.pvalues["form_goal"] > 0.05 or rx > rg)) else "goal-form not beaten by xG"
    print(f"\nVERDICT: {better}")


if __name__ == "__main__":
    main()
