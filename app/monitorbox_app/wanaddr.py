"""This box's own public (WAN) address, and what to make of an address another site tells us.

Sites are paired over a private address (usually through a site-to-site VPN), so when either site's internet drops, the link drops with it and a ping to the
private address proves nothing. The sites therefore tell each other their public addresses, and a silent link is judged by pinging that address from outside
the tunnel (peer.py). Read-only: this only reads the gateway's WAN address, or asks one public page what address a request came from.

Where the address comes from, in order:
  1. The UniFi gateway's own WAN address (UniFi Network login). No request leaves the box.
  2. Only when there is no UniFi gateway to ask: one request to a public page that echoes the caller's address (Cloudflare's trace page), a few times an hour at most.
A UniFi gateway that reports a *private* WAN address (a real double NAT, or a UniFi glitch that reports a private address on a public line) is treated as "cannot tell":
the address is not shared and the reflector is not asked, so a wrong or unpingable address is never handed to the other site. It is read again on the next round.
"""
import ipaddress, re, threading, time, urllib.request

REFLECTOR = "https://www.cloudflare.com/cdn-cgi/trace"       # answers with lines like ip=203.0.113.9
TTL_UNIFI = 300          # seconds a UniFi answer is trusted (a local call, cheap)
TTL_REFLECTOR = 1800     # seconds a reflector answer is trusted (an outside request: as seldom as is useful)
TTL_PRIVATE = 60         # a private or missing address is looked at again soon: the glitch clears by itself


def classify(ip):
    """'public' for an address the internet can reach, 'private' for one it cannot (private, shared 100.64.0.0/10, loopback, link-local, documentation-less reserved), 'invalid' for nonsense."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return "invalid"
    return "public" if a.is_global else "private"


def reflect(url=REFLECTOR, timeout=5):
    """The address a public page sees us as, or None."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            text = r.read(2048).decode("ascii", "replace")
    except Exception:
        return None
    m = re.search(r"^ip=(\S+)$", text, re.M)
    return m.group(1) if m else None


class Own:
    """This box's public address, kept as {"ip", "state", "source", "why"}; state is 'ok', 'private' (cannot tell: see the module note) or 'unknown'."""

    def __init__(self, unifi_ports, reflector=reflect, clock=time.time):
        self.unifi_ports = unifi_ports        # () -> list of {"ip": ..., "up": ...} from the gateway, or None when there is no UniFi gateway to ask
        self.reflector, self.clock = reflector, clock
        self.lock = threading.Lock()
        self.cached, self.at, self.ttl, self.stale = None, 0.0, 0.0, False

    def peek(self):
        """What is known now, without looking anything up (for a screen that must open at once), or None."""
        with self.lock:
            return dict(self.cached) if self.cached is not None else None

    def invalidate(self):
        """Look again at the next ask (the line came back after an outage, say: the address may have changed)."""
        with self.lock:
            self.stale = True

    def get(self):
        with self.lock:
            now = self.clock()
            if self.cached is not None and not self.stale and now - self.at < self.ttl:
                return dict(self.cached)
        got, ttl = self._look()
        with self.lock:
            self.cached, self.at, self.ttl, self.stale = got, self.clock(), ttl, False
            return dict(got)

    def _look(self):
        try:
            ports = self.unifi_ports()
        except Exception:
            ports = None
        if ports:                                                      # the gateway says: believe it, and never ask outside
            ips = [str(p.get("ip") or "").strip() for p in ports if isinstance(p, dict) and p.get("ip")]
            pub = next((i for i in ips if classify(i) == "public"), None)
            if pub:
                return {"ip": pub, "state": "ok", "source": "unifi", "why": ""}, TTL_UNIFI
            if ips:
                return {"ip": None, "state": "private", "source": "unifi",
                        "why": "the UniFi gateway reports a private WAN address (double NAT, or a UniFi glitch); the public address is not shared until it reports a public one"}, TTL_PRIVATE
            return {"ip": None, "state": "unknown", "source": "unifi", "why": "the UniFi gateway reports no WAN address"}, TTL_PRIVATE
        ip = self.reflector()
        if ip and classify(ip) == "public":
            return {"ip": ip, "state": "ok", "source": "reflector", "why": ""}, TTL_REFLECTOR
        return {"ip": None, "state": "unknown", "source": "reflector", "why": "this box could not work out its public address"}, TTL_PRIVATE


LAN = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]


def is_lan(ip):
    """True for an address on a private network (the ranges routers hand out), which is where a gateway lives."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return False
    return any(a in n for n in LAN)


def default_gateway(path="/proc/net/route"):
    """This box's default gateway (a private address on the local network), or None. Read from the network table, nothing is sent."""
    try:
        with open(path) as f:
            for line in f.read().splitlines()[1:]:
                p = line.split()
                if len(p) > 3 and p[1] == "00000000" and int(p[3], 16) & 2:
                    b = bytes.fromhex(p[2])[::-1]
                    ip = ".".join(str(x) for x in b)
                    return ip if is_lan(ip) else None
    except Exception:
        pass
    return None
