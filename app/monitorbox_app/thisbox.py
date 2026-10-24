"""What can MonitorBox see about the machine it runs on and the network around it? Read-only and polite:
it reads the routing table and resolv.conf, opens plain TCP connections to this box's own address, and sends
one SNMPv3 engine-discovery message (the standard "who are you" that carries no credentials). It never guesses
a password or community, never touches the Docker socket, and sends nothing to any other machine.

SNMPv2c cannot be recognised without a community name, so an agent that only speaks v2c shows as "not seen";
the person can still add it by hand.
"""
import ipaddress, os, re, socket, ssl, urllib.error, urllib.request

ROUTE, RESOLV = "/proc/net/route", "/etc/resolv.conf"
NUT_PORT, SNMP_PORT = 3493, 161
PORTAINER_PORTS = (9443, 9000)
PORTAINER_AGENT_PORT = 9001


def gateway(route_text=None):
    """The default route's next hop (IPv4), or None."""
    text = route_text if route_text is not None else _read(ROUTE)
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) >= 4 and f[1] == "00000000" and int(f[3], 16) & 2:
            try:
                return socket.inet_ntoa(bytes.fromhex(f[2])[::-1])
            except (ValueError, OSError):
                return None
    return None


def dns_servers(resolv_text=None):
    """IPv4 name servers in resolv.conf, without loopback ones (Docker's own 127.0.0.11 says nothing about the LAN)."""
    text = resolv_text if resolv_text is not None else _read(RESOLV)
    out = []
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 2 and f[0] == "nameserver":
            try:
                ip = ipaddress.ip_address(f[1])
            except ValueError:
                continue
            if ip.version == 4 and not ip.is_loopback and str(ip) not in out:
                out.append(str(ip))
    return out


def own_ip(gw=None):
    """This box's address on the way out. A UDP connect sends nothing; it only asks the OS which address it would use."""
    for target in (gw, "192.0.2.1"):
        if not target:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 9))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("0."):
                return ip
        except OSError:
            pass
        finally:
            s.close()
    return "127.0.0.1"


def tcp_open(host, port, timeout=0.6):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


# --- SNMPv3 engine discovery: a message with no user, no authentication and no data. Any v3 agent answers with a report.
def _tlv(tag, body):
    n = len(body)
    ln = bytes([n]) if n < 128 else bytes([0x80 | (n.bit_length() + 7) // 8]) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag]) + ln + body


def _int(v):
    return _tlv(2, v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True))


def _oct(b=b""):
    return _tlv(4, b)


def discovery_packet(msg_id=424242):
    usm = _tlv(0x30, _oct() + _int(0) + _int(0) + _oct() + _oct() + _oct())
    pdu = _tlv(0xA0, _int(msg_id) + _int(0) + _int(0) + _tlv(0x30, b""))
    scoped = _tlv(0x30, _oct() + _oct() + pdu)
    header = _tlv(0x30, _int(msg_id) + _int(65507) + _oct(b"\x04") + _int(3))
    return _tlv(0x30, _int(3) + header + _oct(usm) + scoped)


def _is_v3_reply(data):
    """A SEQUENCE whose first element is the INTEGER 3."""
    try:
        if data[0] != 0x30:
            return False
        i = 1
        i += 1 if data[i] < 128 else 1 + (data[i] & 0x7F)
        return data[i] == 2 and data[i + 1] == 1 and data[i + 2] == 3
    except IndexError:
        return False


def snmp_v3_answers(host, port=SNMP_PORT, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(discovery_packet(), (host, port))
        data, _ = s.recvfrom(4096)
        return _is_v3_reply(data)
    except OSError:
        return False
    finally:
        s.close()


def portainer_server(host, ports=PORTAINER_PORTS, timeout=1.5):
    """(port, version) when a Portainer SERVER answers its public status page (no login), else None. An agent has no such page."""
    import json, ssl, urllib.request
    for port in ports:
        if not tcp_open(host, port):
            continue
        for scheme in ("https", "http"):
            ctx = None
            if scheme == "https":
                ctx = ssl.create_default_context()
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            for path in ("/api/system/status", "/api/status"):
                try:
                    with urllib.request.urlopen(f"{scheme}://{host}:{port}{path}", timeout=timeout, context=ctx) as r:
                        data = json.loads(r.read() or b"{}")
                    if isinstance(data, dict) and "Version" in data:
                        return port, str(data["Version"])
                except (OSError, ValueError):
                    continue
    return None


ARP = "/proc/net/arp"
SCRYPTED_PORT = 10443


def unifi_console(host, ports=(443,), schemes=("https",), timeout=1.5):
    """Does a UniFi console (UniFi OS) answer its front page at this address? One plain GET; nothing is sent to anything else."""
    import ssl, urllib.request
    for port in ports:
        if not tcp_open(host, port):
            continue
        for scheme in schemes:
            ctx = None
            if scheme == "https":
                ctx = ssl.create_default_context()
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            try:
                with urllib.request.urlopen(f"{scheme}://{host}:{port}/", timeout=timeout, context=ctx) as r:
                    body = r.read(40000).decode("utf-8", "replace").lower()
                if "unifi" in body:
                    return True
            except OSError:
                continue
            except ValueError:
                continue
    return False


def web_page(host, ports=((443, "https"), (80, "http")), timeout=2.0):
    """The address of the web page this machine serves (its admin page), or None. Any answer counts, even a login wall or an error page."""
    for port, scheme in ports:
        if not tcp_open(host, port):
            continue
        ctx = None
        if scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        try:
            urllib.request.urlopen(f"{scheme}://{host}:{port}/", timeout=timeout, context=ctx).close()
        except urllib.error.HTTPError:
            pass                                    # it answered: that is a web page
        except (OSError, ValueError):
            continue
        return f"{scheme}://{host}/" if port in (80, 443) else f"{scheme}://{host}:{port}/"
    return None


WEB_PORTS = ((443, "https"), (80, "http"), (8443, "https"), (8080, "http"))
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def http_get(url, timeout=2.0, limit=65536):
    """(status, first bytes of the body as text) for a page, or None when nothing answers. Any answer counts, even an error page or a login wall;
    certificates are not checked (this only asks whether a page is there) and nothing is ever sent but the GET."""
    ctx = None
    if url.startswith("https"):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MonitorBox"}), timeout=timeout, context=ctx)
    except urllib.error.HTTPError as e:
        r = e
    except (OSError, ValueError):
        return None
    try:
        return r.status if hasattr(r, "status") else r.code, r.read(limit).decode("utf-8", "replace")
    except OSError:
        return None
    finally:
        r.close()


def identify_web(host, ports=WEB_PORTS, get=http_get, is_open=tcp_open):
    """The web page a machine serves, recognised when it is one we know: {url, kind, title, insecure}, or None when it serves none.
    Known pages get their right address (a Pi-hole's is /admin/); anything else is named by its page title. Read-only: only GETs, no login."""
    for port, scheme in ports:
        if not is_open(host, port):
            continue
        base = f"{scheme}://{host}" + ("" if port in (80, 443) else f":{port}")
        r = get(base + "/admin/")
        if r and "pi-hole" in r[1].lower():
            return {"url": base + "/admin/", "kind": "pihole", "title": "Pi-hole", "insecure": scheme == "https"}
        r = get(base + "/")
        if r is None:
            continue
        low = r[1].lower()
        m = TITLE_RE.search(r[1])
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:50] if m else ""
        kind = "unifi" if "unifi" in low else None
        return {"url": base + "/", "kind": kind, "title": "UniFi" if kind else title, "insecure": scheme == "https"}
    return None


def _reverse(ip):
    try:
        n = socket.gethostbyaddr(ip)[0].split(".")[0]
        return n if n and n != ip else None
    except OSError:
        return None


def netbios_name(ip, port=137, timeout=1.0):
    """The machine's own name from a NetBIOS node-status question (UDP 137): NAS boxes and Windows machines answer it even when DNS knows nothing."""
    import struct
    q = struct.pack("!HHHHHH", 0x4D42, 0, 1, 0, 0, 0) + b"\x20" + b"CK" + b"A" * 30 + b"\x00" + struct.pack("!HH", 0x21, 1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(q, (ip, port))
            d = s.recv(1024)
        qd, an = struct.unpack("!HH", d[4:8])
        i = 12
        for _ in range(qd):
            i += d[i] + 1 + 1 + 4 if d[i] else 1 + 4
        if not an:
            return None
        i += 1 + d[i] + 1 + 10 if d[i] else 1 + 10            # the answer's name, then type, class, ttl and length
        for k in range(d[i]):
            e = d[i + 1 + 18 * k:i + 1 + 18 * (k + 1)]
            if len(e) == 18 and e[15] == 0 and not (e[16] & 0x80):          # a unique workstation name
                return e[:15].decode("ascii", "replace").strip().lower() or None
    except (OSError, IndexError, struct.error):
        pass
    return None


def reverse_name(ip):
    return _reverse(ip) or netbios_name(ip)


def neighbor_mac(ip, arp_text=None):
    """The MAC address this box has seen for an address on its own network (from the ARP table), or None. Only works on the same network,
    and only once the two have talked, which the probes in scan() make sure of."""
    text = arp_text if arp_text is not None else _read(ARP)
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) >= 4 and f[0] == ip and int(f[2], 16) & 2 and f[3] != "00:00:00:00:00:00":
            return f[3].lower()
    return None


def scan(host=None, snmp_port=SNMP_PORT, nut_port=NUT_PORT, portainer_ports=PORTAINER_PORTS, agent_port=PORTAINER_AGENT_PORT, route_text=None, resolv_text=None,
         scrypted_port=SCRYPTED_PORT, console_ports=(443,), console_schemes=("https",), arp_text=None):
    """Look at this box (no host) or at one machine the person named. Reads and asks; never guesses a password."""
    from concurrent.futures import ThreadPoolExecutor
    gw = gateway(route_text)
    ip = host or own_ip(gw)
    with ThreadPoolExecutor(max_workers=8) as ex:
        f = {"snmp": ex.submit(snmp_v3_answers, ip, snmp_port), "nut": ex.submit(tcp_open, ip, nut_port),
             "portainer": ex.submit(portainer_server, ip, portainer_ports), "agent": ex.submit(tcp_open, ip, agent_port),
             "scrypted": ex.submit(tcp_open, ip, scrypted_port), "unifi": ex.submit(unifi_console, ip, console_ports, console_schemes),
             "gwunifi": ex.submit(unifi_console, gw, console_ports, console_schemes) if gw and not host else None,
             "web": ex.submit(web_page, ip) if host else None, "name": ex.submit(reverse_name, ip) if host else None}
        r = {k: (v.result() if v else None) for k, v in f.items()}
    snmp, nut, server, agent = r["snmp"], r["nut"], r["portainer"], r["agent"]
    return {
        "hostname": r["name"] if host else socket.gethostname(), "ip": ip, "gateway": gw, "dns": dns_servers(resolv_text),
        "gatewayUnifi": bool(r["gwunifi"]), "mac": neighbor_mac(ip, arp_text) if host else None,
        "services": [
            {"module": "snmp", "label": "SNMP (health, disks, network ports)", "found": snmp, "port": snmp_port,
             "note": "" if snmp else "Not seen. An agent that only speaks SNMP v2c cannot be detected, but you can still add it."},
            {"module": "nut", "label": "Battery backup (NUT)", "found": nut, "port": nut_port, "note": ""},
            {"module": "portainer", "label": "Portainer", "found": server is not None, "port": server[0] if server else None,
             "note": f"Version {server[1]}. MonitorBox reads it with an access token; one connection covers every environment it manages." if server else
                     ("This box runs a Portainer agent, which another Portainer server manages. Point MonitorBox at that server instead." if agent else "")},
            {"module": "scrypted", "label": "Scrypted (camera hub)", "found": bool(r["scrypted"]), "port": scrypted_port, "optional": True,
             "note": "Answers on Scrypted's usual port. It needs a read-only Scrypted login."},
            {"module": "web", "label": "Web page", "found": bool(r["web"]), "optional": True, "url": r["web"],
             "note": f"{r['web']} answers. MonitorBox can check that it stays up."},
            {"module": "unifi-network", "label": "UniFi Network", "found": bool(r["unifi"]), "optional": True,
             "note": "A UniFi console answers here. It needs a read-only local login."},
            {"module": "unifi-protect", "label": "UniFi Protect (cameras)", "found": bool(r["unifi"]), "optional": True,
             "note": "The same console usually runs Protect too (same kind of read-only login)."},
        ],
    }


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""
