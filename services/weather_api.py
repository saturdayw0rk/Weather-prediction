"""Clients for the external weather data sources.

Sources
-------
* Open-Meteo Forecast API  - model forecast (current conditions, hourly, daily)
                             and per-model output for ECMWF / GFS / ICON.
* Open-Meteo model metadata - initialisation time of the latest model run.
* NOAA Aviation Weather Center METAR API - real station observations.

This module is deliberately free of Streamlit so it can be tested on its own.
Every function either returns real API data or raises WeatherAPIError; nothing
is ever substituted, interpolated or invented when a request fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from config import settings
from data.locations import METAR_STATIONS
from utils.units import KNOTS_TO_KMH, haversine_km, is_missing, relative_humidity

USER_AGENT = "UlaanbaatarWeatherDashboard/1.0 (+https://open-meteo.com)"

# --------------------------------------------------------------------------- #
# Variables requested from Open-Meteo
# --------------------------------------------------------------------------- #
CURRENT_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m", "is_day",
    "precipitation", "rain", "showers", "snowfall", "weather_code", "cloud_cover",
    "pressure_msl", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
HOURLY_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "precipitation_probability", "precipitation", "rain", "showers", "snowfall",
    "weather_code", "cloud_cover", "wind_speed_10m", "wind_direction_10m",
    "wind_gusts_10m", "uv_index", "is_day",
]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "apparent_temperature_min", "precipitation_sum",
    "snowfall_sum", "precipitation_probability_max", "wind_speed_10m_max",
    "wind_gusts_10m_max", "wind_direction_10m_dominant", "uv_index_max",
    "sunrise", "sunset",
]
COMPARISON_HOURLY_VARS = [
    "temperature_2m", "precipitation", "snowfall", "wind_speed_10m", "wind_direction_10m",
]
COMPARISON_DAILY_VARS = [
    "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "snowfall_sum",
    "wind_speed_10m_max", "wind_direction_10m_dominant",
]


@dataclass(frozen=True)
class ModelSpec:
    label: str        # shown in the UI
    api_id: str       # value for the Open-Meteo `models` parameter
    meta_id: str      # path segment for the model metadata endpoint
    provider: str
    description: str


COMPARISON_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("ECMWF", "ecmwf_ifs025", "ecmwf_ifs025", "European Centre for Medium-Range Weather Forecasts",
              "ECMWF IFS 0.25° open data (native 3-hourly, interpolated to hourly by Open-Meteo)"),
    ModelSpec("GFS", "gfs_seamless", "ncep_gfs025", "NOAA NCEP",
              "GFS global (Open-Meteo 'gfs_seamless'; GFS 0.25°/0.11° over Mongolia)"),
    ModelSpec("ICON", "icon_seamless", "dwd_icon", "Deutscher Wetterdienst (DWD)",
              "ICON (Open-Meteo 'icon_seamless'; ICON global ~13 km over Mongolia)"),
)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class WeatherAPIError(Exception):
    """Raised for any failure to obtain valid data. `user_message` is UI-safe."""

    def __init__(self, user_message: str, detail: str = "") -> None:
        super().__init__(f"{user_message} {detail}".strip())
        self.user_message = user_message
        self.detail = detail


# --------------------------------------------------------------------------- #
# Result containers (plain dataclasses so they can be cached / pickled)
# --------------------------------------------------------------------------- #
@dataclass
class GridInfo:
    requested_lat: float
    requested_lon: float
    grid_lat: float
    grid_lon: float
    elevation_m: float | None
    timezone: str
    utc_offset_s: int


@dataclass
class ForecastData:
    """Open-Meteo 'best match' forecast for one location."""
    grid: GridInfo
    current: dict[str, Any]
    current_time: pd.Timestamp | None       # local time the current values are valid for
    current_interval_s: int | None
    hourly: pd.DataFrame                    # index: local time (naive)
    daily: pd.DataFrame                     # index: local date (naive Timestamp)
    units: dict[str, str]
    fetched_at: datetime                    # UTC
    missing_vars: list[str] = field(default_factory=list)
    source: str = "Open-Meteo Forecast API"
    model: str = "best_match (Open-Meteo automatic model blend)"


@dataclass
class ModelRun:
    initialised_at: datetime | None         # UTC
    available_at: datetime | None           # UTC
    temporal_resolution_s: int | None


@dataclass
class ModelComparisonData:
    grid: GridInfo
    hourly: dict[str, pd.DataFrame]         # model label -> hourly frame
    daily: dict[str, pd.DataFrame]          # model label -> daily frame
    units: dict[str, str]                   # variable -> unit (identical across models)
    runs: dict[str, ModelRun | None]
    fetched_at: datetime
    missing_vars: list[str] = field(default_factory=list)


@dataclass
class Observation:
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    distance_km: float
    observed_at: datetime                   # UTC
    temperature_c: float | None
    dewpoint_c: float | None
    relative_humidity: float | None         # derived from temperature & dew point
    wind_direction_deg: float | None        # None when variable / calm
    wind_variable: bool
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    pressure_hpa: float | None
    visibility: str | None
    weather: str | None
    clouds: str | None
    raw: str

    def age_hours(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.observed_at).total_seconds() / 3600


@dataclass
class ObservationResult:
    observation: Observation | None
    status: str                             # "ok" | "stale" | "none_nearby"
    message: str
    fetched_at: datetime
    stations_reporting: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
def _get_json(url: str, params: dict[str, Any] | None = None, allow_empty: bool = False) -> Any:
    """GET a URL and decode JSON, translating every failure into WeatherAPIError."""
    try:
        resp = requests.get(
            url, params=params, timeout=settings.request_timeout_s,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except requests.exceptions.Timeout as exc:
        raise WeatherAPIError(
            f"The weather service did not respond within {settings.request_timeout_s:g} s (timeout).", str(exc)
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise WeatherAPIError(
            "Could not connect to the weather service. Check your internet connection.", str(exc)
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise WeatherAPIError("The request to the weather service failed.", str(exc)) from exc

    if resp.status_code == 204 or (allow_empty and not resp.content.strip()):
        return []

    if resp.status_code >= 400:
        reason = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                reason = str(body.get("reason") or body.get("error") or "")
        except ValueError:
            reason = resp.text[:200]
        kind = "is temporarily unavailable" if resp.status_code >= 500 else "rejected the request"
        raise WeatherAPIError(f"The weather service {kind} (HTTP {resp.status_code}).", reason)

    try:
        return resp.json()
    except ValueError as exc:
        raise WeatherAPIError("The weather service returned an invalid (non-JSON) response.", str(exc)) from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _grid_info(payload: dict[str, Any], lat: float, lon: float) -> GridInfo:
    try:
        return GridInfo(
            requested_lat=lat, requested_lon=lon,
            grid_lat=float(payload["latitude"]), grid_lon=float(payload["longitude"]),
            elevation_m=payload.get("elevation"),
            timezone=str(payload.get("timezone", "GMT")),
            utc_offset_s=int(payload.get("utc_offset_seconds", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherAPIError("The forecast response is missing location metadata.", str(exc)) from exc


def _frame(block: Any, variables: list[str], suffix: str = "", is_daily: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """Build a time-indexed DataFrame from an Open-Meteo hourly/daily block.

    Variables absent from the response become all-NaN columns and are returned
    in the `missing` list so the UI can flag them - they are never filled in.
    """
    if not isinstance(block, dict) or "time" not in block or not isinstance(block["time"], list):
        raise WeatherAPIError("The forecast response is missing its time series.")
    n = len(block["time"])
    if n == 0:
        raise WeatherAPIError("The forecast response contains no time steps.")

    index = pd.to_datetime(block["time"], errors="coerce")
    if index.isna().any():
        raise WeatherAPIError("The forecast response contains invalid timestamps.")

    data: dict[str, Any] = {}
    missing: list[str] = []
    for var in variables:
        values = block.get(f"{var}{suffix}")
        if not isinstance(values, list) or len(values) != n:
            missing.append(var)
            values = [None] * n
        data[var] = values

    df = pd.DataFrame(data, index=index)
    df.index.name = "date" if is_daily else "time"
    for col in df.columns:
        if col not in ("sunrise", "sunset"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # A variable that is present but entirely null carries no data either.
    missing += [v for v in variables if v not in missing and df[v].isna().all()]
    return df, missing


# --------------------------------------------------------------------------- #
# Open-Meteo: best-match forecast
# --------------------------------------------------------------------------- #
def fetch_forecast(lat: float, lon: float) -> ForecastData:
    params = {
        "latitude": lat, "longitude": lon,
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
        "forecast_days": settings.forecast_days,
        "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    }
    payload = _get_json(settings.open_meteo_forecast_url, params)
    if not isinstance(payload, dict):
        raise WeatherAPIError("The forecast response has an unexpected format.")

    grid = _grid_info(payload, lat, lon)
    hourly, miss_h = _frame(payload.get("hourly"), HOURLY_VARS)
    daily, miss_d = _frame(payload.get("daily"), DAILY_VARS, is_daily=True)

    current_block = payload.get("current")
    current: dict[str, Any] = {}
    current_time = None
    interval = None
    miss_c: list[str] = []
    if isinstance(current_block, dict):
        current_time = pd.to_datetime(current_block.get("time"), errors="coerce")
        current_time = None if pd.isna(current_time) else current_time
        interval = current_block.get("interval")
        for var in CURRENT_VARS:
            val = current_block.get(var)
            current[var] = val
            if val is None:
                miss_c.append(var)
    else:
        miss_c = list(CURRENT_VARS)

    units: dict[str, str] = {}
    for key in ("current_units", "hourly_units", "daily_units"):
        if isinstance(payload.get(key), dict):
            units.update({k: v for k, v in payload[key].items() if k not in ("time", "interval")})

    missing = sorted({*(f"current.{v}" for v in miss_c), *(f"hourly.{v}" for v in miss_h),
                      *(f"daily.{v}" for v in miss_d)})
    return ForecastData(
        grid=grid, current=current, current_time=current_time, current_interval_s=interval,
        hourly=hourly, daily=daily, units=units, fetched_at=_utc_now(), missing_vars=missing,
    )


# --------------------------------------------------------------------------- #
# Open-Meteo: per-model forecasts for comparison
# --------------------------------------------------------------------------- #
def fetch_model_run(meta_id: str) -> ModelRun | None:
    """Latest run metadata for a model. Returns None if unavailable (non-fatal)."""
    try:
        meta = _get_json(f"{settings.open_meteo_meta_url}/{meta_id}/static/meta.json")
    except WeatherAPIError:
        return None
    if not isinstance(meta, dict):
        return None

    def ts(key: str) -> datetime | None:
        val = meta.get(key)
        return datetime.fromtimestamp(val, tz=timezone.utc) if isinstance(val, (int, float)) and val > 0 else None

    res = meta.get("temporal_resolution_seconds")
    return ModelRun(ts("last_run_initialisation_time"), ts("last_run_availability_time"),
                    int(res) if isinstance(res, (int, float)) else None)


def fetch_model_comparison(lat: float, lon: float) -> ModelComparisonData:
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(COMPARISON_HOURLY_VARS),
        "daily": ",".join(COMPARISON_DAILY_VARS),
        "models": ",".join(m.api_id for m in COMPARISON_MODELS),
        "timezone": "auto",
        "forecast_days": settings.forecast_days,
        "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    }
    payload = _get_json(settings.open_meteo_forecast_url, params)
    if not isinstance(payload, dict):
        raise WeatherAPIError("The model comparison response has an unexpected format.")

    grid = _grid_info(payload, lat, lon)
    hourly: dict[str, pd.DataFrame] = {}
    daily: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for model in COMPARISON_MODELS:
        # With several models requested, Open-Meteo suffixes each variable with the model id.
        suffix = f"_{model.api_id}"
        h, mh = _frame(payload.get("hourly"), COMPARISON_HOURLY_VARS, suffix)
        d, md = _frame(payload.get("daily"), COMPARISON_DAILY_VARS, suffix, is_daily=True)
        hourly[model.label], daily[model.label] = h, d
        missing += [f"{model.label}: hourly.{v}" for v in mh] + [f"{model.label}: daily.{v}" for v in md]

    units: dict[str, str] = {}
    for key in ("hourly_units", "daily_units"):
        block = payload.get(key)
        if isinstance(block, dict):
            first = COMPARISON_MODELS[0].api_id
            for k, v in block.items():
                if k.endswith(f"_{first}"):
                    units[k[: -len(first) - 1]] = v

    runs = {m.label: fetch_model_run(m.meta_id) for m in COMPARISON_MODELS}
    return ModelComparisonData(grid=grid, hourly=hourly, daily=daily, units=units, runs=runs,
                               fetched_at=_utc_now(), missing_vars=missing)


# --------------------------------------------------------------------------- #
# METAR station observations
# --------------------------------------------------------------------------- #
def _num(value: Any) -> float | None:
    if is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_metar(item: dict[str, Any], lat: float, lon: float) -> Observation | None:
    try:
        st_lat, st_lon = float(item["lat"]), float(item["lon"])
        obs_time = datetime.fromtimestamp(int(item["obsTime"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None

    temp, dew = _num(item.get("temp")), _num(item.get("dewp"))
    wdir_raw = item.get("wdir")
    variable = isinstance(wdir_raw, str) and wdir_raw.upper() == "VRB"
    wdir = None if variable else _num(wdir_raw)
    wspd_kt, wgst_kt = _num(item.get("wspd")), _num(item.get("wgst"))
    if wdir == 0 and wspd_kt == 0:
        wdir = None  # calm

    clouds = item.get("clouds")
    cloud_text = None
    if isinstance(clouds, list) and clouds:
        parts = []
        for layer in clouds:
            if isinstance(layer, dict) and layer.get("cover"):
                base = layer.get("base")
                parts.append(f"{layer['cover']} {base} ft" if base is not None else str(layer["cover"]))
        cloud_text = ", ".join(parts) or None

    visib = item.get("visib")
    return Observation(
        station_id=str(item.get("icaoId", "?")),
        station_name=str(item.get("name", "")).split(",")[0].strip(),
        latitude=st_lat, longitude=st_lon,
        distance_km=haversine_km(lat, lon, st_lat, st_lon),
        observed_at=obs_time,
        temperature_c=temp, dewpoint_c=dew,
        relative_humidity=relative_humidity(temp, dew) if temp is not None and dew is not None else None,
        wind_direction_deg=wdir, wind_variable=variable,
        # The AWC API reports wind in knots regardless of the unit in the raw METAR.
        wind_speed_kmh=wspd_kt * KNOTS_TO_KMH if wspd_kt is not None else None,
        wind_gust_kmh=wgst_kt * KNOTS_TO_KMH if wgst_kt is not None else None,
        pressure_hpa=_num(item.get("altim")),
        visibility=f"{visib} statute mi" if visib not in (None, "") else None,
        weather=item.get("wxString") or None,
        clouds=cloud_text,
        raw=str(item.get("rawOb", "")),
    )


def fetch_observation(lat: float, lon: float) -> ObservationResult:
    """Latest METAR from the nearest reporting Mongolian station.

    Only stations within OBSERVATION_MAX_DISTANCE_KM qualify. A report older than
    OBSERVATION_MAX_AGE_HOURS is returned with status "stale" so the UI can show
    it as unavailable instead of presenting it as current.
    """
    payload = _get_json(settings.metar_url, {"ids": ",".join(METAR_STATIONS), "format": "json"},
                        allow_empty=True)
    if not isinstance(payload, list):
        raise WeatherAPIError("The observation service returned an unexpected format.")

    latest: dict[str, Observation] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        obs = _parse_metar(item, lat, lon)
        if obs and (obs.station_id not in latest or obs.observed_at > latest[obs.station_id].observed_at):
            latest[obs.station_id] = obs

    fetched = _utc_now()
    reporting = sorted(latest)
    nearby = sorted((o for o in latest.values() if o.distance_km <= settings.observation_max_distance_km),
                    key=lambda o: o.distance_km)
    if not nearby:
        return ObservationResult(
            None, "none_nearby",
            f"No weather station within {settings.observation_max_distance_km:.0f} km of this location "
            f"is publishing observations to the international METAR feed.",
            fetched, reporting,
        )

    fresh = [o for o in nearby if o.age_hours(fetched) <= settings.observation_max_age_hours]
    if fresh:
        obs = fresh[0]
        return ObservationResult(obs, "ok", f"Latest report from {obs.station_id}.", fetched, reporting)

    obs = nearby[0]
    return ObservationResult(
        obs, "stale",
        f"The latest report from {obs.station_id} is {obs.age_hours(fetched):.1f} h old "
        f"(limit {settings.observation_max_age_hours:.0f} h), so it is not shown as current.",
        fetched, reporting,
    )
