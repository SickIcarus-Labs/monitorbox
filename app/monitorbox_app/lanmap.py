"""The LAN map: who hangs off which switch, built from the switch report (what each UniFi device and SNMP host says about itself).

Only reads what the report already has. Every rate is from the point of view of the thing further from the gateway: `down` is
traffic going to it, `up` is traffic coming from it. A link's rates are its uplink port's own counters; an endpoint's are its
switch port's. Switch ports that are bonded (link aggregation) are one endpoint, with their traffic added together. The client
list's own rates are not used (they run far below the port counters)."""

GATEWAYS = ("udm", "ugw", "uxg")


def is_iot(c):
    """A client on a network (or Wi-Fi name) with "iot" in its name. Only the name the owner gave the network is used: nothing is guessed from the device."""
    return any("iot" in str(c.get(k) or "").lower() for k in ("network", "essid"))


def _kind(d):
    t = d.get("type")
    return "gateway" if t in GATEWAYS else "ap" if t == "uap" else "switch" if t == "usw" else "device"


def _state(word):
    """The controller's own word for a device -> one of our five states (display only: the monitored states come from the checks)."""
    if word == "connected":
        return "healthy"
    if word == "disconnected":
        return "failed"
    return "unknown" if not word else "degraded"


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def device_ids(devices):
    """One id per device, in order: its own (shortened) address when the controller gave one, else its name. The map and the port history
    both use it, so a switch's readings line up with its place on the map."""
    ids, used = [], set()
    for d in devices:
        base = d.get("mac") if d.get("mac") not in (None, "", "?") else d["name"]
        i, k = base, 2
        while i in used:
            i, k = f"{base}#{k}", k + 1
        used.add(i)
        ids.append(i)
    return ids


def build(sources):
    """sources: the list the switch report returns ([{"connection","module","report"|"error"}]). Returns {"nodes", "counts", "notes"}."""
    notes, devices, clients, hosts, switches = [], [], [], {}, set()
    for s in sources or []:
        r = s.get("report")
        if not isinstance(r, dict):
            continue
        if s.get("module") == "unifi-network":
            devices += [d for d in r.get("devices") or [] if isinstance(d, dict)]
            clients += [c for c in r.get("clients") or [] if isinstance(c, dict)]
            if r.get("clientsNote"):
                notes.append("This UniFi login cannot read the client list, so devices on ports are not named.")
        elif s.get("module") == "snmp":
            name = r.get("sysName") or s.get("connection") or "server"
            for p in r.get("ports") or []:
                if p.get("mac"):
                    hosts.setdefault(p["mac"], name)          # a server's own card address -> its name
            if any(p.get("learned") or p.get("lldp") for p in r.get("ports") or []):
                switches.add(name.lower())                    # it learns addresses or hears neighbours on its ports: a switch, not a server
    if not devices:
        return {"iotIps": sorted({c["ip"] for c in clients if c.get("ip") and is_iot(c)}), "makers": {}, "nodes": [], "counts": {"devices": 0, "wired": 0, "wifi": 0}, "notes": notes + ["No UniFi devices to map yet. The map is built from a UniFi connection."]}
    # Two devices can share a name (a switch and an access point both called "Living Room"), so everything is tied together by id:
    # the device's own (shortened) address when the controller gave one, else its name.
    ids = device_ids(devices)
    by_mac = {d["mac"]: i for d, i in zip(devices, ids) if d.get("mac") not in (None, "", "?")}
    by_name = {}
    for d, i in zip(devices, ids):
        by_name.setdefault(d["name"], []).append(i)
    name_of = dict(zip(ids, (d["name"] for d in devices)))
    pname = {i: {p.get("port_idx"): p.get("name") for p in d.get("ports") or [] if isinstance(p, dict) and p.get("name")} for d, i in zip(devices, ids)}

    def parent_id(d, me):
        up = d.get("uplink") or {}
        if up.get("type") != "wire":
            return None
        pid = by_mac.get(up.get("toMac")) or (by_name[up["to"]][0] if up.get("to") in by_name and len(by_name[up["to"]]) == 1 else None)
        return pid if pid and pid != me else None
    parents = {i: parent_id(d, i) for d, i in zip(devices, ids)}
    children = {}
    for d, i in zip(devices, ids):
        if parents[i]:
            children.setdefault(parents[i], []).append(d)
    wired = [c for c in clients if c.get("wired")]
    nodes = []
    for d, me in zip(devices, ids):
        name, up = d["name"], d.get("uplink") or {}
        ports = {p.get("port_idx"): p for p in d.get("ports") or [] if isinstance(p, dict)}
        node = {"id": me, "name": name, "kind": _kind(d), "model": d.get("model"), "ip": d.get("ip"), "state": _state(d.get("state")),
                "stateWord": d.get("state"), "parent": parents[me], "link": None, "ports": []}
        if node["parent"]:
            local = ports.get(up.get("port")) or {}
            node["link"] = {"to": name_of[node["parent"]], "speedMbps": up.get("speedMbps"), "up": up.get("up") is not False, "port": up.get("port"), "parentPort": up.get("remotePort"),
                            "down": local.get("inBps"), "up_bps": local.get("outBps"),            # None when that switch gave no port counters: unknown, not zero
                            "errors": _num(local.get("rx_errors")) + _num(local.get("tx_errors")), "drops": _num(local.get("rx_dropped")) + _num(local.get("tx_dropped")),
                            # where this link's traffic is counted (device id, the port's name): at the child's own uplink port and at the parent's port
                            "keys": {"self": [me, pname[me].get(up.get("port"))] if pname[me].get(up.get("port")) else None,
                                     "parent": [node["parent"], pname[node["parent"]].get(up.get("remotePort"))] if pname[node["parent"]].get(up.get("remotePort")) else None}}
        if node["kind"] == "ap":
            node["wifi"] = sum(1 for c in clients if not c.get("wired") and c.get("ap") == name)      # clients name their access point; same-named ones share the count
        else:
            child_ports = {(c.get("uplink") or {}).get("remotePort") for c in children.get(me, [])}
            members = {}
            for p in ports.values():
                if p.get("aggregated_by"):
                    members.setdefault(p["aggregated_by"], []).append(p)
            for idx in sorted(i for i in ports if isinstance(i, int)):
                p = ports[idx]
                wan = bool(p.get("is_uplink")) and not node["link"]          # a gateway has no parent switch: its "uplink" port is the way out to the internet, a port in its own right
                if (p.get("is_uplink") and not wan) or idx in child_ports or p.get("aggregated_by"):
                    continue
                group = [p] + members.get(idx, [])
                gports = {g.get("port_idx") for g in group}
                here = [c for c in wired if c.get("switch") == name and c.get("port") in gports]
                server = next((hosts[c["mac"]] for c in here if c.get("mac") in hosts), None)
                if not server:
                    server = next((hosts[g["lastMac"]] for g in group if g.get("lastMac") in hosts), None)
                who = server or (here[0].get("name") or here[0].get("ip") or "unnamed device" if here else ("Internet (WAN)" if wan and node["kind"] == "gateway" else "Uplink" if wan else ""))
                # a switch on this port (found by its SNMP name, or a client of that name) is a link between switches: everything behind it passes through
                infra = wan or (bool(switches) and (str(server or "").lower() in switches or any(str(c.get("name") or "").lower() in switches for c in here)))
                if len(here) > 1 and not server:
                    who += f" and {len(here) - 1} more"
                node["ports"].append({"keys": [[me, g.get("name")] for g in sorted(group, key=lambda g: g.get("port_idx") or 0) if g.get("name")],
                                      "port": "+".join(str(g.get("port_idx")) for g in sorted(group, key=lambda g: g.get("port_idx") or 0)), "name": who,
                                      "server": bool(server), "infra": infra, "macs": [c.get("mac") for c in here if c.get("mac")], "ips": [c.get("ip") for c in here if c.get("ip")], "speedMbps": sum(_num(g.get("speed")) for g in group),
                                      "down": sum(_num(g.get("outBps")) for g in group), "up_bps": sum(_num(g.get("inBps")) for g in group),
                                      "errors": sum(_num(g.get("rx_errors")) + _num(g.get("tx_errors")) for g in group),
                                      "drops": sum(_num(g.get("rx_dropped")) + _num(g.get("tx_dropped")) for g in group)})
        nodes.append(node)
    nodes.sort(key=lambda n: (n["kind"] != "gateway", n["name"].lower()))
    iot = sorted({c["ip"] for c in clients if c.get("ip") and is_iot(c)})
    infra_ips = sorted({d["ip"] for d in devices if d.get("ip")})
    infra_macs = sorted({d["mac"] for d in devices if d.get("mac") not in (None, "", "?")})
    return {"infraIps": infra_ips, "infraMacs": infra_macs, "iotIps": iot, "makers": {c["ip"]: c["oui"] for c in clients if c.get("ip") and c.get("oui")}, "nodes": nodes, "counts": {"devices": len(devices), "wired": len(wired), "wifi": len(clients) - len(wired)}, "notes": notes}
