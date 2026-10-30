"""UniFi checks, from the controller's device list and health summary. Pure functions over those two lists,
so they are easy to test. A controller that cannot be reached is Unknown (main.py), never Failed."""
import time

STATE_WORDS = {0: "disconnected", 1: "connected", 2: "pending adoption", 3: "firmware mismatch", 4: "upgrading",
               5: "provisioning", 6: "heartbeat missed", 7: "adopting", 8: "deleting", 9: "inform error",
               10: "adoption failed", 11: "isolated"}
FAILED_STATES = {0, 9, 10}                      # the controller cannot talk to it
HEALTH_NAMES = {"wan": "WAN", "lan": "LAN", "wlan": "Wi-Fi", "www": "Internet", "vpn": "VPN"}


def norm_mac(m):
    return "".join(ch for ch in str(m or "").lower() if ch.isalnum())


def dev_name(d):
    return d.get("name") or d.get("hostname") or d.get("model") or d.get("mac") or "unnamed device"


def duration(sec):
    sec = int(sec or 0)
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if sec >= size:
            return f"{sec // size} {unit}"
    return f"{sec} s"


def speed(mbps):
    return f"{mbps / 1000:g} Gbps" if mbps >= 1000 else f"{mbps:g} Mbps"


def find_device(devices, name=None, mac=None):
    if mac:
        return next((d for d in devices if norm_mac(d.get("mac")) == norm_mac(mac)), None)
    return next((d for d in devices if dev_name(d).lower() == str(name or "").lower()), None)


def uplink_of(d, devices):
    """(parent name, speed in Mbps, up) for a wired uplink, else None. This is the LAN topology."""
    u = d.get("uplink") or {}
    if u.get("type") != "wire" or not u.get("uplink_mac"):
        return None
    parent = next((p for p in devices if norm_mac(p.get("mac")) == norm_mac(u["uplink_mac"])), None)
    # a gateway's uplink is usually a modem or ISP box the controller does not manage: no name, not a MAC address
    return (dev_name(parent) if parent else None, u.get("speed"), u.get("up", True))


def check_device(params, devices):
    if not params.get("name") and not params.get("mac"):
        return {"state": "unknown", "detail": "this check needs a device 'name' (or 'mac'). Open the server and choose Pick what to watch."}
    d = find_device(devices, params.get("name"), params.get("mac"))
    if not d:
        names = ", ".join(sorted(dev_name(x) for x in devices)) or "none"
        return {"state": "unknown", "detail": f"the controller has no device called '{params.get('name') or params.get('mac')}' (it has: {names})"}
    code = d.get("state")
    bits = [STATE_WORDS.get(code, f"state {code}")]
    if code == 1 and d.get("uptime"):
        bits.append(f"up {duration(d['uptime'])}")
    problem = code != 1
    up = uplink_of(d, devices)
    if up and code == 1:
        parent, mbps, link_up = up
        where = parent or "a device outside UniFi"
        if not link_up:
            bits.append(f"uplink to {where} is down")
            problem = True
        elif mbps:
            bits.append(f"via {where} at {speed(mbps)}")
            floor = params.get("min_uplink_mbps")
            if floor and mbps < floor:
                bits.append(f"expected at least {speed(floor)}")
                problem = True
    if d.get("upgradable"):
        bits.append("update available")                  # information, not a problem
    state = "failed" if code in FAILED_STATES else ("degraded" if problem else "healthy")
    return {"state": state, "detail": " · ".join(bits)}


HOT_C = 80          # degrees C; editable per check (max_c)


def readings(d):
    """Every temperature the controller reports for a device, as (label, degrees C). Empty when it reports none."""
    out = []
    t = d.get("general_temperature")
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        out.append(("board", t))
    for x in d.get("temperatures") or []:
        v = x.get("value") if isinstance(x, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append((str(x.get("name") or "sensor"), v))
    return out


def check_temperature(params, devices):
    if not params.get("name") and not params.get("mac"):
        return {"state": "unknown", "detail": "this check needs a device 'name' (or 'mac'). Open the server and choose Pick what to watch."}
    d = find_device(devices, params.get("name"), params.get("mac"))
    if not d:
        return {"state": "unknown", "detail": f"the controller has no device called '{params.get('name') or params.get('mac')}'"}
    if d.get("state") != 1:
        return {"state": "unknown", "detail": "device is not connected, so its temperature is not known"}
    limit = params.get("max_c") or HOT_C
    rs = readings(d)
    if not rs and not d.get("overheating"):
        return {"state": "unknown", "detail": "the controller reports no temperature for this device"}
    bits = []
    hot = bool(d.get("overheating"))
    if rs:
        label, top = max(rs, key=lambda r: r[1])
        bits.append(f"{top:g} °C" + (f" ({label})" if len(rs) > 1 else ""))
        hot = hot or top >= limit
    if isinstance(d.get("fan_level"), (int, float)) and not isinstance(d.get("fan_level"), bool):
        bits.append(f"fan {d['fan_level']:g}%")
    if d.get("overheating"):
        bits.append("device says it is overheating")
    elif hot:
        bits.append(f"hot, limit {limit:g} °C")
    return {"state": "degraded" if hot else "healthy", "detail": " · ".join(bits)}


def check_devices(params, devices):
    names = {str(n).lower() for n in params.get("names") or []}
    mine = [d for d in devices if d.get("adopted", True) and (not names or dev_name(d).lower() in names)]
    if not mine:
        return {"state": "unknown", "detail": "the controller reports no adopted devices"}
    ok = [d for d in mine if d.get("state") == 1]
    down = [d for d in mine if d.get("state") in FAILED_STATES]
    other = [d for d in mine if d not in ok and d not in down]
    detail = f"{len(ok)} of {len(mine)} devices connected"
    if down:
        detail += " · disconnected: " + ", ".join(sorted(dev_name(d) for d in down))
    if other:
        detail += " · not settled: " + ", ".join(f"{dev_name(d)} ({STATE_WORDS.get(d.get('state'), d.get('state'))})" for d in sorted(other, key=dev_name))
    return {"state": "failed" if down else ("degraded" if other else "healthy"), "detail": detail}


def check_health(params, health, devices=None):
    sub = str(params.get("subsystem") or "").lower()
    if not sub:
        return {"state": "unknown", "detail": "this check needs a 'subsystem' (wan, lan, wlan, www or vpn). Open the server and choose Pick what to watch."}
    h = next((x for x in health if x.get("subsystem") == sub), None)
    if not h:
        return {"state": "unknown", "detail": f"the controller has no '{sub}' health (it has: {', '.join(x.get('subsystem', '?') for x in health) or 'none'})"}
    status = h.get("status")
    bits = [f"{HEALTH_NAMES.get(sub, sub)} {status}"]
    if h.get("wan_ip"):
        bits.append(h["wan_ip"])
    if h.get("latency") is not None and sub == "www":
        bits.append(f"{h['latency']} ms")
    if h.get("num_adopted"):
        bits.append(f"{h['num_adopted'] - (h.get('num_disconnected') or 0)} of {h['num_adopted']} devices connected")
    if sub == "www":
        # the controller's own Internet verdict can say 'warning' while the line is fine (UniFi shows it healthy); show what the verdict
        # is based on (drops, uptime, speed test state) so a disagreement can be explained instead of guessed at
        for k in ("drops", "uptime", "speedtest_status", "speedtest_ping", "uptime_stats"):
            v = h.get(k)
            if isinstance(v, (int, float, str)) and not isinstance(v, bool) and str(v) != "":
                bits.append(f"{k.replace('_', ' ')} {v}")
        extra = sorted(k for k in h if k not in ("subsystem", "status", "latency", "drops", "uptime", "speedtest_status", "speedtest_ping", "uptime_stats")
                       and isinstance(h[k], (int, float, str)) and not isinstance(h[k], bool) and str(h[k]) != ""
                       and not any(w in k for w in ("bytes", "bps", "rx", "tx", "mac", "ip", "xput", "name", "lastrun")))
        bits += [f"{k.replace('_', ' ')} {h[k]}" for k in extra]
    if sub == "vpn":
        # the controller's VPN summary is coarse (it can say 'error' while every tunnel is up), so show what it
        # is based on instead of leaving a bare 'error'
        skip = ("bytes", "bps", "rx", "tx", "ip")
        for k, v in sorted(h.items()):
            if k not in ("subsystem", "status") and isinstance(v, (int, str)) and not any(w in k for w in skip):
                bits.append(f"{k.replace('_', ' ')} {v}")
    state = {"ok": "healthy", "warning": "degraded", "error": "failed"}.get(status, "unknown")
    if sub == "www" and status == "warning" and not h.get("latency") and not h.get("uptime"):
        # UniFi's old Internet summary says 'warning' but has no latency and no uptime behind it. On Tidewater it stayed that way for
        # an hour after the cause (a failing SLA ping target) was removed and UniFi's own screens showed Passing, while MonitorBox's
        # own Internet checks were fine. A verdict with nothing behind it is not an observation of a problem. A real outage still
        # shows: UniFi says 'error', and the WAN, ping and DNS checks fail. The detail keeps UniFi's words so a bad SLA target stays visible.
        state = "unknown"
        bits.append("UniFi's Internet summary has no measurements right now")
        # the gateway's own WAN data is what UniFi's current Internet screens are drawn from: use it instead
        seen = gateway_wans(devices)
        if seen:
            up = [w for w in seen if w["up"]]
            lat = next((w["latency"] for w in up if w["latency"] is not None), None)
            state = "healthy" if up else "failed"
            bits.append(("gateway says " + " and ".join(w["label"] for w in up) + " up" + (f" · {lat} ms" if lat is not None else ""))
                        if up else "gateway says every WAN is down")
        else:
            bits.append("so this is not counted")
    return {"state": state, "detail": " · ".join(bits)}


def gateway_wans(devices):
    """[{label, up, latency}] for the WAN blocks the gateway reports itself (wan1/wan2), the data UniFi's current Internet screens use."""
    out = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        stats = d.get("uptime_stats") if isinstance(d.get("uptime_stats"), dict) else {}
        for key, label, st in (("wan1", "WAN", "WAN"), ("wan2", "WAN 2", "WAN2"), ("wan3", "WAN 3", "WAN3")):
            w = d.get(key)
            if isinstance(w, dict) and isinstance(w.get("up"), bool):
                lat = (stats.get(st) or {}).get("latency_average") if isinstance(stats.get(st), dict) else None
                out.append({"label": label, "up": w["up"], "latency": lat if isinstance(lat, (int, float)) and lat > 0 else None})
    return out


TUNNEL_PURPOSES = {"vpn-client": "VPN client", "site-vpn": "site-to-site"}
TUNNEL_TYPES = {"wireguard-client": "WireGuard", "openvpn-client": "OpenVPN", "ipsec-vpn": "IPsec", "wireguard-site": "WireGuard"}


def tunnels_of(networks):
    """The VPN tunnels configured on the controller (clients and site-to-site)."""
    return [n for n in networks if isinstance(n, dict) and n.get("purpose") in TUNNEL_PURPOSES]


def tunnel_kind(n):
    return TUNNEL_TYPES.get(n.get("vpn_type")) or TUNNEL_PURPOSES.get(n.get("purpose"), "VPN")


def tunnel_status(n, connections):
    """'connected', 'paused' (turned off in UniFi), the controller's own word, or None when it reports none."""
    if n.get("enabled") is False:
        return "paused"
    if connections is None:
        return None
    for c in connections:
        if isinstance(c, dict) and n.get("_id") and n["_id"] in (c.get("network_id"), c.get("id"), c.get("_id")):
            return str(c.get("status") or "").lower() or None
    return None


def check_tunnel(params, networks, connections):
    name = params.get("name")
    mine = tunnels_of(networks)
    if not name:
        return {"state": "unknown", "detail": "this check needs a tunnel 'name'. Open the server and choose Pick what to watch."}
    n = next((t for t in mine if str(t.get("name", "")).lower() == str(name).lower()), None)
    if not n:
        names = ", ".join(sorted(str(t.get("name")) for t in mine)) or "none"
        return {"state": "unknown", "detail": f"the controller has no VPN tunnel called '{name}' (it has: {names})"}
    st = tunnel_status(n, connections)
    bits = [tunnel_kind(n)]
    if n.get("ip_subnet"):
        bits.append(f"tunnel {n['ip_subnet']}")
    if st == "paused":                      # switched off on purpose in UniFi: worth a heads-up, not a red Down
        return {"state": "degraded", "detail": " · ".join(bits + ["paused (turned off in UniFi)"])}
    if st == "connected":
        return {"state": "healthy", "detail": " · ".join(bits + ["connected"])}
    if st in ("disconnected", "down", "error", "failed"):
        return {"state": "failed", "detail": " · ".join(bits + [st])}
    why = f"status '{st}'" if st else "UniFi did not report this tunnel's status"
    return {"state": "unknown", "detail": " · ".join(bits + [why])}


def discover(devices, health, networks=(), connections=None):
    """Ready-made checks plus the LAN topology (which device hangs off which, at what speed)."""
    sug = [{"label": "UniFi devices", "check": "devices", "params": {}, "batch": "Overview"}]
    for h in health:
        s = h.get("subsystem")
        if s in HEALTH_NAMES and s != "vpn" and h.get("status") != "unknown":     # vpn: see per-tunnel checks
            sug.append({"label": f"UniFi {HEALTH_NAMES[s]}", "check": "health", "params": {"subsystem": s}, "batch": "Overview"})
    topo = []
    for d in sorted((x for x in devices if x.get("adopted", True)), key=dev_name):
        sug.append({"label": f"UniFi {dev_name(d)}", "check": "device", "params": {"name": dev_name(d)}, "batch": "Devices"})
        if readings(d) or d.get("overheating"):
            sug.append({"label": f"UniFi {dev_name(d)} temperature", "check": "temperature", "params": {"name": dev_name(d)}, "batch": "Temperatures"})
        up = uplink_of(d, devices)
        topo.append({"name": dev_name(d), "model": d.get("model"), "type": d.get("type"), "ip": d.get("ip"), "state": STATE_WORDS.get(d.get("state"), d.get("state")),
                     "uplink": up[0] if up else None, "uplink_mbps": up[1] if up else None})
    tunnels = []
    for n in sorted(tunnels_of(networks), key=lambda t: str(t.get("name", "")).lower()):
        name = str(n.get("name") or n.get("_id"))
        sug.append({"label": f"UniFi VPN {name}", "check": "tunnel", "params": {"name": name}, "batch": "VPN tunnels"})
        tunnels.append({"name": name, "type": tunnel_kind(n), "subnet": n.get("ip_subnet"), "status": tunnel_status(n, connections)})
    for s in sug:        # the overview shares one item (the devices summary first); every device and tunnel is its own, so one that is off shows as Down by name
        s.update({"node": "UniFi" if s["batch"] == "Overview" else s["label"], "group": "Network", "rule": "primary"})
    return {"devices": topo, "tunnels": tunnels, "suggest": sug}


def wan_ports(devices):
    """The gateway's WAN interfaces as UniFi names them: [{"ifname": "eth9", "label": "WAN", "up": True, "ip": "...", "speedMbps": 5000, "gateway": "name"}].
    UniFi reports them twice (wan1/wan2 blocks and the port table); either is enough, and they are merged by interface name.
    speedMbps is what the link negotiated, which can be less than the port's rating."""
    found = {}
    nice = {"wan1": "WAN", "wan2": "WAN 2", "wan3": "WAN 3"}

    def add(d, ifname, label, up, ip, speed, force=False):
        row = {"ifname": ifname, "label": label if label.lower() != ifname.lower() else "WAN", "up": bool(up), "ip": ip or "",
               "speedMbps": int(speed) if isinstance(speed, (int, float)) and speed > 0 else None, "gateway": dev_name(d)}
        key = (dev_name(d), ifname)
        if force or key not in found:
            found[key] = row
        elif row["speedMbps"] and not found[key]["speedMbps"]:
            found[key]["speedMbps"] = row["speedMbps"]

    for d in devices or []:
        if not isinstance(d, dict):
            continue
        for key in ("wan1", "wan2", "wan3"):
            w = d.get(key)
            if isinstance(w, dict) and w.get("ifname"):
                add(d, w["ifname"], nice[key], w.get("up"), w.get("ip"), w.get("speed"), True)
        for p in d.get("port_table") or []:
            if isinstance(p, dict) and p.get("ifname") and (str(p.get("network_name") or "").lower().startswith("wan") or str(p.get("name") or "").upper().startswith("WAN")):
                add(d, p["ifname"], str(p.get("name") or p.get("network_name") or "WAN"), p.get("up"), p.get("ip"), p.get("speed"))
    return sorted(found.values(), key=lambda x: x["ifname"])


# ---------------------------------------------------------------- LAN report (read-only look at what the controller says about each device and port) ----
PORT_FIELDS = ("port_idx", "name", "up", "enable", "speed", "full_duplex", "is_uplink", "media", "op_mode", "aggregated_by", "network_name",
               "poe_enable", "poe_good", "poe_power", "rx_errors", "tx_errors", "rx_dropped", "tx_dropped", "stp_state", "stp_role",
               "mac_table_count", "link_down_count")


def mask_mac(m):
    """aa:bb:cc:dd:ee:ff -> ..:dd:ee:ff. Enough to tell devices apart in a report that gets pasted around, not enough to identify one."""
    n = norm_mac(m)
    return "..:" + ":".join(n[i:i + 2] for i in (6, 8, 10)) if len(n) == 12 else ("" if not m else "?")


def _client_row(c, devices):
    """One client: its name, where it plugs in (switch and port, or access point) and its rates. Rates keep the controller's own direction names (rx/tx),
    because which way they point is checked against the switch port's own counters, not assumed."""
    wired = bool(c.get("is_wired"))
    sw = find_device(devices, mac=c.get("sw_mac")) if c.get("sw_mac") else None
    ap = find_device(devices, mac=c.get("ap_mac")) if c.get("ap_mac") else None
    pre = "wired-" if wired and isinstance(c.get("wired-rx_bytes-r"), (int, float)) else ""
    row = {"name": c.get("name") or c.get("hostname") or "", "ip": c.get("ip"), "mac": mask_mac(c.get("mac")), "wired": wired}
    if c.get("oui"):
        row["oui"] = str(c["oui"])[:60]                     # the maker the controller looks up from the MAC address
    if c.get("network"):
        row["network"] = str(c["network"])[:40]             # the name of the network (VLAN) the client is on, e.g. "IoT": how the app tells smart-home devices apart
    if wired:
        row.update({"switch": dev_name(sw) if sw else None, "port": c.get("sw_port")})
    else:
        row.update({"ap": dev_name(ap) if ap else None, "essid": c.get("essid")})
    for src, dst in ((pre + "rx_bytes-r", "rxBps"), (pre + "tx_bytes-r", "txBps")):
        if isinstance(c.get(src), (int, float)):
            row[dst] = int(c[src] * 8)
    return row


def lan_report(devices, clients=None, clients_note=None):
    """What each adopted device reports: its links (uplink, LLDP neighbours) and each port's state, speed, rate and what it has learned behind it.
    Only a fixed list of fields is copied, so nothing secret can ride along, and MAC addresses are shortened. The names of the other fields the
    controller sends (never their values) are listed too, so we can see what else there is to build on."""
    out = []
    for d in sorted((x for x in devices or [] if isinstance(x, dict) and x.get("adopted", True)), key=dev_name):
        up = d.get("uplink") if isinstance(d.get("uplink"), dict) else {}
        parent = find_device(devices, mac=up.get("uplink_mac")) if up.get("uplink_mac") else None
        ports, down = [], 0
        for p in d.get("port_table") or []:
            if not isinstance(p, dict):
                continue
            if p.get("up") is False and not p.get("is_uplink"):
                down += 1                                             # a port with nothing on it is counted, not listed
                continue
            row = {k: p[k] for k in PORT_FIELDS if k in p}
            lc = p.get("last_connection")
            if isinstance(lc, dict) and lc.get("mac"):
                row["lastMac"] = mask_mac(lc["mac"])
            for src, dst in (("rx_bytes-r", "inBps"), ("tx_bytes-r", "outBps")):
                if isinstance(p.get(src), (int, float)):
                    row[dst] = int(p[src] * 8)                       # the controller counts bytes a second
            mt = p.get("mac_table")
            if isinstance(mt, list):
                row["learned"] = len(mt)
                names = sorted({str(m.get("hostname")) for m in mt if isinstance(m, dict) and m.get("hostname")})
                if names:
                    row["learnedNames"] = names[:8]
            ports.append(row)
        out.append({"name": dev_name(d), "mac": mask_mac(d.get("mac")), "model": d.get("model"), "type": d.get("type"), "ip": d.get("ip"), "state": STATE_WORDS.get(d.get("state"), d.get("state")),
                    "uplink": {"type": up.get("type"), "to": dev_name(parent) if parent else None, "toMac": mask_mac(up.get("uplink_mac")), "speedMbps": up.get("speed"),
                               "up": up.get("up"), "remotePort": up.get("uplink_remote_port"), "port": up.get("port_idx")},
                    "lldp": [{"port": e.get("local_port_idx"), "chassis": mask_mac(e.get("chassis_id")) if len(norm_mac(e.get("chassis_id"))) == 12 else str(e.get("chassis_id") or "")[:40],
                              "remotePort": str(e.get("port_id") or "")[:40]} for e in d.get("lldp_table") or [] if isinstance(e, dict)],
                    "ports": ports, "downPorts": down,
                    "deviceKeys": sorted(str(k) for k in d.keys()),
                    "portKeys": sorted({str(k) for p in d.get("port_table") or [] if isinstance(p, dict) for k in p.keys()})})
    rep = {"devices": out}
    if clients is not None:
        rep["clients"] = [_client_row(c, devices) for c in sorted((x for x in clients if isinstance(x, dict)), key=lambda x: str(x.get("name") or x.get("hostname") or ""))]
        rep["clientKeys"] = sorted({str(k) for c in clients if isinstance(c, dict) for k in c.keys()})
    if clients_note:
        rep["clientsNote"] = clients_note
    return rep


def client_usage(doc, seconds, top=30):
    """Per-client internet usage from the controller's traffic answer: bytes the client received (down) and sent (up) over `seconds`, all applications added up, biggest
    first. The gateway counts internet traffic and traffic between networks, not what stays on one switch. Clients with no bytes are left out; addresses are shortened."""
    rows = []
    for c in (doc or {}).get("client_usage_by_app") or []:
        cl = (c or {}).get("client") or {}
        apps = [a for a in (c or {}).get("usage_by_app") or [] if isinstance(a, dict)]
        down, up = (sum(int(a.get(k) or 0) for a in apps) for k in ("bytes_received", "bytes_transmitted"))
        if down + up <= 0:
            continue
        rows.append({"id": mask_mac(cl.get("mac")), "name": cl.get("name") or cl.get("hostname") or cl.get("oui") or "unnamed device",
                     "wired": bool(cl.get("is_wired")), "down": down, "up": up})
    rows.sort(key=lambda r: -(r["down"] + r["up"]))
    return {"seconds": int(seconds), "count": len(rows), "clients": rows[:top],
            "total": {"down": sum(r["down"] for r in rows), "up": sum(r["up"] for r in rows)}}


def flow_summary(rows, seconds, now_ms=None, top=300):
    """The gateway's flow records boiled down: one row per (source address, destination, direction) over the last `seconds`, biggest first. A flow that began before
    the window counts only for the part inside it (bytes spread evenly over its life). `down` is what the source device received (the record's bytes_tx: the gateway names the two from the other end's side), `up` what it sent (bytes_rx); destinations
    are named by domain when the gateway knows one, else by address. MACs are shortened like everywhere else."""
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    start = now - int(seconds) * 1000
    agg = {}
    for f in rows or []:
        if not isinstance(f, dict):
            continue
        t = f.get("traffic_data") or {}
        end = f.get("flow_end_time") or f.get("time") or 0
        began = f.get("flow_start_time") or end
        if not end or end < start:
            continue
        share = min(1.0, (end - max(began, start)) / (end - began)) if end > began else 1.0
        down, up = int((t.get("bytes_tx") or 0) * share), int((t.get("bytes_rx") or 0) * share)       # the record names the two from the destination's side: its tx is what the source received
        if down + up <= 0:
            continue
        src, dst = f.get("source") or {}, f.get("destination") or {}
        doms = [d for d in (dst.get("domains") or []) if isinstance(d, str)]
        dst_name = doms[0] if doms else (dst.get("client_name") or dst.get("host_name") or dst.get("ip") or "")
        direction = str(f.get("direction") or "")
        key = (src.get("ip") or "", dst.get("ip") or "", dst_name, direction)
        r = agg.get(key)
        if r is None:
            r = agg[key] = {"src_ip": src.get("ip") or "", "src_mac": mask_mac(src.get("mac")),
                            "src_name": src.get("client_name") or src.get("host_name") or src.get("ip") or "unnamed device",
                            "dst_ip": dst.get("ip") or "", "dst_mac": mask_mac(dst.get("mac")), "dst_name": dst_name, "dst_zone": dst.get("zone_name") or "",
                            "direction": direction, "service": f.get("service") or "", "down": 0, "up": 0}
        r["down"] += down
        r["up"] += up
    out = sorted(agg.values(), key=lambda r: -(r["down"] + r["up"]))[:top]
    return {"seconds": int(seconds), "count": len(agg), "flows": out}
