"""Shared fixtures and environment setup for all tests."""
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Minimal env so modules that call os.environ[] at import time don't blow up
os.environ.setdefault("HUB_IP", "192.168.0.1")
os.environ.setdefault("TIMEZONE", "America/Los_Angeles")
os.environ.setdefault("TEMP_UNIT", "fahrenheit")
os.environ.setdefault("WEATHER_LAT", "0.0")
os.environ.setdefault("WEATHER_LON", "0.0")
os.environ.setdefault("POLL_INTERVAL_MINUTES", "5")
os.environ.setdefault("SCHOOL_CALENDAR_ICS_URL", "https://example.com/cal.ics")
os.environ.setdefault("RESEND_API_KEY", "re_test")
os.environ.setdefault("EMAIL_FROM", "test@example.com")
os.environ.setdefault("EMAIL_TO", "test@example.com")

TZ = ZoneInfo("America/Los_Angeles")
