#!/usr/bin/env python3
"""
Scene orchestrator. Run via cron every 5 min during active hours:
  */5 7-20 * * * /usr/bin/python3 /path/to/shades/scheduler.py >> /path/to/shades/scheduler.log 2>&1
"""
import asyncio
import importlib.util
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

SCENES_DIR = ROOT / "scenes"
STATE_FILE = ROOT / "scheduler_state.json"
TZ = ZoneInfo(os.environ["TIMEZONE"])
POLL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "5"))
WEATHER_LAT = os.environ["WEATHER_LAT"]
WEATHER_LON = os.environ["WEATHER_LON"]


# ── State (prevents double-firing within poll window) ─────────────────────────

def _load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}

def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def _already_ran(state, name):
    return state.get(name) == date.today().isoformat()

def _mark_ran(state, name):
    state[name] = date.today().isoformat()


# ── Schedule matching ─────────────────────────────────────────────────────────

_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def _in_window(schedule, now):
    days = schedule.get("days", _DAY_NAMES)
    if now.strftime("%a").lower() not in days:
        return False

    if "time" in schedule:
        t = now.replace(
            hour=int(schedule["time"][:2]),
            minute=int(schedule["time"][3:]),
            second=0, microsecond=0,
        )
        return t <= now < t + timedelta(minutes=POLL_MINUTES)

    if "window" in schedule:
        start = now.replace(hour=int(schedule["window"][0][:2]), minute=int(schedule["window"][0][3:]), second=0, microsecond=0)
        end   = now.replace(hour=int(schedule["window"][1][:2]), minute=int(schedule["window"][1][3:]), second=0, microsecond=0)
        return start <= now <= end

    return False


# ── Scene loading ─────────────────────────────────────────────────────────────

def _load_scenes():
    scenes = []
    for path in sorted(SCENES_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        scenes.append((path.stem, mod))
    return scenes


# ── Context ───────────────────────────────────────────────────────────────────

def _build_context(now):
    from weather import get_weather
    from school_calendar import get_calendar, is_school_day

    weather = get_weather(WEATHER_LAT, WEATHER_LON)
    cal = get_calendar()
    return {
        "now": now,
        "is_dst": bool(now.dst()),
        "weather": weather,
        "is_school_day": is_school_day(cal, now.date()),
    }


# ── Hub runner ────────────────────────────────────────────────────────────────

async def _run_scenes(scenes, ctx):
    from hub import HubConnection, move_shade

    async with HubConnection() as hub:
        for name, mod in scenes:
            print(f"  -> {name}")
            try:
                await mod.run(hub)
            except Exception as exc:
                print(f"     ERROR: {exc}")
        await asyncio.sleep(2)  # let commands transmit before disconnect


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    now = datetime.now(TZ)
    state = _load_state()

    candidates = []
    for name, mod in _load_scenes():
        schedule = getattr(mod, "SCHEDULE", {})
        if not schedule.get("enabled", True):
            continue
        if not _in_window(schedule, now):
            continue
        if _already_ran(state, name):
            continue
        candidates.append((name, mod))

    if not candidates:
        return

    try:
        ctx = _build_context(now)
    except Exception as exc:
        print(f"[{now.strftime('%H:%M')}] ERROR building context: {exc}")
        return

    to_run = []
    for name, mod in candidates:
        try:
            if mod.should_run(ctx):
                to_run.append((name, mod))
        except Exception as exc:
            print(f"[{now.strftime('%H:%M')}] ERROR in {name}.should_run: {exc}")

    if not to_run:
        return

    print(f"[{now.strftime('%H:%M')}] Running: {', '.join(n for n, _ in to_run)}")
    try:
        await _run_scenes(to_run, ctx)
        for name, _ in to_run:
            _mark_ran(state, name)
        _save_state(state)
    except Exception as exc:
        print(f"[{now.strftime('%H:%M')}] ERROR running scenes: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
