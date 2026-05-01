#!/usr/bin/env python3
import asyncio
import os
from pathlib import Path

import aiopulse2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
HUB_IP = os.environ["HUB_IP"]


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
    if not roller.online:
        print(f"  {name} -> SKIPPED (offline)")
        return
    await roller.move_to(position)
    print(f"  {name} -> {position}% closed")
