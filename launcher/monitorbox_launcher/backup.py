"""Backup and restore: ONE code path, used by the App (to make backups) and by the
launcher (to restore, so it works with the App down).  Standard library only.

An archive is a .tgz holding manifest.json plus the files, paths relative to /config:
  kind "config": config/ and data/app/auth.json            (small, nightly)
  kind "full"  : config/, data/app/, releases/ + link names (everything, so a restore needs no network)

Restore is staged and reversible: validate everything, extract to restore/new, move the current
files aside into restore/old, move the new ones in, and only delete restore/old once the caller
says the result works.  undo() puts everything back, and can be run again after a crash.
"""
import datetime, hashlib, io, json, os, re, shutil, tarfile, tempfile, time

SCHEMA = 1
TARGETS = {"config": ["config", "data/app/auth.json"], "full": ["config", "data/app", "releases"]}
LINKS = ("current", "previous")
MAX_BYTES = 1024 * 1024 * 1024
MAX_FILES = 50000
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.tgz$")
KEEP = {("config", "auto"): 14, ("full", "auto"): 4, ("config", "pre-restore"): 5}


class BackupError(ValueError):
    """A problem in plain words, safe to show the owner."""


def backups_dir(root):
    return os.path.join(root, "backups")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_stamp(root, now):
    """The file-name time in the box's own time zone (Settings > Display), UTC when none is set or it cannot be read.
    Only the name uses it; the manifest's `created` stays UTC, which is what orders and prunes backups."""
    tz = None
    try:
        with open(os.path.join(root, "config", "display.json")) as f:
            name = (json.load(f) or {}).get("timezone")
        if name:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(str(name))
    except Exception:
        tz = None
    t = datetime.datetime.fromtimestamp(time.time() if now is None else now, tz or datetime.timezone.utc)
    return t.strftime("%Y%m%d-%H%M%S")


def _under(rel, kind):
    return any(rel == t or rel.startswith(t + "/") for t in TARGETS[kind])


def _safe(rel):
    p = os.path.normpath(rel)
    return not (rel.startswith("/") or p.startswith("..") or p != rel or "\\" in rel or "\0" in rel)


# ---- create ---------------------------------------------------------------
def site_slug(root):
    """The site's own name (Settings, Sites) as a file-name piece, so backups from several MonitorBoxes can be told apart: 'Bay Harbor' -> 'bay-harbor'.
    Empty when no name has been set."""
    try:
        with open(os.path.join(root, "config", "sites.json")) as f:
            name = str(json.load(f).get("name") or "")
    except (OSError, ValueError, AttributeError):
        return ""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-")


def create(root, kind="config", label="manual", app_version=None, now=None):
    """Write a new backup into /config/backups and return its file name."""
    if kind not in TARGETS:
        raise BackupError("Unknown backup kind.")
    files = {}
    for t in TARGETS[kind]:
        base = os.path.join(root, t)
        if os.path.isfile(base):
            files[t] = base
        for d, _dirs, names in os.walk(base):
            _dirs[:] = [x for x in _dirs if not x.startswith(".tmp-")]     # a module being installed right now is not part of the backup
            for n in names:
                full = os.path.join(d, n)
                if os.path.isfile(full) and not os.path.islink(full) and not n.startswith(".tmp-"):
                    files[os.path.relpath(full, root)] = full
    links = {}
    if kind == "full":
        for ln in LINKS:
            tgt = os.path.realpath(os.path.join(root, ln)) if os.path.islink(os.path.join(root, ln)) else None
            if tgt and tgt.startswith(os.path.realpath(root) + os.sep):
                links[ln] = os.path.relpath(tgt, os.path.realpath(root))
    stamp = local_stamp(root, now)
    site = site_slug(root)
    name = f"monitorbox-{site + '-' if site else ''}{kind}-{stamp}-{label}.tgz"
    os.makedirs(backups_dir(root), exist_ok=True)
    # Every file is copied ONCE into a private snapshot, and both the checksum and the archive come from that copy.
    # (Hashing the live file and then reading it again for the archive let a file the App rewrote in between
    # produce a backup whose own checksum did not match, which restore then refused as damaged.)
    snap = tempfile.mkdtemp(dir=backups_dir(root), prefix=".tmp-snap-")
    fd, tmp = tempfile.mkstemp(dir=backups_dir(root), prefix=".tmp-")
    os.close(fd)
    try:
        copies, shas = {}, {}
        for i, (rel, p) in enumerate(sorted(files.items())):
            dst = os.path.join(snap, str(i))
            try: shutil.copyfile(p, dst)
            except FileNotFoundError: continue                              # replaced by an update while we were looking: leave it out
            copies[rel] = (p, dst); shas[rel] = _sha(dst)
        manifest = {"schema": SCHEMA, "kind": kind, "label": label, "site": site, "appVersion": app_version, "links": links,
                    "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "files": shas}
        os.chmod(tmp, 0o600)  # the archive holds passwords and tokens
        with tarfile.open(tmp, "w:gz") as tf:
            data = json.dumps(manifest, indent=1, sort_keys=True).encode()
            ti = tarfile.TarInfo("manifest.json")
            ti.size, ti.mtime, ti.mode = len(data), int(now or time.time()), 0o600
            tf.addfile(ti, io.BytesIO(data))
            for rel, (orig, dst) in sorted(copies.items()):
                ti = tf.gettarinfo(dst, rel)
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ""
                with open(dst, "rb") as f:
                    tf.addfile(ti, f)
        final = os.path.join(backups_dir(root), name)
        n = 1
        while os.path.exists(final):
            n += 1
            final = os.path.join(backups_dir(root), name[:-4] + f"-{n}.tgz")
        os.replace(tmp, final)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    finally:
        shutil.rmtree(snap, ignore_errors=True)
    prune(root)
    return os.path.basename(final)


def prune(root):
    """Keep the newest few automatic and pre-restore backups. Manual and uploaded ones stay."""
    items = list_backups(root)
    for (kind, label), keep in KEEP.items():
        same = [b for b in items if b["kind"] == kind and b["label"] == label]
        for old in same[keep:]:
            try:
                os.unlink(os.path.join(backups_dir(root), old["name"]))
            except OSError:
                pass


def list_backups(root):
    """Newest first. Unreadable files are skipped here and refused on restore."""
    out = []
    d = backups_dir(root)
    for name in (os.listdir(d) if os.path.isdir(d) else []):
        if not NAME_RE.match(name):
            continue
        p = os.path.join(d, name)
        try:
            with tarfile.open(p, "r:gz") as tf:
                m = json.load(tf.extractfile("manifest.json"))
            out.append({"name": name, "kind": m["kind"], "label": m.get("label", ""), "created": m["created"],
                        "appVersion": m.get("appVersion"), "size": os.path.getsize(p)})
        except Exception:
            continue
    return sorted(out, key=lambda b: (b["created"], b["name"]), reverse=True)


def path_of(root, name):
    if not NAME_RE.match(name or ""):
        raise BackupError("That is not a backup file name.")
    p = os.path.join(backups_dir(root), name)
    if not os.path.isfile(p):
        raise BackupError("That backup does not exist.")
    return p


# ---- validate -------------------------------------------------------------
def validate(archive):
    """Check an archive end to end WITHOUT touching /config. Returns the manifest or raises BackupError."""
    try:
        tf = tarfile.open(archive, "r:gz")
    except (tarfile.TarError, OSError, EOFError):
        raise BackupError("This is not a MonitorBox backup file (or it is damaged).")
    with tf:
        try:
            members = tf.getmembers()
            mm = next((m for m in members if m.name == "manifest.json"), None)
            if not mm or not mm.isfile():
                raise BackupError("This is not a MonitorBox backup (no manifest).")
            man = json.load(tf.extractfile(mm))
            if not isinstance(man, dict) or man.get("schema") != SCHEMA:
                raise BackupError("This backup was made by a newer or unknown version of MonitorBox.")
            kind, listed = man.get("kind"), man.get("files")
            if kind not in TARGETS or not isinstance(listed, dict):
                raise BackupError("The backup's manifest is not valid.")
            if len(members) > MAX_FILES or sum(m.size for m in members) > MAX_BYTES:
                raise BackupError("The backup is too large.")
            seen = set()
            for m in members:
                if m.name == "manifest.json":
                    continue
                if not m.isfile() or not _safe(m.name) or not _under(m.name, kind):
                    raise BackupError(f"The backup contains something unexpected ({m.name[:60]}); nothing was changed.")
                if m.name not in listed:
                    raise BackupError(f"The backup contains a file its manifest does not list ({m.name[:60]}).")
                h = hashlib.sha256()
                f = tf.extractfile(m)
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                if h.hexdigest() != listed[m.name]:
                    raise BackupError(f"The backup is damaged ({m.name[:60]} does not match its checksum).")
                seen.add(m.name)
            if seen != set(listed):
                raise BackupError("The backup is incomplete: files are missing.")
            for rel in ("config/monitorbox.json", "data/app/auth.json"):
                if rel in seen:
                    try:
                        if not isinstance(json.load(tf.extractfile(rel)), dict):
                            raise ValueError
                    except ValueError:
                        raise BackupError(f"{rel} in the backup is not valid.")
            links = man.get("links", {})
            if not isinstance(links, dict) or any(k not in LINKS or not _safe(str(v)) or not str(v).startswith("releases/")
                                                  for k, v in links.items()):
                raise BackupError("The backup's version links are not valid.")
            return man
        except (tarfile.TarError, EOFError, OSError, ValueError, KeyError) as e:
            if isinstance(e, BackupError):
                raise
            raise BackupError("This is not a usable MonitorBox backup (it is damaged).")


# ---- restore --------------------------------------------------------------
def _rdir(root, *a):
    return os.path.join(root, "restore", *a)


def stage(root, archive):
    """Validate, then unpack into restore/new. Returns the manifest."""
    man = validate(archive)
    new = _rdir(root, "new")
    shutil.rmtree(_rdir(root), ignore_errors=True)
    os.makedirs(new)
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            if m.name == "manifest.json":
                continue
            dest = os.path.join(new, m.name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, (m.mode & 0o777) | 0o600)
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(tf.extractfile(m), out)
    return man


def _point(root, link, rel):
    lp, tmp = os.path.join(root, link), os.path.join(root, f".{link}.new")
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(os.path.join(root, rel), tmp)
    os.replace(tmp, lp)


def swap(root, man):
    """Move the current files aside and the staged ones in. Reversible with undo()."""
    kind = man["kind"]
    old = _rdir(root, "old")
    os.makedirs(old)
    absent = [t for t in TARGETS[kind] if not os.path.lexists(os.path.join(root, t))]
    old_links = {ln: os.readlink(os.path.join(root, ln)) for ln in LINKS if os.path.islink(os.path.join(root, ln))}
    journal = {"kind": kind, "targets": TARGETS[kind], "absent": absent, "oldLinks": old_links,
               "linksChanged": bool(man.get("links"))}
    with open(_rdir(root, "journal.json"), "w") as f:
        json.dump(journal, f)
    for t in TARGETS[kind]:
        cur, aside, new = os.path.join(root, t), os.path.join(old, t), os.path.join(_rdir(root, "new"), t)
        if os.path.lexists(cur):
            os.makedirs(os.path.dirname(aside), exist_ok=True)
            os.rename(cur, aside)
        if os.path.lexists(new):
            os.makedirs(os.path.dirname(cur), exist_ok=True)
            os.rename(new, cur)
    for ln, rel in man.get("links", {}).items():
        if os.path.isdir(os.path.join(root, rel)):
            _point(root, ln, rel)


def pending(root):
    return os.path.exists(_rdir(root, "journal.json"))


def undo(root):
    """Put the files from before the restore back. Safe to run twice and after a crash."""
    try:
        with open(_rdir(root, "journal.json")) as f:
            j = json.load(f)
    except (OSError, ValueError):
        shutil.rmtree(_rdir(root), ignore_errors=True)
        return False
    old = _rdir(root, "old")
    for t in j["targets"]:
        cur, aside = os.path.join(root, t), os.path.join(old, t)
        if os.path.lexists(aside):
            if os.path.lexists(cur):
                shutil.rmtree(cur) if os.path.isdir(cur) and not os.path.islink(cur) else os.unlink(cur)
            os.makedirs(os.path.dirname(cur), exist_ok=True)
            os.rename(aside, cur)
        elif t in j["absent"] and os.path.lexists(cur):
            shutil.rmtree(cur) if os.path.isdir(cur) and not os.path.islink(cur) else os.unlink(cur)
    if j.get("linksChanged"):
        for ln in LINKS:
            lp = os.path.join(root, ln)
            if ln in j["oldLinks"]:
                tmp = os.path.join(root, f".{ln}.new")
                if os.path.lexists(tmp):
                    os.unlink(tmp)
                os.symlink(j["oldLinks"][ln], tmp)
                os.replace(tmp, lp)
            elif os.path.islink(lp):
                os.unlink(lp)
    shutil.rmtree(_rdir(root), ignore_errors=True)
    return True


def commit(root):
    """The restored files work: drop the copies from before."""
    shutil.rmtree(_rdir(root), ignore_errors=True)


# ---- password check for the recovery page (same scrypt settings as the App) --
def password_ok(root, password):
    """True if no admin password exists yet (nothing to protect), or the password matches."""
    import hmac
    try:
        with open(os.path.join(root, "data", "app", "auth.json")) as f:
            rec = json.load(f)
        salt, want = bytes.fromhex(rec["salt"]), bytes.fromhex(rec["hash"])
    except (OSError, ValueError, KeyError):
        return True
    got = hashlib.scrypt((password or "").encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got, want)
