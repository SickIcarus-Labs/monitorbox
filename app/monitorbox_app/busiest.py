"""The busiest client: which device is the chattiest right now, and how busy it has been.

Every ten seconds the leader is worked out from the port history (portpeers.PortSeries): each endpoint on the map is its switch port (bonded
ports added together), averaged over the last 30 seconds. So the name does not flap when the LAN is slow, a challenger has to stay clearly
busier for a while before it takes over, and below a small floor nobody is crowned ("quiet"). Wifi clients (and anything else without a port
reading) take part through the gateway's flow log, which counts what they send and receive through the gateway.

The name and the figure in words come from the 60-second average; the line is drawn from the latest reading, so it is not smoothed."""
import threading, time
from collections import deque

KEEP_SECONDS = 3600
FLOOR_BPS = 1_000_000        # under this (bit/s, in plus out) nobody is "busy"
KEEP_FLOOR = FLOOR_BPS / 2   # the leader stays crowned down to half the floor
OVERTAKE = 1.5               # a challenger must be this much busier than the leader ...
HOLD_TICKS = 3               # ... for this many readings in a row (30 s)
QUIET_TICKS = 6              # the leader must be below the keep line this long (60 s) before the crown is dropped
WINDOW = 60                  # seconds of readings averaged into one figure


def norm_mac(m):
    return "".join(ch for ch in str(m or "").lower() if ch in "0123456789abcdef")


def allowed(e, f):
    """Whether the filters let this device take part. `f` is the Busiest client's saved filter (all optional): wired, wifi, servers (default on) and exclude
    ([{mac or id, name}]). A device on a switch port is wired; one only the gateway's flow log sees (wifi, mostly) is the wifi side. Only what the card shows is
    affected: nothing here touches health, alerts or any other graph."""
    f = f or {}
    wired = e.get("node") is not None
    if wired and not f.get("wired", True) or not wired and not f.get("wifi", True):
        return False
    if wired and e.get("server") and not f.get("servers", True):
        return False
    ips = {str(i).lower() for i in (e.get("ips") or [e.get("ip")]) if i}
    if ips & set(f.get("_cameraIps") or ()) and not f.get("cameras", True):
        return False
    if ips & set(f.get("_iotIps") or ()) and not f.get("iot", True):
        return False
    if f.get("blacklist") and f.get("blacklistOn", True) and blocked(e, ips, f):
        return False
    macs = {norm_mac(m) for m in (e.get("macs") or [e.get("mac")]) if m}
    for x in f.get("exclude") or []:
        if (x.get("id") and x["id"] == e.get("id")) or (x.get("mac") and norm_mac(x["mac"]) in macs):
            return False
    return True


def blocked(e, ips, f):
    """Whether any comma-separated term of the owner's list matches this device: part of its name, its MAC address (the last three pairs, because that is all the map keeps;
    a whole address is read by its last six digits), its IP address (whole, or the start of one ending in a dot to hide a range), or part of the maker's name the controller gave it. Capitals do not matter."""
    name = str(e.get("name") or "").lower()
    macs = {norm_mac(m)[-6:] for m in (e.get("macs") or [e.get("mac")]) if m}
    makers = [str(f.get("_makers", {}).get(i) or "").lower() for i in ips]
    for term in str(f.get("blacklist")).split(","):
        t = term.strip().lower()
        if not t:
            continue
        h = norm_mac(t)
        if t in name or any(t in mk for mk in makers if mk):
            return True
        if t[0].isdigit() and set(t) <= set("0123456789.") and any(i == t or (t.endswith(".") and i.startswith(t)) for i in ips):
            return True                                            # an address, or the start of one ending in a dot, such as 192.168.77.
        if len(h) in (6, 12) and set(t) <= set("0123456789abcdef:-. ") and h[-6:] in macs:
            return True
    return False


def endpoints(m):
    """[{id, name, where, node, port, keys}] for every wired device port on the map."""
    out = []
    for n in (m or {}).get("nodes", []):
        for p in n.get("ports", []):
            if p.get("keys"):
                out.append({"id": f"{n['id']}|{p['port']}", "name": p.get("name") or "nothing named", "where": f"{n['name']} port {p['port']}",
                            "node": n["id"], "port": p["port"], "keys": [tuple(k) for k in p["keys"]], "macs": list(p.get("macs") or []), "ips": list(p.get("ips") or []), "server": bool(p.get("server"))})
    return out


def flow_endpoints(rows, eps, seconds):
    """Devices the switch ports cannot see (wifi clients, and anything else that is not on a port with readings), from the gateway's flow log: [{id, name, where, node: None,
    port: None, keys: [], flow: (down_bps, up_bps)}]. `rows` is the log boiled down (module unifi-network `flows`); a device already on a wired port is left to its port."""
    wired = {m for e in eps for m in e.get("macs", [])}
    by = {}
    for r in rows:
        for mac, name, down, up, ip in ((r.get("src_mac"), r.get("src_name"), r.get("down", 0), r.get("up", 0), r.get("src_ip")),
                                        (r.get("dst_mac"), r.get("dst_name"), r.get("up", 0), r.get("down", 0), r.get("dst_ip")) if r.get("direction") == "local" else (None, None, 0, 0, None)):
            if not mac or mac in wired:
                continue
            e = by.setdefault(mac, {"id": "flow|" + mac, "name": name or "unnamed device", "where": "seen by the gateway", "node": None, "port": None, "keys": [], "mac": mac, "ips": [], "flow": [0, 0]})
            if ip and ip not in e["ips"]:
                e["ips"].append(ip)
            e["flow"][0] += down * 8 / seconds
            e["flow"][1] += up * 8 / seconds
    return [{**e, "flow": tuple(e["flow"])} for e in by.values()]


class Busiest:
    def __init__(self, series, clock=time.time):
        self.series, self.clock = series, clock
        self.lock = threading.Lock()
        self.points = deque()        # [time, leader id or None, down_bps, up_bps (averaged: the figure shown in words), latest down_bps, latest up_bps (what is plotted)]
        self.info = {}               # leader id -> its endpoint row
        self.leader = None
        self.challenger, self.held, self.quiet = None, 0, 0

    def _rates(self, eps, now):
        """{endpoint id: (down, up)}: `down` is traffic going to the device (the switch port's out), `up` is traffic from it (the port's in)."""
        from . import portpeers
        keys = {k for e in eps for k in e["keys"]}
        grid = self.series.grid(keys, WINDOW, now)
        out = {}
        for e in eps:
            if e.get("flow"):                      # from the gateway's flow log: no port history, one figure for the window
                out[e["id"]] = (e["flow"][0], e["flow"][1], e["flow"][0], e["flow"][1])
                continue
            rows = [grid[k] for k in e["keys"]]
            ins, outs = portpeers.add_groups(rows)
            known = [(a, b) for a, b in zip(ins, outs) if a is not None and b is not None]
            if known:
                out[e["id"]] = (sum(b for _, b in known) / len(known), sum(a for a, _ in known) / len(known), known[-1][1], known[-1][0])
        return out

    def update(self, m, now=None, flows=None, opts=None):
        """`flows`: the gateway's flow log over the last minute (rows as in flow_endpoints), so wifi clients and other devices without a port reading can take part.
        `opts`: the card's filters (see `allowed`) and `floorMbps`, the least a device must carry to be crowned (1 by default)."""
        now = self.clock() if now is None else now
        opts = opts or {}
        floor = float(opts.get("floorMbps") or FLOOR_BPS / 1e6) * 1e6
        keep = floor / 2
        eps = endpoints(m)
        eps += flow_endpoints(flows or [], eps, WINDOW)          # found before filtering, so a hidden wired device is not rediscovered as a wifi one
        eps = [e for e in eps if allowed(e, opts)]
        rates = self._rates(eps, now)
        act = {i: r[0] + r[1] for i, r in rates.items()}
        by = {e["id"]: e for e in eps}
        top = max(act, key=act.get) if act else None
        lead = self.leader if self.leader in act else None
        if lead is None:
            self.leader, self.challenger, self.held, self.quiet = (top if top and act[top] >= floor else None), None, 0, 0
        else:
            if act[lead] < keep:
                self.quiet += 1
            else:
                self.quiet = 0
            if top and top != lead and act[top] >= max(floor, OVERTAKE * act[lead]):
                self.held = self.held + 1 if self.challenger == top else 1
                self.challenger = top
            else:
                self.challenger, self.held = None, 0
            if self.held >= HOLD_TICKS:
                self.leader, self.challenger, self.held, self.quiet = top, None, 0, 0
            elif self.quiet >= QUIET_TICKS:
                self.leader, self.quiet = None, 0
        with self.lock:
            if self.leader:
                self.info[self.leader] = by[self.leader]
                d, u, ld, lu = rates[self.leader]
                self.points.append([round(now, 2), self.leader, round(d), round(u), round(ld), round(lu)])
            else:
                self.points.append([round(now, 2), None, 0, 0, 0, 0])
            while self.points and self.points[0][0] < now - KEEP_SECONDS:
                self.points.popleft()
            live = {p[1] for p in self.points if p[1]}
            for k in [k for k in self.info if k not in live]:
                del self.info[k]

    def data(self, seconds=300, now=None):
        now = self.clock() if now is None else now
        seconds = max(60, min(int(seconds), KEEP_SECONDS))
        with self.lock:
            pts = [p for p in self.points if p[0] >= now - seconds]
            info = dict(self.info)
            leader = self.points[-1][1] if self.points else None
        before, seen = [], {leader}
        for p in reversed(pts):
            if p[1] and p[1] not in seen:
                seen.add(p[1])
                before.append({"name": info[p[1]]["name"], "where": info[p[1]]["where"], "ago": round(now - p[0])})
        cur = None
        if leader and leader in info and pts:
            e = info[leader]
            cur = {"name": e["name"], "where": e["where"], "node": e["node"], "port": e["port"], "mac": e.get("mac") or next(iter(e.get("macs") or []), None), "id": e["id"],
                   "down": pts[-1][2], "up": pts[-1][3]}
        since = None                 # when the current leader's unbroken run began
        for p in reversed(pts):
            if p[1] != leader:
                break
            since = p[0]
        return {"available": bool(self.points), "seconds": seconds, "now": round(now, 2), "leader": cur, "quiet": bool(self.points) and cur is None,
                "points": [[p[0], p[4], p[5]] for p in pts], "before": before[:3], "since": since}
