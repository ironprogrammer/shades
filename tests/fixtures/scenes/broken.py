SCHEDULE = {"enabled": True, "window": ["11:00", "13:00"]}


def should_run(ctx):
    raise RuntimeError("broken scene")


async def run(hub):
    hub.ran.append(__name__)
