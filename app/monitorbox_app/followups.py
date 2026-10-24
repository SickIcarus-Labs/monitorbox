"""What else could be added, given what is already connected? Each login or server that MonitorBox knows can point at more:
a UniFi Network controller usually sits on a console that also runs Protect (same address, same login), and a declared server that
answers on Scrypted's usual port probably runs Scrypted. Nothing here is a network scan: it only looks at addresses you have already
declared, with one plain TCP connect to one well-known port. Suggestions are proposals; nothing is added until the person says so.
"""
import hashlib, ipaddress, re, socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

SCRYPTED_PORT = 10443


def host_of(conn):
    h = conn.get("host") or urlsplit(str(conn.get("base_url") or "")).hostname or ""
    return str(h).strip().lower()


def tcp_open(host, port, timeout=0.7):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def suggest(conns, port_open=tcp_open):
    """Proposals, each {id, kind, title, why, how: 'add' | 'setup', from?, host?}. 'add' can be done in one tap (the login is reused);
    'setup' needs a login the person has to type."""
    conns = [c for c in conns if isinstance(c, dict)]
    have = {}
    for c in conns:
        have.setdefault(c.get("module"), set()).add(host_of(c))
    out = []
    for c in conns:
        h = host_of(c)
        if c.get("module") == "unifi-network" and h and h not in have.get("unifi-protect", set()):
            out.append({"id": "protect:" + str(c["id"]), "kind": "unifi-protect", "how": "add", "from": c["id"], "host": h,
                        "title": f"UniFi Protect on {h}",
                        "why": "Your UniFi console usually runs Protect too. It reuses the same read-only login and adds your cameras."})
    hosts = sorted({host_of(c) for c in conns if host_of(c)} - have.get("scrypted", set()))
    if hosts:
        with ThreadPoolExecutor(max_workers=min(8, len(hosts))) as ex:
            opened = list(ex.map(lambda h: port_open(h, SCRYPTED_PORT), hosts))
        for h, ok in zip(hosts, opened):
            if ok:
                out.append({"id": "scrypted:" + h, "kind": "scrypted", "how": "setup", "host": h, "title": f"Scrypted on {h}",
                            "why": f"Something answers on port {SCRYPTED_PORT}, Scrypted's usual port. Add it for live video and its cameras (it needs a read-only Scrypted login)."})
    return out


# A container in Portainer that is really one of our integrations: image or container name -> module
CONTAINER_KINDS = (("scrypted", "scrypted", "Scrypted"), ("unifi-network-application", "unifi-network", "UniFi Network"), ("unifi", "unifi-network", "UniFi Network"))


def from_portainer(discoveries, conns):
    """Proposals from what Portainer says is running. `discoveries` is a list of the portainer module's discover() results.
    Reading only: it uses the container list Portainer already gave us."""
    have = {}
    for c in conns:
        have.setdefault(c.get("module"), set()).add(host_of(c))
    out = []
    known = {host_of(c) for c in conns}
    for d in discoveries:
        for e in (d or {}).get("environments", []):          # the machines Portainer manages: each could be a server of its own
            h = str(e.get("address") or "").strip().lower()
            if h and h not in known:
                known.add(h)
                out.append({"id": "server:" + h, "kind": "server", "how": "server", "host": h, "name": str(e.get("name") or h),
                            "title": f"{e.get('name') or h} ({h})",
                            "why": "Portainer manages this machine. Add it as a server to see what it offers."})
    for d in discoveries:
        addr = {e["name"]: e.get("address") or "" for e in (d or {}).get("environments", [])}
        for it in (d or {}).get("suggest", []):
            svc = it.get("service") or {}
            if it.get("check") != "container" or not svc:
                continue
            key = (str(svc.get("icon", "")) + " " + str(svc.get("container", ""))).lower()
            if "watchtower" in key:                  # the updater for Scrypted's container is not Scrypted
                continue
            kind = next(((k, t) for needle, k, t in CONTAINER_KINDS if needle in key), None)
            if not kind:
                continue
            host = (urlsplit(svc["url"]).hostname if svc.get("url") else "") or addr.get(svc.get("env"), "")
            if not host or host.lower() in have.get(kind[0], set()):
                continue
            host = host.lower()
            out.append({"id": f"{kind[0]}:{host}", "kind": kind[0], "how": "setup", "host": host, "title": f"{kind[1]} on {host}",
                        "why": f"Portainer shows a {svc.get('title') or svc.get('container')} container on {svc.get('env')}. Add it (it needs a read-only login of its own)."})
    return out


def new_items(out, watching, seen):
    """What a connection's discover() lists that is worth proposing: not watched yet, not an opt-in extra (default false, a system-level
    item or a network interface), and not already known (present when we first looked, or one the person already answered)."""
    res = []
    for x in ((out or {}).get("suggest") or []) if isinstance(out, dict) else []:
        label = x.get("label")
        if not label or x.get("default") is False or x.get("system") or x.get("batch") == "Network interfaces":
            continue
        if watching(label) or label in seen:
            continue
        res.append(x)
    return res


def runs_at(conn, found, item):
    """(machine address, container name) for a Portainer container or web item: which container on which machine it is, whichever Portainer
    connection reports it. A server Portainer and an agent Portainer on the same machine see the same container; this key is how they are matched.
    None for anything else."""
    svc = item.get("service") or {}
    if not svc.get("container"):
        return None
    env = next((e for e in (found or {}).get("environments", []) if e.get("name") == svc.get("env")), None)
    if env is not None and not env.get("address"):         # an edge agent calls Portainer and has no address: do not guess it is the Portainer server's own machine
        return (f"environment {svc.get('env')}", str(svc["container"]))
    addr = str((env or {}).get("address") or host_of(conn)).strip().lower()
    return (addr, str(svc["container"])) if addr else None


def one_home(per_conn):
    """per_conn: [(conn, found, new_items, known)] where `known(item)` says that connection already watches or has answered it.
    A container that two connections can both see is proposed once: not at all if any connection already knows it, otherwise on the connection
    whose own address is the machine it runs on (else the first). Returns [(conn, items)] with the duplicates removed."""
    known, owner = set(), {}
    for c, found, new, kn in per_conn:
        for it in (found or {}).get("suggest", []):
            k = runs_at(c, found, it)
            if k and kn(it):
                known.add(k)
        for it in new:
            k = runs_at(c, found, it)
            if k and (k not in owner or (host_of(c) == k[0] and owner[k][1] != k[0])):
                owner[k] = (c["id"], host_of(c))
    out = []
    for c, found, new, kn in per_conn:
        keep = []
        for it in new:
            k = runs_at(c, found, it)
            if k and (k in known or owner[k][0] != c["id"]):
                continue
            keep.append(it)
        out.append((c, keep))
    return out


def machine_of(conn, found, items, conns):
    """The machine the new things run on, in the person's own words: when they all run at one address, the server declared at that address
    (else Portainer's name for the environment); otherwise None and the connection that reports them is named."""
    keys = [runs_at(conn, found, it) for it in items]
    addrs = {k[0] for k in keys if k}
    if len(addrs) != 1 or None in keys:                    # (address, container) keys: several containers on one machine are one address
        return None
    addr = next(iter(addrs))
    others = [c for c in conns if c is not conn and c.get("module") != "portainer" and c.get("name")]
    envs = {(it.get("service") or {}).get("env") for it in items}
    env = str(envs.pop()) if len(envs) == 1 and None not in envs else None
    mine = [c for c in others if host_of(c) == addr]
    if not mine and env:                                   # no address to match: a declared server whose name is part of the environment's ("Bay Harbor - Anchor3")
        hit = [c for c in others if str(c["name"]).lower() in env.lower()]
        mine = sorted(hit, key=lambda c: -len(str(c["name"])))[:1] if len({str(c["name"]).lower() for c in hit}) == 1 else []
    return str(mine[0]["name"]) if mine else env


def new_items_proposal(conn, items, machine=None):
    """One proposal per connection that has new things: the id changes when the set changes, so a dismissed set does not hide later arrivals."""
    labels = sorted(str(x["label"]) for x in items)
    name = machine or conn.get("name") or conn.get("id")
    n = len(labels)
    tails = {l.rsplit(" on ", 1)[1] for l in labels if " on " in l}
    plain = [l.rsplit(" on ", 1)[0] for l in labels] if len(tails) == 1 and all(" on " in l for l in labels) else labels      # "Container x on Box" listed under Box says "Container x"
    shown = ", ".join(plain[:4]) + (f" and {n - 4} more" if n > 4 else "")
    return {"id": f"new:{conn['id']}:{hashlib.sha1(chr(10).join(labels).encode()).hexdigest()[:8]}", "kind": "new-items", "how": "items", "from": conn["id"],
            "labels": labels, "on": str(name), "title": f"{n} new thing{'' if n == 1 else 's'} on {name}",
            "why": f"{name} now offers {shown}. Add them to watch them (reading only)."}


def notes_from_portainer(discoveries):
    """Things worth saying about what Portainer manages that cannot be proposed as servers: edge agents call Portainer, so they have no address."""
    out = []
    for d in discoveries:
        edge = [str(e.get("name")) for e in (d or {}).get("environments", []) if e.get("edge")]
        if edge:
            out.append(f"Portainer also manages {len(edge)} edge agent{'' if len(edge) == 1 else 's'} ({', '.join(edge[:4])}{', …' if len(edge) > 4 else ''}). "
                       "They have no address to look at; their containers are watched through Portainer.")
    return out


def web_targets(nodes, conns, gateway=None, dns=()):
    """(host, role) for every address worth looking at for a web page: the gateway, the DNS servers (as configured, plus what this box sees),
    and each declared server. One entry per host, the most specific role first."""
    out = {}
    def add(h, role):
        h = str(h or "").strip().lower()
        try:
            if not ipaddress.ip_address(h).is_private:        # 1.1.1.1 and 8.8.8.8 are not yours to look at
                return
        except ValueError:
            pass                                               # a name a person typed
        if h and h not in out:
            out[h] = role
    for n in nodes:
        for c in n.get("checks", []):
            if c.get("type") == "ping" and n.get("id") == "gateway":
                add(c.get("target"), "gateway")
            elif c.get("type") == "dns":
                add(c.get("server"), "dns")
    add(gateway, "gateway")
    for d in dns:
        add(d, "dns")
    for c in conns:
        add(host_of(c), "server")
    return sorted(out.items())


def origin_of(url):
    """(host, port) of a web address, with the port its scheme implies, or None."""
    try:
        u = urlsplit(str(url))
        if not u.hostname:
            return None
        return u.hostname.lower(), u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        return None


def watched_origins(nodes):
    """The web addresses (host and port) that already have a web check, an opened link or a service URL, so exactly those are not offered again.
    A machine that has one page watched (Portainer on 9443, say) can still be offered its other pages (a Pi-hole on 80)."""
    have = set()
    for n in nodes:
        urls = [c.get("url") for c in n.get("checks", []) if c.get("type") == "http"] + [n.get("link")]
        sv = n.get("service")
        if isinstance(sv, dict):
            urls.append(sv.get("url"))
        for u in urls:
            o = origin_of(u) if u else None
            if o:
                have.add(o)
    return have


def web_suggestions(targets, covered, identify):
    """One proposal per address that serves a web page nobody watches yet. `identify(host)` is thisbox.identify_web.
    Router and DNS servers are offered whatever the page is (a router's admin page is worth watching on any brand); recognised pages get their
    own name; other servers' pages are offered named by their title. Proposals only: nothing is added until the person taps."""
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
        found = list(ex.map(lambda t: identify(t[0]), targets))
    out = []
    for (h, role), w in zip(targets, found):
        if not w or origin_of(w["url"]) in covered:          # nothing there, or that very page is already watched
            continue
        kind, title = w.get("kind"), w.get("title") or ""
        if kind == "pihole":
            name, why = f"Pi-hole admin ({h})", "A Pi-hole answers here. Watch its admin page so you know when it stops."
        elif kind == "unifi":
            name, why = f"UniFi console ({h})", "A UniFi console's web page answers here. Watch it so you know when it stops."
        elif role == "gateway":
            name, why = "Router admin page", f"Your router's admin page answers at {w['url']}. Watch it so you know when it stops."
        else:
            name = f"{title} ({h})" if title else f"Web page ({h})"
            why = f"A web page answers at {w['url']}. Watch it so you know when it stops."
        out.append({"id": "web:" + h, "kind": "web", "how": "webpage", "host": h, "role": role, "url": w["url"], "insecure": bool(w.get("insecure")),
                    "title": name, "why": why})
    return out


def merge(*lists):
    """One proposal per id; the later list wins (Portainer's evidence is stronger than an open port)."""
    seen = {}
    for lst in lists:
        for x in lst:
            seen[x["id"]] = x
    return list(seen.values())


def protect_from(source, existing_ids):
    """The Protect connection that reuses a UniFi Network controller's address and login (copied here, on the box; the secret never reaches the browser)."""
    base, k = str(source["id"]) + "-protect", 2
    cid = base[:40]
    while cid in existing_ids:
        cid, k = f"{base[:36]}-{k}", k + 1
    new = {"id": cid, "module": "unifi-protect"}
    for key in ("base_url", "host", "port", "username", "password", "verify_tls", "timeout"):
        if key in source:
            new[key] = source[key]
    return new


# ---- switches that answer the SNMP login you already saved ----
SNMP_KEYS = ("version", "port", "community", "user", "auth", "authPassword", "priv", "privPassword", "timeout", "retries")
GATEWAY_TYPES = ("udm", "ugw", "uxg")


def snmp_source(conns, sweep):
    """The saved SNMP login to try on the switches: the one on the UniFi gateway (or on the UniFi console's own address), or the only
    SNMP connection there is. With several and no clear match nothing is tried: guessing a login on devices is how accounts get locked."""
    snmps = [c for c in conns if c.get("module") == "snmp" and host_of(c)]
    gw = {str(d.get("ip") or "").lower() for out in (sweep or {}).values() for d in (out or {}).get("devices") or [] if d.get("type") in GATEWAY_TYPES}
    uni = {host_of(c) for c in conns if c.get("module") == "unifi-network"}
    for want in (gw, uni):
        hit = [c for c in snmps if host_of(c) in want]
        if hit:
            return hit[0]
    return snmps[0] if len(snmps) == 1 else None


def switch_candidates(conns, sweep):
    """[(name, ip)] of the UniFi switches that are not an SNMP connection yet (read from what UniFi already told us)."""
    have = {host_of(c) for c in conns if c.get("module") == "snmp"}
    found = {}
    for c in conns:
        if c.get("module") != "unifi-network":
            continue
        for d in ((sweep or {}).get(c.get("id")) or {}).get("devices") or []:
            ip = str(d.get("ip") or "").strip().lower()
            if d.get("type") == "usw" and ip and ip not in have:
                found.setdefault(ip, str(d.get("name") or ip))
    return sorted(((n, ip) for ip, n in found.items()), key=lambda t: t[0].lower())


def switches_proposal(source, answered):
    """One proposal for all the switches that answered. `answered` is [{"name", "ip"}]. The id changes with the set, so a dismissed set
    does not hide a switch that starts answering later."""
    n = len(answered)
    names = sorted(a["name"] for a in answered)
    shown = ", ".join(names[:4]) + (f" and {n - 4} more" if n > 4 else "")
    key = hashlib.sha1(chr(10).join(sorted(a["ip"] for a in answered)).encode()).hexdigest()[:8]
    return {"id": f"snmp-switches:{source['id']}:{key}", "kind": "snmp-switches", "how": "snmp-switches", "from": source["id"],
            "switches": sorted(answered, key=lambda a: a["name"].lower()), "title": f"{n} switch{'' if n == 1 else 'es'} answer your SNMP login",
            "why": f"{shown} answered with the same read-only login as {source.get('name') or source['id']}. Add them for port-by-port numbers on the map."}


def switch_connection(source, sw, existing_ids):
    """An SNMP connection for one switch with the source's login (copied here, on the box; the secret never reaches the browser)."""
    base = "snmp-" + (re.sub(r"[^a-z0-9]+", "-", str(sw["name"]).lower()).strip("-") or sw["ip"].replace(".", "-"))
    cid, k = base[:40], 2
    while cid in existing_ids:
        cid, k = f"{base[:36]}-{k}", k + 1
    new = {"id": cid, "module": "snmp", "name": str(sw["name"])[:60], "host": sw["ip"]}
    for key in SNMP_KEYS:
        if key in source:
            new[key] = source[key]
    return new
