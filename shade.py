#!/usr/bin/env python3
"""
shade — CLI for Rollease Acmeda shade control.

Usage:
  shade list                    # list all shades with index and current position
  shade scenes                  # list all scenes with schedule and today's status
  shade battery                 # check battery levels (no email)
  shade battery --send          # check and email if any shade is below threshold
  shade <name|index> open       # move to fully open (0%)
  shade <name|index> close      # move to fully closed (100%)
  shade <name|index> <0-100>    # move to specific closed percent

Name matching is case-insensitive and partial:
  shade "living" open           # matches any shade containing "living"
  shade 3 close                 # use index from 'shade list'

Index is based on hub registration order and is stable between runs.
"""
import asyncio
import os
import sys
from pathlib import Path

import aiopulse2
import resend
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

HUB_IP            = os.environ.get("HUB_IP")
BATTERY_THRESHOLD = 20  # percent


# ── Hub ───────────────────────────────────────────────────────────────────────

async def with_hub(callback):
    hub = aiopulse2.Hub(HUB_IP)
    task = asyncio.create_task(hub.run())
    await hub.rollers_known.wait()
    try:
        await callback(hub)
        await asyncio.sleep(1)
    finally:
        asyncio.create_task(hub.stop())
        while hub.running:
            await asyncio.sleep(0.3)


def rollers_indexed(hub):
    return list(enumerate(hub.rollers.values(), 1))


def find_roller(hub, target):
    indexed = rollers_indexed(hub)
    if target.isdigit():
        n = int(target)
        return [(i, r) for i, r in indexed if i == n]
    return [(i, r) for i, r in indexed if target.lower() in r.name.lower()]


# ── Commands ──────────────────────────────────────────────────────────────────

def _position_bar(pct):
    if pct is None:
        return "          "
    filled = round(pct / 10)
    return "█" * filled + "░" * (10 - filled)


async def cmd_list(hub):
    print(f"\n{'#':<4} {'Shade':<30} {'':10}  {'%':>4}")
    print("-" * 52)
    for i, roller in rollers_indexed(hub):
        pos = roller.closed_percent
        pct_str = f"{pos}%" if pos is not None else "N/A"
        print(f"{i:<4} {roller.name:<30} {_position_bar(pos)}  {pct_str:>4}")
    print()


async def cmd_move(hub, target, position):
    matches = find_roller(hub, target)
    if not matches:
        print(f"No shade found matching '{target}'. Run 'shade list' to see available shades.")
        return
    for i, roller in matches:
        await roller.move_to(position)
        print(f"  [{i}] {roller.name} -> {position}% closed")


async def cmd_battery(send):
    hub_ip = os.environ.get("HUB_IP")
    if not hub_ip:
        print("Error: HUB_IP is not set. Add it to your .env file.")
        sys.exit(1)

    hub = aiopulse2.Hub(hub_ip)
    await hub.test(update_devices=True)

    index = {r.id: i for i, r in enumerate(hub.rollers.values(), 1)}

    all_shades = []
    low = []
    for roller in hub.rollers.values():
        if not roller.has_battery:
            continue
        pct = roller.battery_percent
        entry = {"name": roller.name, "id": roller.id, "idx": index[roller.id], "battery_pct": pct, "battery_v": roller.battery}
        all_shades.append(entry)
        if pct is not None and pct < BATTERY_THRESHOLD:
            low.append(entry)

    print(f"\n{'#':<4} {'Shade':<30} {'':10}  {'%':>4}")
    print("-" * 52)
    for s in sorted(all_shades, key=lambda x: (x["battery_pct"] or 999)):
        flag = " <- LOW" if s in low else ""
        pct_str = f"{s['battery_pct']}%" if s["battery_pct"] is not None else "N/A"
        print(f"{s['idx']:<4} {s['name']:<30} {_battery_bar(s['battery_pct'])}  {pct_str:>4}{flag}")
    print()

    if not low or not send:
        if send and not low:
            print("All shades above threshold. No alert sent.")
        return

    required = ["RESEND_API_KEY", "EMAIL_FROM", "EMAIL_TO"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Cannot send — missing from .env: {', '.join(missing)}")
        sys.exit(1)

    _send_alert(low)


def _battery_bar(pct):
    if pct is None:
        return "          "
    filled = round(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    if pct < 20:
        color = "\033[31m"
    elif pct < 50:
        color = "\033[33m"
    else:
        color = "\033[32m"
    return f"{color}{bar}\033[0m"


def _send_alert(low_shades):
    lines = "\n".join(
        f"  • {s['name']}: {s['battery_pct']}% ({s['battery_v']}v)"
        for s in low_shades
    )
    body = (
        f"The following shades need charging:\n\n{lines}\n\n"
        "Charge soon to avoid losing position memory."
    )

    resend.api_key = os.environ["RESEND_API_KEY"]
    response = resend.Emails.send({
        "from": os.environ["EMAIL_FROM"],
        "to":   os.environ["EMAIL_TO"],
        "subject": f"Low battery: {len(low_shades)} shade(s) need charging",
        "text": body,
    })
    print(f"Alert sent (id={response.get('id', 'unknown')}) for {len(low_shades)} shade(s).")


# ── Scenes ────────────────────────────────────────────────────────────────────

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
_ALLDAYS  = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _fmt_days(days):
    if days == _WEEKDAYS:
        return "M–F"
    if set(days) == set(_ALLDAYS):
        return "daily"
    abbrev = {"mon": "M", "tue": "T", "wed": "W", "thu": "Th", "fri": "F", "sat": "Sa", "sun": "Su"}
    return " ".join(abbrev.get(d, "?") for d in days)


def _safe_should_run(mod, ctx):
    try:
        return bool(mod.should_run(ctx))
    except Exception:
        return True


def cmd_scenes():
    import importlib.util
    import json
    from datetime import date, datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo

    ROOT = Path(__file__).parent
    SCENES_DIR = ROOT / "scenes"
    STATE_FILE = ROOT / "scheduler_state.json"
    TZ = ZoneInfo(os.environ["TIMEZONE"])
    now = datetime.now(TZ)
    today = date.today().isoformat()
    today_dow = now.strftime("%a").lower()

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    weather = {}
    today_is_school_day = True
    try:
        from weather import get_weather
        weather = get_weather(os.environ.get("WEATHER_LAT", "0"), os.environ.get("WEATHER_LON", "0"))
    except Exception:
        pass
    try:
        from school_calendar import get_calendar, is_school_day as _is_school_day
        today_is_school_day = _is_school_day(get_calendar(), now.date())
    except Exception:
        pass

    real_ctx = {
        "now": now,
        "is_dst": bool(now.dst()),
        "weather": weather,
        "is_school_day": today_is_school_day,
    }

    def probe(high_f=65.0, school_day=True):
        return {"now": now, "is_dst": False, "weather": {"high_f": high_f, "sunset": None}, "is_school_day": school_day}

    scenes = []
    for path in sorted(SCENES_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            scenes.append((path.stem, mod))
        except Exception:
            pass

    def _scene_time_key(item):
        sched = getattr(item[1], "SCHEDULE", {})
        t = sched.get("time") or (sched.get("window") or ["99:99"])[0]
        return t

    scenes.sort(key=_scene_time_key)

    print(f"\n{'Scene':<18} {'Time':<13} {'Temp':<6} {'Days':<7} {'Shades':>6}  Status")
    print("-" * 62)

    for name, mod in scenes:
        schedule = getattr(mod, "SCHEDULE", {})
        enabled = schedule.get("enabled", True)
        shades = getattr(mod, "SHADES", [])
        threshold = getattr(mod, "TEMP_THRESHOLD", None)
        days = schedule.get("days", _ALLDAYS)
        today_in_days = today_dow in days

        if "time" in schedule:
            time_str = schedule["time"]
        elif "window" in schedule:
            w = schedule["window"]
            time_str = f"{w[0]}–{w[1]}"
        else:
            time_str = ""

        temp_str = ""
        temp_gates = False
        if threshold is not None:
            if _safe_should_run(mod, probe(high_f=999)) != _safe_should_run(mod, probe(high_f=-999)):
                temp_gates = True
                temp_str = f">{threshold}"
            else:
                temp_str = f"<{threshold}>"

        school_sensitive = enabled and (
            _safe_should_run(mod, probe(school_day=True)) != _safe_should_run(mod, probe(school_day=False))
        )

        if not enabled:
            status = "\033[90m✗ disabled\033[0m"
        elif state.get(name) == today:
            status = "\033[32m● ran today\033[0m"
        elif school_sensitive and today_in_days and not today_is_school_day:
            status = "\033[33m◌ holiday\033[0m"
        elif temp_gates and today_in_days and not _safe_should_run(mod, real_ctx):
            status = "\033[33m◌ skipped\033[0m"
        else:
            status = "○"

        print(f"{name:<18} {time_str:<13} {temp_str:<6} {_fmt_days(days):<7} {len(shades):>6}  {status}")

    print()


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_position(arg):
    if arg.lower() == "open":
        return 0
    if arg.lower() == "close":
        return 100
    if arg.isdigit() and 0 <= int(arg) <= 100:
        return int(arg)
    return None


def usage():
    print(__doc__)
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]

    if not args:
        usage()

    if args[0] == "battery":
        send = "--send" in args
        await cmd_battery(send)
        return

    if args[0] == "scenes":
        cmd_scenes()
        return

    if not HUB_IP:
        print("Error: HUB_IP is not set. Add it to your .env file.")
        sys.exit(1)

    if args[0] == "list":
        await with_hub(cmd_list)
        return

    if len(args) != 2:
        usage()

    target, pos_arg = args
    position = parse_position(pos_arg)
    if position is None:
        print(f"Invalid position '{pos_arg}'. Use open, close, or a number 0-100.")
        sys.exit(1)

    await with_hub(lambda hub: cmd_move(hub, target, position))


if __name__ == "__main__":
    asyncio.run(main())
