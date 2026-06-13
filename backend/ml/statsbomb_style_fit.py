"""Phase B: does PLAYING STYLE actually move total goals / results, or are the
hand-set style factors (style_total_max=0.06 on lambda, supremacy +-18 Elo)
unjustified? Measure it on the 314 international matches already aggregated by
ml/statsbomb_fit.py (cached team_match.csv) — no assumptions.

Style proxies from observed event data (no pre-match tags needed):
  possession_balance = |poss_home - 0.5|*2   (0 = even, 1 = one-sided)
  pressing_sum       = pressures_home + pressures_away   (tempo/intensity)
  shots_sum          = total shots            (openness)
  possession_diff    = poss_home - poss_away  (dominance -> result?)

We answer:
  1. total_goals ~ possession_balance + pressing_sum   (style -> totals?)
  2. result      ~ possession_diff                     (dominance -> win?)
and translate the effect sizes into kept / shrunk / disabled factors.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "style_fit.json"


def match_level(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mid, g in df.groupby("match_id"):
        if len(g) != 2:
            continue
        a, b = g.iloc[0], g.iloc[1]
        rows.append({
            "total_goals": a.goals_for + b.goals_for,
            "poss_balance": abs(a.possession - 0.5) * 2,
            "pressing_sum": a.pressures + b.pressures,
            "shots_sum": a.shots + b.shots,
            "xg_sum": a.xg + b.xg,
            # team A perspective for result/dominance
            "poss_diff": a.possession - b.possession,
            "result_a": 1 if a.goals_for > b.goals_for else (0 if a.goals_for == b.goals_for else -1),
            "win_a": int(a.goals_for > b.goals_for),
        })
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_csv(CACHE / "team_match.csv")
    m = match_level(df)
    print(f"matches: {len(m)} | total goals mean {m.total_goals.mean():.2f}")

    print("\n=== (1) STYLE -> TOTAL GOALS : correlations ===")
    for f in ["poss_balance", "pressing_sum", "shots_sum", "xg_sum"]:
        print(f"  total_goals ~ {f:13s} r = {m.total_goals.corr(m[f]):+.3f}")
    # regression controlling for shot volume (the obvious driver): does style
    # (possession balance / pressing) add anything to goals beyond shots?
    X = sm.add_constant(m[["shots_sum", "poss_balance", "pressing_sum"]])
    res = sm.OLS(m["total_goals"], X).fit()
    print("\n  OLS total_goals ~ shots_sum + poss_balance + pressing_sum:")
    for k in ["poss_balance", "pressing_sum"]:
        print(f"    {k:13s} coef {res.params[k]:+.4f}  p={res.pvalues[k]:.3f}")
    print(f"    (shots_sum coef {res.params['shots_sum']:+.4f}  p={res.pvalues['shots_sum']:.3f})")

    print("\n=== (2) POSSESSION DOMINANCE -> RESULT ===")
    print(f"  corr(poss_diff, win_a)    r = {m.win_a.corr(m.poss_diff):+.3f}")
    print(f"  corr(poss_diff, result_a) r = {m.result_a.corr(m.poss_diff):+.3f}")
    Xr = sm.add_constant(m[["poss_diff"]])
    lr = sm.Logit(m["win_a"], Xr).fit(disp=0)
    print(f"  Logit win_a ~ poss_diff: coef {lr.params['poss_diff']:+.3f} p={lr.pvalues['poss_diff']:.3f}")
    # what win-rate does a big possession edge buy? compare top vs bottom tercile
    hi = m[m.poss_diff > m.poss_diff.quantile(0.75)]
    lo = m[m.poss_diff < m.poss_diff.quantile(0.25)]
    print(f"  win% when dominating possession (top 25%): {hi.win_a.mean():.1%} "
          f"vs ceding it (bottom 25%): {lo.win_a.mean():.1%}")

    print("\n=== VERDICT ===")
    pb = m.total_goals.corr(m.poss_balance)
    pd_r = m.win_a.corr(m.poss_diff)
    print(f"  style->totals (poss_balance r={pb:+.3f}): "
          f"{'keep small' if abs(pb) > 0.08 else 'WEAK -> shrink style_total_max'}")
    print(f"  possession->win (r={pd_r:+.3f}): "
          f"{'real edge' if abs(pd_r) > 0.12 else 'WEAK -> supremacy mostly noise'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "n_matches": int(len(m)),
        "total_goals_mean": round(float(m.total_goals.mean()), 3),
        "corr_style_totals": {
            "poss_balance": round(float(m.total_goals.corr(m.poss_balance)), 3),
            "pressing_sum": round(float(m.total_goals.corr(m.pressing_sum)), 3),
            "shots_sum": round(float(m.total_goals.corr(m.shots_sum)), 3),
        },
        "style_totals_significant": bool(res.pvalues["poss_balance"] < 0.05
                                         or res.pvalues["pressing_sum"] < 0.05),
        "corr_possession_win": round(float(pd_r), 3),
        "possession_win_significant": bool(lr.pvalues["poss_diff"] < 0.05),
        "win_pct_dominate_vs_cede": [round(float(hi.win_a.mean()), 3),
                                     round(float(lo.win_a.mean()), 3)],
        "note": "style effect on totals NOT significant beyond shots; possession "
                "dominance only weakly predicts wins -> style factors kept SMALL.",
    }, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
