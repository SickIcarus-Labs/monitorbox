"""Sites: more than one MonitorBox, managed from one, like Portainer's environments.

Every site runs a full MonitorBox of its own, so it keeps working and keeps alerting if the others go dark. One box (the
"main" one) can be paired to the others and then shows and manages them: its tabs reach the other box's own screens and settings.
Control only ever goes one way: the main box holds a key for each site it manages; a managed site holds no key to the main box.

The link is a separate "site port" (default 8443), so only that one port has to be forwarded on a router. It speaks TLS with a
pre-shared key (TLS-PSK, built into Python 3.13's ssl module): there are no certificates to make or trust, the key exchange is
ECDHE (forward secrecy), and a visitor without a key gets nothing, not even a page. Failed handshakes are counted per address and
that address is shut out for ten minutes after ten failures in a minute.

Pairing: the box to be managed shows a long one-time code (about 125 bits, valid ten minutes, usable once). The main box connects
with the code as the key and asks for a long-term key (POST /peer/pair); from then on the code is useless. Long-term keys live in
config/sites.json (mode 0600; backups carry it) and are never returned by any API.

What a main box may ask of a managed one: GET /peer/hello (name and version) and /peer/api/<anything> which is passed to the
managed box's own API as if its owner were signed in. Not passed on: signing in/out and first-time setup, anything about sites
(so a main box cannot pair the box it manages to a third one, and control cannot loop back), and the main screen's status stream (it polls instead).
The live-camera setup channel (a server-sent event stream) and its calls are passed, so the main box can start a view on a managed box's cameras.
"""
import urllib.parse, http.client, json, os, re, secrets, socket, ssl, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .store import read_json, write_json

DEFAULT_PORT = 8443
PAIR_TTL = 600
POLL_EVERY = 10.0
MANAGER_QUIET = 90.0      # a managing box polls every 10 s; this long without a word and it is called quiet
MAX_SITES = 8
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
BLOCKED = ("login", "setup", "logout", "sites", "site/", "stream", "ha-callback")     # never passed to a managed box
LOCKOUT_FAILS, LOCKOUT_WINDOW, LOCKOUT_FOR = 10, 60.0, 600.0
RELAY_HEADERS = ("Content-Type", "Content-Disposition", "Cache-Control")
SLUG = re.compile(r"[^a-z0-9]+")


class Invalid(ValueError):
    pass


class PeerError(Exception):
    """A plain-language reason a site could not be reached."""

    def __init__(self, msg, kind="unknown"):
        super().__init__(msg)
        self.kind = kind                    # "unknown" (could not reach it) or "refused" (it does not accept our key)


def _ctx_client(identity, key):
    c = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    c.check_hostname, c.verify_mode = False, ssl.CERT_NONE         # no certificates: the pre-shared key is what proves who is who
    c.maximum_version = ssl.TLSVersion.TLSv1_2
    c.set_ciphers("PSK")
    c.set_psk_client_callback(lambda hint: (identity, key))
    return c


def parse_address(raw):
    """host or host:port (a scheme or path on the end is dropped). Returns (host, port)."""
    s = str(raw or "").strip()
    if "://" not in s:
        s = "//" + s
    u = urlparse(s)
    try:
        port = u.port or DEFAULT_PORT
    except ValueError:
        raise Invalid("That port is not a number.")
    if not u.hostname or any(ch.isspace() for ch in s) or not 1 <= port <= 65535:
        raise Invalid("Enter the other site's address, like tidewater.example.com:8443 or 203.0.113.7:8443")
    return u.hostname, port


def norm_code(raw):
    return re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())


def _plain(e, who):
    if isinstance(e, ssl.SSLError):
        return PeerError(f"{who} did not accept this MonitorBox's key. It may have been removed there; pair the sites again.", "refused")
    if isinstance(e, (socket.timeout, TimeoutError)):
        return PeerError(f"{who} is not answering from here (no reply in time)")
    if isinstance(e, socket.gaierror):
        return PeerError(f"The name for {who} could not be found")
    if isinstance(e, ConnectionRefusedError):
        return PeerError(f"Nothing is listening on {who}'s site port. Is the site port switched on there, and the port forwarded?")
    if isinstance(e, (ConnectionError, OSError, http.client.HTTPException)):
        return PeerError(f"{who} is not answering from here ({type(e).__name__})")
    return PeerError(f"{who} could not be reached ({type(e).__name__})")


def open_link(address, identity, key, method, path, headers=None, body=b"", body_src=None, body_len=0, timeout=15, who="That site"):
    """One request over TLS-PSK. Returns (connection, response); the caller reads the response and closes the connection."""
    host, port = parse_address(address)
    conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=_ctx_client(identity, key))
    try:
        conn.putrequest(method, path, skip_accept_encoding=True)
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        n = body_len if body_src is not None else len(body)
        if method == "POST" or n:
            conn.putheader("Content-Length", str(n))
        conn.endheaders()
        if body_src is not None:
            left = n
            while left > 0:
                chunk = body_src.read(min(1 << 20, left))
                if not chunk:
                    break
                conn.send(chunk)
                left -= len(chunk)
        elif body:
            conn.send(body)
        return conn, conn.getresponse()
    except (PeerError, Invalid):
        conn.close()
        raise
    except Exception as e:
        conn.close()
        raise _plain(e, who)


def call_json(address, identity, key, method, path, obj=None, timeout=8, who="That site", headers=None):
    body = json.dumps(obj).encode() if obj is not None else b""
    conn, resp = open_link(address, identity, key, method, path, {"Content-Type": "application/json", **(headers or {})}, body, timeout=timeout, who=who)
    try:
        raw = resp.read(1 << 22)
        try:
            return resp.status, json.loads(raw) if raw else None
        except ValueError:
            return resp.status, None
    except Exception as e:
        raise _plain(e, who)
    finally:
        conn.close()


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, owner):
        self.owner = owner
        super().__init__(addr, handler)

    def process_request_thread(self, request, client_address):
        try:
            tls = self.owner._handshake(request, client_address)
        except Exception:
            self.shutdown_request(request)
            return
        try:
            self.finish_request(tls, client_address)
        except Exception:
            pass
        finally:
            self.shutdown_request(tls)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        owner = self.server.owner
        ident = getattr(self.connection, "_mb_identity", "") or ""
        n = int(self.headers.get("Content-Length") or 0)
        path = self.path
        try:
            if path == "/peer/hello" and method == "GET":
                return self._json(200, owner.hello())
            if path == "/peer/pair" and method == "POST" and ident == "pair":
                try:
                    body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                except ValueError:
                    return self._json(400, {"error": "bad json"})
                out = owner.accept_pair(body)
                return self._json(200, out) if out else self._json(403, {"error": "pairing is not open"})
            if ident.startswith("m:") and owner.is_manager(ident[2:]):
                owner.seen[ident[2:]] = owner.clock()
                owner.manager_named(ident[2:], self.headers.get("X-MB-Name"))
                if path == "/peer/bye" and method == "POST":
                    owner.remove_manager(ident[2:])
                    return self._json(200, {"ok": True})
                if path.startswith("/peer/api/"):
                    return owner.forward(self, method, path[len("/peer/api/"):], n)
                if path.startswith("/peer/udp?s=") and method == "GET":
                    return owner.udp_in(self, path[len("/peer/udp?s="):])
            return self._json(404, {"error": "not found"})
        except (BrokenPipeError, ConnectionError, ssl.SSLError):
            self.close_connection = True


class Peer:
    def __init__(self, path, app_port, session_cookie, version, hostname=socket.gethostname, clock=time.time):
        self.path, self.app_port, self.session_cookie, self.version = path, app_port, session_cookie, version
        self.hostname, self.clock = hostname, clock
        self.lock = threading.RLock()
        self.pairing = None                         # {"code","expires"} while a pairing window is open
        self.links = {}                             # site id -> last known link state
        self.srv, self.srv_thread = None, None
        self._tl = threading.local()
        self._fails = {}
        self.stopped = False
        self.poll_thread = None
        self.relay_lookup = None                    # set by the app: live view id -> its media pipe
        self.on_change = None                       # set by the app: called (off to the side) when a pairing is made or ended
        self.seen = {}                              # managing box id -> when it last spoke to this box

    # -- stored settings -----------------------------------------------------
    def _cfg(self):
        c = read_json(self.path, {}) or {}
        ls = c.get("listen") if isinstance(c.get("listen"), dict) else {}
        port = ls.get("port")
        return {"name": str(c.get("name") or "")[:60],
                "listen": {"enabled": bool(ls.get("enabled")), "port": port if isinstance(port, int) and 1024 <= port <= 65535 else DEFAULT_PORT},
                "managers": [m for m in (c.get("managers") or []) if isinstance(m, dict) and m.get("id") and m.get("key")],
                "sites": [s for s in (c.get("sites") or []) if isinstance(s, dict) and s.get("id") and s.get("key") and s.get("address")]}

    def _write(self, c):
        write_json(self.path, {"name": c["name"], "listen": c["listen"], "managers": c["managers"], "sites": c["sites"]})

    def name(self):
        return self._cfg()["name"] or str(self.hostname() or "MonitorBox")

    def get(self):
        """For the Sites screen. Keys never leave this file; the one-time code is shown only while a pairing window is open."""
        c = self._cfg()
        with self.lock:
            p = self.pairing if self.pairing and self.pairing["expires"] > self.clock() else None
            links = dict(self.links)
        return {"name": c["name"], "nameDefault": str(self.hostname() or "MonitorBox"), "listen": c["listen"],
                "listening": bool(self.srv),
                "pairing": ({"code": p["code"], "expiresIn": int(p["expires"] - self.clock())} if p else None),
                "managers": [{"id": m["id"], "name": m.get("name", ""), "since": m.get("since")} for m in c["managers"]],
                "sites": [{"id": s["id"], "name": s.get("name", ""), "address": s["address"], "since": s.get("since"), "link": links.get(s["id"])} for s in c["sites"]]}

    def set_name(self, name):
        c = self._cfg()
        c["name"] = str(name or "").strip()[:60]
        self._write(c)

    # -- the site port (this box can be managed, or watched) -------------------
    def set_listen(self, enabled, port=None):
        c = self._cfg()
        if port is not None:
            if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
                raise Invalid("The site port must be a number from 1024 to 65535.")
            c["listen"]["port"] = port
        c["listen"]["enabled"] = bool(enabled)
        self._write(c)
        self._apply_listen(c)
        if not enabled:
            with self.lock:
                self.pairing = None
        return self.get()

    def _apply_listen(self, c=None):
        c = c or self._cfg()
        with self.lock:
            want = c["listen"]
            if self.srv and (not want["enabled"] or self.srv.server_address[1] != want["port"]):
                self.srv.shutdown(); self.srv.server_close(); self.srv = None
            if want["enabled"] and not self.srv:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.maximum_version = ssl.TLSVersion.TLSv1_2
                ctx.set_ciphers("PSK")
                ctx.set_psk_server_callback(self._psk, "monitorbox")
                self._ctx = ctx
                try:
                    srv = _Server(("0.0.0.0", want["port"]), _Handler, self)
                except OSError:
                    raise Invalid(f"Port {want['port']} is already in use on this box. Pick another site port.")
                self.srv = srv
                threading.Thread(target=srv.serve_forever, daemon=True, name="site-port").start()

    def _psk(self, identity):
        self._tl.identity = identity
        if identity == "pair":
            with self.lock:
                p = self.pairing
                if p and p["expires"] > self.clock():
                    return norm_code(p["code"]).encode()
            return b""
        if identity and identity.startswith("m:"):
            for m in self._cfg()["managers"]:
                if m["id"] == identity[2:]:
                    return bytes.fromhex(m["key"])
        return b""

    def _handshake(self, sock, addr):
        ip, now = addr[0], self.clock()
        with self.lock:
            q = self._fails.setdefault(ip, deque())
            while q and now - q[0] > LOCKOUT_FOR:
                q.popleft()
            recent = [t for t in q if now - t <= LOCKOUT_WINDOW]
            if len(recent) >= LOCKOUT_FAILS or (len(q) >= LOCKOUT_FAILS and now - q[-1] <= LOCKOUT_FOR and len(recent) >= LOCKOUT_FAILS):
                raise OSError("shut out")
        sock.settimeout(8)
        self._tl.identity = None
        try:
            tls = self._ctx.wrap_socket(sock, server_side=True)
        except Exception:
            with self.lock:
                self._fails.setdefault(ip, deque()).append(now)
            raise
        tls._mb_identity = self._tl.identity
        tls.settimeout(120)
        return tls

    # -- pairing: this box agrees to be managed ----------------------------------
    def need_name(self, why):
        if not self._cfg()["name"]:
            raise Invalid(f"Give this site a name first (above), like Bay Harbor or Tidewater. {why}")

    def start_pairing(self):
        self.need_name("The main MonitorBox shows it on its tab.")
        if not self._cfg()["listen"]["enabled"]:
            self.set_listen(True)
        else:
            self._apply_listen()
        raw = "".join(secrets.choice(CODE_CHARS) for _ in range(25))
        code = "-".join(raw[i:i + 5] for i in range(0, 25, 5))
        with self.lock:
            self.pairing = {"code": code, "expires": self.clock() + PAIR_TTL}
        return self.get()

    def stop_pairing(self):
        with self.lock:
            self.pairing = None

    def accept_pair(self, body):
        """A main box connected with the one-time code and asks for a long-term key."""
        with self.lock:
            p, self.pairing = self.pairing, None                 # one use, whatever happens next
        if not p or p["expires"] <= self.clock():
            return None
        c = self._cfg()
        mid = secrets.token_hex(6)
        key = secrets.token_hex(32)
        name = str((body or {}).get("name") or "A MonitorBox")[:60]
        c["managers"].append({"id": mid, "name": name, "key": key, "since": int(self.clock())})
        self._write(c)
        self._changed()
        return {"id": mid, "key": key, "name": self.name(), "version": self.version()}

    def _changed(self):
        cb = self.on_change
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def link_check(self, sid):
        """(ok, detail, ms) for the check on a managed site's link. Never False: a silent site is Unknown, not down."""
        s = next((x for x in self._cfg()["sites"] if x["id"] == sid), None)
        if not s:
            return None, "this site is no longer paired", None
        who = s.get("name") or "That site"
        with self.lock:
            link = dict(self.links.get(sid) or {})
        st = link.get("state")
        if st == "linked":
            return True, f"answering from here{' · version ' + str(link['version']) if link.get('version') else ''}", None
        if st == "refused":
            return None, f"{who} no longer accepts this box's key. Pair the sites again.", None
        if st == "unknown":
            return None, link.get("error") or f"{who} is not answering from here", None
        return None, f"{who} has not been checked yet", None

    def manager_check(self, mid):
        """The same from the managed side: has the box that manages this one been in touch lately? Unknown when not, never down."""
        m = next((x for x in self._cfg()["managers"] if x["id"] == mid), None)
        if not m:
            return None, "this box no longer manages this one", None
        who = m.get("name") or "The managing box"
        t = self.seen.get(mid)
        if t is None:
            return None, f"{who} has not been in touch since this box started", None
        ago = self.clock() - t
        if ago <= MANAGER_QUIET:
            return True, f"in touch ({int(ago)} s ago)", None
        return None, f"{who} has not been in touch for {int(ago // 60)} min {int(ago % 60)} s", None

    def is_manager(self, mid):
        return any(m["id"] == mid for m in self._cfg()["managers"])

    def manager_named(self, mid, quoted):
        """The managing box says what it is called now (it may have been named after pairing). Keep that, so 'Managed by <name>' stays right."""
        try:
            name = urllib.parse.unquote(quoted or "").strip()[:60]
        except Exception:
            return
        if not name:
            return
        c = self._cfg()
        m = next((x for x in c["managers"] if x["id"] == mid), None)
        if m and m.get("name") != name:
            m["name"] = name
            self._write(c)
            self._changed()

    def remove_manager(self, mid):
        c = self._cfg()
        c["managers"] = [m for m in c["managers"] if m["id"] != mid]
        self._write(c)
        self.seen.pop(mid, None)
        self._changed()
        return self.get()

    def hello(self):
        return {"app": "monitorbox", "name": self.name(), "version": self.version()}

    def forward(self, h, method, rest, n):
        """Pass a managing box's request to this box's own API, as if its owner were signed in. Streams both ways."""
        first = rest.split("?", 1)[0]
        if any(first == b.rstrip("/") or first.startswith(b) for b in BLOCKED):
            return h._json(403, {"error": "that is not available from another site"})
        conn = http.client.HTTPConnection("127.0.0.1", self.app_port, timeout=120)
        try:
            conn.putrequest(method, "/api/" + rest, skip_accept_encoding=True)
            conn.putheader("Cookie", "mb=" + self.session_cookie())
            conn.putheader("X-MB", "1")
            if h.headers.get("Content-Type"):
                conn.putheader("Content-Type", h.headers["Content-Type"])
            if method == "POST" or n:
                conn.putheader("Content-Length", str(n))
            conn.endheaders()
            left = n
            while left > 0:
                chunk = h.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                conn.send(chunk)
                left -= len(chunk)
            resp = conn.getresponse()
            relay(resp, h, conn)
        except (BrokenPipeError, ConnectionError, ssl.SSLError):
            raise
        except Exception as e:
            h._json(502, {"error": "this box's own API did not answer (" + type(e).__name__ + ")"})
        finally:
            conn.close()

    def udp_in(self, h, sid):
        """A managing box joins a live view's media relay: after the upgrade the connection carries framed UDP packets both ways."""
        pipe = self.relay_lookup(sid) if self.relay_lookup else None
        if pipe is None:
            return h._json(404, {"error": "no such live view"})
        h.wfile.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: mb-udp\r\nConnection: Upgrade\r\n\r\n")
        h.wfile.flush()
        h.close_connection = True
        pipe.serve(h.connection, speak_first=False)

    # -- sites this box manages --------------------------------------------------------
    def add_site(self, address, code, name=None):
        self.need_name("The other MonitorBox shows it as who manages it.")
        host, port = parse_address(address)
        code = norm_code(code)
        if len(code) != 25:
            raise Invalid("The pairing code has 25 letters and numbers (shown in groups of five). Copy it from the other MonitorBox.")
        c = self._cfg()
        if len(c["sites"]) >= MAX_SITES:
            raise Invalid(f"At most {MAX_SITES} sites.")
        addr = f"{host}:{port}"
        if any(s["address"] == addr for s in c["sites"]):
            raise Invalid("That site is already added.")
        try:
            st, j = call_json(addr, "pair", code.encode(), "POST", "/peer/pair", {"name": self.name()}, who="That site")
        except PeerError as e:
            if e.kind == "refused":
                raise Invalid("That site did not accept the code. It may have expired (they last ten minutes) or been typed wrong. Press 'Let a main MonitorBox manage this one' there again.")
            raise Invalid(str(e))
        if st != 200 or not isinstance(j, dict) or not j.get("key") or not j.get("id"):
            raise Invalid("That site did not complete the pairing. Press the pairing button there again.")
        nm = str(name or j.get("name") or host).strip()[:60]
        base, sid, k = SLUG.sub("-", nm.lower()).strip("-") or "site", None, 1
        ids = {s["id"] for s in c["sites"]}
        sid = base
        while sid in ids:
            k += 1
            sid = f"{base}-{k}"
        c["sites"].append({"id": sid, "name": nm, "address": addr, "mid": j["id"], "key": j["key"], "since": int(self.clock())})
        self._write(c)
        self._changed()
        self.poll_once()
        return self.get()

    def _site(self, sid):
        for s in self._cfg()["sites"]:
            if s["id"] == sid:
                return s
        raise PeerError("There is no such site.")

    def remove_site(self, sid):
        s = self._site(sid)
        try:                                              # tell the other box so it forgets us at once; if it cannot be reached we still forget it
            call_json(s["address"], "m:" + s["mid"], bytes.fromhex(s["key"]), "POST", "/peer/bye", {}, timeout=4)
        except Exception:
            pass
        c = self._cfg()
        c["sites"] = [x for x in c["sites"] if x["id"] != sid]
        self._write(c)
        self._changed()
        with self.lock:
            self.links.pop(sid, None)
        return self.get()

    def rename_site(self, sid, name):
        name = str(name or "").strip()[:60]
        if not name:
            raise Invalid("Give the site a name.")
        c = self._cfg()
        for s in c["sites"]:
            if s["id"] == sid:
                s["name"] = name
        self._write(c)
        self._changed()
        return self.get()

    def open_udp(self, sid, remote_sid, pipe):
        """Join the live view `remote_sid` on a managed site: the pipe then carries its media. Runs until either side closes."""
        s = self._site(sid)
        conn, resp = open_link(s["address"], "m:" + s["mid"], bytes.fromhex(s["key"]), "GET", "/peer/udp?s=" + remote_sid,
                               {"Connection": "Upgrade", "Upgrade": "mb-udp"}, timeout=10, who=s.get("name") or "That site")
        if resp.status != 101:
            conn.close()
            raise PeerError("that site would not start the video relay (it may need updating)", "unknown")
        sock = conn.sock
        pipe.serve(sock, speak_first=True)

    def open(self, sid, method, path, headers=None, body_src=None, body_len=0, timeout=60):
        """A request to a managed site's own API. Returns (connection, response) or raises PeerError."""
        s = self._site(sid)
        try:
            return open_link(s["address"], "m:" + s["mid"], bytes.fromhex(s["key"]), method, path, headers, body_src=body_src, body_len=body_len,
                             timeout=timeout, who=s.get("name") or "That site")
        except PeerError as e:
            self._note(sid, e.kind, str(e))
            raise

    # -- link state --------------------------------------------------------------------
    def _note(self, sid, state, error="", **extra):
        with self.lock:
            old = self.links.get(sid) or {}
            self.links[sid] = {"state": state, "error": error, "lastSeen": self.clock() if state == "linked" else old.get("lastSeen"),
                               "version": extra.get("version", old.get("version")), "banner": extra.get("banner", old.get("banner")),
                               "attention": extra.get("attention", old.get("attention"))}

    def poll_once(self):
        for s in self._cfg()["sites"]:
            who = s.get("name") or "That site"
            try:
                key = bytes.fromhex(s["key"])
                st, hello = call_json(s["address"], "m:" + s["mid"], key, "GET", "/peer/hello", timeout=5, who=who,
                                       headers={"X-MB-Name": urllib.parse.quote(self.name())})
                if st != 200 or not isinstance(hello, dict):
                    raise PeerError(f"{who} answered, but not like a MonitorBox")
                st, snap = call_json(s["address"], "m:" + s["mid"], key, "GET", "/peer/api/status", timeout=8, who=who,
                                       headers={"X-MB-Name": urllib.parse.quote(self.name())})
                snap = snap if st == 200 and isinstance(snap, dict) else {}
                self._note(s["id"], "linked", "", version=hello.get("version"), banner=snap.get("banner"), attention=len(snap.get("attention") or []))
            except PeerError as e:
                self._note(s["id"], e.kind, str(e))
            except Exception as e:
                self._note(s["id"], "unknown", f"{s.get('name') or 'That site'} could not be reached ({type(e).__name__})")

    def start(self):
        try:
            self._apply_listen()
        except Invalid:
            pass                                          # shown on the Sites screen as "not listening"; the owner can pick another port

        def loop():
            while not self.stopped:
                try:
                    self.poll_once()
                except Exception:
                    pass
                for _ in range(int(POLL_EVERY * 2)):
                    if self.stopped:
                        return
                    time.sleep(0.5)
        self.poll_thread = threading.Thread(target=loop, daemon=True, name="site-links")
        self.poll_thread.start()

    def stop(self):
        self.stopped = True
        with self.lock:
            if self.srv:
                self.srv.shutdown(); self.srv.server_close(); self.srv = None


def client_gone(h):
    """True when whoever asked has gone away. A request that sends nothing after its headers makes 'readable' mean 'closed'."""
    import select
    sock = h.connection
    try:
        if select.select([sock], [], [], 0)[0]:
            data = sock.recv(1) if isinstance(sock, ssl.SSLSocket) else sock.recv(1, socket.MSG_PEEK)
            return data == b""
    except (OSError, ValueError):
        return True
    return False


def relay(resp, h, conn=None, line_filter=None):
    """Copy an HTTP response to a handler's client (status, a few headers, body in pieces). A body of unknown length is an event
    stream: it is handed on as it arrives, and the copy ends within a second of the client going away."""
    h.send_response(resp.status)
    for k in RELAY_HEADERS:
        v = resp.getheader(k)
        if v:
            h.send_header(k, v)
    n = resp.getheader("Content-Length")
    stream = n is None and not resp.chunked
    if n is not None:
        h.send_header("Content-Length", n)
    else:
        h.send_header("Connection", "close")
        h.close_connection = True
    h.end_headers()
    if stream:
        try:
            resp.fp.raw._sock.settimeout(1)               # http.client hands the socket to a close-delimited response, so reach it there
        except AttributeError:
            stream = False
    held = b""
    read = getattr(resp, "read1", resp.read)               # read1: hand on what has arrived, do not wait for a full block
    while True:
        try:
            chunk = read(1 << 16)
        except (socket.timeout, TimeoutError):
            if stream and client_gone(h):
                break
            if stream:
                try:
                    resp.fp.raw._timeout_occurred = False      # python's socket reader refuses every read after one timeout unless told it is fine
                except AttributeError:
                    pass
                continue
            raise
        if not chunk:
            break
        if line_filter is not None:                          # an event stream the caller wants to change line by line
            held += chunk
            *whole, held = held.split(b"\n")
            for ln in whole:
                h.wfile.write(line_filter(ln) + b"\n")
        else:
            h.wfile.write(chunk)
        if stream:
            h.wfile.flush()
    if held and line_filter is not None:
        h.wfile.write(line_filter(held))
