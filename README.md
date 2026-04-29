# shades <img width="200" height="200" alt="doge shades" src="https://github.com/user-attachments/assets/7bbc7bde-ff03-4331-854b-48497a322bf8" />

Rollease Acmeda Pulse v2 automation for macOS — battery monitoring and scene-based shade control.

## Features

- `shade` CLI for direct control and battery level check for installed shades
- custom scene scheduling (e.g. open bedroom shades at 7 AM)
- "today's high" weather detection for better light/temperature control
- holidays/days off/vacation detection to silence applicable scenes

## Requirements

- **Rollease Acmeda Pulse v2 hub** — connected to your local network. This hub is sold separately and pairs with Rollease Acmeda motorized shades. All communication is local (no cloud required).
- **macOS** — cron and shell setup are macOS-oriented; Linux should work with minor adjustments
- **Python 3.9+**

## Scripts

| Script | Purpose |
|--------|---------|
| `shade.py` | CLI entry point — shade control and battery checks (see Shade CLI below) |
| `scheduler.py` | Scene orchestrator — runs every 5 min via cron, fires scenes whose conditions match |
| `scenes/` | Individual automation scenes (add/remove freely) |

## Setup

```bash
./setup.sh
```

Walks through dependencies, env var configuration, shell function install, and cache priming. Run once after cloning.

After setup, open a new terminal (or `source ~/.zshrc`) and verify:
```bash
shade list       # confirms hub connection
shade battery    # confirms battery levels
```

Then set up cron (see `cron-setup.txt`).

## Shade CLI

Installed by `setup.sh` as a shell function. All shade control in one command:

```bash
shade list               # list all shades — index, name, current position
shade battery            # check battery levels (no email)
shade battery --send     # check and email if any shade is low (requires email vars in .env)
shade "living" open      # partial name match, case-insensitive — moves all matches
shade "deck right" close
shade "office" 50        # 0 = open, 100 = closed
shade 3 close            # use index from 'shade list' instead of name
```

Index from `shade list` is based on hub registration order and is stable between runs.

## Scene scheduler

The scheduler loads every `.py` file in `scenes/` automatically. Each scene declares its own schedule and conditions — no changes to the scheduler needed when adding scenes.

**Disable a scene** without deleting it: set `"enabled": False` in its `SCHEDULE`.

**Add a scene** — create `scenes/your_scene.py`:

```python
SCHEDULE = {
    "enabled": True,
    "time": "09:00",                # fixed time trigger
    # "window": ["16:30", "20:05"], # or a polling window (fires once per day when condition is met)
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
}

def should_run(ctx):
    # ctx keys:
    #   now           — current datetime (timezone-aware)
    #   is_dst        — bool, whether DST is currently active
    #   is_school_day — bool, False on holidays, breaks, and during summer
    #   weather       — dict: high_f (float), sunset (datetime)
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
