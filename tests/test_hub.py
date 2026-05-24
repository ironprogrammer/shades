"""Tests for hub helpers (apply_shades / move_shade).

Hub I/O is faked by recording send_payload calls so we can assert that
apply_shades sends ONE batched shadow desired payload covering every
named shade, instead of N sequential payloads.
"""
import asyncio

import pytest

import hub


class FakeRoller:
    def __init__(self, name, rid, online=True, signal=None):
        self.name = name
        self.id = rid
        self.online = online
        self.signal = signal


class FakeHub:
    """Stand-in for an aiopulse2 Hub that records send_payload calls."""
    def __init__(self, rollers):
        self.rollers = {r.id: r for r in rollers}
        self.sent = []

    async def send_payload(self, payload):
        self.sent.append(payload)


def _hub(*roller_specs):
    return FakeHub([FakeRoller(name, rid) for name, rid in roller_specs])


def _run(coro):
    return asyncio.run(coro)


def _desired(payload):
    return payload["args"]["desired"]["shades"]


def test_dict_shades_sends_one_batched_payload():
    h = _hub(("A", "id-a"), ("B", "id-b"))
    _run(hub.apply_shades(h, {"A": 10, "B": 90}))
    assert len(h.sent) == 1
    assert _desired(h.sent[0]) == {
        "id-a": {"movePercent": 10},
        "id-b": {"movePercent": 90},
    }
    assert h.sent[0]["method"] == "shadow"
    assert "timeStamp" in h.sent[0]["args"]


def test_list_shades_with_default_position_sends_one_batched_payload():
    h = _hub(("A", "id-a"), ("B", "id-b"))
    _run(hub.apply_shades(h, ["A", "B"], position=88))
    assert len(h.sent) == 1
    assert _desired(h.sent[0]) == {
        "id-a": {"movePercent": 88},
        "id-b": {"movePercent": 88},
    }


def test_list_shades_without_position_raises():
    h = _hub(("A", "id-a"), ("B", "id-b"))
    with pytest.raises(ValueError):
        _run(hub.apply_shades(h, ["A", "B"]))


def test_empty_dict_sends_no_payload():
    h = _hub(("A", "id-a"))
    _run(hub.apply_shades(h, {}))
    assert h.sent == []


def test_unknown_name_is_skipped_and_does_not_block_others():
    h = _hub(("A", "id-a"))
    _run(hub.apply_shades(h, {"A": 50, "Ghost": 50}))
    assert len(h.sent) == 1
    assert _desired(h.sent[0]) == {"id-a": {"movePercent": 50}}


def test_all_unknown_names_sends_no_payload():
    h = _hub(("A", "id-a"))
    _run(hub.apply_shades(h, {"Ghost": 50}))
    assert h.sent == []


def test_move_shade_sends_single_shade_batched_payload():
    h = _hub(("A", "id-a"))
    _run(hub.move_shade(h, "A", 42))
    assert len(h.sent) == 1
    assert _desired(h.sent[0]) == {"id-a": {"movePercent": 42}}
