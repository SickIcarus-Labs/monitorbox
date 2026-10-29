"""Backups for the App: a thin wrapper over the launcher's backup.py, so the App and the launcher
(which does the restoring, even with the App down) share ONE code path and ONE file format."""
import json, os, sys, threading, time

OLD_IMAGE = ("The container image is out of date and cannot do backups. "
             "Re-pull the image (redeploy the stack with 'Re-pull image') once, then try again.")


def lib():
    path = os.environ.get("MB_LAUNCHER_PATH")
    if path and path not in sys.path:
        sys.path.append(path)
    try:
        from monitorbox_launcher import backup
    except ImportError:
        raise ValueError(OLD_IMAGE)
    if not getattr(backup.list_backups, "fast", False):
        # The launcher's own list_backups looks each archive's manifest up by name, which reads the whole archive first. Making a backup lists every
        # older backup to prune the old ones, so a 50 KB settings backup took 17 s on a Pi that held a few full backups. The image cannot change
        # without asking every owner to re-pull it, so the App swaps in its own listing (same fields, same order, each archive read once).
        fast = lambda root: listing(root)
        fast.fast = True
        backup.list_backups = fast
    return backup


_cache = {"sig": None, "list": None}
_cache_lock = threading.Lock()


def _signature(root):
    """What is in the backups folder: names, sizes and times. It changes only when a backup is made, removed or replaced."""
    d = os.path.join(root, "backups")
    try:
        names = [n for n in os.listdir(d) if n.endswith(".tgz") and not n.startswith(".")]
        return tuple(sorted((n, os.path.getsize(os.path.join(d, n)), int(os.path.getmtime(os.path.join(d, n)))) for n in names))
    except OSError:
        return ()


_rows = {}                      # (name, size, mtime) -> the archive's row, so only a new archive is ever opened
_compute_lock = threading.Lock()   # one reader at a time: four Settings requests used to each read every archive


def _row(root, name, size):
    """One archive's row, read from the manifest at the very start of the file. (tarfile's own lookup by name reads the whole archive first, which took
    about 14 seconds a request on a Pi with full backups; the manifest is always the first thing in the file.) Unreadable files return None."""
    import tarfile
    try:
        with tarfile.open(os.path.join(root, "backups", name), "r:gz") as tf:
            first = tf.next()
            if first is None or first.name != "manifest.json":
                return None
            m = json.load(tf.extractfile(first))
        return {"name": name, "kind": m["kind"], "label": m.get("label", ""), "created": m["created"], "appVersion": m.get("appVersion"), "size": size}
    except Exception:
        return None


def listing(root):
    """The backups, newest first, as the launcher's list_backups gives them (same fields, same order). The answer only changes when the folder does, so it is
    kept until then, and each archive is read once, however many requests ask at the same moment."""
    sig = _signature(root)
    with _cache_lock:
        if _cache["sig"] == sig and _cache["list"] is not None:
            return [dict(b) for b in _cache["list"]]
    lib()                                     # an out-of-date image still says so, as before
    with _compute_lock:
        with _cache_lock:
            if _cache["sig"] == sig and _cache["list"] is not None:
                return [dict(b) for b in _cache["list"]]
        out = []
        for name, size, mtime in sig:
            if not lib().NAME_RE.match(name):
                continue
            key = (name, size, mtime)
            if key not in _rows:
                _rows[key] = _row(root, name, size)
            if _rows[key]:
                out.append(_rows[key])
        out.sort(key=lambda b: (b["created"], b["name"]), reverse=True)
        for k in [k for k in _rows if k not in set(sig)]:
            del _rows[k]
    with _cache_lock:
        _cache["sig"], _cache["list"] = sig, out
    return [dict(b) for b in out]


def _age_seconds(created):
    return time.time() - time.mktime(time.strptime(created, "%Y-%m-%dT%H:%M:%SZ")) + time.timezone


def due(backups, kind, max_age):
    """True if there is no automatic backup of this kind newer than max_age seconds."""
    return not any(b["kind"] == kind and b["label"] == "auto" and _age_seconds(b["created"]) < max_age for b in backups)


def configured(root):
    """True once the owner has something worth keeping (systems or connections saved).
    A fresh or wiped box has nothing yet, and automatic backups of nothing would only push real ones down the list."""
    try:
        with open(os.path.join(root, "config", "monitorbox.json")) as f:
            cfg = json.load(f)
        return bool((cfg.get("monitoring") or {}).get("nodes") or cfg.get("connections"))
    except (OSError, ValueError, AttributeError):
        return False


def run_auto(root, app_version):
    """Nightly config backup, weekly full backup. Returns the names made."""
    b = lib()
    if not configured(root):
        return []
    made = []
    for kind, age in (("config", 86400), ("full", 7 * 86400)):
        if due(b.list_backups(root), kind, age):
            made.append(b.create(root, kind, "auto", app_version=app_version))
    return made
