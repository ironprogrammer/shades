#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CACHE_FILE = Path(__file__).parent / "weather_cache.json"
TZ = ZoneInfo(os.environ["TIMEZONE"])
API_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&daily=temperature_2m_max,sunset"
    "&temperature_unit={temp_unit}"
    "&timezone={tz}"
    "&forecast_days=1"
)


def _fetch(lat, lon):
    url = API_URL.format(
        lat=lat, lon=lon,
        tz=urllib.parse.quote(os.environ["TIMEZONE"], safe=""),
        temp_unit=os.environ.get("TEMP_UNIT", "fahrenheit"),
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    high_f = data["daily"]["temperature_2m_max"][0]
    sunset_str = data["daily"]["sunset"][0]
    sunset = datetime.fromisoformat(sunset_str).replace(tzinfo=TZ)
    return {"high_f": high_f, "sunset_iso": sunset.isoformat()}


def get_weather(lat, lon):
    today = date.today().isoformat()
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())
        if cache.get("date") == today:
            return {
                "high_f": cache["high_f"],
                "sunset": datetime.fromisoformat(cache["sunset_iso"]),
            }
    data = _fetch(lat, lon)
    CACHE_FILE.write_text(json.dumps({"date": today, **data}, indent=2))
    return {
        "high_f": data["high_f"],
        "sunset": datetime.fromisoformat(data["sunset_iso"]),
    }
