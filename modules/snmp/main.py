"""SNMP module. Watches things BY NAME and finds their current index at run time.

Why: MonitorBox 3 stored raw OIDs ending in a numeric index (…25.2.3.1.6.63). When a server's drive layout
changed, the indexes moved and monitoring read the wrong disk. Here a check says "volume /volume1" or
"interface eno3"; the module looks up which index that name has now, checks the name still matches on every
poll, and re-resolves the moment it does not.

Methods (JSON lines, see modules/hello):
  check    {"check": "uptime|resources|volume|interface|row", "params": {...}, "connection": {...}}
  sample   {"connection": {...}, "names": ["eth0", ...]} -> raw in/out octet counters per interface (the App makes rates)
  lan_report {"connection": {...}} -> ports with rates, errors, learned-address counts and LLDP neighbours (read-only; shortened addresses)
  counters {"connection": {...}} -> {"ports": {name: {"in", "out", "bits"}}} raw octet counters for every real interface, in a few column reads
  probe    {"connection": {...}} -> {"ok": true, "sysName": ...} or {"ok": false, "error": ...}: does this device answer with this login?
  discover {"connection": {...}}  ->  what the device offers right now (the Re-detect list)

A device that cannot be reached over SNMP (timeout, wrong login) is "unknown", never "failed"."""
import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snmplib as L  # noqa: E402
from checks import run_check, discover, sample, lan_report, probe, counters  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]

OUT = threading.Lock()


def handle(req):
    m, a = req.get("method"), req.get("params", {})
    if m == "hello":
        return {"module": "snmp", "version": VERSION}
    if m == "describe":
        return {"title": "SNMP", "text": "Watches devices over SNMP, by name", "status": "healthy"}
    if m == "check":
        return run_check(a.get("check"), a.get("params") or {}, a.get("connection") or {})
    if m == "sample":
        return sample(a.get("connection") or {}, list(a.get("names") or []))
    if m == "lan_report":
        return lan_report(a.get("connection") or {}, wait=float(a.get("wait", 1.0)), everything=bool(a.get("everything")))
    if m == "counters":
        return counters(a.get("connection") or {}, a.get("only") if isinstance(a.get("only"), list) else None)
    if m == "probe":
        return probe(a.get("connection") or {})
    if m == "discover":
        return discover(a.get("connection") or {}, a.get("params") or {})
    raise ValueError(f"unknown method {m}")


PER_DEVICE = 2                     # calls in flight at once for one device; a hung device must not take every worker from the others
_busy, _busy_lock = {}, threading.Lock()


def _device(req):
    c = (req.get("params") or {}).get("connection") or {}
    return (str(c.get("host") or ""), c.get("port", 161)) if c.get("host") else None


def _enter(dev):
    if dev is None:
        return True
    with _busy_lock:
        if _busy.get(dev, 0) >= PER_DEVICE:
            return False
        _busy[dev] = _busy.get(dev, 0) + 1
        return True


def _leave(dev):
    if dev is None:
        return
    with _busy_lock:
        _busy[dev] = max(0, _busy.get(dev, 1) - 1)
        if not _busy[dev]:
            _busy.pop(dev, None)


def serve(req):
    dev = _device(req)
    if not _enter(dev):                # answer at once instead of waiting for a worker behind a device that is not answering
        msg = "SNMP: that device is still busy with earlier requests (it is slow or not answering)"
        out = {"id": req["id"], "result": {"state": "unknown", "detail": msg}} if req.get("method") == "check" else {"id": req["id"], "error": msg}
        with OUT:
            print(json.dumps(out), flush=True)
        return
    try:
        _serve(req)
    finally:
        _leave(dev)


def _serve(req):
    try:
        out = {"id": req["id"], "result": handle(req)}
    except L.SnmpError as e:
        out = {"id": req["id"], "result": {"state": "unknown", "detail": f"SNMP: {e}"}} if req.get("method") == "check" \
            else {"id": req["id"], "error": f"SNMP: {e}"}
    except Exception as e:
        import traceback
        last = traceback.extract_tb(e.__traceback__)[-1]       # say where it broke, so a rare failure can be found from the dashboard alone
        out = {"id": req["id"], "error": f"{e} ({os.path.basename(last.filename)}:{last.lineno})"}
    with OUT:
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    pool = ThreadPoolExecutor(max_workers=8)   # one slow device must not hold up the others
    for line in sys.stdin:
        pool.submit(serve, json.loads(line))
