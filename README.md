# ⚽ AI World Cup 2026 Predictor

> Full-stack football prediction platform for FIFA World Cup 2026 — ML ensemble, Monte Carlo tournament simulation, live in-play win probability, tactical analysis, and odds comparison.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688) ![React](https://img.shields.io/badge/React-Vite%20%2B%20Tailwind-61DAFB) ![Docker](https://img.shields.io/badge/Docker-compose-2496ED) ![i18n](https://img.shields.io/badge/i18n-EN%20%2F%20VI-orange)

---

## ✨ Features

### 🔴 Live match tracking & real-time prediction
- Live score, **real match minute**, goals/cards event feed, corners — auto-refreshing every 20s
- **Win-probability timeline chart** (FiveThirtyEight-style) — the model re-predicts on every scheduler tick and charts how each team's chances evolve minute by minute
- Starting lineups with **formation derived from pitch coordinates** (e.g. 4-3-3, 4-2-3-1)

### 🧠 ML ensemble prediction engine
Trained on **49,405 international matches (1872–2026)** with chronologically-computed Elo, pi-ratings, and rolling form. Backtest on a held-out 2025–26 test set (n = 1,313):

| Model | RPS ↓ | Log-loss ↓ | Accuracy |
|---|---|---|---|
| Elo heuristic (baseline) | 0.1701 | 0.8747 | 61.7% |
| Dixon-Coles bivariate Poisson | 0.1769 | 0.8866 | 58.7% |
| Logistic Regression | 0.1613 | 0.8369 | 61.7% |
| XGBoost (isotonic-calibrated) | 0.1608 | 0.8438 | 61.5% |
| **Ensemble (0.25 LR + 0.75 XGB)** | **0.1605** | **0.8349** | 61.5% |

Final pre-match blend: market odds (de-vigged) 40% / ML ensemble 40% / Poisson 15% / form 5%.

### 🔁 Self-improving all tournament long
- **Online updates**: Elo + pi-ratings + form recomputed after every finished WC match
- **Nightly auto-retrain** (03:00 UTC, never during a live match) on the refreshed dataset; old artifacts kept if training fails
- **Match log**: the app accumulates its own structured dataset (results, HT scores, corners) in SQLite

### 🏆 Tournament Monte Carlo simulation
- 50,000 vectorized tournament runs in ~0.7s (numpy)
- Group stage (real results locked in) → FIFA tiebreakers → **8 best third-placed teams** assigned via the official slot-combination table (backtracking over ≤495 scenarios) → official bracket routing M73–M104
- Title odds, per-round advancement probabilities, most-likely bracket with dates & venues

### 📊 Rich per-match predictions
- Win/draw/loss, most likely scorelines, Over 2.5, BTTS
- **Per-half predictions** (H1/H2 scorelines, HT/FT 9-way matrix)
- **Corners** per half/team with over/under lines, calibrated from in-tournament data
- **Extra time & penalties** (knockouts): P(decided in 90'), P(ET), P(shootout), "wins via" breakdown
- Research-backed in-play adjustments: **red cards** (λ ×0.67 / ×1.25 per man down), **key-player absence** (−40 Elo per missing star, capped, from announced XIs)

### 🎯 Tactical analysis
- Curated profiles for all 48 teams: formation, playing style, manager, key players, squad value tier
- Live XI vs profile comparison — missing stars flagged and fed into the prediction
- Full squads from football-data.org

### 💰 Odds board
- Market odds (1X2, Asian handicap, totals, BTTS, corners) vs **model fair odds** side by side
- Value highlighting when the model rates a probability above the market

### ✅ Honest accuracy reporting
- Built-in backtest report + **per-matchup verification**: pick any team or H2H pair and see what the model predicted for each past match (as-of features, no leakage) with ✓/✗ verdicts

### 🌐 UX
- 7-tab React UI: Live · Groups · Bracket · Match Sim · Title Odds · Odds · Accuracy
- English / Vietnamese language toggle, dark/light mode, today's matches ticker

## 🚧 Coming soon
- 🤖 **AI chatbot match analyst** — ask questions about any fixture ("Why is Spain favored?", "How does Mexico's missing striker change the odds?") and get model-grounded analysis
- Penalty-shootout simulator with kicker-level detail
- Public read-only API & embeddable widgets

---

## 🏗 Architecture

```
                    ┌─────────────────────────────────────────────┐
 football-data.org →│  FastAPI backend                            │
 LiveScore (live)  →│  ├─ clients/   data sources + SQLite cache  │←→ volumes:
 eloratings.net    →│  ├─ engine/    ML ensemble · Poisson · MC   │   cache_data
 The Odds API      →│  ├─ ml/        training pipeline (offline)  │   models_data
                    │  └─ scheduler  auto-refresh · retrain · log │
                    └──────────────────┬──────────────────────────┘
                                       │ /api (nginx proxy in prod)
                    ┌──────────────────┴──────────────────────────┐
                    │  React + Vite + Tailwind (EN/VI)            │
                    └─────────────────────────────────────────────┘
```

## 📡 Data sources

| Source | Role | Key |
|---|---|---|
| [football-data.org](https://www.football-data.org) v4 | Standings, fixtures, results (source of truth) | `FOOTBALL_API_KEY` (free) |
| [LiveScore](https://www.livescore.com) | Real minute, incidents, corners, lineups — *unofficial endpoint, best-effort with graceful fallback; personal use* | — |
| [eloratings.net](https://eloratings.net) | World Football Elo (live scrape + bundled fallback) | — |
| [The Odds API](https://the-odds-api.com) | Market odds, quota-budgeted (~500 credits/mo free) | `ODDS_API_KEY` (optional) |
| [martj42/international_results](https://github.com/martj42/international_results) | 49k matches for ML training | — |

## 🚀 Quick start

### Docker (recommended)

```bash
# .env in the repo root:
#   FOOTBALL_API_KEY=your_key
#   ODDS_API_KEY=your_key        # optional
docker compose up -d --build
# UI  → http://localhost:8080
# API → http://localhost:8000/api/health
```

### Development

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8000

# frontend (separate terminal)
cd frontend
npm install && npm run dev      # http://localhost:5173
```

### Retrain the ML models

```bash
cd backend
.venv/bin/pip install -r requirements-ml.txt
.venv/bin/python -m ml.train    # downloads data, trains, backtests, exports artifacts
```

### Deploy to a VPS

See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** — one-command rsync deploy (`deploy/push.sh user@YOUR_SERVER`), security checklist, HTTPS setup.

## 🔌 API overview

```
GET  /api/groups                         # 12 groups + qualification odds
GET  /api/simulate?runs=50000            # full tournament Monte Carlo
GET  /api/bracket                        # routing + per-slot odds + schedule
GET  /api/match/{H}/{A}/predict          # full prediction (halves/corners/ET-pens)
GET  /api/match/{H}/{A}/predict?minute=69&hg=2&ag=1    # in-play override
GET  /api/match/{H}/{A}/analysis         # lineups, formation, key players, style
GET  /api/live                           # live + today's matches (enriched)
GET  /api/live/{id}/timeline             # win-probability time series
GET  /api/odds                           # market vs model fair odds board
GET  /api/evaluate/h2h/{H}/{A}           # grade the model on past meetings
GET  /api/ml/status   ·  POST /api/ml/retrain
GET  /api/sources/status                 # health of every data source
```

## ⚠️ Limitations & disclaimer

- football-data.org free tier has no live minute → sourced from LiveScore (unofficial) with kickoff-time estimation as fallback
- Playing-style profiles are display-only analysis — only evidence-backed factors (red cards, key absences) adjust probabilities
- Third-place slot allocation uses a valid FIFA-table matching; real fixtures replace projections once announced
- **All outputs are statistical estimates for reference and entertainment — not betting advice.**
