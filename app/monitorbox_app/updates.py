"""Pointer check and verified archive install (small copy of the launcher's, on purpose:
the launcher must stay independent of the App it installs)."""
import hashlib, json, os, re, shutil, tarfile, tempfile, time, urllib.request

from .store import read_json, write_json


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def install_archive(url, sha256, dest):
    if os.path.isdir(dest):
        return dest
    data = fetch(url)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("sha256 mismatch; refusing to install")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".tmp-", dir=os.path.dirname(dest))
    try:
        arc = os.path.join(tmp, "a.tgz")
        with open(arc, "wb") as f:
            f.write(data)
        out = os.path.join(tmp, "x")
        os.mkdir(out)
        with tarfile.open(arc, "r:gz") as t:
            t.extractall(out, filter="data")
        os.rename(out, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


DEFAULTS = {"channel": "dev", "auto_check": True, "auto_update": False, "app_pin": "latest", "module_pins": {},
            "repos": [], "module_sources": {}, "uninstalled": []}


def get_update_cfg(paths, default_channel):
    cfg = {**DEFAULTS, "channel": default_channel, **(read_json(paths.config, {}).get("update") or {})}
    cfg["module_pins"] = dict(cfg.get("module_pins") or {})
    cfg["repos"] = [dict(r) for r in cfg.get("repos") or [] if isinstance(r, dict) and r.get("id") and r.get("url")]
    cfg["module_sources"] = dict(cfg.get("module_sources") or {})
    cfg["uninstalled"] = [m for m in cfg.get("uninstalled") or [] if isinstance(m, str)]
    return cfg


# -- repositories ------------------------------------------------------------
# A repository is a public GitHub repo that holds a catalog and channel pointers, like the default one. The default comes from the container
# (MB_RELEASES_URL) and is always listed first. Others are added by the owner and kept in the settings, so a config backup carries them.
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
RAW_RE = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/")


def parse_repo(text):
    """'owner/repo' or a github.com link -> (id, name, releases url). Only public GitHub repos: no other address and no sign-in is accepted."""
    t = (text or "").strip()
    m = re.match(r"^https://github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?/?$", t)
    if m:
        t = m.group(1)
    if not REPO_RE.match(t) or ".." in t or t.endswith(".git"):
        raise ValueError("Enter a public GitHub repository as owner/name, for example SickIcarus-Labs/monitorbox-modules.")
    return t.lower(), t, f"https://raw.githubusercontent.com/{t}/main"


def default_repo(releases_url):
    m = RAW_RE.match(releases_url or "")
    name = f"{m.group(1)}/{m.group(2)}" if m else "Default repository"
    return {"id": name.lower() if m else "default", "name": name, "url": releases_url, "default": True}


def repo_list(cfg, releases_url):
    """Every repository in order, the default first, each with whether it is switched on."""
    d = default_repo(releases_url)
    out = [{**d, "enabled": True}]         # the default is locked: always on, never removed
    for r in cfg.get("repos") or []:
        if r["id"] != d["id"]:
            out.append({"id": r["id"], "name": r.get("name") or r["id"], "url": r["url"], "default": False, "enabled": r.get("enabled", True) is not False})
    return out


def add_repo(paths, text, releases_url):
    rid, name, url = parse_repo(text)
    cfg = get_update_cfg(paths, "dev")
    if rid in [r["id"] for r in repo_list(cfg, releases_url)]:
        raise ValueError(f"{name} is already in the list.")
    set_update_cfg(paths, repos=cfg["repos"] + [{"id": rid, "name": name, "url": url, "enabled": True}])
    return rid


def set_repo_enabled(paths, rid, enabled, releases_url):
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    cfg = get_update_cfg(paths, "dev")
    if rid == default_repo(releases_url)["id"]:
        raise ValueError("The default repository is locked: it cannot be switched off.")
    repos = cfg["repos"]
    if rid not in [r["id"] for r in repos]:
        raise ValueError("That repository is not in the list.")
    set_update_cfg(paths, repos=[{**r, "enabled": enabled} if r["id"] == rid else r for r in repos])


def remove_repo(paths, rid, releases_url, installed_from, uninstalled=False):
    """Removes a repository. The default cannot be removed. One that installed modules still come from is removed only once they are
    uninstalled (the caller does that first and says so with uninstalled=True)."""
    cfg = get_update_cfg(paths, "dev")
    if rid == default_repo(releases_url)["id"]:
        raise ValueError("The default repository is locked: it cannot be removed.")
    if rid not in [r["id"] for r in cfg["repos"]]:
        raise ValueError("That repository is not in the list.")
    mine = sorted(installed_from(rid))
    if mine and not uninstalled:
        raise ValueError("Modules installed from this repository: " + ", ".join(mine) + ". Removing it uninstalls them.")
    set_update_cfg(paths, repos=[r for r in cfg["repos"] if r["id"] != rid])


def set_update_cfg(paths, **changes):
    cfg = read_json(paths.config, {"schema": 4})
    upd = cfg.setdefault("update", {})
    for k, v in changes.items():
        if k == "channel" and v not in ("dev", "beta", "stable"):
            raise ValueError("channel must be dev, beta or stable")
        if k in ("auto_check", "auto_update") and not isinstance(v, bool):
            raise ValueError(f"{k} must be true or false")
        upd[k] = v
    write_json(paths.config, cfg)


def fresh(url):
    """GitHub's raw file server caches for ~5 minutes; a changing query string gets the current file."""
    return f"{url}?t={int(time.time())}" if url.startswith("http") else url


def fetch_release_info(releases_url, channel):
    base = releases_url.rstrip("/")
    return {"catalog": json.loads(fetch(fresh(f"{base}/catalog.json"))),
            "pointer": json.loads(fetch(fresh(f"{base}/channels/{channel}.json")))}


def request_launcher_install(paths, entry):
    write_json(paths.request, {"action": "install", "app": {k: entry[k] for k in ("version", "url", "sha256")}}, mode=0o644)
