# Pulse Pro Hub — WebSocket RPC API Reference

Empirically mapped against hub `1130415` (RF firmware B17, app firmware
1.10.0) on 2026-05-23 through direct probing. This is what the official
Automate Shades App likely uses; `aiopulse2` only uses a small subset.

## Transport

- **Endpoint:** `wss://{HUB_IP}:443/rpc`
- **TLS:** self-signed cert — must disable verification
- **Format:** JSON-RPC-ish

### Minimal Python client (no aiopulse2)

```python
import asyncio, json, ssl, time
import websockets

async def call(host, method, args=None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    payload = {"id": int(time.time() * 1000), "src": "app", "method": method}
    if args is not None:
        payload["args"] = args
    async with websockets.connect(f"wss://{host}:443/rpc", ssl=ctx) as ws:
        await ws.send(json.dumps(payload))
        return json.loads(await ws.recv())
```

### Request shape

```json
{ "id": 1234567890, "src": "app", "method": "...", "args": ... }
```

### Response shape

Success:
```json
{ "id": 1234567890, "src": "esp32_0137FC", "dst": "app", "result": ... }
```

Error (method unknown):
```json
{ "id": ..., "src": "esp32_0137FC", "dst": "app",
  "error": { "code": 404, "message": "No handler for X" } }
```

Error (method known, bad args):
```json
{ "id": ..., "src": "esp32_0137FC", "dst": "app",
  "error": { "code": -1, "message": "Bad request. ..." } }
```

The `error.code: 404` vs `error.code: -1` distinction is useful: 404 means
the method itself doesn't exist; -1 means the method exists but rejected
the argument shape. This lets you discover valid methods by probing.

## Verified methods

| Method | Args | Returns |
|---|---|---|
| `shadow` | none | Full reported state — all shades, hub identity, firmware, etc. (see schema below) |
| `shadow` | `{"desired": {...}, "timeStamp": ts}` | Same shape as no-args; the `desired` block is the hub's instruction set (see "Group moves" below) |
| `shades` | none | Array of shade ID strings, e.g. `["XJK", "OID", ...]` |
| `scenes` | none | Array of scene UUID strings |
| `scenes` | `"<uuid>"` *(raw string, not a dict)* | Scene definition: `{"<uuid>": {"devices": {"<shade_id>": {"movePercent": N}, ...}}}` |
| `timers` | none | Array of timers (empty on this hub) |

## Methods that return 404 ("No handler")

Confirmed unknown — don't bother:

`scene`, `room`, `rooms`, `group`, `groups`, `motor`, `motors`, `shade`,
`command`, `commands`, `batch`, `move`, `execute`, `list`, `info`,
`describe`, `methods`, `ping`, `config`, `system`, `status`, `state`,
`fire`, `play`, `start`, `stop_scene`, `apply`, `set`, `do`, `dispatch`,
`set_scene`, `start_scene`, `play_scene`, `apply_scene`, `active_scene`,
`tasks`, `task`, `jobs`, `job`, `events`, `event`, `set_state`, `update`,
`patch`, `post`, `scene_trigger`, `scenes_trigger`, `scene_execute`,
`scene_run`, `rpc`, `api`, `call`, `invoke`, `trigger`, `activate`,
`run`, `execute_scene`, `trigger_scene`.

## `shadow` reported schema

The `result.reported` object from a no-args `shadow` call:

```json
{
  "hubId": "1130415",
  "name": "1130415",
  "dailyReboot": false,
  "mac": "0c:b8:15:01:37:fc",
  "networkInterface": "Wi-Fi",
  "onlineLatest": 1779594785.71,
  "mfi": {
    "PD": "a7809d94adde10a3",
    "manufacturer": "Rollease Acmeda",
    "model": "MT02-0401-067001"
  },
  "firmware": { "version": "1.10.0", "RFversion": "B17" },
  "shades": {
    "JNQ": { "ol": false, "mp": 100, "ls": 1, "is": true,
             "vo": "12.6D13", "rs": -96 },
    "QGL": { "ol": false, "mp": 100, "ls": 1, "is": true,
             "rs": -92 },
    ...
  }
}
```

### Per-shade fields

| Field | Meaning | Notes |
|---|---|---|
| `mp` | Closed percent (0-100) | Hub's cached value — last reported by motor |
| `ta` | Target closed percent (0-100) | Hub's commanded target — present when moving |
| `vo` | `"{voltage}{type}{version}"` string | e.g. `"12.6D13"` = 12.6V, type D, fw 13 |
| `rs` | Signal in dBm | Negative, e.g. `-82` |
| `ol` | Online flag | **UNRELIABLE** — frequently shows offline while motor responds to direct queries. Hub's internal heuristic; don't gate behavior on it. |
| `is` | "In stop" / not moving | Boolean |
| `ls` | Limits set (1 if calibrated) | Motors without limits won't respond to move commands |

### `vo` parsing

```python
import re
m = re.match(r"([\.0-9]+)([A-Za-z])(\d{2})", vo)
voltage = float(m.group(1))    # e.g. 12.6
device_type = m.group(2)        # e.g. "D" = DC motor
fw_version = m.group(3)         # e.g. "13"

# Voltage → battery % (aiopulse2's formula)
if voltage < 8.4:
    pct = int(42.8 * voltage - 255)    # 8.3V pack
else:
    pct = int(27.4 * voltage - 255)    # 12V pack
```

## Group / batched shade moves

A single `shadow` desired payload can contain **multiple shades**. The
hub appears to dispatch these together internally.

```python
await call(HUB_IP, "shadow", {
    "desired": {
        "shades": {
            "JNQ": {"movePercent": 100},
            "QGL": {"movePercent": 100},
            "VXI": {"movePercent": 100},
            "WQF": {"movePercent": 100},
        }
    },
    "timeStamp": time.time(),
})
```

The response is the current reported state (not a per-shade ack). The
hub does NOT confirm in the response which shades actually got the RF
command — you have to poll `shadow` afterward to see `mp` change.

This is the most likely API the Automate Shades App uses for scenes.

## Scenes

The hub stores scene definitions but **there is no known RPC method
that triggers a scene server-side**. The App appears to:

1. `scenes` → list UUIDs (for picker UI)
2. `scenes` with `args=<uuid>` → get definition `{shade_id: target_pct}`
3. `shadow` desired with all the scene's shades in one payload

So the App is doing the same per-scene shade dispatch we would; the
"group logic in the hub" mentioned in the LinQ docs is the batched
shadow update path, NOT a hub-side scene executor.

Mitmproxy capture of the iOS App during a scene tap would confirm this
definitively — left as a follow-up if needed.

## What the original `aiopulse2`-based code missed

`aiopulse2` only ever uses two payload shapes:

1. `{"method": "shadow", "src": "app", "id": ts}` — get full state
2. `{"method": "shadow", "args": {"desired": {"shades": {<one>: {"movePercent": N}}}, "timeStamp": ts}}` — set ONE shade

So the project's old `apply_shades(hub, {...})` was looping over shades
and calling `roller.move_to()` one at a time. **That's the inefficiency
to fix.** The hub supports multi-shade desired payloads natively;
sending them as one batched payload is the path that LinQ's docs call
"the group logic in the hub."

`aiopulse2` also:
- Trusts the unreliable `ol` field — treats `ol: false` as offline
- Doesn't surface any per-command failure for `shadow` desired sends
  (none is sent by the hub; just poll `shadow` to detect changes)
- Doesn't use `scenes` or `timers` methods at all

## TCP/1487 ASCII (the LinQ tool's protocol)

Separate, lower-level protocol. See `docs/PROTOCOL.md` in the
`tcp-protocol` research branch. Per the official LinQ docs:

> Room, scene and timer commands are not supported in ASCII commands.
> ...this tool bypasses any of the group logic that is built into the
> hub and the Automate Shades App.

So TCP is for diagnostics. For production scene control, the WS shadow
batched-desired path is the right tool.

## RF reliability caveats (apply to any protocol)

Empirically observed during research (none are protocol-fixable):

- Motors are 433 MHz battery-powered and **sleep aggressively**. The
  hub's polling can fail to reach them at any moment.
- The `ol: false` flag is often factually wrong — motors that the hub
  thinks are offline frequently respond to direct queries within
  seconds. Don't pre-filter on `ol`.
- The hub itself drops commands when busy (`Ebz` error in TCP) —
  pacing matters even though the WS doesn't surface this.
- Low-voltage motors (`Epl`) are unreliable on RF; charging often
  restores reach.
- Hub state can degrade after heavy querying; power cycle resets it.
- `evening_close`-style failures (a few motors miss every time) tend
  to correlate with low battery and/or RF distance, NOT with protocol
  choice. Verify battery levels first before changing protocol layers.
