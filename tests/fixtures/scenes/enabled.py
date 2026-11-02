SCHEDULE = {"enabled": True, "window": ["11:00", "13:00"]}


def should_run(ctx):
    return ctx["is_school_day"]


async def run(hub):
    hub.ran.append(__name__)
