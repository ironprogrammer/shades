"""Tests for scheduler.py — time/window matching and scene filtering."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scheduler import _in_window
from tests.conftest import TZ

# ── _in_window ────────────────────────────────────────────────────────────────

class TestInWindowFixedTime:
    SCHEDULE = {"enabled": True, "time": "07:30", "days": ["mon", "tue", "wed", "thu", "fri"]}

    def test_fires_at_exact_time(self):
        now = datetime(2026, 4, 28, 7, 30, tzinfo=TZ)  # Tuesday
        assert _in_window(self.SCHEDULE, now)

    def test_fires_within_poll_window(self):
        now = datetime(2026, 4, 28, 7, 33, tzinfo=TZ)
        assert _in_window(self.SCHEDULE, now)

    def test_does_not_fire_after_poll_window(self):
        now = datetime(2026, 4, 28, 7, 35, tzinfo=TZ)
        assert not _in_window(self.SCHEDULE, now)

    def test_does_not_fire_before_time(self):
        now = datetime(2026, 4, 28, 7, 29, tzinfo=TZ)
        assert not _in_window(self.SCHEDULE, now)

    def test_does_not_fire_on_weekend(self):
        now = datetime(2026, 5, 2, 7, 30, tzinfo=TZ)  # Saturday
        assert not _in_window(self.SCHEDULE, now)

    def test_fires_on_all_weekdays(self):
        # Mon Apr 27 through Fri May 1
        for day in range(27, 32):
            month = 4 if day <= 30 else 5
            d = day if day <= 30 else day - 30
            now = datetime(2026, month, d, 7, 30, tzinfo=TZ)
            assert _in_window(self.SCHEDULE, now), f"Should fire on day {now.strftime('%A')}"


class TestInWindowPolling:
    SCHEDULE = {
        "enabled": True,
        "window": ["16:30", "20:05"],
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    }

    def test_fires_at_window_start(self):
        now = datetime(2026, 4, 28, 16, 30, tzinfo=TZ)
        assert _in_window(self.SCHEDULE, now)

    def test_fires_mid_window(self):
        now = datetime(2026, 4, 28, 18, 0, tzinfo=TZ)
        assert _in_window(self.SCHEDULE, now)

    def test_fires_at_window_end(self):
        now = datetime(2026, 4, 28, 20, 5, tzinfo=TZ)
        assert _in_window(self.SCHEDULE, now)

    def test_does_not_fire_before_window(self):
        now = datetime(2026, 4, 28, 16, 29, tzinfo=TZ)
        assert not _in_window(self.SCHEDULE, now)

    def test_does_not_fire_after_window(self):
        now = datetime(2026, 4, 28, 20, 6, tzinfo=TZ)
        assert not _in_window(self.SCHEDULE, now)

    def test_fires_on_weekend(self):
        now = datetime(2026, 5, 2, 18, 0, tzinfo=TZ)  # Saturday
        assert _in_window(self.SCHEDULE, now)
