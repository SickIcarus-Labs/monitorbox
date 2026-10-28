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
        return lan_report(a.get("connection") or {}, wait=float(a.get("wait", 1.0)))
    if m == "counters":
        return counters(a.get("connection") or {}, a.get("only") if isinstance(a.get("only"), list) else None)
    if m == "probe":
        return probe(a.get("connection") or {})
    if m == "discover":
        return discover(a.get("connection") or {}, a.get("params") or {})
    raise ValueError(f"unknown method {m}")


def serve(req):
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
