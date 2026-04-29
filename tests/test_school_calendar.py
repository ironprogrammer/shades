"""Tests for school_calendar.py — all data is mocked, no network or real cache needed."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from school_calendar import is_school_day, get_calendar, _fetch_and_parse


# ── Shared mock calendar data ─────────────────────────────────────────────────

MOCK_CAL = {
    "fetched_at": date.today().isoformat(),
    "no_school_dates": [
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # MLK Day
        "2026-03-23", "2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27",  # spring break
        "2026-05-01",  # furlough
        "2026-05-25",  # Memorial Day
    ],
    "first_days": ["2025-08-26", "2026-08-25"],
    "last_days":  ["2026-06-05", "2027-06-04"],
}


# ── is_school_day ─────────────────────────────────────────────────────────────

class TestIsSchoolDay:
    def test_regular_weekday_is_school_day(self):
        assert is_school_day(MOCK_CAL, date(2026, 4, 24))

    def test_listed_holiday_is_not_school(self):
        assert not is_school_day(MOCK_CAL, date(2026, 1, 1))

    def test_mlk_day_is_not_school(self):
        assert not is_school_day(MOCK_CAL, date(2026, 1, 19))

    def test_spring_break_is_not_school(self):
        for day in range(23, 28):
            assert not is_school_day(MOCK_CAL, date(2026, 3, day))

    def test_furlough_day_is_not_school(self):
        assert not is_school_day(MOCK_CAL, date(2026, 5, 1))

    def test_summer_is_not_school(self):
        assert not is_school_day(MOCK_CAL, date(2026, 7, 15))

    def test_day_after_last_day_is_summer(self):
        assert not is_school_day(MOCK_CAL, date(2026, 6, 6))

    def test_last_day_of_school_is_school_day(self):
        assert is_school_day(MOCK_CAL, date(2026, 6, 5))

    def test_first_day_of_school_is_school_day(self):
        assert is_school_day(MOCK_CAL, date(2026, 8, 25))

    def test_day_before_first_day_is_summer(self):
        assert not is_school_day(MOCK_CAL, date(2026, 8, 24))

    def test_defaults_to_today(self):
        # Should not raise — just confirming the default path runs
        is_school_day(MOCK_CAL)


# ── calendar structure ────────────────────────────────────────────────────────

class TestCalendarStructure:
    def test_has_no_school_dates(self):
        assert len(MOCK_CAL["no_school_dates"]) > 0

    def test_has_first_and_last_days(self):
        assert len(MOCK_CAL["first_days"]) > 0
        assert len(MOCK_CAL["last_days"]) > 0

    def test_no_school_dates_are_iso_format(self):
        for d in MOCK_CAL["no_school_dates"]:
            date.fromisoformat(d)


# ── cache behaviour ───────────────────────────────────────────────────────────

class TestCacheBehaviour:
    def test_returns_cached_data_when_fresh(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "school_calendar_cache.json"
        cache_file.write_text(json.dumps(MOCK_CAL))
        monkeypatch.setattr("school_calendar.CACHE_FILE", cache_file)

        with patch("school_calendar._fetch_and_parse") as mock_fetch:
            result = get_calendar()
            mock_fetch.assert_not_called()

        assert result["no_school_dates"] == MOCK_CAL["no_school_dates"]

    def test_refetches_when_cache_stale(self, tmp_path, monkeypatch):
        stale = {**MOCK_CAL, "fetched_at": "2000-01-01", "no_school_dates": []}
        cache_file = tmp_path / "school_calendar_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("school_calendar.CACHE_FILE", cache_file)

        fresh = {**MOCK_CAL, "no_school_dates": ["2026-07-04"]}
        with patch("school_calendar._fetch_and_parse", return_value=fresh):
            result = get_calendar()

        assert result["no_school_dates"] == ["2026-07-04"]

    def test_writes_cache_after_fetch(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "school_calendar_cache.json"
        monkeypatch.setattr("school_calendar.CACHE_FILE", cache_file)

        with patch("school_calendar._fetch_and_parse", return_value=MOCK_CAL):
            get_calendar()

        assert cache_file.exists()
        saved = json.loads(cache_file.read_text())
        assert "fetched_at" in saved


# ── keyword detection ─────────────────────────────────────────────────────────

class TestKeywordDetection:
    """Verify that the iCal parser correctly identifies no-school events."""

    ICS_TEMPLATE = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:{summary}
DTSTART;VALUE=DATE:20260101
DTEND;VALUE=DATE:20260102
END:VEVENT
BEGIN:VEVENT
SUMMARY:Regular School Day
DTSTART;VALUE=DATE:20260105
DTEND;VALUE=DATE:20260106
END:VEVENT
END:VCALENDAR"""

    def _parse(self, summary):
        ics = self.ICS_TEMPLATE.replace(b"{summary}", summary.encode())
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock_open.return_value.__enter__.return_value
            mock_resp.read.return_value = ics
            return _fetch_and_parse()

    def test_detects_no_school(self):
        result = self._parse("No School for Students")
        assert "2026-01-01" in result["no_school_dates"]

    def test_detects_schools_closed(self):
        result = self._parse("Schools Closed Due to Holiday Break")
        assert "2026-01-01" in result["no_school_dates"]

    def test_detects_district_closed(self):
        result = self._parse("Schools & District Closed")
        assert "2026-01-01" in result["no_school_dates"]

    def test_detects_furlough(self):
        result = self._parse("Furlough Day (No school for students)")
        assert "2026-01-01" in result["no_school_dates"]

    def test_detects_holiday_break(self):
        result = self._parse("Schools Closed Due to Holiday Break")
        assert "2026-01-01" in result["no_school_dates"]

    def test_regular_day_not_flagged(self):
        result = self._parse("Regular School Day")
        assert "2026-01-05" not in result["no_school_dates"]

    def test_detects_first_day_of_school(self):
        result = self._parse("First Day of School")
        assert "2026-01-01" in result["first_days"]

    def test_detects_last_day_of_school(self):
        result = self._parse("Last Day of School")
        assert "2026-01-01" in result["last_days"]
