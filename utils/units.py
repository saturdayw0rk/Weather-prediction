"""Unit conversion and formatting helpers.

All data is requested from the APIs in metric units (°C, km/h, mm, cm) and
converted here only for display, so cached responses are unit-independent.
"""

from __future__ import annotations

import math
from typing import Literal

import pandas as pd

TempUnit = Literal["°C", "°F"]

KNOTS_TO_KMH = 1.852

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def convert_temp(value, unit: TempUnit):
    """Convert a °C scalar or pandas Series to the requested unit."""
    if unit == "°F":
        return value * 9 / 5 + 32
    return value


def fmt(value: object, unit: str = "", decimals: int = 1, missing: str = "—") -> str:
    """Format a number with unit, rendering missing values as an em dash."""
    if is_missing(value):
        return missing
    sep = "" if unit.startswith("°") or unit == "%" else " "
    return f"{float(value):.{decimals}f}{sep}{unit}"


def fmt_temp(value_c: object, unit: TempUnit, decimals: int = 1) -> str:
    if is_missing(value_c):
        return "—"
    return fmt(convert_temp(float(value_c), unit), unit, decimals)


def compass(degrees: object) -> str:
    if is_missing(degrees):
        return "—"
    return _COMPASS[int((float(degrees) % 360) / 22.5 + 0.5) % 16]


def relative_humidity(temp_c: float, dewpoint_c: float) -> float:
    """Relative humidity (%) from temperature and dew point (Magnus formula)."""
    a, b = 17.625, 243.04
    rh = 100 * math.exp(a * dewpoint_c / (b + dewpoint_c)) / math.exp(a * temp_c / (b + temp_c))
    return max(0.0, min(100.0, rh))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def circular_mean(degrees: list[float]) -> float | None:
    """Mean of angles in degrees (0-360), or None if there are no values."""
    vals = [d for d in degrees if not is_missing(d)]
    if not vals:
        return None
    s = sum(math.sin(math.radians(d)) for d in vals)
    c = sum(math.cos(math.radians(d)) for d in vals)
    if abs(s) < 1e-9 and abs(c) < 1e-9:
        return None
    return math.degrees(math.atan2(s, c)) % 360


def angular_spread(degrees: list[float]) -> float | None:
    """Largest pairwise angular difference (0-180°) between directions."""
    vals = [d for d in degrees if not is_missing(d)]
    if len(vals) < 2:
        return None
    worst = 0.0
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            diff = abs(a - b) % 360
            worst = max(worst, min(diff, 360 - diff))
    return worst
