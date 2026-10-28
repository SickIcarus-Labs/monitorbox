"""UniFi Protect module: camera health, recording and recorder storage (read-only; see protectlib.py).

  check    {"check": "camera",  "params": {"name": "Driveway"}}      one camera
           {"check": "cameras", "params": {"names": [...]}}          every camera (or just those named)
           {"check": "nvr",     "params": {}}                        the recorder itself
           {"check": "storage", "params": {}}                        recording space and disk health
           {"check": "drive",   "params": {"slot": 1, "max_c": 55}}  one recording drive: temperature and health
           connection: {host or base_url, username, password, verify_tls (default false)}
  cameras  {"connection": {...}} -> the source-neutral camera list (id, name, model, state, detail, recording, lastSeen, motion, source, snapshot)
  snapshot {"connection": {...}, "id": "<camera id>"} -> {"mime": "image/jpeg", "data": "<base64>"}
  discover {"connection": {...}} -> cameras and ready-made checks

A console that cannot be reached, or a login that is refused, is Unknown, never Failed."""
import base64, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protectlib as P  # noqa: E402
import protectchecks as C  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]
OUT = threading.Lock()
CLIENTS, CLIENTS_LOCK = {}, threading.Lock()
CHECKS = {"camera": C.check_camera, "cameras": C.check_cameras, "nvr": C.check_nvr, "storage": C.check_storage, "drive": C.check_drive}


def client(conn):
    """One client per console login, kept for the life of the module so the session (and the login back-off) is shared by every check."""
    key = (conn.get("base_url") or conn.get("host"), conn.get("username"), conn.get("password"), bool(conn.get("verify_tls")))
    with CLIENTS_LOCK:
        if key not in CLIENTS:
            CLIENTS[key] = P.Client(key[0], key[1], key[2], key[3], conn.get("timeout", 8))
        return CLIENTS[key]


def run_check(kind, params, conn):
    fn = CHECKS.get(kind)
    if not fn:
        return {"state": "unknown", "detail": f"unknown UniFi Protect check '{kind}' (known: {', '.join(CHECKS)})"}
    try:
        c = client(conn)
        return fn(params, {"nvr": c.nvr()} if kind == "drive" else c.bootstrap())
    except P.ProtectError as e:
        return {"state": "unknown", "detail": str(e)}          # the console could not be asked: Unknown, never Failed


def handle(req):
    m, a = req.get("method"), req.get("params", {})
    if m == "hello":
        return {"module": "unifi-protect", "version": VERSION}
    if m == "describe":
        return {"title": "UniFi Protect", "text": "Reads camera health, recording and storage from UniFi Protect, read-only", "status": "healthy"}
    if m == "check":
        return run_check(a.get("check") or "cameras", a.get("params") or {}, a.get("connection") or {})
    if m == "cameras":
        return {"cameras": C.camera_list(client(a.get("connection") or {}).bootstrap())}
    if m == "snapshot":
        ctype, raw = client(a.get("connection") or {}).snapshot(a.get("id"))
        return {"mime": ctype, "data": base64.b64encode(raw).decode()}
    if m == "discover":
        c = client(a.get("connection") or {})
        try:
            nvr = c.nvr()
        except P.ProtectError:
            nvr = None                      # drives are only offered when the console shows them; cameras are found regardless
        return C.discover(c.bootstrap(), nvr=nvr)
    raise ValueError(f"unknown method {m}")


def serve(req):
    try:
        out = {"id": req["id"], "result": handle(req)}
    except P.ProtectError as e:
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
