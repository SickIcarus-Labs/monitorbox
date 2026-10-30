"""A READ-ONLY client for the Portainer API. MonitorBox never talks to the Docker socket or to Portainer agents: it
asks the Portainer SERVER, which already manages every environment, using an access token (the X-API-Key header).

Only GET requests are ever sent, and only to the few paths in READ_ONLY. There is no login call, no POST, no PUT,
no DELETE: nothing here can start, stop, create or change anything. The token is sent only to the address in the
connection.

A Portainer that cannot be reached, or a token it refuses, raises PortainerError; the checks turn that into
Unknown, never Failed. Self-signed certificates are normal on Portainer, so the certificate is not verified unless
the connection sets "verify_tls": true."""
import json, re, ssl, threading, time
import urllib.error, urllib.request
from urllib.parse import urlsplit, urlencode

READ_ONLY = re.compile(r"^/api/(system/status|status|endpoints|endpoints/\d+/docker/containers/json)$")
CACHE_SECONDS = 5            # checks that run together share one fetch
DEFAULT_PORT = 9443


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the access token to wherever it points. Refuse it: the answer is then the redirect's own HTTP error."""
    def redirect_request(self, *a, **k):
        return None


class PortainerError(Exception):
    pass


def base_of(conn):
    """Where Portainer is. {base_url} is used as given. {host} alone means https on 9443 (Portainer's own default),
    or plain http on 9000 when the connection says "http": true; "port" overrides either."""
    raw = conn.get("base_url") or conn.get("host") or ""
    if not raw:
        raise PortainerError("this connection has no 'host' or 'base_url'")
    if "://" not in raw:
        plain = bool(conn.get("http"))
        port = conn.get("port") or (9000 if plain else DEFAULT_PORT)
        raw = ("http://" if plain else "https://") + (raw if ":" in raw else f"{raw}:{port}")
    p = urlsplit(raw)
    return f"{p.scheme}://{p.netloc}"


class Client:
    def __init__(self, base_url, token, verify_tls=False, timeout=8):
        if not token:
            raise PortainerError("this connection needs an access token (create one in Portainer under My account > Access tokens)")
        self.base, self.token, self.timeout = base_url, token, float(timeout)
        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler({}), _NoRedirect())
        self.lock, self.cache = threading.Lock(), {}

    def get(self, path, query=None, auth=True):
        if not READ_ONLY.match(path):
            raise PortainerError(f"refusing to fetch '{path}' (this module is read-only)")
        key = (path, tuple(sorted((query or {}).items())))
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        url = self.base + path + ("?" + urlencode(query) if query else "")
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        if auth:
            req.add_header("X-API-Key", self.token)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                data = json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise PortainerError(f"Portainer redirected the request (HTTP {e.code}); the token is never sent on to another address. Check the address, and whether it should be http or https")
            why = {401: "Portainer refused the access token", 403: "Portainer refused the access token (it may not be allowed to see that environment)",
                   404: "Portainer does not have that (is it a newer or older version?)"}.get(e.code, f"Portainer answered HTTP {e.code}")
            raise PortainerError(why)
        except (OSError, ValueError) as e:
            raise PortainerError(f"cannot reach Portainer at {self.base} ({getattr(e, 'reason', e)})")
        with self.lock:
            self.cache[key] = (time.time(), data)
        return data

    def endpoints(self):
        return self.get("/api/endpoints") or []

    def containers(self, env_id):
        return self.get(f"/api/endpoints/{int(env_id)}/docker/containers/json", {"all": "1"}) or []
