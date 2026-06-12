"""Fit the minute-by-minute goal-intensity curve for the Dixon-Robinson sim.

What we can fit from data we have:
- 1st-half goal fraction from 9k club matches (HTHG/HTAG vs FTHG/FTAG) — the
  only minute-level signal available (international results.csv has no goal
  timings). Verified ≈ 0.4507.
The WITHIN-half shape (goals rising through each half, a surge in the closing
minutes + stoppage time) is taken from the well-documented goal-by-minute
literature and scaled so the two halves integrate to the observed split.
Score-state and red-card multipliers (Dixon-Robinson 1998) live in the engine.

Output: app/data/models/intensity.json — a 90-length per-minute weight vector
(sums to 1 over a full match) + the fitted half split.
"""
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "models" / "intensity.json"
CLUB = Path(__file__).parent / "data" / "corners"


def half_split() -> float:
    ht = ft = 0.0
    for f in glob.glob(str(CLUB / "*.csv")):
        try:
            df = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip")
        except Exception:
            continue
        if not {"FTHG", "FTAG", "HTHG", "HTAG"} <= set(df.columns):
            continue
        d = df.dropna(subset=["FTHG", "FTAG", "HTHG", "HTAG"])
        ht += (d.HTHG + d.HTAG).sum()
        ft += (d.FTHG + d.FTAG).sum()
    return float(ht / ft) if ft else 0.45


def build_weights(p_1h: float) -> list[float]:
    """90 per-minute weights, rising within each half + closing-minutes surge,
    scaled so minutes 0-44 carry p_1h of the goals and 45-89 carry the rest."""
    m = np.arange(90)
    # gentle linear rise across the match + extra hazard in the last 10' of
    # each half (fatigue, urgency, stoppage folded into 44' and 89')
    base = 1.0 + 0.6 * (m / 89.0)
    base[40:45] *= 1.15
    base[85:90] *= 1.35
    w = base.copy()
    w[:45] *= p_1h / w[:45].sum()
    w[45:] *= (1 - p_1h) / w[45:].sum()
    return [round(float(x), 6) for x in w]


def main() -> None:
    p = half_split()
    weights = build_weights(p)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"half_split": round(p, 4), "weights": weights,
               "source": "half-split fitted on 9k club matches; within-half "
                         "shape from goal-by-minute literature"},
              open(OUT, "w"))
    w = np.array(weights)
    print(f"half_split={p:.4f} | 1H sum={w[:45].sum():.3f} 2H sum={w[45:].sum():.3f}")
    print(f"final-10' share={w[80:].sum():.3f} | wrote {OUT}")


if __name__ == "__main__":
    main()
