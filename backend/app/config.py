"""App settings. Reads the repo-root .env (FOOTBALL_API_KEY, ODDS_API_KEY)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    football_api_key: str = ""
    odds_api_key: str = ""

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

    # Period / corners model (engine/periods.py)
    h1_goal_share: float = 0.45      # share of goals scored in 1st half
    corners_base: float = 9.7        # international avg total corners
    corners_h1_share: float = 0.46
    et_intensity: float = 0.85       # ET scoring intensity vs regulation
    pens_elo_tilt: float = 0.4


settings = Settings()
HOST_TLAS = {"USA", "MEX", "CAN"}
