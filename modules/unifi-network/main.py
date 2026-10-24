"""UniFi module: devices, LAN topology and network health from a UniFi controller (read-only; see unifilib.py).

  check    {"check": "device",  "params": {"name": "Switch 2", "min_uplink_mbps": 1000}}
           {"check": "devices", "params": {"names": [...]}}        every adopted device (or just those named)
           {"check": "health",  "params": {"subsystem": "wan"}}    wan | lan | wlan | www | vpn
           {"check": "tunnel",  "params": {"name": "PIA Cali"}}    one VPN client or site-to-site tunnel
           connection: {host or base_url, username, password, site (default "default"), verify_tls (default false)}
  wan_ports {"connection": {...}} -> {"ports": [{"ifname","label","up","ip","gateway"}]}  which interfaces are the gateway's WAN
  lan_report {"connection": {...}, "clients": false?} -> every device's links, ports, rates and what it has learned (read-only, fields chosen, MACs shortened)
  client_usage {"connection": {...}, "seconds": 300?} -> bytes up and down per client over that time, as the gateway counts them (the biggest 30)
  flows {"connection": {...}, "seconds": 300?} -> the gateway's flow log boiled down: who talked to what (domain or address) and how many bytes, biggest first (the biggest 300)
  flows_look {"connection": {...}} -> what the gateway answers to the questions behind Insights, Flows: status and shape only (see unifilib.Client.look)
  discover {"connection": {...}} -> devices, which one hangs off which, and ready-made checks

A controller that cannot be reached, or a login that is refused, is Unknown, never Failed."""
import json, os, sys, threading
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
            CLIENTS[key] = U.Client(key[0], key[1], key[2], key[3], key[4], conn.get("timeout", 8))
        return CLIENTS[key]


def run_check(kind, params, conn):
    c = client(conn)
    if kind == "device":
        return C.check_device(params, c.get("stat/device"))
    if kind == "devices":
        return C.check_devices(params, c.get("stat/device"))
    if kind == "health":
        return C.check_health(params, c.get("stat/health"), c.get("stat/device") if str(params.get("subsystem")).lower() == "www" else None)
    if kind == "tunnel":
        return C.check_tunnel(params, c.get("rest/networkconf"), tunnel_status(c))
    return {"state": "unknown", "detail": f"unknown UniFi check '{kind}' (known: device, devices, health, tunnel)"}


def tunnel_status(c):
    """VPN connection status, or None when this controller does not report it (the tunnel then reads Unknown)."""
    try:
        return c.get("v2/vpn/connections")
    except U.UnifiError as e:
        if "does not report VPN tunnel status" in str(e):
            return None
        raise


def handle(req):
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
        return C.client_usage(client(a.get("connection") or {}).usage(sec), max(60, min(sec, 3600)))
    if m == "flows":
        sec = a.get("seconds") if isinstance(a.get("seconds"), int) else 300
        return C.flow_summary(client(a.get("connection") or {}).flows(sec), max(60, min(sec, 3600)))
    if m == "flows_look":
        return {"attempts": client(a.get("connection") or {}).look()}
    if m == "discover":
        c = client(a.get("connection") or {})
        return C.discover(c.get("stat/device"), c.get("stat/health"), c.get("rest/networkconf"), tunnel_status(c))
    raise ValueError(f"unknown method {m}")


def serve(req):
    try:
        out = {"id": req["id"], "result": handle(req)}
    except U.UnifiError as e:
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
