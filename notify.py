"""Send a daily weather forecast to Telegram.

    python notify.py morning     # today's forecast   (run in the morning)
    python notify.py evening     # tomorrow's forecast (run in the evening)
    python notify.py evening --dry-run   # print the message instead of sending

Uses the same Open-Meteo forecast as the dashboard (services.weather_api). As in
the dashboard, nothing is estimated: if the forecast cannot be fetched, the
message says the data is unavailable and the script exits with a non-zero code.

Scheduling: see scripts/register_telegram_tasks.ps1 (Windows Task Scheduler).
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import timedelta

import pandas as pd
import requests

from config import settings
from data.locations import LOCATIONS, Location
from services.weather_api import ForecastData, WeatherAPIError, fetch_forecast
from utils.analysis import DAY_PARTS, dominant_category
from utils.timefmt import get_tz, now_local
from utils.units import fmt, is_missing
from utils.weather_codes import CATEGORY_ICONS, describe

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Mongolian labels for the WMO codes (utils.weather_codes keeps the English ones).
CODE_MN: dict[int, str] = {
    0: "Цэлмэг", 1: "Ихэвчлэн цэлмэг", 2: "Багавтар үүлтэй", 3: "Үүлэрхэг",
    45: "Манан", 48: "Цантай манан",
    51: "Бага зэргийн шиврээ", 53: "Шиврээ бороо", 55: "Их шиврээ",
    56: "Хөлдөх шиврээ", 57: "Хүчтэй хөлдөх шиврээ",
    61: "Бага зэргийн бороо", 63: "Бороо", 65: "Их бороо",
    66: "Хөлдөх бороо", 67: "Хүчтэй хөлдөх бороо",
    71: "Бага зэргийн цас", 73: "Цас", 75: "Их цас", 77: "Мөхлөгт цас",
    80: "Бага зэргийн аадар", 81: "Аадар бороо", 82: "Хүчтэй аадар",
    85: "Бага зэргийн цас орно", 86: "Их цас орно",
    95: "Аянга цахилгаан", 96: "Аянга, бага зэргийн мөндөр", 99: "Аянга, их мөндөр",
}
CATEGORY_MN: dict[str, str] = {
    "Clear": "Цэлмэг", "Partly cloudy": "Багавтар үүлтэй", "Cloudy": "Үүлэрхэг",
    "Fog": "Манан", "Rain": "Бороо", "Snow": "Цас", "Thunderstorm": "Аянга",
}
DAY_PART_MN: dict[str, str] = {"Night": "Шөнө", "Morning": "Өглөө", "Afternoon": "Өдөр", "Evening": "Орой"}
WEEKDAY_MN = ("Даваа", "Мягмар", "Лхагва", "Пүрэв", "Баасан", "Бямба", "Ням")
# Direction the wind blows *from*, 8 points starting at north.
WIND_FROM_MN = ("хойноос", "зүүн хойноос", "зүүнээс", "зүүн өмнөөс",
                "өмнөөс", "баруун өмнөөс", "барууннаас", "баруун хойноос")
ONE_DAY = timedelta(days=1)  # stdlib timedelta: pd.Timedelta(days=1) warns with NumPy 2.5


def _day_value(daily: pd.DataFrame, day: pd.Timestamp, column: str):
    if day not in daily.index or column not in daily.columns:
        return None
    val = daily.at[day, column]
    return None if is_missing(val) else val


def _ms(kmh) -> str:
    """Wind speed in m/s, the unit used by Mongolian weather forecasts."""
    return "—" if kmh is None else f"{float(kmh) / 3.6:.0f} м/с"


def _wind_from(degrees) -> str:
    return "" if degrees is None else WIND_FROM_MN[int((float(degrees) % 360) / 45 + 0.5) % 8]


def _hhmm(value) -> str:
    ts = pd.to_datetime(value, errors="coerce") if value is not None else None
    return "—" if ts is None or pd.isna(ts) else f"{ts:%H:%M}"


def build_message(loc: Location, fc: ForecastData, day: pd.Timestamp, heading: str) -> str:
    """HTML-formatted Telegram message summarising one local calendar day."""
    d = lambda col: _day_value(fc.daily, day, col)  # noqa: E731
    code = d("weather_code")
    cond = describe(code)
    cond_text = CODE_MN.get(cond.code, cond.description)

    lines = [
        f"<b>{html.escape(heading)} — {html.escape(loc.name)}</b>",
        f"📅 {day:%Y-%m-%d}, {WEEKDAY_MN[day.weekday()]}",
        "",
        f"{cond.icon} <b>{html.escape(cond_text)}</b>",
        f"🌡 Температур: {fmt(d('temperature_2m_min'), '°C', 0)} … {fmt(d('temperature_2m_max'), '°C', 0)}",
        f"🤔 Мэдрэгдэх: {fmt(d('apparent_temperature_min'), '°C', 0)} … "
        f"{fmt(d('apparent_temperature_max'), '°C', 0)}",
        f"☔ Хур тунадас: {fmt(d('precipitation_probability_max'), '%', 0)} магадлал, "
        f"{fmt(d('precipitation_sum'), 'мм', 1)}",
    ]
    snow = d("snowfall_sum")
    if snow is not None and float(snow) > 0:
        lines.append(f"❄️ Цас: {fmt(snow, 'см', 1)}")
    lines += [
        f"💨 Салхи: {_wind_from(d('wind_direction_10m_dominant'))} {_ms(d('wind_speed_10m_max'))} хүртэл, "
        f"түр зуур {_ms(d('wind_gusts_10m_max'))} хүртэл ширүүснэ",
        f"🔆 UV индекс: {fmt(d('uv_index_max'), decimals=1).strip()}",
        f"🌅 Нар мандах {_hhmm(d('sunrise'))} · жаргах {_hhmm(d('sunset'))}",
    ]

    hours = fc.hourly[(fc.hourly.index >= day) & (fc.hourly.index < day + ONE_DAY)]
    if not hours.empty:
        lines += ["", "<b>Өдрийн туршид:</b>"]
        for label, h0, h1 in DAY_PARTS:
            part = hours[(hours.index.hour >= h0) & (hours.index.hour < h1)]
            if part.empty:
                continue
            cat = dominant_category(part["weather_code"])
            icon = CATEGORY_ICONS.get(cat, "❔") if cat else "❔"
            cat_text = CATEGORY_MN.get(cat, "—") if cat else "—"
            temp = part["temperature_2m"]
            temp_text = "—" if temp.isna().all() else f"{temp.min():.0f}…{temp.max():.0f}°C"
            pop = part["precipitation_probability"]
            pop_text = "" if pop.isna().all() else f", ☔ {pop.max():.0f}%"
            lines.append(f"{icon} {DAY_PART_MN[label]}: {temp_text}, {html.escape(cat_text)}{pop_text}")

    lines += ["", f"<i>Эх сурвалж: {html.escape(fc.source)} ({html.escape(fc.model)}). "
                  f"Загварын таамаг бөгөөд бодит нөхцөлөөс зөрж болно.</i>"]
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
    resp = requests.post(
        TELEGRAM_API.format(token=settings.telegram_bot_token),
        json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=settings.request_timeout_s,
    )
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or not body.get("ok"):
        raise RuntimeError(f"Telegram API error (HTTP {resp.status_code}): {body.get('description', resp.text[:200])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send the weather forecast to Telegram.")
    parser.add_argument("mode", choices=("morning", "evening"),
                        help="morning = today's forecast, evening = tomorrow's forecast")
    parser.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    args = parser.parse_args(argv)
    # Windows consoles default to a legacy code page that cannot print Cyrillic.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    heading = "Өнөөдрийн цаг агаар" if args.mode == "morning" else "Маргаашийн цаг агаар"
    failed = False
    for name in settings.telegram_locations:
        loc = LOCATIONS.get(name)
        if loc is None:
            print(f"Unknown location {name!r}; choose from: {', '.join(LOCATIONS)}", file=sys.stderr)
            failed = True
            continue
        try:
            fc = fetch_forecast(loc.latitude, loc.longitude)
            today = now_local(get_tz(fc.grid.timezone, fc.grid.utc_offset_s)).normalize()
            day = today if args.mode == "morning" else today + ONE_DAY
            if day not in fc.daily.index:
                raise WeatherAPIError(f"The forecast does not cover {day:%Y-%m-%d}.")
            text = build_message(loc, fc, day, heading)
        except WeatherAPIError as exc:
            print(f"{loc.name}: {exc}", file=sys.stderr)
            text = (f"<b>{html.escape(heading)} — {html.escape(loc.name)}</b>\n"
                    f"⚠️ Мэдээлэл авах боломжгүй: {html.escape(exc.user_message)}")
            failed = True

        if args.dry_run:
            print(text, end="\n\n")
            continue
        try:
            send_telegram(text)
            print(f"{loc.name}: sent")
        except RuntimeError as exc:
            print(f"{loc.name}: {exc}", file=sys.stderr)
            failed = True
        except requests.RequestException as exc:
            # The exception text contains the request URL, which includes the bot token.
            print(f"{loc.name}: could not reach Telegram ({type(exc).__name__})", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
