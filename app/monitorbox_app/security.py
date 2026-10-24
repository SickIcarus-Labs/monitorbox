"""Safe to open over the internet: who is really asking, and how hard we let anyone guess.

The box sits behind a reverse proxy (Caddy) for outside visits. A request is only believed to come "through the proxy" when
the connection itself is from an address the owner listed as a trusted proxy; only then are the forwarded headers read, and
only the last address in X-Forwarded-For (the one the proxy itself added) is used. Everything else is treated as a direct
visit from the network the box is on."""
import ipaddress, threading, time
from .store import read_json, write_json

MAX_PROXIES = 5
FREE_TRIES = 5            # wrong passwords from one address before it is locked out
BASE_LOCK = 60            # seconds; doubles with every further wrong try, up to MAX_LOCK
MAX_LOCK = 900
FORGET = 900              # a quiet address starts again after this long
SPRAY_TRIES, SPRAY_WINDOW, SPRAY_LOCK = 30, 600, 300     # many addresses guessing at once: outside sign-ins pause


def norm_ip(s):
    """'::ffff:192.168.77.9' and '192.168.77.9' are the same address; anything that is not an address gives None."""
    try:
        a = ipaddress.ip_address(str(s).strip())
    except ValueError:
        return None
    return str(getattr(a, "ipv4_mapped", None) or a)


def clean(raw):
    raw = raw if isinstance(raw, dict) else {}
    proxies, seen = [], set()
    for x in raw.get("trustedProxies") or []:
        ip = norm_ip(x)
        if ip is None:
            raise ValueError(f'"{x}" is not an address. Use something like 192.168.77.9.')
        if ip not in seen:
            seen.add(ip); proxies.append(ip)
    if len(proxies) > MAX_PROXIES:
        raise ValueError(f"At most {MAX_PROXIES} proxy addresses.")
    host = str(raw.get("publicHost") or "").strip().lower()
    if host and (len(host) > 253 or any(c in host for c in " /\\@?#") or host.startswith(".")):
        raise ValueError("The public name should look like monitorbox.example.com, with no https:// or path.")
    return {"trustedProxies": proxies, "publicHost": host, "internetNeedsPasskey": bool(raw.get("internetNeedsPasskey"))}


class Request:
    """What one visit looks like once the proxy is taken into account."""
    def __init__(self, ip, via_proxy, https, host):
        self.ip, self.via_proxy, self.https, self.host = ip, via_proxy, https, host


class Lockout:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.by = {}          # address -> [wrong tries, last wrong try, locked until]
        self.spray = []       # times of recent wrong tries that came through the proxy

    def wait(self, ip, via_proxy):
        """Seconds this visitor must wait before another try, 0 if none."""
        now = self.clock()
        with self.lock:
            left = 0
            rec = self.by.get(ip)
            if rec and rec[2] > now:
                left = rec[2] - now
            if via_proxy:
                self.spray = [t for t in self.spray if t > now - SPRAY_WINDOW]
                if len(self.spray) >= SPRAY_TRIES:
                    left = max(left, self.spray[-1] + SPRAY_LOCK - now)
            return int(left + 0.999) if left > 0 else 0

    def failed(self, ip, via_proxy):
        now = self.clock()
        with self.lock:
            rec = self.by.get(ip)
            if not rec or now - rec[1] > FORGET:
                rec = self.by[ip] = [0, now, 0]
            rec[0] += 1; rec[1] = now
            if rec[0] >= FREE_TRIES:
                rec[2] = now + min(MAX_LOCK, BASE_LOCK * 2 ** (rec[0] - FREE_TRIES))
            if via_proxy:
                self.spray.append(now)
            if len(self.by) > 2000:                      # never grow without bound
                self.by = {k: v for k, v in self.by.items() if now - v[1] <= FORGET}

    def ok(self, ip):
        with self.lock:
            self.by.pop(ip, None)


class Security:
    def __init__(self, paths, clock=time.time):
        self.file = paths.p("config", "security.json")
        self.lockout = Lockout(clock)

    def cfg(self):
        try:
            return clean(read_json(self.file, {}))
        except ValueError:
            return {"trustedProxies": [], "publicHost": "", "internetNeedsPasskey": False}

    def save(self, raw):
        c = clean({**self.cfg(), **(raw if isinstance(raw, dict) else {})})      # what is not sent stays as it was
        write_json(self.file, c)
        return c

    def request(self, peer, headers):
        """peer: the address the connection came from. headers: the request's headers (a mapping with .get)."""
        c = self.cfg()
        ip = norm_ip(peer) or str(peer)
        host = str(headers.get("Host") or "").split(":")[0].strip().lower()
        if ip in c["trustedProxies"]:
            fwd = [norm_ip(x) for x in str(headers.get("X-Forwarded-For") or "").split(",") if x.strip()]
            real = fwd[-1] if fwd and fwd[-1] else None
            if real:
                proto = str(headers.get("X-Forwarded-Proto") or "").split(",")[-1].strip().lower()
                fhost = str(headers.get("X-Forwarded-Host") or headers.get("Host") or "").split(",")[-1].split(":")[0].strip().lower()
                return Request(real, True, proto == "https", fhost)
        return Request(ip, False, False, host)

    def host_ok(self, req):
        """Through the proxy, only the owner's public name is answered (when one is set)."""
        want = self.cfg()["publicHost"]
        return not (req.via_proxy and want and req.host != want)
