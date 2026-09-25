"""7-day forecast cards and the weather-condition summary grid."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from utils.analysis import DAY_PARTS, condition_grid
from utils.units import TempUnit, compass, fmt, fmt_temp
from utils.weather_codes import CATEGORIES, CATEGORY_COLORS, CATEGORY_ICONS, describe


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _day_label(day: pd.Timestamp, today: pd.Timestamp) -> str:
    delta = (day.normalize() - today.normalize()).days
    return {0: "Today", 1: "Tomorrow"}.get(delta, day.strftime("%A"))


def render_daily_cards(daily: pd.DataFrame, today: pd.Timestamp, unit: TempUnit) -> None:
    """One card per forecast day. Values are shown exactly as returned; missing -> '—'."""
    days = daily.head(7)
    cols = st.columns(len(days)) if len(days) else []
    for col, (day, row) in zip(cols, days.iterrows()):
        cond = describe(row.get("weather_code"))
        strip = CATEGORY_COLORS.get(cond.category, "#898781")
        wind_dir = compass(row.get("wind_direction_10m_dominant"))
        html = (
            f'<div class="wx-day"><div class="strip" style="background:{strip}"></div>'
            f'<div class="d1">{escape(_day_label(day, today))}</div>'
            f'<div class="d2">{day.strftime("%b %d")}</div>'
            f'<div class="ic">{cond.icon}</div>'
            f'<div class="cond">{escape(cond.description)}</div>'
            f'<div class="temps">{fmt_temp(row.get("temperature_2m_max"), unit, 0)} '
            f'<span class="lo">/ {fmt_temp(row.get("temperature_2m_min"), unit, 0)}</span></div>'
            f'<div class="meta">💧 {fmt(row.get("precipitation_probability_max"), "%", 0)} · '
            f'{fmt(row.get("precipitation_sum"), "mm", 1)}<br>'
            f'💨 {fmt(row.get("wind_speed_10m_max"), "km/h", 0)} {wind_dir}</div></div>'
        )
        col.markdown(html, unsafe_allow_html=True)


def render_condition_summary(hourly: pd.DataFrame, today: pd.Timestamp) -> None:
    """Grid of dominant condition per day and part of day, plus hour counts per category."""
    grid = condition_grid(hourly)
    if grid.empty:
        st.info("Weather codes are missing from the forecast response - condition summary unavailable.")
        return

    head = "".join(f"<th>{label}<br><span style='font-weight:400'>{h0:02d}–{h1:02d}</span></th>"
                   for label, h0, h1 in DAY_PARTS)
    body = []
    for day, row in grid.iterrows():
        cells = [f'<td class="rowh">{escape(_day_label(day, today))}<br>'
                 f'<span style="font-weight:400;opacity:.7">{day.strftime("%b %d")}</span></td>']
        for label, _, _ in DAY_PARTS:
            cat = row.get(label)
            if not isinstance(cat, str):
                cells.append('<td style="opacity:.5">—</td>')
                continue
            bg = _hex_to_rgba(CATEGORY_COLORS[cat], 0.2)
            cells.append(f'<td style="background:{bg}">{CATEGORY_ICONS[cat]}<br>{escape(cat)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<table class="wx-cond"><tr><th></th>{head}</tr>{"".join(body)}</table>',
                unsafe_allow_html=True)

    # Legend with the number of forecast hours in each category over the forecast horizon.
    cats = hourly["weather_code"].dropna().map(lambda c: describe(c).category)
    counts = cats.value_counts()
    items = "".join(
        f'<span><span class="sw" style="background:{CATEGORY_COLORS[c]}"></span>'
        f'{CATEGORY_ICONS[c]} {c}: {int(counts.get(c, 0))} h</span>'
        for c in CATEGORIES
    )
    st.markdown(f'<div class="wx-legend">{items}</div>', unsafe_allow_html=True)
