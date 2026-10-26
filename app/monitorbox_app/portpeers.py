"""Port history and "likely destinations" (#191).

Every few seconds the box reads each switch port's traffic. A device's traffic has to leave the switch through some other port, so a port
whose outgoing traffic rises and falls with the device's incoming traffic is probably where that traffic goes. This is an inference from
rates, not a record of conversations: it is always labelled "likely" or "possible", never certain, and a window with too little activity
says so instead of guessing. Nothing here reads packets.

PortSeries keeps the last hour in memory per (switch, port). `likely()` is a pure function over aligned rate lists."""
import math, threading, time
from collections import deque

KEEP_SECONDS = 3600
STEP = 10.0               # seconds between readings, and the width of one comparison bin
MIN_BINS = 12             # two minutes of both ports known, or no answer
MIN_BPS = 2000            # a port quieter than this on average (bit/s) has nothing to follow
LIKELY, POSSIBLE = 0.7, 0.5
MIN_SHARE = 0.02          # a port carrying less than this part of the device's traffic is not where that traffic goes, however well the shapes match
FLOOD_R, FLOOD_SHARE, FLOOD_SUM, FLOOD_PORTS = 0.8, 0.5, 1.5, 3


class PortSeries:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.last = {}        # (switch, port) -> (time, in, out, bits)
        self.points = {}      # (switch, port) -> deque of [time, in_bps, out_bps]
        self.speed = {}

    def _add(self, key, now, rin, rout):
        with self.lock:
            q = self.points.setdefault(key, deque())
            q.append([round(now, 2), round(rin), round(rout)])
            while q and q[0][0] < now - KEEP_SECONDS:
                q.popleft()

    def feed_counters(self, switch, ports, now=None):
        """ports: {name: {"in", "out", "bits"}} raw octet counters. Rates need two readings; a counter that went backwards (the device
        restarted) or a 32-bit roll-over is handled, and the first reading only starts the series."""
        now = self.clock() if now is None else now
        for name, r in (ports or {}).items():
            if not isinstance(r, dict) or not isinstance(r.get("in"), int) or not isinstance(r.get("out"), int):
                continue
            key, bits = (switch, name), r.get("bits", 64)
            if r.get("speedMbps"):
                self.speed[key] = r["speedMbps"]
            prev = self.last.get(key)
            self.last[key] = (now, r["in"], r["out"], bits)
            if not prev or now <= prev[0] or prev[3] != bits:
                continue
            span, d = now - prev[0], []
            for cur, old in ((r["in"], prev[1]), (r["out"], prev[2])):
                x = cur - old
                if x < 0 and bits == 32 and old > 1 << 31:
                    x += 1 << 32
                d.append(x)
            if min(d) < 0:
                continue
            self._add(key, now, d[0] * 8 / span, d[1] * 8 / span)

    def feed_rates(self, switch, ports, now=None):
        """ports: {name: {"in_bps", "out_bps"}}: rates a controller already worked out."""
        now = self.clock() if now is None else now
        for name, r in (ports or {}).items():
            if isinstance(r, dict) and isinstance(r.get("in_bps"), (int, float)) and isinstance(r.get("out_bps"), (int, float)):
                self._add((switch, name), now, r["in_bps"], r["out_bps"])

    def forget_ports(self, switch, keep):
        """Drop the history of ports of `switch` that are not in `keep` (a Wi-Fi client that left the network)."""
        with self.lock:
            for k in [k for k in self.points if k[0] == switch and k[1] not in keep]:
                del self.points[k]
        for d in (self.last, self.speed):
            for k in [k for k in d if k[0] == switch and k[1] not in keep]:
                del d[k]

    def forget_except(self, switches):
        with self.lock:
            for k in [k for k in self.points if k[0] not in switches]:
                del self.points[k]
        for d in (self.last, self.speed):
            for k in [k for k in d if k[0] not in switches]:
                del d[k]

    def recent(self, keys, seconds, now=None):
        """How busy these ports (one, or a bonded pair added together) were over the last `seconds`: {"avgBps", "peakBps"} of the busier direction,
        or None when the box has no readings of them."""
        now = self.clock() if now is None else now
        lo, tot_in, tot_out, peak, any_ = now - seconds, 0.0, 0.0, 0.0, False
        with self.lock:
            qs = [[p for p in self.points.get(k) or [] if p[0] >= lo] for k in keys]
        for q in qs:
            if not q:
                continue
            any_ = True
            tot_in += sum(p[1] for p in q) / len(q)
            tot_out += sum(p[2] for p in q) / len(q)
            peak += max(max(p[1], p[2]) for p in q)
        return {"avgBps": round(max(tot_in, tot_out)), "peakBps": round(peak)} if any_ else None

    def history_seconds(self, keys, now=None):
        """How long the box has been reading these ports: seconds back to the oldest reading of any of them (0 when there is none)."""
        now = self.clock() if now is None else now
        with self.lock:
            first = [q[0][0] for k in keys for q in [self.points.get(k)] if q]
        return max(0.0, now - min(first)) if first else 0.0

    def grid(self, keys, window, now=None):
        """{key: ([in_bps per bin], [out_bps per bin])} on one shared grid of STEP-second bins ending now, None where there was no reading.
        A port group (bonded links) is several keys that are added together."""
        now = self.clock() if now is None else now
        window = max(60, min(int(window), KEEP_SECONDS))
        n = int(window // STEP)
        start = now - n * STEP
        out = {}
        with self.lock:
            for key in keys:
                a, b = [None] * n, [None] * n
                for t, rin, rout in self.points.get(key, ()):
                    i = int((t - start) // STEP)
                    if 0 <= i < n:
                        a[i], b[i] = rin, rout
                out[key] = (a, b)
        return out


def add_groups(rows):
    """Sum several members into one series (a bonded pair is one link). rows: [(in_list, out_list)]; a bin is unknown if any member is."""
    if len(rows) == 1:
        return rows[0]
    n = len(rows[0][0])
    cols = []
    for k in (0, 1):
        cols.append([None if any(r[k][i] is None for r in rows) else sum(r[k][i] for r in rows) for i in range(n)])
    return cols[0], cols[1]


def pearson(x, y):
    """(r, bins) over the bins where both are known; r is None when there is nothing to compare (fewer than MIN_BINS, or one side is flat)."""
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    n = len(pairs)
    if n < MIN_BINS:
        return None, n
    mx, my = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx <= 0 or syy <= 0:
        return None, n
    return sum((a - mx) * (b - my) for a, b in pairs) / math.sqrt(sxx * syy), n


def pearson_near(x, y):
    """pearson, but the second series may run one reading early or late: two switches (or a switch and a server) report on their own cycles, and a copy that
    starts and stops sharply no longer lines up once one side is a reading behind. Returns the best of the three, with its bin count."""
    best = pearson(x, y)
    for lag in (1, -1):
        r = pearson(x[lag:], y[:-lag]) if lag > 0 else pearson(x[:lag], y[-lag:])
        if r[0] is not None and (best[0] is None or r[0] > best[0]):
            best = r
    return best


def mean(v):
    k = [a for a in v if a is not None]
    return sum(k) / len(k) if k else 0.0


def collapse_floods(found):
    """One port's traffic cannot each go, in full, to several other ports at once. When three or more ports all match closely and each
    carries about as much as the device sent (together far more than it sent), the traffic is being copied to many ports: broadcast or
    multicast (discovery chatter such as mDNS). Say that once instead of naming every port."""
    out, drop = [], set()
    for direction in ("from", "to"):
        strong = [x for x in found if x["direction"] == direction and x["r"] >= FLOOD_R and x["share"] >= FLOOD_SHARE and not x["label"].startswith(("anything ", "everything "))]
        if len(strong) >= FLOOD_PORTS and sum(x["share"] for x in strong) > FLOOD_SUM:
            drop.update(x["label"] for x in strong)
            out.append({"label": f"broadcast or multicast: copies seen on {len(strong)} ports", "kind": "flood", "direction": direction, "r": max(x["r"] for x in strong),
                        "bins": min(x["bins"] for x in strong), "share": round(sum(x["share"] for x in strong), 2), "bps": max(x["bps"] for x in strong), "confidence": "likely",
                        "ports": [x["label"] for x in sorted(strong, key=lambda x: -x["r"])][:8]})
    return [x for x in found if x["label"] not in drop] + out


def _plus(x, y):
    return [None if a is None or b is None else a + b for a, b in zip(x, y)]


def together(focus, pool, seed=(), max_members=16, min_gain=0.03):
    """Devices that move together: many look-alike flows (cameras, VMs, sensors, anything) are hard to tell apart one by one, but their total follows the
    device they all talk to. Grows a group from the best-matching port (or from `seed`, ports already known to be alike), adding a port only while the total
    follows the device more closely, never letting the total exceed what the device carried, and only offering a group that beats its best member by a clear margin.
    focus: (in_list, out_list); pool: {label: (in_list, out_list)}. Returns [{"label"?, "members", "direction", "r", "bins", "share", "bps", "confidence", "seeded"}]; one per direction at most."""
    fin, fout = focus
    out = []
    for direction, a in (("to", fout), ("from", fin)):
        base = mean(a)
        if base < MIN_BPS:
            continue
        series = {l: (v[0] if direction == "to" else v[1]) for l, v in pool.items() if v}
        singles = {}
        for l, x in series.items():
            r, _ = pearson(a, x)
            if r is not None and r >= 0.15 and mean(x) >= MIN_BPS:
                singles[l] = r
        chosen = [l for l in seed if l in series]
        cur = None
        for l in chosen:
            cur = series[l] if cur is None else _plus(cur, series[l])
        cur_r = pearson(a, cur)[0] if cur is not None else None
        while len(chosen) < max_members:
            best = None
            for l in singles:
                if l in chosen:
                    continue
                s = series[l] if cur is None else _plus(cur, series[l])
                if mean(s) > 1.15 * base:
                    continue
                r, _ = pearson(a, s)
                if r is not None and (best is None or r > best[0]):
                    best = (r, l, s)
            if best is None or (cur_r is not None and best[0] < cur_r + min_gain):
                break
            cur_r, cur = best[0], best[2]
            chosen.append(best[1])
        if len(chosen) < 2 or cur is None or cur_r is None or cur_r < POSSIBLE or mean(cur) < MIN_SHARE * base:
            continue
        if cur_r < max(singles.get(l, 0) for l in chosen) + 0.05:          # one member already says as much: no group needed
            continue
        _, n = pearson(a, cur)
        out.append({"members": list(chosen), "direction": direction, "r": round(cur_r, 2), "bins": n, "share": round(mean(cur) / base, 2), "bps": round(min(mean(cur), base)),
                    "confidence": "likely" if cur_r >= LIKELY else "possible", "seeded": bool(seed) and all(l in seed for l in chosen)})
    return out


def likely(focus, candidates, top=6):
    """focus: (in_list, out_list) of the port being asked about; candidates: {label: (in_list, out_list)}.
    Traffic coming in from the device should reappear going out of its destination (and the other way round). Returns
    {"answer": [...], "why": "" | reason}: each answer {"label", "direction": "from"|"to", "r", "bins", "share", "confidence": "likely"|"possible"};
    `share` is how big that port's traffic is next to the device's (it can be a small part of it); `bps` is the most that traffic can be (that port's own rate, never more than the device's)."""
    fin, fout = focus
    total = {"down": round(mean(fout)), "up": round(mean(fin))}        # what the device itself received and sent, averaged over the window (the port's out is the device's in)
    if max(mean(fin), mean(fout)) < MIN_BPS:
        return {"answer": [], "why": "This port was too quiet in that time to tell where its traffic goes.", "total": total}
    found, short = [], 0
    for label, (cin, cout) in candidates.items():
        best = None
        for direction, a, b, base in (("from", fin, cout, mean(fin)), ("to", fout, cin, mean(fout))):
            if base < MIN_BPS:
                continue
            r, n = pearson_near(a, b)
            if r is None:
                short += n < MIN_BINS
                continue
            if r >= POSSIBLE and (best is None or r > best["r"]):
                best = {"label": label, "direction": direction, "r": round(r, 2), "bins": n, "share": round(mean(b) / base, 2) if base else 0, "bps": round(min(mean(b), base)),
                        "confidence": "likely" if r >= LIKELY else "possible"}
        if best:
            found.append(best)
    found = [x for x in found if x["share"] >= MIN_SHARE]
    found = collapse_floods(found)
    found.sort(key=lambda x: -x["r"])
    if not found:
        return {"total": total, "answer": [], "why": "No other port's traffic follows this one closely enough to say." if not short else
                "Not enough history yet. Give it a few minutes with this page open.", "total": total}
    return {"answer": found[:top], "why": "", "total": total}
