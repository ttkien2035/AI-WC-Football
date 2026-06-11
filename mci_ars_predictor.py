"""
MCI vs ARS Match Prediction Model
Uses: Poisson Distribution + ELO Ratings + Form Analysis + H2H Records
"""

import math
from itertools import product

from prediction_utils import (
    HOME_ADVANTAGE_FACTOR, POISSON_BLEND, ELO_BLEND, FORM_IMPACT,
    MAX_GOALS, FORM_MAP, poisson_prob, form_score,
)

# ─────────────────────────────────────────────
# 1. HISTORICAL H2H DATA (last 10 PL meetings)
# ─────────────────────────────────────────────
H2H = [
    # (season, venue, mci_goals, ars_goals)
    ("2024-25", "ARS", 2, 2),
    ("2024-25", "MCI", 3, 1),
    ("2023-24", "ARS", 0, 1),
    ("2023-24", "MCI", 0, 0),
    ("2022-23", "ARS", 4, 1),
    ("2022-23", "MCI", 1, 0),
    ("2021-22", "ARS", 5, 0),
    ("2021-22", "MCI", 2, 1),
    ("2020-21", "ARS", 1, 0),
    ("2020-21", "MCI", 0, 1),
]

# ─────────────────────────────────────────────
# 2. 2025-26 SEASON STATS (approx. up to Apr 2026)
# ─────────────────────────────────────────────
STATS = {
    "MCI": {
        "played": 33, "won": 19, "drawn": 7, "lost": 7,
        "goals_for": 64, "goals_against": 38,
        "home_gf": 35, "home_ga": 16, "home_games": 17,
        "form": [1, 1, 1, 0.5, 1],   # last 5: W=1, D=0.5, L=0
        "elo": 1950,
        "xg_for": 2.08, "xg_against": 1.21,
    },
    "ARS": {
        "played": 33, "won": 20, "drawn": 7, "lost": 6,
        "goals_for": 68, "goals_against": 33,
        "away_gf": 30, "away_ga": 15, "away_games": 16,
        "form": [1, 1, 0.5, 1, 1],
        "elo": 1930,
        "xg_for": 2.15, "xg_against": 1.05,
    },
}

LEAGUE_AVG_GOALS = 2.65  # PL 2025-26 avg goals per game

# ─────────────────────────────────────────────
# 3. ATTACK / DEFENCE STRENGTH
# ─────────────────────────────────────────────
def attack_defence_strength(home_team, away_team, stats):
    home = stats[home_team]
    away = stats[away_team]

    home_attack  = (home["home_gf"] / home["home_games"]) / (LEAGUE_AVG_GOALS / 2)
    home_defence = (home["home_ga"] / home["home_games"]) / (LEAGUE_AVG_GOALS / 2)
    away_attack  = (away["away_gf"] / away["away_games"]) / (LEAGUE_AVG_GOALS / 2)
    away_defence = (away["away_ga"] / away["away_games"]) / (LEAGUE_AVG_GOALS / 2)

    # Expected goals (Dixon-Coles-style)
    home_lambda = home_attack * away_defence * (LEAGUE_AVG_GOALS / 2) * HOME_ADVANTAGE_FACTOR
    away_lambda = away_attack * home_defence * (LEAGUE_AVG_GOALS / 2)

    return round(home_lambda, 3), round(away_lambda, 3)

# ─────────────────────────────────────────────
# 4. POISSON PROBABILITY
# ─────────────────────────────────────────────
def match_probabilities(lam_home, lam_away, max_goals=MAX_GOALS):
    prob_matrix = {}
    for h, a in product(range(max_goals + 1), repeat=2):
        prob_matrix[(h, a)] = poisson_prob(lam_home, h) * poisson_prob(lam_away, a)

    home_win = sum(p for (h, a), p in prob_matrix.items() if h > a)
    draw     = sum(p for (h, a), p in prob_matrix.items() if h == a)
    away_win = sum(p for (h, a), p in prob_matrix.items() if h < a)

    top5 = sorted(prob_matrix.items(), key=lambda x: x[1], reverse=True)[:5]
    return home_win, draw, away_win, top5

# ─────────────────────────────────────────────
# 5. ELO EXPECTED SCORE
# ─────────────────────────────────────────────
def elo_expected(elo_a, elo_b, home_bonus=50):
    return 1 / (1 + 10 ** ((elo_b - elo_a - home_bonus) / 400))

# ─────────────────────────────────────────────
# 6. H2H SUMMARY (MCI vs ARS hardcoded data)
# ─────────────────────────────────────────────
def mci_ars_h2h_summary():
    mci_w  = sum(1 for _, v, mg, ag in H2H if mg > ag)
    draws  = sum(1 for _, v, mg, ag in H2H if mg == ag)
    ars_w  = sum(1 for _, v, mg, ag in H2H if mg < ag)
    mci_gf = sum(mg for _, v, mg, ag in H2H)
    ars_gf = sum(ag for _, v, mg, ag in H2H)
    return mci_w, draws, ars_w, mci_gf, ars_gf

# ─────────────────────────────────────────────
# 7. COMBINED PREDICTION
# ─────────────────────────────────────────────
def predict(home="MCI", away="ARS"):
    print("=" * 58)
    print(f"  MATCH PREDICTION: {home} vs {away}  (Home: {home})")
    print(f"  Premier League 2025-26  |  Date: 19 Apr 2026")
    print("=" * 58)

    # Base Poisson lambdas
    lam_h, lam_a = attack_defence_strength(home, away, STATS)

    # xG blended (50/50 with attack-defence model)
    xg_h = (lam_h + STATS[home]["xg_for"] * 0.95) / 2
    xg_a = (lam_a + STATS[away]["xg_for"] * 0.85) / 2  # away xg penalty

    print(f"\n  Expected Goals (blended xG model):")
    print(f"    {home}: {xg_h:.2f}   |   {away}: {xg_a:.2f}")

    hw, dr, aw, top5 = match_probabilities(xg_h, xg_a)
    over25 = sum(poisson_prob(xg_h, h) * poisson_prob(xg_a, a)
                 for h in range(MAX_GOALS + 1) for a in range(MAX_GOALS + 1) if h + a > 2)

    # ELO adjustment
    elo_home = elo_expected(STATS[home]["elo"], STATS[away]["elo"])
    hw_final = hw * POISSON_BLEND + elo_home * ELO_BLEND
    aw_final = aw * POISSON_BLEND + (1 - elo_home) * ELO_BLEND
    dr_final = max(0, 1 - hw_final - aw_final)

    # Form adjustment
    form_h     = form_score(STATS[home]["form"])
    form_a     = form_score(STATS[away]["form"])
    form_delta = (form_h - form_a) * FORM_IMPACT
    hw_final   = min(1, hw_final + form_delta)
    aw_final   = max(0, aw_final - form_delta)
    dr_final   = max(0, 1 - hw_final - aw_final)
    _tot = hw_final + dr_final + aw_final
    hw_final /= _tot; dr_final /= _tot; aw_final /= _tot

    print(f"\n  Win Probabilities:")
    print(f"    {home} Win : {hw_final*100:5.1f}%  {'#' * int(hw_final*40)}")
    print(f"    Draw     : {dr_final*100:5.1f}%  {'#' * int(dr_final*40)}")
    print(f"    {away} Win : {aw_final*100:5.1f}%  {'#' * int(aw_final*40)}")

    print(f"\n  Top 5 Most Likely Scorelines ({home}-{away}):")
    for (h, a), p in top5:
        result = "W" if h > a else ("D" if h == a else "L")
        print(f"    {h}-{a}  [{result}]  {p*100:4.1f}%  {'#' * int(p * 200)}")

    # H2H
    mci_w, draws, ars_w, mci_gf, ars_gf = mci_ars_h2h_summary()
    print(f"\n  Head-to-Head (last {len(H2H)} PL meetings):")
    print(f"    MCI: {mci_w}W  |  Draw: {draws}  |  ARS: {ars_w}W")
    print(f"    Goals: MCI {mci_gf} - {ars_gf} ARS")

    # Form
    mci_str = " ".join(FORM_MAP[x] for x in STATS[home]["form"])
    ars_str = " ".join(FORM_MAP[x] for x in STATS[away]["form"])
    print(f"\n  Last 5 Games:")
    print(f"    {home}: {mci_str}  (score: {form_score(STATS[home]['form']):.2f})")
    print(f"    {away}: {ars_str}  (score: {form_score(STATS[away]['form']):.2f})")

    # Verdict
    print(f"\n  VERDICT:")
    if hw_final > aw_final and hw_final > dr_final:
        fav, prob = home, hw_final
    elif aw_final > hw_final and aw_final > dr_final:
        fav, prob = away, aw_final
    else:
        fav, prob = "Draw", dr_final

    top_score = top5[0][0]
    print(f"    Predicted outcome : {fav} ({prob*100:.1f}%)")
    print(f"    Most likely score : {top_score[0]}-{top_score[1]}")
    print(f"    Over 2.5 goals    : {over25*100:.1f}%")
    print(f"    Both teams score  : {(1 - poisson_prob(xg_h,0)) * (1 - poisson_prob(xg_a,0))*100:.1f}%")
    print("=" * 58)
    print("  * Model: Poisson + xG + ELO + Form blend")
    print("  * Based on 2025-26 stats up to matchday 33")
    print("=" * 58)


if __name__ == "__main__":
    predict("MCI", "ARS")
