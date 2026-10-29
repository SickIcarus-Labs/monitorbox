#!/usr/bin/env python3
"""Build deterministic App/module archives and update a channel pointer.

  build_release.py --out dist --url-template 'https://.../download/{tag}/{file}' \
                   --pointer ../monitorbox-modules/channels/dev.json \
                   --catalog ../monitorbox-modules/catalog.json

Versions come from app/monitorbox_app/VERSION and modules/<id>/manifest.json.
A new version is added to the catalog as "dev" and becomes the dev pointer.
A version is immutable: re-publishing the same version with different content is refused.
Writes only what changed; prints the list of files to upload as release assets.
"""
import argparse, contextlib, gzip, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"__pycache__"}


HIGHLIGHT = re.compile(r"^\[highlight:\s*(.+?)\s*\]\s*")


def parse_changes(root, version):
    """(lines, highlights) for one app version. A line the author wants in the short version of a long update starts, after the ticket number, with
    [highlight: the short sentence]; the tag is taken off the full line and the short sentence goes into highlights."""
    out, marks = [], []
    for ln in changes_for(root, version, raw=True):
        m = HIGHLIGHT.match(ln)
        if m:
            marks.append(m.group(1))
            ln = ln[m.end():]
        out.append(ln)
    return out, marks


def changes_for(root, version, raw=False):
    """The plain-words lines CHANGELOG.md has for one app version ("- **1.6.33** (#313) Text ..."), without the version and the ticket number.
    They go into the catalog entry, so the box can show "What changed" for an update it has not installed yet."""
    try:
        with open(os.path.join(root, "CHANGELOG.md")) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        m = re.match(r"^- \*\*" + re.escape(version) + r"\*\*\s*(?:\(#\d+(?:,\s*#\d+)*\)\s*)?(.*\S)\s*$", ln)
        if m:
            out.append(m.group(1))
    return out if raw else [HIGHLIGHT.sub("", x) for x in out]


def backfill_highlights(entries, root):
    """Notes only, never the archive: highlights marked in CHANGELOG.md after a version was published reach its catalog entry on the next build."""
    for e in entries:
        if not e.get("highlights"):
            marks = parse_changes(root, e["version"])[1]
            if marks:
                e["highlights"] = marks


def make_tgz(src_dir, arc_prefix=""):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for base, dirs, files in os.walk(src_dir):
                dirs[:] = sorted(d for d in dirs if d not in SKIP)
                for name in sorted(files):
                    if name.endswith(".pyc"):
                        continue
                    full = os.path.join(base, name)
                    rel = os.path.join(arc_prefix, os.path.relpath(full, src_dir))
                    ti = tar.gettarinfo(full, arcname=rel)
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ""
                    ti.mtime = 0
                    ti.mode = 0o755 if ti.mode & 0o100 else 0o644
                    with open(full, "rb") as f:
                        tar.addfile(ti, f)
    return buf.getvalue()


@contextlib.contextmanager
def with_node_packages(src_dir, skip=False):
    """A module with a package.json and package-lock.json ships its Node packages inside its archive (the Pi has Node but no npm and no
    network to install from). They are installed from the lock file, without scripts or links, so the same lock gives the same files."""
    if skip or not (os.path.isfile(os.path.join(src_dir, "package.json")) and os.path.isfile(os.path.join(src_dir, "package-lock.json"))):
        yield src_dir
        return
    npm = os.environ.get("MB_NPM") or shutil.which("npm")
    if not npm:
        sys.exit(f"{src_dir} needs its Node packages but npm is not installed here")
    with tempfile.TemporaryDirectory(prefix="mb-node-") as tmp:
        stage = os.path.join(tmp, "module")
        shutil.copytree(src_dir, stage, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        r = subprocess.run([npm, "ci", "--omit=dev", "--ignore-scripts", "--no-bin-links", "--no-audit", "--no-fund"], cwd=stage, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isdir(os.path.join(stage, "node_modules")):
            sys.exit(f"npm ci failed for {src_dir}: {(r.stderr or r.stdout)[-400:]}")
        yield stage


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url-template", required=True, help="uses {tag} and {file}")
    ap.add_argument("--pointer", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--skip", action="append", default=[], metavar="MODULE",
                    help="a module that is published somewhere else (or not at all): not built, not added to the catalog or the pointer. Repeatable.")
    ap.add_argument("--skip-node-packages", action="store_true", help="tests only: do not install a module's Node packages")
    a = ap.parse_args(argv)

    with open(a.pointer) as f:
        ptr = json.load(f)
    with open(a.catalog) as f:
        cat = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    assets, changed = [], False
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def publish(entries, slot_set, name, version, data, changes=None, highlights=None):
        nonlocal changed
        fname = f"{name}-{version}.tar.gz"
        sha = hashlib.sha256(data).hexdigest()
        known = next((e for e in entries if e["version"] == version), None)
        if known:
            if known["sha256"] != sha:
                sys.exit(f"{name} {version} already published with different content; bump the version.")
            return
        with open(os.path.join(a.out, fname), "wb") as f:
            f.write(data)
        assets.append(fname)
        entry = {"version": version,
                 "url": a.url_template.format(tag=fname[:-7], file=fname),
                 "sha256": sha, "signature": None}
        entries.insert(0, {**entry, "published": now, "channels": ["dev"], **({"changes": changes} if changes else {}),
                          **({"highlights": highlights} if highlights else {})})
        slot_set(entry)
        changed = True

    # App: archive holds the monitorbox_app package at its top level
    appdir = os.path.join(a.root, "app", "monitorbox_app")
    with open(os.path.join(appdir, "VERSION")) as f:
        ver = f.read().strip()
    publish(cat.setdefault("app", []), lambda v: ptr.__setitem__("app", v), "app", ver,
            make_tgz(appdir, "monitorbox_app"), *parse_changes(a.root, ver))
    backfill_highlights(cat["app"], a.root)

    # Modules: archive holds manifest.json and code at its top level
    moddir = os.path.join(a.root, "modules")
    for mid in sorted(os.listdir(moddir)):
        mpath = os.path.join(moddir, mid, "manifest.json")
        if not os.path.isfile(mpath) or mid in a.skip:
            continue
        with open(mpath) as f:
            man = json.load(f)
        if man["id"] != mid:
            sys.exit(f"modules/{mid}/manifest.json has id {man['id']!r}")
        with with_node_packages(os.path.join(moddir, mid), a.skip_node_packages) as src:
            data = make_tgz(src)
        publish(cat.setdefault("modules", {}).setdefault(mid, []),
                lambda v, mid=mid: ptr["modules"].__setitem__(mid, v),
                f"module-{mid}", man["version"], data)

    # Launcher: the image version this release was built for. A box whose own launcher is older tells its owner to re-pull the image.
    with open(os.path.join(a.root, "launcher", "monitorbox_launcher", "VERSION")) as f:
        lv = f.read().strip()
    if ptr.get("launcher") != {"version": lv}:
        ptr["launcher"] = {"version": lv}
        changed = True

    if changed:
        ptr["updated"] = now
        for path, obj in ((a.pointer, ptr), (a.catalog, cat)):
            with open(path, "w") as f:
                json.dump(obj, f, indent=2)
                f.write("\n")
    print(json.dumps({"changed": changed, "assets": assets}))


if __name__ == "__main__":
    main()
