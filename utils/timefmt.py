"""Timezone-aware timestamp formatting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

DEFAULT_TZ = "Asia/Ulaanbaatar"


def get_tz(name: str | None, utc_offset_s: int | None = None) -> tzinfo:
    """Resolve an IANA zone name; fall back to a fixed offset, then to Ulaanbaatar."""
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        if utc_offset_s is not None:
            return timezone(timedelta(seconds=utc_offset_s))
        return timezone(timedelta(hours=8))


def now_local(tz: tzinfo) -> pd.Timestamp:
    """Current local wall-clock time as a naive Timestamp (matches API time indexes)."""
    return pd.Timestamp(datetime.now(tz).replace(tzinfo=None))


def _offset_label(dt: datetime) -> str:
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    return f"UTC{sign}{abs(total) // 60:02d}:{abs(total) % 60:02d}"


def fmt_utc(dt: datetime | None, tz: tzinfo) -> str:
    """Format an aware UTC datetime in local time with its UTC offset."""
    if dt is None:
        return "—"
    local = dt.astimezone(tz)
    return f"{local:%Y-%m-%d %H:%M} ({_offset_label(local)})"


def fmt_local(ts: pd.Timestamp | None, tz: tzinfo) -> str:
    """Format a naive local Timestamp (as returned by Open-Meteo) with its UTC offset."""
    if ts is None or pd.isna(ts):
        return "—"
    aware = ts.to_pydatetime().replace(tzinfo=tz)
    return f"{aware:%Y-%m-%d %H:%M} ({_offset_label(aware)})"


def fmt_run(dt: datetime | None) -> str:
    """Model run initialisation time, conventionally shown in UTC ('00Z')."""
    if dt is None:
        return "run time unavailable"
    return f"{dt:%Y-%m-%d %H}Z run"
