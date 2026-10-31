"""Network probes, standard library only. Each returns (ok, detail, ms):
ok True = worked, False = it answered wrongly or not at all, None = could not be checked here.
A probe never raises."""
import os, random, socket, ssl, struct, time, urllib.error, urllib.request


def _ms(t0):
    return round((time.monotonic() - t0) * 1000, 1)


# ---- ping ---------------------------------------------------------------
def _checksum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack(f"!{len(data) // 2}H", data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def _icmp_socket():
    """Unprivileged ICMP first, raw (needs NET_RAW) second."""
    for kind in (socket.SOCK_DGRAM, socket.SOCK_RAW):
        try:
            return socket.socket(socket.AF_INET, kind, socket.IPPROTO_ICMP), kind
        except (PermissionError, OSError):
            continue
    return None, None


def ping(host, timeout=2.0):
    try:
        ip = socket.gethostbyname(host)
    except OSError as e:
        return False, f"cannot resolve {host}", None
    s, kind = _icmp_socket()
    if s is None:
        return None, "ping is not permitted here (the container needs NET_RAW)", None
    ident = os.getpid() & 0xFFFF
    seq = random.randrange(1, 65535)
    body = b"monitorbox" + b"\0" * 22
    hdr = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
    pkt = struct.pack("!BBHHH", 8, 0, _checksum(hdr + body), ident, seq) + body
    try:
        s.settimeout(timeout)
        t0 = time.monotonic()
        s.sendto(pkt, (ip, 0))
        end = t0 + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return False, f"no reply from {ip}", None
            s.settimeout(left)
            data, addr = s.recvfrom(1024)
            if addr[0] != ip:
                continue
            icmp = data[(data[0] & 0x0F) * 4:] if kind == socket.SOCK_RAW else data
            if len(icmp) >= 8 and icmp[0] == 0 and (kind == socket.SOCK_DGRAM or struct.unpack("!HH", icmp[4:8]) == (ident, seq)):
                return True, f"reply from {ip}", _ms(t0)
    except socket.timeout:
        return False, f"no reply from {ip}", None
    except OSError as e:
        return None, f"ping failed to run: {e.strerror or e}", None
    finally:
        s.close()


# ---- tcp ----------------------------------------------------------------
def tcp(host, port, timeout=3.0):
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"port {port} open", _ms(t0)
    except socket.timeout:
        return False, f"port {port} timed out", None
    except ConnectionRefusedError:
        return False, f"port {port} refused the connection", None
    except OSError as e:
        return False, f"port {port}: {e.strerror or e}", None


# ---- http ---------------------------------------------------------------
BODY_LIMIT = 256 * 1024     # how much of a page is searched for `contains`


def status_codes(expect):
    """Allowed status codes from a list of numbers and "200-399" style ranges (the list a config holds)."""
    out = set()
    for e in expect or []:
        if isinstance(e, str) and "-" in e:
            a, b = e.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(e))
    return out


def _lan_ip_host(url):
    """True for an address that is a private-network IP (https://192.168.1.13/). A certificate can never properly match a bare IP, and a LAN
    device's own certificate is nearly always self-signed, so verifying it would only ever report a false problem. Names on the internet keep
    full verification."""
    import ipaddress
    from urllib.parse import urlsplit
    try:
        return ipaddress.ip_address(urlsplit(url).hostname or "").is_private
    except ValueError:
        return False


def http(url, timeout=10.0, expect=None, insecure=False, contains=None):
    """expect: allowed status codes (default 200-399). contains: text the page must include, so a login page
    or a different app answering on the same port does not read as healthy."""
    ctx = None
    if url.startswith("https") and (insecure or _lan_ip_host(url)):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    want = status_codes(expect) or set(range(200, 400))
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MonitorBox"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            code, body = r.status, (r.read(BODY_LIMIT) if contains else b"")
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read(BODY_LIMIT) if contains else b""
        except OSError:
            body = b""
    except (urllib.error.URLError, OSError, ValueError) as e:
        why = getattr(e, "reason", e)
        return False, f"{url}: {why}", None
    ok = code in want
    if ok and contains and str(contains).lower() not in body.decode("utf-8", "replace").lower():
        return False, f"HTTP {code} but the page does not contain '{contains}'", _ms(t0)
    return ok, f"HTTP {code}" + ("" if ok else " (not expected)"), _ms(t0)


# ---- dns ----------------------------------------------------------------
def _dns_query(name, qid):
    out = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    for label in name.rstrip(".").split("."):
        out += bytes([len(label)]) + label.encode()
    return out + b"\0" + struct.pack("!HH", 1, 1)  # A, IN


def _skip_name(buf, i):
    while True:
        n = buf[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:
            return i + 2
        i += 1 + n


def dns(server, name="google.com", timeout=3.0, port=53):
    """Ask one specific resolver for an A record. Tells you if THAT server answers and resolves."""
    qid = random.randrange(0, 65535)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        t0 = time.monotonic()
        s.sendto(_dns_query(name, qid), (server, port))
        while True:
            data, addr = s.recvfrom(2048)
            if addr[0] == server and len(data) >= 12 and struct.unpack("!H", data[:2])[0] == qid:
                break
        ms = _ms(t0)
        flags, qd, an = struct.unpack("!HHH", data[2:8])
        rcode = flags & 0xF
        if rcode != 0:
            return False, f"{server} answered with an error ({ {2: 'SERVFAIL', 3: 'NXDOMAIN', 5: 'REFUSED'}.get(rcode, rcode) })", ms
        i = 12
        for _ in range(qd):
            i = _skip_name(data, i) + 4
        for _ in range(an):
            i = _skip_name(data, i)
            rtype, _cls, _ttl, rdlen = struct.unpack("!HHIH", data[i:i + 10])
            i += 10
            if rtype == 1 and rdlen == 4:
                return True, f"{name} → {socket.inet_ntoa(data[i:i + 4])}", ms
            i += rdlen
        return False, f"{server} answered but gave no address for {name}", ms
    except socket.timeout:
        return False, f"{server} did not answer", None
    except (OSError, struct.error, IndexError) as e:
        return None, f"DNS check could not run: {e}", None
    finally:
        s.close()


def run(check):
    """Run one configured check dict and return (ok, detail, ms)."""
    t = check["type"]
    if t == "ping":
        return ping(check["target"], check.get("timeout", 2.0))
    if t == "tcp":
        return tcp(check["target"], check["port"], check.get("timeout", 3.0))
    if t == "http":
        return http(check["url"], check.get("timeout", 10.0), check.get("expect"), check.get("insecure", False), check.get("contains"))
    if t == "dns":
        return dns(check["server"], check.get("name", "google.com"), check.get("timeout", 3.0), check.get("port", 53))
    return None, f"unknown check type {t}", None
