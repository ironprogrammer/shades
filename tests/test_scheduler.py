"""Tests for scheduler.py — time/window matching and scene filtering."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import hub
import scheduler
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



class TestInWindowDstAwareTime:
    SCHEDULE = {"enabled": True, "time": {"dst": "11:00", "std": "10:00"}, "days": ["mon", "tue", "wed", "thu", "fri"]}

    def test_uses_dst_time_in_summer(self):
        assert _in_window(self.SCHEDULE, datetime(2026, 7, 7, 11, 0, tzinfo=TZ))
        assert not _in_window(self.SCHEDULE, datetime(2026, 7, 7, 10, 0, tzinfo=TZ))

    def test_uses_std_time_in_winter(self):
        assert _in_window(self.SCHEDULE, datetime(2026, 12, 8, 10, 0, tzinfo=TZ))
        assert not _in_window(self.SCHEDULE, datetime(2026, 12, 8, 11, 0, tzinfo=TZ))


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


# ── main ──────────────────────────────────────────────────────────────────────

FIXTURE_SCENES = Path(__file__).parent / "fixtures" / "scenes"


class FakeHubConnection:
    """Stands in for hub.HubConnection and records which scenes ran."""

    def __init__(self):
        self.ran = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 7, 12, 0, tzinfo=tz)


class TestMain:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        self.hub = FakeHubConnection()
        self.ctx = {"is_school_day": True}
        monkeypatch.setattr(scheduler, "SCENES_DIR", FIXTURE_SCENES)
        monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
        monkeypatch.setattr(scheduler, "STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(scheduler, "_build_context", lambda now: self.ctx)
        monkeypatch.setattr(hub, "HubConnection", lambda: self.hub)
        monkeypatch.setattr(scheduler.asyncio, "sleep", self._no_sleep)

    @staticmethod
    async def _no_sleep(_seconds):
        pass

    def test_runs_only_enabled_scenes_that_pass_should_run(self):
        # disabled.py is skipped, and broken.py raising in should_run doesn't block enabled.py
        asyncio.run(scheduler.main())
        assert self.hub.ran == ["enabled"]

    def test_skips_scene_when_should_run_is_false(self):
        self.ctx["is_school_day"] = False
        asyncio.run(scheduler.main())
        assert self.hub.ran == []

    def test_fires_once_per_day(self):
        asyncio.run(scheduler.main())
        asyncio.run(scheduler.main())
        assert self.hub.ran == ["enabled"]
