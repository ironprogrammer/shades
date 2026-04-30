#!/usr/bin/env python3
"""
Fetches and caches a school district iCal feed.
Extracts no-school dates and school year start/end for use by the scheduler.
"""
import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import icalendar
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CACHE_FILE = Path(__file__).parent / "school_calendar_cache.json"
ICS_URL = os.environ["SCHOOL_CALENDAR_ICS_URL"]
CACHE_DAYS = 7
RETRY_ATTEMPTS = 3

# Event summaries containing any of these strings (case-insensitive) are
# treated as no-school days. Expand this list to match your district's wording.
NO_SCHOOL_KEYWORDS = [
    "no school",
    "schools closed",
    "district closed",
    "furlough",
    "holiday break",
]


def _expand_dates(start, end):
    """Expand a date range to individual ISO date strings. end is exclusive (iCal spec)."""
    dates = []
    d = start
    while d < end:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    return dates


def _fetch_ics():
    req = urllib.request.Request(ICS_URL, headers={"User-Agent": "Mozilla/5.0"})
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS - 1:
                delay = 2 ** attempt
                print(f"  school calendar fetch failed ({exc}); retrying in {delay}s")
                time.sleep(delay)
    raise last_exc


def _fetch_and_parse():
    content = _fetch_ics()

    cal = icalendar.Calendar.from_ical(content)

    no_school = set()
    first_days = []
    last_days = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", ""))
        summary_lower = summary.lower()
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")

        if not dtstart:
            continue

        start_val = dtstart.dt
        end_val = dtend.dt if dtend else None

        # Only handle all-day (date) events
        if not isinstance(start_val, date) or isinstance(start_val, datetime):
            continue

        end_val = (
            end_val
            if isinstance(end_val, date) and not isinstance(end_val, datetime)
            else start_val + timedelta(days=1)
        )

        if summary_lower.startswith("first day of school"):
            first_days.append(start_val.isoformat())
        elif summary_lower.startswith("last day of school"):
            last_days.append(start_val.isoformat())

        if any(kw in summary_lower for kw in NO_SCHOOL_KEYWORDS):
            no_school.update(_expand_dates(start_val, end_val))

    return {
        "no_school_dates": sorted(no_school),
        "first_days": sorted(first_days),
        "last_days": sorted(last_days),
    }


def get_calendar():
    today = date.today()
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else None
    if cache:
        fetched = date.fromisoformat(cache.get("fetched_at", "2000-01-01"))
        if (today - fetched).days < CACHE_DAYS:
            return cache

    print("Refreshing school calendar cache...")
    try:
        data = _fetch_and_parse()
    except Exception as exc:
        if cache:
            print(f"  fetch failed ({exc}); falling back to stale cache from {cache.get('fetched_at')}")
            return cache
        raise
    cache = {"fetched_at": today.isoformat(), **data}
    CACHE_FILE.write_text(json.dumps(cache, indent=2))
    return cache


def is_school_day(cal, d=None):
    """True if d is a regular school day (not a no-school day, not summer)."""
    if d is None:
        d = date.today()

    if d.isoformat() in cal["no_school_dates"]:
        return False

    # Summer: after last day of school, before next first day
    today_str = d.isoformat()
    last_day = next(
        (date.fromisoformat(ld) for ld in reversed(sorted(cal["last_days"])) if ld <= today_str),
        None,
    )
    next_first_day = next(
        (date.fromisoformat(fd) for fd in sorted(cal["first_days"]) if fd > today_str),
        None,
    )
    if last_day and next_first_day and d > last_day:
        return False

    return True


if __name__ == "__main__":
    cal = get_calendar()
    today = date.today()
    print(f"No-school dates: {len(cal['no_school_dates'])}")
    print(f"First days of school: {cal['first_days']}")
    print(f"Last days of school:  {cal['last_days']}")
    print(f"Today ({today}) is {'a school day' if is_school_day(cal) else 'NOT a school day'}.")
