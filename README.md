# shades <img width="200" height="200" alt="doge shades" src="https://github.com/user-attachments/assets/7bbc7bde-ff03-4331-854b-48497a322bf8" />

Rollease Acmeda Automate Pulse 2 automation and CLI for macOS -- shade control, battery monitoring, and scene-based shade control.

## Features

- `shades` CLI for direct control and battery level check for installed shades
- custom scene scheduling (e.g. open bedroom shades at 7 AM)
- "today's high" weather detection for better light/temperature control
- holidays/days off/vacation detection to silence applicable scenes

## Requirements

- **Rollease Acmeda Pulse v2 hub** -- connected to your local network. This hub is sold separately and pairs with Rollease Acmeda motorized shades. All communication is local (no cloud required).
- **macOS** -- cron and shell setup are macOS-oriented; Linux should work with minor adjustments
- **Python 3.9+**

## Scripts

| Script | Purpose |
|--------|---------|
| `shades.py` | CLI entry point -- shade control and battery checks |
| `scheduler.py` | Scene orchestrator -- runs via cron, fires scenes whose conditions match |
| `scenes/` | Individual automation scenes |

## Setup

```bash
./setup.sh
```

Walks through dependencies, env var configuration, shell function install, and cache priming. Run once after cloning.

After setup, open a new terminal (or `source ~/.zshrc`) and verify:
```bash
shades list       # confirms hub connection
shades battery    # confirms battery levels
```

## Shades CLI

Installed by `setup.sh` as a shell function. All shade control in one command:

```bash
shades list               # list all shades -- index, name, current position
shades battery            # check battery levels (no email)
shades battery --send     # check and email if any shade is low (requires Resend config in .env)
shades "living" open      # partial name match, case-insensitive -- moves all matches
shades "deck right" close # exact name match
shades "office" 50        # percentage closed: 0 = open, 100 = closed
shades 3 close            # use index from 'shades list' instead of name
shades scenes             # list all scenes -- name, days, time, temp, status
shades scenes "wake"      # activate scene by name, bypassing day/time config
```

Index from `shades list` is based on hub registration order and should be stable between runs.

## Scene scheduler

Each scene declares its own schedule and conditions. The scheduler loads every `.py` file in `scenes/` automatically, so there are no other changes needed when adding/removing scenes.

**Getting started**

Copy an example scene and fill in your shade names:

```bash
# get list of registered shade names
shades list
cp scenes/weekday_schedule.py.example scenes/my_morning.py
```

Three examples are included, each demonstrating a key feature:

| Example | Feature |
|---------|---------|
| `weekday_schedule.py.example` | Basic timed weekday trigger |
| `weather_restriction.py.example` | Only runs when today's high exceeds a threshold |
| `days_off_exclusion.py.example` | Skips holidays, breaks, and summer via school calendar |

**Disable a scene** without deleting it: set `"enabled": False` in its `SCHEDULE`.

**Scene structure** -- `scenes/your_scene.py`:

```python
SCHEDULE = {
    "enabled": True,
    "time": "09:00",                # fixed time trigger
    # "window": ["16:30", "20:05"], # use for a polling window (fires once per day when condition is met)
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
}

def should_run(ctx):
    # ctx keys:
    #   now           - current datetime (timezone-aware)
    #   is_dst        - bool, whether DST is currently active
    #   is_school_day - bool, False on holidays, breaks, and during summer
    #   weather       - dict: high_f (float), sunset (datetime)
    return True

async def run(hub):
    from hub import move_shade
    await move_shade(hub, "Your Shade Name", 50)  # 0 = open, 100 = closed
```

## School/holidays calendar

`school_calendar.py` fetches your district's (or arbitrary) iCal feed (configured via `SCHOOL_CALENDAR_ICS_URL` in `.env`) and caches it locally for 7 days.

**How days off are detected:** events whose summary contains any of these strings (case-insensitive) are treated as no-school days:

- `no school`
- `schools closed`
- `district closed`
- `furlough`
- `holiday break`

If your district uses different wording, add keywords to `NO_SCHOOL_KEYWORDS` in `school_calendar.py`.

**Summer break** is detected automatically using `First Day of School` and `Last Day of School` events in the feed — no manual configuration needed.

Inspect the current cache:
```bash
python3 school_calendar.py
```

## Acknowledgements

Hub communication is built on [aiopulse2](https://github.com/sillyfrog/aiopulse2), which also served as inspiration for early hub interaction patterns in this project.

## Weather

Today's high and sunset time are fetched from [Open-Meteo](https://open-meteo.com) (free, no API key) and cached daily. Units and timezone are configured in `.env`.

## Running tests

```bash
python3 -m pytest tests/ -v
```

Tests cover scene logic, scheduler time-window matching, weather caching, and school calendar keyword detection. No network or hub connection required.
