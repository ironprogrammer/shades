#!/usr/bin/env python3
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CACHE_FILE = Path(__file__).parent / "weather_cache.json"
TZ = ZoneInfo(os.environ["TIMEZONE"])
FORECAST_DAYS = 3
RETRY_ATTEMPTS = 3
API_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&daily=temperature_2m_max"
    "&temperature_unit={temp_unit}"
    "&timezone={tz}"
    "&forecast_days={days}"
)


def _fetch(lat, lon):
    url = API_URL.format(
        lat=lat, lon=lon,
        tz=urllib.parse.quote(os.environ["TIMEZONE"], safe=""),
        temp_unit=os.environ.get("TEMP_UNIT", "fahrenheit"),
        days=FORECAST_DAYS,
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    return {
        iso_date: {"high_f": high_f}
        for iso_date, high_f in zip(
            data["daily"]["time"], data["daily"]["temperature_2m_max"]
        )
    }


def _fetch_with_retry(lat, lon):
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return _fetch(lat, lon)
        except Exception as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS - 1:
                delay = 2 ** attempt
                print(f"  weather fetch failed ({exc}); retrying in {delay}s")
                time.sleep(delay)
    raise last_exc


def _compute_sunset(lat, lon, d):
    loc = LocationInfo(latitude=float(lat), longitude=float(lon), timezone=str(TZ))
    return sun(loc.observer, date=d, tzinfo=loc.timezone)["sunset"]


def get_weather(lat, lon):
    today = date.today()
    today_iso = today.isoformat()
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else None

    sunset = _compute_sunset(lat, lon, today)

    if cache and cache.get("fetched_at") == today_iso and today_iso in cache.get("days", {}):
        return {"high_f": cache["days"][today_iso]["high_f"], "sunset": sunset}

    try:
        days = _fetch_with_retry(lat, lon)
        CACHE_FILE.write_text(json.dumps({"fetched_at": today_iso, "days": days}, indent=2))
        return {"high_f": days[today_iso]["high_f"], "sunset": sunset}
    except Exception as exc:
        if cache and today_iso in cache.get("days", {}):
            print(f"  weather fetch failed ({exc}); falling back to cached forecast from {cache.get('fetched_at')}")
            return {"high_f": cache["days"][today_iso]["high_f"], "sunset": sunset}
        raise
