"""Verified download + safe extraction + atomic symlink switching."""
import hashlib, json, os, shutil, tarfile, tempfile, urllib.request

TIMEOUT = 30


def fetch(url, timeout=TIMEOUT):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # file:// works too (tests)
        return r.read()


def fetch_json(url):
    return json.loads(fetch(url).decode())


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def install_archive(url, sha256, dest):
    """Download url, require sha256, extract to dest atomically. Returns dest.
    If dest already exists it is trusted (releases are immutable)."""
    if os.path.isdir(dest):
        return dest
    data = fetch(url)
    got = sha256_hex(data)
    if got != sha256:
        raise ValueError(f"sha256 mismatch for {url}: expected {sha256[:12]}…, got {got[:12]}…")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".tmp-", dir=os.path.dirname(dest))
    try:
        with tempfile.NamedTemporaryFile(dir=tmp, suffix=".tgz", delete=False) as f:
            f.write(data)
            name = f.name
        out = os.path.join(tmp, "x")
        os.mkdir(out)
        with tarfile.open(name, "r:gz") as t:
            t.extractall(out, filter="data")  # rejects absolute paths, '..', links outside
        os.rename(out, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


def switch_link(link, target):
    """Atomically point `link` at `target` (a directory)."""
    tmp = link + ".new"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)


def link_target(link):
    return os.path.realpath(link) if os.path.islink(link) else None
