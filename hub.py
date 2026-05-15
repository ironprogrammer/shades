#!/usr/bin/env python3
import asyncio
import os
import sys
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


async def move_shade(hub, name, position):
    roller = next((r for r in hub.rollers.values() if r.name == name), None)
    if roller is None:
        print(f"  WARNING: roller '{name}' not found")
        return
    await roller.move_to(position)
    if not roller.online:
        sig = f", {roller.signal} dBm" if roller.signal is not None else ""
        print(f"  {name} -> {position}% closed {_yellow(f'(reported offline{sig})')}")
    else:
        print(f"  {name} -> {position}% closed")
