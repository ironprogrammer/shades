"""Tests for weather.py — all HTTP calls are mocked."""
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

import weather
from weather import get_weather, _fetch

TZ = ZoneInfo("America/Los_Angeles")
TODAY = date.today().isoformat()

MOCK_API_RESPONSE = {
    "daily": {
        "time": [TODAY, "2099-01-02", "2099-01-03"],
        "temperature_2m_max": [62.5, 70.0, 55.0],
        "sunset": ["2026-04-28T20:13", "2099-01-02T17:30", "2099-01-03T17:31"],
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

    def test_sunset_iso_parseable(self):
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = _fetch("45.0", "-122.0")
        dt = datetime.fromisoformat(result[TODAY]["sunset_iso"])
        assert dt.hour == 20
        assert dt.minute == 13

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
            "days": {TODAY: {"high_f": 55.0, "sunset_iso": "2026-04-28T20:00:00-07:00"}},
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
            "days": {"2000-01-01": {"high_f": 0.0, "sunset_iso": "2000-01-01T18:00:00-08:00"}},
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

    def test_writes_multi_day_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "weather_cache.json"
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            get_weather("45.0", "-122.0")

        cache = json.loads(cache_file.read_text())
        assert cache["fetched_at"] == TODAY
        assert len(cache["days"]) == 3


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
            return {TODAY: {"high_f": 99.0, "sunset_iso": "2026-04-28T20:00:00-07:00"}}

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
            "days": {TODAY: {"high_f": 42.0, "sunset_iso": "2026-04-28T19:00:00-07:00"}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        monkeypatch.setattr("weather.time.sleep", lambda _: None)
        monkeypatch.setattr("weather._fetch", lambda l, o: (_ for _ in ()).throw(TimeoutError("x")))

        result = get_weather("45.0", "-122.0")
        assert result["high_f"] == 42.0

    def test_raises_when_cache_lacks_today(self, tmp_path, monkeypatch):
        stale = {
            "fetched_at": "2000-01-01",
            "days": {"1999-12-31": {"high_f": 0.0, "sunset_iso": "1999-12-31T17:00:00-08:00"}},
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(stale))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)
        monkeypatch.setattr("weather.time.sleep", lambda _: None)
        monkeypatch.setattr("weather._fetch", lambda l, o: (_ for _ in ()).throw(TimeoutError("x")))

        with pytest.raises(TimeoutError):
            get_weather("45.0", "-122.0")
