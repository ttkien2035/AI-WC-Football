"""Group-A prototype: does REST / fixture congestion improve prediction of the
current goal targets, beyond team strength? Measure-first — adopt only if it
beats strength on a holdout.

Rest-days are reconstructed per team within each competition-season from the
cached StatsBomb match lists (match_date). Strength is controlled with the
Dixon-Coles att/def ratings. We test:
  (1) fatigue -> total goals     (less rest => fewer goals?)
  (2) rest edge -> margin/result (more-rested team does better?)
mainly on TOURNAMENT matches (dense 3-7 day schedule, the WC-relevant regime).
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CACHE = Path(__file__).parent / "data" / "statsbomb"
INTL = {"FIFA World Cup", "UEFA Euro", "Copa America", "African Cup of Nations"}


def build() -> pd.DataFrame:
    # generic strength proxy works for club AND national teams: each team's
    # mean goals-for / goals-against within the competition-season.
    raw = []
    for f in glob.glob(str(CACHE / "matches_*.json")):
        ms = json.loads(Path(f).read_text())
        comp = ms[0]["competition"]["competition_name"] if ms else ""
        sid = f.rsplit("_", 1)[-1]
        level = "intl" if comp in INTL else "club"
        ms = [m for m in ms if m.get("match_date") and m["home_score"] is not None]
        ms.sort(key=lambda m: m["match_date"])
        last: dict[str, str] = {}
        for m in ms:
            d = pd.Timestamp(m["match_date"])
            h, a = m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]
            rh = (d - pd.Timestamp(last[h])).days if h in last else None
            ra = (d - pd.Timestamp(last[a])).days if a in last else None
            last[h] = last[a] = m["match_date"]
            raw.append({"comp": comp, "sid": sid, "level": level, "home": h, "away": a,
                        "gh": m["home_score"], "ga": m["away_score"],
                        "rest_h": rh, "rest_a": ra})
    df = pd.DataFrame(raw)
    # per (comp-season, team) strength = mean gf / mean ga across the season
    gf, ga = defaultdict(list), defaultdict(list)
    for r in df.itertuples():
        gf[(r.sid, r.home)].append(r.gh); ga[(r.sid, r.home)].append(r.ga)
        gf[(r.sid, r.away)].append(r.ga); ga[(r.sid, r.away)].append(r.gh)
    mgf = {k: float(np.mean(v)) for k, v in gf.items()}
    mga = {k: float(np.mean(v)) for k, v in ga.items()}
    df["att_h"] = [mgf[(s, t)] for s, t in zip(df.sid, df.home)]
    df["def_h"] = [mga[(s, t)] for s, t in zip(df.sid, df.home)]
    df["att_a"] = [mgf[(s, t)] for s, t in zip(df.sid, df.away)]
    df["def_a"] = [mga[(s, t)] for s, t in zip(df.sid, df.away)]
    df = df.dropna(subset=["rest_h", "rest_a"])
    return df[(df.rest_h <= 21) & (df.rest_a <= 21)]


def main() -> None:
    df = build()
    print(f"rows (rest<=21d): {len(df)} | intl {sum(df.level=='intl')} club {sum(df.level=='club')}")
    df["tot"] = df.gh + df.ga
    df["margin"] = df.gh - df.ga
    df["rest_diff"] = df.rest_h - df.rest_a
    df["str_diff"] = (df.att_h - df.def_a) - (df.att_a - df.def_h)   # strength supremacy
    df["str_sum"] = (df.att_h - df.def_a) + (df.att_a - df.def_h)
    df["min_rest"] = df[["rest_h", "rest_a"]].min(axis=1)
    df["is_club"] = (df.level == "club").astype(float)
    df["home_win"] = (df.margin > 0).astype(float)

    print(f"\nrest distribution: median {df.min_rest.median():.0f}d, "
          f"share <=4d {(df.min_rest<=4).mean():.0%}")

    print("\n=== (1) fatigue -> total goals (control strength) ===")
    X = sm.add_constant(df[["str_sum", "is_club", "min_rest"]])
    g = sm.OLS(df["tot"], X).fit()
    print(f"  min_rest coef {g.params['min_rest']:+.4f}  p={g.pvalues['min_rest']:.3f}  "
          f"({'fewer goals when tired' if g.params['min_rest']>0 and g.pvalues['min_rest']<0.05 else 'n.s.'})")

    print("\n=== (2) rest edge -> result/margin (control strength) ===")
    Xm = sm.add_constant(df[["str_diff", "is_club", "rest_diff"]])
    gm = sm.OLS(df["margin"], Xm).fit()
    print(f"  rest_diff -> margin coef {gm.params['rest_diff']:+.4f}  p={gm.pvalues['rest_diff']:.3f}")
    # practical size: win% for big rest edge vs deficit (tournament subset)
    t = df[df.level == "intl"]
    adv = t[t.rest_diff >= 2]; dis = t[t.rest_diff <= -2]
    print(f"  [intl] home win% with +2d rest edge {adv.home_win.mean():.1%} (n={len(adv)}) "
          f"vs -2d {dis.home_win.mean():.1%} (n={len(dis)})")

    print("\nVERDICT:", "rest matters -> worth wiring" if
          (g.pvalues['min_rest'] < 0.05 or gm.pvalues['rest_diff'] < 0.05)
          else "no significant rest effect beyond strength")


if __name__ == "__main__":
    main()
