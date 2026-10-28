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

from .store import read_json, write_json

STALE_OTHERS = 1800      # seconds: an interface the map does not show, with no new reading for this long, is dropped
KEEP = 24 * 3600          # seconds of readings kept per port (a day, so the last busy spell is still remembered)
EVERY = 30                # at most one kept reading per port per this many seconds
RECENT = 900              # the window that is compared with the port's earlier pace (15 minutes)
MIN_HISTORY = 1800        # readings of a port needed before it can be called rising (30 minutes)
RISE = 5                  # the recent pace must be at least this many times the earlier pace
FLOOR = {"errors": 20, "drops": 10000, "flaps": 3}     # new in the window, at least, before it is worth a line, on a 1 Gbit link; errors and drops scale with the link speed (below)
FLOOR_MIN = {"errors": 20, "drops": 1000}               # ... but never lower than this, however slow the link
WORDS = {"errors": "errors", "drops": "drops", "flaps": "link drops"}
KINDS = ("errors", "drops", "flaps")
EXPECT_AFTER = 3600       # seconds a link must have been up without a break before it is expected to stay up (learned, no setup)
DOWN_AFTER = 60           # seconds an expected link must be down before it is worth a heads-up
SAVE_EVERY = 300          # seconds between saves of the history; it is kept thinned to one reading per this long
FIRST_READINGS = 180      # seconds after a start that the first counters are waited for before the check says it cannot read any


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


def judge(q, flaps=True, speed=None):
    """How one port is doing, from its readings [[t, errors, drops, flaps], ...] (oldest first).
    -> {"learning": bool, "rising": [kinds], "perHour": {kind: new per hour over the last 15 minutes}, "was": {kind: earlier per hour}}"""
    out = {"learning": True, "rising": [], "perHour": {}, "was": {}, "split": {}}
    if len(q) < 2:
        return out
    now, first = q[-1][0], q[0][0]
    if now - first < RECENT:
        return out
    cut = _at(q, now - RECENT)
    span_before = cut[0] - first
    out["learning"] = now - first < MIN_HISTORY
    for i, kind in enumerate(KINDS, start=1):
        if kind == "flaps" and not flaps:
            continue                                              # a client port drops whenever a laptop sleeps: only uplinks and servers are worth it
        new = q[-1][i] - cut[i]
        out["perHour"][kind] = round(new * 3600 / RECENT)
        if kind in SPLIT and len(q[-1]) >= 8 and len(cut) >= 8:     # receive and transmit apart: a bad link shows as receive errors, a backed-up port as transmit drops
            a, b = SPLIT[kind]
            out["split"][kind] = {"rx": round((q[-1][a] - cut[a]) * 3600 / RECENT), "tx": round((q[-1][b] - cut[b]) * 3600 / RECENT)}
        worst = _worst(q, cut[0], i)
        if worst is None and span_before >= 60:
            worst = cut[i] - q[0][i]                                  # less than one stretch of history: what there was
        was = None if worst is None else worst * 3600 / RECENT
        out["was"][kind] = None if was is None else round(was)
        if out["learning"] or new < floor_for(kind, speed):
            continue
        if was is None or new * 3600 / RECENT >= RISE * was:
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
        self.speeds = {}          # key -> link speed in Mbit/s, from the map, so the minimums scale with the port
        self.flap_ports = set()   # keys of ports whose link drops count: uplinks, links between switches, and servers (set from the map)
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
        rising, off = [], []
        for k, (label, q) in sorted(snap.items(), key=lambda x: x[1][0]):
            j = judge(q, k in self.flap_ports, self.speeds.get(k))
            row = {"key": k, "label": label, "alert": k not in known}
            if k in known:
                off.append({**row, "kinds": j["rising"]})
            elif j["rising"]:
                rising.append({**row, "label": self.named(k, label), "kinds": j["rising"], "perHour": j["perHour"], "learning": False})
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
                            **({"resets": r[0], "resetKind": WORDS.get(r[1], r[1]), "resetAgoMin": int((self.clock() - r[2]) // 60)} if r else {})})
        rest = [k for k in snap if k not in set(counted)]
        others = sorted(snap[k][0] for k in rest)
        groups = {}
        for k in rest:
            g = groups.setdefault(k.rsplit("|", 1)[0], {"from": snap[k][0].rsplit(", ", 1)[0], "id": k.rsplit("|", 1)[0], "count": 0, "last": 0})
            g["count"] += 1
            g["last"] = max(g["last"], snap[k][1][-1][0] if snap[k][1] else 0)
        now = self.clock()
        where = [{"from": g["from"], "id": g["id"], "count": g["count"], "lastAgoMin": int((now - g["last"]) // 60), "why": self.why.get(g["id"], "")} for g in sorted(groups.values(), key=lambda g: -g["count"])]
        return {"on": self.enabled(), "ready": bool(self.shown), "ports": len(counted), "inUse": inuse, "onLinks": links, "watched": watched, "others": {"count": len(others), "names": others[:40], "where": where, "unifiNames": self.unifi_names},
                "rising": rising, "off": off, "down": down}

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
                    if None in e or None in dr:
                        continue                                  # that switch gave no counters for this port: nothing to watch, nothing invented
                    k = self.key(i, p["name"])
                    seen.add(k)
                    self._link(k, p.get("up"), now)
                    self.labels[k] = f"{d.get('name') or 'A switch'}, {p['name']}"
                    row = [now, sum(e), sum(dr), fl or 0, e[0], e[1], dr[0], dr[1]]
                    q = self.series.setdefault(k, deque())
                    if q and any(row[j] < q[-1][j] for j in (1, 2, 3)):
                        kind = KINDS[next(j for j in (1, 2, 3) if row[j] < q[-1][j]) - 1]
                        r = self.resets.setdefault(k, [0, kind, 0.0])
                        r[0], r[1], r[2] = r[0] + 1, kind, now
                        q.clear()                                 # a counter went backwards: the device restarted, so start again from here
                    if not q or now - q[-1][0] >= EVERY:
                        q.append(row)
                    else:
                        q[-1] = row                               # same slot, newer figures
                    while q and q[0][0] < now - KEEP:
                        q.popleft()
            here = {i for _, i in zip(devices, ids)}                    # the devices that answered this round
            for k in [k for k in self.series if k not in seen and k.rsplit("|", 1)[0] not in hold
                      and (k.rsplit("|", 1)[0] in here or not self.series[k] or self.series[k][-1][0] < now - KEEP)]:   # a port gone from a device that answered, or one not seen for a day
                del self.series[k]
                self.labels.pop(k, None)
                self.links.pop(k, None)
            if self.shown:                                              # readings of interfaces the map does not show and nothing has fed for a while: forgotten
                for k in [k for k in self.series if k not in self.shown and k not in seen and k.rsplit("|", 1)[0] not in hold
                          and (not self.series[k] or self.series[k][-1][0] < now - STALE_OTHERS)]:
                    del self.series[k]
                    self.labels.pop(k, None)
                    self.links.pop(k, None)
            if seen:
                self.fed = True
        self.save(now)

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
                    and (k in self.flap_ports or k.startswith("snmp:")) and k not in known and k not in gone}
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
        return f"{label} ({who})" if who and key not in self.peers else label

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
        j = judge(q, pk in self.flap_ports, self.speeds.get(pk))
        if not j["split"]:
            return {"label": label, "state": "learning", "split": {}}
        return {"label": label, "state": "figures", "split": j["split"]}

    def set_speeds(self, speeds):
        self.speeds = dict(speeds)

    def set_shown(self, keys, used=(), link_ends=()):
        """keys: the ports the map shows. used: those listed under a device (in use). link_ends: the ends of links between devices that are not in that list."""
        self.shown, self.used, self.link_ends = set(keys), set(used), set(link_ends)

    def split(self, keys):
        """(ports in use, link ports) among these keys, for saying what the count is made of."""
        keys = set(keys)
        return len(keys & self.used), len(keys & self.link_ends)

    def _counted(self, keys):
        keys = list(keys)
        mine = [k for k in keys if k in self.shown]
        return mine or keys           # nothing matched the map (or no map yet): count what is read rather than say there is nothing

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
            for k in [k for k in self.series if k.startswith(pre)]:
                del self.series[k]
                self.labels.pop(k, None)
                self.links.pop(k, None)

    def set_flap_ports(self, keys):
        """The ports whose link drops are worth reporting. A port with a laptop or a TV on it drops every time that sleeps, so it is left out."""
        self.flap_ports = set(keys)

    def forget(self):
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
                           "shown": {"all": sorted(self.shown), "used": sorted(self.used), "ends": sorted(self.link_ends), "speeds": self.speeds}}, f, separators=(",", ":"))
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
            sh = data.get("shown") or {}
            if not self.shown and isinstance(sh.get("all"), list):      # which ports the map showed last time: the count is right from the first second, before the map is rebuilt
                self.shown = {str(k) for k in sh["all"]}
                self.used = {str(k) for k in sh.get("used") or []}
                self.link_ends = {str(k) for k in sh.get("ends") or []}
                self.speeds = {str(k): v for k, v in (sh.get("speeds") or {}).items() if isinstance(v, (int, float))}
        except (AttributeError, TypeError, ValueError):
            pass
        self.restored = n
        return n

    # ---- answers ----
    def state(self, keys):
        """One map port (one or several keys, a bonded pair) in words and figures, or None when there is nothing to say."""
        known = self.known()
        with self.lock:
            js = [judge(list(self.series[k]), k in self.flap_ports, self.speeds.get(k)) for k in keys if k in self.series]
        if not js:
            return None
        per = {kind: sum(j["perHour"].get(kind, 0) for j in js) for kind in KINDS}
        was = {kind: (None if any(j["was"].get(kind) is None for j in js) else sum(j["was"][kind] for j in js)) for kind in KINDS}
        rising = sorted({kind for j in js for kind in j["rising"]}, key=KINDS.index)
        split = {kind: {side: sum(j["split"][kind][side] for j in js if kind in j["split"]) for side in ("rx", "tx")} for kind in SPLIT if any(kind in j["split"] for j in js)}
        busy = self.traffic(list(keys), RECENT) if self.traffic else None
        other = self.other_end(keys[0]) if len(keys) == 1 else None
        return {"other": other, "learning": all(j["learning"] for j in js), "rising": rising, "perHour": per, "was": was, "split": split, "traffic": busy,
                "known": any(k in known for k in keys)}

    def findings(self):
        """[{label, kinds, perHour, was, split, traffic}] for ports that are rising and not marked known."""
        known = self.known()
        with self.lock:
            snap = {k: (self.labels.get(k, k), list(q)) for k, q in self.series.items()}
        out = []
        for k, (label, q) in sorted(snap.items(), key=lambda x: x[1][0]):
            j = judge(q, k in self.flap_ports, self.speeds.get(k))
            if j["rising"] and k not in known:
                out.append({"label": self.named(k, label), "kinds": j["rising"], "perHour": j["perHour"], "was": j["was"], "split": j["split"], "other": self.other_end(k),
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
                return True, f"nothing rising so far ({ready} of {n} ports have half an hour of readings)", None, {}
            return True, f"no port is getting worse ({n} ports watched)", None, {}
        parts = []
        for f in found[:3]:
            per, was, split = f["perHour"], f["was"], f["split"]
            what = " and ".join(f"{WORDS[k]} rising (about {per[k]:,} an hour"
                                + (f": {split[k]['rx']:,} receive, {split[k]['tx']:,} transmit" if k in split else "")
                                + (f", was {was[k]:,}" if was[k] is not None else "") + ")" for k in f["kinds"])
            busy, other = f["traffic"], f["other"]
            kind = next((k for k in f["kinds"] if k in SPLIT), None)
            far = ""
            if other and kind:
                far = (f" · other end ({other['label']}): " + (f"{other['split'][kind]['rx']:,} receive, {other['split'][kind]['tx']:,} transmit an hour" if other["state"] == "figures"
                                                          else "still learning" if other["state"] == "learning" else "no counters"))
            parts.append(f"{f['label']}: {what}" + (f", carrying about {bps_words(busy['avgBps'])} (peak {bps_words(busy['peakBps'])})" if busy else "") + far)
        more = f" (and {len(found) - 3} more)" if len(found) > 3 else ""
        for d in downs[:3]:
            mins = max(1, int((self.clock() - d["since"]) // 60))
            parts.append(f"{d['label']}{' (' + d['other'] + ')' if d['other'] else ''}: link is down (was up, down for {mins} min)")
        if len(downs) > 3:
            more += f" (and {len(downs) - 3} more links down)"
        return True, "; ".join(parts) + more, None, {"warn": True}
