"""Tests for each scene's should_run() logic."""
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_ctx, TZ

SCENES_DIR = Path(__file__).parent.parent / "scenes"


def load_scene(name):
    path = SCENES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Reusable datetimes
TUESDAY   = datetime(2026, 4, 28, 12, 0, tzinfo=TZ)  # school day, DST
FRIDAY    = datetime(2026, 5,  1, 12, 0, tzinfo=TZ)  # furlough day, DST
DECEMBER  = datetime(2025, 12, 15, 12, 0, tzinfo=TZ) # standard time


# ── wake ──────────────────────────────────────────────────────────────────────

class TestWake:
    scene = load_scene("wake")

    def test_fires_on_school_day(self):
        assert self.scene.should_run(make_ctx(TUESDAY, is_school_day=True))

    def test_skips_on_no_school_day(self):
        assert not self.scene.should_run(make_ctx(TUESDAY, is_school_day=False))

    def test_schedule_is_weekdays_only(self):
        assert self.scene.SCHEDULE["days"] == ["mon", "tue", "wed", "thu", "fri"]

    def test_enabled_by_default(self):
        assert self.scene.SCHEDULE.get("enabled", True)

    def test_fires_at_0730(self):
        assert self.scene.SCHEDULE["time"] == "07:30"


# ── wake_full ─────────────────────────────────────────────────────────────────

class TestWakeFull:
    scene = load_scene("wake_full")

    def test_fires_on_school_day(self):
        assert self.scene.should_run(make_ctx(TUESDAY, is_school_day=True))

    def test_skips_on_no_school_day(self):
        assert not self.scene.should_run(make_ctx(TUESDAY, is_school_day=False))

    def test_moves_to_fully_open(self):
        assert self.scene.POSITION == 0

    def test_fires_after_wake(self):
        assert self.scene.SCHEDULE["time"] == "07:45"


# ── south_sun ─────────────────────────────────────────────────────────────────

class TestSouthSun:
    scene = load_scene("south_sun")

    def test_fires_above_threshold(self):
        assert self.scene.should_run(make_ctx(TUESDAY, high_f=65.0))

    def test_skips_below_threshold(self):
        assert not self.scene.should_run(make_ctx(TUESDAY, high_f=55.0))

    def test_skips_at_exact_threshold(self):
        assert not self.scene.should_run(make_ctx(TUESDAY, high_f=60.0))

    def test_fires_one_degree_above_threshold(self):
        assert self.scene.should_run(make_ctx(TUESDAY, high_f=60.1))

    def test_skips_when_high_is_none(self):
        ctx = make_ctx(TUESDAY)
        ctx["weather"]["high_f"] = None
        assert not self.scene.should_run(ctx)

    def test_runs_every_day(self):
        assert set(self.scene.SCHEDULE["days"]) == {"mon","tue","wed","thu","fri","sat","sun"}


# ── evening_close ─────────────────────────────────────────────────────────────

class TestEveningClose:
    scene = load_scene("evening_close")

    # Standard time (DST off)
    def test_standard_time_fires_at_1700(self):
        now = DECEMBER.replace(hour=17, minute=0)
        assert self.scene.should_run(make_ctx(now))

    def test_standard_time_fires_after_1700(self):
        now = DECEMBER.replace(hour=18, minute=0)
        assert self.scene.should_run(make_ctx(now))

    def test_standard_time_skips_before_1700(self):
        now = DECEMBER.replace(hour=16, minute=59)
        assert not self.scene.should_run(make_ctx(now))

    # DST — sunset before 8 PM cap
    def test_dst_fires_at_sunset_when_before_cap(self):
        now = TUESDAY.replace(hour=19, minute=30)
        ctx = make_ctx(now, sunset_hour=19, sunset_minute=30)
        assert self.scene.should_run(ctx)

    def test_dst_skips_before_sunset(self):
        now = TUESDAY.replace(hour=19, minute=0)
        ctx = make_ctx(now, sunset_hour=19, sunset_minute=30)
        assert not self.scene.should_run(ctx)

    # DST — sunset after 8 PM cap
    def test_dst_caps_at_2000_when_sunset_is_later(self):
        now = TUESDAY.replace(hour=20, minute=0)
        ctx = make_ctx(now, sunset_hour=20, sunset_minute=30)
        assert self.scene.should_run(ctx)

    def test_dst_skips_before_cap_when_sunset_is_late(self):
        now = TUESDAY.replace(hour=19, minute=59)
        ctx = make_ctx(now, sunset_hour=20, sunset_minute=30)
        assert not self.scene.should_run(ctx)

    def test_runs_every_day(self):
        assert set(self.scene.SCHEDULE["days"]) == {"mon","tue","wed","thu","fri","sat","sun"}

    def test_closes_fully(self):
        assert self.scene.POSITION == 100
