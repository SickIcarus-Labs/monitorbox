"""Reads every switch port's traffic every few seconds into the port history (portpeers.PortSeries), read-only.

UniFi gives every device's ports and rates in one request. A switch that is also an SNMP connection (matched by its address) is read
over SNMP instead, which gives exact counters for every port. Ports are keyed by (device id, the port's name as UniFi spells it), so
a switch's history lines up with its place on the map. A source that does not answer is skipped; nothing is invented."""
import threading, time

from . import lanmap, followups

EVERY = 10.0
WIFI = "wifi"           # the history's stand-in for a switch: every Wi-Fi client is a "port" under it


class LanSampler:
    def __init__(self, series, load_conns, call, clock=time.time, after=None):
        """call(module, method, params, timeout) -> result, like the module runner."""
        self.series, self.load_conns, self.call, self.clock, self.after = series, load_conns, call, clock, after
        self.stopping = threading.Event()
        self.thread = None
        self.status = {"at": 0.0, "switches": 0, "snmp": 0, "unifi": 0}
        self.wifi = {}          # port name in the history (under WIFI) -> {"name", "ap"}: the Wi-Fi clients read this round

    def tick(self):
        conns = [c for c in self.load_conns() if isinstance(c, dict) and c.get("id")]
        unifis = [c for c in conns if c.get("module") == "unifi-network"]
        if not unifis:
            self.status.update(at=self.clock(), switches=0, snmp=0, unifi=0)
            return
        devices, wifi = [], {}
        for u in unifis:
            try:
                r = self.call("unifi-network", "lan_report", {"connection": u, "clients": True}, 30)
            except Exception:
                continue
            devices += [d for d in (r or {}).get("devices") or [] if isinstance(d, dict)]
            for c in (r or {}).get("clients") or []:
                # a Wi-Fi client has no switch port of its own; the controller's per-client rate (through the access point, so local traffic too) stands in for one.
                # rx/tx are kept as the controller names them: which way they point is settled against the port being asked about (server.lan_peers), not assumed here.
                if not isinstance(c, dict) or c.get("wired") or not isinstance(c.get("rxBps"), (int, float)) or not isinstance(c.get("txBps"), (int, float)):
                    continue
                name = str(c.get("name") or c.get("ip") or "").strip()
                if name:
                    wifi[f"{name}|{c.get('mac') or ''}"] = {"name": name, "ap": c.get("ap"), "rx": c["rxBps"], "tx": c["txBps"]}
        ids = lanmap.device_ids(devices)
        now = self.clock()
        by_ip = {str(d.get("ip") or "").strip().lower(): i for d, i in zip(devices, ids) if d.get("ip")}
        covered = set()
        for c in conns:
            if c.get("module") != "snmp":
                continue
            dev = by_ip.get(followups.host_of(c))
            if not dev:
                continue
            try:
                r = self.call("snmp", "counters", {"connection": c}, 20)
            except Exception:
                continue
            ports = {(v.get("label") or name): v for name, v in ((r or {}).get("ports") or {}).items() if isinstance(v, dict)}
            if ports:
                self.series.feed_counters(dev, ports, now)
                covered.add(dev)
        for d, i in zip(devices, ids):
            if i in covered or d.get("type") not in ("usw", "udm", "ugw", "uxg"):
                continue
            self.series.feed_rates(i, {p["name"]: {"in_bps": p.get("inBps"), "out_bps": p.get("outBps")} for p in d.get("ports") or []
                                      if isinstance(p, dict) and p.get("name") and p.get("inBps") is not None and p.get("outBps") is not None}, now)
        if wifi:
            self.series.feed_rates(WIFI, {k: {"in_bps": v["rx"], "out_bps": v["tx"]} for k, v in wifi.items()}, now)
        self.series.forget_ports(WIFI, set(wifi))
        self.wifi = {k: {"name": v["name"], "ap": v["ap"]} for k, v in wifi.items()}
        self.series.forget_except(set(ids) | {WIFI})
        self.status.update(at=now, switches=sum(1 for d in devices if d.get("type") == "usw"), snmp=len(covered), unifi=len(unifis))
        if self.after:
            self.after()

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
