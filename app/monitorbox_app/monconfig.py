"""The monitoring part of monitorbox.json: validate, apply with revisions, built-in internet checks.

  "monitoring": {"builtinInternet": true,
                 "nodes": [ {"id","name","group","critical","checks":[...],"rule","dependsOn":[...]} ,
                            {"id","name","group","critical","kind":"aggregate","children":[...],"rule","dependsOn":[...]} ]}

Every edit: validate -> revision check -> atomic write -> numbered copy kept (last 20).
A bad edit is refused with every error listed and changes nothing."""
import ipaddress, os, re

from .store import read_json, write_json

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
MODULE_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
SECRET_RE = re.compile(r"pass|secret|token|key|community", re.I)  # fields shown as dots in the editor
MASK = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
MAX_CHECKS = 300         # a NAS with many shared folders, disks and ports is one system with a hundred checks
TYPES = {"ping": {"target"}, "tcp": {"target", "port"}, "http": {"url"}, "dns": {"server"}, "module": {"module"}, "site": {"site"}, "manager": {"manager"}, "ports": set()}
OPTIONAL = {"ping": {"timeout", "interval"}, "tcp": {"timeout", "interval"},
            "http": {"timeout", "interval", "expect", "insecure", "contains", "connection"}, "dns": {"timeout", "interval", "name", "port"},
            "module": {"timeout", "interval", "connection", "check", "params"}, "site": {"interval"}, "manager": {"interval"}, "ports": {"interval"}}
NODE_KEYS = {"id", "name", "group", "critical", "checks", "rule", "dependsOn", "poweredBy", "kind", "children", "wake", "service", "link", "confirmFailures", "confirmSeconds"}
SERVICE_KEYS = {"title", "env", "container", "stack", "icon", "url"}
WAKE_KEYS = {"macs", "broadcast", "port", "timeout", "retry"}
KEEP_REVISIONS = 20


class Conflict(Exception):
    pass


class Invalid(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def validate(mon, connection_ids=None):
    """Returns (nodes, errors). nodes are normalized copies, errors a list of plain sentences.
    connection_ids: the ids in 'connections', so a check cannot point at one that does not exist."""
    errs, nodes = [], []
    if not isinstance(mon, dict):
        return [], ["monitoring must be an object"]
    for k in mon:
        if k not in ("nodes", "builtinInternet", "expectedDown", "confirm"):
            errs.append(f"monitoring: unknown setting '{k}'")
    if "builtinInternet" in mon and not isinstance(mon["builtinInternet"], bool):
        errs.append("builtinInternet must be true or false")
    cf = mon.get("confirm", {})
    if not isinstance(cf, dict) or any(k not in ("failures", "seconds") for k in cf):
        errs.append("confirm may only hold 'failures' and 'seconds'")
    else:
        if "failures" in cf and not (isinstance(cf["failures"], int) and not isinstance(cf["failures"], bool) and 1 <= cf["failures"] <= 20):
            errs.append("confirm failures must be a whole number from 1 to 20")
        if "seconds" in cf and not _num(cf["seconds"], 0, 3600):
            errs.append("confirm seconds must be 0 to 3600")
    exp = mon.get("expectedDown", [])
    if not isinstance(exp, list) or len(exp) > 500 or not all(isinstance(x, str) and ID_RE.match(x) for x in exp):
        errs.append("expectedDown must be a list of system ids")
    raw = mon.get("nodes", [])
    if not isinstance(raw, list):
        return [], errs + ["nodes must be a list"]
    ids = [n.get("id") if isinstance(n, dict) else None for n in raw]
    for i, n in enumerate(raw):
        where = f"node {i + 1}" + (f" '{n.get('id')}'" if isinstance(n, dict) and n.get("id") else "")
        if not isinstance(n, dict):
            errs.append(f"{where}: must be an object")
            continue
        for k in n:
            if k not in NODE_KEYS:
                errs.append(f"{where}: unknown field '{k}'")
        nid = n.get("id")
        if not isinstance(nid, str) or not ID_RE.match(nid):
            errs.append(f"{where}: id must be lowercase letters, digits and dashes")
        elif ids.count(nid) > 1:
            errs.append(f"{where}: id used more than once")
        if not isinstance(n.get("name"), str) or not n["name"].strip():
            errs.append(f"{where}: name is required")
        if not isinstance(n.get("group"), str) or not n["group"].strip():
            errs.append(f"{where}: group is required (for example Servers)")
        if "critical" in n and not isinstance(n["critical"], bool):
            errs.append(f"{where}: critical must be true or false")
        dep = n.get("dependsOn", [])
        if not isinstance(dep, list) or not all(isinstance(d, str) for d in dep):
            errs.append(f"{where}: dependsOn must be a list of ids")
            dep = []
        norm = {"id": nid, "name": n.get("name", ""), "group": n.get("group", ""),
                "critical": bool(n.get("critical", False)), "dependsOn": list(dep)}
        if "poweredBy" in n:
            pw = n["poweredBy"]
            if isinstance(pw, list) and all(isinstance(d, str) for d in pw):
                norm["poweredBy"] = list(pw)                # [] is an answer too: "nothing I know of" (it stops a guess)
            else:
                errs.append(f"{where}: poweredBy must be a list of ids")
        if "confirmFailures" in n:
            if isinstance(n["confirmFailures"], int) and not isinstance(n["confirmFailures"], bool) and 1 <= n["confirmFailures"] <= 20:
                norm["confirmFailures"] = n["confirmFailures"]
            else:
                errs.append(f"{where}: confirmFailures must be a whole number from 1 to 20")
        if "confirmSeconds" in n:
            if _num(n["confirmSeconds"], 0, 3600):
                norm["confirmSeconds"] = n["confirmSeconds"]
            else:
                errs.append(f"{where}: confirmSeconds must be 0 to 3600")
        if n.get("kind") == "aggregate":
            norm["kind"] = "aggregate"
            kids = n.get("children")
            if not isinstance(kids, list) or not kids:
                errs.append(f"{where}: an aggregate needs a list of children")
                kids = []
            norm["children"] = list(kids)
            norm["rule"] = n.get("rule", "any")
            if norm["rule"] not in ("any", "all"):
                errs.append(f"{where}: rule must be 'any' or 'all'")
            if "checks" in n:
                errs.append(f"{where}: an aggregate has children, not checks")
        else:
            if n.get("kind", "leaf") != "leaf":
                errs.append(f"{where}: kind must be 'aggregate' or left out")
            norm["rule"] = n.get("rule", "primary")
            if norm["rule"] not in ("primary", "any"):
                errs.append(f"{where}: rule must be 'primary' or 'any'")
            checks = n.get("checks")
            if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
                errs.append(f"{where}: needs 1 to {MAX_CHECKS} checks")
                checks = []
            norm["checks"] = []
            seen = set()
            for j, c in enumerate(checks):
                cw = f"{where}: check {j + 1}"
                if not isinstance(c, dict) or c.get("type") not in TYPES:
                    errs.append(f"{cw}: type must be one of {', '.join(sorted(TYPES))}")
                    continue
                t = c["type"]
                allowed = TYPES[t] | OPTIONAL[t] | {"type", "id", "label"}
                for k in c:
                    if k not in allowed:
                        errs.append(f"{cw}: unknown field '{k}' for a {t} check")
                for k in TYPES[t]:
                    if k not in c:
                        errs.append(f"{cw}: {t} check needs '{k}'")
                if t == "tcp" and "port" in c and not (isinstance(c["port"], int) and 1 <= c["port"] <= 65535):
                    errs.append(f"{cw}: port must be 1 to 65535")
                if t == "module":
                    if not isinstance(c.get("module"), str) or not MODULE_RE.match(c["module"]):
                        errs.append(f"{cw}: module must be a module id such as snmp")
                    if "check" in c and not isinstance(c["check"], str):
                        errs.append(f"{cw}: check must be text")
                    if "params" in c and not isinstance(c["params"], dict):
                        errs.append(f"{cw}: params must be an object")
                    if "connection" in c:
                        if not isinstance(c["connection"], str):
                            errs.append(f"{cw}: connection must be text")
                        elif connection_ids is not None and c["connection"] not in connection_ids:
                            errs.append(f"{cw}: connection '{c['connection']}' does not exist")
                if t != "module" and "connection" in c:     # which connection a check came from (a container's web check, say)
                    if not isinstance(c["connection"], str):
                        errs.append(f"{cw}: connection must be text")
                    elif connection_ids is not None and c["connection"] not in connection_ids:
                        errs.append(f"{cw}: connection '{c['connection']}' does not exist")
                if t == "http" and not str(c.get("url", "")).startswith(("http://", "https://")):
                    errs.append(f"{cw}: url must start with http:// or https://")
                if "expect" in c and not _codes_ok(c["expect"]):
                    errs.append(f"{cw}: expect must be a list of status codes (100 to 599) or ranges like \"200-399\"")
                if "timeout" in c and not _num(c["timeout"], 0.2, 30):
                    errs.append(f"{cw}: timeout must be 0.2 to 30 seconds")
                if "interval" in c and not _num(c["interval"], 2, 3600):
                    errs.append(f"{cw}: interval must be 2 to 3600 seconds")
                cid = c.get("id", t if j == 0 else f"{t}{j + 1}")
                if not isinstance(cid, str) or not re.match(r"^[a-z0-9][a-z0-9-]{0,30}$", cid) or cid in seen:
                    errs.append(f"{cw}: check id must be unique lowercase letters, digits, dashes")
                seen.add(cid)
                norm["checks"].append({**c, "id": cid})
        if "service" in n:
            sv = n["service"]
            if not isinstance(sv, dict) or any(k not in SERVICE_KEYS or not isinstance(v, str) or len(v) > 300 for k, v in sv.items()):
                errs.append(f"{where}: service may only hold text for {', '.join(sorted(SERVICE_KEYS))}")
            elif sv.get("url") and not sv["url"].startswith(("http://", "https://")):
                errs.append(f"{where}: service url must start with http:// or https://")
            else:
                norm["service"] = dict(sv)
        if "link" in n:
            lk = n["link"]
            if not isinstance(lk, str) or not lk.startswith(("http://", "https://")) or len(lk) > 300 or " " in lk:
                errs.append(f"{where}: link must be a web address starting with http:// or https://")
            else:
                norm["link"] = lk
        if "wake" in n:
            if n.get("kind") == "aggregate":
                errs.append(f"{where}: only a system with its own checks can be woken")
            else:
                w, werrs = validate_wake(n["wake"])
                errs += [f"{where}: wake {e}" for e in werrs]
                norm["wake"] = w
        nodes.append(norm)
    valid_ids = {n["id"] for n in nodes if isinstance(n["id"], str)}
    for n in nodes:
        where = f"'{n['id']}'"
        for d in n["dependsOn"]:
            if d not in valid_ids:
                errs.append(f"{where}: dependsOn '{d}' does not exist")
            if d == n["id"]:
                errs.append(f"{where}: cannot depend on itself")
        for c in n.get("children", []):
            if c not in valid_ids:
                errs.append(f"{where}: child '{c}' does not exist")
        for d in n.get("poweredBy", []):
            if d not in valid_ids:
                errs.append(f"{where}: poweredBy '{d}' does not exist")
            if d == n["id"]:
                errs.append(f"{where}: cannot be powered by itself")
    # cycles in dependsOn
    graph = {n["id"]: [d for d in n["dependsOn"] if d in valid_ids and d != n["id"]] for n in nodes}
    state = {}

    def visit(x, path):
        if state.get(x) == 1:
            errs.append("dependency loop: " + " -> ".join(path[path.index(x):] + [x]))
            return
        if state.get(x) == 2:
            return
        state[x] = 1
        for y in graph.get(x, []):
            visit(y, path + [x])
        state[x] = 2

    for x in graph:
        if state.get(x) is None:
            visit(x, [])
    return nodes, errs


def _mac(m):
    flat = re.sub(r"[:.\-]", "", str(m)).lower()
    return ":".join(flat[i:i + 2] for i in range(0, 12, 2)) if re.fullmatch(r"[0-9a-f]{12}", flat) else None


def validate_wake(w):
    """Wake-on-LAN settings of a system: {"macs": [...], "broadcast": ip, "port": 9, "timeout": 120, "retry": 30}.
    Returns (normalized, errors). MACs are stored as aa:bb:cc:dd:ee:ff whatever way they were typed."""
    errs = []
    if not isinstance(w, dict):
        return {}, ["must be an object"]
    for k in w:
        if k not in WAKE_KEYS:
            errs.append(f"has an unknown field '{k}'")
    macs = w.get("macs")
    norm = []
    if not isinstance(macs, list) or not macs:
        errs.append("needs 'macs': a list of one or more MAC addresses")
    else:
        for m in macs:
            nm = _mac(m)
            if nm is None:
                errs.append(f"'{m}' is not a MAC address (like aa:bb:cc:dd:ee:ff)")
            elif nm in norm:
                errs.append(f"MAC {nm} is listed twice")
            else:
                norm.append(nm)
    out = {"macs": norm}
    if "broadcast" in w:
        try:
            if ipaddress.ip_address(w["broadcast"]).version != 4:
                raise ValueError("the wake packet is sent over IPv4")
            out["broadcast"] = w["broadcast"]
        except ValueError:
            errs.append("broadcast must be an IPv4 address such as 192.0.2.255")
    if "port" in w:
        if isinstance(w["port"], int) and not isinstance(w["port"], bool) and 1 <= w["port"] <= 65535:
            out["port"] = w["port"]
        else:
            errs.append("port must be 1 to 65535")
    for key, lo, hi, dflt in (("timeout", 5, 3600, 120), ("retry", 2, 300, 30)):
        if key in w:
            if _num(w[key], lo, hi):
                out[key] = w[key]
            else:
                errs.append(f"{key} must be {lo} to {hi} seconds")
    return out, errs


def builtin_internet(user_ids):
    """Pre-populated so the app can tell "no route to the internet" from "local DNS broken"
    from "public DNS broken". Hung under the user's gateway node when there is one."""
    gw = ["gateway"] if "gateway" in user_ids else []

    def ping(i, ip):
        return {"id": i, "name": f"Ping {ip}", "group": "Internet", "critical": False, "dependsOn": gw, "rule": "primary",
                "checks": [{"id": "ping", "type": "ping", "target": ip}]}

    def dns(i, ip):
        return {"id": i, "name": f"DNS via {ip}", "group": "Internet", "critical": False, "dependsOn": ["internet"],
                "rule": "primary", "checks": [{"id": "dns", "type": "dns", "server": ip, "name": "google.com"}]}

    return [
        ping("inet-ping-cloudflare", "1.1.1.1"), ping("inet-ping-google", "8.8.8.8"),
        {"id": "internet", "name": "Internet", "group": "Internet", "critical": True, "dependsOn": gw, "kind": "aggregate",
         "children": ["inet-ping-cloudflare", "inet-ping-google"], "rule": "any"},
        dns("inet-dns-cloudflare", "1.1.1.1"), dns("inet-dns-google", "8.8.8.8"),
        {"id": "inet-web-google", "name": "google.com", "group": "Internet", "critical": False, "dependsOn": ["internet"],
         "rule": "primary", "checks": [{"id": "http", "type": "http", "url": "https://www.google.com/"}]},
    ]


# ---- file handling -------------------------------------------------------
RENAMED_MODULES = {"unifi": "unifi-network"}       # old module id -> new id; applied when the config is read, so nothing needs re-entering


def migrate_modules(cfg):
    """Follow module renames in connections and in module checks. Done in memory on every read; the file is rewritten on the next save,
    so an App rolled back before then still finds the old name."""
    if not isinstance(cfg, dict):
        return cfg
    for c in cfg.get("connections") or []:
        if isinstance(c, dict) and c.get("module") in RENAMED_MODULES:
            c["module"] = RENAMED_MODULES[c["module"]]
    mon = cfg.get("monitoring")
    for n in (mon.get("nodes") if isinstance(mon, dict) else None) or []:
        for k in (n.get("checks") if isinstance(n, dict) else None) or []:
            if isinstance(k, dict) and k.get("module") in RENAMED_MODULES:
                k["module"] = RENAMED_MODULES[k["module"]]
    return cfg


def load_config(paths):
    return migrate_modules(read_json(paths.config, {"schema": 4}))


def get_monitoring(paths):
    cfg = load_config(paths)
    return {"revision": cfg.get("revision", 0), "monitoring": cfg.get("monitoring", {"builtinInternet": True, "nodes": []})}


def _conn_ids(cfg):
    conns = cfg.get("connections")
    return {c.get("id") for c in conns if isinstance(c, dict)} if isinstance(conns, list) else set()


def all_nodes(paths):
    """Built-in nodes plus the owner's. Returns (nodes, error_or_None); a broken stored config
    never takes the App down: the built-in checks keep running and the error is reported."""
    cfg = load_config(paths)
    mon = cfg.get("monitoring", {"builtinInternet": True, "nodes": []})
    user, errs = validate(mon, _conn_ids(cfg))
    if errs:
        user = []
    use_builtin = isinstance(mon, dict) and mon.get("builtinInternet", True) is not False
    builtin = builtin_internet({n["id"] for n in user}) if use_builtin else []
    for n in builtin:
        n["builtin"] = True
    exp = set(mon.get("expectedDown", [])) if isinstance(mon, dict) and isinstance(mon.get("expectedDown"), list) else set()
    for n in builtin + user:
        if n["id"] in exp:
            n["expectedDown"] = True
    return builtin + user, ("; ".join(errs[:5]) if errs else None)


def set_powered_by(paths, system_id, ups_id):
    """Say which UPS powers one of the owner's systems (None: none, which also stops a guess). One UPS at a time: the Power page offers a system to only one."""
    cur = get_monitoring(paths)
    mon = cur["monitoring"]
    nodes = mon.get("nodes", []) if isinstance(mon, dict) else []
    n = next((x for x in nodes if isinstance(x, dict) and x.get("id") == system_id), None)
    if n is None:
        raise Invalid([f"'{system_id}' is not one of the systems you watch"])
    if ups_id and not any(isinstance(x, dict) and x.get("id") == ups_id for x in nodes):
        raise Invalid([f"'{ups_id}' is not one of the systems you watch"])
    n["poweredBy"] = [ups_id] if ups_id else []
    return save_monitoring(paths, mon, cur["revision"])


def save_monitoring(paths, mon, base_revision):
    nodes, errs = validate(mon, _conn_ids(load_config(paths)))
    if not errs:
        taken = {n["id"] for n in nodes}
        clash = taken & {n["id"] for n in builtin_internet(taken)} if mon.get("builtinInternet", True) else set()
        errs += [f"id '{c}' is reserved for the built-in internet checks" for c in sorted(clash)]
    if errs:
        raise Invalid(errs)
    cfg = load_config(paths)
    if cfg.get("revision", 0) != base_revision:
        raise Conflict(f"The configuration changed since you loaded it (now revision {cfg.get('revision', 0)}). Reload and try again.")
    rev = cfg.get("revision", 0) + 1
    cfg["monitoring"], cfg["revision"], cfg["schema"] = mon, rev, 4
    rdir = os.path.join(os.path.dirname(paths.config), "revisions")
    write_json(os.path.join(rdir, f"{rev:06d}.json"), {"revision": rev, "monitoring": mon})
    write_json(paths.config, cfg)
    for old in sorted(os.listdir(rdir))[:-KEEP_REVISIONS]:
        os.unlink(os.path.join(rdir, old))
    return rev


def _codes_ok(v):
    """A list of status codes, each a number or a "200-399" range, all within 100 to 599."""
    if not isinstance(v, list) or not v or len(v) > 500:   # settings saved before ranges existed list every code (200 to 399 is 200 entries)
        return False
    for e in v:
        try:
            a, b = (str(e).split("-", 1) + [None])[:2] if isinstance(e, str) and "-" in e else (e, None)
            lo, hi = int(a), int(b if b is not None else a)
        except (TypeError, ValueError):
            return False
        if isinstance(e, bool) or not (100 <= lo <= hi <= 599):
            return False
    return True


def compact_codes(codes):
    """[200, 201, ..., 399, 404] -> ["200-399", 404]: a long run of codes stays readable in the saved settings."""
    nums = sorted({int(c) for c in codes if str(c).isdigit()} | {x for c in codes if isinstance(c, str) and "-" in c for x in range(int(c.split("-")[0]), int(c.split("-")[1]) + 1)})
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(nums[i] if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return out


def _slug(t):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", str(t).lower()))


def check_id(label):
    """The id Watch gives a check, from its label. Long names stay valid and distinct."""
    cid = _slug(label) or "check"
    if len(cid) > 30:
        import hashlib
        cid = cid[:24].rstrip("-") + "-" + hashlib.sha1(label.encode()).hexdigest()[:5]
    return cid


def node_slug(name):
    """A valid node id (lowercase letters, digits, dashes, at most 31 characters) from a name. A long name keeps its start and gains a short
    fingerprint of the whole name, so two long names that begin alike stay distinct."""
    sid = _slug(name) or "device"
    if len(sid) > 31:
        import hashlib
        sid = sid[:25].rstrip("-") + "-" + hashlib.sha1(name.encode()).hexdigest()[:5]
    return sid


def watched_ids(paths, cid):
    """Ids of the checks that use connection `cid` (so Re-detect can show what is already watched)."""
    mon = get_monitoring(paths)["monitoring"]
    return {c.get("id") for n in mon.get("nodes", []) for c in n.get("checks", []) if c.get("connection") == cid}


def remove_watches(paths, cid, labels):
    """Stop watching items: remove those checks (and a node too if nothing is left in it), in one save."""
    import copy
    cur = get_monitoring(paths)
    mon, rev = copy.deepcopy(cur["monitoring"]), cur["revision"]
    want, removed = {check_id(l) for l in labels}, 0
    for n in mon.get("nodes", []):
        keep = [c for c in n.get("checks", []) if not (c.get("connection") == cid and c.get("id") in want)]
        removed += len(n.get("checks", [])) - len(keep)
        if len(keep) != len(n.get("checks", [])):
            n["checks"] = keep
    gone = {n.get("id") for n in mon.get("nodes", []) if n.get("kind") != "aggregate" and not n.get("checks")}
    mon["nodes"] = [n for n in mon.get("nodes", []) if n.get("id") not in gone]
    for n in mon["nodes"]:                      # nothing may keep pointing at a system that is gone
        if gone & set(n.get("dependsOn", [])):
            n["dependsOn"] = [d for d in n["dependsOn"] if d not in gone]
        if gone & set(n.get("children", [])):
            n["children"] = [c for c in n["children"] if c not in gone]
        if gone & set(n.get("poweredBy", [])):
            n["poweredBy"] = [d for d in n["poweredBy"] if d not in gone]
    if not removed:
        return {"removed": 0, "revision": rev}
    return {"removed": removed, "revision": save_monitoring(paths, mon, rev)}


def remove_watch(paths, cid, label):
    return remove_watches(paths, cid, [label])


ITEM_KEYS = ("label", "check", "params", "node", "group", "rule", "type", "url", "expect", "insecure", "service", "requires")


def watch_item(x):
    """A discovered item as add_watches wants it: every part that matters. (Two server paths used to copy only the first six keys, which turned a
    container's web check into an empty module check and dropped the container's service details and its dependency on the environment.)"""
    return {k: x[k] for k in ITEM_KEYS if x.get(k) is not None}


# Earlier versions watched everything one integration found as checks inside ONE shared item with the 'any' rule, so a camera, switch or access
# point that was off only made that item Degraded. {old node id: (module, the summary check that is dropped, the checks that stay together, new name for those)}
SHARED_ITEMS = {"cameras": ("unifi-protect", "cameras", ("nvr", "storage"), "UniFi Protect"),
                "unifi": ("unifi-network", None, ("devices", "health"), "UniFi"),
                "scrypted": ("scrypted", "cameras", ("server",), "Scrypted")}
EACH_OWN = ("camera", "device", "tunnel")


def split_shared_items(paths):
    """Give each camera, device and tunnel its own item (rule 'primary', so an offline one is Down by name), keep the integration's overview checks together
    (the "is it there" check first) and drop the old all-cameras summary, which the cameras now say themselves. Only touches a shared item made of exactly
    that integration's checks, and does nothing the second time. Returns whether it changed anything."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    changed = False
    for old_id, (module, summary, together, together_name) in SHARED_ITEMS.items():
        old = next((n for n in mon.get("nodes", []) if n.get("id") == old_id and n.get("kind") != "aggregate" and n.get("rule") == "any"), None)
        checks = (old or {}).get("checks") or []
        known = set(together) | set(EACH_OWN) | ({summary} if summary else set())
        if not checks or not all(c.get("type") == "module" and c.get("module") == module and c.get("check") in known for c in checks):
            continue
        taken = {n.get("id") for n in mon["nodes"]} - {old_id}
        mon["nodes"].remove(old)

        def make(name):
            base = node_slug(name)
            nid, k = base, 2
            while nid in taken:
                nid, k = f"{base[:31 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
            taken.add(nid)
            n = {"id": nid, "name": name, "group": old.get("group") or "Servers", "rule": "primary", "checks": []}
            for k2 in ("critical", "dependsOn", "poweredBy"):
                if old.get(k2):
                    n[k2] = copy.deepcopy(old[k2])
            mon["nodes"].append(n)
            return n
        shared = None
        for c in sorted(checks, key=lambda c: (list(together).index(c["check"]) if c["check"] in together else 99)):
            if c["check"] == summary:
                continue
            if c["check"] in EACH_OWN:
                make(str(c.get("label") or (c.get("params") or {}).get("name") or "item"))["checks"].append(c)
            else:
                shared = shared or make(together_name)
                shared["checks"].append(c)
        for n in mon["nodes"]:
            if old_id in n.get("dependsOn", []):
                n["dependsOn"] = [d for d in n["dependsOn"] if d != old_id]
        changed = True
    if changed:
        save_monitoring(paths, mon, cur["revision"])
    return changed


def add_watches(paths, cid, items):
    """Re-detect's Watch button. Each item is {label, check, params, node?, group?}. Without `node` the check
    goes under the device that already pings this connection's host (or a new device). With `node` (a UPS,
    say) it goes in that named node and group. An item may instead be a plain web check ({type: "http", url}),
    carry `service` details for the services list, and `requires` another item (a container needs its
    environment's check): that one is added first and the new node depends on it. Earlier one-node-per-item
    entries are folded in. All in ONE save on the server, so quick taps cannot overwrite each other and a
    refusal comes with its reasons."""
    import copy
    cur = get_monitoring(paths)
    mon, rev = copy.deepcopy(cur["monitoring"]), cur["revision"]
    conn = connection(paths, cid)
    if not conn:
        raise ValueError(f"There is no connection called '{cid}'.")
    mon.setdefault("nodes", [])
    state = {"added": 0, "first": None, "changed": False}

    def new_node(name, group, taken_ids, rule="primary"):
        base = node_slug(name)
        nid, k = base, 2
        while nid in taken_ids:
            nid, k = f"{base[:31 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
        n = {"id": nid, "name": name, "group": group, "rule": rule, "checks": []}
        mon["nodes"].append(n)
        return n

    def place(it, top=True):
        label = str(it.get("label", ""))
        if it.get("type") == "http":
            spec = {"id": check_id(label), "type": "http", "url": str(it.get("url", "")), "label": label, "connection": cid}
            if it.get("expect"):
                spec["expect"] = compact_codes(it["expect"])
            if it.get("insecure"):
                spec["insecure"] = True
        else:
            spec = {"id": check_id(label), "type": "module", "module": conn["module"], "connection": cid,
                    "check": str(it.get("check", "")), "params": it.get("params") or {}, "label": label}
        req = place(it["requires"], False) if isinstance(it.get("requires"), dict) else None
        legacy = _slug(f"{cid}-{label}")[:60]
        mon["nodes"] = [n for n in mon["nodes"] if n.get("id") != legacy]       # earlier per-item nodes
        taken = {n.get("id") for n in mon["nodes"]}
        if it.get("node"):
            nid = node_slug(str(it["node"]))
            dev = next((n for n in mon["nodes"] if n.get("id") == nid), None) or new_node(str(it["node"]), str(it.get("group") or "Servers"), taken, "any" if it.get("rule") == "any" else "primary")
        else:
            host = conn.get("host")
            dev = next((n for n in mon["nodes"] if host and any(c.get("target") == host for c in n.get("checks", []))), None) \
                or next((n for n in mon["nodes"] if n.get("name") == (conn.get("name") or cid) and n.get("group") == "Servers"
                         and any(c.get("connection") == cid for c in n.get("checks", []))), None) \
                or next((n for n in mon["nodes"] if n.get("id") == node_slug(str(conn.get("name") or cid))), None) \
                or new_node(conn.get("name") or cid, "Servers", taken)
        if not it.get("node") and conn.get("name") and dev["name"] != conn["name"]:
            dev["name"] = conn["name"]       # the name the owner typed for this device is the name the main screen shows
        if top:
            state["first"] = state["first"] or dev["name"]
        if req is not None and req["id"] != dev["id"] and req["id"] not in dev.get("dependsOn", []):
            dev.setdefault("dependsOn", []).append(req["id"])
        if isinstance(it.get("service"), dict):
            merged = {**it["service"], **dev.get("service", {})}           # what the owner edited stays
            if merged != dev.get("service"):
                state["changed"] = True
            dev["service"] = merged
        broken = next((c for c in dev["checks"] if c.get("id") == spec["id"] and spec["type"] == "http" and c.get("type") == "module" and not c.get("check")), None)
        if broken is not None:            # a web check an earlier version saved without its address: replace it with the real one
            dev["checks"][dev["checks"].index(broken)] = spec
            state["added"] += 1
        elif not any(c.get("id") == spec["id"] for c in dev["checks"]):
            dev["checks"].append(spec)
            state["added"] += 1
        return dev

    # an earlier version left one system per check, all with the device's name: fold those into one, so the main screen shows one line per server
    referenced = {d for n in mon["nodes"] for d in n.get("dependsOn", [])}
    split = [n for n in mon["nodes"] if n.get("name") == (conn.get("name") or cid) and n.get("group") == "Servers" and len(n.get("checks", [])) == 1
             and n["checks"][0].get("connection") == cid and not n.get("service") and not n.get("wake") and not n.get("dependsOn") and n.get("id") not in referenced]
    if len(split) > 1:
        keep = split[0]
        for extra in split[1:]:
            keep["checks"].extend(extra["checks"])
            mon["nodes"].remove(extra)
        state["changed"] = True
    for it in items:
        place(it)
    if not state["added"] and not state["changed"]:      # a link or icon found for a service already watched is worth saving too
        return {"node": state["first"], "revision": rev, "added": 0}
    return {"node": state["first"], "revision": save_monitoring(paths, mon, rev), "added": state["added"]}


def rename_node(paths, nid, name):
    """Give a system a new display name. Its id (which checks and dependencies refer to) does not change."""
    import copy
    name = str(name or "").strip()
    if not name or len(name) > 60:
        raise Invalid(["The name must be 1 to 60 characters."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    node = next((n for n in mon.get("nodes", []) if n.get("id") == nid), None)
    if not node:
        raise Invalid([f"There is no system '{nid}' to rename (built-in ones cannot be renamed)."])
    node["name"] = name
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def set_service_link(paths, nid, url):
    """The link a row opens: a service's own address (Portainer containers keep it with their service details), or an admin page for any other
    system (a server's console, a gateway). For apps whose address cannot be found automatically (host network, a reverse proxy).
    An empty address removes the link."""
    import copy
    url = str(url or "").strip()
    if url and (not url.startswith(("http://", "https://")) or len(url) > 300 or " " in url):
        raise Invalid(["The link must start with http:// or https:// and have no spaces."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    node = next((n for n in mon.get("nodes", []) if n.get("id") == nid), None)
    if not node:
        raise Invalid([f"There is no system '{nid}' (built-in ones cannot have a link)."])
    holder = node["service"] if isinstance(node.get("service"), dict) else node
    key = "url" if holder is not node else "link"
    if url:
        holder[key] = url
    else:
        holder.pop(key, None)
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def set_check_url(paths, nid, cid, url):
    """Change the address a web check opens (an app moved its page, a port changed). The check starts fresh; everything else about it stays."""
    import copy
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")) or " " in url or len(url) > 300:
        raise Invalid(["The address must start with http:// or https:// and have no spaces."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    node = next((n for n in mon.get("nodes", []) if n.get("id") == nid), None)
    chk = next((c for c in (node or {}).get("checks", []) if c.get("id") == cid and c.get("type") == "http"), None)
    if not chk:
        raise Invalid([f"There is no web check '{cid}' on '{nid}' to change."])
    chk["url"] = url
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def ensure_server(paths, name, host, probe_ping=None, probe_tcp=None):
    """Every server gets a system with a reachability check first, so everything picked later (SNMP, UPS, UniFi...) goes under that one line.
    A ping check, unless the machine does not answer pings: then a plain TCP check on the first usual port that answers. A server that already has
    either check is left alone. Returns {id, name, created}."""
    import copy, ipaddress, re as _re
    name, host = str(name or "").strip() or str(host or "").strip(), str(host or "").strip().lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host):
            raise Invalid(["The address must be an IP address or a host name."])
    if not name or len(name) > 60:
        raise Invalid(["The name must be 1 to 60 characters."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    nodes = mon.setdefault("nodes", [])
    have = next((n for n in nodes if any(str(c.get("target", "")).lower() == host and c.get("type") in ("ping", "tcp") for c in n.get("checks", []))), None)
    if have:
        return {"id": have["id"], "name": have.get("name"), "created": False, "revision": cur["revision"]}
    check = {"id": "ping", "type": "ping", "target": host}
    if probe_ping and probe_ping(host) is False:
        for port in (443, 22, 80, 9443, 9000, 3493, 161, 10443):
            if probe_tcp and probe_tcp(host, port):
                check = {"id": f"tcp-{port}", "type": "tcp", "target": host, "port": port}
                break
    taken = {n.get("id") for n in nodes}
    base, nid, k = node_slug(name), node_slug(name), 2
    while nid in taken:
        nid, k = f"{base[:31 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
    nodes.append({"id": nid, "name": name, "group": "Servers", "rule": "primary", "checks": [check]})
    return {"id": nid, "name": name, "created": True, "revision": save_monitoring(paths, mon, cur["revision"])}


def add_ping(paths, name, target, system=None):
    """Watch an address with a plain ping, by hand. With `system` (a node id) the check joins that system; otherwise it becomes a system of its own."""
    import copy, ipaddress, re as _re
    name, target = str(name or "").strip(), str(target or "").strip()
    errs = []
    if not name or len(name) > 60:
        errs.append("The name must be 1 to 60 characters.")
    try:
        ipaddress.ip_address(target)
    except ValueError:
        if not _re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", target):
            errs.append("The address must be an IP address or a host name.")
    if errs:
        raise Invalid(errs)
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    nodes = mon.setdefault("nodes", [])
    cid = "ping-" + node_slug(target)[:40]
    if system:
        node = next((n for n in nodes if n.get("id") == system), None)
        if node is None:
            raise Invalid([f"There is no system '{system}'."])
        if any(c.get("id") == cid for c in node.get("checks", [])):
            return {"revision": cur["revision"], "added": 0}
        node.setdefault("checks", []).append({"id": cid, "type": "ping", "target": target})
    else:
        have = {n.get("id") for n in nodes}
        base = node_slug(name)
        nid, k = base, 2
        while nid in have:
            nid, k = f"{base[:31 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
        nodes.append({"id": nid, "name": name, "group": "Servers", "rule": "primary", "checks": [{"id": "ping", "type": "ping", "target": target}]})
    return {"revision": save_monitoring(paths, mon, cur["revision"]), "added": 1}


def add_web_page(paths, name, url, system=None, group="Services", contains=None, expect=None, insecure=False, link=None):
    """Watch a web page by hand: a server's admin console, a gateway's login page, an app that is not a container.
    With `system` (an id) the check joins that system, which then reads Degraded if the page stops answering while the
    rest is fine; otherwise it becomes a system of its own in `group`. The page's address (or `link`) becomes the system's
    "open" link unless it already has one."""
    import copy
    name, url = str(name or "").strip(), str(url or "").strip()
    errs = []
    if not name or len(name) > 60:
        errs.append("The name must be 1 to 60 characters.")
    if not url.startswith(("http://", "https://")) or " " in url or len(url) > 300:
        errs.append("The address must start with http:// or https:// and have no spaces.")
    link = str(link or "").strip() or url
    if not link.startswith(("http://", "https://")) or " " in link or len(link) > 300:
        errs.append("The link must start with http:// or https:// and have no spaces.")
    exp = list(expect or [])
    if exp and not _codes_ok(exp):
        errs.append("Expected status codes are numbers from 100 to 599, or ranges like 200-399.")
    contains = str(contains or "").strip()
    if len(contains) > 100:
        errs.append("The text the page must contain is at most 100 characters.")
    group = str(group or "Services").strip()[:40] or "Services"
    if errs:
        raise Invalid(errs)
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    mon.setdefault("nodes", [])
    spec = {"type": "http", "url": url, "label": name}
    if exp:
        spec["expect"] = compact_codes(exp)
    if contains:
        spec["contains"] = contains
    if insecure and url.startswith("https"):
        spec["insecure"] = True
    if system:
        node = next((n for n in mon["nodes"] if n.get("id") == system and n.get("kind") != "aggregate"), None)
        if not node:
            raise Invalid([f"There is no system '{system}' to add a web page to."])
    else:
        taken = {n.get("id") for n in mon["nodes"]}
        base, nid, k = node_slug(name), node_slug(name), 2
        while nid in taken:
            nid, k = f"{base[:31 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
        node = {"id": nid, "name": name, "group": group, "rule": "primary", "checks": []}
        mon["nodes"].append(node)
    have = {c.get("id") for c in node.get("checks", [])}
    base, cid, k = check_id(name), check_id(name), 2
    while cid in have:
        cid, k = f"{base[:30 - len(str(k)) - 1].rstrip('-')}-{k}", k + 1
    node.setdefault("checks", []).append({"id": cid, **spec})
    if not node.get("link") and not isinstance(node.get("service"), dict):
        node["link"] = link
    return {"node": node["id"], "revision": save_monitoring(paths, mon, cur["revision"])}


def add_network(paths, gateway=None, dns=()):
    """First-run setup: watch the gateway and the LAN's DNS servers. Ids that already exist are left alone, so running
    it twice (or on a box that already has them) changes nothing."""
    import copy, ipaddress
    def ip4(v):
        try:
            a = ipaddress.ip_address(str(v).strip())
        except ValueError:
            raise Invalid([f"'{v}' is not an IP address."])
        if a.version != 4:
            raise Invalid([f"'{v}' is not an IPv4 address."])
        return str(a)
    gateway = ip4(gateway) if gateway else None
    dns = list(dict.fromkeys(ip4(d) for d in dns))
    if len(dns) > 8:
        raise Invalid(["That is more than 8 DNS servers."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    nodes = mon.setdefault("nodes", [])
    have = {n.get("id") for n in nodes}
    added = []
    def add(n):
        if n["id"] not in have:
            nodes.append(n); have.add(n["id"]); added.append(n["id"])
    if gateway:
        add({"id": "gateway", "name": "Gateway", "group": "Network", "critical": True, "rule": "primary",
             "checks": [{"id": "ping", "type": "ping", "target": gateway}]})
    dep = ["gateway"] if "gateway" in have else []
    kids = []
    for ip in dns:
        nid = "dns-" + ip.replace(".", "-")
        add({"id": nid, "name": f"DNS {ip}", "group": "DNS", "critical": False, "dependsOn": dep, "rule": "primary",
             "checks": [{"id": "dns", "type": "dns", "server": ip, "name": "google.com"}]})
        kids.append(nid)
    if len(kids) > 1:
        add({"id": "dns", "name": "DNS", "group": "DNS", "critical": False, "dependsOn": dep, "kind": "aggregate",
             "children": kids, "rule": "any"})
    if not added:
        return {"revision": cur["revision"], "added": []}
    return {"revision": save_monitoring(paths, mon, cur["revision"]), "added": added}


def set_confirm(paths, nid, failures, seconds):
    """Give one system its own grace period (failures in a row, seconds), or None to use the site default again."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    node = next((n for n in mon.get("nodes", []) if n.get("id") == nid and n.get("kind") != "aggregate"), None)
    if not node:
        raise Invalid([f"There is no system '{nid}' with its own checks to set this on (built-in ones use the site default)."])
    for key, v in (("confirmFailures", failures), ("confirmSeconds", seconds)):
        if v is None:
            node.pop(key, None)
        else:
            node[key] = v
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


HEAT_CHECKS = {"temperature": 80, "drive": 55}      # the module checks that have a temperature limit, and the limit used when none is set (degrees C)


def set_limit(paths, nid, max_c):
    """Give one device's or drive's temperature check its own warning limit in degrees C, or None to use the built-in one again."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    node = next((n for n in mon.get("nodes", []) if n.get("id") == nid and n.get("kind") != "aggregate"), None)
    checks = [c for c in (node or {}).get("checks", []) if c.get("type") == "module" and c.get("check") in HEAT_CHECKS]
    if not checks:
        raise Invalid([f"'{nid}' has no temperature check to set a limit on."])
    if max_c is not None:
        if isinstance(max_c, bool) or not isinstance(max_c, (int, float)) or not 20 <= max_c <= 150:
            raise Invalid(["The limit must be a number of degrees between 20 and 150, or empty for the built-in one."])
    for c in checks:
        params = dict(c.get("params") or {})
        if max_c is None:
            params.pop("max_c", None)
        else:
            params["max_c"] = max_c
        c["params"] = params
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def set_expected(paths, nid, on):
    """Mark a system as down on purpose (or clear it). Only alerts and the banner care; what is observed is unchanged."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    known = {n.get("id") for n in mon.get("nodes", [])} | {n["id"] for n in builtin_internet(set()) if mon.get("builtinInternet", True) is not False}
    if nid not in known:
        raise Invalid([f"There is no system '{nid}'."])
    ids = [x for x in mon.get("expectedDown", []) if x != nid]
    if on:
        ids.append(nid)
    if ids:
        mon["expectedDown"] = sorted(ids)
    else:
        mon.pop("expectedDown", None)
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def set_critical(paths, ids, on):
    """Mark systems as critical (or clear it): when a critical one is Down the whole banner goes red with the loudest message. Only what the owner set up can change;
    the built-in internet checks stay as they are. Several ids are saved together."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    by = {n.get("id"): n for n in mon.get("nodes", [])}
    bad = [i for i in ids if i not in by]
    if bad:
        raise Invalid([f"'{bad[0]}' is built in or no longer exists, so its importance cannot be changed here."])
    for i in ids:
        if on:
            by[i]["critical"] = True
        else:
            by[i].pop("critical", None)
    return {"revision": save_monitoring(paths, mon, cur["revision"])}


def _prune(mon, gone):
    """Take the nodes in `gone` out of mon, then anything left pointing at them: a group with nothing left in it goes too,
    and dependsOn, children and expectedDown forget them. Returns the full set of removed ids."""
    gone = set(gone)
    nodes = [n for n in mon.get("nodes", []) if n.get("id") not in gone]
    while True:
        empty = {n["id"] for n in nodes if n.get("kind") == "aggregate" and not [c for c in n.get("children", []) if c not in gone]}
        if not empty - gone:
            break
        gone |= empty
        nodes = [n for n in nodes if n["id"] not in gone]
    for n in nodes:
        if n.get("dependsOn"):
            n["dependsOn"] = [d for d in n["dependsOn"] if d not in gone]
        if n.get("children"):
            n["children"] = [c for c in n["children"] if c not in gone]
    mon["nodes"] = nodes
    if mon.get("expectedDown"):
        mon["expectedDown"] = [x for x in mon["expectedDown"] if x not in gone] or None
        if mon["expectedDown"] is None:
            del mon["expectedDown"]
    return gone


def remove_connection(paths, cid):
    """Remove a service connection whatever is using it: its checks go (a system left with none goes too), then the connection.
    Removing something that is broken is how people fix it, so this never refuses for being in use."""
    import copy
    cfg = load_config(paths)
    conns = [c for c in cfg.get("connections", []) if isinstance(c, dict)]
    if not any(c.get("id") == cid for c in conns):
        raise Invalid([f"There is no connection '{cid}'."])
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    gone, dropped = set(), 0
    for n in mon.get("nodes", []):
        ks = n.get("checks")
        if ks and any(k.get("connection") == cid for k in ks):
            n["checks"] = [k for k in ks if k.get("connection") != cid]
            dropped += len(ks) - len(n["checks"])
            if not n["checks"]:
                gone.add(n["id"])
    gone = _prune(mon, gone)
    if gone or dropped:
        save_monitoring(paths, mon, cur["revision"])
    cfg = load_config(paths)
    rev = save_connections(paths, [c for c in cfg.get("connections", []) if c.get("id") != cid], cfg.get("revision", 0))
    return {"revision": rev, "removed": sorted(gone), "checksDropped": dropped}


def sync_nodes(paths, prefix, desired):
    """Keep the nodes whose id starts with `prefix` equal to `desired` (a list of node dicts): added, renamed, removed. Used for the
    systems that follow a pairing (a link to each managed site, a note of each managing box). Writes only when something changed."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    nodes = mon.get("nodes", [])
    have = {n["id"]: n for n in nodes if str(n.get("id", "")).startswith(prefix)}
    want = {n["id"]: n for n in desired}
    shape = lambda n: (n.get("name"), n.get("group"), [(c.get("type"), c.get("site"), c.get("manager")) for c in n.get("checks", [])])
    if set(have) == set(want) and all(shape(have[i]) == shape(want[i]) for i in want):
        return None
    gone = set(have) - set(want)
    out = []
    for n in nodes:
        i = n.get("id")
        if i in want:
            out.append(copy.deepcopy(want[i]))          # in the same place
        elif i not in gone:
            out.append(n)
    out += [copy.deepcopy(n) for i, n in want.items() if i not in have]
    mon["nodes"] = out
    if gone:
        _prune(mon, gone)
    return save_monitoring(paths, mon, cur["revision"])


def remove_node(paths, nid, with_children=False):
    """Stop watching a whole system: its checks go, and so does anything left pointing at it. Connections stay.
    with_children: for a group, the systems inside it go too (how a renamed Portainer environment's old group is cleared away)."""
    import copy
    cur = get_monitoring(paths)
    mon = copy.deepcopy(cur["monitoring"])
    nodes = mon.get("nodes", [])
    if not any(n.get("id") == nid for n in nodes):
        raise Invalid(["The built-in internet checks cannot be stopped here." if any(b["id"] == nid for b in builtin_internet(set())) else f"There is no system '{nid}'."])
    gone = {nid}
    if with_children:
        top = next(n for n in nodes if n.get("id") == nid)
        if top.get("kind") == "aggregate":
            gone |= {c for c in top.get("children", []) if any(n.get("id") == c for n in nodes)}
    gone = _prune(mon, gone)
    return {"revision": save_monitoring(paths, mon, cur["revision"]), "removed": sorted(gone)}


def add_watch(paths, cid, label, check, params, node=None, group=None):
    return add_watches(paths, cid, [{"label": label, "check": check, "params": params, "node": node, "group": group}])


# ---- connections: how to reach a device (host, login, ...). Settings are the module's business. ----
def masked(conns):
    """Copies of the connections with every secret-looking field replaced by dots (for the editor)."""
    out = []
    for c in conns:
        out.append({k: (MASK if SECRET_RE.search(k) and isinstance(v, str) and v else v) for k, v in c.items()})
    return out


def get_connections(paths):
    cfg = load_config(paths)
    return {"revision": cfg.get("revision", 0), "connections": masked(cfg.get("connections", []))}


def validate_connections(conns):
    errs = []
    if not isinstance(conns, list):
        return ["connections must be a list"]
    ids = [c.get("id") if isinstance(c, dict) else None for c in conns]
    for i, c in enumerate(conns):
        where = f"connection {i + 1}" + (f" '{c.get('id')}'" if isinstance(c, dict) and c.get("id") else "")
        if not isinstance(c, dict):
            errs.append(f"{where}: must be an object")
            continue
        if not isinstance(c.get("id"), str) or not ID_RE.match(c["id"]):
            errs.append(f"{where}: id must be lowercase letters, digits and dashes")
        elif ids.count(c["id"]) > 1:
            errs.append(f"{where}: id used more than once")
        if not isinstance(c.get("module"), str) or not MODULE_RE.match(c["module"]):
            errs.append(f"{where}: module must be a module id such as snmp")
    return errs


def save_connections(paths, conns, base_revision):
    """Same rules as monitoring: validate first, refuse on a stale revision, write atomically.
    A secret sent back as dots keeps its stored value, so the editor never needs to show it."""
    errs = validate_connections(conns)
    cfg = load_config(paths)
    old = {c.get("id"): c for c in cfg.get("connections", []) if isinstance(c, dict)}
    if not errs:
        for c in conns:
            for k, v in c.items():
                if v == MASK:
                    if k in old.get(c["id"], {}):
                        c[k] = old[c["id"]][k]
                    else:
                        errs.append(f"connection '{c['id']}': enter a real value for '{k}'")
        _nodes, merrs = validate(cfg.get("monitoring", {"builtinInternet": True, "nodes": []}), {c["id"] for c in conns})
        errs += [e for e in merrs if "does not exist" in e and "connection" in e]
    if errs:
        raise Invalid(errs)
    if cfg.get("revision", 0) != base_revision:
        raise Conflict(f"The configuration changed since you loaded it (now revision {cfg.get('revision', 0)}). Reload and try again.")
    rev = cfg.get("revision", 0) + 1
    for c in conns:       # a server's name is also what the main screen calls it: renaming one renames the other
        nm, was = str(c.get("name") or "").strip(), str((old.get(c["id"]) or {}).get("name") or "").strip()
        if c.get("module") == "snmp" and nm and nm != was:
            held = [n for n in (cfg.get("monitoring") or {}).get("nodes", []) if isinstance(n, dict)
                    and any(isinstance(k, dict) and k.get("connection") == c["id"] for k in n.get("checks", []))]
            if len(held) == 1:
                held[0]["name"] = nm
    cfg["connections"], cfg["revision"], cfg["schema"] = conns, rev, 4
    rdir = os.path.join(os.path.dirname(paths.config), "revisions")
    write_json(os.path.join(rdir, f"{rev:06d}.json"), {"revision": rev, "monitoring": cfg.get("monitoring")})  # no secrets in history
    write_json(paths.config, cfg)
    for stale in sorted(os.listdir(rdir))[:-KEEP_REVISIONS]:
        os.unlink(os.path.join(rdir, stale))
    return rev


def connection(paths, cid):
    """The full stored settings (secrets included) for the module that runs a check. Never sent to the browser."""
    return next((c for c in load_config(paths).get("connections", []) if isinstance(c, dict) and c.get("id") == cid), None)
