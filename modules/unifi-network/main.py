"""UniFi module: devices, LAN topology and network health from a UniFi controller (read-only; see unifilib.py).

  check    {"check": "device",  "params": {"name": "Switch 2", "min_uplink_mbps": 1000}}
           {"check": "devices", "params": {"names": [...]}}        every adopted device (or just those named)
           {"check": "health",  "params": {"subsystem": "wan"}}    wan | lan | wlan | www | vpn
           {"check": "tunnel",  "params": {"name": "PIA Cali"}}    one VPN client or site-to-site tunnel
           {"check": "temperature", "params": {"name": "Aggregation", "max_c": 80}}   one device's temperature and fan
           connection: {host or base_url, username, password, site (default "default"), verify_tls (default false)}
  wan_ports {"connection": {...}} -> {"ports": [{"ifname","label","up","ip","gateway"}]}  which interfaces are the gateway's WAN
  lan_report {"connection": {...}, "clients": false?} -> every device's links, ports, rates and what it has learned (read-only, fields chosen, MACs shortened)
  client_usage {"connection": {...}, "seconds": 300?} -> bytes up and down per client over that time, as the gateway counts them (the biggest 30)
  flows {"connection": {...}, "seconds": 300?} -> the gateway's flow log boiled down: who talked to what (domain or address) and how many bytes, biggest first (the biggest 300)
  flows_look {"connection": {...}} -> what the gateway answers to the questions behind Insights, Flows: status and shape only (see unifilib.Client.look)
  discover {"connection": {...}} -> devices, which one hangs off which, and ready-made checks

A controller that cannot be reached, or a login that is refused, is Unknown, never Failed."""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unifilib as U  # noqa: E402
import unifichecks as C  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]
OUT = threading.Lock()
CLIENTS, CLIENTS_LOCK = {}, threading.Lock()


def client(conn):
    """One client per controller login, kept for the life of the module so the session (and the login
    back-off) is shared by every check."""
    key = (conn.get("base_url") or conn.get("host"), conn.get("username"), conn.get("password"), conn.get("site"), bool(conn.get("verify_tls")))
    with CLIENTS_LOCK:
        if key not in CLIENTS:
            CLIENTS[key] = U.Client(key[0], key[1], key[2], key[3], key[4], conn.get("timeout", 15))
        return CLIENTS[key]


def run_check(kind, params, conn):
    c = client(conn)
    if kind == "device":
        return C.check_device(params, c.get("stat/device"))
    if kind == "temperature":
        return C.check_temperature(params, c.get("stat/device"))
    if kind == "devices":
        return C.check_devices(params, c.get("stat/device"))
    if kind == "health":
        return C.check_health(params, c.get("stat/health"), c.get("stat/device") if str(params.get("subsystem")).lower() == "www" else None)
    if kind == "tunnel":
        return C.check_tunnel(params, c.get("rest/networkconf"), tunnel_status(c))
    return {"state": "unknown", "detail": f"unknown UniFi check '{kind}' (known: device, devices, temperature, health, tunnel)"}


def tunnel_status(c):
    """VPN connection status, or None when this controller does not report it (the tunnel then reads Unknown)."""
    try:
        return c.get("v2/vpn/connections")
    except U.UnifiError as e:
        if "does not report VPN tunnel status" in str(e):
            return None
        raise


def handle(req, deadline=None):
    """deadline: time.monotonic() by which the App wants an answer (None: no limit). The slow reads stop in time and say what they have."""
    m, a = req.get("method"), req.get("params", {})
    if m == "hello":
        return {"module": "unifi-network", "version": VERSION}
    if m == "describe":
        return {"title": "UniFi Network", "text": "Reads devices, topology and health from a UniFi controller, read-only", "status": "healthy"}
    if m == "check":
        return run_check(a.get("check") or "devices", a.get("params") or {}, a.get("connection") or {})
    if m == "wan_ports":
        return {"ports": C.wan_ports(client(a.get("connection") or {}).get("stat/device"))}
    if m == "lan_report":
        c = client(a.get("connection") or {})
        devices = c.get("stat/device")
        if a.get("clients", True) is False:               # the port history only needs the devices: one request, not two
            return C.lan_report(devices)
        try:
            clients, note = c.get("stat/sta"), None
        except U.UnifiError as e:                         # a login that may not read the client list still gets the rest
            clients, note = None, str(e)
        return C.lan_report(devices, clients, note)
    if m == "client_usage":
        sec = a.get("seconds") if isinstance(a.get("seconds"), int) else 300
        return C.client_usage(client(a.get("connection") or {}).usage(sec, deadline), max(60, min(sec, 3600)))
    if m == "flows":
        sec = a.get("seconds") if isinstance(a.get("seconds"), int) else 300
        info = {}
        out = C.flow_summary(client(a.get("connection") or {}).flows(sec, deadline, info), max(60, min(sec, 3600)))
        if info.get("partial"):
            out["partial"] = True                         # the newest flows only: the console was too slow to page through the rest in time
        return out
    if m == "flows_look":
        return {"attempts": client(a.get("connection") or {}).look(deadline)}
    if m == "discover":
        c = client(a.get("connection") or {})
        return C.discover(c.get("stat/device"), c.get("stat/health"), c.get("rest/networkconf"), tunnel_status(c))
    raise ValueError(f"unknown method {m}")


# Two lanes, so slow traffic questions can never use up the threads the device checks need (2026-11-14: they did, and ~20 items went Unknown).
# Status: checks and the quick reads. Slow: the flow log, per-client usage and the look report. Those all take the client's flow_lock, so only one can run at a
# time anyway: one thread is all that lane can use, and a short waiting line stops a pile-up while the console is slow.
SLOW = ("flows", "client_usage", "flows_look")
SLOW_WAITING = 3          # different slow questions that may wait behind the one running; one more answers "busy" at once
MARGIN = 1.0              # answer this much before the App stops waiting, so a partial answer still reaches it
STATUS_POOL = ThreadPoolExecutor(max_workers=4)
SLOW_POOL = ThreadPoolExecutor(max_workers=1)
JOBS, JOBS_LOCK = {}, threading.Lock()     # slow question (method and params) -> [(request id, deadline, arrived), ...]: identical questions share one job


def reply(out):
    with OUT:
        print(json.dumps(out), flush=True)


def answer(req, deadline=None):
    """Runs one request and returns its answer line (without the id)."""
    try:
        return {"result": handle(req, deadline)}
    except U.UnifiError as e:
        return {"result": {"state": "unknown", "detail": str(e)}} if req.get("method") == "check" else {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def deadline_of(req, arrived):
    """When the App stops waiting for this request (it sends its timeout with each one), less a margin; None if it did not say."""
    t = req.get("timeout")
    return arrived + max(0.5, float(t) - MARGIN) if isinstance(t, (int, float)) and t > 0 else None


def took(arrived, started):
    return {"wait": round((started - arrived) * 1000), "run": round((time.monotonic() - started) * 1000)}


def serve(req, arrived=None):
    """A status request. One that waited past the App's patience is not run: nobody is listening for its answer."""
    arrived = time.monotonic() if arrived is None else arrived
    started, deadline = time.monotonic(), deadline_of(req, arrived)
    if deadline is not None and started > deadline + MARGIN:
        return
    reply(dict(answer(req, deadline), id=req["id"], took=took(arrived, started)))


def ask_slow(req, arrived):
    key = req.get("method") + " " + json.dumps(req.get("params", {}), sort_keys=True)
    with JOBS_LOCK:
        if key in JOBS:                                   # the same question is already being asked: wait for that answer
            JOBS[key].append((req["id"], deadline_of(req, arrived), arrived))
            return
        if len(JOBS) > SLOW_WAITING:
            reply({"id": req["id"], "error": "the UniFi module is still busy with earlier traffic questions (the console is slow); try again shortly"})
            return
        JOBS[key] = [(req["id"], deadline_of(req, arrived), arrived)]
    SLOW_POOL.submit(run_slow, key, req)


def run_slow(key, req):
    started = time.monotonic()
    with JOBS_LOCK:
        waiters = list(JOBS[key])
    deadlines = [d for _, d, _ in waiters]
    deadline = None if None in deadlines else max(deadlines)
    if deadline is not None and started > deadline:      # everyone asking has given up: do not ask the console for nothing
        out = None
    else:
        out = answer(req, deadline)
    with JOBS_LOCK:
        waiters = JOBS.pop(key, [])                       # anyone who joined while it ran gets the same answer
    if out is not None:
        for rid, _, arrived in waiters:
            reply(dict(out, id=rid, took=took(arrived, started)))


def receive(req):
    arrived = time.monotonic()
    if req.get("method") in SLOW:
        ask_slow(req, arrived)
    else:
        STATUS_POOL.submit(serve, req, arrived)


if __name__ == "__main__":
    for line in sys.stdin:
        receive(json.loads(line))
