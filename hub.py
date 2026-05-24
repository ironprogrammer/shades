#!/usr/bin/env python3
import asyncio
import os
import sys
import time
from pathlib import Path

import aiopulse2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
HUB_IP = os.environ["HUB_IP"]


def _yellow(s):
    return f"\033[33m{s}\033[0m" if sys.stdout.isatty() else s


class HubConnection:
    async def __aenter__(self):
        self.hub = aiopulse2.Hub(HUB_IP)
        self._task = asyncio.create_task(self.hub.run())
        await self.hub.rollers_known.wait()
        return self.hub

    async def __aexit__(self, *args):
        asyncio.create_task(self.hub.stop())
        while self.hub.running:
            await asyncio.sleep(0.5)


def _normalize(shades, position):
    if isinstance(shades, dict):
        return list(shades.items())
    if position is None:
        raise ValueError("position is required when shades is not a dict")
    return [(name, position) for name in shades]


async def apply_shades(hub, shades, position=None):
    """Move a group of shades in a single batched WebSocket payload.

    `shades` is either a {name: position} dict or an iterable of names paired
    with a shared `position`. All shades resolved by name go out in one
    `shadow` desired send — the hub's native group-dispatch path.
    """
    items = _normalize(shades, position)
    if not items:
        return

    by_name = {r.name: r for r in hub.rollers.values()}
    desired_shades = {}
    resolved = []
    for name, pos in items:
        roller = by_name.get(name)
        if roller is None:
            print(f"  WARNING: roller '{name}' not found")
            continue
        desired_shades[roller.id] = {"movePercent": int(pos)}
        resolved.append((name, pos, roller))

    if not desired_shades:
        return

    await hub.send_payload({
        "method": "shadow",
        "args": {
            "desired": {"shades": desired_shades},
            "timeStamp": time.time(),
        },
    })

    for name, pos, roller in resolved:
        if not roller.online:
            sig = f", {roller.signal} dBm" if roller.signal is not None else ""
            print(f"  {name} -> {pos}% closed {_yellow(f'(reported offline{sig})')}")
        else:
            print(f"  {name} -> {pos}% closed")


async def move_shade(hub, name, position):
    """Move a single shade by name. Thin wrapper over apply_shades."""
    await apply_shades(hub, {name: position})
