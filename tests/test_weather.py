"""Tests for weather.py — all HTTP calls are mocked, sunset computed locally via astral."""
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

import weather
from weather import get_weather, _fetch, _compute_sunset

TZ = ZoneInfo("America/Los_Angeles")
TODAY = date.today().isoformat()

MOCK_API_RESPONSE = {
    "daily": {
        "time": [TODAY, "2099-01-02", "2099-01-03"],
        "temperature_2m_max": [62.5, 70.0, 55.0],
    }
}


def make_mock_urlopen(payload: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=mock_resp)


# ── _fetch ────────────────────────────────────────────────────────────────────

class TestFetch:
    def test_returns_dict_keyed_by_date(self):
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = _fetch("45.0", "-122.0")
        assert TODAY in result
        assert result[TODAY]["high_f"] == 62.5

    def test_includes_all_forecast_days(self):
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = _fetch("45.0", "-122.0")
        assert len(result) == 3

    def test_does_not_request_sunset(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(MOCK_API_RESPONSE).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp
        with patch("urllib.request.urlopen", fake_urlopen):
            _fetch("45.0", "-122.0")
        assert "sunset" not in captured["url"]

    def test_url_includes_temp_unit(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(MOCK_API_RESPONSE).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _fetch("45.0", "-122.0")
        assert "fahrenheit" in captured["url"]


# ── _compute_sunset ───────────────────────────────────────────────────────────

class TestComputeSunset:
    def test_returns_timezone_aware_datetime(self):
        result = _compute_sunset("45.5", "-122.6", date(2026, 6, 21))
        assert result.tzinfo is not None

    def test_summer_solstice_sunset_is_evening(self):
        # Portland summer solstice sunset is ~21:00 local
        result = _compute_sunset("45.5", "-122.6", date(2026, 6, 21))
        assert 20 <= result.hour <= 22

    def test_winter_solstice_sunset_earlier_than_summer(self):
        winter = _compute_sunset("45.5", "-122.6", date(2026, 12, 21))
        summer = _compute_sunset("45.5", "-122.6", date(2026, 6, 21))
        # Compare hour-of-day in local tz
        assert winter.hour < summer.hour


# ── get_weather ───────────────────────────────────────────────────────────────

class TestGetWeather:
    def test_returns_high_f_and_sunset(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weather.CACHE_FILE", tmp_path / "weather_cache.json")
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = get_weather("45.0", "-122.0")
        assert result["high_f"] == 62.5
        assert isinstance(result["sunset"], datetime)

    def test_uses_cache_when_fresh(self, tmp_path, monkeypatch):
        cache = {
            "fetched_at": TODAY,
            "days": {TODAY: {"high_f": 55.0}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(cache))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = get_weather("45.0", "-122.0")
            mock_urlopen.assert_not_called()

        assert result["high_f"] == 55.0

    def test_refetches_when_cache_stale(self, tmp_path, monkeypatch):
        stale = {
            "fetched_at": "2000-01-01",
            "days": {"2000-01-01": {"high_f": 0.0}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)

        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = get_weather("45.0", "-122.0")

        assert result["high_f"] == 62.5

    def test_sunset_is_timezone_aware(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weather.CACHE_FILE", tmp_path / "weather_cache.json")
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = get_weather("45.0", "-122.0")
        assert result["sunset"].tzinfo is not None

    def test_sunset_is_in_evening_for_temperate_lat(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weather.CACHE_FILE", tmp_path / "weather_cache.json")
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = get_weather("45.5", "-122.6")
        # Sanity check: real sunset always between 16:00 and 22:00 at this latitude
        assert 16 <= result["sunset"].hour <= 22

    def test_writes_multi_day_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "weather_cache.json"
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            get_weather("45.0", "-122.0")

        cache = json.loads(cache_file.read_text())
        assert cache["fetched_at"] == TODAY
        assert len(cache["days"]) == 3

    def test_cache_does_not_store_sunset(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "weather_cache.json"
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            get_weather("45.0", "-122.0")

        cache = json.loads(cache_file.read_text())
        for day_data in cache["days"].values():
            assert "sunset_iso" not in day_data
            assert "sunset" not in day_data


# ── retry + fallback ──────────────────────────────────────────────────────────

class TestRetryAndFallback:
    def test_retries_on_failure_then_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weather.CACHE_FILE", tmp_path / "weather_cache.json")
        monkeypatch.setattr("weather.time.sleep", lambda _: None)

        calls = {"n": 0}
        def flaky(lat, lon):
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("simulated")
            return {TODAY: {"high_f": 99.0}}

        monkeypatch.setattr("weather._fetch", flaky)
        result = get_weather("45.0", "-122.0")
        assert calls["n"] == 3
        assert result["high_f"] == 99.0

    def test_raises_after_all_retries_when_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weather.CACHE_FILE", tmp_path / "weather_cache.json")
        monkeypatch.setattr("weather.time.sleep", lambda _: None)
        monkeypatch.setattr("weather._fetch", lambda l, o: (_ for _ in ()).throw(TimeoutError("x")))

        with pytest.raises(TimeoutError):
            get_weather("45.0", "-122.0")

    def test_falls_back_to_stale_cache_when_today_present(self, tmp_path, monkeypatch):
        stale = {
            "fetched_at": "2000-01-01",
            "days": {TODAY: {"high_f": 42.0}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        monkeypatch.setattr("weather.time.sleep", lambda _: None)
        monkeypatch.setattr("weather._fetch", lambda l, o: (_ for _ in ()).throw(TimeoutError("x")))

        result = get_weather("45.0", "-122.0")
        assert result["high_f"] == 42.0
        # Sunset still computed locally — not pulled from stale cache
        assert isinstance(result["sunset"], datetime)

    def test_raises_when_cache_lacks_today(self, tmp_path, monkeypatch):
        stale = {
            "fetched_at": "2000-01-01",
            "days": {"1999-12-31": {"high_f": 0.0}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        monkeypatch.setattr("weather.time.sleep", lambda _: None)
        monkeypatch.setattr("weather._fetch", lambda l, o: (_ for _ in ()).throw(TimeoutError("x")))

        with pytest.raises(TimeoutError):
            get_weather("45.0", "-122.0")
