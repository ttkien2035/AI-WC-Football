"""App settings. Reads the repo-root .env (FOOTBALL_API_KEY, ODDS_API_KEY)."""
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    football_api_key: str = ""
    football_api_key_1: str = Field(
        default="", validation_alias=AliasChoices("FOOTBALL_API_KEY1", "FOOTBALL_API_KEY_1"))
    football_api_key_2: str = Field(
        default="", validation_alias=AliasChoices("FOOTBALL_API_KEY2", "FOOTBALL_API_KEY_2"))

    def football_keys(self) -> list[str]:
        """fd.org keys; rate limit is 10 req/min per key — usage sits ~1-2/min
        thanks to caching, so extra keys are optional resilience, not a need."""
        return [k for k in (self.football_api_key, self.football_api_key_1,
                            self.football_api_key_2) if k]

    odds_api_key: str = ""
    odds_api_key_1: str = Field(
        default="", validation_alias=AliasChoices("ODDS_API_KEY1", "ODDS_API_KEY_1"))
    odds_api_key_2: str = Field(
        default="", validation_alias=AliasChoices("ODDS_API_KEY2", "ODDS_API_KEY_2"))

    def odds_keys(self) -> list[str]:
        """All Odds-API keys, primary first — clients rotate on quota errors
        (free tier is 500 credits/MONTH per key)."""
        return [k for k in (self.odds_api_key, self.odds_api_key_1,
                            self.odds_api_key_2) if k]
    admin_token: str = ""      # gates /api/pipeline/*, /api/refresh, /api/ml/retrain
    gemini_api_key: str = Field(
        default="", validation_alias=AliasChoices("GEMINI_API", "GEMINI_API_KEY"))
    gemini_api_key_1: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_1"))
    gemini_api_key_2: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_2"))
    gemini_api_key_3: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_3"))
    gemini_api_key_4: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_4"))

    def gemini_keys(self) -> list[str]:
        """All configured keys, primary first — chat rotates on quota errors."""
        return [k for k in (self.gemini_api_key, self.gemini_api_key_1,
                            self.gemini_api_key_2, self.gemini_api_key_3,
                            self.gemini_api_key_4) if k]

    # AI chat (cost control)
    chat_model: str = "gemini-2.5-flash"
    chat_daily_per_user: int = 10
    chat_daily_global: int = 300
    chat_max_output_tokens: int = 850   # room for a full match breakdown + verdict
    chat_analysis_max_output_tokens: int = 1500  # deep-think answers run longer
    # NOTE: the request cap sent to Gemini is answer_budget + chat_think_budget,
    # because 2.5 counts thinking tokens against maxOutputTokens (see chat.py).
    chat_think_budget: int = 3072    # Gemini thinking tokens for analysis intent
    chat_analysis_rounds: int = 5    # tool rounds allowed for analytical questions

    fd_base: str = "https://api.football-data.org/v4"
    odds_base: str = "https://api.the-odds-api.com/v4"
    elo_base: str = "https://www.eloratings.net"

    # Cache TTLs (seconds)
    ttl_matches: int = 60          # live window handled by scheduler refresh
    ttl_standings: int = 300
    ttl_elo: int = 86_400
    ttl_odds: int = 6 * 3600
    ttl_fifa: int = 7 * 86_400

    # Model
    n_sims_tournament: int = 50_000
    goals_mu: float = 2.6          # tournament avg total goals prior
    elo_sup_scale: float = 333.0   # elo diff -> goal supremacy (0.3 per 100)
    host_elo_bonus: float = 60.0   # hosts USA/MEX/CAN playing at home
    max_goals: int = 8

    # Outcome blend weights (heuristic fallback, no ML artifacts)
    w_market: float = 0.45
    w_poisson_with_market: float = 0.30
    w_elo_with_market: float = 0.20
    w_form_with_market: float = 0.05
    w_poisson: float = 0.50
    w_elo: float = 0.40
    w_form: float = 0.10
    # Outcome blend weights when the ML ensemble is available
    ml_w_market: float = 0.40
    ml_w_ml: float = 0.40
    ml_w_poisson: float = 0.15
    ml_w_form: float = 0.05
    ml_only_w_ml: float = 0.55       # no market odds
    ml_only_w_poisson: float = 0.30
    ml_only_w_elo: float = 0.10
    ml_only_w_form: float = 0.05

    # Score-model corrections (fitted from 49k-match history)
    ko_goal_factor: float = 0.955   # knockout caginess, per-90 (WC 1986-2022)
    # per-stage caginess multipliers (escalate toward the final)
    ko_stage_factors: dict = {
        "LAST_32": 0.97, "LAST_16": 0.95, "QUARTER_FINALS": 0.93,
        "SEMI_FINALS": 0.91, "THIRD_PLACE": 0.97, "FINAL": 0.90,
    }

    # Style/tactics interaction layer (literature-direction, bounded, audited
    # in-tournament via pipeline review)
    style_adjust_enabled: bool = True
    # DISABLED 2026-06-25 after MD2: the style->O/U total nudge HURT the O/U Brier
    # on real WC results, consistently across both rounds (factor_scorecard "style":
    # MD1 +0.0058 n10, MD2 +0.0054 n20) — matching the original StatsBomb fit that
    # found style adds NOTHING to total goals beyond shot volume (p=0.29/0.38). So
    # the goal-total style multiplier is off; style still feeds W/D/L supremacy
    # (style_sup, HELPING) + the minute sim. Re-enable by raising this if MD3 flips.
    style_total_max: float = 0.0    # 0.06 -> 0.03 -> 0 (measured hurting on O/U)
    # style -> W/D/L supremacy. Same fit: possession dominance barely predicts
    # wins (r=+0.05, p=0.37; dominate 50% vs cede 37%). Shrunk from 18 -> 10.
    style_sup_enabled: bool = True
    style_sup_max_elo: float = 10.0
    style_sup_draw_bump: float = 0.010
    # style-conditioned minute simulation (state response by team traits)
    style_sim_enabled: bool = True
    style_sim_lead_hold: float = 0.35   # counter team leading: keeps this share of its ease-off
    style_sim_chase_damp: float = 0.30  # chasing INTO a low block: bump damped by this
    style_sim_press_early: float = 0.06 # high-press: scoring intensity shifted early

    # Match-context layer (final-group-game stakes / dead rubber / seeding)
    context_adjust_enabled: bool = True
    # SHRUNK toward neutral 2026-06-28 after the full group stage: the group
    # context layer (dead-rubber/decider/seeding goal cut) HURT the O/U Brier in
    # MD3 (factor_scorecard "context" +0.019, n17) — "settled teams score fewer"
    # over-fired (rotated/open dead rubbers often score normally-or-more). Group
    # context can't recur this WC; gentle de-aggression is the correct direction
    # (re-validate on history before trusting it). KO factors below unchanged.
    context_dead_factor: float = 0.94     # was 0.88 — dead-rubber goal cut over-fired
    context_decider_factor: float = 0.99  # was 0.98
    context_seeding_elo_gap: float = 60.0 # Elo edge to flag "finish 2nd to dodge"
    context_seeding_factor: float = 0.99  # was 0.97
    # Knockout caution escalates by stage (replaces flat ko_goal_factor);
    # big-mismatch ties: underdog locks down & plays for the shootout lottery
    context_ko_underdog_gap: float = 120.0  # Elo gap to flag "play for penalties"
    context_ko_lockdown_factor: float = 0.90

    # Meta-calibration: learn the pre-match WDL blend weights from finished
    # tournament matches (engine/meta_weights.py), shrunk toward hand weights
    meta_weights_enabled: bool = True
    meta_weights_min_n: int = 8     # finished samples needed to activate
    meta_weights_k: float = 8.0     # shrink: fit carries n/(n+k)

    # Pot-tier strength prior (official draw pots -> bounded Elo shrink,
    # decays as the team plays; mainly steadies thin-data teams)
    pot_prior_enabled: bool = True
    pot_prior_w0: float = 0.15   # max shrink weight (team yet to play)
    pot_prior_k: float = 2.0     # decay: w = w0*k/(k+played)
    # Squad-strength refinement of the prior target (ml/squad_strength.py:
    # Wikipedia squads x ClubElo). Offset = clamp(sigma*z, ±cap) * coverage.
    squad_prior_enabled: bool = True
    squad_prior_sigma: float = 40.0  # Elo per squad-index z-unit
    squad_prior_cap: float = 70.0    # max |offset| on the tier baseline

    # Venue-conditions O/U factor (WC-2026 altitude + heat)
    venue_adjust_enabled: bool = True
    venue_alt_max: float = 0.07     # max altitude goal bump (Mexico City)
    venue_heat_max: float = 0.06    # max heat goal reduction (hot afternoon, open roof)

    # Real kickoff weather (Open-Meteo, free/no-key). When a forecast is
    # available the heat cut scales linearly with apparent temperature
    # between start and full; otherwise venue.py keeps the static heuristic.
    weather_enabled: bool = True
    weather_heat_start_c: float = 27.0  # apparent °C where the cut starts
    weather_heat_full_c: float = 37.0   # apparent °C of the full venue_heat_max cut
    weather_timeout_s: float = 4.0
    ttl_weather: float = 3 * 3600.0

    # Dixon-Robinson minute simulator (engine/match_sim.py)
    sim_state_effect: float = 0.12   # leading team eases / trailing pushes
    sim_lambda_cv: float = 0.18      # pre-match parameter uncertainty (Gamma CV)
    sim_runs: int = 20000

    # Period / corners model (engine/periods.py)
    h1_goal_share: float = 0.45      # share of goals scored in 1st half
    # FITTED from 314 modern men's international matches (StatsBomb event data,
    # ml/statsbomb_fit.py): mean total corners = 9.07/game. Adapts to WC-2026.
    # O/U calibration (ml/ measured on 8-9k holdout matches): the trained O/U
    # head is isotonic-calibrated; the Poisson matrix over-predicts Over ~+8.5pp.
    # Lever 1 — lean the O/U blend on the head; Lever 2 — scale the total-goals
    # of the Asian-line matrix so all lines calibrate (0.94 -> main lines ±0.5pp).
    ou_head_weight: float = 0.95
    btts_head_weight: float = 0.9
    ou_total_scale: float = 0.94
    # blend Dixon-Coles attack/defence lambda into the goal rates (asymmetric
    # attack-vs-defence matchup; holdout: O/U Brier 0.2512->0.244, MAE 1.48->1.42)
    goal_dc_weight: float = 0.5
    # in-tournament xG-form rating nudge: a team out-performing its scoreline on
    # xG ("unlucky") is better than results show. Group-B holdout: rolling
    # xG-form beats goal-form (R2 +17%). Direction-validated; magnitude bounded
    # (grounded: ~190 Elo/goal, applied as a small fraction, capped) + scorecard.
    xg_form_enabled: bool = True
    xg_form_elo: float = 40.0    # Elo per (goal/game) of xG-vs-result luck
    xg_form_cap: float = 25.0    # max |nudge| Elo
    xg_form_k: float = 2.0       # confidence decay: weight = n/(n+k)
    # pre-match shot-volume form nudge (recent_form_proto: recent shot-volume
    # differential improves OUTCOME +0.007 RPS, 4/4 CV folds; shot_form_fit
    # grounds the Elo coef on the PARTIAL slope after Elo+goal-form, p<1e-4).
    # Coefficient/cap/k live in data/models/shot_form.json (regenerate via
    # ml.espn_backfill + ml.shot_form_fit). 44/48 WC teams covered (free, ESPN).
    shot_form_enabled: bool = True

    corners_base: float = 9.07
    # adaptive base: blend the prior with the observed tournament mean, n/(n+k).
    # k kept high (conservative): a few cagey openers must NOT slash the base —
    # corners regress to the ~9 international norm as the tournament opens up.
    corners_adapt_enabled: bool = True
    corners_adapt_k: float = 20.0    # ~20 matches before observed carries half
    corners_dispersion: float = 1.96 # NB var/mean — corners are ~2x overdispersed
    corners_h1_share: float = 0.46
    # style-matchup multiplier on TOTAL corners (crossfest vs starved)
    corners_style_enabled: bool = True
    corners_style_max: float = 0.12
    # corners predicted from the MECHANISM (crossing volume + style), not the
    # noisy raw count. cross->corner ratio FITTED at 0.389 on 314 intl matches
    # (StatsBomb; was a hand-set 0.28) — overridden at runtime by the value in
    # corners_fit.json if present. Raw corner count trusted only slowly (raw_k).
    corners_cross_to_corner: float = 0.389
    corners_raw_k: float = 6.0
    # corners scale SUB-linearly with attack intensity (lam-sum). Round-1 WC2026
    # review (ml/corners_round1_review.py): error vs lam-sum corr ~0, but softening
    # 0.70->0.55 nudged O/U hit 18->19/27 and cut the +0.43 over-bias. Bounded,
    # tunable as more matches land. NOTE: a mismatch favourite often wins WITHOUT
    # racking up corners (ARG-ALG, USA-PAR) — the irreducible game-state variance
    # the NB dispersion (1.96) already models.
    corners_intensity_exp: float = 0.55
    # pre-match corner-form prior: seed each team's corner for/against rate from
    # recent ESPN internationals (corner_form.json) so the corners model has
    # team-specific data from match 1, not just base x intensity. Round-1 study
    # (ml/corners_form_fit.py): the team corner-rate blend beats a flat base on
    # 548 matches (O/U hit 59→62% holdout, MAE 3.85→3.57; CV +2pp) — small but
    # consistent (corners are high-variance, corr 0.20). Blended via raw_k, capped
    # prior weight, in-tournament data takes over as it accumulates.
    corner_form_enabled: bool = True
    et_intensity: float = 0.85       # ET scoring intensity vs regulation
    pens_elo_tilt: float = 0.4


settings = Settings()
HOST_TLAS = {"USA", "MEX", "CAN"}
