"""Reads every switch port's traffic every few seconds into the port history (portpeers.PortSeries), read-only.

UniFi gives every device's ports and rates in one request. A switch that is also an SNMP connection (matched by its address) is read
over SNMP instead, which gives exact counters for every port. Ports are keyed by (device id, the port's name as UniFi spells it), so
a switch's history lines up with its place on the map. A source that does not answer is skipped; nothing is invented."""
import re
import threading, time

from . import lanmap, followups

squash = lanmap.squash


EVERY = 10.0
SERVER_EVERY = 3        # a server's network cards are read every third round (30 s): the port watch moves slowly
WIFI = "wifi"           # the history's stand-in for a switch: every Wi-Fi client is a "port" under it


ROLES_EVERY = 600


def stacked(name):
    """A bond or team master, or a VLAN sub-interface: it only repeats the physical ports under it, so it is not a port of its own (one fault would show as three rows)."""
    n = str(name or "").strip().lower()
    if re.match(r"^(dummy|lxdbr|lxcbr|virbr|docker|ifb|sit|ip6tnl|ip6gre|gre|gretap|erspan|tunl|nlmon)\d*$", n):
        return True        # leftovers that are not a cable at all: dummy and container bridges, tunnel stubs
    return bool(re.match(r"^(bond|team|vlan|po|port-channel|ae|lag)\d+$", n) or re.match(r"^(vlan|bond|team)[-_ ]?\d+$", n) or re.match(r"^[a-z][a-z0-9_-]*\d+\.\d+$", n))


class LanSampler:
    def __init__(self, series, load_conns, call, clock=time.time, after=None, watch=None):
        """call(module, method, params, timeout) -> result, like the module runner."""
        self.series, self.load_conns, self.call, self.clock, self.after = series, load_conns, call, clock, after
        self.watch = watch      # portwatch.PortWatch: fed the error and drop counters only while its tick is on
        self.stopping = threading.Event()
        self.thread = None
        self.status = {"at": 0.0, "switches": 0, "snmp": 0, "unifi": 0}
        self.rounds = 0
        self.sys_raw = {}       # SNMP connection id -> the device's own name as it reported it
        self.explain = lambda c: ""
        self.macs_of = {}       # SNMP connection id -> the shortened addresses of all its interfaces ("..:dd:ee:ff", like the UniFi report): the surest way to tell which UniFi device it is
        self.links = {}         # server card key -> {"n": link drops counted, "abs": when its link last changed, "up": whether it was up}: the box counts them itself, from each card's last-change time
        self.uptime = {}        # server id -> its uptime when last read: a drop in it is a restart, not a flap
        self.sys_of = {}        # SNMP connection id -> the device's own name (sysName), squashed: tells which UniFi device a connection is when the address does not
        self.roles = {}         # server id -> {"at", "switch", "links"}: which ports of an SNMP device that learns addresses or hears neighbours (a switch) are uplinks or links, read every ROLES_EVERY seconds
        self.has_unifi = False  # UniFi gave devices this round
        self.matched = {}       # SNMP connection id -> the id of the UniFi device it is, as last worked out: the map leaves those out (they are drawn as the UniFi device)
        self.wifi = {}          # port name in the history (under WIFI) -> {"name", "ap"}: the Wi-Fi clients read this round

    def tick(self):
        conns = [c for c in self.load_conns() if isinstance(c, dict) and c.get("id")]
        unifis = [c for c in conns if c.get("module") == "unifi-network"]
        if not unifis and not any(c.get("module") == "snmp" for c in conns):
            self.status.update(at=self.clock(), switches=0, snmp=0, unifi=0)
            return
        devices, wifi = [], {}
        for u in unifis:
            try:
                r = self.call("unifi-network", "lan_report", {"connection": u, "clients": True}, 30)
            except Exception:
                continue
            devices += lanmap.tell_ports_apart([d for d in (r or {}).get("devices") or [] if isinstance(d, dict)])
            for c in (r or {}).get("clients") or []:
                # a Wi-Fi client has no switch port of its own; the controller's per-client rate (through the access point, so local traffic too) stands in for one.
                # rx/tx are kept as the controller names them: which way they point is settled against the port being asked about (server.lan_peers), not assumed here.
                if not isinstance(c, dict) or c.get("wired") or not isinstance(c.get("rxBps"), (int, float)) or not isinstance(c.get("txBps"), (int, float)):
                    continue
                name = str(c.get("name") or c.get("ip") or "").strip()
                if name:
                    wifi[f"{name}|{c.get('mac') or ''}"] = {"name": name, "ap": c.get("ap"), "rx": c["rxBps"], "tx": c["txBps"]}
        if unifis and not devices:
            # UniFi gave no devices this round (slow or unreachable, e.g. just after a restart). Without its list nothing can be matched, so every SNMP switch would be read as a
            # server and every port forgotten: an outage is Unknown, not a different picture. Leave everything as it was until the next round.
            self.status.update(at=self.clock(), unifi=len(unifis), unifiEmpty=True)
            return
        self.status["unifiEmpty"] = False
        self.has_unifi = bool(devices)
        ids = lanmap.device_ids(devices)
        now = self.clock()
        by_ip = {str(d.get("ip") or "").strip().lower(): i for d, i in zip(devices, ids) if d.get("ip")}
        by_name = {}
        for d, i in zip(devices, ids):
            by_name.setdefault(squash(d.get("name")), []).append(i)

        by_mac = {}
        for d, i in zip(devices, ids):
            if str(d.get("mac") or "").startswith("..:"):
                by_mac.setdefault(d["mac"].lower(), []).append(i)

        def match(c):
            """The UniFi device an SNMP connection is: by its address, else by an interface address that exactly one UniFi device has, else by a name (the connection's, or the device's own sysName) that exactly one UniFi device has
            (the SNMP address is often not the one UniFi lists)."""
            hit = by_ip.get(followups.host_of(c))
            if hit:
                return hit
            found = {i for m in self.macs_of.get(str(c.get("id")), []) for i in by_mac.get(m, [])}
            if len(found) == 1:
                return next(iter(found))
            for nm in (squash(c.get("name")), self.sys_of.get(str(c.get("id")), "")):
                same = by_name.get(nm) or [] if nm else []
                if len(same) == 1:
                    return same[0]
            return None

        def explain(c):
            """Why a connection is read as a server: what it was matched on and what UniFi calls its devices (shown on the Port errors page, so a mismatch can be seen)."""
            host, nm, own = followups.host_of(c), squash(c.get("name")), self.sys_of.get(str(c.get("id")), "")
            macs = self.macs_of.get(str(c.get("id")), [])
            return (f"address {host or '?'} is not a UniFi device address; {len(macs)} interface addresses match {len({i for m in macs for i in by_mac.get(m, [])})} of {len(devices)} UniFi devices; name \"{c.get('name') or ''}\" (compared as \"{nm}\") matches {len(by_name.get(nm) or [])} of {len(devices)} UniFi devices; "
                    f"its own name \"{self.sys_raw.get(str(c.get('id')), '') or 'not reported'}\" (compared as \"{own}\") matches {len(by_name.get(own) or []) if own else 0}")
        self.explain = explain
        if self.watch is not None:
            self.watch.set_unifi_names(sorted({f"{d.get('name')} (as \"{squash(d.get('name'))}\")" for d in devices if d.get("name")}))
        covered, snmp_bad, snmp_conf = set(), {}, set()      # snmp_bad: device id -> {port label: error and drop counters over SNMP}; snmp_conf: devices that have an SNMP connection at all
        for c in conns:
            if c.get("module") != "snmp":
                continue
            dev = match(c)
            self.matched[str(c["id"])] = dev
            if not dev:
                continue
            snmp_conf.add(dev)
            try:
                only = self.watch.only_for(dev) if self.watch is not None else None
                r = self.call("snmp", "counters", {"connection": c, **({"only": only} if only else {})}, 20)
            except Exception:
                continue
            if isinstance(r, dict) and r.get("sysName"):
                self.sys_of[str(c["id"])] = squash(r["sysName"])
            if isinstance(r, dict) and r.get("macs"):
                self.macs_of[str(c["id"])] = [str(m).lower() for m in r["macs"]]
            ports = {(v.get("label") or name): v for name, v in ((r or {}).get("ports") or {}).items() if isinstance(v, dict)}
            if ports:
                self.series.feed_counters(dev, ports, now)
                covered.add(dev)
                snmp_bad[dev] = {lab: {"rx_errors": v["rxErr"], "tx_errors": v["txErr"], "rx_dropped": v["rxDrop"], "tx_dropped": v["txDrop"]}
                                 for lab, v in ports.items() if all(isinstance(v.get(k), int) for k in ("rxErr", "txErr", "rxDrop", "txDrop"))}
        for d, i in zip(devices, ids):
            if i in covered or d.get("type") not in ("usw", "udm", "ugw", "uxg"):
                continue
            self.series.feed_rates(i, {p["name"]: {"in_bps": p.get("inBps"), "out_bps": p.get("outBps")} for p in d.get("ports") or []
                                      if isinstance(p, dict) and p.get("name") and p.get("inBps") is not None and p.get("outBps") is not None}, now)
        if self.watch is not None:
            if self.watch.enabled():
                self.rounds += 1
                servers, held = self._read_servers(conns, match)
                self._feed_watch(devices, ids, snmp_bad, snmp_conf, now, servers, held)
            elif self.watch.switched_off():
                self.watch.forget()
        if wifi:
            self.series.feed_rates(WIFI, {k: {"in_bps": v["rx"], "out_bps": v["tx"]} for k, v in wifi.items()}, now)
        self.series.forget_ports(WIFI, set(wifi))
        self.wifi = {k: {"name": v["name"], "ap": v["ap"]} for k, v in wifi.items()}
        self.series.forget_except(set(ids) | {WIFI})
        self.status.update(at=now, switches=sum(1 for d in devices if d.get("type") == "usw"), snmp=len(covered), unifi=len(unifis))
        if self.after:
            self.after()

    def _read_servers(self, conns, match):
        """The network cards of SNMP servers (SNMP connections that are not UniFi devices): errors and discards per interface, for the port watch only.
        -> ([(id, pseudo device)], ids that could not be read this round and are held). An id is "snmp:<connection id>"."""
        out, held = [], set()
        for c in conns:
            if c.get("module") != "snmp" or match(c):
                continue
            sid = "snmp:" + str(c["id"])
            if (self.rounds - 1) % SERVER_EVERY:
                held.add(sid)
                continue
            try:
                r = self.call("snmp", "counters", {"connection": c}, 20)
            except Exception:
                held.add(sid)
                continue
            if isinstance(r, dict) and r.get("sysName"):
                self.sys_raw[str(c["id"])] = str(r["sysName"])
            fresh = isinstance(r, dict) and bool(r.get("macs")) and self.macs_of.get(str(c["id"])) != [str(m).lower() for m in r["macs"]]
            if fresh:
                self.macs_of[str(c["id"])] = [str(m).lower() for m in r["macs"]]
            if (isinstance(r, dict) and r.get("sysName") and self.sys_of.get(str(c["id"])) != squash(r["sysName"])) or fresh:
                if isinstance(r, dict) and r.get("sysName"):
                    self.sys_of[str(c["id"])] = squash(r["sysName"])
                if match(c):                                         # its own name says it is a UniFi device: from the next round it is read as that device, not as a server
                    if self.watch is not None:
                        self.watch.drop_device(sid)
                    continue
            if self.watch is not None:
                self.watch.set_why(sid, self.explain(c))
            role = self._role(c, sid)
            if self.watch is not None:
                self.watch.set_switch_like(sid, bool(role.get("switch")) and self.has_unifi)       # a switch read on its own while UniFi has devices: worth saying why it was not matched
            up_s = r.get("uptimeS") if isinstance(r, dict) else None
            rebooted = isinstance(up_s, int) and isinstance(self.uptime.get(sid), int) and up_s + 5 < self.uptime[sid]
            if isinstance(up_s, int):
                self.uptime[sid] = up_s
            now = self.clock()
            ports, members, speeds, clients = [], {}, {}, set()
            for nm, v in ((r or {}).get("ports") or {}).items():
                if not isinstance(v, dict) or v.get("stacked") or stacked(nm) or not all(isinstance(v.get(k), int) for k in ("rxErr", "txErr", "rxDrop", "txDrop")):
                    continue                                          # a bond, team or VLAN only repeats the cards under it
                key = self.watch.key(sid, nm) if self.watch is not None else f"{sid}|{nm}"
                ports.append({"name": nm, "rx_errors": v["rxErr"], "tx_errors": v["txErr"], "rx_dropped": v["rxDrop"], "tx_dropped": v["txDrop"], "up": v.get("up"),
                              **({"link_down_count": self._link_drops(key, v, now, rebooted)} if isinstance(v.get("changedAgo"), int) else {})})
                if v.get("bond"):
                    members[key] = ", ".join(v["bond"])
                if isinstance(v.get("speedMbps"), (int, float)):
                    speeds[key] = v["speedMbps"]
                if role.get("switch") and nm not in role.get("links", ()):
                    clients.add(key)                                  # a switch port with no neighbour and at most one address behind it: a client's
            if self.watch is not None:
                self.watch.set_snmp_ports(sid, speeds, clients)
                self.watch.set_cards(sid, [self.watch.key(sid, p["name"]) for p in ports if p.get("up") is not False], members)
            if ports:
                out.append((sid, {"name": str(c.get("name") or c["id"]), "ports": ports}))
            else:
                held.add(sid)
        return out, held

    def _role(self, c, sid):
        """Whether this SNMP device is a switch (it learns addresses or hears LLDP neighbours) and which of its ports are links (a neighbour, or several addresses behind it).
        Read with the module's switch report, without its two-second traffic reading, once at first and then every ROLES_EVERY seconds; if it cannot be read the last answer stands."""
        now, cur = self.clock(), self.roles.get(sid)
        if cur and now - cur["at"] < ROLES_EVERY:
            return cur
        try:
            r = self.call("snmp", "lan_report", {"connection": c, "wait": 0}, 40)
        except Exception:
            return cur or {}
        ports = [p for p in (r or {}).get("ports") or [] if isinstance(p, dict) and p.get("name")]
        cur = self.roles[sid] = {"at": now, "switch": any(p.get("learned") or p.get("lldp") for p in ports),
                                 "links": {p["name"] for p in ports if p.get("lldp") or (p.get("learned") or 0) >= 2}}
        return cur

    def _link_drops(self, key, v, now, rebooted):
        """How many times this card's link went down since the box started counting. The device only says when the link last changed, so a change since the last read is a drop if
        the link is down now, or if it is up now and was up before (down and up again between two reads); coming back up after being down is the end of a drop, not a new one."""
        st = self.links.get(key)
        if st is None:
            st = self.links[key] = {"n": self.watch.last_flaps(key) if self.watch is not None else 0, "abs": None, "up": v.get("up")}
        absn = now - v["changedAgo"]
        if rebooted or st["abs"] is None:
            st["abs"] = absn                                          # a restart resets every link's time: not a flap
        elif absn - st["abs"] > 3:
            if v.get("up") is False or (v.get("up") is True and st["up"] is True):
                st["n"] += 1
            st["abs"] = absn
        st["up"] = v.get("up")
        return st["n"]

    def _feed_watch(self, devices, ids, snmp_bad, snmp_conf, now, servers=(), held_servers=()):
        """The port watch's counters. UniFi's port table has them for every UniFi device; a switch that is also an SNMP connection gives them over SNMP
        instead (straight from the interface). The two count differently, so one device never mixes them: an SNMP device whose answer did not come this
        round is left out of this round altogether, not read from UniFi. Link drops (UniFi's link_down_count) stay from UniFi."""
        use, keep, held = [], [], set()
        for d, i in zip(devices, ids):
            if i in snmp_bad:
                bad = snmp_bad[i]
                d = {**d, "ports": [{**p, **bad[p["name"]]} if isinstance(p, dict) and p.get("name") in bad else p for p in d.get("ports") or []]}
            elif i in snmp_conf:
                held.add(i)
                continue
            use.append(d)
            keep.append(i)
        for sid, d in servers:
            use.append(d)
            keep.append(sid)
        self.watch.feed(use, keep, now, hold=held | set(held_servers))

    def run(self):
        while not self.stopping.is_set():
            t0 = self.clock()
            try:
                self.tick()
            except Exception:
                pass
            self.stopping.wait(max(1.0, EVERY - (self.clock() - t0)))

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="lansampler")
        self.thread.start()

    def stop(self):
        self.stopping.set()
