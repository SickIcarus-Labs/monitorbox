"""Portainer module: environments and containers, through the Portainer API (read-only; see portainerlib.py).

  check    {"check": "environment", "params": {"name": "Anchor3"}}                 is Portainer able to reach that environment
           {"check": "container",   "params": {"env": "Anchor3", "name": "plex", "allow_stopped": false}}
           connection: {base_url or host, token, verify_tls (default false)}
  discover {"connection": {...}} -> environments, containers (by Compose stack) and web checks for the ones that answer HTTP

Portainer that cannot be reached, or a token it refuses, is Unknown, never Failed. A container Portainer cannot read
because its environment is down is Unknown too (the environment's own check is the one that fails)."""
import json, os, ssl, sys, threading, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portainerlib as P  # noqa: E402
import portainerchecks as C  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]
OUT = threading.Lock()
CLIENTS, CLIENTS_LOCK = {}, threading.Lock()


def client(conn):
    key = (P.base_of(conn), conn.get("token"), bool(conn.get("verify_tls")))
    with CLIENTS_LOCK:
        if key not in CLIENTS:
            CLIENTS[key] = P.Client(key[0], key[1], key[2], conn.get("timeout", 8))
        return CLIENTS[key]


def probe_web(host, port, timeout=2.0):
    """Does something on host:port speak HTTP? One GET to the app's own port; nothing is sent anywhere else."""
    for scheme in ("http", "https"):
        ctx = None
        if scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        url = f"{scheme}://{host}:{port}/"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MonitorBox"}), timeout=timeout, context=ctx) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (urllib.error.URLError, OSError, ValueError):
            continue
        if code >= 500:
            return None
        out = {"url": url}
        if not 200 <= code < 400:
            out["expect"] = list(range(200, 400)) + [code]       # a login wall (401/403) still proves the app is answering
        if scheme == "https":
            out["insecure"] = True
        return out
    return None


def run_check(kind, params, conn):
    c = client(conn)
    if kind == "environment":
        return C.check_environment(params, c.endpoints())
    if kind == "container":
        return C.check_container(params, c.endpoints(), c.containers)
    return {"state": "unknown", "detail": f"unknown Portainer check '{kind}' (known: environment, container)"}


def handle(req):
    m, a = req.get("method"), req.get("params", {})
    if m == "hello":
        return {"module": "portainer", "version": VERSION}
    if m == "describe":
        return {"title": "Portainer", "text": "Reads environments and containers through the Portainer API, read-only", "status": "healthy"}
    if m == "check":
        return run_check(a.get("check") or "container", a.get("params") or {}, a.get("connection") or {})
    if m == "discover":
        conn = a.get("connection") or {}
        c = client(conn)
        host = P.urlsplit(P.base_of(conn)).hostname
        return C.discover(c.endpoints(), c.containers, host, probe_web)
    raise ValueError(f"unknown method {m}")


def serve(req):
    try:
        out = {"id": req["id"], "result": handle(req)}
    except P.PortainerError as e:
        out = {"id": req["id"], "result": {"state": "unknown", "detail": str(e)}} if req.get("method") == "check" \
            else {"id": req["id"], "error": str(e)}
    except Exception as e:
        out = {"id": req["id"], "error": str(e)}
    with OUT:
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    pool = ThreadPoolExecutor(max_workers=4)
    for line in sys.stdin:
        pool.submit(serve, json.loads(line))
