"""What the Protect picture means: one camera, all cameras, the recorder, its storage, and the source-neutral camera list
the App shows on the Cameras card. Pure functions of the bootstrap document, so they are easy to test."""
import time

REC_WORDS = {"always": "records all the time", "detections": "records on motion", "schedule": "records on a schedule", "never": "recording is off"}


def ago(ms, now=None):
    if not ms:
        return None
    s = max(0, int(((now or time.time() * 1000) - ms) // 1000))
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{s // 60} min ago"
    if s < 172800:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1000 or unit == "PB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000


def cam_name(c):
    return str(c.get("name") or c.get("marketName") or c.get("id") or "camera")


def find(cameras, name=None, cid=None):
    if cid:
        hit = next((c for c in cameras if c.get("id") == cid), None)
        if hit:
            return hit
    n = str(name or "").strip().lower()
    return next((c for c in cameras if cam_name(c).lower() == n), None) if n else None


def camera_state(c, now=None):
    """(state, detail) for one camera. A camera that cannot be reached is Failed (the console itself said so);
    one that is starting, updating or not recording when it should is Degraded."""
    mode = (c.get("recordingSettings") or {}).get("mode")
    bits = [c.get("marketName") or c.get("type")] if (c.get("marketName") or c.get("type")) else []
    state = str(c.get("state") or "").upper()
    connected = c.get("isConnected")
    if connected is None:
        connected = state == "CONNECTED"
    seen = ago(c.get("lastSeen"), now)
    if c.get("isAdopting"):
        return "degraded", " · ".join(bits + ["being adopted"])
    if c.get("isUpdating"):
        return "degraded", " · ".join(bits + ["updating its firmware"])
    if state == "CONNECTING":
        return "degraded", " · ".join(bits + ["connecting"])
    if not connected or state == "DISCONNECTED":
        return "failed", " · ".join(bits + ["offline" + (f", last seen {seen}" if seen else "")])
    if mode == "always" and c.get("isRecording") is False:
        return "degraded", " · ".join(bits + ["connected but not recording (it should record all the time)"])
    if c.get("isRecording"):
        bits.append("recording")
    elif mode in REC_WORDS:
        bits.append(REC_WORDS[mode])
    if c.get("isMotionDetected"):
        bits.append("motion now")
    if c.get("isThirdPartyCamera") and not bits:
        bits.append("third-party camera")
    return "healthy", " · ".join(bits + ["connected"])


def check_camera(params, boot, now=None):
    cams = boot.get("cameras") or []
    if not (params.get("name") or params.get("id")):
        return {"state": "unknown", "detail": "this check needs a camera 'name'. Open the server and choose Pick what to watch."}
    c = find(cams, params.get("name"), params.get("id"))
    if not c:
        names = ", ".join(sorted(cam_name(x) for x in cams)) or "none"
        return {"state": "unknown", "detail": f"UniFi Protect has no camera called '{params.get('name')}' any more (it has: {names}). Open the server and choose Pick what to watch."}
    st, detail = camera_state(c, now)
    return {"state": st, "detail": detail}


def check_cameras(params, boot, now=None):
    cams = [c for c in boot.get("cameras") or [] if not c.get("isDeleting")]
    names = {str(n).lower() for n in params.get("names") or []}
    if names:
        cams = [c for c in cams if cam_name(c).lower() in names]
    if not cams:
        return {"state": "unknown", "detail": "UniFi Protect reports no cameras"}
    rows = [(c, *camera_state(c, now)) for c in cams]
    good = sum(1 for _c, st, _d in rows if st == "healthy")
    bad = [cam_name(c) for c, st, _d in rows if st == "failed"]
    shaky = [cam_name(c) for c, st, _d in rows if st == "degraded"]
    detail = f"{good} of {len(rows)} cameras fine"
    if bad:
        detail += " · offline: " + ", ".join(bad)
    if shaky:
        detail += " · needs a look: " + ", ".join(shaky)
    return {"state": "failed" if bad else "degraded" if shaky else "healthy", "detail": detail}


def disks(nvr):
    return ((nvr.get("systemInfo") or {}).get("storage") or {}).get("devices") or []


def check_nvr(params, boot, now=None):
    nvr = boot.get("nvr") or {}
    if not nvr:
        return {"state": "unknown", "detail": "UniFi Protect did not describe its recorder"}
    bits = [nvr.get("name") or "Protect recorder"]
    if nvr.get("version"):
        bits.append(f"Protect {nvr['version']}")
    up = nvr.get("uptime")
    if isinstance(up, (int, float)) and up > 0:
        bits.append(f"up {int(up // 86400000)} d")
    return {"state": "healthy", "detail": " · ".join(bits)}


def check_storage(params, boot, now=None):
    """Recording space. A recorder that is nearly full is NORMAL (it overwrites the oldest video), so fullness is only shown; a disk that
    reports itself unhealthy is the problem."""
    nvr = boot.get("nvr") or {}
    stats = nvr.get("storageStats") or {}
    space = stats.get("recordingSpace") or {}
    total, used = space.get("total") or stats.get("capacity"), space.get("used")
    bits = []
    if total and used is not None:
        bits.append(f"{size(used)} of {size(total)} used")
    elif stats.get("utilization") is not None:
        bits.append(f"{stats['utilization']:.0f}% used")
    bad = [str(d.get("model") or d.get("name") or "a disk") for d in disks(nvr) if d.get("healthy") is False]
    if bad:
        return {"state": "failed", "detail": " · ".join(bits + ["disk not healthy: " + ", ".join(bad)])}
    if not bits and not disks(nvr):
        return {"state": "unknown", "detail": "UniFi Protect did not report its storage"}
    n = len(disks(nvr))
    if n:
        bits.append(f"{n} disk{'s' if n != 1 else ''} healthy")
    return {"state": "healthy", "detail": " · ".join(bits)}


HOT_DRIVE_C = 55          # degrees C; editable per check (max_c). A recording drive runs warmer than a switch chip's limit allows no slack for.


def drives(nvr):
    d = ((nvr.get("systemInfo") or {}).get("ustorage") or {}).get("disks")
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def drive_name(d):
    return f"{d.get('model') or 'drive'} (slot {d.get('slot')})" if d.get("slot") is not None else str(d.get("model") or "drive")


def number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


SECTORS_SEEN = {}         # (model, serial, slot) -> the bad-sector count first seen while this module has been running


def check_drive(params, boot, now=None):
    """One recording drive: its temperature and the drive's own verdict. 'hddNotCompatible' (a model Ubiquiti does not list) is not read at all:
    Protect's own screen shows such a drive green."""
    nvr = boot.get("nvr") or {}
    if params.get("slot") is None and not params.get("model"):
        return {"state": "unknown", "detail": "this check needs a drive 'slot'. Open the server and choose Pick what to watch."}
    mine = [d for d in drives(nvr) if (params.get("slot") is None or d.get("slot") == params.get("slot")) and (not params.get("model") or d.get("model") == params.get("model"))]
    if not mine:
        return {"state": "unknown", "detail": "UniFi Protect does not list that drive (it may be out, or the console did not report its drives)"}
    d = mine[0]
    limit = params.get("max_c") or HOT_DRIVE_C
    temp = number(d.get("temperature"))
    bits, problem = [], []
    if temp is not None:
        bits.append(f"{temp:g} °C")
        if temp >= limit:
            problem.append(f"hot, limit {limit:g} °C")
    sectors = number(d.get("bad_sector"))
    if sectors is not None:       # only growth is news: a drive that has always had a few is not warned about every time
        key = (d.get("model"), d.get("serial"), d.get("slot"))
        first = SECTORS_SEEN.get(key)
        if first is None or sectors < first:        # first look, or a counter that went down (a drive swapped in)
            first = SECTORS_SEEN[key] = sectors
        if sectors > first:
            problem.append(f"bad sectors up from {first:g} to {sectors:g}")
    if d.get("healthy") not in (None, "good", True):
        problem.append(f"drive health: {d.get('healthy')}")
    if d.get("state") not in (None, "normal"):
        problem.append(f"drive state: {d.get('state')}")
    if d.get("reason"):
        reason = d["reason"]
        problem.append("drive reports: " + (", ".join(map(str, reason)) if isinstance(reason, list) else str(reason)))
    if temp is None and not problem and d.get("healthy") is None:
        return {"state": "unknown", "detail": "UniFi Protect reports nothing about this drive"}
    return {"state": "degraded" if problem else "healthy", "detail": " · ".join(bits + problem or ["healthy"])}


def camera_list(boot, now=None):
    """The source-neutral camera shape the App's Cameras view reads (any camera source can return the same fields):
    id, name, model, state, detail, recording, lastSeen, motion, source, snapshot (and, when the source knows, mac and host)."""
    out = []
    for c in sorted(boot.get("cameras") or [], key=lambda x: cam_name(x).lower()):
        if c.get("isDeleting"):
            continue
        st, detail = camera_state(c, now)
        out.append({"id": c.get("id"), "name": cam_name(c), "model": c.get("marketName") or c.get("type"), "state": st, "detail": detail,
                    "recording": (c.get("recordingSettings") or {}).get("mode"), "lastSeen": c.get("lastSeen"),
                    "motion": bool(c.get("isMotionDetected")), "source": "unifi-protect", "snapshot": st != "failed",
                    "mac": c.get("mac"), "host": c.get("host")})          # where the camera is on the network, so its switch port can be found
    return out


def discover(boot, now=None, nvr=None):
    cams = camera_list(boot, now)
    sug = [{"label": "Protect recorder", "check": "nvr", "params": {}, "batch": "Overview", "node": "UniFi Protect", "rule": "primary"},       # "is it there" comes first
           {"label": "Protect storage", "check": "storage", "params": {}, "batch": "Overview", "node": "UniFi Protect", "rule": "primary"}]
    for c in cams:      # every camera is its own item, so one that is off shows as Down by name (the all-cameras summary check is no longer offered: it would repeat what they say)
        sug.append({"label": f"Camera {c['name']}", "check": "camera", "params": {"name": c["name"]}, "batch": "Cameras", "node": f"Camera {c['name']}", "rule": "primary"})
    for d in drives(nvr or boot.get("nvr") or {}):     # each drive is its own item, so a hot one shows by name
        if d.get("slot") is not None and (number(d.get("temperature")) is not None or d.get("healthy") is not None):
            sug.append({"label": f"Protect drive {drive_name(d)}", "check": "drive", "params": {"slot": d["slot"]}, "batch": "Drives",
                        "node": f"Protect drive {drive_name(d)}", "rule": "primary"})
    for s in sug:
        s["group"] = "Cameras"
    return {"cameras": cams, "suggest": sug}
