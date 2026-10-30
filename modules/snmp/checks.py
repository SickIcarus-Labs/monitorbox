"""The checks themselves: resolve names to indexes, read values, judge them."""
import json, threading, time

import snmplib as L

# well-known objects (numeric on purpose: no MIB files needed at run time)
SYS_UPTIME, SYS_NAME = "1.3.6.1.2.1.1.3.0", "1.3.6.1.2.1.1.5.0"
IF_NAME, IF_DESCR, IF_OPER, IF_HIGHSPEED = "1.3.6.1.2.1.31.1.1.1.1", "1.3.6.1.2.1.2.2.1.2", "1.3.6.1.2.1.2.2.1.8", "1.3.6.1.2.1.31.1.1.1.15"
HR_TYPE, HR_DESCR, HR_UNITS, HR_SIZE, HR_USED = (f"1.3.6.1.2.1.25.2.3.1.{i}" for i in (2, 3, 4, 5, 6))
HR_FIXED_DISK = "1.3.6.1.2.1.25.2.1.4"
UCD_IDLE, UCD_MEM_TOTAL, UCD_MEM_AVAIL, UCD_MEM_BUF, UCD_MEM_CACHED = (
    "1.3.6.1.4.1.2021.11.11.0", "1.3.6.1.4.1.2021.4.5.0", "1.3.6.1.4.1.2021.4.6.0", "1.3.6.1.4.1.2021.4.14.0", "1.3.6.1.4.1.2021.4.15.0")
Q = "1.3.6.1.4.1.55062.2.10"   # QNAP QuTS / QTS storage MIB
PRESETS = {                      # named-row shortcuts: what to look the name up in, and where the status is
    "qnap-pool": {"batch": "Storage pools", "name_column": f"{Q}.7.1.2", "status_column": f"{Q}.7.1.5", "capacity_column": f"{Q}.7.1.3", "free_column": f"{Q}.7.1.4",
                  "ok": [0], "warn": [-1, -2], "bad": [-3, -5, -6], "what": "Storage pool"},
    "qnap-raid": {"batch": "RAID groups", "name_column": f"{Q}.5.1.3", "status_column": f"{Q}.5.1.4", "what": "RAID group"},
    "qnap-disk": {"batch": "Disks", "name_column": f"{Q}.2.1.5", "status_column": f"{Q}.2.1.7", "temp_column": f"{Q}.2.1.8", "what": "Disk (by serial number)"},
    "qnap-volume": {"batch": "Shared folders", "name_column": f"{Q}.9.1.2", "status_column": f"{Q}.9.1.5", "capacity_column": f"{Q}.9.1.3", "free_column": f"{Q}.9.1.4",
                    "what": "Volume / shared folder"},
}
OK_WORDS = {"good", "ready", "normal", "ok", "online", "healthy", "optimal", "active", "0"}
WARN_WORDS = {"warning", "degraded", "rebuilding", "resyncing", "syncing", "verifying", "scrubbing", "initializing"}
BAD_WORDS = {"error", "abnormal", "failed", "offline", "inactive", "critical", "faulty", "missing", "-1"}

_sessions, _index, _lock = {}, {}, threading.Lock()


def session(conn):
    """One Session per distinct connection settings (so editing a password makes a fresh one)."""
    if not conn.get("host"):
        raise L.SnmpError("this connection has no 'host'")
    key = json.dumps(conn, sort_keys=True)
    with _lock:
        s = _sessions.get(key)
        if not s:
            v = str(conn.get("version", "3"))
            s = _sessions[key] = L.Session(
                conn["host"], conn.get("port", 161), v, community=conn.get("community", "public"),
                user=conn.get("user"), auth=conn.get("auth"), auth_password=conn.get("authPassword"),
                priv=conn.get("priv"), priv_password=conn.get("privPassword"),
                timeout=conn.get("timeout", 2.0), retries=conn.get("retries", 1))
        return s


def ok(detail, **kw):
    return {"state": "healthy", "detail": detail, **kw}


def res(state, detail):
    return {"state": state, "detail": detail}


def size(n):
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def clean(v):
    return None if isinstance(v, L.NoSuch) else v


def by_name(sess, cid, name_col, name, extra_cols=(), refresh=False):
    """Find the row whose name is `name` and return (index, {column: value}).
    The index is remembered, but the name is read again on every call: if it moved, we search again."""
    want = name.strip().lower()
    key = (cid, name_col, want)
    idx = None if refresh else _index.get(key)
    if idx is not None:
        got = sess.get([f"{name_col}.{idx}"] + [f"{c}.{idx}" for c in extra_cols])
        nv = got.get(f"{name_col}.{idx}")
        if nv and L.text(nv).strip().lower() == want:
            return idx, {c: clean(got.get(f"{c}.{idx}")) for c in extra_cols}
        _index.pop(key, None)                       # moved or renamed: look again below
    names = sess.column(name_col)
    hits = [i for i, v in names.items() if L.text(v).strip().lower() == want]
    if not hits:
        raise _Missing(sorted({L.text(v) for v in names.values() if L.text(v)}))
    if len(hits) > 1:
        raise L.SnmpError(f"'{name}' matches {len(hits)} rows; use a more specific name")
    idx = hits[0]
    _index[key] = idx
    got = sess.get([f"{c}.{idx}" for c in extra_cols]) if extra_cols else {}
    return idx, {c: clean(got.get(f"{c}.{idx}")) for c in extra_cols}


class _Missing(Exception):
    def __init__(self, found):
        self.found = found


def not_found(what, name, found):
    shown = ", ".join(found[:8]) + (" …" if len(found) > 8 else "")
    return res("unknown", f"{what} '{name}' is not on the device any more" + (f" (it has: {shown})" if found else "") +
               ". Open the server, choose Pick what to watch, and pick the current name.")


# ---------------------------------------------------------------- checks ----
def uptime(sess, p, conn):
    r = sess.get([SYS_UPTIME, SYS_NAME])
    up = r.get(SYS_UPTIME)
    if not up and up != 0:
        return res("unknown", "the device answered but does not report its uptime")
    s = up // 100
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    name = L.text(r.get(SYS_NAME) or b"")
    return ok(f"{name + ': ' if name else ''}up {d}d {h}h {m}m")


def resources(sess, p, conn):
    r = sess.get([UCD_IDLE, UCD_MEM_TOTAL, UCD_MEM_AVAIL, UCD_MEM_BUF, UCD_MEM_CACHED])
    idle, tot, avail = r.get(UCD_IDLE), r.get(UCD_MEM_TOTAL), r.get(UCD_MEM_AVAIL)
    if not idle and idle != 0 or not tot:
        return res("unknown", "this device does not report CPU and memory over SNMP (net-snmp's UCD tables)")
    cpu = 100 - int(idle)
    free = int(avail or 0) + int(r.get(UCD_MEM_BUF) or 0) + int(r.get(UCD_MEM_CACHED) or 0)
    mem = 100 * (1 - min(free, int(tot)) / int(tot))
    detail = f"CPU {cpu}% busy, memory {mem:.0f}% used"
    cw, mw = p.get("cpu_warn", 90), p.get("mem_warn", 90)
    return ok(detail, notice=True) if cpu >= cw or mem >= mw else ok(detail)       # a busy server is doing its job: worth a line, not a problem


def volume(sess, p, conn):
    name = p.get("name")
    if not name:
        return res("unknown", "this check needs a 'name' (a volume name; open the server and choose Pick what to watch to see them)")
    try:
        idx, v = by_name(sess, conn.get("id"), HR_DESCR, name, (HR_UNITS, HR_SIZE, HR_USED))
    except _Missing as m:
        return not_found("Volume", name, m.found)
    units, total, used = (v[c] for c in (HR_UNITS, HR_SIZE, HR_USED))
    if not total or used is None or isinstance(total, L.NoSuch):
        return res("unknown", f"the device did not report the size of '{name}'")
    pct = 100 * int(used) / int(total)
    detail = f"{name}: {pct:.0f}% used ({size(int(used) * int(units))} of {size(int(total) * int(units))})"
    if pct >= p.get("fail", 95):
        return res("failed", detail)
    if pct >= p.get("warn", 85):
        return res("degraded", detail)
    return ok(detail, notice=True) if pct >= p.get("notice", 75) else ok(detail)     # filling up: worth a line before it is a problem


def interface(sess, p, conn):
    name = p.get("name")
    if not name:
        return res("unknown", "this check needs a 'name' (an interface name; open the server and choose Pick what to watch to see them)")
    try:
        idx, v = by_name(sess, conn.get("id"), IF_NAME, name, (IF_OPER, IF_HIGHSPEED))
    except _Missing as m:
        try:  # some devices only fill ifDescr
            idx, v = by_name(sess, conn.get("id"), IF_DESCR, name, (IF_OPER, IF_HIGHSPEED))
        except _Missing:
            return not_found("Interface", name, m.found)
    st, speed = v[IF_OPER], v[IF_HIGHSPEED]
    states = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "not present", 7: "lower layer down"}
    word = states.get(st if isinstance(st, int) else -1, f"state {st}")
    sp = f", {int(speed)} Mbit/s" if isinstance(speed, int) and speed else ""
    detail = f"{name} is {word}{sp}"
    if st == 1:
        mn = p.get("min_speed_mbps")
        return res("degraded", detail + f" (expected at least {mn})") if mn and isinstance(speed, int) and speed < mn else ok(detail)
    return res("failed", detail) if st in (2, 6, 7) else res("degraded", detail)


def row(sess, p, conn):
    """Any table row by name: preset or explicit columns; status judged by ok/warn/bad lists."""
    spec = dict(PRESETS.get(p.get("preset"), {}))
    if p.get("preset") and p["preset"] not in PRESETS:
        return res("unknown", f"unknown preset '{p['preset']}' (known: {', '.join(sorted(PRESETS))})")
    spec.update({k: v for k, v in p.items() if k not in ("preset",)})
    name = spec.get("name")
    if not spec.get("name_column") or not spec.get("status_column") or name in (None, ""):
        return res("unknown", "a row check needs 'name', 'name_column' and 'status_column' (or a 'preset')")
    cols = [spec["status_column"]] + [spec[k] for k in ("capacity_column", "free_column", "temp_column") if spec.get(k)]
    try:
        idx, v = by_name(sess, conn.get("id"), spec["name_column"], str(name), cols)
    except _Missing as m:
        return not_found(spec.get("what", "Row"), name, m.found)
    st = v[spec["status_column"]]
    if st is None or isinstance(st, L.NoSuch):
        return res("unknown", f"the device did not report a status for '{name}'")
    raw = L.text(st).lower() if isinstance(st, bytes) else st
    norm = lambda xs: {x.lower() if isinstance(x, str) else x for x in xs}
    okset = norm(spec.get("ok", [])) or OK_WORDS | {0}
    warnset = norm(spec.get("warn", [])) or WARN_WORDS
    badset = norm(spec.get("bad", [])) or BAD_WORDS
    parts = [f"{name}: status {L.text(st) if isinstance(st, bytes) else st}"]
    cap, free = v.get(spec.get("capacity_column")), v.get(spec.get("free_column"))
    pct = None
    if isinstance(cap, int) and isinstance(free, int) and cap > 0:
        pct = 100 * (cap - free) / cap
        parts.append(f"{pct:.0f}% used ({size(cap - free)} of {size(cap)})")
    temp = v.get(spec.get("temp_column"))
    if isinstance(temp, int):
        parts.append(f"{temp} °C")
    detail = ", ".join(parts)
    if raw in okset or str(raw) in okset:
        state = "healthy"
    elif raw in badset or str(raw) in badset:
        state = "failed"
    elif raw in warnset or str(raw) in warnset:
        state = "degraded"
    else:
        state, detail = "degraded", detail + " (unrecognised status; tell MonitorBox what it means with ok / warn / bad)"
    if state == "healthy" and pct is not None:
        if pct >= spec.get("fail", 95):
            state = "failed"
        elif pct >= spec.get("warn_used", spec.get("warn", 85) if isinstance(spec.get("warn"), (int, float)) else 85):
            state = "degraded"
    if state == "healthy" and isinstance(temp, int) and temp >= spec.get("temp_warn", 55):
        state = "degraded"
    return res(state, detail)


CHECKS = {"uptime": uptime, "resources": resources, "volume": volume, "interface": interface, "row": row}


def run_check(name, params, conn):
    fn = CHECKS.get(name or "uptime")
    if not fn:
        return res("unknown", f"unknown SNMP check '{name}' (known: {', '.join(CHECKS)})")
    t0 = time.monotonic()
    out = fn(session(conn), params, conn)
    out["ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


# ---------------------------------------------------------------- traffic counters ----
IF_HC_IN, IF_HC_OUT = "1.3.6.1.2.1.31.1.1.1.6", "1.3.6.1.2.1.31.1.1.1.10"      # 64-bit octet counters
IF_PKTS_IN = {"inU": "1.3.6.1.2.1.31.1.1.1.7", "inM": "1.3.6.1.2.1.31.1.1.1.8", "inB": "1.3.6.1.2.1.31.1.1.1.9"}        # 64-bit packet counters: unicast, multicast, broadcast
IF_PKTS_OUT = {"outU": "1.3.6.1.2.1.31.1.1.1.11", "outM": "1.3.6.1.2.1.31.1.1.1.12", "outB": "1.3.6.1.2.1.31.1.1.1.13"}
IF_IN_DISC, IF_IN_ERR, IF_OUT_DISC, IF_OUT_ERR = "1.3.6.1.2.1.2.2.1.13", "1.3.6.1.2.1.2.2.1.14", "1.3.6.1.2.1.2.2.1.19", "1.3.6.1.2.1.2.2.1.20"   # errors and discards, per direction
IF_IN, IF_OUT = "1.3.6.1.2.1.2.2.1.10", "1.3.6.1.2.1.2.2.1.16"                  # 32-bit ones, for devices without the 64-bit pair


def sample(conn, names):
    """Raw octet counters for the named interfaces, read together. The App turns two readings into a rate, so
    nothing is remembered here. {name: {"in": n, "out": n, "bits": 64|32}}, or {"error": why} for a name that is gone."""
    s = session(conn)
    out = {}
    for name in names:
        try:
            try:
                idx, _ = by_name(s, conn.get("id"), IF_NAME, name)
            except _Missing:
                idx, _ = by_name(s, conn.get("id"), IF_DESCR, name)
        except _Missing as m:
            out[name] = {"error": f"interface '{name}' is not on the device any more"}
            continue
        got = s.get([f"{IF_HC_IN}.{idx}", f"{IF_HC_OUT}.{idx}", f"{IF_IN}.{idx}", f"{IF_OUT}.{idx}", f"{IF_HIGHSPEED}.{idx}"])
        sp = clean(got.get(f"{IF_HIGHSPEED}.{idx}"))
        speed = {"speedMbps": int(sp)} if isinstance(sp, int) and sp > 0 else {}       # what the link is rated for: the top of the graph
        hi, ho = clean(got.get(f"{IF_HC_IN}.{idx}")), clean(got.get(f"{IF_HC_OUT}.{idx}"))
        if isinstance(hi, int) and isinstance(ho, int):
            out[name] = {"in": hi, "out": ho, "bits": 64, **speed}
            continue
        li, lo = clean(got.get(f"{IF_IN}.{idx}")), clean(got.get(f"{IF_OUT}.{idx}"))
        out[name] = {"in": li, "out": lo, "bits": 32, **speed} if isinstance(li, int) and isinstance(lo, int) else {"error": f"'{name}' does not report traffic counters"}
    return out


LAYOUT_FOR = 600            # seconds the list of real interfaces (names, speeds, descriptions) is trusted: it hardly ever changes
GET_AT_ONCE = 30            # object ids per request on the quick path
_layouts = {}               # connection settings -> {"at": time, "wide": bool, "ifs": {index: (name, speedMbps or None, label)}}


BIG_DEVICE = 64             # a device with more interfaces than this is checked for ones that are not really there (empty stack slots, tunnels)
NOT_PRESENT = 6             # ifOperStatus "notPresent": a slot with no port in it
NOT_LAN_TYPES = (24, 131, 135, 136)   # ifType: software loopback, tunnel, VLAN interface (layer 2 and 3): not ports on the LAN


def _absent(s, names, everything=False):
    """({index of an interface that is not a real port}, {index: ifOperStatus}, {index: ifType}). Only for a big device (hundreds of interfaces make every full read slow),
    and only on clear signals: the device says the port is not present, or says it is a tunnel, loopback or VLAN. A down port is never hidden (it is a real
    port with nothing plugged in), a link aggregation is never hidden, and a device that gives no type or state hides nothing. If that would hide
    everything, nothing is hidden."""
    if everything or len(names) <= BIG_DEVICE:
        return set(), {}, {}
    types, opers = _safe(s, IF_TYPE), _safe(s, IF_OPER)
    gone = {i for i in names if clean(opers.get(i)) == NOT_PRESENT or clean(types.get(i)) in NOT_LAN_TYPES}
    return (gone if len(gone) < len(names) else set()), opers, types


def counters(conn, only=None):
    """Raw octet counters for every real interface. The App turns two readings into rates and keeps the history.
    {"ports": {name: {"in", "out", "bits", "speedMbps"?, "label"?, "rxErr"?, "txErr"?, "rxDrop"?, "txDrop"?}}} (the last four are the interface's
    error and discard counters, when the device has them); `label` is the port's description (on UniFi switches the same name UniFi uses, "Port 10").
    Virtual interfaces are left out. The first reading (and one every ten minutes) walks the tables to learn which interfaces are real; the readings
    in between ask only for those interfaces' counters (and, when `only` lists port names, only for those: a switch can have hundreds of port-channel and VLAN interfaces nobody watches), a few dozen objects per request, which is much faster on a server with hundreds of virtual ones."""
    s = session(conn)
    key = json.dumps(conn, sort_keys=True)
    lay = _layouts.get(key)
    try:
        ut = clean(s.get([SYS_UPTIME]).get(SYS_UPTIME))                 # the device's uptime: with each interface's last-change time it says how long ago a link went up or down
    except L.SnmpError:
        ut = None
    ut = ut if isinstance(ut, int) else None
    if lay and time.time() - lay["at"] < LAYOUT_FOR:
        try:
            out = _quick(s, lay, only, ut)
            if out is not None:
                return {"ports": out, "sysName": lay.get("sys", ""), "macs": lay.get("macs", []), **({"uptimeS": ut // 100} if ut is not None else {})}
        except L.SnmpError:
            pass                                                       # fall back to the full walk, which says what is wrong
        _layouts.pop(key, None)
    out, lay = _full(s, ut)
    if lay["ifs"]:
        lay["at"] = time.time()
        _layouts[key] = lay
    return {"ports": out, "sysName": lay.get("sys", ""), "macs": lay.get("macs", []), **({"uptimeS": ut // 100} if ut is not None else {})}


def _ago(uptime, changed):
    """Seconds since the link last changed, from the device's uptime and the interface's last-change time (both in hundredths of a second); None when either is missing."""
    return (uptime - changed) // 100 if isinstance(uptime, int) and isinstance(changed, int) and uptime >= changed else None


def _packets(v):
    """{"rxPkts", "txPkts"} (every packet, whatever its kind) when the device reported all six counters, else nothing."""
    ins, outs = [v.get(k) for k in IF_PKTS_IN], [v.get(k) for k in IF_PKTS_OUT]
    if all(isinstance(x, int) for x in ins + outs):
        return {"rxPkts": sum(ins), "txPkts": sum(outs)}
    return {}


def _row(a, b, wide, sp, lab, bad, oper=None, ago=None, stack=None):
    return {"in": a, "out": b, "bits": 64 if wide else 32, **({"up": oper == 1} if isinstance(oper, int) else {}), **({"speedMbps": int(sp)} if isinstance(sp, int) and sp > 0 else {}), **({"label": lab} if lab else {}),
            **({"changedAgo": ago} if isinstance(ago, int) else {}), **(stack or {}),
            **{k: v for k, v in bad.items() if isinstance(v, int)}}


def _get_many(s, oids):
    """{oid: value} for any number of objects, GET_AT_ONCE per request. A device that refuses a whole request because one object is missing (SNMP v1) is asked one by one."""
    got = {}
    for i in range(0, len(oids), GET_AT_ONCE):
        chunk = oids[i:i + GET_AT_ONCE]
        try:
            got.update(s.get(chunk))
        except L.SnmpError:
            for o in chunk:
                try:
                    got.update(s.get([o]))
                except L.SnmpError:
                    pass
    return got


def _get_by_index(s, oid, idxs):
    """{index: value} for one column, asking for just these interfaces. An object the device does not have is left out, as a walk would leave it."""
    got = _get_many(s, [f"{oid}.{i}" for i in idxs])
    return {i: v for i in idxs for v in [got.get(f"{oid}.{i}")] if v is not None and not isinstance(v, L.NoSuch)}


def _read(s, idxs, wide, alias=False, counters_only=False):
    """{index: {"in", "out", "speed", "oper", "rxErr", "txErr", "rxDrop", "txDrop"[, "alias"]}} for just these interfaces (counters_only: just "in" and "out")."""
    c_in, c_out = (IF_HC_IN, IF_HC_OUT) if wide else (IF_IN, IF_OUT)
    cols = [("in", c_in), ("out", c_out)]
    if not counters_only:
        cols += [("speed", IF_HIGHSPEED), ("oper", IF_OPER), ("changed", IF_LAST_CHANGE), ("rxErr", IF_IN_ERR), ("txErr", IF_OUT_ERR), ("rxDrop", IF_IN_DISC), ("txDrop", IF_OUT_DISC)]
        if wide:
            cols += list(IF_PKTS_IN.items()) + list(IF_PKTS_OUT.items())          # packets, so the App can judge drops as a share of the traffic (no 64-bit counters: none)
        if alias:
            cols.append(("alias", IF_ALIAS))
    got = _get_many(s, [f"{oid}.{idx}" for idx in idxs for _, oid in cols])
    return {idx: {name: clean(got.get(f"{oid}.{idx}")) for name, oid in cols} for idx in idxs}


def _quick(s, lay, only=None, ut=None):
    """The counters of the interfaces already known, by index. None when an interface no longer answers (the list changed: read it again)."""
    wide, out = lay["wide"], {}
    want = set(only) if only else None
    ifs = {i: t for i, t in lay["ifs"].items() if want is None or t[0] in want or t[2] in want} or lay["ifs"]       # nothing matched: read them all rather than nothing
    vals = _read(s, list(ifs), wide)
    for idx, (nm, _sp, lab) in ifs.items():
        v = vals[idx]
        if not isinstance(v["in"], int) or not isinstance(v["out"], int):
            return None
        out[nm] = _row(v["in"], v["out"], wide, v["speed"], lab, {**{k: v[k] for k in ("rxErr", "txErr", "rxDrop", "txDrop")}, **_packets(v)}, v["oper"], _ago(ut, v["changed"]), lay.get("stack", {}).get(idx))      # the speed is read each time: a link that negotiates down shows at once
    return out


def _stack(s, names, types=None):
    """Which interfaces sit on top of which, from the standard stack table: {index: {"stacked": True}} for a bond, team or VLAN (it has interfaces beneath it, so it only repeats them),
    and {index: {"bond": ["bond0"]}} for a physical card that is a member of a link aggregation. Empty when the device has no such table."""
    lower, higher = {}, {}
    try:
        for suffix in s.column(IF_STACK):
            hi, _, lo = suffix.partition(".")
            if hi.isdigit() and lo.isdigit() and hi != "0" and lo != "0":
                lower.setdefault(hi, set()).add(lo)
                higher.setdefault(lo, set()).add(hi)
    except L.SnmpError:
        return {}
    if types:
        types = {i: clean(v) for i, v in types.items()}             # already read to find the interfaces that are not ports
    else:
        try:
            types = {i: clean(v) for i, v in s.column(IF_TYPE).items()}
        except L.SnmpError:
            types = {}
    nm = lambda i: L.text(names.get(i) or b"")

    def is_lag(i):
        return types.get(i) == 161 or nm(i).lower().startswith(LAG_NAMES)
    out = {}
    for i in set(lower) | set(higher):
        row = {}
        if lower.get(i):
            row["stacked"] = True
        bonds = sorted(nm(h) for h in higher.get(i, ()) if len(lower.get(h, ())) >= 2 and is_lag(h) and nm(h))
        if bonds:
            row["bond"] = bonds[:3]
        if row:
            out[i] = row
    return out


def _full(s, ut=None):
    """The first reading: one walk of the interface names, then the counters of just the real interfaces by index (a server can have hundreds of container
    interfaces; walking every column across all of them is what made this slow)."""
    names = s.column(IF_NAME) or s.column(IF_DESCR)
    gone, _, types = _absent(s, names)
    real = {idx: L.text(n) for idx, n in names.items() if L.text(n) and not L.text(n).startswith(VIRTUAL_IF) and idx not in gone}
    out, ifs, wide = {}, {}, True
    for wide in (True, False):                                           # 64-bit counters first, then the 32-bit pair
        first = _read(s, list(real), wide, counters_only=True)
        have = [i for i, v in first.items() if isinstance(v["in"], int) and isinstance(v["out"], int)]
        if have:
            break
    vals = _read(s, have, wide, alias=True) if have else {}               # the rest only for interfaces that have counters at all (a switch can list hundreds that do not)
    stack = _stack(s, names, types) if have else {}
    for idx, nm in real.items():
        v = vals.get(idx)
        if not v or not isinstance(v["in"], int) or not isinstance(v["out"], int):
            continue
        lab = L.text(v["alias"] or b"")[:60]
        out[nm] = _row(v["in"], v["out"], wide, v["speed"], lab, {**{k: v[k] for k in ("rxErr", "txErr", "rxDrop", "txDrop")}, **_packets(v)}, v["oper"], _ago(ut, v["changed"]), stack.get(idx))
        ifs[idx] = (nm, v["speed"] if isinstance(v["speed"], int) else None, lab)
    try:
        sysname = L.text(s.get([SYS_NAME]).get(SYS_NAME) or b"")[:60]           # the device's own name: the App uses it to tell which UniFi device this connection is
    except L.SnmpError:
        sysname = ""
    try:
        macs = sorted({_mac_text(m) for m in (_get_by_index(s, IF_PHYS, [i for i in names if i not in gone]) if gone else s.column(IF_PHYS)).values() if isinstance(m, (bytes, bytearray)) and len(m) == 6 and any(m)})[:1000]     # every interface's address, shortened: the App matches them to a UniFi device's address
    except L.SnmpError:
        macs = []
    return out, {"wide": wide, "ifs": ifs, "sys": sysname, "macs": macs, "stack": stack}


# ---------------------------------------------------------------- Re-detect ----
VIRTUAL_IF = ("veth", "br-", "docker", "virbr", "lo", "tun", "tap")
SYSTEM_VOL = ("/mnt", "/tmp", "/var", "/new_root", "/samba", "/python", "/share/external", "/share/NFSv", "/boot", "/usr", "/opt", "/etc")
VIRTUAL_VOL = ("/run", "/dev", "/sys", "/proc", "/snap", "/boot/efi")


def discover(conn, params=None):
    """What this device offers right now, by name, so the owner can pick (or fix) what to watch.
    `suggest` is a ready-made list of checks the Settings page turns into one-tap Watch buttons."""
    s = session(conn)
    out = {"interfaces": [], "volumes": [], "tables": {}, "suggest": [{"label": "Reachable (uptime)", "check": "uptime", "params": {}, "batch": "Device"}]}
    out["sysName"] = L.text(s.get([SYS_NAME]).get(SYS_NAME) or b"")
    names = s.column(IF_NAME) or s.column(IF_DESCR)
    gone, opers, _ = _absent(s, names, bool((params or {}).get("everything")))
    oper = opers or s.column(IF_OPER)
    speed = s.column(IF_HIGHSPEED) if not gone else _get_by_index(s, IF_HIGHSPEED, [i for i in names if i not in gone])
    states = {1: "up", 2: "down"}
    out["hiddenInterfaces"] = len(gone)
    for i, n in sorted(names.items(), key=lambda kv: int(kv[0].split(".")[0])):
        nm = L.text(n)
        if nm.startswith(VIRTUAL_IF) or i in gone:
            continue          # virtual interfaces (containers, loopback) and slots with no port in them are noise
        out["interfaces"].append({"index": i, "name": nm, "status": states.get(oper.get(i), str(oper.get(i))), "speedMbps": speed.get(i)})
        out["suggest"].append({"label": f"Interface {nm}", "check": "interface", "params": {"name": nm}, "batch": "Network interfaces"})
    descr, units, total, used, typ = (s.column(c) for c in (HR_DESCR, HR_UNITS, HR_SIZE, HR_USED, HR_TYPE))
    for i, d in descr.items():
        nm = L.text(d)
        if typ.get(i) != HR_FIXED_DISK or not total.get(i) or nm.startswith(VIRTUAL_VOL):
            continue
        pct = round(100 * used.get(i, 0) / total[i]) if total.get(i) else None
        out["volumes"].append({"index": i, "name": nm, "usedPercent": pct, "size": size(total[i] * (units.get(i) or 1))})
        out["suggest"].append({"label": f"Volume {nm}", "check": "volume", "params": {"name": nm}, "batch": "Volumes",
                               "system": nm.startswith(SYSTEM_VOL) or "@" in nm or "/." in nm})   # shown only on request
    for pname, spec in PRESETS.items():
        try:
            names = s.column(spec["name_column"])
        except L.SnmpError:
            continue
        if names:
            status = s.column(spec["status_column"])
            rows = []
            for i, n in sorted(names.items()):
                st = status.get(i)
                st = L.text(st) if isinstance(st, bytes) else st
                rows.append({"index": i, "name": L.text(n), "status": st})
                out["suggest"].append({"label": f"{spec.get('what', pname)} {L.text(n)}", "check": "row",
                                       "params": {"preset": pname, "name": L.text(n)}, "batch": spec.get("batch", pname)})
            out["tables"][pname] = rows
    mem = s.get([UCD_MEM_TOTAL]).get(UCD_MEM_TOTAL)
    if mem is not None and not isinstance(mem, L.NoSuch):
        out["suggest"].insert(1, {"label": "CPU and memory", "check": "resources", "params": {}, "batch": "Device"})
    return out


# ---------------------------------------------------------------- LAN report (read-only look at a switch's ports, neighbours and learned addresses) ----
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"
IF_IN_ERR, IF_OUT_ERR, IF_IN_DISC, IF_OUT_DISC = (f"1.3.6.1.2.1.2.2.1.{i}" for i in (14, 20, 13, 19))
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
IF_LAST_CHANGE, IF_TYPE = "1.3.6.1.2.1.2.2.1.9", "1.3.6.1.2.1.2.2.1.3"   # when the link last went up or down (timeticks), and what kind of interface it is (161 = link aggregation)
IF_STACK = "1.3.6.1.2.1.31.1.2.1.3"                  # ifStackStatus, indexed higher.lower: which interfaces sit on top of which (a bond over its cards, a VLAN over a port)
LAG_NAMES = ("bond", "team", "po", "port-channel", "ae", "lag")
IF_PHYS = "1.3.6.1.2.1.2.2.1.6"                     # ifPhysAddress: the card's own address, so a server can be matched to the switch port it is plugged into
LLDP_REM = "1.0.8802.1.1.2.1.4.1.1"                 # lldpRemTable: .5 chassis id, .7 port id, .9 system name; index = time mark . local port . remote index
BASE_PORT_IF = "1.3.6.1.2.1.17.1.4.1.2"             # dot1dBasePortIfIndex: bridge port -> ifIndex
FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"                 # dot1dTpFdbPort: learned address -> bridge port
Q_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"           # dot1qTpFdbPort: the same, per VLAN


def _mac_text(b):
    """A 6-byte id as ..:dd:ee:ff (shortened, like the UniFi report); anything else as short printable text."""
    if isinstance(b, (bytes, bytearray)) and len(b) == 6:
        return "..:" + ":".join(f"{x:02x}" for x in b[3:])
    t = L.text(b) if b is not None else ""
    return "".join(ch for ch in t if ch.isprintable())[:40]


def probe(conn):
    """Does this device answer SNMP with this login? One quick read of its name; never raises, and never keeps a session
    (it is used to try one login on many addresses)."""
    if not conn.get("host"):
        return {"ok": False, "error": "no host"}
    try:
        v = str(conn.get("version", "3"))
        s = L.Session(conn["host"], conn.get("port", 161), v, community=conn.get("community", "public"), user=conn.get("user"), auth=conn.get("auth"),
                      auth_password=conn.get("authPassword"), priv=conn.get("priv"), priv_password=conn.get("privPassword"),
                      timeout=float(conn.get("timeout", 1.5)), retries=int(conn.get("retries", 0)))
        return {"ok": True, "sysName": L.text(s.get([SYS_NAME]).get(SYS_NAME) or b"")[:60]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def lan_report(conn, wait=1.0, everything=False):
    """What one device (usually a switch) reports about its ports: name, label, state, speed, traffic rate (two counter readings `wait` seconds apart),
    errors and discards, how many addresses it has learned behind each port, and the neighbour LLDP says is on the other end. Each part is optional:
    what the device does not offer is named in `notes`, not an error. No addresses are shown in full."""
    s = session(conn)
    notes = []
    sysr = s.get([SYS_NAME, SYS_DESCR])
    names = s.column(IF_NAME) or s.column(IF_DESCR)
    if not names:
        raise L.SnmpError("the device lists no interfaces")
    gone, opers, _ = _absent(s, names, everything)
    keep = [i for i in names if i not in gone]
    if gone:
        notes.append(f"{len(gone)} interfaces that are not present, or are tunnels or VLANs, were not read")

    def col(oid, safe=True):
        """One column. On a big device with empty slots, just the interfaces that are really there (asked by index) instead of the whole table."""
        if gone:
            return _get_by_index(s, oid, keep)
        return _safe(s, oid) if safe else s.column(oid)
    oper, speed, alias, phys = opers or s.column(IF_OPER), col(IF_HIGHSPEED, False), col(IF_ALIAS), col(IF_PHYS)
    errs = {k: col(c) for k, c in (("inErrors", IF_IN_ERR), ("outErrors", IF_OUT_ERR), ("inDiscards", IF_IN_DISC), ("outDiscards", IF_OUT_DISC))}

    def counters():
        return {k: col(c, False) for k, c in (("in", IF_HC_IN), ("out", IF_HC_OUT))}
    c1 = counters(); t1 = time.time()
    if wait > 0:
        time.sleep(wait)
        c2 = counters()
    else:
        c2 = c1                                                         # no second reading: the caller only wants the layout
    dt = max(time.time() - t1, 0.001)
    if not c1["in"]:
        notes.append("no 64-bit traffic counters, so no rates")
    learned, lldp = {}, {}
    try:
        bp = {k: int(v) for k, v in s.column(BASE_PORT_IF).items() if isinstance(v, int)}
        rows = s.column(Q_FDB_PORT) or s.column(FDB_PORT)
        for _, port in rows.items():
            idx = bp.get(str(port), port if isinstance(port, int) else None)
            if idx is not None:
                learned[str(idx)] = learned.get(str(idx), 0) + 1
        if not rows:
            notes.append("no learned-address table (bridge MIB)")
    except L.SnmpError as e:
        notes.append(f"learned addresses: {e}")
    try:
        for suffix, v in s.column(f"{LLDP_REM}.9").items():            # system name of the neighbour
            lldp.setdefault(suffix.split(".")[1], {})["name"] = L.text(v)[:60]
        for suffix, v in s.column(f"{LLDP_REM}.5").items():
            lldp.setdefault(suffix.split(".")[1], {})["chassis"] = _mac_text(v)
        for suffix, v in s.column(f"{LLDP_REM}.7").items():
            lldp.setdefault(suffix.split(".")[1], {})["port"] = _mac_text(v)
        if not lldp:
            notes.append("no LLDP neighbours (off, or not supported)")
    except (L.SnmpError, IndexError) as e:
        notes.append(f"LLDP: {e}")
    ports, down, virtual = [], 0, 0
    for idx, nm in sorted(names.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        if idx in gone:
            continue                                                   # not a port: counted in hiddenPorts, never read
        if L.text(nm).startswith(VIRTUAL_IF):
            virtual += 1                                               # container and tunnel interfaces are not the LAN
            continue
        if clean(oper.get(idx)) == 2:
            down += 1                                                  # a port with nothing on it is counted, not listed
            continue
        row = {"ifIndex": idx, "name": L.text(nm), "state": {1: "up", 2: "down"}.get(clean(oper.get(idx)), "other")}
        mac = phys.get(idx)
        if isinstance(mac, (bytes, bytearray)) and len(mac) == 6 and any(mac):
            row["mac"] = _mac_text(mac)
        if alias.get(idx):
            row["label"] = L.text(alias[idx])[:60]
        sp = clean(speed.get(idx))
        if isinstance(sp, int) and sp > 0:
            row["speedMbps"] = sp
        for k, key in (("inBps", "in"), ("outBps", "out")):
            a, b = clean(c1[key].get(idx)), clean(c2[key].get(idx))
            if wait > 0 and isinstance(a, int) and isinstance(b, int) and b >= a:
                row[k] = int((b - a) * 8 / dt)
        for k, col in errs.items():
            v = clean(col.get(idx))
            if isinstance(v, int) and v:
                row[k] = v
        if idx in learned:
            row["learned"] = learned[idx]
        if idx in lldp:
            row["lldp"] = lldp[idx]
        ports.append(row)
    return {"sysName": L.text(sysr.get(SYS_NAME) or b""), "sysDescr": L.text(sysr.get(SYS_DESCR) or b"")[:120], "ports": ports, "downPorts": down, "virtualPorts": virtual, "hiddenPorts": len(gone), "notes": notes}


def _safe(sess, col):
    try:
        return sess.column(col)
    except L.SnmpError:
        return {}
