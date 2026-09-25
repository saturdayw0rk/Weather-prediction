"""Ulaanbaatar Weather Dashboard - Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

import streamlit as st

from components import sections
from components.cards import inject_css, render_unavailable
from components.sections import Loaded
from config import settings
from data.locations import LOCATIONS
from services.weather_api import (WeatherAPIError, fetch_forecast, fetch_model_comparison,
                                  fetch_observation)
from utils.analysis import PERIOD_OPTIONS
from utils.timefmt import DEFAULT_TZ, fmt_utc, get_tz, now_local

st.set_page_config(page_title="Ulaanbaatar Weather Dashboard", page_icon="🌤️", layout="wide")
inject_css()


# --------------------------------------------------------------------------- #
# Cached data access. Only successful responses are cached: st.cache_data does
# not store results of calls that raise, so a failed request is retried on the
# next run rather than masked.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=settings.cache_ttl_s, show_spinner=False)
def load_forecast(lat: float, lon: float):
    return fetch_forecast(lat, lon)


@st.cache_data(ttl=settings.cache_ttl_s, show_spinner=False)
def load_comparison(lat: float, lon: float):
    return fetch_model_comparison(lat, lon)


# METARs are issued every 30-60 min, so observations use a shorter TTL.
@st.cache_data(ttl=min(settings.cache_ttl_s, 300), show_spinner=False)
def load_observation(lat: float, lon: float):
    return fetch_observation(lat, lon)


def clear_caches() -> None:
    for fn in (load_forecast, load_comparison, load_observation):
        fn.clear()
    st.session_state["last_refresh_ts"] = time.time()


def safe_load(name: str, loader: Callable[..., Any], *args: Any) -> Loaded:
    """Call a loader and record the outcome. Failures never fall back to older data."""
    history: dict[str, datetime] = st.session_state.setdefault("last_success", {})
    key = f"{name}|{args}"
    try:
        data = loader(*args)
    except WeatherAPIError as exc:
        return Loaded(name, None, exc.user_message, history.get(key))
    except Exception as exc:  # defensive: an unexpected payload shape must not crash the page
        return Loaded(name, None, f"Unexpected error while processing the response: {exc}", history.get(key))
    history[key] = data.fetched_at
    return Loaded(name, data, None, data.fetched_at)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar() -> tuple[str, str, str, st.delta_generator.DeltaGenerator]:
    sb = st.sidebar
    sb.header("Settings")
    names = list(LOCATIONS)
    default = names.index(settings.default_location) if settings.default_location in LOCATIONS else 0
    location = sb.selectbox("Location", names, index=default,
                            format_func=lambda n: f"{n} ({LOCATIONS[n].province})")
    period = sb.radio("Forecast period (charts)", list(PERIOD_OPTIONS), index=0)
    unit = sb.radio("Temperature unit", ["°C", "°F"], horizontal=True)

    sb.divider()
    if sb.button("🔄 Refresh Weather Data", width="stretch", type="primary"):
        clear_caches()
    auto = sb.toggle("Auto refresh", value=False)
    if auto:
        minutes = sb.select_slider("Interval (minutes)", options=[5, 10, 15, 30, 60], value=15)
        start_auto_refresh(minutes * 60)
    sb.divider()
    status = sb.container()
    sb.caption(f"Responses are cached for {settings.cache_ttl_s // 60} min "
               "(observations 5 min). Refresh forces new requests.")
    return location, period, unit, status


def start_auto_refresh(interval_s: int) -> None:
    """Re-fetch all data every `interval_s` seconds while the page is open."""
    st.session_state.setdefault("last_refresh_ts", time.time())

    @st.fragment(run_every=interval_s)
    def _ticker() -> None:
        if time.time() - st.session_state["last_refresh_ts"] >= interval_s - 1:
            clear_caches()
            st.rerun()

    _ticker()


def render_status(status, loads: list[Loaded], tz) -> None:
    status.markdown("**Last updated**")
    labels = {"forecast": "Forecast", "observation": "Observation", "comparison": "Model comparison"}
    for ld in loads:
        if ld.data is not None:
            status.caption(f"✅ {labels[ld.name]}: {fmt_utc(ld.data.fetched_at, tz)}")
        else:
            last = fmt_utc(ld.last_success, tz) if ld.last_success else "none this session"
            status.caption(f"⚠️ {labels[ld.name]}: data unavailable (last success: {last})")


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def main() -> None:
    location_name, period, unit, status = render_sidebar()
    loc = LOCATIONS[location_name]

    with st.spinner("Fetching weather data…"):
        fc = safe_load("forecast", load_forecast, loc.latitude, loc.longitude)
        obs = safe_load("observation", load_observation, loc.latitude, loc.longitude)
        comp = safe_load("comparison", load_comparison, loc.latitude, loc.longitude)

    # Local time zone comes from the API (Open-Meteo timezone=auto); western aimags use UTC+7.
    tz = get_tz(fc.data.grid.timezone, fc.data.grid.utc_offset_s) if fc.data else get_tz(DEFAULT_TZ)
    now = now_local(tz)
    render_status(status, [fc, obs, comp], tz)

    # Header
    tz_name = fc.data.grid.timezone if fc.data else DEFAULT_TZ
    st.markdown(
        f'<div class="wx-header"><h1>Ulaanbaatar Weather Dashboard</h1>'
        f'<div class="wx-meta">📍 {loc.name}, Mongolia · {loc.latitude:.4f}°N, {loc.longitude:.4f}°E'
        f' &nbsp;·&nbsp; 🕒 {now:%A, %d %B %Y · %H:%M} local ({tz_name})</div></div>',
        unsafe_allow_html=True,
    )
    st.write("")

    if fc.data is None and obs.data is None and comp.data is None:
        st.error("⚠️ Weather data is currently unavailable from all sources. "
                 "Check your internet connection and use **Refresh Weather Data** to retry.")

    # KPI row + current weather
    sections.render_kpis(fc, obs, unit, tz, now)
    st.subheader("Current weather — observed vs model")
    sections.render_current(fc, obs, unit, tz, now)

    if fc.data is None:
        st.subheader("Forecast")
        render_unavailable("hourly and daily forecast", fc.error or "",
                           fmt_utc(fc.last_success, tz) if fc.last_success else None)
    else:
        st.subheader(f"Hourly forecast — {period.lower()}")
        sections.render_hourly_charts(fc.data, period, unit, tz, now)

        st.subheader("7-day forecast")
        sections.render_forecast_days(fc.data, unit, tz, now)

        left, right = st.columns([1, 1])
        with left:
            st.subheader("Temperature range")
            sections.render_temperature_range(fc.data, unit, tz, now)
        with right:
            st.subheader("Weather condition summary")
            sections.render_conditions(fc.data, tz, now)

    st.subheader(f"Forecast model comparison — ECMWF vs GFS vs ICON ({period.lower()})")
    sections.render_model_comparison(comp, period, unit, tz, now)

    st.subheader("Data sources")
    sections.render_data_sources(fc, obs, comp, loc.latitude, loc.longitude, tz)


main()
