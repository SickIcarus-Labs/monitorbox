#!/usr/bin/env python3
"""SNMP speed test for one device (read-only): where does the time go when MonitorBox reads a slow switch?

It uses MonitorBox's own SNMP code (modules/snmp/snmplib.py), so what it measures is what the box does. It only sends GET and GETBULK
requests, in short bursts, for about two minutes in all. Nothing is written to the device, and nothing secret is printed.

Run it from a machine on the same network as the device (it needs Python 3 only):

    export SNMP_HOST=192.0.2.10 SNMP_VERSION=3 SNMP_USER=... SNMP_AUTH=sha SNMP_AUTH_PW=... SNMP_PRIV=aes SNMP_PRIV_PW=...
    python3 snmp_bench.py            (for SNMP v2c: SNMP_VERSION=2c SNMP_COMMUNITY=...)

Tests (each says what it tells you):
  1 latency       30 single reads of the device's uptime: is each request slow, or do some get lost (and retried)?
  2 walk          the interface-name table with 10, 25, 40 and 80 rows per request: is the time per request or per row?
  3 batch         reading N counters in one request (1, 12, 24, 48, 96): does a bigger request cost more?
  4 tables        the address and neighbour tables the LAN report reads: rows, requests, time
  5 overlap       a light read every half second while a heavy walk runs, on ONE shared session (what the box does) and on a SEPARATE
                  session: if the light reads are slow only when they share, calls are queueing behind each other; if both are slow the
                  device is the bottleneck
  6 cpu           how much of a request is this computer working (SNMP v3 encryption is done in Python) instead of waiting for the device
  8 what          what the interfaces are: how many of each type and state, with a few names of each (no addresses)
  7 functions     MonitorBox's own readings, run exactly as the box runs them: the first counters reading (walks the layout), the next
                  one (just the counters), the LAN report and Re-detect: how long each takes and how many requests it makes

Options: --only 1,2   run only these tests;   --seconds 20   length of the overlap test (default 20)
"""
import argparse, os, statistics, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.environ.get("SNMP_REF")                                       # a branch or commit to measure (default: main); always fetched fresh
if REF and not os.path.exists(os.path.join(HERE, "..", "modules", "snmp", "snmplib.py")):
    for name in ("snmplib.py", "checks.py"):
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/SickIcarus-Labs/monitorbox/{REF}/modules/snmp/{name}", timeout=20) as r, open(os.path.join(HERE, name), "wb") as f:
            f.write(r.read())
for cand in (os.path.join(HERE, "..", "modules", "snmp"), HERE):
    if os.path.exists(os.path.join(cand, "snmplib.py")):
        sys.path.insert(0, cand)
        break
else:                                                                   # run on its own: fetch the library it measures
    for name in ("snmplib.py", "checks.py"):
        url = "https://raw.githubusercontent.com/SickIcarus-Labs/monitorbox/main/modules/snmp/" + name
        with urllib.request.urlopen(url, timeout=20) as r, open(os.path.join(HERE, name), "wb") as f:
            f.write(r.read())
    sys.path.insert(0, HERE)
import snmplib as L  # noqa: E402
try:
    import checks as C  # noqa: E402
except Exception:       # run on its own with only snmplib.py beside it (an earlier run fetched that): fetch the other file the same way
    try:
        url = "https://raw.githubusercontent.com/SickIcarus-Labs/monitorbox/main/modules/snmp/checks.py"
        with urllib.request.urlopen(url, timeout=20) as r, open(os.path.join(HERE, "checks.py"), "wb") as f:
            f.write(r.read())
        import checks as C  # noqa: E402
    except Exception:
        C = None

UPTIME = "1.3.6.1.2.1.1.3.0"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_HC_IN = "1.3.6.1.2.1.31.1.1.1.6"
FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"
LLDP_REM = "1.0.8802.1.1.2.1.4.1.1"


class Meter:
    """Wraps one Session's requests: wall time, CPU time (this thread), and requests that took as long as a timeout (probably retried)."""
    def __init__(self, s):
        self.s, self.rec, self.lock = s, [], threading.Lock()
        real = s._exchange

        def timed(payload, rid):
            w0, c0 = time.perf_counter(), time.thread_time()
            try:
                return real(payload, rid)
            finally:
                w, c = time.perf_counter() - w0, time.thread_time() - c0
                with self.lock:
                    self.rec.append((w, c))
        s._exchange = timed

    def mark(self):
        return len(self.rec)

    def since(self, m):
        with self.lock:
            return list(self.rec[m:])


def session(timeout=2.0, retries=1):
    e = os.environ
    if not e.get("SNMP_HOST"):
        sys.exit("Set SNMP_HOST (and the login: see the top of this file).")
    v = e.get("SNMP_VERSION", "3")
    return L.Session(e["SNMP_HOST"], int(e.get("SNMP_PORT", 161)), v, community=e.get("SNMP_COMMUNITY", "public"), user=e.get("SNMP_USER"),
                     auth=e.get("SNMP_AUTH"), auth_password=e.get("SNMP_AUTH_PW"), priv=e.get("SNMP_PRIV"), priv_password=e.get("SNMP_PRIV_PW"),
                     timeout=timeout, retries=retries)


def pct(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(len(v) * p))] if v else float("nan")


def ms(x):
    return f"{x * 1000:7.0f}"


def line(label, walls, extra=""):
    if not walls:
        print(f"  {label:<34} (no answers) {extra}")
        return
    print(f"  {label:<34} n={len(walls):<3} min{ms(min(walls))}  median{ms(statistics.median(walls))}  p95{ms(pct(walls, .95))}  max{ms(max(walls))} ms {extra}")


def t_latency(s, m):
    print("1 latency: 30 single reads of the uptime, 0.2 s apart")
    walls, fails, mk = [], 0, m.mark()
    for _ in range(30):
        t0 = time.perf_counter()
        try:
            s.get([UPTIME])
            walls.append(time.perf_counter() - t0)
        except L.SnmpError:
            fails += 1
        time.sleep(0.2)
    line("one read", walls, f"failed={fails}")
    slow = sum(1 for w, _ in m.since(mk) if w >= 1.9)
    print(f"  requests that took about a timeout (2 s), so were probably lost and retried: {slow}")


def t_walk(s, m):
    print("2 walk: interface names, different rows per request")
    for rows in (10, 25, 40, 80):
        L.BULK_ROWS, mk, t0 = rows, m.mark(), time.perf_counter()
        try:
            got = s.walk(IF_NAME)
        except L.SnmpError as e:
            print(f"  {rows:>3} rows per request: failed ({e})")
            continue
        total, recs = time.perf_counter() - t0, m.since(mk)
        per = statistics.median([w for w, _ in recs]) if recs else 0
        print(f"  {rows:>3} rows per request: {len(got):>4} rows in {len(recs):>3} requests, {total:6.2f} s total, median request{ms(per)} ms, {total / max(1, len(got)) * 1000:5.1f} ms per row")
        time.sleep(1)
    L.BULK_ROWS = 40
    return s.walk(IF_NAME)


def t_batch(s, m, names):
    print("3 batch: counters read N at a time (one request each)")
    idx = [o.rsplit(".", 1)[1] for o, _ in names][:96]
    if not idx:
        print("  (no interfaces found)")
        return
    for n in (1, 12, 24, 48, 96):
        if n > len(idx):
            break
        walls = []
        for _ in range(5):
            t0 = time.perf_counter()
            try:
                s.get([f"{IF_HC_IN}.{i}" for i in idx[:n]])
                walls.append(time.perf_counter() - t0)
            except L.SnmpError as e:
                print(f"  {n:>3} at a time: failed ({e})")
                break
            time.sleep(0.3)
        line(f"{n} counters in one request", walls)


def t_tables(s, m):
    print("4 tables: what the LAN report reads")
    for label, base in (("learned addresses (bridge FDB)", FDB_PORT), ("neighbours (LLDP)", LLDP_REM)):
        mk, t0 = m.mark(), time.perf_counter()
        try:
            got = s.walk(base)
        except L.SnmpError as e:
            print(f"  {label:<32} failed ({e})")
            continue
        print(f"  {label:<32} {len(got):>5} rows in {len(m.since(mk)):>3} requests, {time.perf_counter() - t0:6.2f} s")
        time.sleep(1)


def heavy(s, stop, done):
    while not stop.is_set():
        try:
            s.walk(IF_NAME)
            s.walk(FDB_PORT)
        except L.SnmpError:
            pass
        done.append(time.monotonic())


def t_overlap(seconds):
    print(f"5 overlap: a light read every 0.5 s for {seconds} s while a heavy walk runs")
    for label, shared in (("shared session (what the box does)", True), ("separate session for the light reads", False)):
        a = session()
        b = a if shared else session()
        ma, mb = Meter(a), (None if shared else Meter(b))
        try:
            a.get([UPTIME])
            if not shared:
                b.get([UPTIME])
        except L.SnmpError as e:
            print(f"  {label}: cannot start ({e})")
            continue
        stop, done = threading.Event(), []
        th = threading.Thread(target=heavy, args=(a, stop, done), daemon=True)
        th.start()
        walls, fails, end = [], 0, time.monotonic() + seconds
        while time.monotonic() < end:
            t0 = time.perf_counter()
            try:
                b.get([UPTIME])
                walls.append(time.perf_counter() - t0)
            except L.SnmpError:
                fails += 1
            time.sleep(0.5)
        stop.set()
        th.join(timeout=60)
        line(label, walls, f"failed={fails}  heavy walks finished={len(done)}")
        time.sleep(2)


def t_cpu(s, m):
    print("6 cpu: this computer's work per request (everything above, summed)")
    recs = m.since(0)
    if not recs:
        return
    w, c = sum(x for x, _ in recs), sum(x for _, x in recs)
    print(f"  {len(recs)} requests: {w:.1f} s on the wire and waiting, {c:.1f} s of this computer's own work ({c / len(recs) * 1000:.1f} ms per request, {c / max(w, 1e-9) * 100:.0f}% of the time)")


def t_functions():
    print("7 functions: MonitorBox's own readings, run as the box runs them (a fresh session, nothing remembered)")
    if C is None:
        print("  (checks.py not available)")
        return
    e = os.environ
    conn = {"host": e["SNMP_HOST"], "port": int(e.get("SNMP_PORT", 161)), "version": e.get("SNMP_VERSION", "3"), "community": e.get("SNMP_COMMUNITY", "public"),
            "user": e.get("SNMP_USER"), "auth": e.get("SNMP_AUTH"), "authPassword": e.get("SNMP_AUTH_PW"), "priv": e.get("SNMP_PRIV"), "privPassword": e.get("SNMP_PRIV_PW")}
    s = C.session(conn)
    m = Meter(s)
    for label, fn in (("counters, first reading (learns the layout)", lambda: C.counters(conn)),
                      ("counters, next reading", lambda: C.counters(conn)),
                      ("LAN report (no second reading)", lambda: C.lan_report(conn, wait=0)),
                      ("Re-detect (discover)", lambda: C.discover(conn, {}))):
        mk, t0 = m.mark(), time.perf_counter()
        try:
            r = fn()
            note = ""
            if isinstance(r, dict) and "ports" in r:
                note = f"{len(r['ports'])} ports"
        except Exception as err:
            note = f"failed: {err}"
        recs = m.since(mk)
        print(f"  {label:<44} {time.perf_counter() - t0:6.2f} s   {len(recs):>4} requests   {note}")
        time.sleep(1)


IF_TYPE, IF_OPER = "1.3.6.1.2.1.2.2.1.3", "1.3.6.1.2.1.2.2.1.8"
TYPES = {6: "ethernet", 24: "loopback", 53: "virtual", 135: "vlan", 136: "vlan-sub", 161: "link-aggregate", 117: "gigabit-eth", 131: "tunnel", 142: "ip-forward", 150: "mpls", 209: "bridge", 53 + 1000: ""}


def t_what(s):
    print("8 what: the device's interfaces, by type and state")
    try:
        names = {o.rsplit(".", 1)[1]: L.text(v) for o, v in s.walk(IF_NAME)}
        types = {o.rsplit(".", 1)[1]: v for o, v in s.walk(IF_TYPE)}
        oper = {o.rsplit(".", 1)[1]: v for o, v in s.walk(IF_OPER)}
    except L.SnmpError as e:
        print(f"  failed ({e})")
        return
    groups = {}
    for idx, nm in names.items():
        t = types.get(idx)
        o = oper.get(idx)
        key = (TYPES.get(t, f"type {t}"), "up" if o == 1 else "down" if o == 2 else f"state {o}")      # the raw number: 3 testing, 4 unknown, 5 dormant, 6 notPresent, 7 lowerLayerDown
        groups.setdefault(key, []).append(nm)
    print(f"  {len(names)} interfaces")
    for (t, st), lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(lst):>4}  {t:<15} {st:<6} e.g. {', '.join(lst[:4])}")


def main():
    ap = argparse.ArgumentParser(description="SNMP speed test (read-only)")
    ap.add_argument("--only", default="1,2,3,4,6,8,7,5")
    ap.add_argument("--seconds", type=int, default=20)
    a = ap.parse_args()
    want = {x.strip() for x in a.only.split(",")}
    e = os.environ
    print(f"device {e.get('SNMP_HOST')}  SNMP {e.get('SNMP_VERSION', '3')}  {time.strftime('%Y-%m-%d %H:%M:%S')}  python {sys.version.split()[0]}")
    s = session()
    m = Meter(s)
    try:
        t0 = time.perf_counter()
        s.get([UPTIME])
        print(f"first read (includes SNMPv3 setup): {(time.perf_counter() - t0) * 1000:.0f} ms")
    except L.SnmpError as err:
        sys.exit(f"The device did not answer: {err}")
    names = []
    if "1" in want:
        t_latency(s, m)
    if "2" in want or "3" in want:
        names = t_walk(s, m) if "2" in want else s.walk(IF_NAME)
    if "3" in want:
        t_batch(s, m, names)
    if "4" in want:
        t_tables(s, m)
    if "6" in want:
        t_cpu(s, m)
    if "8" in want:
        t_what(s)
    if "7" in want:
        t_functions()
    if "5" in want:
        t_overlap(a.seconds)
    print("done")


if __name__ == "__main__":
    main()
