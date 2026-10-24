"""NUT module: UPS status from a NUT server (read-only; see nutlib.py).

  check    {"check": "ups", "params": {"ups": "name", "load_warn": 80, "charge_warn": 50, "runtime_warn_s": 300}, "connection": {host, port}}
  discover {"connection": {...}} -> the UPSes the server knows, as ready-made checks

A NUT server that cannot be reached = Unknown, never Failed. A UPS that reports low battery = Failed."""
import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nutlib as N  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]
OUT = threading.Lock()

STATUS_WORDS = {"OL": "online", "OB": "on battery", "LB": "low battery", "HB": "high battery", "RB": "replace battery",
                "CHRG": "charging", "DISCHRG": "discharging", "BYPASS": "on bypass", "CAL": "calibrating", "OFF": "off",
                "OVER": "overloaded", "TRIM": "trimming voltage", "BOOST": "boosting voltage", "FSD": "shutting down",
                "ALARM": "alarm"}
BAD = {"LB", "FSD", "OFF"}                      # failed
WARN = {"OB", "RB", "OVER", "BYPASS", "ALARM", "DISCHRG", "CAL"}   # degraded (still working, but look)


def client(conn):
    if not conn.get("host"):
        raise N.NutError("this connection has no 'host'")
    return N.Client(conn["host"], conn.get("port", 3493), conn.get("timeout", 3), conn.get("username"), conn.get("password"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mins(sec):
    return f"{sec / 60:.0f} min" if sec >= 120 else f"{sec:.0f} s"


def check_ups(params, conn):
    name = params.get("ups")
    c = client(conn)
    if not name:
        names = ", ".join(c.list_ups()) or "none"
        return {"state": "unknown", "detail": f"this check needs a 'ups' name (the server has: {names}). Use Re-detect."}
    try:
        v = c.list_vars(name)
    except N.StaleData as e:
        return {"state": "unknown", "detail": str(e)}
    except N.NutError as e:
        if "UNKNOWN-UPS" in str(e):
            return {"state": "unknown", "detail": f"the NUT server has no UPS called '{name}' (it has: {', '.join(c.list_ups()) or 'none'})"}
        raise
    tokens = (v.get("ups.status") or "").split()
    if not tokens:
        return {"state": "unknown", "detail": "the UPS did not report a status"}
    words = [STATUS_WORDS.get(t, t) for t in tokens]
    bits = [", ".join(words)]
    ch, load, rt = num(v.get("battery.charge")), num(v.get("ups.load")), num(v.get("battery.runtime"))
    if ch is not None:
        bits.append(f"battery {ch:.0f}%")
    if load is not None:
        bits.append(f"load {load:.0f}%")
    if rt is not None:
        bits.append(f"{mins(rt)} runtime")
    detail = " · ".join(bits)
    if BAD & set(tokens):
        return {"state": "failed", "detail": detail}
    problems = bool(WARN & set(tokens))
    problems |= ch is not None and ch < params.get("charge_warn", 50) and "CHRG" not in tokens
    problems |= load is not None and load >= params.get("load_warn", 80)
    problems |= rt is not None and rt < params.get("runtime_warn_s", 300)
    return {"state": "degraded" if problems else "healthy", "detail": detail}


def discover(conn):
    c = client(conn)
    ups = c.list_ups()
    sug = []
    for name, desc in sorted(ups.items()):
        sug.append({"label": f"UPS {name}" + (f" ({desc})" if desc and desc != "Description unavailable" else ""),
                    "check": "ups", "params": {"ups": name}, "node": f"UPS {name}", "group": "Power", "batch": "UPS"})
    return {"ups": [{"name": n, "description": d} for n, d in sorted(ups.items())], "suggest": sug}


def handle(req):
    m, a = req.get("method"), req.get("params", {})
    if m == "hello":
        return {"module": "nut", "version": VERSION}
    if m == "describe":
        return {"title": "UPS (NUT)", "text": "Reads UPS status from a NUT server, read-only", "status": "healthy"}
    if m == "check":
        if (a.get("check") or "ups") != "ups":
            return {"state": "unknown", "detail": f"unknown NUT check '{a.get('check')}' (known: ups)"}
        return check_ups(a.get("params") or {}, a.get("connection") or {})
    if m == "discover":
        return discover(a.get("connection") or {})
    if m == "clients":
        return {"clients": client(a.get("connection") or {}).list_clients(str(a.get("ups") or ""))}
    raise ValueError(f"unknown method {m}")


def serve(req):
    try:
        out = {"id": req["id"], "result": handle(req)}
    except N.NutError as e:
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
