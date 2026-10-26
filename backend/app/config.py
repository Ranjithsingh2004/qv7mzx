"""Application settings, resolved from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every value has a safe default so the service starts with no environment
    set up at all; deployments override via environment variables.
    """

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    # --- Upstream (Elexon BMRS Insights API; public, no API key required) ---
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_timeout_seconds: float = 30.0
    elexon_max_retries: int = 3

    # --- Analysis defaults (see docs/METHODOLOGY.md) ---
    # The agreed analysis scope is purchase decisions taken in January 2026.
    default_decision_from: str = "2026-01-01"
    default_decision_to: str = "2026-01-31"
    # Assumed day-ahead decision cutoff: 09:00 Europe/London on the day before
    # delivery. This is a documented product assumption, not a market rule.
    default_cutoff_time: str = "09:00"
    default_cutoff_days_before: int = 1
    # Actuals below this level (MW) are excluded from MAPE to avoid division
    # by near-zero denominators.
    default_mape_floor_mw: float = 100.0

    # --- Caching ---
    cache_ttl_seconds: int = 900
    cache_max_entries: int = 32

    # --- HTTP ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"


settings = Settings()
