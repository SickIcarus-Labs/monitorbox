"""A READ-ONLY client for UniFi Protect (the camera system on a UniFi OS console such as a Cloud Key, Dream Machine Pro or UNVR).

It logs in once (the only POST it ever sends, to /api/auth/login) and then only GETs two things: the Protect "bootstrap" (the NVR, every
camera and their state) and a camera's still snapshot. Nothing here can record, reboot, move a camera, change a setting or open a stream.
Use a local account that can only VIEW Protect.

Self-signed certificates are normal on a console, so the certificate is not verified unless the connection sets "verify_tls": true.
The password only ever goes to the address in the connection."""
import json, re, ssl, threading, time
import urllib.error, urllib.request
from urllib.parse import urlsplit

PREFIX = "/proxy/protect/api"
LOGIN_BACKOFF = 60                       # after a refused login, do not try again for this long (a wrong password must not lock the account)
UNREACHABLE_FOR = 10                                      # after the console does not answer, every call fails at once for this long (then one real try)
CACHE_SECONDS = 5                        # checks that run together share one fetch
MAX_SNAPSHOT = 3_000_000                 # bytes; a still image is far smaller
CAMERA_ID = re.compile(r"^[A-Za-z0-9]{6,40}$")


class ProtectError(Exception):
    pass


class Client:
    def __init__(self, base_url, username, password, verify_tls=False, timeout=15):
        if not base_url:
            raise ProtectError("this connection has no 'host' or 'base_url'")
        if not username or not password:
            raise ProtectError("this connection needs a 'username' and 'password' (a local account that can only view Protect)")
        base = base_url if "://" in base_url else "https://" + base_url
        parts = urlsplit(base)
        self.base = f"{parts.scheme}://{parts.netloc}"
        self.username, self.password, self.timeout = username, password, float(timeout)
        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler({}))
        self.lock = threading.Lock()
        self.cookie, self.login_failed, self.cache = None, None, {}
        self.unreachable = None      # (when, message) of the last time the console did not answer

    def _request(self, method, path, body=None, limit=None):
        if self.unreachable and time.time() - self.unreachable[0] < UNREACHABLE_FOR:
            raise ProtectError(self.unreachable[1])       # a console that just did not answer is not asked again by every check queued behind this one: each would wait out its own timeout
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                self.unreachable = None
                return r.status, r.read(limit) if limit else r.read(), r.headers
        except urllib.error.HTTPError as e:
            self.unreachable = None
            return e.code, e.read(2000), e.headers
        except (OSError, ValueError) as e:
            msg = f"cannot reach UniFi Protect at {self.base} ({getattr(e, 'reason', e)})"
            self.unreachable = (time.time(), msg)
            raise ProtectError(msg)

    def _login(self):
        if self.login_failed and time.time() - self.login_failed[0] < LOGIN_BACKOFF:
            raise ProtectError(self.login_failed[1] + " (not retrying for a minute, so the account is not locked out)")
        self.cookie = None
        status, _raw, headers = self._request("POST", "/api/auth/login", {"username": self.username, "password": self.password, "remember": False})
        if status != 200:
            why = {400: "the login was refused", 401: "the username or password was refused", 403: "the login was refused",
                   404: "this is not a UniFi OS console", 429: "the console says too many login attempts"}.get(status, f"the console answered HTTP {status}")
            self.login_failed = (time.time(), f"cannot log in to UniFi Protect: {why}")
            raise ProtectError(self.login_failed[1])
        cookies = [c.split(";", 1)[0] for c in headers.get_all("Set-Cookie") or []]
        if not cookies:
            self.login_failed = (time.time(), "cannot log in to UniFi Protect: the console accepted the login but sent no session")      # backed off like any other failed login
            raise ProtectError(self.login_failed[1])
        self.cookie, self.login_failed = "; ".join(cookies), None

    def _get(self, path, limit=None):
        for attempt in (1, 2):
            if not self.cookie:
                self._login()
            status, raw, headers = self._request("GET", PREFIX + path, limit=limit)
            if status in (401, 403) and attempt == 1:
                self.cookie = None                                  # session expired: log in again, once
                continue
            break
        if status in (401, 403):
            raise ProtectError("UniFi Protect refused this account's access (give it view access to Protect)")
        if status == 404:
            raise ProtectError("this console has no UniFi Protect (or it is not running)")
        if status != 200:
            raise ProtectError(f"UniFi Protect answered HTTP {status}")
        return raw, headers

    def bootstrap(self):
        """The whole Protect picture: {"nvr": {...}, "cameras": [...]}."""
        with self.lock:
            hit = self.cache.get("bootstrap")
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
            raw, _ = self._get("/bootstrap")
            try:
                doc = json.loads(raw)
                if not isinstance(doc, dict) or not isinstance(doc.get("cameras"), list):
                    raise ValueError
            except ValueError:
                raise ProtectError("UniFi Protect sent an answer this module cannot read")
            self.cache["bootstrap"] = (time.time(), doc)
            return doc

    def nvr(self):
        """The recorder on its own ({...}). It carries systemInfo.ustorage, the drives' temperature and health. A GET, like everything here."""
        with self.lock:
            hit = self.cache.get("nvr")
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
            raw, _ = self._get("/nvr")
            try:
                doc = json.loads(raw)
                if not isinstance(doc, dict):
                    raise ValueError
            except ValueError:
                raise ProtectError("UniFi Protect sent an answer this module cannot read")
            self.cache["nvr"] = (time.time(), doc)
            return doc

    def snapshot(self, camera_id):
        """(content type, JPEG bytes) of one camera's current still."""
        if not CAMERA_ID.match(str(camera_id or "")):
            raise ProtectError("that is not a camera id")
        raw, headers = self._get(f"/cameras/{camera_id}/snapshot?ts={int(time.time() * 1000)}", limit=MAX_SNAPSHOT + 1)
        if len(raw) > MAX_SNAPSHOT:
            raise ProtectError("the snapshot is larger than expected")
        ctype = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in ("image/jpeg", "image/png"):
            raise ProtectError("the camera did not return a picture")
        return ctype, raw
