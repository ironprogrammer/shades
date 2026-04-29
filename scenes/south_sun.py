SCHEDULE = {
    "enabled": True,
    "time": "10:00",
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
}

SHADES = ["Your Shade Name 1", "Your Shade Name 2"]
POSITION = 88  # 22% open
TEMP_THRESHOLD = 60  # matches TEMP_UNIT in .env (currently fahrenheit)


def should_run(ctx):
    high = ctx["weather"].get("high_f")
    return high is not None and high > TEMP_THRESHOLD


async def run(hub):
    from hub import move_shade
    for shade in SHADES:
        await move_shade(hub, shade, POSITION)
