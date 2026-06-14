# A Measure-First Probabilistic Engine for Football Prediction

*AI World Cup 2026 Predictor — a research testbed for football-prediction
algorithms (academic; not a betting product).*

## Abstract

We describe the prediction methodology of an open World-Cup-2026 forecasting
system. All match targets — match result (1X2), exact score, Asian handicap and
Over/Under (goals and corners) — are read from **one reconciled bivariate goal
distribution**, so they are mutually consistent by construction. Team strength
is an ML ensemble (RPS 0.1605 on a 1,313-match hold-out); on top of it sit a set
of **bounded factor priors** whose *direction* is taken from literature but whose
*magnitude* is either fitted from data or held small and audited live. We adopt
a single discipline — **measure first: a factor is wired in only if it beats a
strength baseline on a hold-out; otherwise it is shrunk, dropped, or recorded as
a null result.** Following it we (i) fitted corner coefficients from 314–5,232
StatsBomb matches, (ii) calibrated Over/Under, (iii) estimated the causal
score-state effect with a strength-controlled GLM, (iv) blended Dixon-Coles
attack/defence ratings into the goal rate, and (v) added an xG-based
in-tournament rating update — while explicitly *rejecting* rest/fatigue, graph
embeddings, tactical counter-matchups and player-style features that did not
beat the baseline. Every coefficient lives in a JSON artifact read at serving
time and is graded by live scorecards.

**Guiding rule.** *Don't assume a coefficient if it can be measured; if it
can't be measured cleanly, keep it small, bounded, and audited live.*

---

## 1. Introduction

Football outcomes are strength-dominated and high-variance, which sets a low
ceiling on predictability and a high bar for any new feature. The system is
built so that (a) every user-facing market derives from a single coherent
distribution, and (b) every modelling choice is testable and reversible. This
document records each factor, the experiment behind it, and — importantly —
which appealing ideas were *refuted* by the data.

---

## 2. Data

| Source | Role | Notes |
|---|---|---|
| football-data.org v4 | fixtures, standings, results | free tier; no venue/minute |
| LiveScore (unofficial) | live minute, score, incidents, stats, shot map | possession, shots, crosses, corners |
| **StatsBomb open data** | event-level (passes, shots, xG, pressures) | basis for all corner/style/sim/att-def fits |
| eloratings.net | World Football Elo | live + static snapshot |
| ClubElo | club strength | squad-strength prior |
| martj42/international_results | 49k internationals | ensemble + Dixon-Coles training |
| football-data.co.uk | 9k club matches (corners/shots/odds) | corners dispersion, ensemble |
| The Odds API | bookmaker h2h/totals/spreads | market comparison / value |

The StatsBomb **men's** event corpus used for fits spans WC 2018/2022,
Euro 2020/2024, Copa América 2024, AFCON 2023 and full club seasons
(PL/La Liga/Ligue 1/Serie A 2015-16, Bundesliga, La Liga 2004-21, …) —
**5,232 team-match rows** (628 international, 4,604 club).

---

## 3. Methodology and algorithms

### 3.1 Pipeline

Everything converges on a per-team expected-goals rate **λ**, from which one
score matrix is built and reconciled to the headline marginals:

```
 Elo (live) ─┐
 Seeding / squad prior  (±Elo, decays as a team plays) ─┤
 Key absences           (−Elo) ─┤
 Style → W/D/L supremacy (±Elo, fitted-bounded) ─┤
 xG-form nudge          (±Elo, in-tournament) ─┴─→ effective Elo ─┐
                                                                  ├─→ λ
 Dixon-Coles attack/defence ──────────────────────────────────────┘  (blend)
        │
 ML ensemble (XGB+LR) → W/D/L ─┐
 Market odds → implied probs ──┼─ meta-calibrated blend ─→ headline W/D/L, O/U
 Style/Context/Venue → λ × (bounded) ─┘
        ▼
 reconcile_matrix (IPF)  →  ONE score matrix
        ▼
 W/D/L · scorelines · Asian O/U (goals & corners) · Asian handicap · BTTS
        ▼
 Dixon-Robinson minute simulation → scenarios (comeback, late goal, volatility)
```

The headline always comes from the reconciled matrix; the minute simulation is
additive (scenarios only) and validated separately.

### 3.2 Algorithm 1 — Consistency by iterative proportional fitting

```
reconcile_matrix(M, p_wdl, p_over, p_btts):
  repeat until converged:
     for each partition (home/draw/away), (over/under 2.5), (btts/not):
        scale matrix cells in each region so its mass = the target marginal
     renormalise M
  return M            # W/D/L, O/U, BTTS, scorelines now read from one M
```

IPF tilts the Poisson/Dixon-Coles matrix the minimal (KL) amount needed to match
the blended headline marginals, so no two displayed markets can contradict.

### 3.3 Algorithm 2 — Goal rate (Elo gap ⊕ attack/defence)

```
λ_elo_h = exp(a + b·Δelo/100),   λ_elo_a = exp(a − b·Δelo/100)
λ_dc_h  = exp(c + adv + att_h + def_a),  λ_dc_a = exp(c + att_a + def_h)
λ = (1−w)·λ_elo + w·λ_dc          # w = goal_dc_weight = 0.5
M = DixonColes(λ_h, λ_a, ρ);  then ×ou_total_scale for O/U lines
```

The Elo gap is symmetric; the Dixon-Coles term injects the **asymmetric
attack-vs-defence** structure a single rating cannot express (§4.4).

### 3.4 Algorithm 3 — Bounded, decaying priors

Seeding, squad-strength and xG-form are Elo offsets that shrink with confidence:

```
δ = clip(scale · signal, ±cap) · n/(n+k)        # n = matches played
effective_elo = base_elo + Σ δ                  # all priors are additive in Elo
```

Direction from literature/theory; `scale`/`cap` bounded; `n/(n+k)` makes a thin
sample unable to dominate. Each δ is counterfactually graded by the scorecard.

### 3.5 Algorithm 4 — Strength-controlled causal estimation

To estimate a *within-match* effect (e.g. the score-state response) free of the
selection confound that strong teams both lead and score, we fit a Poisson GLM
with the team's own expected rate as an **offset**:

```
goals_minute ~ Poisson;  log μ = β·state + offset(log team_xg_per_min)
multiplier(state) = exp(β_state)      # causal, net of team quality
```

---

## 4. Experiments and results

All fits run offline (`backend/ml/*.py`) and write JSON artifacts read at serving
time, so re-running a script updates production with no code change.

### 4.1 Corner determinants

![Fig 1](figures/corner_determinants.png)

On 628 international team-matches, corners-for correlate with shots (r=0.58),
crosses (0.53), possession (0.51), xG (0.27) and — counter-intuitively —
**negatively with pressing** (−0.18). A Poisson GLM `corners ~ crosses +
possession + shots` is significant on all terms (p<0.01). **Fitted:**
crosses→corner ratio **0.389** (was a hand-set 0.28); base **9.07** corners/game
(was a club-leaning 9.67), then adaptively shrunk toward the observed WC-2026
mean. The old `high_press` and manager corner bumps were **dropped** (pressing
is negative). On the enriched 5,232-match set the intl coefficients are
confirmed (club runs higher: 0.429 / 10.06); **box entries** (passes into the
box) are the strongest corner signal (r=0.67) but are event-level and not
available live, so they inform — not serve — the model.

### 4.2 Goal distribution and Over/Under calibration

![Fig 2](figures/total_dispersion.png)
![Fig 3](figures/ou_reliability.png)

Total goals are **over-dispersed** vs a single Poisson (Var/Mean≈1.29, fatter
0–1 and 7+ tails). The raw Elo-gap matrix therefore **over-predicts Over** by
~+8.5pp uniformly across deciles (Fig 3). The trained O/U head is, by contrast,
isotonic-calibrated (hold-out bias +0.4pp). **Adopted (two levers):** lean the
O/U/BTTS blend on the head (`ou_head_weight=0.95`); scale the Asian-line matrix
total by `ou_total_scale=0.94` so all lines calibrate (main lines within ±0.5pp,
re-confirmed after the att/def blend). Asian handicap is read from the same
reconciled matrix (margin calibration within ±3pp on 8k hold-out).

### 4.3 Score-state simulation (a confounding lesson)

![Fig 4](figures/sim_state.png)

Naively, leading teams *appear* to score more (×1.19 at +1) — but that is
selection (strong teams lead). The strength-controlled GLM (Alg. 4) shows the
textbook "leading team eases off ×0.88" is **not supported** (lead +1 ×1.15,
p=0.18), while a **trailing team genuinely pushes** (−1 ×1.35, −2 ×1.47, p<0.01).
The minute simulator now uses the fitted table; the leading side is capped ≤1.0
(residual momentum confound), the trailing push adopted where significant.

### 4.4 Attack/defence λ — the forward-vs-defender matchup

![Fig 5](figures/attdef.png)

Hypothesis: the single Elo gap can't tell a great-attack/weak-defence team from
a balanced one. The Dixon-Coles att/def ratings express that asymmetry (they
lose to Elo for 1X2, so weight 0 there) — but do they help the *goal* targets?
Hold-out (2,492 recent intl matches):

| λ source | O/U Brier | O/U bias | total MAE | score log-loss |
|---|---|---|---|---|
| Elo-gap | 0.2512 | +0.084 | 1.477 | 2.906 |
| att/def (DC) | 0.2522 | −0.023 | 1.428 | 2.966 |
| **blend 50/50** | **0.2440** | +0.036 | **1.421** | **2.887** |

The blend wins all three goal metrics. **Adopted:** `λ = 0.5·Elo + 0.5·att/def`
(48/48 WC teams covered); 1X2 stays the Elo ensemble.

### 4.5 In-tournament xG-form

![Fig 6](figures/xgform.png)

Rolling **xG-form predicts the next result better than goals-form** (3,742 obs:
solo R² 0.113 vs 0.097, +17%; joint coef 0.61 vs 0.20). xG is the less-noisy
strength signal. **Adopted** as a bounded in-tournament Elo nudge: a team
out-performing its scoreline on xG (unlucky) is rated up, an over-performer down
(±25 Elo, decaying n/(n+2)), feeding every goal target and scorecard-audited.

### 4.6 Style factors (shrunk to measured effect)

On 314 matches, controlling for shots, neither possession-balance (p=0.29) nor
pressing (p=0.38) adds to total goals; possession dominance barely predicts wins
(r=0.05). The style λ-multiplier was halved (`style_total_max` 0.06→0.03) and the
style→W/D/L supremacy cap cut (±18→±10 Elo) — kept small, audited live.

---

## 5. Negative results (tested, rejected)

A research record is incomplete without the "no"s. Each was measured, not
assumed:

| Hypothesis | Test | Verdict |
|---|---|---|
| Graph / passing-network style embedding | leave-one-tournament-out CV | RPS 0.2376→0.2381 (worse) — no gain beyond strength |
| Tactical counter-matchup amplifies corners | wide-attack × opp-concede interaction | coef −0.0037 (sub-additive), not amplifying |
| Rest / fixture congestion → goals/result | 1,820 matches, strength-controlled | p=0.15 / 0.86 — no effect |
| shots-in-box (shotmap) proxy for box entries | 5,232-match GLM | +AIC 22 vs box-entry's 817 — negligible |
| Style/tactics → 1X2 beyond strength | §4.6 | weak, shrunk not added |
| Player cohesion / "found out" / solo breakthrough | — | not validatable (no labels); variance, not signal |

The only genuinely useful graph — the team-result network — is already exploited
by Elo/pi-rating propagation.

---

## 6. Self-correction loop

- **Pre-match snapshots** store, before kickoff, the prediction *and* per-factor
  counterfactuals ("the O/U / W-D-L *without* factor X").
- **Factor scorecard** grades each bounded factor with/without on the actual
  result (Brier for O/U factors, RPS for Elo factors) → helping / hurting /
  neutral. Hurting factors are disabled by an env flag, no code change.
- **Corners** and **sim-timing** scorecards validate corner O/U and scenario
  probabilities (late goal, comeback, result-flips-vs-HT) against outcomes.
- **Adaptive corners base** + **online Elo** + **nightly retrain** keep the model
  current; fitted JSON artifacts make re-fits hot-swappable.

---

## 7. Limitations

- WC-2026 lacks event-level data (LiveScore has no passing network), so
  event-derived features (box entries) inform but cannot serve live.
- Venue altitude/heat and situational context (dead rubber, biscotto) lack a
  clean labelled dataset → kept as bounded literature priors, audited live.
- Outcome predictability is intrinsically capped by variance; gains are modest
  by nature, which is why every claim is hold-out-validated.

We deliberately **do not fabricate** coefficients where data can't support them.

---

## 8. Reproducibility

```bash
cd backend
python -m ml.train                # WDL + O/U + BTTS ensemble (49k+9k)
python -m ml.statsbomb_dataset    # enriched 5,232-match event dataset
python -m ml.statsbomb_fit        # corner determinants + crosses→corner
python -m ml.corner_tactics_fit   # B2/B3 tactical corner + counter-matchup
python -m ml.statsbomb_style_fit  # style → totals / results
python -m ml.statsbomb_sim_fit    # strength-controlled score-state
python -m ml.attdef_lambda_proto  # attack/defence λ vs Elo-gap
python -m ml.xgform_proto         # xG-form vs goal-form
python -m ml.fatigue_proto        # rest/fatigue (null)
python -m ml.squad_strength       # squad prior (Wikipedia × ClubElo)
python -m ml.make_figures         # regenerate the figures in this paper
```

Artifacts: `backend/app/data/models/*_fit.json`. StatsBomb data used under their
licence — attribution: StatsBomb. All predictions are statistical estimates for
research/reference — not betting advice.

---

## 9. TODO — validation pass after group-stage round 1

Every bounded factor was adopted with a hold-out-validated *direction* but is
graded LIVE. **After matchday 1 of all 12 groups** (~24 real matches), re-read
the scorecards and keep / disable / re-fit each:

- [ ] Factor scorecard verdicts: `style`, `context`, `venue`, `prior`,
      `style_sup`, `xg_form` → disable any "hurting" (n≥~10) via its env flag.
- [ ] Corners scorecard + adaptive base (9.07 → observed).
- [ ] sim-timing scorecard (ht_flip / late-goal / comeback / clean-sheet).
- [ ] meta-weights (W/D/L blend; active ≥8 finished).
- [ ] O/U + handicap calibration on round-1 results (`ou_total_scale`,
      `goal_dc_weight`).
- [ ] xG-form nudge verdict (`xg_form_elo`, `xg_form_cap`).

Not yet built: §2C derived markets (clean-sheet, win-to-nil, odd/even, HT/FT,
first/next goal) — free from the reconciled matrix/sim, zero accuracy risk.
