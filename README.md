# Ulaanbaatar Weather Dashboard

A Streamlit dashboard for weather in Ulaanbaatar and other Mongolian cities.
It shows **measured station observations** and **model forecasts** side by side,
compares three forecast models (ECMWF, GFS, ICON), and labels the source,
model, timestamp, coordinates and units of every value it displays.

> **Data integrity:** every value shown comes from a live API response. Nothing is
> simulated, hard-coded, interpolated or filled in. If a source fails, the
> dashboard shows **"Data unavailable"** plus the last successful update time. It
> never substitutes older or estimated values.

---

## Features

| Area | What it shows |
|---|---|
| **KPI cards** | Temperature, feels-like, condition, humidity, wind, precipitation probability. Each card has an **Observed** or **Forecast** badge and a timestamp. Temperature, humidity and wind use the station observation when a fresh one exists. |
| **Current weather** | Two panels side by side: *Observed* (METAR station report, including the raw METAR) and *Model current conditions* (Open-Meteo, 15-minute model step) |
| **Hourly charts** | Temperature vs feels-like; precipitation probability and amount (stacked panels on a shared time axis); wind speed, gusts and direction arrows, plus a wind rose |
| **7-day forecast** | Day cards with condition, min/max, precipitation probability and amount, and max wind with direction |
| **Temperature range** | Floating min–max bars per day, with the daily mean (average of the hourly values) |
| **Condition summary** | The dominant WMO condition for each day and each 6-hour period (Clear, Partly cloudy, Cloudy, Fog, Rain, Snow, Thunderstorm), plus hour counts per condition |
| **Model comparison** | ECMWF vs GFS vs ICON for temperature, precipitation, wind speed, wind direction and snowfall. Includes model range, average and spread (a circular mean and angular spread for direction), an hourly chart with a spread band, and daily tables. Model run times are shown. |
| **Data sources** | A table listing source, API/model, observed or forecast, last updated time, coordinates (requested and returned grid cell), data timestamp and units |
| **Sidebar** | Location (23 Mongolian cities), forecast period (Today / Tomorrow / Next 3 days / Next 7 days), °C/°F, a refresh button, optional auto-refresh (5–60 min) and the last-updated time per source |
| **Robustness** | Friendly messages for no internet, timeouts, HTTP errors, invalid JSON and missing variables. Each section fails on its own without affecting the rest. |
| **Caching** | `st.cache_data`: forecasts are cached for 10 min, observations for 5 min. Failed calls are never cached. |
| **Theming** | Follows Streamlit's light/dark theme. Condition colours are consistent across all components. |

## Data sources / APIs

| Source | Used for | Key | Notes |
|---|---|---|---|
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) `api.open-meteo.com/v1/forecast` | current, hourly and daily forecast (`best_match`) | none | `timezone=auto`, metric units. The dashboard reports the model grid cell returned. |
| Open-Meteo, `models=ecmwf_ifs025,gfs_seamless,icon_seamless` | model comparison | none | ECMWF IFS 0.25° is natively 3-hourly and Open-Meteo interpolates it to hourly |
| Open-Meteo model metadata `api.open-meteo.com/data/<model>/static/meta.json` | model run initialisation and availability time | none | used for `ecmwf_ifs025`, `ncep_gfs025`, `dwd_icon` |
| [NOAA Aviation Weather Center METAR API](https://aviationweather.gov/data/api/) `aviationweather.gov/api/data/metar` | **observed** conditions | none | uses the nearest reporting Mongolian aerodrome within 50 km whose report is under 2 h old |

**About observations:** Open-Meteo's "current" values are model output, not
measurements. Real measurements come from airport METAR reports. At the time of
writing, only **Ulaanbaatar Buyant-Ukhaa (ZMUB)** and **Chinggis Khaan Intl (ZMCK)**
publish to the international feed. Ulaanbaatar and Zuunmod therefore have
observations. Other cities show *"No weather station within 50 km…"* and use
model values only, labelled as such. Relative humidity from a station is derived
from its measured temperature and dew point (Magnus formula), and is labelled
"derived".

## Installation

Requires **Python 3.11+**.

```powershell
cd weather_dashboard

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux

pip install -r requirements.txt

# Optional: customise settings
copy .env.example .env              # cp .env.example .env on macOS / Linux
```

### Dependencies

`streamlit`, `plotly`, `pandas`, `requests`, `python-dotenv`, `tzdata` (IANA time zones on Windows).

## Running

```powershell
streamlit run app.py
```

Then open <http://localhost:8501>.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `REQUEST_TIMEOUT_SECONDS` | `15` | HTTP timeout per request |
| `CACHE_TTL_SECONDS` | `600` | cache lifetime for forecasts (observations: min(this, 300)) |
| `DEFAULT_LOCATION` | `Ulaanbaatar` | city selected on start-up |
| `OBSERVATION_MAX_DISTANCE_KM` | `50` | max station distance for observations |
| `OBSERVATION_MAX_AGE_HOURS` | `2` | older reports are shown as unavailable |
| `FORECAST_DAYS` | `7` | forecast length requested |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | Telegram bot and target chat for `notify.py` |
| `TELEGRAM_LOCATIONS` | `DEFAULT_LOCATION` | comma-separated cities to send notifications for |
| `OPEN_METEO_FORECAST_URL`, `OPEN_METEO_META_URL`, `METAR_URL` | public endpoints | override the API base URLs |

## Telegram notifications

`notify.py` sends a forecast summary (in Mongolian) to a Telegram chat, using the
same Open-Meteo forecast as the dashboard:

| Command | Sends | Scheduled at |
|---|---|---|
| `python notify.py morning` | **today's** forecast | 07:00 |
| `python notify.py evening` | **tomorrow's** forecast | 20:00 |

Each message gives the condition, min/max and feels-like temperature, precipitation
probability and amount, snowfall, wind (m/s, with gusts and direction), UV index,
sunrise/sunset, and a night / morning / afternoon / evening breakdown. If the
forecast cannot be fetched, the message says the data is unavailable. No values
are substituted.

**Setup**

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Send your bot any message. Then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
   For a group, add the bot to the group first. For a channel, make the bot an admin.
3. In `.env`, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Optionally set
   `TELEGRAM_LOCATIONS`, a comma-separated list of cities that each get their own message.
4. Test it: `python notify.py evening --dry-run` prints the message without
   sending it. `python notify.py evening` sends it.
5. Schedule it with Windows Task Scheduler:

   ```powershell
   .\scripts\register_telegram_tasks.ps1                                   # 07:00 and 20:00
   .\scripts\register_telegram_tasks.ps1 -MorningTime 07:30 -EveningTime 21:00
   .\scripts\register_telegram_tasks.ps1 -Unregister                       # remove both tasks
   ```

   The tasks run while you are logged on. If the PC was asleep at the scheduled
   time, the task runs as soon as the PC wakes. On Linux/macOS, use cron instead:
   `0 7 * * * cd /path/to/weather_dashboard && .venv/bin/python notify.py morning`.

## Project structure

```
weather_dashboard/
├── app.py                  # entry point: page layout, sidebar, caching, refresh
├── notify.py               # Telegram notifications (morning: today, evening: tomorrow)
├── config.py               # settings from environment / .env
├── requirements.txt
├── README.md
├── .env.example
├── .streamlit/config.toml
├── scripts/
│   └── register_telegram_tasks.ps1  # Windows Task Scheduler jobs for notify.py
├── data/
│   └── locations.py        # city coordinates + METAR station list
├── services/
│   └── weather_api.py      # Open-Meteo + METAR clients, validation, error mapping
├── components/
│   ├── cards.py            # CSS, KPI cards, badges, panels, HTML tables
│   ├── charts.py           # Plotly figure builders
│   ├── forecast.py         # 7-day cards, condition summary grid
│   └── sections.py         # page sections (current, charts, model comparison, sources)
└── utils/
    ├── weather_codes.py    # WMO code -> description / icon / category
    ├── analysis.py         # period filtering, condition grid, model statistics
    ├── units.py            # unit conversion & formatting, geo / angle helpers
    └── timefmt.py          # time-zone aware timestamp formatting
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` opens the Microsoft Store | Install Python from python.org or with `winget install Python.Python.3.12`, then open a new terminal |
| "Could not connect to the weather service" | Check your internet connection and any proxy or firewall that might block `api.open-meteo.com` and `aviationweather.gov`, then click **Refresh Weather Data** |
| "did not respond within 15 s (timeout)" | The service is slow. Retry, or raise `REQUEST_TIMEOUT_SECONDS` in `.env` |
| "HTTP 429" | The Open-Meteo free tier rate-limited you. Wait a minute. Caching keeps normal use well below the limit |
| Observed panel says "No weather station within 50 km" | Expected for most cities outside Ulaanbaatar. See *About observations* above |
| Observed panel says the report is too old | The station has not reported recently. Stale data is deliberately not shown as current |
| `DLL load failed … Application Control policy` (pyarrow) | Some locked-down Windows machines block pyarrow's DLL. This app renders its tables as HTML and does not need pyarrow |
| Time zone errors on Windows | Make sure `tzdata` is installed (`pip install -r requirements.txt`) |
| Port already in use | `streamlit run app.py --server.port 8502` |

## Disclaimer

Forecast values are model predictions and may differ from actual observed
conditions. Station observations may be taken some distance from the selected
location.
