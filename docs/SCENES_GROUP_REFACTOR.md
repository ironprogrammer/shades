# Scenes Refactor — Batched Group Moves

A concrete plan for the next agent. Builds on findings documented in
`docs/WS_API.md`.

## Motivation

Today's `hub.apply_shades()` and `move_shade()` iterate over shades and
send one WebSocket payload per shade. The hub's `shadow` desired channel
supports **N shades in a single payload** — sending them batched is the
"group logic" the official Pulse LinQ docs talk about.

It's also fewer round-trips, less hub load, and the most likely API the
Automate Shades App uses for its scene controls.

## The change in one line

In `hub.py`, replace the per-shade loop in `apply_shades()` with one
batched WS `shadow` desired send that includes every named shade in the
scene at once.

## Concrete diff sketch

**Before** (`hub.py`):

```python
async def apply_shades(hub, shades, position=None):
    if isinstance(shades, dict):
        items = list(shades.items())
    else:
        if position is None:
            raise ValueError("position is required when shades is not a dict")
        items = [(name, position) for name in shades]
    for name, pos in items:
        await move_shade(hub, name, pos)   # one WS send per shade
```

**After:**

```python
import time

async def apply_shades(hub, shades, position=None):
    items = _normalize(shades, position)
    if not items:
        return
    desired_shades = {}
    by_name = {r.name: r for r in hub.rollers.values()}
    for name, pos in items:
        roller = by_name.get(name)
        if roller is None:
            print(f"  WARNING: roller '{name}' not found")
            continue
        desired_shades[roller.id] = {"movePercent": int(pos)}
        print(f"  {name} -> {pos}% closed")

    if not desired_shades:
        return

    await hub.send_payload({
        "method": "shadow",
        "args": {
            "desired": {"shades": desired_shades},
            "timeStamp": time.time(),
        },
    })
```

`hub.send_payload(...)` is already an `aiopulse2.Hub` method that pushes
a raw payload onto its websocket. No new dependency, no new connection
management.

## Scene file format — no change required

Scenes already use the dict shape that maps cleanly to a batched move:

```python
# scenes/evening_close.py
SHADES = {
    "Living 1": 100,
    "Living 2": 100,
    "Living 3": 100,
    # ...
}
```

`apply_shades(hub, SHADES)` now sends ALL of them in one payload
instead of 17 sequential payloads.

A few existing scenes still use the older list form
(`SHADES = ["Living 1", ...]` + a shared `position` arg). Those work
unchanged — `_normalize` handles both shapes (see below).

```python
def _normalize(shades, position):
    if isinstance(shades, dict):
        return list(shades.items())
    if position is None:
        raise ValueError("position is required when shades is not a dict")
    return [(name, position) for name in shades]
```

## What this DOESN'T fix

Be honest with users about scope:

- **Motors with low batteries / RF-asleep** will still miss commands.
  The hub doesn't ack at the shadow layer — you only learn a motor
  missed by polling `shadow` afterward and seeing `mp` didn't change.
- **No retry mechanism is added** by this change. If a motor missed
  during a batched move, you'd need to poll-and-resend, which is a
  separate enhancement.
- **`ol` is still unreliable** — don't add filtering based on it.

## Optional follow-up: confirm-and-retry

Once batched moves are in, layer this on if reliability is still an
issue (separate PR):

```python
async def apply_shades_with_confirm(hub, items, *, retries=2, settle_seconds=8):
    targets = {<roller_id>: target_pct for ...}
    for attempt in range(retries + 1):
        await _send_batched(hub, targets)
        await asyncio.sleep(settle_seconds)  # let RF round-trips happen
        # Re-read shadow, find shades that haven't reached target
        misses = {
            rid: pct for rid, pct in targets.items()
            if abs(hub.rollers[rid].closed_percent - pct) > 5
        }
        if not misses:
            return
        targets = misses   # only re-send the ones that missed
```

The `settle_seconds` value matters — the hub's shadow doesn't update
instantly; motors need to physically move and the hub needs to receive
the RF position update. 5-10 seconds is reasonable.

## Testing approach

The original tests in `tests/test_hub.py` monkey-patched `move_shade`
to assert the per-shade call list. After the refactor:

- `move_shade` should be a thin wrapper around `apply_shades(hub, {name: pos})`
- Tests should monkey-patch `hub.send_payload` (or the equivalent) and
  assert ONE call was made containing the expected per-shade map
- See the abandoned `tcp-protocol` branch for an example of FakeHub
  pattern that records sent payloads

## Things to verify against the real hub after merging

Single shot of confidence to gain before relying on this for
`evening_close`:

1. Trigger a scene with 4+ shades. Watch `wireshark` or a `tcpdump` on
   port 443 to confirm ONE payload went out (not N).
2. Diff `shadow` `mp` values before and ~10s after. Count how many
   shades reached their target. Compare to current per-shade
   `evening_close` behavior over a few nights.
3. If the batched path doesn't materially improve reliability, the
   bottleneck is RF reach (batteries, distance), not the dispatch
   pattern. See `WS_API.md` "RF reliability caveats" section.

## Out of scope for this refactor (separate efforts)

- Migrating off `aiopulse2` to a hand-rolled WS client. The library
  has its quirks but works for what we need.
- TCP/1487 ASCII protocol exploration. See the abandoned
  `tcp-protocol` branch for ~150 LoC of research code, a verified
  protocol doc (`docs/PROTOCOL.md` on that branch), and the conclusion
  that TCP/1487 is "for diagnostics, not scene control" per the
  vendor's own LinQ docs.
- Replacing the cached `ol` field with our own derivation. WS shadow's
  `ol` is unreliable but our own retries would be equally unreliable
  given underlying RF behavior.
- Adding a hub-side scene trigger via RPC. Probed extensively
  (~30 method names + arg shapes) — no such method appears to exist.
  The App likely does the read-scene-def + batched-shadow dance.

## Reference: the abandoned `tcp-protocol` branch

For future digging:
- 7 commits of TCP/1487 ASCII protocol implementation
- Complete protocol vocabulary documentation (`docs/PROTOCOL.md`)
- Test fixtures captured from the live hub
- Demonstrates that TCP per-command acks don't translate to reliability
  improvements when the underlying RF medium is the actual problem

Worth keeping for reference, not worth merging.
