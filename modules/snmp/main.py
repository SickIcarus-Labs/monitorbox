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
import collections, json, os, sys, threading, time
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


PER_DEVICE = 4                     # calls running at once for one device
WAIT = 10.0                        # seconds a call may wait its turn for a device before it is answered "busy"
MAX_QUEUE = 300                    # calls waiting for one device; beyond this the answer is "busy" at once
_BUSY = "SNMP: that device is still busy with earlier requests (it is slow or not answering)"
_pools, _pending, _queued, _lock = {}, {}, collections.deque(), threading.Lock()
_general = ThreadPoolExecutor(max_workers=8)      # calls that name no device (probe, discover): the old shared pool


def _device(req):
    c = (req.get("params") or {}).get("connection") or {}
    return (str(c.get("host") or ""), c.get("port", 161)) if c.get("host") else None


class _Job:
    """One call waiting for, or running on, its device. state: 0 waiting, 1 running, 2 already answered busy."""
    __slots__ = ("req", "dev", "deadline", "lock", "state")

    def __init__(self, req, dev):
        self.req, self.dev, self.deadline, self.lock, self.state = req, dev, time.monotonic() + WAIT, threading.Lock(), 0


def _reply_busy(req):
    out = {"id": req["id"], "result": {"state": "unknown", "detail": _BUSY}} if req.get("method") == "check" else {"id": req["id"], "error": _BUSY}
    with OUT:
        print(json.dumps(out), flush=True)


def dispatch(req):
    """Each device gets its own four workers and calls wait their turn there (a device with forty checks used to have thirty-six of them refused every round).
    A device that does not answer only ever holds its own workers: a call that has waited WAIT seconds is answered "busy", so the others are never held up."""
    dev = _device(req)
    if dev is None:
        _general.submit(_serve, req)
        return
    with _lock:
        if _pending.get(dev, 0) >= MAX_QUEUE:
            job = None
        else:
            _pending[dev] = _pending.get(dev, 0) + 1
            job = _Job(req, dev)
            _queued.append(job)
            pool = _pools.get(dev) or _pools.setdefault(dev, ThreadPoolExecutor(max_workers=PER_DEVICE))
    if job is None:
        _reply_busy(req)
        return
    pool.submit(_run, job)


def _run(job):
    try:
        with job.lock:
            if job.state != 0:
                return                       # already answered "busy" while it waited
            job.state = 1
        _serve(job.req)
    finally:
        with _lock:
            _pending[job.dev] = max(0, _pending.get(job.dev, 1) - 1)
            if not _pending[job.dev]:
                _pending.pop(job.dev, None)


def reap():
    """Answer "busy" for every call that has waited too long (one thread, one look a half second)."""
    now = time.monotonic()
    while True:
        with _lock:
            if not _queued or _queued[0].deadline > now:
                return
            job = _queued.popleft()
        with job.lock:
            if job.state != 0:
                continue
            job.state = 2
        _reply_busy(job.req)


def _reaper():
    while True:
        time.sleep(0.5)
        try:
            reap()
        except Exception:
            pass


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
    threading.Thread(target=_reaper, daemon=True).start()
    for line in sys.stdin:
        try:
            req = json.loads(line)
            req["id"]
        except (ValueError, TypeError, KeyError):
            continue                       # one garbled line must not end the module (and so every check)
        dispatch(req)
