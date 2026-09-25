"""WMO weather interpretation codes (as used by Open-Meteo) -> text, icon, category.

Reference: https://open-meteo.com/en/docs (section "WMO Weather interpretation codes").
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherCondition:
    code: int
    description: str
    icon: str
    category: str


# Broad categories used by the condition summary. Ordered by severity, which is
# also the tie-breaker when two categories are equally frequent in a period.
CATEGORIES: tuple[str, ...] = (
    "Clear",
    "Partly cloudy",
    "Cloudy",
    "Fog",
    "Rain",
    "Snow",
    "Thunderstorm",
)
CATEGORY_SEVERITY: dict[str, int] = {name: i for i, name in enumerate(CATEGORIES)}

# One consistent colour per category, reused by every component.
CATEGORY_COLORS: dict[str, str] = {
    "Clear": "#eda100",
    "Partly cloudy": "#6da7ec",
    "Cloudy": "#898781",
    "Fog": "#b4b2a9",
    "Rain": "#2a78d6",
    "Snow": "#9085e9",
    "Thunderstorm": "#e34948",
}
CATEGORY_ICONS: dict[str, str] = {
    "Clear": "☀️",
    "Partly cloudy": "⛅",
    "Cloudy": "☁️",
    "Fog": "🌫️",
    "Rain": "🌧️",
    "Snow": "🌨️",
    "Thunderstorm": "⛈️",
}

_CODES: dict[int, tuple[str, str, str]] = {
    0: ("Clear sky", "☀️", "Clear"),
    1: ("Mainly clear", "🌤️", "Clear"),
    2: ("Partly cloudy", "⛅", "Partly cloudy"),
    3: ("Overcast", "☁️", "Cloudy"),
    45: ("Fog", "🌫️", "Fog"),
    48: ("Depositing rime fog", "🌫️", "Fog"),
    51: ("Light drizzle", "🌦️", "Rain"),
    53: ("Moderate drizzle", "🌦️", "Rain"),
    55: ("Dense drizzle", "🌧️", "Rain"),
    56: ("Light freezing drizzle", "🌧️", "Rain"),
    57: ("Dense freezing drizzle", "🌧️", "Rain"),
    61: ("Slight rain", "🌦️", "Rain"),
    63: ("Moderate rain", "🌧️", "Rain"),
    65: ("Heavy rain", "🌧️", "Rain"),
    66: ("Light freezing rain", "🌧️", "Rain"),
    67: ("Heavy freezing rain", "🌧️", "Rain"),
    71: ("Slight snowfall", "🌨️", "Snow"),
    73: ("Moderate snowfall", "🌨️", "Snow"),
    75: ("Heavy snowfall", "❄️", "Snow"),
    77: ("Snow grains", "🌨️", "Snow"),
    80: ("Slight rain showers", "🌦️", "Rain"),
    81: ("Moderate rain showers", "🌧️", "Rain"),
    82: ("Violent rain showers", "🌧️", "Rain"),
    85: ("Slight snow showers", "🌨️", "Snow"),
    86: ("Heavy snow showers", "❄️", "Snow"),
    95: ("Thunderstorm", "⛈️", "Thunderstorm"),
    96: ("Thunderstorm with slight hail", "⛈️", "Thunderstorm"),
    99: ("Thunderstorm with heavy hail", "⛈️", "Thunderstorm"),
}

# Night-time icon substitutions for clear / partly cloudy skies.
_NIGHT_ICONS: dict[int, str] = {0: "🌙", 1: "🌙", 2: "☁️"}

UNKNOWN = WeatherCondition(code=-1, description="Unknown", icon="❔", category="Unknown")


def describe(code: float | int | None, is_day: float | int | None = 1) -> WeatherCondition:
    """Translate a WMO code into a WeatherCondition. Missing/unknown codes -> UNKNOWN."""
    if code is None or (isinstance(code, float) and math.isnan(code)):
        return UNKNOWN
    code_int = int(code)
    if code_int not in _CODES:
        return WeatherCondition(code_int, f"Unknown code {code_int}", "❔", "Unknown")
    description, icon, category = _CODES[code_int]
    if is_day is not None and not (isinstance(is_day, float) and math.isnan(is_day)) and int(is_day) == 0:
        icon = _NIGHT_ICONS.get(code_int, icon)
    return WeatherCondition(code_int, description, icon, category)


def category_of(code: float | int | None) -> str:
    return describe(code).category
