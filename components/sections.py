"""Dashboard sections. Each function renders one self-contained part of the page.

Every section receives a `Loaded` wrapper so it can distinguish "data present"
from "request failed" and show the failure plus the last successful update
time instead of any substitute values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Callable

import pandas as pd
import streamlit as st

from components import charts
from components.cards import (key_value_panel, kpi_card, render_kpi_row, render_table,
                              render_unavailable)
from components.forecast import render_condition_summary, render_daily_cards
from services.weather_api import (COMPARISON_MODELS, ForecastData, ModelComparisonData,
                                  Observation, ObservationResult)
from utils.analysis import (combine_models, daily_mean_temperature, filter_period,
                            model_stats, value_at)
from utils.timefmt import fmt_local, fmt_run, fmt_utc
from utils.units import TempUnit, compass, convert_temp, fmt, fmt_temp, is_missing
from utils.weather_codes import describe


@dataclass
class Loaded:
    """Outcome of one data request: either `data` or `error`, never both."""
    name: str
    data: Any | None
    error: str | None
    last_success: datetime | None


def _last(ld: Loaded, tz: tzinfo) -> str | None:
    return fmt_utc(ld.last_success, tz) if ld.last_success else None


def _plot(fig) -> None:
    st.plotly_chart(fig, width="stretch", theme="streamlit", config={"displaylogo": False})


def _fresh_observation(obs_ld: Loaded) -> Observation | None:
    res: ObservationResult | None = obs_ld.data
    return res.observation if res is not None and res.status == "ok" else None


def forecast_stamp(fc: ForecastData, tz: tzinfo) -> str:
    g = fc.grid
    return (f"FORECAST · Open-Meteo best_match · grid {g.grid_lat:.2f}°N {g.grid_lon:.2f}°E · "
            f"fetched {fmt_utc(fc.fetched_at, tz)}")


# --------------------------------------------------------------------------- #
# KPI row
# --------------------------------------------------------------------------- #
def render_kpis(fc_ld: Loaded, obs_ld: Loaded, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    fc: ForecastData | None = fc_ld.data
    obs = _fresh_observation(obs_ld)
    cur = fc.current if fc else {}
    model_sub = (f"Model current · valid {fc.current_time:%H:%M}" if fc and fc.current_time is not None
                 else "Forecast data unavailable")
    obs_sub = (f"Station {obs.station_id} · {obs.observed_at.astimezone(tz):%H:%M} local" if obs else "")

    def model_card(label: str, value: str) -> str:
        return kpi_card(label, value if fc else "Unavailable", "forecast", model_sub)

    cards: list[str] = []
    # Temperature, humidity and wind prefer a real station observation when one is fresh.
    if obs and obs.temperature_c is not None:
        cards.append(kpi_card("Temperature", fmt_temp(obs.temperature_c, unit), "observed", obs_sub))
    else:
        cards.append(model_card("Temperature", fmt_temp(cur.get("temperature_2m"), unit)))

    cards.append(model_card("Feels like", fmt_temp(cur.get("apparent_temperature"), unit)))

    cond = describe(cur.get("weather_code"), cur.get("is_day"))
    cards.append(model_card("Condition", f"{cond.icon} {cond.description}"))

    if obs and obs.relative_humidity is not None:
        cards.append(kpi_card("Humidity", fmt(obs.relative_humidity, "%", 0), "observed",
                              f"{obs_sub} · from T/dew point"))
    else:
        cards.append(model_card("Humidity", fmt(cur.get("relative_humidity_2m"), "%", 0)))

    if obs and obs.wind_speed_kmh is not None:
        direction = "variable" if obs.wind_variable else compass(obs.wind_direction_deg)
        cards.append(kpi_card("Wind speed", f"{obs.wind_speed_kmh:.0f} km/h {direction}", "observed", obs_sub))
    else:
        cards.append(model_card("Wind speed",
                                f"{fmt(cur.get('wind_speed_10m'), 'km/h', 0)} {compass(cur.get('wind_direction_10m'))}"))

    pop = value_at(fc.hourly, "precipitation_probability", now) if fc else None
    cards.append(kpi_card("Precip. probability", fmt(pop, "%", 0) if fc else "Unavailable", "forecast",
                          f"Model · {now:%H}:00–{(now + pd.Timedelta(hours=1)):%H}:00" if fc else model_sub))
    render_kpi_row(cards)


# --------------------------------------------------------------------------- #
# Current weather: observed vs model
# --------------------------------------------------------------------------- #
def render_current(fc_ld: Loaded, obs_ld: Loaded, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    left, right = st.columns(2)

    with left:
        res: ObservationResult | None = obs_ld.data
        if res is None:
            render_unavailable("station observation", obs_ld.error or "", _last(obs_ld, tz))
        elif res.status != "ok" or res.observation is None:
            render_unavailable("station observation", res.message, _last(obs_ld, tz))
        else:
            o = res.observation
            wind = ("Variable" if o.wind_variable else f"{compass(o.wind_direction_deg)} "
                    f"({fmt(o.wind_direction_deg, '°', 0)})") if o.wind_direction_deg is not None or o.wind_variable \
                else "Calm / not reported"
            rows = [
                ("Station", f"{o.station_name} ({o.station_id}), {o.distance_km:.0f} km away"),
                ("Observed at", f"{fmt_utc(o.observed_at, tz)} · {o.age_hours() * 60:.0f} min ago"),
                ("Temperature", fmt_temp(o.temperature_c, unit)),
                ("Dew point", fmt_temp(o.dewpoint_c, unit)),
                ("Relative humidity", f"{fmt(o.relative_humidity, '%', 0)} (derived from T and dew point)"),
                ("Wind", f"{fmt(o.wind_speed_kmh, 'km/h', 0)} · {wind}"),
                ("Gusts", fmt(o.wind_gust_kmh, "km/h", 0) if o.wind_gust_kmh is not None else "None reported"),
                ("Pressure (QNH)", fmt(o.pressure_hpa, "hPa", 0)),
                ("Visibility", o.visibility or "—"),
                ("Present weather", o.weather or "None reported"),
                ("Clouds", o.clouds or "—"),
            ]
            st.markdown(key_value_panel("Observed — station report (METAR)", "observed", rows,
                                        "Source: NOAA Aviation Weather Center · measured values, not a forecast"),
                        unsafe_allow_html=True)
            with st.expander("Raw METAR"):
                st.code(o.raw or "—", language=None)

    with right:
        fc: ForecastData | None = fc_ld.data
        if fc is None:
            render_unavailable("model current conditions", fc_ld.error or "", _last(fc_ld, tz))
            return
        c = fc.current
        cond = describe(c.get("weather_code"), c.get("is_day"))
        uv = value_at(fc.hourly, "uv_index", now)
        rows = [
            ("Valid at", f"{fmt_local(fc.current_time, tz)}"
                         f"{f' · {fc.current_interval_s // 60}-min step' if fc.current_interval_s else ''}"),
            ("Temperature", fmt_temp(c.get("temperature_2m"), unit)),
            ("Feels like", fmt_temp(c.get("apparent_temperature"), unit)),
            ("Condition", f"{cond.icon} {cond.description}"),
            ("Relative humidity", fmt(c.get("relative_humidity_2m"), "%", 0)),
            ("Wind", f"{fmt(c.get('wind_speed_10m'), 'km/h', 0)} · {compass(c.get('wind_direction_10m'))} "
                     f"({fmt(c.get('wind_direction_10m'), '°', 0)})"),
            ("Gusts", fmt(c.get("wind_gusts_10m"), "km/h", 0)),
            ("Precipitation", f"{fmt(c.get('precipitation'), 'mm', 1)} (snowfall {fmt(c.get('snowfall'), 'cm', 1)})"),
            ("Cloud cover", fmt(c.get("cloud_cover"), "%", 0)),
            ("UV index (this hour)", fmt(uv, "", 1)),
            ("Pressure (MSL)", fmt(c.get("pressure_msl"), "hPa", 0)),
        ]
        st.markdown(key_value_panel("Model current conditions", "forecast", rows,
                                    f"Source: Open-Meteo best_match model · grid {fc.grid.grid_lat:.2f}°N "
                                    f"{fc.grid.grid_lon:.2f}°E · model estimate, not a measurement"),
                    unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Hourly charts
# --------------------------------------------------------------------------- #
def render_hourly_charts(fc: ForecastData, period: str, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    df = filter_period(fc.hourly, period, now).copy()
    if df.empty:
        st.info(f"The forecast response contains no hourly data for '{period}'.")
        return
    for col in ("temperature_2m", "apparent_temperature"):
        df[col] = convert_temp(df[col], unit)
    stamp = forecast_stamp(fc, tz)

    t_temp, t_precip, t_wind = st.tabs(["🌡️ Temperature", "💧 Precipitation", "💨 Wind"])
    with t_temp:
        _plot(charts.temperature_chart(df, unit, now, stamp))
    with t_precip:
        _plot(charts.precipitation_chart(df, now, stamp))
    with t_wind:
        c1, c2 = st.columns([3, 2])
        with c1:
            _plot(charts.wind_chart(df, now, stamp))
        with c2:
            _plot(charts.wind_rose(df, stamp))
        st.caption("Arrows point in the direction the wind blows towards. "
                   "Wind direction in the data is the direction the wind comes from (meteorological convention).")


def render_temperature_range(fc: ForecastData, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    daily = fc.daily.head(7)
    means = daily_mean_temperature(fc.hourly)
    days = pd.DataFrame({
        "label": [d.strftime("%a %d") for d in daily.index],
        "tmin": convert_temp(daily["temperature_2m_min"], unit).values,
        "tmax": convert_temp(daily["temperature_2m_max"], unit).values,
        "tmean": convert_temp(means.reindex(daily.index.normalize()), unit).values,
    }).dropna(subset=["tmin", "tmax"])
    if days.empty:
        st.info("Daily minimum/maximum temperatures are missing from the forecast response.")
        return
    _plot(charts.temperature_range_chart(days, unit, forecast_stamp(fc, tz)))
    st.caption("Min/max: Open-Meteo daily values. Average: mean of the 24 hourly model temperatures for each day.")


def render_forecast_days(fc: ForecastData, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    st.caption(forecast_stamp(fc, tz))
    render_daily_cards(fc.daily, now, unit)


def render_conditions(fc: ForecastData, tz: tzinfo, now: pd.Timestamp) -> None:
    st.caption(forecast_stamp(fc, tz) + " · dominant WMO condition per 6-hour period")
    render_condition_summary(fc.hourly, now)


# --------------------------------------------------------------------------- #
# Model comparison
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompVar:
    column: str
    unit: str
    decimals: int
    summary: str                         # "now" -> value this hour, "sum" -> total over period
    daily: tuple[tuple[str, str], ...]   # (label, daily column)
    is_temp: bool = False
    circular: bool = False


COMP_VARS: dict[str, CompVar] = {
    "Temperature": CompVar("temperature_2m", "°C", 1, "now",
                           (("Daily maximum", "temperature_2m_max"), ("Daily minimum", "temperature_2m_min")),
                           is_temp=True),
    "Precipitation": CompVar("precipitation", "mm", 1, "sum", (("Daily total", "precipitation_sum"),)),
    "Wind speed": CompVar("wind_speed_10m", "km/h", 1, "now", (("Daily maximum", "wind_speed_10m_max"),)),
    "Wind direction": CompVar("wind_direction_10m", "°", 0, "now",
                              (("Dominant direction", "wind_direction_10m_dominant"),), circular=True),
    "Snowfall": CompVar("snowfall", "cm", 1, "sum", (("Daily total", "snowfall_sum"),)),
}


def _comp_fmt(v: float | None, var: CompVar, unit: str) -> str:
    if is_missing(v):
        return "—"
    if var.circular:
        return f"{v:.0f}° {compass(v)}"
    return fmt(v, unit, var.decimals)


def _period_total(series: pd.Series) -> float | None:
    # A total is only meaningful when every hour of the period is present.
    if series.empty or series.isna().any():
        return None
    return float(series.sum())


def render_model_comparison(ld: Loaded, period: str, unit: TempUnit, tz: tzinfo, now: pd.Timestamp) -> None:
    comp: ModelComparisonData | None = ld.data
    if comp is None:
        render_unavailable("forecast model comparison", ld.error or "", _last(ld, tz))
        return

    st.markdown(
        "Raw output of three independent global models for the same grid point. "
        "**This is a model comparison, not an observed measurement.** "
        "Where models disagree, the spread indicates forecast uncertainty."
    )
    choice = st.radio("Variable", list(COMP_VARS), horizontal=True, key="comp_var", label_visibility="collapsed")
    var = COMP_VARS[choice]
    disp_unit = unit if var.is_temp else var.unit
    conv: Callable[[Any], Any] = (lambda x: convert_temp(x, unit)) if var.is_temp else (lambda x: x)

    runs = " · ".join(f"{m.label} {fmt_run(comp.runs[m.label].initialised_at if comp.runs.get(m.label) else None)}"
                      for m in COMPARISON_MODELS)
    stamp = (f"MODEL COMPARISON · {runs} · grid {comp.grid.grid_lat:.2f}°N {comp.grid.grid_lon:.2f}°E · "
             f"fetched {fmt_utc(comp.fetched_at, tz)}")

    # --- Summary: this hour's value, or the total over the selected period -----
    hourly_period = {m: filter_period(df, period, now) for m, df in comp.hourly.items()}
    if var.summary == "now":
        values = {m: value_at(df, var.column, now) for m, df in comp.hourly.items()}
        when = f"Valid {now:%Y-%m-%d %H}:00 local"
    else:
        values = {m: _period_total(df[var.column]) for m, df in hourly_period.items()}
        when = f"Total over '{period}'"
    values = {m: (conv(v) if v is not None else None) for m, v in values.items()}
    stats = model_stats(values, circular=var.circular)

    cards = [kpi_card(m, _comp_fmt(values.get(m), var, disp_unit), "model", when) for m in comp.hourly]
    if var.circular:
        cards.append(kpi_card("Model average", _comp_fmt(stats.mean, var, disp_unit), "derived",
                              f"Circular mean of {stats.n_models} models"))
        cards.append(kpi_card("Model spread", fmt(stats.spread, "°", 0), "derived", "Largest angular difference"))
    else:
        rng = (f"{_comp_fmt(stats.low, var, disp_unit)} to {_comp_fmt(stats.high, var, disp_unit)}"
               if stats.n_models else "—")
        cards.append(kpi_card("Model range", rng, "derived", f"{stats.n_models} of {len(comp.hourly)} models"))
        cards.append(kpi_card("Model average", _comp_fmt(stats.mean, var, disp_unit), "derived",
                              f"Spread {_comp_fmt(stats.spread, var, disp_unit)}"))
    render_kpi_row(cards)

    # --- Hourly chart --------------------------------------------------------
    wide = conv(combine_models(hourly_period, var.column))
    if wide.empty:
        st.info(f"No hourly model data for '{period}'.")
    else:
        _plot(charts.model_comparison_chart(wide, disp_unit, f"{choice}: ECMWF vs GFS vs ICON (hourly)",
                                            stamp, now, circular=var.circular))

    # --- Daily tables ----------------------------------------------------------
    cols = st.columns(len(var.daily))
    for col, (label, daily_col) in zip(cols, var.daily):
        with col:
            st.markdown(f"**{choice} — {label.lower()} per day**")
            rows = _daily_comparison_table(comp, daily_col, var, conv, disp_unit)
            render_table(rows, numeric_cols=tuple(c for c in rows[0] if c != "Day") if rows else ())
    if comp.missing_vars:
        st.caption("Not provided by the API (shown as —): " + ", ".join(comp.missing_vars))
    st.caption("ECMWF open data is published at 3-hour resolution; Open-Meteo interpolates it to hourly steps.")


def _daily_comparison_table(comp: ModelComparisonData, column: str, var: CompVar,
                            conv: Callable[[Any], Any], unit: str) -> list[dict[str, str]]:
    rows = []
    first = next(iter(comp.daily.values()))
    for day in first.index:
        vals = {m: (conv(df.at[day, column]) if column in df and not is_missing(df.at[day, column]) else None)
                for m, df in comp.daily.items()}
        s = model_stats(vals, circular=var.circular)
        row: dict[str, Any] = {"Day": day.strftime("%a %d %b")}
        row.update({m: _comp_fmt(v, var, unit) for m, v in vals.items()})
        if var.circular:
            row["Circular mean"] = _comp_fmt(s.mean, var, unit)
            row["Max difference"] = fmt(s.spread, "°", 0)
        else:
            row["Range"] = f"{_comp_fmt(s.low, var, unit)} to {_comp_fmt(s.high, var, unit)}" if s.n_models else "—"
            row["Average"] = _comp_fmt(s.mean, var, unit)
            row["Spread"] = _comp_fmt(s.spread, var, unit)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Data sources
# --------------------------------------------------------------------------- #
def render_data_sources(fc_ld: Loaded, obs_ld: Loaded, comp_ld: Loaded, loc_lat: float, loc_lon: float,
                        tz: tzinfo) -> None:
    unavailable = "Data unavailable"
    rows: list[dict[str, str]] = []

    def failed(source: str, api: str, kind: str, ld: Loaded) -> dict[str, str]:
        return {"Source": source, "API / model": api, "Type": kind,
                "Last updated": f"{unavailable} (last success: {_last(ld, tz) or 'none this session'})",
                "Coordinates": f"requested {loc_lat:.4f}, {loc_lon:.4f}", "Data timestamp": unavailable,
                "Units": "—"}

    # 1. Station observation
    res: ObservationResult | None = obs_ld.data
    src_obs, api_obs = "NOAA Aviation Weather Center (aviationweather.gov)", "METAR API"
    if res is None:
        rows.append(failed(src_obs, api_obs, "Observed", obs_ld))
    elif res.observation is None:
        rows.append({"Source": src_obs, "API / model": api_obs, "Type": "Observed",
                     "Last updated": fmt_utc(res.fetched_at, tz), "Coordinates": "No station nearby",
                     "Data timestamp": "No report", "Units": "—"})
    else:
        o = res.observation
        status = "" if res.status == "ok" else " — STALE, not displayed"
        rows.append({"Source": src_obs, "API / model": f"{api_obs} · station {o.station_id} ({o.station_name})",
                     "Type": "Observed", "Last updated": fmt_utc(res.fetched_at, tz),
                     "Coordinates": f"{o.latitude:.3f}, {o.longitude:.3f} ({o.distance_km:.0f} km from location)",
                     "Data timestamp": fmt_utc(o.observed_at, tz) + status,
                     "Units": "°C, km/h (API knots × 1.852), hPa, statute miles"})

    # 2-3. Best-match forecast
    fc: ForecastData | None = fc_ld.data
    src_om = "Open-Meteo Forecast API (api.open-meteo.com)"
    if fc is None:
        rows.append(failed(src_om, "best_match — current / hourly / daily", "Forecast", fc_ld))
    else:
        coords = (f"grid {fc.grid.grid_lat:.4f}, {fc.grid.grid_lon:.4f} "
                  f"(requested {loc_lat:.4f}, {loc_lon:.4f}; elev. {fmt(fc.grid.elevation_m, 'm', 0)})")
        rows.append({"Source": src_om, "API / model": "best_match — current conditions",
                     "Type": "Forecast (model estimate for now)", "Last updated": fmt_utc(fc.fetched_at, tz),
                     "Coordinates": coords, "Data timestamp": f"valid {fmt_local(fc.current_time, tz)}",
                     "Units": "°C, %, km/h, mm, cm, hPa"})
        rows.append({"Source": src_om, "API / model": "best_match — hourly & daily forecast",
                     "Type": "Forecast", "Last updated": fmt_utc(fc.fetched_at, tz), "Coordinates": coords,
                     "Data timestamp": f"{fmt_local(fc.hourly.index.min(), tz)} → {fmt_local(fc.hourly.index.max(), tz)}",
                     "Units": "°C, %, km/h, mm, cm"})

    # 4-6. Model comparison
    comp: ModelComparisonData | None = comp_ld.data
    for m in COMPARISON_MODELS:
        if comp is None:
            rows.append(failed(src_om, f"{m.label} ({m.api_id})", "Forecast — model comparison", comp_ld))
            continue
        run = comp.runs.get(m.label)
        run_txt = (f"{fmt_run(run.initialised_at)}; available {fmt_utc(run.available_at, tz)}" if run
                   else "run metadata unavailable")
        rows.append({"Source": f"{src_om} — {m.provider}", "API / model": f"{m.description}",
                     "Type": "Forecast — model comparison", "Last updated": fmt_utc(comp.fetched_at, tz),
                     "Coordinates": f"grid {comp.grid.grid_lat:.4f}, {comp.grid.grid_lon:.4f}",
                     "Data timestamp": run_txt, "Units": "°C, mm, cm, km/h, °"})

    render_table(rows)
    if fc is not None and fc.missing_vars:
        st.caption("Variables not provided by the API for this location (shown as —): " + ", ".join(fc.missing_vars))
    st.markdown(
        '<div class="wx-disclaimer">Forecast values are model predictions and may differ from actual observed '
        "conditions. Observed values are measured by the listed station, which may be some distance from the "
        "selected location. No values on this dashboard are estimated, filled in or simulated; anything the "
        "sources do not provide is shown as “—” or “Data unavailable”.</div>",
        unsafe_allow_html=True,
    )
