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
    chat_analysis_max_output_tokens: int = 1100  # deep-think answers run longer
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
    style_total_max: float = 0.06   # max |lambda adjustment| from style matchup
    # style -> W/D/L supremacy (Elo-equivalent, literature-direction priors,
    # graded by the factor scorecard like every other nudge)
    style_sup_enabled: bool = True
    style_sup_max_elo: float = 18.0
    style_sup_draw_bump: float = 0.012  # possession-mirror slight draw tilt
    # style-conditioned minute simulation (state response by team traits)
    style_sim_enabled: bool = True
    style_sim_lead_hold: float = 0.35   # counter team leading: keeps this share of its ease-off
    style_sim_chase_damp: float = 0.30  # chasing INTO a low block: bump damped by this
    style_sim_press_early: float = 0.06 # high-press: scoring intensity shifted early

    # Match-context layer (final-group-game stakes / dead rubber / seeding)
    context_adjust_enabled: bool = True
    context_dead_factor: float = 0.88     # both teams' fate settled -> fewer goals
    context_decider_factor: float = 0.98  # both must-win -> mild knockout caution
    context_seeding_elo_gap: float = 60.0 # Elo edge to flag "finish 2nd to dodge"
    context_seeding_factor: float = 0.97  # small: teams often still try to win
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
    # international-tournament prior (WC2022 8.94, Euro2024 9.75, ~EPL 9.9
    # -> intl avg ~9.4); was 9.67 club-leaning. Adapts to WC-2026 reality.
    corners_base: float = 9.4
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
    # corners are predicted from the MECHANISM (crossing volume + style), not
    # the noisy raw count: a team's crosses/game map to corners by this ratio
    # (crosses ~16-18/g/team, corners ~4.7 -> ~0.28), and the raw corner count
    # is trusted only slowly (large raw_k) since 1-2 games are noisy.
    corners_cross_to_corner: float = 0.28
    corners_raw_k: float = 6.0
    et_intensity: float = 0.85       # ET scoring intensity vs regulation
    pens_elo_tilt: float = 0.4


settings = Settings()
HOST_TLAS = {"USA", "MEX", "CAN"}
