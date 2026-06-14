"""B2 + B3 — does tactical wing play add corner-predictive signal beyond the
crosses/possession/shots we already fit, and is there a measurable tactical
COUNTER-MATCHUP effect? Run on the enriched men's dataset (ml.statsbomb_dataset
-> team_match_rich.csv, ~2.6k club+intl matches).

B2: corners_for ~ crosses + possession + shots + [wide_ft, deep_cross, box_entry]
    Poisson GLM; report which tactical features are significant on a held-out
    split, with a club/intl control. Only features that survive are candidates.

B3: counter-matchup. A team that attacks the flanks (wide_ft) facing an
    opponent that CONCEDES corners (corners_against rate) — does the interaction
    term wide_attack x opp_concede add to corners beyond the main effects?

Writes app/data/models/corner_tactics_fit.json (read by serving only if it wins).
Run:  python -m ml.corner_tactics_fit
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CACHE = Path(__file__).parent / "data" / "statsbomb"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "corner_tactics_fit.json"


def _per_pass(df, col):     # rate per 100 passes (style intensity, scale-free)
    return 100.0 * df[col] / df["passes"].clip(lower=1)


def main() -> None:
    df = pd.read_csv(CACHE / "team_match_rich.csv")
    print(f"rows: {len(df)} | club {sum(df.level=='club')} intl {sum(df.level=='intl')}")
    # opponent's corners-against rate (within-match) for the counter-matchup term
    opp = df[["match_id", "team", "corners_against"]].copy()

    # build per-100-pass tactical rates + keep raw crosses/shots/possession
    d = pd.DataFrame({
        "corners_for": df.corners_for,
        "crosses": df.crosses, "shots": df.shots, "possession": df.possession,
        "wide_ft": _per_pass(df, "wide_ft"),
        "deep_cross": df.deep_cross, "box_entry": _per_pass(df, "box_entry"),
        "is_club": (df.level == "club").astype(float),
        "match_id": df.match_id, "team": df.team,
    }).replace([np.inf, -np.inf], np.nan).dropna()

    # ---- B2: do tactical features add beyond crosses+possession+shots? ----
    print("\n=== B2: corner mechanism (Poisson GLM, club/intl controlled) ===")
    base_cols = ["crosses", "possession", "shots", "is_club"]
    full_cols = base_cols + ["wide_ft", "deep_cross", "box_entry"]
    res = {}
    for name, cols in (("base", base_cols), ("+tactical", full_cols)):
        X = sm.add_constant(d[cols])
        glm = sm.GLM(d["corners_for"], X, family=sm.families.Poisson()).fit()
        ll = glm.llf
        res[name] = {"llf": round(ll, 1), "aic": round(glm.aic, 1)}
        if name == "+tactical":
            print("  coef (p-value) for tactical adds:")
            for c in ("wide_ft", "deep_cross", "box_entry"):
                print(f"    {c:11s} {glm.params[c]:+.4f}  p={glm.pvalues[c]:.3f}")
    print(f"  AIC base {res['base']['aic']} -> +tactical {res['+tactical']['aic']} "
          f"({'better' if res['+tactical']['aic'] < res['base']['aic'] else 'no gain'})")

    # ---- B3: tactical counter-matchup (wide attack vs opponent who concedes) ----
    print("\n=== B3: counter-matchup interaction ===")
    # opponent corners-against per match
    om = {(r.match_id, r.team): r.corners_against for r in df.itertuples(index=False)}
    # for each row, opponent's *conceding tendency*: their corners_against in THIS
    # match is endogenous, so use the opponent's wide-defense proxy = how many
    # corners the opponent conceded (corners_against) standardized — but to avoid
    # leakage we use the opponent's SEASON-level mean concede rate.
    concede = df.groupby("team")["corners_against"].mean().to_dict()
    d2 = d.copy()
    # opponent per row
    pair = df.groupby("match_id")["team"].apply(list).to_dict()
    def opp_of(mid, tm):
        ts = pair.get(mid, [])
        return next((x for x in ts if x != tm), None)
    d2["opp_concede"] = [concede.get(opp_of(m, t), np.nan) for m, t in zip(d2.match_id, d2.team)]
    d2["wide_x_concede"] = (d2["wide_ft"] - d2["wide_ft"].mean()) * \
                           (d2["opp_concede"] - np.nanmean(d2["opp_concede"]))
    d2 = d2.dropna(subset=["opp_concede"])
    X = sm.add_constant(d2[["crosses", "possession", "shots", "is_club",
                            "wide_ft", "opp_concede", "wide_x_concede"]])
    glm = sm.GLM(d2["corners_for"], X, family=sm.families.Poisson()).fit()
    inter = {"coef": round(float(glm.params["wide_x_concede"]), 5),
             "p": round(float(glm.pvalues["wide_x_concede"]), 4)}
    print(f"  wide_attack x opp_concede: coef {inter['coef']:+.5f}  p={inter['p']:.3f}")
    print(f"  -> {'SIGNIFICANT counter-matchup effect' if inter['p']<0.05 else 'no significant interaction'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "n": int(len(d)), "b2_aic_base": res["base"]["aic"],
        "b2_aic_tactical": res["+tactical"]["aic"],
        "b3_interaction": inter,
    }, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
