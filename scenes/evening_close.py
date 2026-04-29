SCHEDULE = {
    "enabled": True,
    "window": ["16:30", "20:05"],
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
}

SHADES = ["Your Shade Name 1", "Your Shade Name 2"]
POSITION = 100  # fully closed

STANDARD_TIME_CLOSE = (17, 0)   # 5:00 PM
DST_FALLBACK_CLOSE  = (20, 0)   # 8:00 PM cap during DST


def should_run(ctx):
    now = ctx["now"]

    if not ctx["is_dst"]:
        h, m = STANDARD_TIME_CLOSE
        return now.hour > h or (now.hour == h and now.minute >= m)

    # DST: close at sunset or fallback, whichever comes first
    sunset = ctx["weather"].get("sunset")
    fh, fm = DST_FALLBACK_CLOSE
    fallback = now.replace(hour=fh, minute=fm, second=0, microsecond=0)
    close_at = min(sunset, fallback) if sunset else fallback
    return now >= close_at


async def run(hub):
    from hub import move_shade
    for shade in SHADES:
        await move_shade(hub, shade, POSITION)
