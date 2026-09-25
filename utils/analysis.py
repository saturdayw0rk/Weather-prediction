"""Pure data-processing helpers (no Streamlit, no plotting).

Everything here only reshapes or summarises values that came from the APIs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from utils.units import angular_spread, circular_mean, is_missing
from utils.weather_codes import CATEGORY_SEVERITY, category_of

PERIOD_OPTIONS: dict[str, int] = {"Today": 1, "Tomorrow": 1, "Next 3 days": 3, "Next 7 days": 7}

# Parts of the day used by the condition summary: (label, start hour, end hour).
DAY_PARTS: tuple[tuple[str, int, int], ...] = (
    ("Night", 0, 6), ("Morning", 6, 12), ("Afternoon", 12, 18), ("Evening", 18, 24),
)


def filter_period(df: pd.DataFrame, period: str, today: pd.Timestamp) -> pd.DataFrame:
    """Slice an hourly frame (local-time index) to a calendar-day period."""
    start = today.normalize()
    if period == "Tomorrow":
        start += pd.Timedelta(days=1)
    end = start + pd.Timedelta(days=PERIOD_OPTIONS.get(period, 7))
    return df[(df.index >= start) & (df.index < end)]


def value_at(df: pd.DataFrame, column: str, when: pd.Timestamp) -> float | None:
    """Value of `column` in the hourly row covering `when` (floor to the hour)."""
    if column not in df.columns or df.empty:
        return None
    hour = when.floor("h")
    if hour not in df.index:
        return None
    val = df.at[hour, column]
    return None if is_missing(val) else float(val)


def daily_mean_temperature(hourly: pd.DataFrame) -> pd.Series:
    """Mean of the hourly model temperatures per local calendar day."""
    if "temperature_2m" not in hourly:
        return pd.Series(dtype=float)
    return hourly["temperature_2m"].groupby(hourly.index.normalize()).mean()


def dominant_category(codes: pd.Series) -> str | None:
    """Most frequent condition category; ties go to the more severe category."""
    cats = [category_of(c) for c in codes.dropna()]
    cats = [c for c in cats if c in CATEGORY_SEVERITY]
    if not cats:
        return None
    counts = pd.Series(cats).value_counts()
    top = counts[counts == counts.max()].index
    return max(top, key=lambda c: CATEGORY_SEVERITY[c])


def condition_grid(hourly: pd.DataFrame) -> pd.DataFrame:
    """Rows = days, columns = parts of day, values = dominant condition category."""
    if "weather_code" not in hourly:
        return pd.DataFrame()
    rows = {}
    for day, group in hourly.groupby(hourly.index.normalize()):
        rows[day] = {
            label: dominant_category(group[(group.index.hour >= h0) & (group.index.hour < h1)]["weather_code"])
            for label, h0, h1 in DAY_PARTS
        }
    return pd.DataFrame.from_dict(rows, orient="index")


# --------------------------------------------------------------------------- #
# Model comparison statistics
# --------------------------------------------------------------------------- #
@dataclass
class ModelStats:
    values: dict[str, float | None]   # model label -> value
    low: float | None
    high: float | None
    mean: float | None
    spread: float | None              # high - low (or max angular difference for directions)
    n_models: int


def model_stats(values: dict[str, float | None], circular: bool = False) -> ModelStats:
    """Range / mean / spread across models. Missing model values are excluded, not filled."""
    clean = {k: float(v) for k, v in values.items() if not is_missing(v)}
    vals = list(clean.values())
    if not vals:
        return ModelStats(values, None, None, None, None, 0)
    if circular:
        return ModelStats(values, None, None, circular_mean(vals), angular_spread(vals), len(vals))
    return ModelStats(values, min(vals), max(vals), sum(vals) / len(vals), max(vals) - min(vals), len(vals))


def combine_models(frames: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    """Wide frame: one column per model for a given variable, aligned on time."""
    return pd.DataFrame({label: df[column] for label, df in frames.items() if column in df})
