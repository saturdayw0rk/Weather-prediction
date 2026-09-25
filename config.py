"""Application configuration loaded from environment variables / a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    open_meteo_forecast_url: str
    open_meteo_meta_url: str
    metar_url: str
    request_timeout_s: float
    cache_ttl_s: int
    default_location: str
    observation_max_distance_km: float
    observation_max_age_hours: float
    forecast_days: int


settings = Settings(
    open_meteo_forecast_url=_env_str("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"),
    open_meteo_meta_url=_env_str("OPEN_METEO_META_URL", "https://api.open-meteo.com/data"),
    metar_url=_env_str("METAR_URL", "https://aviationweather.gov/api/data/metar"),
    request_timeout_s=_env_float("REQUEST_TIMEOUT_SECONDS", 15.0),
    cache_ttl_s=_env_int("CACHE_TTL_SECONDS", 600),
    default_location=_env_str("DEFAULT_LOCATION", "Ulaanbaatar"),
    observation_max_distance_km=_env_float("OBSERVATION_MAX_DISTANCE_KM", 50.0),
    observation_max_age_hours=_env_float("OBSERVATION_MAX_AGE_HOURS", 2.0),
    forecast_days=_env_int("FORECAST_DAYS", 7),
)
