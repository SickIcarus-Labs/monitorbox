"""Docker MAC address watch: two containers on one Docker bridge with the same MAC address (and the fixed MAC settings that lead to it).

Why: on 2026-11-25 Goliath had two pairs of containers sharing a MAC on its "media" bridge. Packets went to one or the other at random, so
Spottarr's NNTP import hung for twelve hours while Docker still called the container healthy. The cause was a MAC address that had been written
into a container's own settings when it was recreated: Docker then gave the container a new IP address but kept the old MAC, and another
container later got the old IP and the MAC that goes with it.

What this looks at, per Docker environment, through Portainer and read-only (GET only; see portainerlib.READ_ONLY):
  - every local network with the bridge driver, and each endpoint Docker lists on it (stopped or stale ones too, if Docker lists them)
  - every container's own settings: Config.MacAddress (the MAC asked for at creation) and, for a stopped container, the MAC its network
    settings ask for (Docker 25 and later report the requested address there while a container is not running)

States:
  failed    two or more endpoints on the SAME network share a MAC (case does not matter; an empty MAC is ignored; the same MAC on two
            different networks or two different hosts is fine). An allowed fixed MAC never hides a clash.
  degraded  no clash, but a container has a fixed MAC that the owner has not allowed (Edit monitoring, "Containers allowed a fixed MAC")
  healthy   neither
  unknown   any part could not be read. A half-read network is never called clean, so a clash that was announced is not called over.

The 02:42 + IPv4 rule (02:42:ac:1d:00:06 for 172.29.0.6) is only used as a hint in the wording: other Docker versions and drivers choose MACs
differently, so a MAC that does not follow it is not a fault.

Nothing here logs or returns a whole inspect answer: only the few fields below are kept (no environment variables, labels or secrets)."""
import hashlib, ipaddress, re, threading, time
from concurrent.futures import ThreadPoolExecutor

SNAP_SECONDS = 20          # a check repeated while confirming a problem reuses what was read this recently, so Portainer is not asked every 3 s
MAX_SHOWN = 4              # how many clashes or fixed MACs are spelled out in one message before "and N more"
ADVICE_CLASH = ("This can drop packets and time out connections at random. Recreate the affected containers from their compose files or stacks "
                "(not by hand, which can lose their settings), and look for a fixed MAC in their settings.")
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def norm_mac(x):
    """'02-42-AC-1D-00-09' or '02:42:ac:1d:00:09' -> '02:42:ac:1d:00:09'; anything empty or unreadable -> ''."""
    m = str(x or "").strip().lower().replace("-", ":")
    return m if _MAC.match(m) and m != "00:00:00:00:00:00" else ""


def bare_ip(x):
    return str(x or "").split("/")[0].strip()


def derived_mac(ipv4):
    """The MAC older Docker gives a bridge endpoint: 02:42 followed by the four bytes of its IPv4 address. '' if there is no IPv4 address."""
    try:
        b = ipaddress.IPv4Address(bare_ip(ipv4)).packed
    except ValueError:
        return ""
    return "02:42:" + ":".join(f"{x:02x}" for x in b)


def _name(x):
    return str(x or "").lstrip("/")


def _short(nid):
    return str(nid or "")[:12]


# ---- reading ---------------------------------------------------------------
class Reader:
    """Reads one environment's networks and containers. A container's own settings cannot change without the container being recreated (which
    gives it a new id), so they are read once per id and state; networks are read every time (at most every SNAP_SECONDS)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.settings = {}             # (env key, container id, state) -> the few fields kept from its inspect answer
        self.snaps = {}                # env key -> (time, snapshot)

    def read(self, client, env, now=None):
        now = time.time() if now is None else now
        key = (client.base, env["Id"])
        with self.lock:
            hit = self.snaps.get(key)
            if hit and now - hit[0] < SNAP_SECONDS:
                return hit[1]
        snap = self._read(client, env, key)
        with self.lock:
            self.snaps[key] = (now, snap)
        return snap

    def _read(self, client, env, key):
        eid = env["Id"]
        nets = [n for n in client.networks(eid) or []
                if str(n.get("Driver", "")).lower() == "bridge" and str(n.get("Scope", "local")).lower() == "local" and n.get("Id")]
        with ThreadPoolExecutor(max_workers=4) as pool:
            full = list(pool.map(lambda n: client.network(eid, n["Id"]), nets))      # any error stops the whole read: half a picture is no picture
        endpoints = []
        for n, f in zip(nets, full):
            nid, nname = str(f.get("Id") or n["Id"]), str(f.get("Name") or n.get("Name") or "")
            for cid, ep in (f.get("Containers") or {}).items():
                ep = ep or {}
                endpoints.append({"network": nname, "network_id": nid, "container_id": str(cid), "endpoint_id": str(ep.get("EndpointID") or ""),
                                  "name": _name(ep.get("Name")) or _short(cid), "ipv4": bare_ip(ep.get("IPv4Address")),
                                  "ipv6": bare_ip(ep.get("IPv6Address")), "mac": norm_mac(ep.get("MacAddress")), "raw_mac": str(ep.get("MacAddress") or "")})
        listed = client.containers(eid) or []
        wanted = [(str(c.get("Id", "")), str(c.get("State", "")).lower(), _name((c.get("Names") or [""])[0])) for c in listed if c.get("Id")]
        with self.lock:
            todo = [w for w in wanted if (key, w[0], w[1]) not in self.settings]
        with ThreadPoolExecutor(max_workers=4) as pool:
            got = list(pool.map(lambda w: self._settings(client, eid, w[0]), todo))
        with self.lock:
            for w, s in zip(todo, got):
                if s is not None:
                    self.settings[(key, w[0], w[1])] = s
            live = {(key, w[0], w[1]) for w in wanted}
            for k in [k for k in self.settings if k[0] == key and k not in live]:
                del self.settings[k]                    # containers that are gone, or changed state
            containers = []
            for cid, state, name in wanted:
                s = self.settings.get((key, cid, state))
                if s is not None:                       # None: removed between the list and the read (a recreate in progress); not an error
                    containers.append({"id": cid, "name": s.get("name") or name, "state": state, **s})
        return {"env": str(env.get("Name", "")), "networks": [{"id": str(f.get("Id") or n["Id"]), "name": str(f.get("Name") or n.get("Name") or "")} for n, f in zip(nets, full)],
                "endpoints": endpoints, "containers": containers}

    @staticmethod
    def _settings(client, eid, cid):
        """The few fields kept from one container's inspect answer, or None when the container has gone (404)."""
        from portainerlib import PortainerError
        try:
            d = client.inspect(eid, cid) or {}
        except PortainerError as e:
            if e.code == 404:
                return None
            raise
        cfg, hc, ns = d.get("Config") or {}, d.get("HostConfig") or {}, d.get("NetworkSettings") or {}
        running = bool((d.get("State") or {}).get("Running"))
        eps = {}
        for net, ep in (ns.get("Networks") or {}).items():
            ep = ep or {}
            eps[str(net)] = {"mac": norm_mac(ep.get("MacAddress")), "ip": bare_ip(ep.get("IPAddress")), "network_id": str(ep.get("NetworkID") or "")}
        return {"name": _name(d.get("Name")), "config_mac": norm_mac(cfg.get("MacAddress")), "network_mode": str(hc.get("NetworkMode") or ""),
                "running": running, "endpoints": eps}


# ---- judging ---------------------------------------------------------------
def _allowed(allow, container, network=""):
    """allow: names the owner allows a fixed MAC: 'spottarr' (any network) or 'spottarr/media' (that network only). Case does not matter."""
    c, n = str(container).lower(), str(network).lower()
    for a in allow or []:
        a = str(a).strip().lower()
        if not a:
            continue
        name, _, net = a.partition("/")
        if name == c and (not net or net == n):
            return True
    return False


def duplicates(endpoints):
    """Endpoints that share a MAC on the same network: [{network, network_id, mac, members: [endpoint, ...]}], members sorted by name."""
    groups = {}
    for e in endpoints:
        if e["mac"]:
            groups.setdefault((e["network_id"], e["mac"]), {}).setdefault(e["container_id"] or e["endpoint_id"], e)
    out = []
    for (nid, mac), members in groups.items():
        if len(members) >= 2:
            ms = sorted(members.values(), key=lambda e: (e["name"].lower(), e["container_id"]))
            out.append({"network": ms[0]["network"], "network_id": nid, "mac": mac, "members": ms})
    return sorted(out, key=lambda g: (g["network"].lower(), g["mac"]))


def fixed_macs(snap):
    """Containers whose own settings ask for a MAC: [{container, network, mac, runtime, ipv4, expected, where}]. where: 'container' for
    Config.MacAddress, 'endpoint' for a stopped container's network settings. A runtime MAC alone is never counted."""
    by_cont = {}
    for e in snap["endpoints"]:
        by_cont.setdefault(e["container_id"], []).append(e)
    out = []
    for c in snap["containers"]:
        mode = c.get("network_mode", "").lower()
        if mode in ("host", "none") or mode.startswith("container:"):
            continue                                    # no MAC of its own on a bridge, whatever its settings say
        seen = set()
        if c.get("config_mac"):
            eps = by_cont.get(c["id"], [])
            want = c.get("network_mode") if mode not in ("", "default") else "bridge"      # the network the old single-MAC setting applies to
            ep = next((e for e in eps if e["network"].lower() == want.lower()), None) or (eps[0] if eps else None)
            net = ep["network"] if ep else want
            cep = (c.get("endpoints") or {}).get(net) or {}
            ipv4 = (ep or {}).get("ipv4") or cep.get("ip", "")
            out.append({"container": c["name"], "network": net, "mac": c["config_mac"], "runtime": (ep or {}).get("mac") or cep.get("mac", ""),
                        "ipv4": ipv4, "expected": derived_mac(ipv4), "where": "container"})
            seen.add(c["config_mac"])
        if not c.get("running"):
            for net, ep in sorted((c.get("endpoints") or {}).items()):
                if ep.get("mac") and not ep.get("ip") and ep["mac"] not in seen:
                    out.append({"container": c["name"], "network": net, "mac": ep["mac"], "runtime": "", "ipv4": "", "expected": "", "where": "endpoint"})
                    seen.add(ep["mac"])
    return sorted(out, key=lambda f: (f["container"].lower(), f["network"].lower()))


def _who(e):
    ip = e["ipv4"] or e["ipv6"]
    return f"{e['name']} ({ip})" if ip else e["name"]


def _hint(mac, ipv4):
    """' (Docker would give it 02:42:...)' when the MAC looks like Docker's own 02:42 kind but does not match the IPv4 address; else ''."""
    exp = derived_mac(ipv4)
    return f", Docker would give it {exp}" if exp and mac.startswith("02:42:") and mac != exp else ""


def _clash_text(g):
    names = [_who(e) for e in g["members"]]
    joined = ", ".join(names[:-1]) + " and " + names[-1]
    hints = "".join(f" {e['name']} has {e['ipv4']}{_hint(g['mac'], e['ipv4'])}." for e in g["members"] if _hint(g["mac"], e["ipv4"]))
    return f"MAC {g['mac']} on network {g['network']} is used by {joined}.{hints}"


def _fixed_text(f):
    bits = [f"network {f['network']}"] if f["network"] else []
    if f["ipv4"]:
        bits.append(f["ipv4"])
    if f["expected"] and f["mac"] != f["expected"]:
        bits.append(f"Docker would give it {f['expected']}")
    if f["runtime"] and f["runtime"] != f["mac"]:
        bits.append(f"running with {f['runtime']}")
    where = "in its settings" if f["where"] == "container" else "in its network settings (it is stopped)"
    return f"{f['container']} has a fixed MAC {f['mac']} {where}" + (f" ({', '.join(bits)})" if bits else "")


def _more(items, n=MAX_SHOWN):
    return f" And {len(items) - n} more." if len(items) > n else ""


def judge(snap, allow=(), host=""):
    """{state, detail, key, clashes, fixed, allowed} for one environment's snapshot. `key` names exactly what is wrong (which MACs clash and between
    whom, which containers have a fixed MAC), so the App can tell the owner again when that changes while the problem stays."""
    host = host or snap.get("env", "")
    clashes = duplicates(snap["endpoints"])
    fixed = fixed_macs(snap)
    unexpected = [f for f in fixed if not _allowed(allow, f["container"], f["network"])]
    allowed = [f for f in fixed if f not in unexpected]
    ids = [f"docker-mac-duplicate:{host}:{g['network_id']}:{g['mac']}=" + ",".join(sorted(e["name"] for e in g["members"])) for g in clashes]
    ids += [f"docker-mac-persisted:{host}:{f['container']}" + (f":{f['network']}" if f["where"] == "endpoint" else "") for f in unexpected]
    key = hashlib.sha1("\n".join(sorted(ids)).encode()).hexdigest()[:16] if ids else ""
    out = {"key": key, "ids": sorted(ids), "clashes": clashes, "fixed": unexpected, "allowed": allowed}
    if clashes:
        text = " ".join(_clash_text(g) for g in clashes[:MAX_SHOWN]) + _more(clashes) + " " + ADVICE_CLASH
        if unexpected:
            text += " Fixed MACs: " + "; ".join(_fixed_text(f) for f in unexpected[:MAX_SHOWN]) + "." + _more(unexpected)
        return {**out, "state": "failed", "detail": text}
    if unexpected:
        text = "; ".join(_fixed_text(f) for f in unexpected[:MAX_SHOWN]) + "." + _more(unexpected)
        text += (" No clash now, but if Docker gives it a different IP address it can end up with another container's MAC. Recreate it from its "
                 "compose file or stack, or, if the fixed MAC is on purpose, allow it under Edit monitoring.")
        return {**out, "state": "degraded", "detail": text}
    nets, eps = len(snap["networks"]), sum(1 for e in snap["endpoints"] if e["mac"])
    text = f"{nets} bridge network{'s' if nets != 1 else ''}, {eps} MAC address{'es' if eps != 1 else ''}, no two the same on one network"
    if allowed:
        text += "; fixed MAC allowed for " + ", ".join(sorted({f["container"] for f in allowed}))
    return {**out, "state": "healthy", "detail": text}
