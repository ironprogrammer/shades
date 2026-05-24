# Scenes — Batched Group Moves

**Status:** implemented. See `hub.py` (`apply_shades`, `move_shade`) and
`tests/test_hub.py`. Background and rationale captured below in case the
batched path ever needs to be revisited or extended.

Builds on findings documented in `docs/WS_API.md`.

## Motivation

The earlier `hub.apply_shades()` / `move_shade()` iterated over shades
and sent one WebSocket payload per shade. The hub's `shadow` desired
channel supports **N shades in a single payload** — sending them
batched is the "group logic" the official Pulse LinQ docs talk about.

Fewer round-trips, less hub load, and the most likely API the Automate
Shades App uses for its scene controls.

## What the implementation does

`apply_shades(hub, shades, position=None)` resolves each name to a
roller, builds a single `{roller_id: {"movePercent": N}}` map, and
sends ONE `shadow` desired payload covering all of them at once via
`hub.send_payload(...)` — already an `aiopulse2.Hub` method that
pushes a raw payload onto its existing websocket. No new dependency,
no new connection management.

`move_shade(hub, name, position)` is now a thin wrapper:
`apply_shades(hub, {name: position})`. Single-shade callers and tests
keep working.

Per-shade print lines (and the `(reported offline, -XX dBm)`
annotation) are preserved after the batched send completes.

## Scene file format

Scenes use a `{name: position}` dict that maps cleanly to a batched
move:

```python
# scenes/evening_close.py
SHADES = {
    "Living 1": 100,
    "Living 2": 100,
    "Living 3": 100,
    # ...
}

async def run(hub):
    from hub import apply_shades
    await apply_shades(hub, SHADES)
```

The legacy list form (`SHADES = [...]` + a shared `position` arg) still
works — `_normalize` accepts both shapes. `scenes/office_sun.py` keeps
the list form because its position is computed at runtime from
temperature; `scenes/office_mid.py` keeps the list form because it
pre-filters shades by current position before dispatching.

## What this DOESN'T fix

Be honest about scope:

- **Motors with low batteries / RF-asleep** will still miss commands.
  The hub doesn't ack at the shadow layer — you only learn a motor
  missed by polling `shadow` afterward and seeing `mp` didn't change.
- **No retry mechanism.** If a motor missed during a batched move,
  you'd need to poll-and-resend (see "Optional follow-up" below).
- **`ol` is still unreliable** — don't add filtering based on it.

## Optional follow-up: confirm-and-retry

If reliability is still an issue, layer this on (separate PR):

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
the RF position update. 5–10 seconds is reasonable.

## Testing approach

`tests/test_hub.py` uses a `FakeHub` that records `send_payload` calls,
asserting that one batched payload is sent containing the expected
per-shade map. The same pattern covers `move_shade` (one-shade batched
payload), unknown-name skips, and the empty-input no-op.

## Things to verify against the real hub

Single shot of confidence to gain before relying on this for
`evening_close`:

1. Trigger a scene with 4+ shades. Watch `wireshark` or a `tcpdump` on
   port 443 to confirm ONE payload went out (not N).
2. Diff `shadow` `mp` values before and ~10s after. Count how many
   shades reached their target. Compare to the old per-shade
   `evening_close` behavior over a few nights.
3. If the batched path doesn't materially improve reliability, the
   bottleneck is RF reach (batteries, distance), not the dispatch
   pattern. See `WS_API.md` "RF reliability caveats".

## Out of scope (separate efforts)

- Migrating off `aiopulse2` to a hand-rolled WS client. The library
  has quirks but works for what we need.
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
