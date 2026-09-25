"""Plotly figure builders.

Each builder receives data that is already filtered and converted to display
units, plus a `stamp` string (source, model, grid point, timestamp) that is
rendered as the chart subtitle so every chart carries its provenance.

Design rules followed throughout: one y-axis per plot (measures with different
units get separate stacked panels), thin 2px lines, fixed series colours,
recessive grid, unified hover.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.units import compass

# Categorical slots (fixed order - colour follows the series, never its rank).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_LIGHT, BLUE_DARK = "#86b6ef", "#184f95"
MUTED = "#898781"
SPREAD_FILL = "rgba(137,135,129,0.18)"
MODEL_COLORS: dict[str, str] = {"ECMWF": BLUE, "GFS": ORANGE, "ICON": AQUA}
# Sequential blue ramp (light -> dark) for binned wind speeds.
WIND_BIN_COLORS = ("#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281")


def _layout(fig: go.Figure, title: str, stamp: str, height: int = 380, y_title: str | None = None) -> go.Figure:
    # The provenance stamp goes on its own lines so it never collides with the plot or legend.
    stamp_html = stamp.replace(" · fetched", "<br>fetched")
    fig.update_layout(
        title=dict(text=f"{title}<br><span style='font-size:11px;opacity:0.7'>{stamp_html}</span>",
                   x=0, xanchor="left", font=dict(size=15)),
        height=height,
        margin=dict(l=10, r=10, t=96, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, ticks="outside", ticklen=4)
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.22)", zeroline=False)
    if y_title:
        fig.update_yaxes(title_text=y_title)
    return fig


def _now_marker(fig: go.Figure, now: pd.Timestamp, x_range: tuple[pd.Timestamp, pd.Timestamp]) -> None:
    """Vertical 'Now' line (drawn as a shape: add_vline + annotation misbehaves on date axes)."""
    if not (x_range[0] <= now <= x_range[1]):
        return
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, xref="x", yref="paper",
                  line=dict(color=MUTED, width=1, dash="dot"))
    fig.add_annotation(x=now, y=1, xref="x", yref="paper", text="Now", showarrow=False,
                       yanchor="bottom", font=dict(size=10, color=MUTED))


def _range(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    return df.index.min(), df.index.max()


def temperature_chart(df: pd.DataFrame, unit: str, now: pd.Timestamp, stamp: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["temperature_2m"], name="Temperature", mode="lines",
                             line=dict(color=BLUE, width=2),
                             hovertemplate=f"%{{y:.1f}}{unit}<extra>Temperature</extra>"))
    fig.add_trace(go.Scatter(x=df.index, y=df["apparent_temperature"], name="Feels like", mode="lines",
                             line=dict(color=ORANGE, width=2),
                             hovertemplate=f"%{{y:.1f}}{unit}<extra>Feels like</extra>"))
    _now_marker(fig, now, _range(df))
    return _layout(fig, "Hourly temperature vs feels-like", stamp, y_title=unit)


def precipitation_chart(df: pd.DataFrame, now: pd.Timestamp, stamp: str) -> go.Figure:
    """Probability (%) and amount (mm) as two stacked panels sharing the time axis."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.42, 0.58],
                        subplot_titles=("Precipitation probability (%)", "Precipitation amount (mm / hour)"))
    fig.add_trace(go.Scatter(x=df.index, y=df["precipitation_probability"], name="Probability",
                             mode="lines", line=dict(color=BLUE, width=2), showlegend=False,
                             hovertemplate="%{y:.0f}%<extra>Probability</extra>"), row=1, col=1)
    snow = df["snowfall"] if "snowfall" in df else pd.Series(index=df.index, dtype=float)
    fig.add_trace(go.Bar(x=df.index, y=df["precipitation"], name="Amount", marker_color=BLUE,
                         marker_cornerradius=4, showlegend=False, customdata=snow,
                         hovertemplate="%{y:.1f} mm (snowfall %{customdata:.2f} cm)<extra>Amount</extra>"),
                  row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=1, col=1)
    fig.update_yaxes(rangemode="tozero", row=2, col=1)
    fig.update_layout(bargap=0.15)
    fig.update_annotations(font=dict(size=11), x=0, xanchor="left", selector=dict(text="Precipitation probability (%)"))
    fig.update_annotations(font=dict(size=11), x=0, xanchor="left", selector=dict(text="Precipitation amount (mm / hour)"))
    _now_marker(fig, now, _range(df))
    return _layout(fig, "Hourly precipitation", stamp, height=460)


def wind_chart(df: pd.DataFrame, now: pd.Timestamp, stamp: str) -> go.Figure:
    """Wind speed & gusts (same unit, one axis) with direction arrows along the speed line."""
    fig = go.Figure()
    dirs = df["wind_direction_10m"]
    fig.add_trace(go.Scatter(
        x=df.index, y=df["wind_speed_10m"], name="Wind speed", mode="lines",
        line=dict(color=BLUE, width=2), customdata=[compass(d) for d in dirs],
        hovertemplate="%{y:.1f} km/h from %{customdata}<extra>Wind speed</extra>"))
    fig.add_trace(go.Scatter(x=df.index, y=df["wind_gusts_10m"], name="Gusts", mode="lines",
                             line=dict(color=ORANGE, width=2, dash="dot"),
                             hovertemplate="%{y:.1f} km/h<extra>Gusts</extra>"))

    # Arrows point where the wind blows TO (meteorological direction is where it comes FROM).
    step = 2 if len(df) <= 48 else 6
    sample = df.iloc[::step].dropna(subset=["wind_speed_10m", "wind_direction_10m"])
    fig.add_trace(go.Scatter(
        x=sample.index, y=sample["wind_speed_10m"], mode="markers", name="Direction",
        marker=dict(symbol="arrow", size=11, angle=(sample["wind_direction_10m"] + 180) % 360,
                    color=BLUE_DARK, line=dict(width=0)),
        hoverinfo="skip"))
    _now_marker(fig, now, _range(df))
    return _layout(fig, "Hourly wind speed, gusts and direction", stamp, y_title="km/h")


def wind_rose(df: pd.DataFrame, stamp: str) -> go.Figure:
    """Distribution of forecast hours by direction (16 sectors) and speed bin."""
    sectors = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    bins = [0, 5, 10, 20, 30, 40, float("inf")]
    labels = ["<5", "5–10", "10–20", "20–30", "30–40", "≥40"]
    data = df[["wind_speed_10m", "wind_direction_10m"]].dropna()
    fig = go.Figure()
    if not data.empty:
        sector = ((data["wind_direction_10m"] % 360) / 22.5 + 0.5).astype(int) % 16
        speed_bin = pd.cut(data["wind_speed_10m"], bins=bins, labels=labels, right=False)
        counts = pd.crosstab(speed_bin, sector).reindex(index=labels, columns=range(16), fill_value=0)
        for label, color in zip(labels, WIND_BIN_COLORS):
            fig.add_trace(go.Barpolar(r=counts.loc[label].values, theta=sectors, name=f"{label} km/h",
                                      marker_color=color, marker_line_width=1,
                                      marker_line_color="rgba(128,128,128,0.35)",
                                      hovertemplate="%{theta}: %{r} h<extra>" + label + " km/h</extra>"))
    fig.update_layout(polar=dict(domain=dict(y=[0, 0.93]), angularaxis=dict(direction="clockwise", rotation=90),
                                 radialaxis=dict(showticklabels=False, ticks=""),
                                 bgcolor="rgba(0,0,0,0)"))
    _layout(fig, "Wind rose (forecast hours by direction)", stamp, height=440)
    fig.update_layout(hovermode="closest", legend=dict(y=-0.05, font=dict(size=10)))
    return fig


def temperature_range_chart(days: pd.DataFrame, unit: str, stamp: str) -> go.Figure:
    """Floating min-max bars per day with the daily mean as a marker.

    `days` columns: label, tmin, tmax, tmean.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=days["label"], y=days["tmax"] - days["tmin"], base=days["tmin"], name="Min – max range",
        marker=dict(color=BLUE_LIGHT, cornerradius=4), width=0.45,
        customdata=days[["tmin", "tmax"]].values,
        hovertemplate=f"Min %{{customdata[0]:.1f}}{unit} · Max %{{customdata[1]:.1f}}{unit}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=days["label"], y=days["tmean"], name="Average (mean of hourly)", mode="markers",
        marker=dict(color=BLUE_DARK, size=10, line=dict(width=2, color="rgba(255,255,255,0.9)")),
        hovertemplate=f"Average %{{y:.1f}}{unit}<extra></extra>"))
    # Direct labels for the two numbers the chart exists to compare.
    fig.add_trace(go.Scatter(x=days["label"], y=days["tmax"], mode="text", text=[f"{v:.0f}°" for v in days["tmax"]],
                             textposition="top center", textfont=dict(size=11), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=days["label"], y=days["tmin"], mode="text", text=[f"{v:.0f}°" for v in days["tmin"]],
                             textposition="bottom center", textfont=dict(size=11, color=MUTED), showlegend=False,
                             hoverinfo="skip"))
    pad = max(2.0, float((days["tmax"].max() - days["tmin"].min()) * 0.12))
    fig.update_yaxes(range=[days["tmin"].min() - pad, days["tmax"].max() + pad])
    return _layout(fig, "7-day temperature range", stamp, y_title=unit)


def model_comparison_chart(wide: pd.DataFrame, y_title: str, title: str, stamp: str,
                           now: pd.Timestamp, circular: bool = False) -> go.Figure:
    """One line per model plus a shaded min-max spread band.

    For wind direction (circular) values are drawn as markers only and no band
    is shown, because a linear min/max is meaningless across the 0°/360° wrap.
    """
    fig = go.Figure()
    models = [c for c in wide.columns if wide[c].notna().any()]
    if not circular and len(models) >= 2:
        lo, hi = wide[models].min(axis=1), wide[models].max(axis=1)
        fig.add_trace(go.Scatter(x=wide.index, y=hi, mode="lines", line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=wide.index, y=lo, mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor=SPREAD_FILL, name="Model spread (min–max)", hoverinfo="skip"))
    for model in models:
        color = MODEL_COLORS.get(model, MUTED)
        if circular:
            fig.add_trace(go.Scatter(x=wide.index, y=wide[model], name=model, mode="markers",
                                     marker=dict(color=color, size=6),
                                     customdata=[compass(v) for v in wide[model]],
                                     hovertemplate="%{y:.0f}° (%{customdata})<extra>" + model + "</extra>"))
        else:
            fig.add_trace(go.Scatter(x=wide.index, y=wide[model], name=model, mode="lines",
                                     line=dict(color=color, width=2),
                                     hovertemplate="%{y:.1f}<extra>" + model + "</extra>"))
    if circular:
        fig.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360],
                         ticktext=["N 0°", "E 90°", "S 180°", "W 270°", "N 360°"])
    if not wide.empty:
        _now_marker(fig, now, _range(wide))
    return _layout(fig, title, stamp, height=400, y_title=y_title)
