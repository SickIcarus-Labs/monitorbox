"""Which versions a channel offers, and what "Latest" or a pinned choice resolves to."""


def vkey(v):
    core, _, pre = v.partition("-")
    nums = tuple(int(x) for x in core.split(".")[:3])
    return nums + ((0,) if pre else (1,))  # 1.0.0-beta sorts before 1.0.0


def offered(entries, channel):
    """Entries the channel offers, newest first. dev sees all, beta sees beta+stable, stable sees stable."""
    return sorted((e for e in entries if channel in e.get("channels", [])),
                  key=lambda e: vkey(e["version"]), reverse=True)


def resolve(pin, latest, offered_versions):
    """The version to run for this choice, or None if it is not available in the channel."""
    want = latest if pin == "latest" else pin
    return want if want in offered_versions else None


def component(running, pin, latest, entries, channel, failed):
    opts = offered(entries, channel)
    versions = [e["version"] for e in opts]
    target = resolve(pin, latest, versions)
    return {
        "running": running,
        "pin": pin,
        "latest": latest if latest in versions else None,
        "target": target,
        "options": [{"version": e["version"], "channels": e["channels"]} for e in opts],
        "failed": list(failed),
        "needsApply": target is not None and target != running,
        "pinMissing": pin != "latest" and pin not in versions,
    }
