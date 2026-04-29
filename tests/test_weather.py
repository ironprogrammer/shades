"""Tests for weather.py — all HTTP calls are mocked."""
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

from weather import get_weather, _fetch

TZ = ZoneInfo("America/Los_Angeles")

MOCK_API_RESPONSE = {
    "daily": {
        "temperature_2m_max": [62.5],
        "sunset": ["2026-04-28T20:13"],
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
    def test_returns_high_f(self):
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = _fetch("45.0", "-122.0")
        assert result["high_f"] == 62.5

    def test_returns_sunset_iso(self):
        with patch("urllib.request.urlopen", make_mock_urlopen(MOCK_API_RESPONSE)):
            result = _fetch("45.0", "-122.0")
        assert "sunset_iso" in result
        dt = datetime.fromisoformat(result["sunset_iso"])
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
            "date": date.today().isoformat(),
            "high_f": 55.0,
            "sunset_iso": "2026-04-28T20:00:00-07:00",
        }
        cache_file = tmp_path / "weather_cache.json"
        cache_file.write_text(json.dumps(cache))
        monkeypatch.setattr("weather.CACHE_FILE", cache_file)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = get_weather("45.0", "-122.0")
            mock_urlopen.assert_not_called()

        assert result["high_f"] == 55.0

    def test_refetches_when_cache_stale(self, tmp_path, monkeypatch):
        stale = {"date": "2000-01-01", "high_f": 0.0, "sunset_iso": "2000-01-01T18:00:00-08:00"}
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
