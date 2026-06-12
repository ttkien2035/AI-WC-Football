"""Dataset + chronological feature engineering for the ML ensemble.

Source: martj42/international_results (public CSV, 49k+ matches 1872-2026).
All rating features (Elo, pi-ratings, rolling form) are computed strictly
chronologically — a match only sees information available before kickoff.
"""
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

DATA_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CACHE = Path(__file__).parent / "data" / "results.csv"

ELO_HOME_ADV = 60.0

# K factor by tournament importance (eloratings.net convention)
def k_factor(tournament: str) -> float:
    t = tournament.lower()
    if "fifa world cup" in t and "qualification" not in t:
        return 60.0
    if any(x in t for x in ("euro", "copa am", "africa cup", "asian cup", "gold cup")) \
            and "qualification" not in t:
        return 50.0
    if "qualification" in t or "nations league" in t:
        return 40.0
    if "friendly" in t:
        return 20.0
    return 30.0


def importance(tournament: str) -> int:
    t = tournament.lower()
    if "fifa world cup" in t and "qualification" not in t:
        return 3
    if any(x in t for x in ("euro", "copa am", "africa cup", "asian cup", "gold cup")) \
            and "qualification" not in t:
        return 2
    if "friendly" in t:
        return 0
    return 1


def goal_mult(gd: int) -> float:
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


def load_results() -> pd.DataFrame:
    if CACHE.exists():
        df = pd.read_csv(CACHE)
    else:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        df = pd.read_csv(DATA_URL)
        df.to_csv(CACHE, index=False)
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"] = df["neutral"].astype(bool)
    return df.sort_values("date").reset_index(drop=True)


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Walk matches chronologically; emit pre-match features per match and the
    final post-walk team state (used at serving time for current ratings)."""
    elo: dict[str, float] = defaultdict(lambda: 1500.0)
    # pi-ratings (Constantinou & Fenton): separate home/away ratings
    pi_h: dict[str, float] = defaultdict(float)
    pi_a: dict[str, float] = defaultdict(float)
    LAM, GAM = 0.06, 0.5
    recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))  # (pts, gf, ga)

    rows = []
    for r in df.itertuples(index=False):
        h, a = r.home_team, r.away_team
        eh, ea = elo[h], elo[a]
        adv = 0.0 if r.neutral else ELO_HOME_ADV

        def roll(team, n):
            q = list(recent[team])[-n:]
            if not q:
                return 1.0, 1.3, 1.3   # priors: pts/game, gf, ga
            return (sum(x[0] for x in q) / len(q),
                    sum(x[1] for x in q) / len(q),
                    sum(x[2] for x in q) / len(q))

        ph5, gf5h, ga5h = roll(h, 5)
        pa5, gf5a, ga5a = roll(a, 5)

        # expected goal diff from pi-ratings (home uses home rating, away its away rating)
        pi_diff = (pi_h[h] - pi_a[a])

        rows.append({
            "date": r.date, "home": h, "away": a,
            "elo_h": eh, "elo_a": ea, "elo_diff": eh + adv - ea,
            "pi_diff": pi_diff,
            "form5_diff": ph5 - pa5,
            "gf5_diff": gf5h - gf5a,
            "ga5_diff": ga5h - ga5a,
            # goal-market features (O/U & BTTS heads): tempo + attack/defence levels
            "elo_sum": eh + ea,
            "gf5_sum": gf5h + gf5a, "ga5_sum": ga5h + ga5a,
            "gf5_min": min(gf5h, gf5a), "ga5_max": max(ga5h, ga5a),
            "neutral": int(r.neutral), "importance": importance(r.tournament),
            "gh": r.home_score, "ga": r.away_score,
            "outcome": 0 if r.home_score > r.away_score else (1 if r.home_score == r.away_score else 2),
            "over25": int(r.home_score + r.away_score > 2),
            "btts": int(r.home_score > 0 and r.away_score > 0),
        })

        # ---- updates (post-match) ----
        gd = r.home_score - r.away_score
        we = 1.0 / (1.0 + 10 ** (-(eh + adv - ea) / 400.0))
        res = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        k = k_factor(r.tournament) * goal_mult(gd)
        elo[h] = eh + k * (res - we)
        elo[a] = ea - k * (res - we)

        # pi-rating update (simplified two-rating scheme)
        exp_gd = pi_diff
        err = gd - exp_gd
        psi = 2.0 * np.log10(1.0 + abs(err)) * np.sign(err)
        pi_h[h] += LAM * psi
        pi_a[h] += LAM * GAM * psi
        pi_a[a] -= LAM * psi
        pi_h[a] -= LAM * GAM * psi

        recent[h].append((3 if gd > 0 else (1 if gd == 0 else 0), r.home_score, r.away_score))
        recent[a].append((3 if gd < 0 else (1 if gd == 0 else 0), r.away_score, r.home_score))

    feat = pd.DataFrame(rows)
    state = {
        team: {
            "elo": elo[team], "pi_home": pi_h[team], "pi_away": pi_a[team],
            "form5_pts": float(np.mean([x[0] for x in list(recent[team])[-5:]] or [1.0])),
            "gf5": float(np.mean([x[1] for x in list(recent[team])[-5:]] or [1.3])),
            "ga5": float(np.mean([x[2] for x in list(recent[team])[-5:]] or [1.3])),
        }
        for team in set(df["home_team"]) | set(df["away_team"])
    }
    return feat, state


FEATURES = ["elo_diff", "pi_diff", "form5_diff", "gf5_diff", "ga5_diff", "neutral", "importance"]
# O/U & BTTS heads (research: tempo=elo_sum, attack/defence levels, weakest
# attack & strongest defence drive BTTS, stage importance drives caginess)
MARKET_FEATURES = ["elo_sum", "elo_diff", "gf5_sum", "ga5_sum",
                   "gf5_min", "ga5_max", "neutral", "importance"]

# dataset team names for the 48 WC TLAs (only where name differs from static_data)
DATASET_NAMES = {
    "USA": "United States", "KOR": "South Korea", "IRN": "Iran",
    "CIV": "Ivory Coast", "CZE": "Czech Republic", "BIH": "Bosnia and Herzegovina",
    "CPV": "Cape Verde", "COD": "DR Congo", "CUW": "Curaçao", "TUR": "Turkey",
    "URY": "Uruguay", "RSA": "South Africa", "NZL": "New Zealand",
    "KSA": "Saudi Arabia", "ALG": "Algeria", "MAR": "Morocco", "TUN": "Tunisia",
    "EGY": "Egypt", "SEN": "Senegal", "GHA": "Ghana", "JOR": "Jordan",
    "IRQ": "Iraq", "UZB": "Uzbekistan", "QAT": "Qatar", "PAN": "Panama",
    "HAI": "Haiti", "PAR": "Paraguay", "ECU": "Ecuador", "COL": "Colombia",
    "MEX": "Mexico", "CAN": "Canada", "AUS": "Australia", "JPN": "Japan",
    "ARG": "Argentina", "BRA": "Brazil", "ESP": "Spain", "FRA": "France",
    "ENG": "England", "GER": "Germany", "POR": "Portugal", "NED": "Netherlands",
    "BEL": "Belgium", "CRO": "Croatia", "SUI": "Switzerland", "AUT": "Austria",
    "SWE": "Sweden", "NOR": "Norway", "SCO": "Scotland",
}
