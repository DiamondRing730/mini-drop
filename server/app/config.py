"""Centralized configuration, sourced from MINIDROP_* environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIDROP_", extra="ignore")

    # Postgres connection (overridden by compose).
    database_url: str = "postgresql+psycopg2://minidrop:minidrop@postgres:5432/minidrop"

    # Shared volume where agent writes raw data and analyzer writes visualizations.
    artifacts_dir: str = "/data/artifacts"

    # An agent is considered offline if no heartbeat arrives within this window.
    offline_threshold_sec: int = 30
    # How often the background monitor scans for offline agents.
    monitor_interval_sec: int = 5
    # Cadence advertised back to agents on each heartbeat.
    heartbeat_interval_sec: int = 5

    # CORS origins for the web UI (comma-separated, "*" allows all in dev).
    cors_origins: str = "*"


settings = Settings()
