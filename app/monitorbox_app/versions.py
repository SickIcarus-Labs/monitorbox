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


def image(have, wants):
    """Does the container image need re-pulling? `have` is the launcher version this image carries (None for an image from before it was recorded),
    `wants` the one the channel's release was built for (None when the release does not say). No notice unless both are known and the image is older."""
    try:
        if not have or not wants:
            return None
        return {"have": have, "wants": wants, "outdated": vkey(have) < vkey(wants)}
    except ValueError:
        return None


def whats_changed(entries, running, target):
    """The plain-words notes the catalog carries for an update: every version after the running one up to the target (newest first), or, when nothing
    is waiting, the running version's own. Versions published before notes travelled with releases have none and are left out."""
    try:
        if running and target and vkey(target) > vkey(running):
            keep = [e for e in entries if vkey(running) < vkey(e["version"]) <= vkey(target)]
        else:
            keep = [e for e in entries if e["version"] == running]
    except (ValueError, KeyError, TypeError):
        return []
    keep = sorted(keep, key=lambda e: vkey(e["version"]), reverse=True)
    return [{"version": e["version"], "changes": [str(c) for c in e["changes"]][:20]} for e in keep if isinstance(e.get("changes"), list) and e["changes"]][:30]
