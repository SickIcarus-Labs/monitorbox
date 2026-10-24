"""Throughput graphs: which interfaces to draw (config/graphs.json, so backups carry it) and the live readings behind them.

The SNMP module only reads raw octet counters. This file turns two readings into a rate, keeps the last hour in memory
and picks the pace: one reading a second while someone has the page open, one every ten seconds otherwise."""
import re, threading, time
from collections import deque

MAX_GRAPHS = 12
KEEP_SECONDS = 3600
FAST, SLOW, WATCHING_FOR = 1.0, 10.0, 15.0
_ID = re.compile(r"[^a-z0-9]+")


class Invalid(ValueError):
    pass


def clean_filter(raw):
    """The Busiest client card's filters, only what differs from the defaults: wired / wifi / servers / cameras / iot ticks (on), floorMbps (1), and the devices it never shows."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise Invalid("the Busiest client filters must be an object")
    out = {}
    for k in ("wired", "wifi", "servers", "cameras", "iot"):
        if k in raw:
            if not isinstance(raw[k], bool):
                raise Invalid(f"'{k}' must be on or off")
            if raw[k] is False:
                out[k] = False
    bl = raw.get("blacklist")
    if bl not in (None, ""):
        if not isinstance(bl, str) or len(bl) > 500:
            raise Invalid("the hide list must be text, up to 500 characters, with the entries separated by commas")
        if bl.strip(" ,"):
            out["blacklist"] = bl.strip()
    if "blacklistOn" in raw:
        if not isinstance(raw["blacklistOn"], bool):
            raise Invalid("'blacklistOn' must be on or off")
        if raw["blacklistOn"] is False:
            out["blacklistOn"] = False
    fl = raw.get("floorMbps")
    if fl not in (None, ""):
        if isinstance(fl, bool) or not isinstance(fl, (int, float)) or not 0.01 <= fl <= 10_000:
            raise Invalid("the minimum bandwidth must be a number of Mbit/s, such as 1 or 0.5")
        if fl != 1:
            out["floorMbps"] = fl
    ex = raw.get("exclude") or []
    if not isinstance(ex, list) or len(ex) > 50:
        raise Invalid("the exclude list can hold up to 50 devices")
    keep = []
    for x in ex:
        if not isinstance(x, dict) or not (x.get("mac") or x.get("id")):
            raise Invalid("each excluded device needs a MAC address or an id")
        row = {"name": str(x.get("name") or "")[:60]}
        for key, cap in (("mac", 40), ("id", 80)):
            if x.get(key):
                row[key] = str(x[key])[:cap]
        if row not in keep:
            keep.append(row)
    if keep:
        out["exclude"] = keep
    return out


def clean_list(raw, connection_ok):
    """Validate the whole list; give every graph an id. connection_ok(id) says whether it is an SNMP connection."""
    if not isinstance(raw, list):
        raise Invalid("graphs must be a list")
    if len(raw) > MAX_GRAPHS:
        raise Invalid(f"at most {MAX_GRAPHS} graphs")
    out, seen = [], set()
    for i, g in enumerate(raw, 1):
        if not isinstance(g, dict):
            raise Invalid(f"graph {i}: not an object")
        conn, name = g.get("connection"), g.get("interface")
        title = str(g.get("title") or "").strip()[:60]
        if g.get("kind") == "busiest":          # not an interface: the front page's "who is the chattiest client" graph (see busiest.py)
            if "busiest" in seen:
                raise Invalid("Busiest client can only be on the main screen once")
            seen.add("busiest")
            row = {"id": "busiest", "kind": "busiest", "title": title or "Busiest client"}
            flt = clean_filter(g.get("filter"))
            if flt:
                row["filter"] = flt
            out.append(row)
            continue
        if not isinstance(conn, str) or not connection_ok(conn):
            raise Invalid(f"graph {i}: '{conn}' is not an SNMP connection")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise Invalid(f"graph {i}: pick an interface")
        title = title or name.strip()
        gid = str(g.get("id") or "") or _ID.sub("-", f"{conn}-{name}".lower()).strip("-")[:60]
        base, n = gid, 2
        while gid in seen:
            gid, n = f"{base}-{n}", n + 1
        seen.add(gid)
        row = {"id": gid, "title": title, "connection": conn, "interface": name.strip()}
        top = g.get("maxMbps")
        if top not in (None, ""):
            if not isinstance(top, int) or isinstance(top, bool) or not 1 <= top <= 1_000_000:
                raise Invalid(f"graph {i}: the top speed must be a whole number of Mbit/s, such as 2500")
            row["maxMbps"] = top
        out.append(row)
    return out


class Graphs:
    def __init__(self, load, sample, clock=time.time):
        """load() -> the saved list; sample(connection_id, [names]) -> {name: {"in","out","bits"} | {"error"}}."""
        self.load, self.sample, self.clock = load, sample, clock
        self.lock = threading.Lock()
        self.last = {}          # graph id -> (time, in, out, bits) of the previous reading
        self.points = {}        # graph id -> deque of [time, in_bps, out_bps]
        self.errors = {}        # graph id -> why there is no reading
        self.speed = {}         # graph id -> the link's rated speed in Mbit/s, when the device says
        self.viewed_at = 0.0
        self.due = 0.0
        self.stopping = threading.Event()
        self.thread = None

    # ---- the pace
    def viewing(self):
        self.viewed_at = self.clock()

    def interval(self):
        return FAST if self.clock() - self.viewed_at < WATCHING_FOR else SLOW

    # ---- readings
    def tick(self):
        """One round: read every configured interface (one call per connection) and store the rates."""
        graphs = [g for g in self.load() if g.get("kind") != "busiest"]
        by_conn = {}
        for g in graphs:
            by_conn.setdefault(g["connection"], []).append(g)
        now = self.clock()
        for cid, gs in by_conn.items():
            try:
                got = self.sample(cid, sorted({g["interface"] for g in gs}))
            except Exception as e:
                for g in gs:
                    self.errors[g["id"]] = str(e)
                continue
            for g in gs:
                r = got.get(g["interface"]) or {"error": "no answer"}
                if "error" in r:
                    self.errors[g["id"]] = r["error"]
                    self.last.pop(g["id"], None)
                    continue
                self.errors.pop(g["id"], None)
                if r.get("speedMbps"):
                    self.speed[g["id"]] = r["speedMbps"]
                prev = self.last.get(g["id"])
                self.last[g["id"]] = (now, r["in"], r["out"], r["bits"])
                if not prev or now <= prev[0] or prev[3] != r["bits"]:
                    continue
                span = now - prev[0]
                rates = []
                for cur, old in ((r["in"], prev[1]), (r["out"], prev[2])):
                    d = cur - old
                    if d < 0 and r["bits"] == 32 and old > 1 << 31:
                        d += 1 << 32           # a 32-bit counter rolled over
                    rates.append(d)
                if min(rates) < 0:             # the device restarted its counters: skip this one
                    continue
                rin, rout = rates
                with self.lock:
                    q = self.points.setdefault(g["id"], deque())
                    q.append([round(now, 2), round(rin * 8 / span), round(rout * 8 / span)])
                    while q and q[0][0] < now - KEEP_SECONDS:
                        q.popleft()
        keep = {g["id"] for g in graphs}
        with self.lock:
            for k in [k for k in self.points if k not in keep]:
                del self.points[k]
        for d in (self.last, self.errors, self.speed):
            for k in [k for k in d if k not in keep]:
                del d[k]

    def data(self, seconds=300):
        seconds = max(10, min(int(seconds), KEEP_SECONDS))
        since = self.clock() - seconds
        out = []
        with self.lock:
            for g in self.load():
                pts = [p for p in self.points.get(g["id"], ()) if p[0] >= since]
                out.append({**g, "points": pts, "error": self.errors.get(g["id"], ""), "speedMbps": self.speed.get(g["id"])})
        return {"seconds": seconds, "now": round(self.clock(), 2), "graphs": out}

    # ---- the loop
    def run(self):
        while not self.stopping.is_set():
            t0 = self.clock()
            try:
                if self.load():
                    self.tick()
            except Exception:
                pass
            self.stopping.wait(max(0.2, self.interval() - (self.clock() - t0)))

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="graphs")
        self.thread.start()

    def stop(self):
        self.stopping.set()
