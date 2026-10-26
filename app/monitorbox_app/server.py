from concurrent.futures import ThreadPoolExecutor
import sys, shutil, base64, json, os, re, secrets, socket, threading, time
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

from .modules import current as modules_current
from . import liverelay, version, updates, versions, monconfig, demo, engine, sysinfo, backups, probes
from .history import History
from . import thisbox, followups, graphs, alerts, peer, perfstats, lanmap, portpeers, lansampler, busiest, security, passkeys
from .monitor import Monitor
from .auth import Auth
from .modules import Modules
from .store import Paths, read_json
from .ui import PAGE

RESTART_EXIT = 75



BRAND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brand")
BRAND_ROUTES = {"/favicon.ico": ("favicon-64.png", "image/png"), "/favicon.svg": ("mark.svg", "image/svg+xml"),
                "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"), "/brand/icon-192.png": ("icon-192.png", "image/png"),
                "/brand/icon-512.png": ("icon-512.png", "image/png"), "/brand/icon-maskable-512.png": ("icon-maskable-512.png", "image/png"), "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
                "/brand/sora.ttf": ("sora.ttf", "font/ttf"), "/brand/figtree.ttf": ("figtree.ttf", "font/ttf")}
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
ICON_ALIASES = {"home-assistant": "homeassistant", "pi-hole": "pihole", "overseerr": "seerr", "jellyseerr": "seerr", "qbittorrent-nox": "qbittorrent"}


def plain_error(msg):
    """A device's error in words an owner can act on. The raw message is kept next to it for anyone who wants it."""
    m = msg.lower()
    if any(w in m for w in ("wrongdigest", "unknownusername", "unsupportedsecurity", "decrypt", "authentication fail", "not in time window", "usm")):
        return "The device answered but refused the login. Check the user name, the passwords and the encryption types."
    if any(w in m for w in ("401", "403", "unauthorized", "forbidden", "invalid credentials", "login failed", "login refused", "bad username", "username or password", "login was refused", "refused this account")):
        return "The device refused the user name or password."
    if "certificate" in m or "ssl" in m:
        return ("The device's security certificate is not trusted (often it is self-signed, which is normal for Portainer and UniFi). "
                "If you trust this device on your own network, turn off 'Check the certificate' and test again.")
    if "refused" in m:
        return "The device refused the connection. Is the service turned on, and is the port right?"
    if any(w in m for w in ("timed out", "timeout", "no response", "did not answer")):
        return "Nothing answered at that address. Check the address and port, and that the device allows MonitorBox to ask it."
    if any(w in m for w in ("unreachable", "no route", "name or service", "getaddrinfo", "nodename")):
        return "MonitorBox cannot reach that address from here."
    return "The device did not accept the request: " + msg[:200]

class App:
    def __init__(self, root, releases_url, channel, port):
        self.paths = Paths(root)
        self.releases_url = releases_url
        self.default_channel = channel
        self.port = port
        self.auth = Auth(self.paths)
        self.security = security.Security(self.paths)
        self.passkeys = passkeys.Passkeys(self.paths)
        self.modules = Modules(self.paths, updates.install_archive)
        self.modules.wanted = self.used_modules
        self.exit_code = None
        self.wipe = False
        self.httpd = None
        self.infos = {}           # repository id -> last fetched {"catalog","pointer","error"} for the current channel
        self.info_channel = None
        self.checked_at = None
        self.check_error = None
        self.check_seconds = int(os.environ.get("MB_CHECK_SECONDS", "1800"))
        self.thisbox_scan = thisbox.scan      # replaceable in tests
        self.history = History(os.path.join(self.paths.root, "config", "history.jsonl"))
        self.monitor = Monitor(runner=self.run_check, history=self.history)
        self.wakes = {}   # node id -> {state, detail, at}; state: sending | waiting | up | timeout | error
        self.wake_lock = threading.Lock()
        self.pt_cache, self.pt_running = {}, set()
        self.web_cache = {"at": 0.0, "out": [], "running": False}      # web pages found on known addresses, looked for every 10 minutes   # Portainer's last answer per connection, for the follow-ups
        self.dismissed_file = self.paths.p("config", "dismissed-followups.json")
        self.seen_file = self.paths.p("config", "seen-items.json")        # per connection: the items already known, so only new ones are offered
        self.sweep = {"at": 0.0, "running": False, "out": {}}
        self.sw_cache = {"at": 0.0, "running": False, "key": None, "source": None, "answered": []}      # UniFi switches that answer the saved SNMP login
        self.display_file = self.paths.p("config", "display.json")
        try:
            self.apply_timezone()
        except Exception:
            pass
        self.graphs_file = self.paths.p("config", "graphs.json")
        self.graphs = graphs.Graphs(lambda: read_json(self.graphs_file, []) or [], self.graph_sample)
        self.series = portpeers.PortSeries()          # the last hour of every switch port's traffic, for "where does it go"
        self.last_map = None
        self.last_sources = []           # what every source said when the map was last built (the SNMP ones say which MAC each interface has)
        self.gw_cache = {}
        self.minute_flows = []           # the gateway's flow log for the last minute, kept fresh by flow_loop, for the Busiest client
        self.busiest = busiest.Busiest(self.series)
        self.lansampler = lansampler.LanSampler(self.series, lambda: monconfig.load_config(self.paths).get("connections", []), lambda m, meth, p, t: self.modules.call(m, meth, p, t),
                                                after=lambda: self.last_map and self.busiest.update(self.last_map, flows=self.minute_flows, opts=self.busiest_opts()))
        self.alerts = alerts.Alerts(self.paths.p("config", "alerts.json"), self.paths.p("config", "alerts-state.json"), self.monitor.snapshot,
                                   hostname=lambda: self.peer.name())     # alerts say the site's own name (Settings, Sites), the computer name only when none is set
        self.peer = peer.Peer(self.paths.p("config", "sites.json"), self.port, self.internal_session, version)
        self.peer.relay_lookup = self.live_relay
        self.peer.on_change = self.sync_site_nodes
        self.relays = liverelay.Registry()            # live views of managed sites whose media passes through this box
        self.port_open = followups.tcp_open   # replaceable in tests
        self.demo = None  # a demo scenario name while the owner is previewing screens; never persisted

    def snapshot(self):
        if self.demo:
            nodes, res = demo.build(self.demo)
            snap = engine.evaluate(nodes, res, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            snap["version"], snap["configError"] = self.monitor.version, None
        else:
            snap = self.monitor.snapshot()
        snap["demo"] = self.demo
        snap["wakes"] = self.wake_view()
        return snap

    # -- wake on LAN: send the packets, then confirm the machine really answers ------
    def wake_view(self):
        now = time.time()
        with self.wake_lock:  # a finished wake stays visible for two minutes
            return {k: {"state": v["state"], "detail": v["detail"]} for k, v in self.wakes.items()
                    if v["state"] in ("sending", "waiting") or now - v["at"] < 120}

    def _wake_set(self, nid, state, detail):
        with self.wake_lock:
            self.wakes[nid] = {"state": state, "detail": detail, "at": time.time()}
        with self.monitor.lock:
            self.monitor._bump()  # push to every open screen

    def wake(self, nid):
        nodes, _err = monconfig.all_nodes(self.paths)
        node = next((n for n in nodes if n["id"] == nid), None)
        if not node or not node.get("wake"):
            raise ValueError("That system has no wake settings. Add a 'wake' block with its MAC addresses.")
        with self.wake_lock:
            cur = self.wakes.get(nid)
            if cur and cur["state"] in ("sending", "waiting"):
                return {"state": cur["state"], "detail": cur["detail"]}
        self._wake_set(nid, "sending", f"Sending wake packets to {node['name']}…")
        threading.Thread(target=self._wake_job, args=(node,), daemon=True, name=f"wake-{nid}").start()
        return {"state": "sending", "detail": f"Sending wake packets to {node['name']}…"}

    def _wake_job(self, node):
        nid, w = node["id"], node["wake"]
        timeout, retry = w.get("timeout", 120), w.get("retry", 30)
        started = time.monotonic()
        next_send, sends = 0.0, 0
        try:
            while True:
                el = time.monotonic() - started
                if el >= next_send:
                    params = {"macs": w["macs"], "broadcast": w.get("broadcast", "255.255.255.255"), "port": w.get("port", 9)}
                    sent = self.modules.call("wol", "wake", params, timeout=10)["sent"]
                    sends += 1
                    next_send = el + retry
                    self._wake_set(nid, "waiting", f"Sent {sent} wake packet{'s' if sent != 1 else ''} (try {sends}). "
                                                   f"Waiting for {node['name']} to answer, up to {int(timeout)} s…")
                self.monitor.check_now(nid, wait=True)   # the confirmation: its own checks, run right now
                if self.monitor.snapshot()["nodes"][nid]["state"] in ("healthy", "degraded"):
                    self._wake_set(nid, "up", f"{node['name']} is up (answered after {int(time.monotonic() - started)} s).")
                    return
                if time.monotonic() - started >= timeout:
                    self._wake_set(nid, "timeout", f"{node['name']} did not answer within {int(timeout)} s. "
                                                   f"Check the MAC addresses and that Wake on LAN is on in its BIOS and network card.")
                    return
                time.sleep(2)
        except Exception as e:
            self._wake_set(nid, "error", f"Could not send the wake packets: {e}")

    def set_demo(self, name):
        if name not in (None, *demo.SCENARIOS):
            raise ValueError("unknown demo scenario")
        self.demo = name
        with self.monitor.lock:
            self.monitor._bump()  # wake every open screen

    def run_check(self, check):
        """The one place a check is run: built-in probes here, everything else asks its module."""
        if check["type"] == "site":
            return self.peer.link_check(check["site"])
        if check["type"] == "manager":
            return self.peer.manager_check(check["manager"])
        if check["type"] != "module":
            return probes.run(check)
        cid = check.get("connection")
        conn = monconfig.connection(self.paths, cid) if cid else {}
        if cid and conn is None:
            return None, f"connection '{cid}' is not configured", None, {}
        return self.modules.check(check, conn)

    def detect(self, cid):
        """Re-detect: ask the connection's module what the device offers right now (read-only)."""
        conn = monconfig.connection(self.paths, cid)
        if not conn:   # ids are typed on a tablet: match without regard to case
            conn = next((c for c in monconfig.load_config(self.paths).get("connections", [])
                         if isinstance(c, dict) and str(c.get("id", "")).lower() == cid.strip().lower()), None)
        if not conn:
            raise ValueError(f"There is no connection called '{cid}'.")
        try:
            out = self.modules.call(conn["module"], "discover", {"connection": conn}, 30)
            if isinstance(out, dict):
                have = monconfig.watched_ids(self.paths, conn["id"])
                for sug in out.get("suggest", []):
                    sug["watching"] = monconfig.check_id(sug["label"]) in have
                out["connection"] = conn["id"]
                if conn["module"] == "snmp" and not out.get("sysName"):          # an SNMP module that does not report its name yet: read it from the uptime line ("Granite: up 3d ...")
                    try:
                        r = self.modules.call("snmp", "check", {"check": "uptime", "params": {}, "connection": conn}, 12)
                        m = re.match(r"^(.+?): up ", str((r or {}).get("detail", "")))
                        out["sysName"] = m.group(1) if m else ""
                    except Exception:
                        pass
            return out
        except Exception as e:
            raise ValueError(f"Could not read the device: {e}")

    def test_connection(self, conn_in):
        """Test connection: ask the module what this device offers, using the settings typed in the form (not yet saved).
        A secret still shown as dots is filled in from the saved copy of the same connection. Read-only."""
        if not isinstance(conn_in, dict):
            raise ValueError("Nothing to test.")
        conn = dict(conn_in)
        saved = monconfig.connection(self.paths, conn.get("id")) if conn.get("id") else None
        for k, v in list(conn.items()):
            if v == monconfig.MASK:
                if not (saved and k in saved):
                    raise ValueError("Type the password again to test it; it has not been saved yet.")
                conn[k] = saved[k]
        module = conn.get("module")
        if not isinstance(module, str) or not module:
            raise ValueError("Choose what kind of device this is.")
        if not (conn.get("host") or conn.get("base_url")):
            raise ValueError("Enter the address of the device.")
        t0 = time.time()
        try:
            out = self.modules.call(module, "discover", {"connection": conn}, 30)
        except Exception as e:
            return {"ok": False, "seconds": round(time.time() - t0, 1), "error": plain_error(str(e)), "detail": str(e)}
        found = {}
        for sug in (out.get("suggest") or []) if isinstance(out, dict) else []:
            found[sug.get("batch") or "Items"] = found.get(sug.get("batch") or "Items", 0) + 1
        return {"ok": True, "seconds": round(time.time() - t0, 1), "found": [{"label": k, "count": n} for k, n in found.items()]}

    CAMERA_SOURCES = ("unifi-protect", "scrypted")      # modules that answer `cameras` and `snapshot` in the source-neutral camera shape, in the order their picture is preferred

    def cameras(self):
        """Every camera from every connected camera source, in one list. One source being down does not hide the others.
        A camera that two sources both report (same name, as with Protect and Scrypted) shows once, from the preferred source, with the others in `alsoIn`."""
        conns = [c for c in monconfig.load_config(self.paths).get("connections", [])
                 if isinstance(c, dict) and c.get("module") in self.CAMERA_SOURCES]
        conns.sort(key=lambda c: self.CAMERA_SOURCES.index(c["module"]))
        out, errors, byname = [], [], {}
        for c in conns:
            try:
                got = self.modules.call(c["module"], "cameras", {"connection": c}, 20)
            except Exception as e:
                errors.append({"connection": c.get("id"), "error": plain_error(str(e))})
                continue
            for cam in (got or {}).get("cameras", []):
                key = str(cam.get("name", "")).strip().lower()
                via = {"connection": c.get("id"), "id": cam.get("id")} if c["module"] == "scrypted" and cam.get("live") else None
                if key in byname:
                    byname[key].setdefault("alsoIn", []).append(c["module"])
                    if via and "liveVia" not in byname[key]:
                        byname[key]["liveVia"] = via
                    continue
                byname[key] = {**cam, "connection": c.get("id")}
                if via:
                    byname[key]["liveVia"] = via                        # live video comes from Scrypted, even for a camera Protect shows
                out.append(byname[key])
        out.sort(key=lambda x: str(x.get("name", "")).lower())
        return {"cameras": out, "errors": errors}

    def camera_snapshot(self, conn_id, cam_id):
        """(content type, bytes) of one camera's current picture. Only for a saved camera source; the module checks the camera id."""
        c = monconfig.connection(self.paths, conn_id)
        if not c or c.get("module") not in self.CAMERA_SOURCES:
            raise ValueError("That is not a camera source.")
        got = self.modules.call(c["module"], "snapshot", {"connection": c, "id": cam_id}, 20)
        return got["mime"], base64.b64decode(got["data"])

    # -- live video (WebRTC through Scrypted): MonitorBox only passes the setup messages; the video flows between Scrypted and the browser --
    LIVE_MAX = 10
    LIVE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

    def _live_state(self):
        if not hasattr(self, "_live"):
            self._live = {"lock": threading.Lock(), "clients": {}, "sessions": {}}
        return self._live

    def live_hub_open(self, cid):
        """One setup-message channel per open page (a browser only allows a few connections to this box, so every camera shares it)."""
        import queue
        if not self.LIVE_ID.match(cid or ""):
            raise ValueError("bad live channel id")
        st = self._live_state()
        with st["lock"]:
            if cid in st["clients"]:
                raise ValueError("that live channel is already open")
            q = st["clients"][cid] = queue.Queue()
            return q

    def live_hub_close(self, cid):
        st = self._live_state()
        with st["lock"]:
            st["clients"].pop(cid, None)
            mine = [sid for sid, s in st["sessions"].items() if s["client"] == cid]
        for sid in mine:
            self.live_close(sid)

    def _relay_learn(self, r, cands):
        """Scrypted's own address, from the candidates it offered: where the relay sends the browser's packets (until real packets say otherwise)."""
        r["cands"] += cands
        if r["pipe"].sent == 0:
            t = liverelay.pick_target(r["cands"], r["host"])
            if t:
                r["pipe"].target = t

    def _live_answer(self, sid, call_id):
        try:
            self.modules.call("scrypted", "live_input", {"session": sid, "message": {"type": "result", "callId": call_id, "value": None}}, 10)
        except Exception:
            pass

    def _live_event(self, sid, message):
        st = self._live_state()
        with st["lock"]:
            s = st["sessions"].get(sid)
            q = st["clients"].get(s["client"]) if s else None
            r = s.get("relay") if s else None
        if r and message.get("type") == "call":
            a = message.get("args") or []
            first = a[0] if a and isinstance(a[0], dict) else {}
            if message.get("method") == "addIceCandidate":
                self._relay_learn(r, liverelay.parse_candidate_attr(first.get("candidate")))
                threading.Thread(target=self._live_answer, args=(sid, message.get("callId")), daemon=True).start()
                return                                  # the browser is not told Scrypted's own addresses: it is given the relay's instead
            if message.get("method") == "setRemoteDescription" and "sdp" in first:
                self._relay_learn(r, liverelay.parse_candidates(first["sdp"]))
                message = dict(message, args=[dict(first, sdp=liverelay.strip_candidates(first["sdp"]))] + list(a[1:]))
        if q is not None:
            q.put({"session": sid, "message": message})
        if message.get("type") == "closed":
            self._live_forget(sid)

    def _live_forget(self, sid):
        st = self._live_state()
        with st["lock"]:
            s = st["sessions"].pop(sid, None)
        if s:
            self.modules.unlisten(s["module"], sid)
            if s.get("relay"):
                s["relay"]["pipe"].close()

    def live_open(self, cid, conn_id, cam_id, options, relay=False):
        c = monconfig.connection(self.paths, conn_id)
        if not c or c.get("module") != "scrypted":
            raise ValueError("Live video comes from Scrypted only.")
        st = self._live_state()
        with st["lock"]:
            if cid not in st["clients"]:
                raise ValueError("The live channel is not open.")
            if len(st["sessions"]) >= self.LIVE_MAX:
                raise ValueError(f"Too many live views are open ({self.LIVE_MAX}). Close some and try again.")
            sid = secrets.token_urlsafe(12)
            rl = None
            if relay:      # a managing box asked for the media to come through the site link: a UDP port here, aimed at Scrypted
                try:
                    host = peer.parse_address(c.get("host") or "")[0]
                    rl = {"pipe": liverelay.Pipe(), "ip": liverelay.local_ip_toward(host), "host": socket.gethostbyname(host), "cands": [], "sent": False}
                except (OSError, ValueError):
                    raise ValueError("This box could not work out which of its addresses reaches Scrypted.")
            st["sessions"][sid] = {"client": cid, "module": "scrypted", "t": time.time(), "relay": rl}
        if not isinstance(options, dict) or len(json.dumps(options)) > 20000:
            options = {}
        try:
            self.modules.listen("scrypted", sid, lambda msg, sid=sid: self._live_event(sid, msg.get("message") or {}))
            self.modules.call("scrypted", "live_open", {"connection": c, "id": str(cam_id), "session": sid, "options": options}, 15)
        except Exception:
            self._live_forget(sid)
            raise
        return sid

    def live_input(self, sid, message):
        st = self._live_state()
        with st["lock"]:
            known = sid in st["sessions"]
        if not known or not isinstance(message, dict) or message.get("type") not in ("result", "candidate"):
            return {}
        with st["lock"]:
            r = (st["sessions"].get(sid) or {}).get("relay")
        if r:       # the browser's addresses mean nothing to Scrypted here: hand it the relay's one instead
            ours = (r["ip"], r["pipe"].port)
            v = message.get("value")
            if message["type"] == "result" and isinstance(v, dict) and "sdp" in v:
                message = dict(message, value=dict(v, sdp=liverelay.with_candidate(v["sdp"], *ours)))
            elif message["type"] == "candidate":
                if r["sent"]:
                    return {}
                r["sent"] = True
                c = message.get("candidate") if isinstance(message.get("candidate"), dict) else {}
                message = dict(message, candidate=dict(c, candidate=liverelay.candidate_line(*ours)[2:]))
        return self.modules.call("scrypted", "live_input", {"session": sid, "message": message}, 10)

    def live_relay(self, sid):
        """The media pipe of a live view that is being relayed through the site link (what /peer/udp joins), else None."""
        st = self._live_state()
        with st["lock"]:
            r = (st["sessions"].get(sid) or {}).get("relay")
        return r["pipe"] if r else None

    def live_close(self, sid):
        st = self._live_state()
        with st["lock"]:
            known = sid in st["sessions"]
        if known:
            try:
                self.modules.call("scrypted", "live_close", {"session": sid}, 10)
            except Exception:
                pass
            self._live_forget(sid)

    def sync_site_nodes(self):
        """Each pairing is something to watch: a managed site's link here ('Tidewater is not answering from here'), and on a managed box,
        whether the box that manages it is still in touch. Both are Unknown when silent, never down: a silent link proves nothing about the
        site. They follow the pairings (removing a pairing removes them)."""
        try:
            info = self.peer.get()
            mk = lambda i, name, chk: {"id": i, "name": name, "group": "Sites", "checks": [dict(chk, id="link", interval=15)]}
            monconfig.sync_nodes(self.paths, "site-", [mk("site-" + s["id"], (s.get("name") or "Site") + " link", {"type": "site", "site": s["id"]}) for s in info["sites"]])
            monconfig.sync_nodes(self.paths, "managed-by-", [mk("managed-by-" + m["id"], "Managed by " + (m.get("name") or "another MonitorBox"), {"type": "manager", "manager": m["id"]}) for m in info["managers"]])
            self.reload_monitoring()
        except Exception:
            pass          # the pairing itself is already saved; the nodes are caught up at the next start

    def reload_monitoring(self):
        try:
            monconfig.split_shared_items(self.paths)         # older boxes watched everything one integration found as one item
        except Exception:
            pass
        nodes, err = monconfig.all_nodes(self.paths)
        mon = monconfig.load_config(self.paths).get("monitoring", {})
        self.monitor.configure(nodes, err, mon.get("confirm") if isinstance(mon, dict) and not err else None)

    # -- settings and release info --------------------------------------
    def cfg(self):
        return updates.get_update_cfg(self.paths, self.default_channel)

    def launcher_state(self):
        return read_json(os.path.join(self.paths.root, "data", "launcher", "state.json"), {})

    def repos(self, cfg=None):
        return updates.repo_list(cfg or self.cfg(), self.releases_url)

    def default_id(self):
        return updates.default_repo(self.releases_url)["id"]

    def refresh(self):
        """Fetch the catalog and the channel's pointer from every switched-on repository, all at once. One that cannot be reached says so
        on its own line and keeps what we last knew; it never makes the others fail."""
        cfg = self.cfg()
        ch = cfg["channel"]
        repos = [r for r in self.repos(cfg) if r["enabled"]]

        def one(r):
            try:
                return r["id"], updates.fetch_release_info(r["url"], ch), None
            except Exception as e:
                return r["id"], None, f"Could not reach {r['name']}: {e}"
        old = self.infos if self.info_channel == ch else {}
        infos = {}
        if repos:
            with ThreadPoolExecutor(max_workers=len(repos)) as ex:
                for rid, info, err in ex.map(one, repos):
                    infos[rid] = {**info, "error": None} if info else {**(old.get(rid) or {}), "error": err}
        self.infos, self.info_channel = infos, ch
        d = infos.get(self.default_id())
        self.check_error = f"Could not reach the release server: {d['error'].split(': ', 1)[-1]}" if d and d.get("error") else None
        self.checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            self.reconcile()
        except Exception:
            pass          # looking after sources must never stop an update check

    def sources(self, cfg=None):
        """{module id: id of the repository it was installed from}. A module from before repositories came from the default one."""
        cfg = cfg or self.cfg()
        d = self.default_id()
        return {mid: (cfg["module_sources"].get(mid) or d) for mid in self.modules.state()}

    def installed_from(self, rid):
        return [mid for mid, src in self.sources().items() if src == rid]

    def reconcile(self):
        """After a check: remember each installed module's source and build, and hand a module over to another repository when its own no longer
        offers the build that is installed but another one offers exactly the same bytes (same sha256). A different build is never taken over
        on its own: modules keep their settings, which may hold passwords, so who may update one is the owner's decision."""
        cfg = self.cfg()
        repos = self.repos(cfg)
        known = {r["id"] for r in repos}
        st = self.modules.state()
        sources = self.sources(cfg)
        new_sources, changed = dict(cfg["module_sources"]), False

        def offers(rid, mid, sha):
            info = self.infos.get(rid) or {}
            return any(e.get("sha256") == sha for e in (info.get("catalog") or {}).get("modules", {}).get(mid, []))
        same_builds = self.same_builds
        for mid, rec in st.items():
            src = sources[mid]
            sha = rec.get("sha256")
            if not sha and rec.get("active") and src in self.infos:      # installed before builds were recorded: the source's catalog knows it
                ent = next((e for e in ((self.infos[src].get("catalog") or {}).get("modules", {}).get(mid, [])) if e["version"] == rec["active"]), None)
                if ent:
                    sha = ent["sha256"]
                    with self.modules.lock:
                        cur = self.modules.state()
                        if mid in cur and not cur[mid].get("sha256"):
                            cur[mid]["sha256"] = sha
                            self.modules._save(cur)
            if new_sources.get(mid) != src:
                new_sources[mid] = src
                changed = True
            info = self.infos.get(src)
            if not sha or src not in known or not info or info.get("error") or not info.get("catalog"):
                continue
            if offers(src, mid, sha):
                # still offered here: only the same repository under a new name (a rename; GitHub keeps answering at the old address) is taken over
                # automatically, which shows as both catalogs holding exactly the same builds. A copy with more or fewer is left to the owner.
                # only toward a repository further down the list: two identical repos would otherwise hand the module back and forth at every check
                later = [r for i, r in enumerate(repos) if i > next(j for j, q in enumerate(repos) if q["id"] == src)]
                for r in later:
                    if r["enabled"] and not (self.infos.get(r["id"]) or {}).get("error") and same_builds(src, r["id"]):
                        new_sources[mid] = r["id"]
                        changed = True
                        break
                continue
            for r in repos:
                if r["enabled"] and r["id"] != src and not (self.infos.get(r["id"]) or {}).get("error") and offers(r["id"], mid, sha):
                    new_sources[mid] = r["id"]
                    changed = True
                    break
        if changed:
            updates.set_update_cfg(self.paths, module_sources=new_sources)

    def builds(self, rid):
        mods = ((self.infos.get(rid) or {}).get("catalog") or {}).get("modules", {})
        return {(m, e["version"], e.get("sha256")) for m, es in mods.items() for e in es}

    def same_builds(self, x, y):
        """Two repositories holding exactly the same builds: one repository under two names."""
        return bool(self.builds(x)) and self.builds(x) == self.builds(y)

    def module_connections(self, mid):
        """The saved connections that use this module (their settings hold the passwords and keys)."""
        try:
            return [c["id"] for c in monconfig.load_config(self.paths).get("connections") or [] if isinstance(c, dict) and c.get("module") == mid and c.get("id")]
        except Exception:
            return []

    def uninstall(self, mid, backup="none"):
        """Delete a module and the settings that belong to it: the connections that use it (with their checks), its version choice and its
        source. A backup of the settings or of everything is made first when asked; if it cannot be made nothing is deleted."""
        if mid not in self.modules.state():
            raise ValueError(f"{mid} is not installed.")
        if backup not in ("none", "config", "full"):
            raise ValueError("backup must be none, config or full")
        if backup != "none":
            backups.lib().create(self.paths.root, backup, "manual", app_version=version())
        conns = self.module_connections(mid)
        for cid in conns:
            monconfig.remove_connection(self.paths, cid)
        self.modules.uninstall(mid)
        cfg = self.cfg()
        pins = {k: v for k, v in cfg["module_pins"].items() if k != mid}
        srcs = {k: v for k, v in cfg["module_sources"].items() if k != mid}
        updates.set_update_cfg(self.paths, module_pins=pins, module_sources=srcs, uninstalled=sorted(set(cfg["uninstalled"]) | {mid}))
        if conns:
            self.reload_monitoring()
        return {"message": f"{mid} is uninstalled" + (f", with {len(conns)} connection{'s' if len(conns) != 1 else ''} that used it." if conns else ".")}

    def remove_repo(self, rid, uninstall=False, backup="none"):
        mine = sorted(self.installed_from(rid))
        if mine and not uninstall:
            raise ValueError("Modules installed from this repository: " + ", ".join(mine) + ". Removing it uninstalls them.")
        if mine and backup != "none":
            if backup not in ("config", "full"):
                raise ValueError("backup must be none, config or full")
            backups.lib().create(self.paths.root, backup, "manual", app_version=version())      # once, before anything is deleted
        for mid in mine:
            self.uninstall(mid, "none")
        updates.remove_repo(self.paths, rid, self.releases_url, self.installed_from, uninstalled=True)
        return {"message": "Repository removed" + (f"; uninstalled {', '.join(mine)}." if mine else ".")}

    def adopt(self, mid, rid):
        """The owner's choice: let another repository that offers the very same build look after a module."""
        st = self.modules.state()
        sha = (st.get(mid) or {}).get("sha256")
        if not sha:
            raise ValueError("That module is not installed, or its build is not known yet. Check for updates first.")
        repo = next((r for r in self.repos() if r["id"] == rid and r["enabled"]), None)
        info = self.infos.get(rid) or {}
        if not repo or not any(e.get("sha256") == sha for e in (info.get("catalog") or {}).get("modules", {}).get(mid, [])):
            raise ValueError(f"{rid} does not offer the same build of {mid}, so it cannot take over.")
        updates.set_update_cfg(self.paths, module_sources={**self.cfg()["module_sources"], mid: rid})
        return {"message": f"{mid} is now updated from {repo['name']}."}

    def view(self):
        """What the update screen shows. Uses the last fetch; refresh() makes it current."""
        cfg = self.cfg()
        repos = self.repos(cfg)
        out = {"version": version(), "channel": cfg["channel"], "settings":
               {"autoCheck": cfg["auto_check"], "autoUpdate": cfg["auto_update"]},
               "checkedAt": self.checked_at, "checkError": self.check_error,
               "last": self.launcher_state().get("last"), "app": None, "modules": {}, "repos": []}
        fresh = self.info_channel == cfg["channel"]
        infos = self.infos if fresh else {}
        d = self.default_id()
        st = self.modules.state()
        sources = self.sources(cfg)
        out["repos"] = [{"id": r["id"], "name": r["name"], "default": r["default"], "enabled": r["enabled"],
                         "error": (infos.get(r["id"]) or {}).get("error"), "checked": r["id"] in infos,
                         "installed": sorted(m for m, src in sources.items() if src == r["id"]),
                         "uses": {m: len(self.module_connections(m)) for m, src in sources.items() if src == r["id"]}} for r in repos]
        enabled = [r for r in repos if r["enabled"]]
        dinfo = infos.get(d) if any(r["id"] == d and r["enabled"] for r in repos) else None
        if dinfo and dinfo.get("pointer"):
            out["app"] = versions.component(
                version(), cfg["app_pin"], (dinfo["pointer"].get("app") or {}).get("version"),
                dinfo["catalog"].get("app", []), cfg["channel"], self.launcher_state().get("failed", []))
        out["imageVersion"] = self.launcher_state().get("launcher_version")
        out["image"] = versions.image(self.launcher_state().get("launcher_version"),
                                      ((dinfo or {}).get("pointer") or {}).get("launcher", {}).get("version") if isinstance(((dinfo or {}).get("pointer") or {}).get("launcher"), dict) else None)
        offered = {}                 # module id -> repositories (in order) whose pointer names it
        for r in enabled:
            for mid in ((infos.get(r["id"]) or {}).get("pointer") or {}).get("modules", {}):
                offered.setdefault(mid, []).append(r["id"])
        names = {r["id"]: r["name"] for r in repos}
        for mid in sorted(modules_current(set(st) | set(offered))):
            rid = sources[mid] if mid in st else offered[mid][0]
            on = any(r["id"] == rid and r["enabled"] for r in repos)
            info = infos.get(rid) if on else None
            ptr, cat = (info or {}).get("pointer") or {}, (info or {}).get("catalog") or {}
            comp = versions.component(
                (st.get(mid) or {}).get("active"), cfg["module_pins"].get(mid, "latest"),
                (ptr.get("modules", {}).get(mid) or {}).get("version"),
                cat.get("modules", {}).get(mid, []), cfg["channel"], (st.get(mid) or {}).get("failed", []))
            sha = (st.get(mid) or {}).get("sha256")
            comp.update({"repo": rid, "repoName": names.get(rid, rid), "fromDefault": rid == d, "repoOn": on,
                         "installed": mid in st, "uses": len(self.module_connections(mid)) if mid in st else 0,
                         "declined": mid in cfg["uninstalled"] and mid not in st,
                         "repoGone": rid not in names,
                         "alsoIn": [o for o in offered.get(mid, []) if o != rid and not self.same_builds(rid, o) and (not sha or any(
                             e.get("sha256") == sha for e in ((infos.get(o) or {}).get("catalog") or {}).get("modules", {}).get(mid, [])))]})
            out["modules"][mid] = comp
        return out

    def entry(self, kind, mid, ver, rid=None):
        info = self.infos[rid or self.default_id()]
        cat = info["catalog"]
        entries = cat["app"] if kind == "app" else cat.get("modules", {}).get(mid, [])
        return next(e for e in entries if e["version"] == ver)

    # -- actions ---------------------------------------------------------
    def apply(self, kind, mid=None):
        v = self.view()
        comp = v["app"] if kind == "app" else v["modules"].get(mid)
        if not comp or not comp["target"]:
            raise ValueError("Nothing to install: that version is not offered in this channel.")
        if comp["target"] == comp["running"]:
            return {"message": "Already running that version."}
        ent = self.entry(kind, mid, comp["target"], comp.get("repo"))
        if kind == "app":
            if self.launcher_state().get("protocol", 1) < 2:
                raise ValueError("The container image is out of date and cannot install a chosen version. "
                                 "Re-pull the image (redeploy the stack with 'Re-pull image') once, then try again.")
            updates.request_launcher_install(self.paths, ent)
            self.exit_code = RESTART_EXIT
            threading.Thread(target=lambda: (time.sleep(0.5), self.httpd.shutdown()), daemon=True).start()
            return {"message": f"Installing App {ent['version']}…", "restarting": True}
        res = self.modules.apply_one(mid, ent)
        if res.startswith("failed"):
            raise RuntimeError(res)
        if mid in self.cfg()["uninstalled"]:
            updates.set_update_cfg(self.paths, uninstalled=[m for m in self.cfg()["uninstalled"] if m != mid])
        if self.cfg()["module_sources"].get(mid) != comp["repo"]:
            updates.set_update_cfg(self.paths, module_sources={**self.cfg()["module_sources"], mid: comp["repo"]})
        return {"message": f"{mid} is now {ent['version']}."}

    def apply_all(self):
        """Install every update that is waiting: the modules first, one after another, then the App last (it restarts).
        One module failing does not stop the rest; what happened is said in plain words."""
        v = self.view()
        done, failed = [], []
        for mid, c in sorted(v["modules"].items()):
            if c.get("needsApply") and c.get("target") and c["target"] not in c.get("failed", []) and (c.get("running") or (c.get("fromDefault") and not c.get("declined"))):
                try:
                    self.apply("module", mid)
                    done.append(f"{mid} {c['target']}")
                except Exception as e:
                    failed.append(f"{mid}: {e}")
        restarting = False
        a = v.get("app")
        if a and a.get("needsApply") and a.get("target") and a["target"] not in a.get("failed", []):
            try:
                restarting = bool(self.apply("app").get("restarting"))
                done.append(f"App {a['target']}")
            except Exception as e:
                failed.append(f"App: {e}")
        msg = ("Installed " + ", ".join(done) + "." if done else "Nothing needed installing.") + ((" Could not install: " + "; ".join(failed)) if failed else "")
        if restarting:
            msg += " Restarting…"
        return {"message": msg, "restarting": restarting}

    def select(self, kind, mid, pin):
        cfg = self.cfg()
        if kind == "app":
            updates.set_update_cfg(self.paths, app_pin=pin)
        else:
            pins = cfg["module_pins"]
            pins[mid] = pin
            updates.set_update_cfg(self.paths, module_pins=pins)

    def auto_loop(self):
        """Check for updates on a timer; apply them only if auto-update is on."""
        time.sleep(3)
        while True:
            try:
                self.auto_step()
            except Exception:
                pass
            time.sleep(self.check_seconds)

    def auto_step(self):
        """One round of automatic checking and installing. It works the same on every channel (dev, beta and stable): the channel only
        decides which releases are on offer, and only items set to Latest are updated."""
        cfg = self.cfg()
        if cfg["auto_check"]:
            self.refresh()
            if cfg["auto_update"] and self.infos:
                v = self.view()
                for mid, c in v["modules"].items():
                    # a module from another repository is never installed unasked; once the owner has installed it, it follows its updates
                    if c["pin"] == "latest" and c["needsApply"] and c["target"] not in c["failed"] and (c.get("running") or (c.get("fromDefault") and not c.get("declined"))):
                        self.apply("module", mid)
                a = v["app"]
                if a and a["pin"] == "latest" and a["needsApply"] and a["target"] not in a["failed"]:
                    self.apply("app")

    # -- backups ---------------------------------------------------------
    def backup_list(self):
        b = backups.lib()
        st = self.launcher_state()
        return {"backups": backups.listing(self.paths.root), "last": st.get("last") if (st.get("last") or {}).get("restore") is not None else None,
                "canRestore": st.get("protocol", 1) >= 3}

    def backup_loop(self):
        try:
            backups.listing(self.paths.root)        # read once now, so the first time Settings asks it is already known
        except Exception:
            pass
        time.sleep(60)
        while True:
            try:
                backups.run_auto(self.paths.root, version())
                backups.listing(self.paths.root)    # and again after a new backup, here rather than when someone taps Settings
            except Exception:
                pass
            time.sleep(900)

    def restore(self, name):
        b = backups.lib()
        if self.launcher_state().get("protocol", 1) < 3:
            raise ValueError(backups.OLD_IMAGE.replace("do backups", "restore"))
        b.validate(b.path_of(self.paths.root, name))  # refuse a bad file now, while the App is still up
        os.makedirs(os.path.dirname(self.paths.request), exist_ok=True)
        if os.path.exists(self.paths.auth):      # the password you have now survives the restore (put back when the App starts)
            shutil.copy2(self.paths.auth, self.paths.auth_keep)
        with open(self.paths.request, "w") as f:
            json.dump({"action": "restore", "backup": name}, f)
        self.exit_code = RESTART_EXIT
        threading.Thread(target=lambda: (time.sleep(0.5), self.httpd.shutdown()), daemon=True).start()
        return {"message": "Restoring... MonitorBox restarts and the page reloads itself.", "restarting": True}

    def used_modules(self):
        """Modules a saved connection or check uses. Only these start with the App; the others start when first asked."""
        try:
            cfg = monconfig.load_config(self.paths)
            return {c.get("module") for c in cfg.get("connections") or [] if isinstance(c, dict)} | \
                   {c.get("module") for c in cfg.get("checks") or [] if isinstance(c, dict) and c.get("module")}
        except Exception:
            return None

    def apply_start_files(self):
        """At start: (1) a restore keeps the password the box had before it; (2) a file named factory-reset in the config folder
        (made by someone with access to the box itself, for a forgotten password) does what the Factory reset button does.
        There is no password recovery: you start over, then restore a backup or run the setup again."""
        try:
            if os.path.exists(self.paths.auth_keep):
                shutil.move(self.paths.auth_keep, self.paths.auth)
            if os.path.exists(self.paths.reset_flag):
                self.wipe_settings()          # also removes the flag, as it lives in the config folder
                if os.path.exists(self.paths.reset_flag):
                    os.unlink(self.paths.reset_flag)
        except OSError:
            pass

    def graph_sample(self, cid, names):
        c = monconfig.connection(self.paths, cid)
        if not c or c.get("module") != "snmp":
            raise ValueError(f"'{cid}' is not an SNMP connection any more")
        return self.modules.call("snmp", "sample", {"connection": c, "names": names}, 10)

    def map_loop(self):
        """Keep the map's names and ports fresh in the background (every 5 minutes), so the front page can name the busiest client without the map page open."""
        stop = self.lansampler.stopping
        stop.wait(8)
        while not stop.is_set():
            try:
                if any(c.get("module") == "unifi-network" for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)):
                    self.build_map()
            except Exception:
                pass
            stop.wait(300)

    def power_scan(self, ask=False):
        """Which systems each UPS powers, guessed from the UPS servers' own client lists (the machines running upsmon against it). Confident only: a client address
        that is exactly one watched system's address (a client of the NUT server itself says 127.0.0.1, meaning the NUT server's own machine). Returns
        {"ups": [{"id", "name"}], "guess": {system id: [UPS ids]}, "notes": [...]}. Read-only: it only sends LIST CLIENT."""
        nodes, _ = monconfig.all_nodes(self.paths)
        conns = {c.get("id"): c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)}
        host_of = lambda t: str(t or "").split(":")[0].strip().lower()
        ups, claims, notes = [], {}, []
        is_ups = lambda n: any(k.get("module") == "nut" for k in n.get("checks", []))
        by_snmp, by_ping = {}, {}                               # address -> [ids of the watched systems there]; a system holding an SNMP login is the server's own one (as on the server page)
        for n in nodes:
            if n.get("kind") == "aggregate" or is_ups(n) or n.get("builtin"):
                continue
            for k in n.get("checks", []):
                if k.get("module") == "snmp" and conns.get(k.get("connection")):
                    a = host_of(conns[k["connection"]].get("host"))
                    if a and n["id"] not in by_snmp.setdefault(a, []):
                        by_snmp[a].append(n["id"])
                elif k.get("type") in ("ping", "tcp") and k.get("target"):
                    a = host_of(k["target"])
                    if n["id"] not in by_ping.setdefault(a, []):
                        by_ping[a].append(n["id"])
        systems = {a: by_snmp.get(a) or by_ping.get(a, []) for a in set(by_snmp) | set(by_ping)}
        for n in nodes:
            if not is_ups(n):
                continue
            ups.append({"id": n["id"], "name": n["name"]})
            k = next(k for k in n["checks"] if k.get("module") == "nut")
            conn = conns.get(k.get("connection"))
            name = (k.get("params") or {}).get("ups")
            if not conn or not name:
                continue
            try:
                addrs = self.modules.call("nut", "clients", {"connection": conn, "ups": name}, 10).get("clients", [])
            except Exception as e:
                notes.append(f"{n['name']}: {str(e)[:120]}")
                continue
            for a in addrs:
                a = host_of(a)
                if a in ("127.0.0.1", "::1", "localhost"):
                    a = host_of(conn.get("host"))
                ids = systems.get(a, [])
                if len(ids) == 1 and n["id"] not in claims.setdefault(ids[0], []):
                    claims[ids[0]].append(n["id"])
        guess = {sid: u for sid, u in claims.items() if len(u) == 1}      # one UPS per system: two UPSes both claiming it is not confident, so nothing is guessed
        follow, why = {}, {}                                # a Portainer environment runs on a machine: it has that machine's power, so nobody ticks it
        for c in conns.values():
            if c.get("module") == "portainer" and ask and not (self.pt_cache.get(c["id"]) or {}).get("out") and c["id"] not in self.pt_running:
                self.pt_running.add(c["id"])
                self._refresh_portainer(c)
        for n in nodes:
            for k in n.get("checks", []):
                if k.get("module") == "portainer" and k.get("check") == "environment":
                    out = (self.pt_cache.get(k.get("connection")) or {}).get("out")
                    name = (k.get("params") or {}).get("name")
                    e = next((e for e in (out or {}).get("environments", []) if e.get("name") == name), None)
                    addr = host_of(e.get("address")) if e else ""
                    ids = systems.get(addr, []) if addr else []
                    if len(ids) == 1 and ids[0] != n["id"]:
                        follow[n["id"]] = ids[0]
                    else:
                        why[n["id"]] = ("Waiting for Portainer to say where this runs." if not out else "Portainer does not list an environment called '%s'." % name if not e
                                        else "An edge agent: it has no address to match." if e.get("edge") else "Portainer gave no address for it." if not addr
                                        else f"Portainer says it is at {addr}; no watched system is at that address." if not ids else f"{len(ids)} watched systems share {addr}, so it is not clear which it runs on.")
        return {"ups": ups, "guess": guess, "follow": follow, "why": why, "notes": notes}

    def power_view(self, refresh=False, ask=False):
        hit = getattr(self, "_power", None)
        if hit and not refresh and time.time() - hit[0] < 300:
            return hit[1]
        out = self.power_scan(ask)
        self._power = (time.time(), out)
        self.monitor.power_guess = out["guess"]
        self.monitor.power_follow = out["follow"]
        return out

    def power_page(self, refresh=False):
        """What the Power page needs: each UPS, every system that could be on one (not a container, not built in, not already explained by something it depends on),
        which UPS each is on now (the owner's answer, else the guess), and where that came from."""
        v = self.power_view(refresh)
        nodes, _ = monconfig.all_nodes(self.paths)
        mine = {n["id"]: n for n in nodes if not n.get("builtin")}
        ups_ids = {u["id"] for u in v["ups"]}
        systems = []
        for n in nodes:
            if n.get("builtin") or n.get("kind") == "aggregate" or n["id"] in ups_ids or n.get("service") or n.get("dependsOn") or n["id"] in v["follow"] \
                    or any(k.get("type") in ("site", "manager") for k in n.get("checks", [])):       # a link to another MonitorBox is not a machine
                continue
            if "poweredBy" in n:
                on, src = (n["poweredBy"] or [None])[0], "set"
            else:
                on, src = (v["guess"].get(n["id"]) or [None])[0], "guess"
            systems.append({"id": n["id"], "name": n["name"], "group": n.get("group", ""), "ups": on if on in ups_ids else None, "from": src if on in ups_ids else "none", "why": v["why"].get(n["id"], "")})
        systems.sort(key=lambda x: (x["group"].lower(), x["name"].lower()))
        follows = sorted(({"name": mine[i]["name"], "host": mine[h]["name"]} for i, h in v["follow"].items() if i in mine and h in mine), key=lambda x: x["name"].lower())
        return {"ups": v["ups"], "systems": systems, "follows": follows, "notes": v["notes"]}

    def power_loop(self):
        """Keep the guessed power links fresh (every 10 minutes). A box with no UPS watched never asks anyone."""
        stop = self.lansampler.stopping
        stop.wait(20)
        while not stop.is_set():
            try:
                self.power_view(refresh=True, ask=True)
            except Exception:
                pass
            stop.wait(600)

    def flow_loop(self):
        """Keep the last minute of the gateway's flow log at hand (every 20 s) so the Busiest client can count wifi clients. A box with no UniFi login never asks."""
        stop = self.lansampler.stopping
        stop.wait(12)
        while not stop.is_set():
            try:
                if any(c.get("module") == "unifi-network" for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)):
                    self.minute_flows = self.flow_rows(60)["rows"]
                else:
                    self.minute_flows = []
            except Exception:
                self.minute_flows = []
            stop.wait(20)

    def camera_ids(self):
        """(MACs, addresses) of every camera the connected camera sources know, for finding their switch ports and for the Busiest client's Cameras tick (their names: camera_names).
        Asked at most every five minutes; a look that failed or missed a source is not remembered, so the next one tries again."""
        hit = getattr(self, "_cam_ids", None)
        if hit and time.time() - hit[0] < 300:
            return hit[1]
        macs, ips, names, ok = set(), set(), set(), True
        self._cam_names = set()
        try:
            got = self.cameras()
            ok = not got.get("errors")
            for cam in got.get("cameras", []):
                m = re.sub(r"[^0-9a-f]", "", str(cam.get("mac") or "").lower())
                if len(m) == 12:
                    macs.add(m)
                if cam.get("host"):
                    ips.add(str(cam["host"]).strip().lower())
                if cam.get("name"):
                    names.add(str(cam["name"]).strip().lower())
        except Exception:
            ok = False
        self._cam_names = names
        if ok:
            self._cam_ids = (time.time(), (macs, ips))
        return macs, ips

    def camera_names(self):
        """The names of the cameras the camera sources know (lower case), from the same look as camera_ids."""
        self.camera_ids()
        return getattr(self, "_cam_names", set())

    def camera_ports(self, by, me, row):
        """The map ports with a camera on them (by MAC, else address), not counting the port being asked about. Needs at least two to be a group."""
        macs, ips = self.camera_ids()
        norm = lambda m: re.sub(r"[^0-9a-f]", "", str(m or "").lower())
        found = []
        for n in by.values():
            for p in n.get("ports", []):
                if (n is me and p is row) or not p.get("keys"):
                    continue
                on = {norm(m) for m in p.get("macs") or []}
                if (on & macs) or ({str(i).lower() for i in p.get("ips") or []} & ips):
                    found.append(p)
        return found if len(found) >= 2 else []

    def lan_peers(self, node_id, port, win):
        """Where a port's traffic most likely goes, from the history of every port (see portpeers). Uses the map the page is showing."""
        m = self.last_map
        by = {n["id"]: n for n in (m or {}).get("nodes", [])}
        me = by.get(node_id)
        row = next((p for p in (me or {}).get("ports", []) if p.get("port") == port), None)
        if not row:
            return {"answer": [], "why": "That port is not on the map any more. Reload the map.", "window": 0, "read": 0, "unread": []}
        win = max(60, min(win, portpeers.KEEP_SECONDS))
        cands, labels_of = {}, {}        # label -> [keys]; id(port) -> label
        for n in by.values():
            for p in n.get("ports", []):
                if n is me and p is row or not p.get("keys"):
                    continue
                who = p.get("name") or "nothing named"
                cands[f"{who} ({n['name']} port {p['port']})"] = [tuple(k) for k in p["keys"]]
                labels_of[id(p)] = f"{who} ({n['name']} port {p['port']})"
        group = self.camera_ports(by, me, row)           # ports known to be alike (cameras): where the search for devices that move together starts
        if me.get("link") and (me["link"].get("keys") or {}).get("self"):
            cands[f"anything beyond the link to {me['link']['to']}"] = [tuple(me["link"]["keys"]["self"])]
        for n in by.values():
            k = (((n.get("link") or {}).get("keys") or {}).get("parent")) if n.get("parent") == me["id"] else None
            if k:
                cands[f"anything behind {n['name']}"] = [tuple(k)]
        wifi = {}                         # label -> history key: Wi-Fi clients, matched below against the same port (they have no port of their own)
        for key, info in dict(getattr(self.lansampler, "wifi", None) or {}).items():
            label = f"{info['name']} (Wi-Fi)"
            if label in wifi or label in cands:
                label = f"{info['name']} (Wi-Fi {key.rsplit('|', 1)[-1][-5:]})"
            wifi[label] = (lansampler.WIFI, key)
        wanted = {k for ks in cands.values() for k in ks} | {tuple(k) for k in row["keys"]} | set(wifi.values())
        grid = self.series.grid(wanted, win)
        def vec(keys):
            return portpeers.add_groups([grid[k] for k in keys]) if keys else None
        focus = vec([tuple(k) for k in row["keys"]])
        got = {k[0] for k in wanted if any(v is not None for v in grid[k][0])}
        unread = sorted({by[k[0]]["name"] for k in wanted if k[0] in by and k[0] not in got})       # a switch is named only when none of its ports has a reading
        vecs = {lab: vec(ks) for lab, ks in cands.items()}
        out = portpeers.likely(focus, vecs) if focus and any(v is not None for v in focus[0]) else \
            {"answer": [], "why": "No traffic readings for this port yet. The box reads every port about every 10 seconds; give it a minute."}
        if focus and any(v is not None for v in focus[0]):
            seed = [labels_of[id(p)] for p in group if id(p) in labels_of]
            pool = {l: v for l, v in vecs.items() if v and not l.startswith("anything")}
            for g in portpeers.together(focus, pool, seed):
                who = [m.rsplit(" (", 1)[0] for m in g["members"]]
                names = ", ".join(dict.fromkeys(who[:3])) + (" …" if len(who) > 3 else "")
                g["label"] = f"your cameras ({len(who)} combined)" if g.pop("seeded") else f"{len(who)} devices together ({names})"
                members = set(g.pop("members"))
                out["answer"] = [x for x in out.get("answer", []) if x.get("label") not in members]          # the total says it; its members said again would add up to more than there is
                out["answer"].append(g)
            out["answer"] = sorted(out.get("answer", []), key=lambda x: -x["r"])[:6]
            if out["answer"]:
                out["why"] = ""
        if focus and any(v is not None for v in focus[0]) and wifi:
            out["answer"] = (out.get("answer") or []) + self.wifi_peers(focus, wifi, grid)
            out["answer"] = sorted(out["answer"], key=lambda x: -x["r"])[:6]
            if out["answer"]:
                out["why"] = ""
        return {**out, "window": win, "read": len(wanted) - sum(1 for k in wanted if all(v is None for v in grid[k][0])), "unread": unread,
                "history": round(self.series.history_seconds([tuple(k) for k in row["keys"]]))}

    @staticmethod
    def wifi_peers(focus, wifi, grid):
        """Wi-Fi clients that follow this port's traffic. The controller's per-client rates are tried both ways round (its rx/tx are not
        trusted to point the way this page assumes), the way round that fits better wins, and only a close fit counts (`likely`, not `possible`),
        because a rate read from an access point is rougher than a switch port's counters."""
        both = {}
        for label, key in wifi.items():
            a, b = grid[key]
            if any(v is not None for v in a) or any(v is not None for v in b):
                both[label] = (a, b)
                both[label + "\u200b"] = (b, a)
        if not both:
            return []
        best = {}
        for x in portpeers.likely(focus, both, top=len(both)).get("answer", []):
            base = x["label"].rstrip("\u200b")
            if x.get("kind") != "flood" and x["r"] >= portpeers.LIKELY and (base not in best or x["r"] > best[base]["r"]):
                best[base] = {**x, "label": base, "confidence": "likely"}
        return list(best.values())

    def build_map(self):
        srcs = self.lan_report(wait=0)["sources"]
        self.last_sources = srcs
        self.last_map = lanmap.build(srcs)
        return self.last_map

    def graph_port(self, g, conns, nodes):
        """(node id, port, host) of the map port a graph's interface is plugged into, or (None, None, host). The graph is one interface of a device, so match by that
        interface's own MAC address (a device with two NICs has two ports on the map); fall back to the connection's address."""
        conn = next((c for c in conns if c.get("id") == g.get("connection")), None)
        host = followups.host_of(conn or {})
        mac = next((p.get("mac") for src in self.last_sources if src.get("connection") == g.get("connection") for p in ((src.get("report") or {}).get("ports") or [])
                    if isinstance(p, dict) and p.get("name") == g.get("interface") and p.get("mac")), None)
        node = port = None
        for n in nodes:
            for p in n.get("ports", []):
                if (mac and mac in (p.get("macs") or [])) or (not mac and host and host in (p.get("ips") or [])):
                    node, port = n["id"], p["port"]
        if node is None and mac and host:
            for n in nodes:
                for p in n.get("ports", []):
                    if host in (p.get("ips") or []):
                        node, port = n["id"], p["port"]
        return node, port, host

    def busiest_data(self, seconds=300):
        """The Busiest client's numbers. When the leader is a device this box also reads itself over SNMP and graphs on the main screen, the line is that graph's own
        readings (so the two lines agree) from the moment it took the lead; otherwise it is drawn from the switch port's latest readings."""
        d = self.busiest.data(seconds)
        lead, since = d.get("leader"), d.get("since")
        if not lead or since is None:
            return d
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)]
        nodes = (self.last_map or {}).get("nodes", [])
        for g in read_json(self.graphs_file, []) or []:
            if not isinstance(g, dict) or g.get("kind") == "busiest" or not g.get("connection"):
                continue
            if self.graph_port(g, conns, nodes)[:2] != (lead["node"], lead["port"]):
                continue
            mine = next((x for x in self.graphs.data(d["seconds"])["graphs"] if x["id"] == g["id"]), None)
            pts = [[p[0], p[1], p[2]] for p in (mine or {}).get("points", []) if p[0] >= since]
            if pts:
                d["points"] = [p for p in d["points"] if p[0] < pts[0][0]] + pts
                d["source"] = g.get("title") or g["id"]
            break
        return d

    @staticmethod
    def unmatched(total, flows):
        """The part of a device's own traffic (what its switch port carried) that the list above does not explain: the gateway only logs what it routes, and the
        estimate for the rest names only ports that rise and fall with the device. Said out loud so a gap is not mistaken for nothing. Nothing when it is small."""
        if not total:
            return []
        down = max(0, total.get("down", 0) - sum(f["down_bps"] for f in flows))
        up = max(0, total.get("up", 0) - sum(f["up_bps"] for f in flows))
        big = lambda left, whole: left >= 100_000 and left >= 0.1 * whole
        down, up = (down if big(down, total.get("down", 0)) else 0), (up if big(up, total.get("up", 0)) else 0)
        return [{"scope": "unmatched", "label": "not matched to anything", "down_bps": down, "up_bps": up}] if down or up else []

    def lan_flows(self, graph_id, win):
        """The list under a graph's side panel: where its traffic goes, biggest first, local and internet mixed. Local = other devices on the LAN (an estimate from how
        traffic rises and falls on the switch ports, see portpeers); internet = what the gateway counts for that device (or, for a graph of the gateway itself, the
        clients using the internet most). A graph is matched to a device on the map by its address; one that cannot be matched says so."""
        win = max(60, min(int(win), portpeers.KEEP_SECONDS))
        out = {"flows": [], "why": "", "window": win, "read": 0, "unread": []}
        g = next((x for x in (read_json(self.graphs_file, []) or []) if isinstance(x, dict) and x.get("id") == graph_id), None)
        nodes = (self.last_map or {}).get("nodes", [])
        if not g:
            return {**out, "why": "That graph is not on the main screen any more."}
        node = port = None
        if g.get("kind") == "busiest":
            leader = self.busiest.data(win).get("leader")
            if not leader:
                return {**out, "why": "The wired LAN is quiet in that time."}
            if leader.get("node") is None:                  # a device the gateway's flow log named (wifi): its flows are the list
                mac = leader.get("mac")
                fr = self.flow_rows(win)
                ent = self.flow_entries(fr["rows"], win, (), [mac] if mac else [])
                out["flows"] = sorted(ent, key=lambda f: -(f["down_bps"] + f["up_bps"]))[:25]
                out["why"] = "" if out["flows"] else "The gateway's flow log has nothing for it in that time."
                out["focus"] = leader["name"]
                return out
            node, port = leader["node"], leader["port"]
        else:
            conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)]
            conn = next((c for c in conns if c.get("id") == g.get("connection")), None)
            host = followups.host_of(conn or {})
            gateway_hosts = {followups.host_of(c) for c in conns if c.get("module") == "unifi-network"} | {str(n.get("ip") or "").lower() for n in nodes if n.get("kind") == "gateway"}
            if host and host in gateway_hosts:           # a connection to the gateway (or the UniFi console): the WAN graph. The map knows the gateway by its WAN address, the SNMP login uses its LAN one.
                fr = self.flow_rows(win)
                out["flows"] = sorted(self.flow_entries(fr["rows"], win), key=lambda f: -(f["down_bps"] + f["up_bps"]))[:15]
                if not out["flows"]:                    # the flow log did not answer: say who is using the internet instead
                    gw = self.gateway_usage(win)
                    out["flows"] = [{"scope": "internet", "label": x["name"] + (" (wired)" if x["wired"] else " (wifi)"), "down_bps": x["down_bps"], "up_bps": x["up_bps"]} for x in gw["clients"][:15]]
                out["why"] = "" if out["flows"] else "Nothing went through the gateway in that time." + (" The gateway's flow log said: " + "; ".join(fr["notes"]) if fr["notes"] else "")
                return out
            node, port, host = self.graph_port(g, conns, nodes)
            if node is None:
                named = host and not re.fullmatch(r"[\d.]+", host)
                return {**out, "why": "This graph could not be matched to a device on the map" + (" (it is set up by name, and the map matches by address)." if named else ".")}
        peers = self.lan_peers(node, port, win)
        for a in peers.get("answer", []):
            if a.get("label", "").startswith(("anything beyond", "anything behind")):
                continue                                           # "somewhere that way": says nothing the reader can use
            bps = a.get("bps", 0)
            label = a["label"] + " (" + ", ".join(a.get("ports") or []) + ")" if a.get("kind") == "flood" else ("sends to " if a["direction"] == "from" else "receives from ") + a["label"]
            out["flows"].append({"scope": "local", "label": label, "confidence": a["confidence"], "match": round(a["r"] * 100),
                                 "down_bps": bps if a["direction"] == "to" else 0, "up_bps": bps if a["direction"] == "from" else 0})
        by = {n["id"]: n for n in nodes}
        row = next((p for p in (by.get(node) or {}).get("ports", []) if p.get("port") == port), None) or {}
        seen = self.flow_entries(self.flow_rows(win)["rows"], win, row.get("ips") or [], row.get("macs") or [])
        out["flows"] += seen
        mine = [x for x in self.gateway_usage(win)["clients"] if x["id"] in (row.get("macs") or [])]
        if mine:        # the gateway counts every byte this device sent or got through it; its flow log lags behind a long download and may name only the small flows
            named = [f for f in seen if f["scope"] == "internet"]
            d, u = (max(0, sum(x[k] for x in mine) - sum(f[k] for f in named)) for k in ("down_bps", "up_bps"))
            big = lambda left, whole: left >= 100_000 and left >= 0.1 * whole
            whole_d, whole_u = sum(x["down_bps"] for x in mine), sum(x["up_bps"] for x in mine)
            if not named or big(d, whole_d) or big(u, whole_u):
                out["flows"].append({"scope": "internet", "label": "the internet and other networks" if not named else "more internet traffic (the gateway has not named where yet)",
                                     "down_bps": d if named else whole_d, "up_bps": u if named else whole_u})
        out["flows"] += self.unmatched(peers.get("total"), out["flows"])
        out["history"] = peers.get("history", 0)
        young = 0 < out["history"] < 0.9 * win                  # the box has not been reading long enough to fill the window: a gap may only mean it has not learned yet
        out["young"] = young
        if young:
            for f in out["flows"]:
                if f["scope"] == "unmatched":
                    f["label"] = "not matched yet"
        out["flows"] = sorted(out["flows"], key=lambda f: -(f["down_bps"] + f["up_bps"]))[:25]
        out.update({"why": "" if out["flows"] else peers.get("why", ""), "read": peers.get("read", 0), "unread": peers.get("unread", []), "focus": (by.get(node) or {}).get("name", "") + " port " + str(port)})
        return out

    def wan_ports(self, cid):
        """Which interfaces of this SNMP device are its WAN, when a UniFi Network login on the same address can say."""
        from urllib.parse import urlparse as _u
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)]
        me = next((c for c in conns if c.get("id") == cid), None)
        host = str((me or {}).get("host") or "").lower()
        if not host:
            return {"ports": []}
        for c in conns:
            if c.get("module") != "unifi-network":
                continue
            if str(c.get("host") or _u(str(c.get("base_url") or "")).hostname or "").lower() != host:
                continue
            try:
                return self.modules.call("unifi-network", "wan_ports", {"connection": c}, 20)
            except Exception:
                return {"ports": []}
        return {"ports": []}

    def gateway_usage(self, seconds=300):
        """Who is using the internet (and other networks) through the gateway, per client over the last `seconds`, wifi and wired, as rates. Counted by the gateway, so
        traffic that stays on a switch is not in it. Asked of each UniFi login at most every 20 s per window; a login that cannot answer is named in `notes`."""
        seconds = max(60, min(int(seconds), 3600))
        hit = self.gw_cache.get(seconds)
        if hit and time.time() - hit[0] < 20:
            return hit[1]
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") == "unifi-network"]
        clients, notes, tot = [], [], [0, 0]
        for c in conns:
            try:
                r = self.modules.call(c["module"], "client_usage", {"connection": c, "seconds": seconds}, 20)
            except Exception as e:
                notes.append(f"{c.get('id')}: {str(e)[:120]}")
                continue
            for x in r.get("clients", []):
                clients.append({"id": x["id"], "name": x["name"], "wired": x["wired"], "down_bps": round(x["down"] * 8 / seconds), "up_bps": round(x["up"] * 8 / seconds)})
            tot[0] += (r.get("total") or {}).get("down", 0)
            tot[1] += (r.get("total") or {}).get("up", 0)
        clients.sort(key=lambda x: -(x["down_bps"] + x["up_bps"]))
        out = {"seconds": seconds, "clients": clients[:30], "total": {"down_bps": round(tot[0] * 8 / seconds), "up_bps": round(tot[1] * 8 / seconds)}, "notes": notes, "at": round(time.time(), 2)}
        self.gw_cache[seconds] = (time.time(), out)
        return out

    def flow_rows(self, seconds=300):
        """What the gateway's flow log says about who talked to whom over the last `seconds` (one row per source, destination and direction), from every UniFi login.
        Asked at most every 20 s per window. `rows` is empty and `notes` says why when a login cannot answer."""
        seconds = max(60, min(int(seconds), 3600))
        hit = self.gw_cache.get(("flows", seconds))
        if hit and time.time() - hit[0] < 20:
            return hit[1]
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") == "unifi-network"]
        rows, notes = [], []
        for c in conns:
            try:
                rows += self.modules.call(c["module"], "flows", {"connection": c, "seconds": seconds}, 30).get("flows", [])
            except Exception as e:
                notes.append(f"{c.get('id')}: {str(e)[:120]}")
        out = {"seconds": seconds, "rows": rows, "notes": notes}
        self.gw_cache[("flows", seconds)] = (time.time(), out)
        return out

    @staticmethod
    def flow_entries(rows, seconds, ips=(), macs=()):
        """Flow rows as list entries. With ips/macs: the flows of the device that owns them (what it talks to, and who talks to it). Without: the internet side of the
        whole network, one entry per destination, naming who is using it."""
        ips, macs, by = set(ips), set(macs), {}

        def add(key, label, scope, down, up, who=None):
            e = by.setdefault(key, {"scope": scope, "label": label, "down_bps": 0, "up_bps": 0, "who": {}})
            e["down_bps"] += down * 8 / seconds
            e["up_bps"] += up * 8 / seconds
            if who:
                e["who"][who] = e["who"].get(who, 0) + down + up
        for r in rows:
            internet = r["direction"] in ("outgoing", "incoming")
            if not ips and not macs:
                if r["direction"] == "outgoing":
                    add(("i", r["dst_name"]), r["dst_name"] or "an unnamed address", "internet", r["down"], r["up"], r["src_name"])
                continue
            if (r["src_mac"] and r["src_mac"] in macs) or (r["src_ip"] and r["src_ip"] in ips):
                if r["dst_zone"] == "Gateway":
                    continue                                       # a device talking to its own gateway: already in the totals
                name = r["dst_name"] or "an unnamed address"
                add(("o", name, internet), name, "internet" if internet else "local", r["down"], r["up"])
            elif (r["dst_mac"] and r["dst_mac"] in macs) or (r["dst_ip"] and r["dst_ip"] in ips):
                add(("a", r["src_name"], internet), "from " + r["src_name"], "internet" if internet else "local", r["up"], r["down"])
        out = []
        for e in by.values():
            who = sorted(e.pop("who").items(), key=lambda kv: -kv[1])
            if who:
                e["label"] += " (" + ", ".join(n for n, _ in who[:2]) + (f" and {len(who) - 2} more" if len(who) > 2 else "") + ")"
            e["down_bps"], e["up_bps"] = round(e["down_bps"]), round(e["up_bps"])
            e["match"], e["seen"] = None, True
            out.append(e)
        return out

    def flows_look(self):
        """A read-only look at what each UniFi login answers to the questions behind Insights, Flows (status and shape only, addresses scrubbed), so the flows list can be
        built on what your gateway really says. Connection settings are never returned."""
        from concurrent.futures import ThreadPoolExecutor
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") == "unifi-network"]

        def one(c):
            row = {"connection": str(c.get("id") or ""), "module": c["module"]}
            try:
                row["report"] = self.modules.call(c["module"], "flows_look", {"connection": c}, 60)
            except Exception as e:
                row["error"] = str(e)[:200]
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            return {"sources": list(pool.map(one, conns))}

    def lan_report(self, wait=None):
        """A read-only look at what every UniFi login and every SNMP device reports about its ports and neighbours, for building the LAN map. Each source
        answers on its own; one that cannot be reached is named with the reason and does not hold up the others. Connection settings are never returned."""
        from concurrent.futures import ThreadPoolExecutor
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") in ("unifi-network", "snmp")]

        def one(c):
            row = {"connection": str(c.get("id") or ""), "module": c["module"]}
            try:
                row["report"] = self.modules.call(c["module"], "lan_report", {"connection": c, **({"wait": wait} if wait is not None else {})}, 40)
            except Exception as e:
                row["error"] = str(e)[:200]
            return row
        with ThreadPoolExecutor(max_workers=4) as pool:
            return {"sources": list(pool.map(one, conns))}

    def busiest_opts(self):
        """The saved filters plus who is a camera and who is on an IoT network (addresses, from the camera sources and the map), so the cameras and IoT ticks can act."""
        f = dict(self.busiest_filter())
        macs, ips = self.camera_ids()
        f["_cameraIps"], f["_cameraMacs"], f["_cameraNames"] = sorted(ips), sorted(macs), sorted(self.camera_names())
        f["_makers"] = (self.last_map or {}).get("makers") or {}
        f["_iotIps"] = (self.last_map or {}).get("iotIps") or []
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") == "unifi-network"]
        gw = {h for h in (followups.host_of(c) for c in conns) if h}                # the UniFi login's own address is the gateway's LAN address
        f["_infraIps"] = sorted(set((self.last_map or {}).get("infraIps") or []) | gw)
        f["_infraMacs"] = (self.last_map or {}).get("infraMacs") or []
        return f

    def busiest_filter(self):
        """The Busiest client card's saved filters (empty when none were set)."""
        g = next((x for x in (read_json(self.graphs_file, []) or []) if isinstance(x, dict) and x.get("kind") == "busiest"), None)
        return (g or {}).get("filter") or {}

    def set_graphs(self, raw):
        from .store import write_json
        conns = {c.get("id"): c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)}
        out = graphs.clean_list(raw, lambda cid: (conns.get(cid) or {}).get("module") == "snmp")
        write_json(self.graphs_file, out)
        return out

    # gwin = how long a stretch the main-screen traffic graphs show, gpanel = how long the panel that opens when you tap one shows (seconds; the box keeps one hour of readings, so that is the most)
    DISPLAY = {"view": ("summary", "detail"), "hist": (3600, 86400, 604800, 2592000), "cammode": ("pics", "live"),
               "gwin": (60, 300, 900, 1800, 3600), "gpanel": (60, 300, 900, 1800, 3600)}

    def get_display(self):
        """The box's default display choices (main screen view, history window, side-panel width, camera mode). Kept in config/ so every backup carries them;
        a device that has chosen otherwise keeps its own."""
        raw = read_json(self.display_file, {}) or {}
        out = {k: raw[k] for k, ok in self.DISPLAY.items() if raw.get(k) in ok}
        if isinstance(raw.get("dw"), int) and 0 <= raw["dw"] <= 4000:
            out["dw"] = raw["dw"]
        return out

    def set_display(self, body):
        from .store import write_json
        cur = self.get_display()
        for k, v in (body or {}).items():
            if k in self.DISPLAY and v in self.DISPLAY[k]:
                cur[k] = v
            elif k == "dw" and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 4000:
                cur[k] = v
            else:
                raise ValueError(f"'{k}' is not a display setting, or its value is not allowed.")
        raw = read_json(self.display_file, {}) or {}
        keep = {k: raw[k] for k in ("timezone", "barshow") if k in raw}           # the time zone and bar filter live in the same file; saving display choices keeps them
        write_json(self.display_file, dict(cur, **keep))
        return cur

    BAR_STATES = ("failed", "degraded", "unknown")

    def get_barshow(self):
        """Which states the history bars may show, in any combination or none (a display choice: history itself keeps everything)."""
        v = (read_json(self.display_file, {}) or {}).get("barshow")
        return [x for x in self.BAR_STATES if x in v] if isinstance(v, list) else list(self.BAR_STATES)

    def set_barshow(self, v):
        from .store import write_json
        if not isinstance(v, list) or any(x not in self.BAR_STATES for x in v):
            raise ValueError("Pick from down, degraded and unknown (the names failed, degraded, unknown).")
        cur = read_json(self.display_file, {}) or {}
        cur["barshow"] = [x for x in self.BAR_STATES if x in v]
        write_json(self.display_file, cur)
        return {"show": cur["barshow"]}

    def get_timezone(self):
        """This box's time zone (an IANA name such as America/Chicago), or '' when none is set yet."""
        tz = (read_json(self.display_file, {}) or {}).get("timezone")
        return tz if isinstance(tz, str) else ""

    def apply_timezone(self):
        """Make the clock text this box writes itself (file names, mails) follow the chosen zone."""
        tz = self.get_timezone()
        if tz:
            os.environ["TZ"] = tz
            time.tzset()

    def set_timezone(self, name):
        from .store import write_json
        from zoneinfo import ZoneInfo
        if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+){0,2}$", name):
            raise ValueError("That is not a time zone name. Pick one from the list, for example America/Chicago.")
        try:
            ZoneInfo(name)
        except Exception:
            raise ValueError(f"This box does not know the time zone '{name}'.")
        cur = read_json(self.display_file, {}) or {}
        cur["timezone"] = name
        write_json(self.display_file, cur)
        self.apply_timezone()
        return {"timezone": name}

    def dismissed(self):
        return set(read_json(self.dismissed_file, []) or [])

    def dismiss_followup(self, fid):
        from .store import write_json
        write_json(self.dismissed_file, sorted(self.dismissed() | {str(fid)}))
        if str(fid).startswith("new:"):                       # answered: those items are known now, and only later ones are offered
            sug = next((x for x in self.followups(include_dismissed=True)["suggestions"] if x["id"] == fid), None)
            if sug:
                seen = self.seen_items()
                seen.setdefault(sug["from"], set()).update(sug["labels"])
                self._save_seen(seen)
        return {"message": "Hidden. It will not be suggested again."}

    SWEEP_EVERY = 1800

    def seen_items(self):
        d = read_json(self.seen_file, {})
        return {str(k): set(v) for k, v in d.items() if isinstance(v, list)} if isinstance(d, dict) else {}

    def _save_seen(self, seen):
        from .store import write_json
        write_json(self.seen_file, {k: sorted(v) for k, v in seen.items()})

    def _sweep_run(self):
        """Ask every connection what it can see (read-only, in the background, one at a time). A connection that cannot be reached is skipped
        and keeps what it showed last time: a silent source proposes nothing. The first time a connection is seen, everything it offers is
        taken as known, so only things that appear later are proposed."""
        try:
            conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict) and c.get("module") and c.get("id")]
            seen, changed = self.seen_items(), False
            for c in conns:
                try:
                    ent = self.pt_cache.get(c["id"]) if c["module"] == "portainer" else None
                    out = ent["out"] if ent and ent.get("out") else self.modules.call(c["module"], "discover", {"connection": c}, 30)
                except Exception:
                    continue
                if not isinstance(out, dict):
                    continue
                self.sweep["out"][c["id"]] = out
                if c["id"] not in seen:
                    seen[c["id"]] = {str(x.get("label")) for x in out.get("suggest") or [] if x.get("label")}
                    changed = True
            for gone in set(self.sweep["out"]) - {c["id"] for c in conns}:
                self.sweep["out"].pop(gone, None)
            if changed:
                self._save_seen(seen)
        except Exception:
            pass
        finally:
            self.sweep.update(at=time.time(), running=False)

    def new_item_followups(self, conns):
        seen, per = self.seen_items(), []
        for c in conns:
            found = self.sweep["out"].get(c.get("id"))
            if not found or c.get("id") not in seen:
                continue
            have = monconfig.watched_ids(self.paths, c["id"])
            known = lambda it, have=have, sn=seen[c["id"]]: monconfig.check_id(it.get("label")) in have or it.get("label") in sn
            items = followups.new_items(found, lambda label, have=have: monconfig.check_id(label) in have, seen[c["id"]])
            per.append((c, found, items, known))
        founds = {c["id"]: f for c, f, _, _ in per}
        return [followups.new_items_proposal(c, items, followups.machine_of(c, founds[c["id"]], items, conns)) for c, items in followups.one_home(per) if items]

    def _refresh_portainer(self, conn):
        try:
            out = self.modules.call("portainer", "discover", {"connection": conn}, 40)
        except Exception:
            out = None
        self.pt_cache[conn["id"]] = {"at": time.time(), "out": out}
        self.pt_running.discard(conn["id"])

    def followups(self, include_dismissed=False):
        """Everything MonitorBox can propose adding. Portainer is asked in the background (it can take seconds); until it has answered
        the reply says `pending` and the page asks again."""
        conns = [c for c in monconfig.load_config(self.paths).get("connections", []) if isinstance(c, dict)]
        pending, outs = False, []
        for c in conns:
            if c.get("module") != "portainer":
                continue
            ent = self.pt_cache.get(c["id"])
            if (not ent or time.time() - ent["at"] > 600) and c["id"] not in self.pt_running:
                self.pt_running.add(c["id"])
                threading.Thread(target=self._refresh_portainer, args=(c,), daemon=True).start()
            if not ent:
                pending = True
            elif ent["out"]:
                outs.append(ent["out"])
        nodes, _err = monconfig.all_nodes(self.paths)
        covered = followups.watched_origins(nodes)
        if time.time() - self.web_cache["at"] > 600 and not self.web_cache["running"]:
            self.web_cache["running"] = True
            tg = followups.web_targets(nodes, conns, thisbox.gateway(), thisbox.dns_servers())
            threading.Thread(target=self._refresh_web, args=(tg,), daemon=True).start()
        if not self.web_cache["at"]:
            pending = True
        web = [x for x in self.web_cache["out"] if followups.origin_of(x["url"]) not in covered]
        gone = set() if include_dismissed else self.dismissed()
        if time.time() - self.sweep["at"] > self.SWEEP_EVERY and not self.sweep["running"]:
            self.sweep["running"] = True
            threading.Thread(target=self._sweep_run, daemon=True).start()
        sug = followups.merge(web, followups.suggest(conns, self.port_open), followups.from_portainer(outs, conns), self.new_item_followups(conns),
                              self.switch_followups(conns))
        return {"suggestions": [x for x in sug if x["id"] not in gone], "pending": pending or self.sw_cache["running"], "notes": followups.notes_from_portainer(outs)}

    SWITCH_EVERY = 1800

    def switch_followups(self, conns):
        """UniFi switches that answer the SNMP login already saved (read-only; the first look is in the background, a retry every 30 minutes
        and whenever the list of switches changes)."""
        source = followups.snmp_source(conns, self.sweep["out"])
        cands = followups.switch_candidates(conns, self.sweep["out"]) if source else []
        if not source or not cands:
            return []
        key = (source["id"], tuple(ip for _n, ip in cands))
        c = self.sw_cache
        if (c["key"] != key or time.time() - c["at"] > self.SWITCH_EVERY) and not c["running"]:
            c["running"] = True
            threading.Thread(target=self._refresh_switches, args=(source, cands, key), daemon=True).start()
        known = {ip for _n, ip in cands}
        answered = [a for a in c["answered"] if c["source"] == source["id"] and a["ip"] in known]
        return [followups.switches_proposal(source, answered)] if answered else []

    def _refresh_switches(self, source, cands, key):
        """Try the one login on each switch's address, four at a time. A wrong login or a silent switch just means 'not offered'."""
        def one(t):
            name, ip = t
            try:
                r = self.modules.call("snmp", "probe", {"connection": {**source, "host": ip}}, 15)
            except Exception:
                return None
            return {"name": name, "ip": ip} if isinstance(r, dict) and r.get("ok") else None
        try:
            with ThreadPoolExecutor(max_workers=4) as ex:
                answered = [a for a in ex.map(one, cands) if a]
        except Exception:
            answered = []
        self.sw_cache.update(at=time.time(), running=False, key=key, source=source["id"], answered=answered)

    def add_snmp_switches(self, sug):
        """Add an SNMP connection for each switch that answered, with the saved login copied on the box. Connections only: UniFi already
        watches these switches, and the map and switch report read their ports."""
        cfg = monconfig.load_config(self.paths)
        conns = cfg.get("connections", [])
        source = next((c for c in conns if c.get("id") == sug["from"]), None)
        if not source:
            raise ValueError("That suggestion is no longer available.")
        have = {c.get("id") for c in conns}
        hosts = {followups.host_of(c) for c in conns if c.get("module") == "snmp"}
        new = []
        for sw in sug["switches"]:
            if sw["ip"].lower() in hosts:
                continue
            n = followups.switch_connection(source, sw, have)
            have.add(n["id"]); new.append(n)
        if new:
            monconfig.save_connections(self.paths, conns + new, cfg.get("revision", 0))
            self.reload_monitoring()
        self.sw_cache["answered"] = []
        return {"message": f"Added {len(new)} switch{'' if len(new) == 1 else 'es'}. Their ports now show on the network map and in the switch report.", "added": len(new)}

    def _refresh_web(self, targets):
        try:
            out = followups.web_suggestions(targets, set(), thisbox.identify_web)       # what is already watched is filtered when asked, so adding one clears it at once
        except Exception:
            out = []
        self.web_cache.update(at=time.time(), out=out, running=False)

    def add_web_followup(self, sug):
        """Watch a recognised web page. The router and DNS servers join the system they already have (so the page going quiet while the
        machine still answers reads Degraded, not Down); anything else becomes a system of its own."""
        nodes = {n.get("id"): n for n in monconfig.get_monitoring(self.paths)["monitoring"].get("nodes", [])}
        system = "gateway" if sug.get("role") == "gateway" else "dns-" + sug["host"].replace(".", "-") if sug.get("role") == "dns" else None
        system = system if system in nodes and nodes[system].get("kind") != "aggregate" else None
        group = "Network" if sug.get("role") in ("gateway", "dns") else "Services"
        out = monconfig.add_web_page(self.paths, sug["title"][:60], sug["url"], system, group, None, None, bool(sug.get("insecure")), sug["url"])
        self.web_cache["out"] = [x for x in self.web_cache["out"] if x["id"] != sug["id"]]
        self.reload_monitoring()
        return {"message": f"Now watching {sug['title']}.", "node": out["node"]}

    def add_followup(self, fid):
        """Add what a follow-up proposes, in one step: the connection (login copied on the box), then everything its module suggests by default."""
        sug = next((x for x in self.followups(include_dismissed=True)["suggestions"] if x["id"] == fid), None)
        if sug and sug["how"] == "webpage":
            return self.add_web_followup(sug)
        if sug and sug["how"] == "items":
            return self.add_new_items(sug)
        if sug and sug["how"] == "snmp-switches":
            return self.add_snmp_switches(sug)
        if not sug or sug["how"] != "add":
            raise ValueError("That suggestion is no longer available.")
        cfg = monconfig.load_config(self.paths)
        conns = cfg.get("connections", [])
        source = next(c for c in conns if c.get("id") == sug["from"])
        new = followups.protect_from(source, {c.get("id") for c in conns})
        monconfig.save_connections(self.paths, conns + [new], cfg.get("revision", 0))
        added = 0
        try:
            found = self.detect(new["id"])
            items = [monconfig.watch_item(x)
                     for x in found.get("suggest", []) if not x.get("system") and x.get("default") is not False and x.get("batch") != "Network interfaces"]
            if items:
                added = monconfig.add_watches(self.paths, new["id"], items).get("added", 0)
        except (ValueError, monconfig.Invalid) as e:
            self.reload_monitoring()
            return {"message": f"Added {sug['title']}, but could not read it yet: {e}", "connection": new["id"], "added": 0}
        self.reload_monitoring()
        return {"message": f"Added {sug['title']}" + (f" and started watching {added} thing{'' if added == 1 else 's'}." if added else "."), "connection": new["id"], "added": added}

    def add_new_items(self, sug):
        """Watch the new things a connection offers: the same items Re-detect would tick by default."""
        cid = sug["from"]
        found = self.sweep["out"].get(cid) or {}
        want = set(sug["labels"])
        items = [monconfig.watch_item(x) for x in found.get("suggest", []) if x.get("label") in want]
        added = monconfig.add_watches(self.paths, cid, items).get("added", 0) if items else 0
        seen = self.seen_items()
        seen.setdefault(cid, set()).update(want)
        self._save_seen(seen)
        self.reload_monitoring()
        return {"message": f"Now watching {added} new thing{'' if added == 1 else 's'}.", "connection": cid, "added": added}

    def restart_app(self, wipe=False):
        """Ask the launcher for a fresh App (it starts one whenever the App exits). With wipe, settings, password and history go first."""
        self.wipe = wipe
        self.exit_code = RESTART_EXIT
        threading.Thread(target=lambda: (time.sleep(0.5), self.httpd.shutdown()), daemon=True).start()
        return {"message": "Factory reset: starting over from the setup screen…" if wipe else "Restarting…", "restarting": True}

    def factory_reset(self, confirm):
        """Back to a new box: the settings, the password, the history and the installed modules are deleted. The backups stay, so a mistake
        can be undone by restoring one; the modules are downloaded again, fresh, when the App starts. Done once the App has stopped."""
        if confirm != "RESET":
            raise ValueError('Type RESET to confirm.')
        return self.restart_app(wipe=True)

    def wipe_settings(self):
        for d in ("config",):
            full = os.path.join(self.paths.root, d)
            for name in os.listdir(full) if os.path.isdir(full) else []:
                p = os.path.join(full, name)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.unlink(p)
        for p in (self.paths.auth, self.paths.modules_state):
            if os.path.exists(p):
                os.unlink(p)
        shutil.rmtree(self.paths.module_releases, ignore_errors=True)     # installed modules: first_run_sync fetches the channel's again

    def first_run_sync(self):
        """Install the modules the channel names that we have never had (hello runs on first start)."""
        try:
            self.refresh()
            st = self.modules.state()
            d = self.default_id()
            sources = self.cfg()["module_sources"]
            for r in self.repos():
                if not r["enabled"]:
                    continue
                for mid, ent in ((self.infos.get(r["id"]) or {}).get("pointer") or {}).get("modules", {}).items():
                    # the default repository's modules are all installed on a new box; another repository's only if this box (restored from a backup) used it
                    if mid not in st and mid not in self.cfg()["uninstalled"] and mid in modules_current([mid]) and (r["id"] == d and sources.get(mid, d) == d or sources.get(mid) == r["id"]):
                        self.modules.apply_one(mid, ent)
        except Exception:
            pass

    # -- http ------------------------------------------------------------
    def internal_session(self):
        """A session token for this box's own site port to call its API on a paired main box's behalf (never leaves this process)."""
        tok = getattr(self, "_internal_tok", None)
        if not tok:
            tok = self._internal_tok = secrets.token_urlsafe(32)
        self.auth.sessions[tok] = time.time() + 3600
        return tok

    def sites_post(self, path, body):
        p = self.peer
        if path == "/api/sites/name":
            p.set_name(body.get("name")); return p.get()
        if path == "/api/sites/listen":
            port = body.get("port")
            return p.set_listen(bool(body.get("enabled")), int(port) if port not in (None, "") else None)
        if path == "/api/sites/pair/start":
            return p.start_pairing()
        if path == "/api/sites/pair/stop":
            p.stop_pairing(); return p.get()
        if path == "/api/sites/add":
            return p.add_site(str(body.get("address", "")), str(body.get("code", "")), body.get("name"))
        if path == "/api/sites/remove":
            return p.remove_site(str(body.get("id", "")))
        if path == "/api/sites/remote-name":
            return p.name_remote(str(body.get("id", "")))
        if path == "/api/sites/rename":
            return p.rename_site(str(body.get("id", "")), body.get("name"))
        if path == "/api/sites/manager/remove":
            return p.remove_manager(str(body.get("id", "")))
        return None

    def serve(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def token(self):
                c = SimpleCookie(self.headers.get("Cookie", ""))
                return c["mb"].value if "mb" in c else None

            def req(self):
                """Who is really asking (see security.py): the proxy's visitor, or the direct peer."""
                r = getattr(self, "_req", None)
                if r is None:
                    r = self._req = app.security.request(self.client_address[0], self.headers)
                return r

            def send(self, code, obj=None, cookie=None, html=None):
                body = (html or json.dumps(obj if obj is not None else {})).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "frame-ancestors 'none'")      # nothing may put this page in a frame (the page's own scripts are untouched)
                if self.req().https:
                    self.send_header("Strict-Transport-Security", "max-age=31536000")
                if cookie:
                    self.send_header("Set-Cookie", cookie + ("; Secure" if self.req().https else ""))
                self.end_headers()
                self.wfile.write(body)

            def brand(self, fname, ctype):
                """MonitorBox's own mark: favicon, home-screen icons and the install manifest. Public, so a browser can fetch them before sign-in."""
                with open(os.path.join(BRAND_DIR, fname), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(body)

            def icon(self, name):
                """The app's own bundled service icons (app/monitorbox_app/icons/<name>.svg). Nothing is fetched from anywhere else."""
                base = name.split("?")[0]
                if base == "index.json":          # which icons exist, so the page picks one by name without guessing at 404s
                    names = sorted(f[:-4] for f in os.listdir(ICON_DIR) if f.endswith(".svg"))
                    body = json.dumps({"icons": names, "aliases": ICON_ALIASES}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                slug = ICON_ALIASES.get(base[:-4], base[:-4]) if base.endswith(".svg") else ""
                path = next((q for q in (os.path.join(ICON_DIR, c + ".svg") for c in (slug, slug.replace("-", "")))
                             if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", os.path.basename(q)[:-4]) and os.path.isfile(q)), None)
                if not path:
                    self.send_response(404); self.end_headers(); return
                with open(path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
                self.end_headers()
                self.wfile.write(body)

            def site_pass(self, method, n):
                """/api/site/<id>/<rest>: the same request, made on a managed site."""
                m = re.match(r"/api/site/([a-z0-9-]+)/(.*)$", self.path, re.S)
                if not m:
                    return self.send(404, {"error": "not found"})
                site, rest = m.group(1), m.group(2)
                first = rest.split("?", 1)[0]
                if method == "POST" and first == "live/open":
                    return self.site_live_open(site, n)
                line_filter, after = None, None
                if method == "GET" and first == "live/events":
                    line_filter = self.relay_events
                    cid = (parse_qs(urlparse(rest).query).get("client") or [""])[0]
                    after = lambda: app.relays.close_client(cid)           # the page went away: its media goes with it
                hdr = {"X-MB": "1"}
                if self.headers.get("Content-Type"):
                    hdr["Content-Type"] = self.headers["Content-Type"]
                try:
                    conn, resp = app.peer.open(site, method, "/peer/api/" + rest, hdr, self.rfile, n)
                except peer.PeerError as e:
                    return self.send(502, {"error": str(e), "unreachable": True, "kind": e.kind})
                try:
                    peer.relay(resp, self, conn, line_filter)
                finally:
                    conn.close()
                    if after:
                        after()

            def site_live_open(self, site, n):
                """Start a live view on a managed site, with its video coming through the site link: this box opens a UDP port for the
                browser and joins the site's own relay port to it. A site that does not know about relays answers without one, and the
                view is then direct (which works where the browser can reach Scrypted)."""
                import io
                try:
                    body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                except ValueError:
                    return self.send(400, {"error": "bad json"})
                body["relay"] = True
                data = json.dumps(body).encode()
                app.relays.begin()
                try:
                    try:
                        conn, resp = app.peer.open(site, "POST", "/peer/api/live/open", {"X-MB": "1", "Content-Type": "application/json"}, io.BytesIO(data), len(data))
                    except peer.PeerError as e:
                        return self.send(502, {"error": str(e), "unreachable": True, "kind": e.kind})
                    try:
                        status, raw = resp.status, resp.read(1 << 16)
                    finally:
                        conn.close()
                    try:
                        out = json.loads(raw)
                    except ValueError:
                        out = {"error": "the site sent an answer this box cannot read"}
                    sid = out.get("session") if isinstance(out, dict) else None
                    if status == 200 and sid and out.get("relay"):
                        ip = self.connection.getsockname()[0].replace("::ffff:", "")      # the address the browser reached this box at
                        pipe = liverelay.Pipe()
                        app.relays.add(sid, pipe, ip, str(body.get("client", "")))
                        def run():
                            try:
                                app.peer.open_udp(site, sid, pipe)
                            except Exception:
                                pass
                            finally:
                                pipe.close()
                        threading.Thread(target=run, daemon=True).start()
                    return self.send(status, out)
                finally:
                    app.relays.end()

            def relay_events(self, line):
                """One line of a managed site's live event stream, on its way to the browser. The site has taken its own addresses out of the
                setup messages; this box puts its relay address in, so the browser sends its media here."""
                if not line.startswith(b"data: "):
                    return line
                try:
                    item = json.loads(line[6:])
                    sid, msg = item.get("session"), item.get("message") or {}
                    if msg.get("type") == "closed":
                        e = app.relays.pop(sid)
                        if e:
                            e["pipe"].close()
                    elif msg.get("type") == "call" and msg.get("method") == "setRemoteDescription":
                        e = app.relays.get(sid, 3.0)
                        a = msg.get("args") or []
                        if e and a and isinstance(a[0], dict) and "sdp" in a[0]:
                            a[0]["sdp"] = liverelay.with_candidate(a[0]["sdp"], e["ip"], e["pipe"].port)
                            return b"data: " + json.dumps(item, separators=(",", ":")).encode()
                except (ValueError, AttributeError, TypeError):
                    pass
                return line

            def peer_gone(self):
                """True when the other end has closed the connection (it sends nothing after its request, so 'readable' means 'closed')."""
                import select, socket
                try:
                    if select.select([self.connection], [], [], 0)[0]:
                        return self.connection.recv(1, socket.MSG_PEEK) == b""
                except OSError:
                    return True
                return False

            def live_events(self):
                """The setup messages of this page's live views, as a server-sent event stream (one per page, shared by every camera)."""
                import queue
                cid = (parse_qs(urlparse(self.path).query).get("client") or [""])[0]
                try:
                    q = app.live_hub_open(cid)
                except ValueError as e:
                    return self.send(409, {"error": str(e)})
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(b": open\n\n"); self.wfile.flush()
                    last = time.monotonic()
                    while True:
                        try:
                            item = q.get(timeout=1)
                            self.wfile.write(b"data: " + json.dumps(item, separators=(",", ":")).encode() + b"\n\n")
                            last = time.monotonic()
                        except queue.Empty:
                            if self.peer_gone():
                                break                                      # the page closed: its live views end now, not at the next write
                            if time.monotonic() - last > 15:
                                self.wfile.write(b": ping\n\n"); last = time.monotonic()
                        self.wfile.flush()
                except (OSError, ValueError):
                    pass                                                   # the page went away
                finally:
                    app.live_hub_close(cid)

            def ha_callback(self):
                """Home Assistant sends the browser back here after the owner signs in there. The browser is arriving from another
                address, so it carries no MonitorBox session; the one-time state value started by the signed-in owner is the proof."""
                q = parse_qs(urlparse(self.path).query)
                ok, msg = app.alerts.complete_connect((q.get("code") or [""])[0], (q.get("state") or [""])[0], (q.get("error") or [""])[0])
                from html import escape
                dest = "/#/settings/alerts"
                body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>MonitorBox</title>"
                        f"<body style='font:17px system-ui;background:#10201f;color:#e8f0ef;padding:2rem'>"
                        f"<p>{escape(msg)}</p><p><a style='color:#6fe3c1' href='{dest}'>Back to MonitorBox</a></p>"
                        f"<script>setTimeout(function(){{location.replace('{dest}')}},{600 if ok else 4000})</script>")
                return self.send(200, html=body)

            def passkey_flags(self):
                n = app.passkeys.count()
                return {"passkeys": n > 0, "passkeyOnly": n > 0 and self.req().via_proxy and app.security.cfg()["internetNeedsPasskey"]}

            def ceremony(self):
                """(site name, exact origin) a passkey answer must carry. Only the owner's public HTTPS name counts (and plain localhost, for tests)."""
                r = self.req(); host = app.security.cfg()["publicHost"]
                if not host:
                    raise ValueError("Set your public name first, under Settings \u2192 Sign-in and security.")
                if r.via_proxy:
                    if not r.https:
                        raise ValueError("Passkeys need HTTPS. Open MonitorBox at https://" + host)
                    return host, "https://" + host
                if host == "localhost" and str(self.headers.get("Host") or "").startswith("localhost"):
                    return host, "http://" + str(self.headers.get("Host"))
                raise ValueError("Passkeys work only through your public HTTPS address: https://" + host)

            def signed_in_cookie(self, tok):
                return self.send(200, {"ok": True}, cookie=f"mb={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000")

            def wrong_host(self):
                if app.security.host_ok(self.req()):
                    return False
                self.send(421, {"error": "wrong address"})
                return True

            def do_GET(self):
                t0 = time.monotonic()
                try:
                    if self.wrong_host():
                        return
                    return self._get()
                finally:
                    if not perfstats.skip(self.path):
                        perfstats.record("request", perfstats.request_key("GET", self.path), (time.monotonic() - t0) * 1000)

            def do_POST(self):
                t0 = time.monotonic()
                try:
                    if self.wrong_host():
                        return
                    return self._post()
                finally:
                    if not perfstats.skip(self.path):
                        perfstats.record("request", perfstats.request_key("POST", self.path), (time.monotonic() - t0) * 1000)

            def _get(self):
                if self.path.startswith("/icons/"):
                    return self.icon(self.path[7:])
                if self.path in BRAND_ROUTES:
                    return self.brand(*BRAND_ROUTES[self.path])
                if self.path == "/":
                    return self.send(200, html=PAGE)
                if self.path.startswith("/ha-callback?"):
                    return self.ha_callback()
                if self.path == "/api/health":
                    if self.req().via_proxy and not app.auth.valid(self.token()):      # a stranger on the internet learns nothing about the box
                        return self.send(200, {"ok": True, "passwordSet": app.auth.is_set(), **self.passkey_flags()})
                    return self.send(200, {"ok": True, "version": version(), "channel": app.cfg()["channel"],
                                           "passwordSet": app.auth.is_set(), **self.passkey_flags()})
                if not app.auth.valid(self.token()):
                    return self.send(401, {"error": "sign in"})
                if self.path.startswith("/api/site/"):
                    return self.site_pass("GET", 0)
                if self.path == "/api/sites":
                    return self.send(200, app.peer.get())
                if self.path == "/api/state":
                    return self.send(200, {"version": version(), "channel": app.cfg()["channel"],
                                           "modules": app.modules.describe()})
                if self.path == "/api/versions":
                    return self.send(200, app.view())
                if self.path == "/api/about":
                    return self.send(200, sysinfo.about())
                if self.path == "/api/perf":
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.send(200, {"version": version(), "requests": perfstats.summary("request"), "modules": perfstats.summary("module"),
                                           "processes": sysinfo.processes(app.modules.pids()), "about": sysinfo.about(), "since": int(perfstats.started()), "cpus": os.cpu_count()})
                if self.path == "/api/lan/map":
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.send(200, app.build_map())
                if self.path.startswith("/api/power"):
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.send(200, app.power_page(refresh="refresh=1" in self.path))
                if self.path.startswith("/api/lan/busiest"):
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    try:
                        secs = int((parse_qs(urlparse(self.path).query).get("seconds") or ["300"])[0])
                    except ValueError:
                        secs = 300
                    return self.send(200, app.busiest_data(secs))
                if self.path.startswith("/api/lan/peers?"):
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    q = parse_qs(urlparse(self.path).query)
                    try:
                        win = int((q.get("win") or ["900"])[0])
                    except ValueError:
                        win = 900
                    return self.send(200, app.lan_peers((q.get("node") or [""])[0], (q.get("port") or [""])[0], win))
                if self.path.startswith("/api/lan/flows?"):
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    q = parse_qs(urlparse(self.path).query)
                    win = (q.get("win") or ["900"])[0]
                    return self.send(200, app.lan_flows((q.get("graph") or [""])[0], int(win) if win.isdigit() else 900))
                if self.path == "/api/lan/flows-look":
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.send(200, app.flows_look())
                if self.path == "/api/lan/report":
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.send(200, app.lan_report())
                if self.path == "/api/status":
                    return self.send(200, app.snapshot())
                if self.path == "/api/cameras":
                    return self.send(200, app.cameras())
                if self.path.startswith("/api/camera-snapshot?"):
                    q = parse_qs(urlparse(self.path).query)
                    try:
                        mime, raw = app.camera_snapshot((q.get("conn") or [""])[0], (q.get("id") or [""])[0])
                    except Exception as e:
                        return self.send(404, {"error": plain_error(str(e))})
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/api/live/relays":
                    st = app._live_state()
                    with st["lock"]:
                        site = [dict(x["relay"]["pipe"].stats(), view=sid[:4]) for sid, x in st["sessions"].items() if x.get("relay")]
                    return self.send(200, {"mainBox": app.relays.stats(), "siteBox": site, "liveViews": len(st["sessions"])})
                if self.path.startswith("/api/live/events?"):
                    return self.live_events()
                if self.path == "/api/followups":
                    return self.send(200, app.followups())
                if self.path == "/api/display":
                    return self.send(200, app.get_display())
                if self.path == "/api/timezone":
                    return self.send(200, {"timezone": app.get_timezone()})
                if self.path == "/api/barshow":
                    return self.send(200, {"show": app.get_barshow()})
                if self.path == "/api/security":
                    r = self.req()
                    return self.send(200, {**app.security.cfg(), "passkeys": app.passkeys.listing(), "signedIn": app.auth.signed_in(), "you": {"ip": r.ip, "viaProxy": r.via_proxy, "https": r.https}})
                if self.path == "/api/alerts":
                    return self.send(200, app.alerts.get())
                if self.path == "/api/alerts/ha/devices":
                    try:
                        return self.send(200, {"devices": app.alerts.devices()})
                    except alerts.Invalid as e:
                        return self.send(200, {"devices": [], "error": str(e), "needsSignIn": app.alerts.needs_sign_in})
                if self.path == "/api/graphs":
                    return self.send(200, {"graphs": read_json(app.graphs_file, []) or []})
                if self.path == "/api/graphs/data" or self.path.startswith("/api/graphs/data?"):
                    sec = (parse_qs(urlparse(self.path).query).get("seconds") or ["300"])[0]
                    app.graphs.viewing()
                    return self.send(200, app.graphs.data(int(sec) if sec.isdigit() else 300))
                if self.path == "/api/thisbox" or self.path.startswith("/api/thisbox?"):
                    host = (parse_qs(urlparse(self.path).query).get("host") or [""])[0].strip()
                    if host and not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host):
                        return self.send(400, {"error": "That is not an address."})
                    return self.send(200, app.thisbox_scan(host) if host else app.thisbox_scan())
                if self.path.startswith("/api/history?"):
                    q = parse_qs(urlparse(self.path).query)
                    if q.get("events"):                    # the history page: every stretch that was not healthy in a range, newest first
                        try:
                            lo, hi = int(q["from"][0]), int(q["to"][0])
                        except (KeyError, ValueError, IndexError):
                            return self.send(400, {"error": "from and to must be numbers"})
                        want = [x for x in (q.get("states") or ["failed,degraded,unknown"])[0].split(",") if x in ("failed", "degraded", "unknown")]
                        r = app.history.trouble(app.history.node_ids(), lo, hi, limit=500, show=want, newest_first=True,
                                                min_seconds=app.monitor.grace_seconds, brief=bool(q.get("brief")))
                        r["names"] = {n["id"]: n.get("name") or n["id"] for n in app.monitor.nodes}
                        return self.send(200, r)
                    if q.get("trouble"):                   # what was not healthy in one slice of a card's bar
                        ids = [x for x in q["trouble"][0].split(",") if x][:200]
                        try:
                            lo, hi = int(q["from"][0]), int(q["to"][0])
                        except (KeyError, ValueError, IndexError):
                            return self.send(400, {"error": "from and to must be numbers"})
                        return self.send(200, app.history.trouble(ids, lo, hi, show=app.get_barshow(), min_seconds=app.monitor.grace_seconds))
                    if q.get("strip"):                     # one card's 24 h bar: the worst of its nodes, hour by hour
                        ids = [x for x in q["strip"][0].split(",") if x][:200]
                        return self.send(200, app.history.strip(ids, show=app.get_barshow(), min_seconds=app.monitor.grace_seconds))
                    nid = (q.get("node") or [""])[0]
                    try:
                        secs = int((q.get("seconds") or [0])[0]) or None
                    except ValueError:
                        return self.send(400, {"error": "seconds must be a number"})
                    return self.send(200, app.history.timeline(nid, secs)) if nid else self.send(400, {"error": "node is required"})
                if self.path == "/api/config/monitoring":
                    return self.send(200, monconfig.get_monitoring(app.paths))
                if self.path == "/api/config/connections":
                    return self.send(200, monconfig.get_connections(app.paths))
                if self.path == "/api/stream":
                    return self.stream()
                if self.path == "/api/backups":
                    try:
                        return self.send(200, app.backup_list())
                    except ValueError as e:
                        return self.send(400, {"error": str(e)})
                if self.path.startswith("/api/backups/download"):
                    try:
                        lib = backups.lib()
                        name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
                        p = lib.path_of(app.paths.root, name)
                    except (ValueError, Exception) as e:
                        return self.send(400, {"error": str(e)})
                    self.send_response(200)
                    self.send_header("Content-Type", "application/gzip")
                    self.send_header("Content-Length", str(os.path.getsize(p)))
                    self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    with open(p, "rb") as f:
                        while True:
                            chunk = f.read(1 << 20)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                    return
                self.send(404, {"error": "not found"})

            def stream(self):
                """Server-sent events: a full snapshot now, then one each time something changes."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                seen = -1
                try:
                    while not app.monitor.stopped:
                        # a snapshot on every change, and one every 15 s anyway so the screen can say how fresh it is
                        seen = app.monitor.version
                        self.wfile.write(b"data: " + json.dumps(app.snapshot()).encode() + b"\n\n")
                        self.wfile.flush()
                        app.monitor.wait_for_change(seen, 15)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def upload(self, n):
                if not app.auth.valid(self.token()):
                    return self.send(401, {"error": "sign in"})
                try:
                    lib = backups.lib()
                    if n <= 0 or n > lib.MAX_BYTES:
                        return self.send(400, {"error": "That file is empty or too large."})
                    bdir = lib.backups_dir(app.paths.root)
                    os.makedirs(bdir, exist_ok=True)
                    tmp = os.path.join(bdir, f".tmp-upload-{os.getpid()}")
                    try:
                        with open(tmp, "wb") as f:
                            left = n
                            while left:
                                chunk = self.rfile.read(min(left, 1 << 20))
                                if not chunk:
                                    break
                                f.write(chunk)
                                left -= len(chunk)
                        lib.validate(tmp)
                        final = os.path.join(bdir, time.strftime("monitorbox-uploaded-%Y%m%d-%H%M%S.tgz"))
                        os.replace(tmp, final)
                    finally:
                        if os.path.exists(tmp):
                            os.unlink(tmp)
                    return self.send(200, {"name": os.path.basename(final), **app.backup_list()})
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                except Exception as e:
                    return self.send(400, {"error": str(e)})

            def _post(self):
                if self.headers.get("X-MB") != "1":  # blocks cross-site form posts
                    return self.send(403, {"error": "forbidden"})
                n = int(self.headers.get("Content-Length") or 0)
                if self.path.startswith("/api/site/"):
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    return self.site_pass("POST", n)
                if self.path == "/api/backups/upload":
                    return self.upload(n)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self.send(400, {"error": "bad json"})
                path = self.path
                try:
                    if path == "/api/setup":
                        if self.req().via_proxy:                  # a reset box must not be claimable by whoever finds it first on the internet
                            return self.send(403, {"error": "Set the first password from your home network, not through the internet address."})
                        app.auth.set_password(body.get("password", ""))
                        return self.send(200, {"ok": True})
                    if path in ("/api/passkeys/login/options", "/api/passkeys/login/finish"):
                        r = self.req()
                        w = app.security.lockout.wait(r.ip, r.via_proxy)
                        if w:
                            return self.send(429, {"error": f"Too many wrong tries. Try again in {max(1, (w + 59) // 60)} minute{'' if w <= 60 else 's'}.", "retryAfter": w})
                        try:
                            rp, origin = self.ceremony()
                            if path.endswith("options"):
                                return self.send(200, app.passkeys.login_options(rp))
                            app.passkeys.login_finish(body.get("handle"), body.get("credential") or {}, rp, origin)
                        except ValueError as e:
                            if path.endswith("finish"):
                                app.security.lockout.failed(r.ip, r.via_proxy)
                                print(f"passkey sign-in failed from {r.ip}{' (through the proxy)' if r.via_proxy else ''}", file=sys.stderr, flush=True)
                            return self.send(401 if path.endswith("finish") else 400, {"error": str(e)})
                        app.security.lockout.ok(r.ip)
                        return self.signed_in_cookie(app.auth.issue())
                    if path == "/api/login":
                        r = self.req()
                        if r.via_proxy and app.security.cfg()["internetNeedsPasskey"] and app.passkeys.count():
                            return self.send(403, {"error": "From outside your home network, sign in with a passkey."})
                        w = app.security.lockout.wait(r.ip, r.via_proxy)
                        if w:
                            return self.send(429, {"error": f"Too many wrong passwords. Try again in {max(1, (w + 59) // 60)} minute{'' if w <= 60 else 's'}.", "retryAfter": w})
                        tok = app.auth.login(body.get("password", ""))
                        if not tok:
                            app.security.lockout.failed(r.ip, r.via_proxy)
                            print(f"sign-in failed from {r.ip}{' (through the proxy)' if r.via_proxy else ''}", file=sys.stderr, flush=True)
                            return self.send(401, {"error": "wrong password"})
                        app.security.lockout.ok(r.ip)
                        return self.send(200, {"ok": True},
                                         cookie=f"mb={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000")
                    if not app.auth.valid(self.token()):
                        return self.send(401, {"error": "sign in"})
                    if path == "/api/logout":
                        app.auth.logout(self.token())
                        return self.send(200, {"ok": True}, cookie="mb=; Max-Age=0; Path=/")
                    if path.startswith("/api/sites/"):
                        try:
                            out = app.sites_post(path, body)
                        except peer.Invalid as e:
                            return self.send(400, {"error": str(e)})
                        except peer.PeerError as e:
                            return self.send(400, {"error": str(e)})
                        if out is not None:
                            return self.send(200, out)
                    if path == "/api/demo":
                        app.set_demo(body.get("scenario"))
                        return self.send(200, {"demo": app.demo})
                    if path == "/api/live/open":
                        via_site = self.headers.get("X-MB") == "1"
                        return self.send(200, {"session": app.live_open(str(body.get("client", "")), str(body.get("connection", "")), str(body.get("id", "")), body.get("options"),
                                                                        relay=bool(body.get("relay")) and via_site), "relay": bool(body.get("relay")) and via_site})
                    if path == "/api/live/input":
                        app.live_input(str(body.get("session", "")), body.get("message"))
                        return self.send(200, {"ok": True})
                    if path == "/api/live/close":
                        app.live_close(str(body.get("session", "")))
                        return self.send(200, {"ok": True})
                    if path == "/api/wake":
                        return self.send(200, app.wake(str(body.get("id", ""))))
                    if path == "/api/connections/test":
                        return self.send(200, app.test_connection(body.get("connection")))
                    if path == "/api/detect":
                        return self.send(200, app.detect(str(body.get("connection", ""))))
                    if path == "/api/watch":
                        try:
                            items = body.get("items") or [{k: body.get(k) for k in ("label", "check", "params", "node", "group")}]
                            out = monconfig.add_watches(app.paths, str(body.get("connection", "")), items)
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "Could not add it: " + "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/power":
                        try:
                            out = monconfig.set_powered_by(app.paths, str(body.get("system", "")), str(body.get("ups")) if body.get("ups") else None)
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        app._power = None
                        return self.send(200, app.power_page())
                    if path == "/api/rename":
                        try:
                            out = monconfig.rename_node(app.paths, str(body.get("id", "")), body.get("name"))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/check-url":
                        try:
                            out = monconfig.set_check_url(app.paths, str(body.get("id", "")), str(body.get("check", "")), body.get("url"))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/service-link":
                        try:
                            out = monconfig.set_service_link(app.paths, str(body.get("id", "")), body.get("url"))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/web-page":
                        try:
                            out = monconfig.add_web_page(app.paths, body.get("name"), body.get("url"), body.get("system") or None,
                                                         body.get("group") or "Services", body.get("contains"), body.get("expect"),
                                                         bool(body.get("insecure")), body.get("link"))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/alerts/ha/begin":
                        origin = self.headers.get("Origin") or "http://" + str(self.headers.get("Host") or "")
                        try:
                            return self.send(200, {"url": app.alerts.begin_connect(body.get("url"), origin)})
                        except alerts.Invalid as e:
                            return self.send(400, {"error": str(e)})
                    if path in ("/api/alerts/ha/token", "/api/alerts/ha/disconnect", "/api/alerts/ha/devices"):
                        try:
                            if path.endswith("/token"):
                                return self.send(200, app.alerts.connect_token(body.get("url"), body.get("token")))
                            if path.endswith("/disconnect"):
                                return self.send(200, app.alerts.disconnect())
                            return self.send(200, app.alerts.set_devices(body.get("devices")))
                        except alerts.Invalid as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/alerts/test":
                        return self.send(200, app.alerts.test())
                    if path == "/api/security":
                        if body.get("internetNeedsPasskey") and not app.passkeys.count():
                            raise ValueError("Add a passkey first.")
                        return self.send(200, app.security.save(body))
                    if path == "/api/passkeys/register/options":
                        return self.send(200, app.passkeys.register_options(self.ceremony()[0]))
                    if path == "/api/passkeys/register/finish":
                        rp, origin = self.ceremony()
                        return self.send(200, {"name": app.passkeys.register_finish(body.get("handle"), body.get("credential") or {}, rp, origin, body.get("name")), "passkeys": app.passkeys.listing()})
                    if path == "/api/signout-others":
                        return self.send(200, {"signedOut": app.auth.sign_out_others(self.token()), "signedIn": app.auth.signed_in()})
                    if path == "/api/passkeys/remove":
                        if app.passkeys.remove(body.get("id")) == 0:
                            app.security.save({"internetNeedsPasskey": False})        # with none left, the internet must not be left with nothing that works
                        return self.send(200, {"passkeys": app.passkeys.listing(), **app.security.cfg()})
                    if path == "/api/alerts":
                        try:
                            return self.send(200, app.alerts.set(body))
                        except alerts.Invalid as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/graphs/wan":
                        return self.send(200, app.wan_ports(str(body.get("connection") or "")))
                    if path == "/api/graphs":
                        try:
                            return self.send(200, {"graphs": app.set_graphs(body.get("graphs"))})
                        except graphs.Invalid as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/history/clear":
                        app.history.clear()
                        return self.send(200, {"cleared": True})
                    if path == "/api/barshow":
                        try:
                            return self.send(200, app.set_barshow(body.get("show")))
                        except ValueError as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/timezone":
                        try:
                            return self.send(200, app.set_timezone(body.get("timezone")))
                        except ValueError as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/display":
                        try:
                            return self.send(200, app.set_display(body))
                        except ValueError as e:
                            return self.send(400, {"error": str(e)})
                    if path == "/api/server":
                        try:
                            out = monconfig.ensure_server(app.paths, body.get("name"), body.get("host"),
                                                          lambda h: probes.ping(h, 2.0)[0], lambda h, p: followups.tcp_open(h, p, 1.0))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/ping":
                        try:
                            out = monconfig.add_ping(app.paths, body.get("name"), body.get("target"), body.get("system") or None)
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/network":
                        try:
                            out = monconfig.add_network(app.paths, body.get("gateway") or None, body.get("dns") or [])
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/confirm":
                        try:
                            out = monconfig.set_confirm(app.paths, str(body.get("id", "")), body.get("failures"), body.get("seconds"))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path in ("/api/expected", "/api/stopwatching", "/api/critical"):
                        try:
                            if path == "/api/critical":
                                ids = body.get("ids") if isinstance(body.get("ids"), list) else [body.get("id")]
                                out = monconfig.set_critical(app.paths, [str(i) for i in ids if i], bool(body.get("critical")))
                            elif path == "/api/expected":
                                out = monconfig.set_expected(app.paths, str(body.get("id", "")), bool(body.get("expected")))
                            else:
                                out = monconfig.remove_node(app.paths, str(body.get("id", "")), bool(body.get("children")))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/unwatch":
                        try:
                            labels = [str(i.get("label", "")) for i in body.get("items", [])] or [str(body.get("label", ""))]
                            out = monconfig.remove_watches(app.paths, str(body.get("connection", "")), labels)
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "Could not remove it: " + "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, out)
                    if path == "/api/check-now":
                        n = app.monitor.check_now(body.get("id"))
                        return self.send(200, {"checking": n})
                    if path == "/api/config/monitoring":
                        try:
                            rev = monconfig.save_monitoring(app.paths, body.get("monitoring"), body.get("revision", -1))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "The configuration has problems; nothing was changed.", "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        return self.send(200, {"revision": rev})
                    if path == "/api/backups":
                        lib = backups.lib()
                        if body.get("kind") not in lib.TARGETS:
                            raise ValueError("Choose a config or full backup.")
                        lib.create(app.paths.root, body["kind"], "manual", app_version=version())
                        return self.send(200, app.backup_list())
                    if path == "/api/backups/delete":
                        lib = backups.lib()
                        os.unlink(lib.path_of(app.paths.root, str(body.get("name", ""))))
                        return self.send(200, app.backup_list())
                    if path == "/api/followups/dismiss":
                        return self.send(200, app.dismiss_followup(str(body.get("id", ""))))
                    if path == "/api/followups/add":
                        return self.send(200, app.add_followup(str(body.get("id", ""))))
                    if path == "/api/app/restart":
                        return self.send(200, app.restart_app())
                    if path == "/api/factory-reset":
                        return self.send(200, app.factory_reset(str(body.get("confirm", ""))))
                    if path == "/api/restore":
                        return self.send(200, app.restore(str(body.get("name", ""))))
                    if path == "/api/config/connection/remove":
                        try:
                            out = monconfig.remove_connection(app.paths, str(body.get("id", "")))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "; ".join(e.errors), "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        app.monitor.check_now()
                        return self.send(200, out)
                    if path == "/api/config/connections":
                        try:
                            rev = monconfig.save_connections(app.paths, body.get("connections"), body.get("revision", -1))
                        except monconfig.Invalid as e:
                            return self.send(400, {"error": "The connections have problems; nothing was changed.", "errors": e.errors})
                        except monconfig.Conflict as e:
                            return self.send(409, {"error": str(e)})
                        app.reload_monitoring()
                        app.monitor.check_now()
                        return self.send(200, {"revision": rev})
                    if path == "/api/check":
                        app.refresh()
                        return self.send(200, app.view())
                    if path == "/api/select":
                        app.select(body.get("kind"), body.get("id"), str(body.get("pin", "latest")))
                        return self.send(200, app.view())
                    if path == "/api/apply":
                        return self.send(200, app.apply(body.get("kind"), body.get("id")))
                    if path == "/api/apply-all":
                        return self.send(200, app.apply_all())
                    if path == "/api/settings":
                        changes = {}
                        if "autoCheck" in body:
                            changes["auto_check"] = body["autoCheck"]
                        if "autoUpdate" in body:
                            changes["auto_update"] = body["autoUpdate"]
                        updates.set_update_cfg(app.paths, **changes)
                        return self.send(200, app.view())
                    if path == "/api/repos/add":
                        rid = updates.add_repo(app.paths, str(body.get("repo", "")), app.releases_url)
                        app.refresh()
                        return self.send(200, app.view())
                    if path == "/api/repos/enable":
                        updates.set_repo_enabled(app.paths, str(body.get("id", "")), body.get("enabled"), app.releases_url)
                        app.refresh()
                        return self.send(200, app.view())
                    if path == "/api/repos/remove":
                        out = app.remove_repo(str(body.get("id", "")), bool(body.get("uninstall")), str(body.get("backup", "none")))
                        return self.send(200, {**out, "view": app.view()})
                    if path == "/api/modules/uninstall":
                        out = app.uninstall(str(body.get("id", "")), str(body.get("backup", "none")))
                        return self.send(200, {**out, "view": app.view()})
                    if path == "/api/repos/adopt":
                        out = app.adopt(str(body.get("module", "")), str(body.get("id", "")))
                        return self.send(200, {**out, "view": app.view()})
                    if path == "/api/channel":
                        updates.set_update_cfg(app.paths, channel=body.get("channel", ""))
                        app.refresh()
                        return self.send(200, app.view())
                except (ValueError, PermissionError) as e:
                    return self.send(400, {"error": str(e)})
                except Exception as e:
                    return self.send(502, {"error": str(e)})
                self.send(404, {"error": "not found"})

        self.apply_start_files()
        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        self.sync_site_nodes()
        self.reload_monitoring()
        self.monitor.start()
        self.graphs.start()
        self.lansampler.start()
        threading.Thread(target=self.map_loop, daemon=True, name="lanmap").start()
        threading.Thread(target=self.flow_loop, daemon=True, name="flowlog").start()
        threading.Thread(target=self.power_loop, daemon=True, name="powerlinks").start()
        self.alerts.start()
        self.peer.start()
        threading.Thread(target=lambda: (self.modules.start_all(), self.first_run_sync()), daemon=True).start()
        threading.Thread(target=self.auto_loop, daemon=True).start()
        threading.Thread(target=self.backup_loop, daemon=True).start()
        try:
            self.httpd.serve_forever()
        finally:
            self.graphs.stop()
            self.lansampler.stop()
            self.alerts.stop()
            self.peer.stop()
            self.monitor.stop()
            self.modules.stop_all()
            if self.wipe:
                self.wipe_settings()
        return self.exit_code or 0
