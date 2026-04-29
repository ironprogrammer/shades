SCHEDULE = {
    "enabled": True,
    "time": "07:45",
    "days": ["mon", "tue", "wed", "thu", "fri"],
}

SHADES = ["Your Shade Name 1", "Your Shade Name 2"]
POSITION = 0  # fully open


def should_run(ctx):
    return ctx["is_school_day"]


async def run(hub):
    from hub import move_shade
    for shade in SHADES:
        await move_shade(hub, shade, POSITION)
