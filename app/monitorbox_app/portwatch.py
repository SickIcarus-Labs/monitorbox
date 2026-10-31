"""Port errors, drops and link flaps: watch the change, not the lifetime total (#194).

A switch port's counters only ever go up, so 122 million drops says nothing by itself. What matters is whether a port is getting worse *now*,
compared with how that same port normally behaves. Every few seconds the sampler hands over each port's counters (read-only, from the UniFi
port table). Here they are kept for a few hours, in memory, per port.

A port is "rising" when, in the last 15 minutes, it gained at least a floor's worth of errors (or drops, or link flaps) AND that is at least
5 times the worst 15 minutes it has had before (a port that has always had a trickle of errors is not news, and neither is one that only
errors while a big transfer fills the link: that burst is its normal; a port that never had any and suddenly does, is). The worst earlier
window is used, not the average, so a port that is quiet most of the day and noisy under load is not flagged every time the load comes. The
box needs half an hour of readings of a port before it says anything: until then the port is "learning". A counter that goes backwards means
the device restarted: that port starts again from there.

Off by default. When it is switched on, one built-in check ("Port errors") reports Degraded (never Down: the link still works) while any port
that is not marked "known issue" is rising; the usual 2-in-a-row confirmation and the alert triggers apply on top. A port marked known still
shows its numbers, but never raises anything: the same rule as everywhere else, observed state is never hidden, only the alerting is."""
import json, os, threading, time
from collections import deque

from . import applog
from .store import read_json, write_json

STALE_OTHERS = 1800      # seconds: an interface the map does not show, with no new reading for this long, is dropped
KEEP = 24 * 3600          # seconds of readings kept per port (a day, so the last busy spell is still remembered)
EVERY = 60                # at most one kept reading per port per this many seconds (a day of them is about 1,400 per port)
RECENT = 900              # the window that is compared with the port's earlier pace (15 minutes)
MIN_HISTORY = 1800        # readings of a port needed before it can be called rising (30 minutes)
RISE = 5                  # the recent pace must be at least this many times the earlier pace
FLOOR = {"errors": 20, "drops": 10000, "flaps": 3}     # new in the window, at least, before it is worth a line, on a 1 Gbit link; errors and drops scale with the link speed (below)
DROP_SHARE = 0.001        # packet drops are only worth a line when they are at least this share of the packets (0.1%), where the port's packet counts are known
ERROR_SHARE = 0.0001      # errors count from 0.01% of the packets (1 in 10,000), where one download stream starts to slow; the owner's WAN ran at about 0.00015% under a full-rate download (2026-10-30) without harm
FLOOR_MIN = {"errors": 20, "drops": 1000}               # ... but never lower than this, however slow the link
WORDS = {"errors": "errors", "drops": "packet drops", "flaps": "link drops"}
KINDS = ("errors", "drops", "flaps")
EXPECT_AFTER = 3600       # seconds a link must have been up without a break before it is expected to stay up (learned, no setup)
DOWN_AFTER = 60           # seconds an expected link must be down before it is worth a heads-up
SAVE_EVERY = 300          # seconds between saves of the history; it is kept thinned to one reading per this long
FIRST_READINGS = 180      # seconds after a start that the first counters are waited for before the check says it cannot read any


DIP_KEEPS = 0.5          # a counter that falls but keeps at least half of what it had wobbled; a restart takes it (and the packet counts) back to about nothing


SPLIT = {"errors": (4, 5), "drops": (6, 7)}      # which stored columns are the receive and transmit parts


def bps_words(x):
    x = float(x or 0)
    for div, unit in ((1e9, "Gbit/s"), (1e6, "Mbit/s"), (1e3, "kbit/s")):
        if x >= div:
            return f"{x / div:.1f} {unit}"
    return f"{round(x)} bit/s"


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _at(q, t):
    """The latest reading at or before time t (the oldest one when t is older than all of them)."""
    best = q[0]
    for p in q:
        if p[0] > t:
            break
        best = p
    return best


def _worst(q, end_t, i):
    """The most one port gained in any 15-minute stretch ending at or before end_t, for counter i (None when its history is shorter than one stretch)."""
    pts = [p for p in q if p[0] <= end_t]
    best, j, full = 0, 0, False
    for k, p in enumerate(pts):
        while j + 1 <= k and pts[j + 1][0] <= p[0] - RECENT:
            j += 1
        if p[0] - pts[j][0] >= RECENT * 0.8:
            full = True
            best = max(best, p[i] - pts[j][i])
    return best if full else None


def floor_for(kind, speed_mbps=None):
    """The least a port must gain in 15 minutes before it is worth a line. Errors and drops scale with the link's speed (a 10 Gbit port carries ten times the frames of
    a 1 Gbit one, so the same count is a tenth of the share), down to a minimum for slow links. Link drops do not scale. Unknown speed counts as 1 Gbit."""
    if kind not in FLOOR_MIN:
        return FLOOR[kind]
    scale = (speed_mbps if isinstance(speed_mbps, (int, float)) and speed_mbps > 0 else 1000) / 1000.0
    return max(FLOOR_MIN[kind], round(FLOOR[kind] * scale))


def one_in(share):
    """A share of packets as people say it: "about 1 in 56,000 packets" (two significant figures), or "under 1 in a million"."""
    if not share or share <= 0:
        return ""
    n = 1 / share
    if n >= 1_000_000:
        return "under 1 in a million packets" if n > 1_500_000 else "about 1 in a million packets"
    n = int(float(f"{n:.2g}"))
    return f"about 1 in {max(n, 1):,} packets"


def drop_share(last, cut, tx_only=False):
    """The share of packets dropped between two readings: the worse of receive and transmit (drops / (packets + drops)). None when either reading has no packet counts
    (an older saved reading, a device that does not report them) or a counter went backwards."""
    return _share(last, cut, ((7, 9),) if tx_only else ((6, 8), (7, 9)))


def error_share(last, cut):
    """The same for errors: the worse of receive errors and transmit errors, each against the packets in that direction."""
    return _share(last, cut, ((4, 8), (5, 9)))


def _share(last, cut, pairs):
    if len(last) < 10 or len(cut) < 10:
        return None
    worst = 0.0
    for d, pk in pairs:
        dd, pp = last[d] - cut[d], last[pk] - cut[pk]
        if dd < 0 or pp < 0:
            return None
        if dd + pp > 0:
            worst = max(worst, dd / (dd + pp))
    return worst


def judge(q, flaps=True, speed=None, server=False):
    """How one port is doing, from its readings [[t, errors, drops, flaps], ...] (oldest first).
    -> {"learning": bool, "rising": [kinds], "count": {kind: how many in the last 15 minutes}, "was": {kind: the most in any earlier 15 minutes}}
    Counts are what was seen in the window, never scaled up to an hour (#331: a 15-minute burst of 133 read as "about 532 an hour").
    `server`: this is a server's network card. Its receive drops are frames the kernel discarded because nothing wanted them (unknown protocol or VLAN), not loss: a card that really
    loses frames shows receive errors, which are counted as ever. So only its transmit drops count as drops."""
    out = {"learning": True, "rising": [], "count": {}, "was": {}, "split": {}, "share": None, "shares": {}}
    if len(q) < 2:
        return out
    now, first = q[-1][0], q[0][0]
    if now - first < RECENT:
        return out
    cut = _at(q, now - RECENT)
    span_before = cut[0] - first
    out["learning"] = now - first < MIN_HISTORY
    for i, kind in enumerate(KINDS, start=1):
        if kind in ("flaps", "drops") and not flaps:
            continue                                              # a client port drops whenever a laptop sleeps, and a TV in standby backs up its port: only uplinks, links between switches and servers are worth a line
        ci = 7 if kind == "drops" and server and len(q[-1]) >= 8 and len(cut) >= 8 else i      # the column that is judged: a server card's drops are its transmit drops
        new = q[-1][ci] - cut[ci]
        out["count"][kind] = new
        if kind in SPLIT and len(q[-1]) >= 8 and len(cut) >= 8:     # receive and transmit apart: a bad link shows as receive errors, a backed-up port as transmit drops
            a, b = SPLIT[kind]
            out["split"][kind] = {"rx": q[-1][a] - cut[a], "tx": q[-1][b] - cut[b]}
        if kind in ("drops", "errors") and kind not in out["shares"]:
            out["shares"][kind] = drop_share(q[-1], cut, tx_only=(ci == 7)) if kind == "drops" else error_share(q[-1], cut)   # shown even when it stays below the line
        worst = _worst(q, cut[0], ci)
        if worst is None and span_before >= 60:
            worst = cut[ci] - q[0][ci]                                  # less than one stretch of history: what there was
        was = worst
        out["was"][kind] = None if was is None else round(was)
        if out["learning"] or new < floor_for(kind, speed):
            continue
        if was is None or new >= RISE * was:
            if kind in ("drops", "errors"):
                sh = drop_share(q[-1], cut, tx_only=(ci == 7)) if kind == "drops" else error_share(q[-1], cut)
                out["shares"][kind] = sh
                if kind == "drops":
                    out["share"] = sh
                if sh is not None and sh < (DROP_SHARE if kind == "drops" else ERROR_SHARE):
                    continue                                          # plenty of them, but a sliver of the traffic (a busy link, a server's card discarding frames it does not want): not a problem
            out["rising"].append(kind)
    return out


class PortWatch:
    def __init__(self, paths, clock=time.time, traffic=None, available=None):
        self.paths, self.clock = paths, clock
        self.available = available      # available() -> True when the box has a switch it could read counters from (a UniFi or SNMP login)
        self.history_path = paths.p("data", "app", "port-history.json")
        self.started, self.fed, self._saved_at = clock(), False, 0.0
        self.restored = 0
        self.traffic = traffic      # traffic(keys, seconds) -> {avgBps, peakBps} or None: how busy the port was, from the port history
        self.lock = threading.Lock()
        self.series = {}          # "device id|port name" -> deque of [t, errors, drops, flaps]
        self.labels = {}          # the same keys -> "Switch name, Port 5"
        self.why = {}             # series prefix -> why that device is read as a server (shown beside the uncounted interfaces)
        self.unifi_names = []     # what UniFi calls its devices, to compare with an SNMP device's own name
        self.attached = {}        # key -> the name of what is plugged into that port (the UniFi client's name): said in the alert so "Theater, Port 2" also says "Apple TV"
        self.peers = {}           # key -> (key of the port at the other end of that link, "Switch name, Port 3"): set from the map
        self.used, self.link_ends = set(), set()
        self.shown = set()        # keys of the ports the map shows (in use); when known, only these are counted and listed, the rest are read quietly so a port plugged in later has history
        self.cards = {}           # server id ("snmp:<connection>") -> keys of its network cards that have a link: those count as ports in use, like a switch port with something on it
        self.members = {}         # key -> the bond or team a network card belongs to ("bond0"): said in the alert
        self.used_at = {}         # key -> when the map last showed this port: a port that was in use in the last day keeps its history while its device sleeps (link down), the rest of the clean-up is for interfaces that never were ports
        self.speeds = {}          # key -> link speed in Mbit/s, from the map, so the minimums scale with the port
        self.slot = {}            # key -> when the current kept reading started (rounds come every 10 s; a reading is kept every EVERY seconds)
        self.raw = {}             # key -> the last raw [rx errors, tx errors, rx drops, tx drops] read
        self.off = {}             # key -> what has been added to each of those so far to undo wraps: some drivers report a 16-bit counter, which starts again after 65,535
        self.switch_like = set()  # SNMP device ids that look like a switch (they learn addresses or hear neighbours) but were not matched to a UniFi device while UniFi has devices: said on the page, with why
        self.card_speeds = {}     # the same for ports read over SNMP, from the device itself (the map does not show a switch that UniFi does not know)
        self.switches = set()     # ids of SNMP devices that are switches (their ports are not server cards: see judge())
        self.client_ports = set() # keys of ports on an SNMP-only switch that look like a client's (no neighbour, at most one address behind them): packet and link drops are not a problem there
        self.flap_ports = set()   # keys of ports whose link drops count: uplinks, links between switches, and servers (set from the map)
        self.held = {}            # key -> True while a dipped counter is being held at its old figure (so the log says so once)
        self.resets = {}          # key -> [times its counter went backwards (so its history started again), which counter, when]: shown on the page, to explain a port that never finishes learning
        self.links = {}           # key -> {"up": bool, "since": when it last changed, "expected": it has been up for an hour, so its going away is news}
        self.restore()

    # ---- settings (in the box's config file) ----
    def _cfg(self):
        c = read_json(self.paths.config, {"schema": 4}).get("portwatch")
        return c if isinstance(c, dict) else {}

    def enabled(self):
        """On when it was switched on, or when nobody has chosen yet and the box has something to read. Switched off by hand stays off."""
        on = self._cfg().get("on")
        if on is None:
            return bool(self.available and self.available())
        return on is True

    def switched_off(self):
        """True only when it was switched off by hand. A config file that cannot be read for a moment is not that, and must never wipe the history."""
        return self._cfg().get("on") is False

    def chosen(self):
        """True once someone switched it on or off by hand."""
        return "on" in self._cfg()

    def page(self):
        """What the Port errors item page lists: the ports rising now and the ports ticked off (not alerting), each with the key that the tick uses."""
        known = self._marked()
        with self.lock:
            snap = {k: (self.labels.get(k, k), list(q)) for k, q in self.series.items()}
        rising, off, quiet = [], [], []
        for k, (label, q) in sorted(snap.items(), key=lambda x: x[1][0]):
            j = judge(q, self._links(k), self._speed(k), self._is_server(k))
            row = {"key": k, "label": label, "alert": k not in known}
            if k in known:
                off.append({**row, "kinds": j["rising"]})
            elif j["rising"]:
                rising.append({**row, "label": self.named(k, label), "kinds": j["rising"], "count": j["count"], "learning": False})
            elif any(j["count"].get(kind) for kind in ("errors", "drops")):
                quiet.append({**row, "label": self.named(k, label), "count": {kind: j["count"][kind] for kind in ("errors", "drops") if j["count"].get(kind)},
                              "shares": {kind: v for kind, v in j["shares"].items() if v is not None}, "learning": j["learning"]})
        stale = sorted(k for k in known if k not in snap)
        for k in stale:
            off.append({"key": k, "label": k.split("|", 1)[-1] if "|" in k else k, "alert": False, "kinds": []})
        down = [{"key": d["key"], "label": d["label"] + (f" ({d['other']})" if d["other"] else ""), "since": d["since"]} for d in self.downs()]
        counted = self._counted(snap)
        inuse, links = self.split(counted)
        watched = []
        for k in sorted(counted, key=lambda k: snap[k][0]):
            q = snap[k][1]
            r = self.resets.get(k)
            watched.append({"label": snap[k][0], "minutes": int((q[-1][0] - q[0][0]) // 60) if len(q) > 1 else 0,
                            **({"resets": r[0], "resetKind": WORDS.get(r[1], r[1]), "resetAgoMin": int((self.clock() - r[2]) // 60),
                                **({"resetFrom": r[3], "resetTo": r[4]} if len(r) > 4 and r[3] is not None else {})} if r else {})})
        rest = [k for k in snap if k not in set(counted)]
        others = sorted(snap[k][0] for k in rest)
        groups = {}
        for k in rest:
            g = groups.setdefault(k.rsplit("|", 1)[0], {"from": snap[k][0].rsplit(", ", 1)[0], "id": k.rsplit("|", 1)[0], "count": 0, "last": 0})
            g["count"] += 1
            g["last"] = max(g["last"], snap[k][1][-1][0] if snap[k][1] else 0)
        now = self.clock()
        where = [{"from": g["from"], "id": g["id"], "count": g["count"], "lastAgoMin": int((now - g["last"]) // 60), "why": self.why.get(g["id"], "")} for g in sorted(groups.values(), key=lambda g: -g["count"])]
        cardkeys = set().union(*self.cards.values()) if self.cards else set()
        return {"on": self.enabled(), "ready": bool(self.shown), "ports": len(counted), "cards": len([k for k in counted if k in cardkeys]), "inUse": inuse, "onLinks": links, "watched": watched, "suspect": [{"from": next((snap[k][0].rsplit(", ", 1)[0] for k in sorted(snap) if k.startswith(sid + "|")), sid), "id": sid, "why": self.why[sid]} for sid in sorted(self.switch_like) if self.why.get(sid)],
                "others": {"count": len(others), "names": others[:40], "where": where, "unifiNames": self.unifi_names},
                "rising": rising, "quiet": quiet, "off": off, "down": down}

    def known(self):
        """Ports marked as a known issue, and the far end of each of those links (a known problem on a cable is known from both sides)."""
        marked = self._marked()
        return marked | {self.peers[k][0] for k in marked if k in self.peers}

    def _marked(self):
        return set(str(k) for k in self._cfg().get("known") or [])

    def _save(self, **changes):
        cfg = read_json(self.paths.config, {"schema": 4})
        pw = cfg.get("portwatch") if isinstance(cfg.get("portwatch"), dict) else {}
        pw.update(changes)
        cfg["portwatch"] = pw
        write_json(self.paths.config, cfg)

    def set_enabled(self, on):
        self._save(on=bool(on))

    def set_known(self, keys, known):
        """Mark ports (each one a list of "device id|port name" keys, like a bonded pair) as a known issue, or take the mark off."""
        now = self._marked()          # only what was marked by hand is saved, never a far end that was silenced with it
        for k in keys:
            (now.add if known else now.discard)(str(k))
        self._save(known=sorted(now))

    # ---- readings ----
    @staticmethod
    def key(dev_id, port_name):
        return f"{dev_id}|{port_name}"

    def feed(self, devices, ids, now=None, hold=()):
        """devices: the controller's devices with their `ports` (rx_errors, tx_errors, rx_dropped, tx_dropped, link_down_count); ids: their ids. `hold`: ids of devices that could not be read this round: what is known of them is kept, not forgotten."""
        now = self.clock() if now is None else now
        seen = set()
        with self.lock:
            for d, i in zip(devices, ids):
                for p in d.get("ports") or []:
                    if not isinstance(p, dict) or not p.get("name"):
                        continue
                    e = [_num(p.get("rx_errors")), _num(p.get("tx_errors"))]
                    dr = [_num(p.get("rx_dropped")), _num(p.get("tx_dropped"))]
                    fl = _num(p.get("link_down_count"))
                    pk = [_num(p.get("rx_packets")), _num(p.get("tx_packets"))]
                    if None in e or None in dr:
                        continue                                  # that switch gave no counters for this port: nothing to watch, nothing invented
                    k = self.key(i, p["name"])
                    seen.add(k)
                    self._link(k, p.get("up"), now)
                    self.labels[k] = f"{d.get('name') or 'A switch'}, {p['name']}"
                    raw = [e[0], e[1], dr[0], dr[1]]
                    off = self.off.setdefault(k, [0, 0, 0, 0])
                    prev = self.raw.get(k)
                    for n in range(4):
                        if prev and raw[n] < prev[n]:
                            for bits in (16, 32):                         # a counter that falls from just under its top went round, it did not reset
                                if (1 << bits) * 0.9 <= prev[n] < (1 << bits):
                                    off[n] += 1 << bits
                                    break
                    self.raw[k] = raw
                    a = [raw[n] + off[n] for n in range(4)]
                    row = [now, a[0] + a[1], a[2] + a[3], fl or 0, a[0], a[1], a[2], a[3]]
                    q = self.series.setdefault(k, deque())
                    if not q:
                        self._trace(now, f"start {self._nm(k)} row={row[1:]} raw={raw} off={off}")
                    if (q and len(q[-1]) >= 8 and row[3] >= q[-1][3] and any(a[n] < q[-1][4 + n] for n in range(4))
                            and all(a[n] >= q[-1][4 + n] * DIP_KEEPS for n in range(4))
                            and not (len(q[-1]) >= 10 and None not in pk and any(pk[n] < q[-1][8 + n] * DIP_KEEPS for n in range(2)))):
                        # an error or drop count fell a little, and nothing fell a long way (a restart sends every counter back to about nothing):
                        # the counter wobbled (UniFi reported SFP+ 1's receive errors 402 then 325, and 924 then 923, on 2026-10-30). Hold the old
                        # figure until the counter passes it again, so no history is lost and no error is invented.
                        if not self.held.get(k):
                            fell = [KINDS[0] if n < 2 else KINDS[1] for n in range(4) if a[n] < q[-1][4 + n]][0]
                            r = self.resets.setdefault(k, [0, fell, 0.0, None, None])
                            r[0], r[1], r[2], r[3], r[4] = r[0] + 1, fell, now, q[-1][1 if fell == "errors" else 2], row[1 if fell == "errors" else 2]
                            self._trace(now, f"{fell} dipped {self._nm(k)} was={list(q[-1])[1:8]} now={row[1:]} packets={pk} (held, carried on)")
                        self.held[k] = True
                        a = [max(a[n], q[-1][4 + n]) for n in range(4)]
                        row = [now, a[0] + a[1], a[2] + a[3], fl or 0, a[0], a[1], a[2], a[3]]
                    else:
                        self.held.pop(k, None)
                    if q and row[2] < q[-1][2] and row[1] >= q[-1][1] and row[3] >= q[-1][3]:
                        # only the drop counter fell (some NIC drivers shrink it by themselves): carry on from where it was, so the errors and link history and the learning survive
                        r = self.resets.setdefault(k, [0, "drops", 0.0, None, None])
                        r[0], r[1], r[2], r[3], r[4] = r[0] + 1, "drops", now, q[-1][2], row[2]
                        self._trace(now, f"drops fell {self._nm(k)} was={q[-1][2]} now={row[2]} raw={raw} off={off} (carried on)")
                        for n in (2, 3):
                            if a[n] < q[-1][4 + n]:
                                off[n] = q[-1][4 + n] - raw[n]
                        a = [raw[n] + off[n] for n in range(4)]
                        row = [now, a[0] + a[1], a[2] + a[3], fl or 0, a[0], a[1], a[2], a[3]]
                    if q and any(row[j] < q[-1][j] for j in (1, 2, 3)):
                        col = next(j for j in (1, 2, 3) if row[j] < q[-1][j])
                        kind = KINDS[col - 1]
                        r = self.resets.setdefault(k, [0, kind, 0.0, None, None])
                        r[0], r[1], r[2], r[3], r[4] = r[0] + 1, kind, now, q[-1][col], row[col]      # what it read before and what it reads now: shown on the page
                        self.off[k] = [0, 0, 0, 0]
                        row = [now, raw[0] + raw[1], raw[2] + raw[3], fl or 0, raw[0], raw[1], raw[2], raw[3]]
                        self._trace(now, f"reset {self._nm(k)} {kind} to={row[1:]} was={list(q[-1])[1:]}")
                        q.clear()                                 # a counter went backwards: the device restarted, so start again from here
                    if None not in pk:
                        row = row + [int(pk[0]), int(pk[1])]               # packets received and sent, so a drop count can be judged as a share of the traffic
                    if not q or now - self.slot.get(k, q[-1][0]) >= EVERY:
                        q.append(row)
                        self.slot[k] = now
                    else:
                        q[-1] = row                               # same slot, newer figures (the slot keeps its start: otherwise a round every 10 s would never reach the next slot)
                    while q and q[0][0] < now - KEEP:
                        q.popleft()
            here = {i for _, i in zip(devices, ids)}                    # the devices that answered this round
            for k in [k for k in self.series if k not in seen and k.rsplit("|", 1)[0] not in hold and not self._was_in_use(k, now)
                      and (k.rsplit("|", 1)[0] in here or not self.series[k] or self.series[k][-1][0] < now - KEEP)]:   # a port gone from a device that answered, or one not seen for a day
                self._trace(now, f"gone {self._nm(k)} (not read this round)")
                del self.series[k]
                self.labels.pop(k, None)
                self.links.pop(k, None)
                self.raw.pop(k, None); self.off.pop(k, None); self.slot.pop(k, None)
            if self.shown:                                              # readings of interfaces the map does not show and nothing has fed for a while: forgotten
                for k in [k for k in self.series if k not in self.shown and k not in seen and k.rsplit("|", 1)[0] not in hold and not self._was_in_use(k, now)
                          and (not self.series[k] or self.series[k][-1][0] < now - STALE_OTHERS)]:
                    self._trace(now, f"stale {self._nm(k)} (not on the map, no reading for a while)")
                    del self.series[k]
                    self.labels.pop(k, None)
                    self.links.pop(k, None)
                    self.raw.pop(k, None); self.off.pop(k, None); self.slot.pop(k, None)
            if seen:
                self.fed = True
            applog.debug("portwatch", f"round: {len(seen)} ports read, {len(self.series)} kept, {len(hold)} devices held back")
        self.save(now)

    def _links(self, k):
        """Packet drops and link drops count on this port: an uplink, a link between switches, or a server (the map says which; every network card read over SNMP is a server's)."""
        return k in self.flap_ports or (k.startswith("snmp:") and k not in self.client_ports)

    def _is_server(self, k):
        """A network card of a server read over SNMP (not a switch port): see judge()."""
        dev = k.rsplit("|", 1)[0]
        return k.startswith("snmp:") and dev in self.cards and dev not in self.switches

    def _speed(self, k):
        return self.speeds.get(k) or self.card_speeds.get(k)

    def _was_in_use(self, k, now):
        """The map showed this port within the last day: its device may just be asleep (a Mac that wakes for a backup), so what it learned is kept."""
        t = self.used_at.get(k)
        return t is not None and t >= now - KEEP

    def _link(self, k, up, now):
        """Follows whether a port's link is up. A link that has stayed up for an hour becomes expected; one that never came up never does (a server's unplugged cards stay quiet).
        A link that comes back after "not coming back" starts again from here."""
        if not isinstance(up, bool):
            return
        L = self.links.get(k)
        if L is None:
            self.links[k] = {"up": up, "since": now, "expected": False}
            return
        if L["up"] != up:
            L["up"], L["since"] = up, now
            if up:
                L["expected"] = False
                if k in self._gone():
                    self._save(gone=sorted(self._gone() - {k}))          # it lit again: the "not coming back" is over
        if L["up"] and not L["expected"] and now - L["since"] >= EXPECT_AFTER:
            L["expected"] = True

    def _gone(self):
        return set(str(k) for k in self._cfg().get("gone") or [])

    def set_gone(self, keys, gone):
        """"Not coming back": forget that these links are expected up, until they light again. gone=False takes it back."""
        now = self._gone()
        for k in keys:
            (now.add if gone else now.discard)(str(k))
        self._save(gone=sorted(now))

    def downs(self):
        """Expected links that are down now, once per cable: [{key, label, since, other}]. Only uplinks, links between devices and servers (never an ordinary client's port)."""
        known, gone, now = self.known(), self._gone(), self.clock()
        with self.lock:
            cand = {k: dict(L) for k, L in self.links.items() if L["expected"] and not L["up"] and now - L["since"] >= DOWN_AFTER
                    and self._links(k) and k not in known and k not in gone}
            labels = {k: self.labels.get(k, k) for k in cand}
        out = []
        for k, L in sorted(cand.items(), key=lambda x: labels[x[0]]):
            peer = self.peers.get(k)
            if peer and peer[0] in cand and peer[0] < k:
                continue                                              # the other end of the same cable is already listed
            out.append({"key": k, "label": labels[k], "since": L["since"], "other": peer[1] if peer and peer[0] in cand else None})
        return out

    def set_attached(self, names):
        self.attached = {k: str(v) for k, v in names.items() if v}

    def named(self, key, label):
        who = self.attached.get(key)
        label = f"{label} ({who})" if who and key not in self.peers else label
        return f"{label} (in {self.members[key]})" if self.members.get(key) else label

    def set_peers(self, peers):
        """The port at the other end of each link between two devices, so a port can say what its far end is doing."""
        self.peers = dict(peers)

    def other_end(self, key):
        """What the port at the other end of this link is doing, or None when this port is not one end of a link between two devices.
        {"label", "state": "figures"|"learning"|"none", "split": {kind: {rx, tx}}}. "none": that end gave no counters."""
        peer = self.peers.get(key)
        if not peer:
            return None
        pk, label = peer
        with self.lock:
            q = list(self.series.get(pk) or [])
        if not q:
            return {"label": label, "state": "none", "split": {}}
        j = judge(q, self._links(pk), self._speed(pk), self._is_server(pk))
        if not j["split"]:
            return {"label": label, "state": "learning", "split": {}}
        return {"label": label, "state": "figures", "split": j["split"]}

    def set_speeds(self, speeds):
        self.speeds = dict(speeds)

    def set_shown(self, keys, used=(), link_ends=()):
        """keys: the ports the map shows. used: those listed under a device (in use). link_ends: the ends of links between devices that are not in that list."""
        self.shown, self.used, self.link_ends = set(keys), set(used), set(link_ends)
        now = self.clock()
        for k in self.shown:
            self.used_at[k] = now
        for k in [k for k, t in self.used_at.items() if t < now - KEEP]:
            del self.used_at[k]

    def split(self, keys):
        """(ports in use, link ports) among these keys, for saying what the count is made of."""
        keys = set(keys)
        return len(keys & self.used), len(keys & self.link_ends)

    def _counted(self, keys):
        keys = list(keys)
        cards = set().union(*self.cards.values()) if self.cards else set()
        mine = [k for k in keys if k in self.shown or k in cards]
        return mine or keys           # nothing matched the map (or no map yet): count what is read rather than say there is nothing

    def _nm(self, k):
        """A port as the owner knows it ("Bonus Room, Port 7"); the internal key only when no name is known."""
        return self.labels.get(k) or k

    def _trace(self, now, what):
        """One line in the App's log whenever a port's history is started, thrown away or forgotten (the reason is the line)."""
        applog.info("portwatch", what)

    def only_for(self, dev):
        """The names of this device's ports that are worth reading (the ones the map shows), or None while that is not known: then everything is read."""
        pre = f"{dev}|"
        mine = {k[len(pre):] for k in self.shown if k.startswith(pre)}
        return sorted(mine) if mine else None

    def set_why(self, dev, text):
        self.why[dev] = text

    def set_unifi_names(self, names):
        self.unifi_names = list(names)

    def drop_device(self, dev):
        """Forgets every reading of one device id (it turned out to be read under another id)."""
        pre = f"{dev}|"
        with self.lock:
            self.switch_like.discard(dev)
            for k in [k for k in self.series if k.startswith(pre)]:
                self._trace(self.clock(), f"drop_device {self._nm(k)}")
                del self.series[k]
                self.labels.pop(k, None)
                self.links.pop(k, None)

    def set_cards(self, sid, up_keys, members=None):
        """The network cards of one SNMP server that have a link (they count as ports in use), and which bond or team each belongs to."""
        with self.lock:
            self.cards[sid] = set(up_keys)
            pre = f"{sid}|"
            for k in [k for k in self.members if k.startswith(pre)]:
                del self.members[k]
            self.members.update({k: v for k, v in (members or {}).items() if v})

    def last_flaps(self, key):
        """The last link-drop count kept for a port (0 if none): a restarted box carries on from it instead of counting from zero, which would look like a device restart."""
        with self.lock:
            q = self.series.get(key)
            return int(q[-1][3]) if q else 0

    def set_is_switch(self, sid, on):
        """Whether an SNMP device is a switch (it learns addresses or hears neighbours): its ports are not a server's cards, whether or not UniFi is there too."""
        with self.lock:
            (self.switches.add if on else self.switches.discard)(sid)

    def set_switch_like(self, sid, on):
        with self.lock:
            (self.switch_like.add if on else self.switch_like.discard)(sid)

    def set_snmp_ports(self, sid, speeds, clients):
        """What one SNMP device's own report says about its ports (key -> speed in Mbit/s), and which of them look like a client's, for a device that is a switch."""
        with self.lock:
            pre = sid + "|"
            self.card_speeds = {**{k: v for k, v in self.card_speeds.items() if not k.startswith(pre)}, **{k: v for k, v in speeds.items() if isinstance(v, (int, float)) and v > 0}}
            self.client_ports = {k for k in self.client_ports if not k.startswith(pre)} | set(clients)

    def set_flap_ports(self, keys):
        """The ports whose link drops are worth reporting. A port with a laptop or a TV on it drops every time that sleeps, so it is left out."""
        self.flap_ports = set(keys)

    def forget(self):
        self._trace(self.clock(), "forget (watch switched off)")
        with self.lock:
            self.series.clear()
            self.labels.clear()
        try:
            os.remove(self.history_path)
        except OSError:
            pass

    # ---- the history, kept across a restart ----
    def save(self, now=None, force=False):
        """Keeps the last day of readings on disk, thinned to one reading every five minutes, at most every five minutes: a restart then resumes with what
        each port normally does instead of learning for half an hour again. Read-only data about the network (names and counters); not readable by other users."""
        now = self.clock() if now is None else now
        if not force and now - self._saved_at < SAVE_EVERY:
            return
        with self.lock:
            if not self.series:
                return
            thin = {}
            for k, q in self.series.items():
                keep, slot = [], None
                for row in q:
                    b = int(row[0] // SAVE_EVERY)
                    if b == slot:
                        keep[-1] = row                      # the last reading of each five minutes
                    else:
                        keep.append(row); slot = b
                thin[k] = {"label": self.labels.get(k, k), "rows": keep}
            self._saved_at = now
        try:
            os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
            tmp = self.history_path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"saved": now, "ports": thin, "links": {k: dict(v) for k, v in self.links.items()},
                           "shown": {"all": sorted(self.shown), "used": sorted(self.used), "ends": sorted(self.link_ends), "speeds": self.speeds, "usedAt": self.used_at, "cards": {k: sorted(v) for k, v in self.cards.items()}},
                           "wrap": {k: {"raw": self.raw[k], "off": o} for k, o in self.off.items() if any(o) and k in self.raw and k in self.series}}, f, separators=(",", ":"))
            os.replace(tmp, self.history_path)
        except OSError:
            pass                                            # only a slower start next time

    def restore(self):
        """Loads the saved history (only while the watch is on, and only what is less than a day old)."""
        if not self.enabled():
            return 0
        try:
            with open(self.history_path) as f:
                data = json.load(f)
            ports = data["ports"]
            now = self.clock()
            if not isinstance(ports, dict) or now - float(data["saved"]) > KEEP:
                return 0
        except (OSError, ValueError, KeyError, TypeError):
            return 0
        n = 0
        with self.lock:
            for k, v in ports.items():
                try:
                    rows = [[float(r[0])] + [int(x) for x in r[1:]] for r in v["rows"] if now - float(r[0]) <= KEEP and len(r) >= 4]
                except (TypeError, ValueError, KeyError):
                    continue
                if rows:
                    self.series[str(k)] = deque(rows)
                    self.labels[str(k)] = str(v.get("label") or k)
                    n += 1
        try:
            for k, v in (data.get("links") or {}).items():
                if isinstance(v, dict) and isinstance(v.get("up"), bool) and isinstance(v.get("since"), (int, float)):
                    self.links[str(k)] = {"up": v["up"], "since": float(v["since"]), "expected": v.get("expected") is True}
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            for k, v in (data.get("wrap") or {}).items():       # ports whose counter has wrapped: without this a restart would read the next wrap as a reset
                if str(k) in self.series and len(v["raw"]) == 4 and len(v["off"]) == 4:
                    self.raw[str(k)], self.off[str(k)] = [int(x) for x in v["raw"]], [int(x) for x in v["off"]]
        except (AttributeError, TypeError, ValueError, KeyError):
            pass
        try:
            sh = data.get("shown") or {}
            if not self.shown and isinstance(sh.get("all"), list):      # which ports the map showed last time: the count is right from the first second, before the map is rebuilt
                self.shown = {str(k) for k in sh["all"]}
                self.used = {str(k) for k in sh.get("used") or []}
                self.link_ends = {str(k) for k in sh.get("ends") or []}
                self.speeds = {str(k): v for k, v in (sh.get("speeds") or {}).items() if isinstance(v, (int, float))}
                self.used_at = {str(k): v for k, v in (sh.get("usedAt") or {}).items() if isinstance(v, (int, float))}
                self.cards = {str(k): {str(x) for x in v} for k, v in (sh.get("cards") or {}).items() if isinstance(v, list)}
        except (AttributeError, TypeError, ValueError):
            pass
        self.restored = n
        self._trace(self.clock(), f"restored {n} ports from the saved history")
        return n

    # ---- answers ----
    def state(self, keys):
        """One map port (one or several keys, a bonded pair) in words and figures, or None when there is nothing to say."""
        known = self.known()
        with self.lock:
            js = [judge(list(self.series[k]), self._links(k), self._speed(k), self._is_server(k)) for k in keys if k in self.series]
        if not js:
            return None
        per = {kind: sum(j["count"].get(kind, 0) for j in js) for kind in KINDS}
        was = {kind: (None if any(j["was"].get(kind) is None for j in js) else sum(j["was"][kind] for j in js)) for kind in KINDS}
        rising = sorted({kind for j in js for kind in j["rising"]}, key=KINDS.index)
        split = {kind: {side: sum(j["split"][kind][side] for j in js if kind in j["split"]) for side in ("rx", "tx")} for kind in SPLIT if any(kind in j["split"] for j in js)}
        busy = self.traffic(list(keys), RECENT) if self.traffic else None
        other = self.other_end(keys[0]) if len(keys) == 1 else None
        shares = {kind: max(v) for kind in ("errors", "drops") if (v := [j["shares"][kind] for j in js if j["shares"].get(kind) is not None])}
        return {"other": other, "learning": all(j["learning"] for j in js), "rising": rising, "count": per, "was": was, "split": split, "traffic": busy, "shares": shares,
                "known": any(k in known for k in keys)}

    def findings(self):
        """[{label, kinds, count, was, split, traffic}] for ports that are rising and not marked known."""
        known = self.known()
        with self.lock:
            snap = {k: (self.labels.get(k, k), list(q)) for k, q in self.series.items()}
        out = []
        for k, (label, q) in sorted(snap.items(), key=lambda x: x[1][0]):
            j = judge(q, self._links(k), self._speed(k), self._is_server(k))
            if j["rising"] and k not in known:
                out.append({"label": self.named(k, label), "kinds": j["rising"], "count": j["count"], "was": j["was"], "split": j["split"], "share": j["share"], "shares": j.get("shares", {}), "other": self.other_end(k),
                            "traffic": self.traffic([k], RECENT) if self.traffic else None})
        return out

    def check(self):
        """The built-in check: (ok, detail, ms, extra). Degraded (a warning) while any watched port is rising; never a failure."""
        if not self.enabled():
            return None, "port watching is switched off", None, {}
        with self.lock:
            mine = self._counted(self.series)
            n = len(mine)
            ready = sum(1 for k in mine if len(self.series[k]) >= 2 and self.series[k][-1][0] - self.series[k][0][0] >= MIN_HISTORY)
        if not self.fed and self.clock() - self.started < FIRST_READINGS:
            return None, "waiting for the first port readings", None, {"starting": True}      # a restart: its counters come in a moment, that is not "unknown"
        if not self.fed:
            return None, "no switch port counters to read yet", None, {}
        if not n:
            return None, "no switch port counters to read yet", None, {}
        found, downs = self.findings(), self.downs()
        if not found and not downs:
            if ready < n:
                return True, f"learning what is normal ({ready} of {n} ports ready)", None, {}
            return True, f"all {n} ports look normal", None, {}
        parts = []
        for f in found[:3]:
            per, was, split = f["count"], f["was"], f["split"]
            what = " and ".join(f"{WORDS[k]} rising ({per[k]:,} in the last 15 min"
                                + (f": {split[k]['rx']:,} receive, {split[k]['tx']:,} transmit" if k in split else "")
                                + (f", {one_in(f['shares'][k])}" if (f.get('shares') or {}).get(k) else "")
                                + ((", none before" if not was[k] else f", earlier at most {was[k]:,} in 15 min") if was[k] is not None else "") + ")" for k in f["kinds"])
            busy, other = f["traffic"], f["other"]
            kind = next((k for k in f["kinds"] if k in SPLIT), None)
            far = ""
            if other and kind:
                far = (f" · other end ({other['label']}): " + (f"{other['split'][kind]['rx']:,} receive, {other['split'][kind]['tx']:,} transmit in the last 15 min" if other["state"] == "figures"
                                                          else "still learning" if other["state"] == "learning" else "no counters"))
            parts.append(f"{f['label']}: {what}" + (f", carrying about {bps_words(busy['avgBps'])} (peak {bps_words(busy['peakBps'])})" if busy else "") + far)
        more = f" (and {len(found) - 3} more)" if len(found) > 3 else ""
        for d in downs[:3]:
            mins = max(1, int((self.clock() - d["since"]) // 60))
            parts.append(f"{d['label']}{' (' + d['other'] + ')' if d['other'] else ''}: link is down (was up, down for {mins} min)")
        if len(downs) > 3:
            more += f" (and {len(downs) - 3} more links down)"
        return True, "; ".join(parts) + more, None, {"warn": True, "names": [f["label"] for f in found] + [d["label"] for d in downs]}      # every port, not only the three the text has room for: History names them all
