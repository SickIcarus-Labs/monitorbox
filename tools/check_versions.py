#!/usr/bin/env python3
"""Pull-request check: a change to the app or to a module must come with a new version number.

Why: a published version is immutable. The dev publish step refuses to publish the same version with different content ("bump the version"), and by then the change is
already merged, so nothing reaches the box until another pull request fixes the number (this happened with 0.81.5 and the UniFi module). This catches it on the
pull request instead. Standard library only; needs the base branch fetched.

Usage: tools/check_versions.py [BASE_REF]   (default origin/main). Exit 1 and one GitHub annotation per problem when a version is missing."""
import json, os, subprocess, sys

IGNORED = ("__pycache__/", ".pyc", "/tests/", "node_modules/")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def changed_files(base, cwd):
    """Files that differ between the merge base with `base` and the working tree (committed or not)."""
    mb = git("merge-base", base, "HEAD", cwd=cwd)
    ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base
    out = git("diff", "--name-only", ref, cwd=cwd)
    if out.returncode != 0:
        raise SystemExit(f"git diff against {base} failed: {out.stderr.strip()}")
    return [f for f in out.stdout.splitlines() if f and not any(i in "/" + f for i in IGNORED)], ref


def old_text(ref, path, cwd):
    r = git("show", f"{ref}:{path}", cwd=cwd)
    return r.stdout if r.returncode == 0 else None


def new_text(path, cwd):
    try:
        with open(os.path.join(cwd, path)) as f:
            return f.read()
    except OSError:
        return None


def check(base="origin/main", cwd="."):
    """A list of problems (empty when every change carries a new version)."""
    files, ref = changed_files(base, cwd)
    problems = []
    app = [f for f in files if f.startswith("app/monitorbox_app/") and f != "app/monitorbox_app/VERSION"]
    if app:
        old, new = old_text(ref, "app/monitorbox_app/VERSION", cwd), new_text("app/monitorbox_app/VERSION", cwd)
        if old is not None and new is not None and old.strip() == new.strip():
            problems.append(f"The app changed ({len(app)} file{'s' if len(app) != 1 else ''}, for example {app[0]}) but app/monitorbox_app/VERSION is still {new.strip()}. Bump it.")
    mods = sorted({f.split("/")[1] for f in files if f.startswith("modules/") and f.count("/") >= 2 and f != "modules/%s/manifest.json" % f.split("/")[1]})
    for mid in mods:
        path = f"modules/{mid}/manifest.json"
        old, new = old_text(ref, path, cwd), new_text(path, cwd)
        if old is None or new is None:
            continue                                                  # a new module, or one being removed: nothing to compare
        try:
            same = json.loads(old).get("version") == json.loads(new).get("version")
        except ValueError:
            continue                                                  # a broken manifest is somebody else's error
        if same:
            ex = next(f for f in files if f.startswith(f"modules/{mid}/"))
            problems.append(f"The {mid} module changed (for example {ex}) but its version in {path} is still {json.loads(new).get('version')}. Bump it.")
    return problems


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    found = check(base)
    for p in found:
        print(f"::error title=Version not bumped::{p}")
    if not found:
        print("Every changed component carries a new version.")
    sys.exit(1 if found else 0)
