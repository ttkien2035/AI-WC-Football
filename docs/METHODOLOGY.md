# Prediction Methodology

*AI World Cup 2026 Predictor — a research testbed for football-prediction
algorithms (academic, not a betting product).*

This document records **how every prediction factor is derived** and, crucially,
**which are fitted from data versus which remain bounded literature priors**.
The guiding rule is: *don't assume a coefficient if it can be measured; if it
can't be measured cleanly, keep it small, bounded, and audited live.*

---

## 1. Pipeline architecture

Everything converges on one quantity — **λ (expected goals per team)** — from
which all goal-derived targets are read off a single distribution so they can
never contradict each other:

```
 Elo (live) ─┐
 Seeding/squad prior (±Elo, decays as a team plays) ─┤
 Key absences (−Elo) ─┤
 Style → W/D/L supremacy (±Elo, fitted-bounded) ─┴─→ effective Elo ─→ λ (fitted Poisson rates)
                                                                        │
 ML ensemble (XGB+LR) → W/D/L ──────────────────────────────────────────┤  meta-calibrated blend
 Market odds → implied probs ────────────────────────────────────────────┤
                                                                        ▼
 Style / Context / Venue → λ multipliers (bounded) ────────────────→  adjusted λ
                                                                        ▼
 O/U 2.5 + BTTS trained heads  ──→  reconcile_matrix (IPF)
                                                                        ▼
        ONE score matrix → W/D/L · scorelines · O/U · BTTS · Asian lines · corners
                                                                        ▼
        Dixon-Robinson minute simulation → scenarios (comeback, late goal, volatility)
```

The headline always comes from the reconciled matrix; the minute simulation is
additive (scenarios only), validated separately.

---

## 2. Factor classification

| Model / factor | Status | Source | Live validation |
|---|---|---|---|
| Goal λ, W/D/L, scorelines | **ML-fitted** | 49k internationals + 9k club matches | RPS 0.1605 holdout (vs 0.1701 heuristic) |
| O/U 2.5, BTTS | **ML-fitted** trained heads + meta-blend | same | Brier holdout |
| Corners: crosses→corners | **Data-fitted** | StatsBomb, 314 intl matches | corners scorecard |
| Corners: base level | **Data-fitted** (9.07) + adapts to WC-2026 | StatsBomb + in-tournament | corners scorecard |
| Style → total goals | **Measured & shrunk** | StatsBomb, 314 matches | factor scorecard |
| Style → W/D/L supremacy | **Measured & shrunk** | StatsBomb, 314 matches | factor scorecard |
| Sim score-state response | **Data-fitted** (strength-controlled) | StatsBomb minute events | sim-timing scorecard |
| Seeding / squad prior | Tiered + decaying shrink | FIFA ranks + ClubElo | factor scorecard |
| Venue altitude / heat | **Literature prior** (bounded) | no clean fit dataset | factor scorecard |
| Context (dead rubber, biscotto, knockout) | **Situational prior** (bounded) | rare, hard to label | factor scorecard |
| Manager → corners | **Dropped** | data-contradicted | — |

---

## 3. Fitted coefficients (with the data behind them)

All fits run on **StatsBomb open event data** for 6 modern men's national-team
tournaments — **WC 2022, WC 2018, Euro 2024, Euro 2020, Copa América 2024,
AFCON 2023** (314 matches, 628 team-match rows). Scripts:
`backend/ml/statsbomb_fit.py`, `statsbomb_style_fit.py`, `statsbomb_sim_fit.py`.
Outputs: `backend/app/data/models/{corners,style,sim}_fit.json` — read by the
serving engine at runtime, so re-running a fit auto-updates production.

### 3.1 Corners (`corners_fit.json`)

Univariate correlation with corners-for (628 team-matches):

| Feature | r |
|---|---|
| shots | +0.579 |
| crosses | +0.528 |
| possession | +0.507 |
| xG | +0.269 |
| **pressures** | **−0.175** |

Poisson GLM `corners ~ crosses + possession + shots` — all p < 0.01.

**Changes made:**
- crosses→corner ratio **0.28 (hand-set) → 0.389 (fitted)**.
- base corners **9.67 (club-leaning) → 9.07 (intl mean)**, then adaptively
  shrunk toward observed WC-2026 corners (`n/(n+20)`).
- **Dropped** the `high_press +0.3` earn bump and the manager corner bumps —
  pressing correlates *negatively* (−0.18), contradicting the assumption.
- Kept possession/wing-play (data-supported, +0.51/+0.53).

### 3.2 Style factors (`style_fit.json`)

Tested whether playing style moves outcomes **beyond what shot volume / Elo
already capture** (314 matches):

- **Total goals**: controlling for shots, possession-balance (p=0.29) and
  pressing (p=0.38) are **both insignificant** — style adds ~nothing to totals
  beyond shots (which λ already encodes).
- **Possession → win**: r = +0.05 (p=0.37). Teams dominating possession win
  50% vs 37% when ceding it — a weak, noisy edge.

**Changes made (shrink toward measured effect, don't disable — keep a small
literature prior, audit live):**
- `style_total_max` **0.06 → 0.03**.
- style→W/D/L supremacy cap **±18 → ±10 Elo**.

### 3.3 Simulation score-state (`sim_fit.json`) — a methodological lesson

The naive rate-by-state is **confounded**: strong teams both lead *and* keep
scoring, so leading teams *look* like they score more (×1.19 raw) — that is
selection, not the causal "ease-off". We isolate the causal effect with a
**strength-controlled Poisson GLM** (offset = team's match xG per minute):

| State | Naive (confounded) | **Controlled (causal)** | p |
|---|---|---|---|
| Leading +1 | ×1.19 | ×1.15 | 0.18 (n.s.) |
| Leading +2 | ×1.81 | ×1.44 | 0.003 |
| **Trailing −1** | ×1.19 | **×1.35** | 0.003 |
| **Trailing −2** | ×1.05 | **×1.47** | 0.014 |

**Findings:** the textbook "leading team eases off ×0.88" is **not supported**
(1-goal lead n.s.); a trailing team **genuinely pushes and scores more** than
its own baseline (+0.35 / +0.47, significant).

**Changes made:** replaced the symmetric hand-set `sim_state_effect=0.12` with
the fitted table; the **leading** side is capped at ≤1.0 (its positive estimate
is residual momentum confound — a team 2-up is having an exceptional game beyond
its season xG), the **trailing** push is adopted where significant.

> This is the difference between *measuring a number* and *measuring it
> scientifically*: a raw conditional rate can be worse than no adjustment if it
> encodes a confound.

---

## 4. What is NOT fitted, and why (honest limitations)

- **Venue altitude / heat** — no clean dataset in hand (WC 2022 was single-venue
  Qatar; altitude needs cross-venue data with goal counts). Kept as a bounded
  literature-direction prior (altitude → more goals, open-roof heat → fewer),
  validated live by the factor scorecard. A future fit would source club-league
  matches at altitude (Denver / Mexico City / La Paz).
- **Context** (dead rubber, biscotto, knockout caution) — situational and rare;
  no large labelled historical set. Bounded, env-tunable, scorecard-audited.
- **O/U / BTTS mechanism features** — possession/crossing are not in the 49k+9k
  training set (only in the 314 StatsBomb matches, too few to beat the baseline),
  so the heads stay strength/form-based. Style enters O/U through the (now
  shrunk) λ factor instead.

We deliberately **do not fabricate** coefficients where data can't support them.

---

## 5. Self-correction loop

Every bounded factor is graded on real results, continuously:

- **Pre-match snapshot** stores, before kickoff, the prediction *and* a
  per-factor counterfactual ("what would the O/U / W-D-L be without factor X").
- **Factor scorecard** (admin Pipeline) compares with/without on the actual
  result (Brier for O/U factors, RPS for W/D/L factors) → verdict
  helping / hurting / neutral. A factor that hurts can be disabled by an env
  flag with no code change.
- **Corners scorecard** + **sim-timing scorecard** validate corner O/U and the
  simulation's scenario probabilities (late goal, comeback, result-flips-vs-HT)
  against actual minute-by-minute outcomes.
- **Adaptive corners base** shrinks the prior toward observed WC-2026 corners as
  matches accumulate (conservative, so a few cagey openers can't skew it).
- Online Elo updates after every match; ML ensemble retrains nightly.

Fitted coefficients live in JSON artifacts read at serving time, so re-running
the fit scripts after the tournament updates production with no code change.

---

## 6. Reproducing the fits

```bash
cd backend
python -m ml.statsbomb_fit        # corners: download events, correlations, Poisson fit
python -m ml.statsbomb_style_fit  # style → totals / results effect sizes
python -m ml.statsbomb_sim_fit    # strength-controlled score-state multipliers
python -m ml.train                # WDL + O/U + BTTS ensemble (49k+9k matches)
python -m ml.corners              # club-data corners byproducts (NB dispersion)
python -m ml.squad_strength       # squad-strength prior (Wikipedia squads × ClubElo)
```

Event JSONs are cached under `backend/ml/data/statsbomb/`; re-runs are instant.
StatsBomb open data is used under their license — attribution: StatsBomb.

---

## 7. Data sources

- **football-data.org v4** — fixtures, standings, results (no venue/minute, free tier).
- **LiveScore** (unofficial JSON) — live minute, score, incidents, statistics
  (possession, shots, crosses, corners), shot map.
- **StatsBomb open data** — event-level data for the 6 tournaments above; the
  basis for all corner/style/simulation fits.
- **eloratings.net** — World Football Elo.
- **ClubElo** (api.clubelo.com) — club strength for the squad prior.
- **martj42/international_results** (49k matches) + **football-data.co.uk**
  (9k club matches) — ML ensemble training.
- **The Odds API** — bookmaker odds for market comparison / value.

All predictions are statistical estimates for research and reference — not
betting advice.


## 8. Negative result: graph / style embeddings (tested, not adopted)

We tested whether a **passing-network style embedding** (per-team fingerprint
of pass length, forward/final-third/cross/long-ball ratios, pressing, possession
— from the 314 StatsBomb matches) carries predictive signal **beyond raw team
strength**, via leave-one-tournament-out CV (`ml/style_embed_proto.py`):

| | strength only | + style embedding |
|---|---|---|
| Outcome RPS | 0.2376 | 0.2381 (worse +0.0005) |
| Total-goals MAE | 1.645 | 1.654 (worse +0.008) |

**Verdict: no incremental value at this scale** — it slightly *hurts* (added
noise). This is consistent with §3.2 (style adds nothing to totals beyond shots)
and with the football literature: outcomes are strength-dominated and high
variance, so a GNN / graph-embedding layer for outcome/totals would face the
same low ceiling with greater overfitting risk. The one genuinely useful
graph — the team-result network — is **already exploited by Elo / pi-ratings**
(rating propagation over the head-to-head graph). We therefore keep the
calibrated ensemble and did **not** wire graph features into production. The
prototype is retained as a reproducible negative result.
