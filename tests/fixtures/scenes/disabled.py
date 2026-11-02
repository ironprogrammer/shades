SCHEDULE = {"enabled": False, "window": ["11:00", "13:00"]}


def should_run(ctx):
    return True


async def run(hub):
    hub.ran.append(__name__)
