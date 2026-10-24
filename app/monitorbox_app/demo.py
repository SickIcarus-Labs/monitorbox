"""Demo scenarios: pretend homelab states, so every screen can be seen without breaking anything.
Built on the same engine as the real thing. Nothing here touches the network."""

SCENARIOS = ("green", "headsup", "yellow", "down", "blue", "red")


def _leaf(i, name, group, critical=False, dep=()):
    return {"id": i, "name": name, "group": group, "critical": critical, "dependsOn": list(dep), "rule": "primary",
            "checks": [{"id": "c", "type": "ping", "target": "demo"}]}


NODES = [
    _leaf("a3", "Anchor3", "Servers", True), _leaf("granite", "Granite", "Servers", True),
    _leaf("core", "Core switch", "Network", True), _leaf("agg", "Aggregation switch", "Network", True, ["core"]),
    _leaf("ap1", "Upstairs AP", "Network", False, ["core"]), _leaf("ap2", "Downstairs AP", "Network", False, ["core"]),
    _leaf("wan", "Internet", "Internet", True), _leaf("dns", "DNS", "Internet", True),
    _leaf("ups1", "Rack UPS", "Power"), _leaf("ups2", "Desk UPS", "Power"),
    _leaf("scrypted", "Scrypted", "Services", False, ["a3"]), _leaf("plex", "Plex", "Services", False, ["a3"]),
    _leaf("tautulli", "Tautulli", "Services", False, ["a3"]), _leaf("portainer", "Portainer", "Services", False, ["a3"]),
    _leaf("nextcloud", "Nextcloud", "Services", False, ["granite"]), _leaf("immich", "Immich", "Services", False, ["granite"]),
    _leaf("paperless", "Paperless", "Services", False, ["granite"]),
    _leaf("cam-front", "Front door camera", "Cameras", False, ["scrypted"]), _leaf("cam-pool", "Pool Equipment camera", "Cameras", False, ["scrypted"]),
    _leaf("cam-garage", "Garage camera", "Cameras", False, ["scrypted", "agg"]), _leaf("cam-patio", "Patio camera", "Cameras", False, ["scrypted", "agg"]),
]

import time


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def build(name, now=None):
    """Returns (nodes, results) for one scenario. Times are relative to now so durations look right."""
    now = now or time.time()
    _AT = _iso(now)
    ago = lambda minutes: _iso(now - minutes * 60)
    ok = lambda: {"ok": True, "detail": "All good", "ms": 2.0, "at": _AT, "since": ago(60 * 24 * 4)}
    res = {f"{n['id']}/c": ok() for n in NODES}

    def put(i, state, detail, since, **flags):
        res[f"{i}/c"] = {"ok": state, "detail": detail, "ms": None, "at": _AT, "since": since, **flags}

    if name == "headsup":       # busy, not broken: the banner stays green with a quiet line under it
        put("a3", True, "CPU 95% busy, memory 45% used", ago(30), notice=True)
    elif name == "yellow":      # answers, but not properly
        put("plex", True, "Answering slowly (6.1 s)", ago(40), warn=True)
    elif name == "down":        # something is actually down, but nothing critical depends on it
        put("cam-pool", False, "Offline in Scrypted", ago(168))
        put("tautulli", False, "Not responding on Anchor3", ago(78))
    elif name == "blue":
        put("ups1", None, "Cannot reach the UPS service. Last good reading 14 minutes ago.", ago(14))
        put("scrypted", None, "Scrypted is not answering, so camera status is unknown.", ago(10))
        for c in ("cam-front", "cam-pool", "cam-garage", "cam-patio"):
            put(c, None, "Scrypted is not answering", ago(10))
    elif name == "red":
        put("granite", False, "Not responding to ping or SNMP. Wake-on-LAN is available.", ago(3))
        put("agg", False, "Offline. Garage and Patio are cut off behind it.", ago(5))
        for i in ("nextcloud", "immich", "paperless"):
            put(i, False, "Host is down", ago(3))
        for i in ("cam-garage", "cam-patio"):
            put(i, False, "Unreachable", ago(5))
    return NODES, res
