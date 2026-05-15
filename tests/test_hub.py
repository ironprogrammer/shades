"""Tests for hub helpers (apply_shades). Hub I/O itself is not exercised."""
import asyncio

import pytest

import hub


class FakeHub:
    """Stand-in for an aiopulse2 Hub that records move_shade calls."""
    def __init__(self):
        self.calls = []


async def _fake_move_shade(fake_hub, name, position):
    fake_hub.calls.append((name, position))


@pytest.fixture(autouse=True)
def _patch_move_shade(monkeypatch):
    monkeypatch.setattr(hub, "move_shade", _fake_move_shade)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_dict_shades_applies_per_shade_position():
    h = FakeHub()
    _run(hub.apply_shades(h, {"A": 10, "B": 90}))
    assert h.calls == [("A", 10), ("B", 90)]


def test_list_shades_with_default_position():
    h = FakeHub()
    _run(hub.apply_shades(h, ["A", "B"], position=88))
    assert h.calls == [("A", 88), ("B", 88)]


def test_list_shades_without_position_raises():
    h = FakeHub()
    with pytest.raises(ValueError):
        _run(hub.apply_shades(h, ["A", "B"]))


def test_empty_dict_makes_no_calls():
    h = FakeHub()
    _run(hub.apply_shades(h, {}))
    assert h.calls == []
