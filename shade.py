#!/usr/bin/env python3
"""
shade — CLI for Rollease Acmeda shade control.

Usage:
  shade list                    # list all shades with index and current position
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
