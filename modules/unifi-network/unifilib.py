"""A READ-ONLY client for a UniFi controller (UniFi OS gateway such as a Dream Machine/Cloud Gateway, or a
classic controller). It logs in once (the only POST it ever sends) and then only GETs three read endpoints:
the device list, the health summary, the network settings (to list VPN tunnels) and the VPN connection status. Nothing here can change the network.

Self-signed certificates are normal on a controller, so the certificate is not verified unless the connection
sets "verify_tls": true. The password only ever goes to the address in the connection."""
import json, re, ssl, threading, time
import urllib.error, urllib.request
from urllib.parse import urlencode, urlsplit

READ_ONLY_PATHS = ("stat/device", "stat/health", "rest/networkconf", "v2/vpn/connections", "stat/sta")   # the only things this module may fetch
# The flows look (Client.look) may also do exactly these, and nothing else ({site} is the connection's site name).
# The only POST is a search of the flow list with a fixed small body: it creates and changes nothing, but it is the only request besides the login that is not a GET.
LOOK_ALLOWED = (("GET", "v2/api/site/{site}/traffic"), ("GET", "v2/api/site/{site}/traffic-flows"), ("POST", "v2/api/site/{site}/traffic-flows"),
                ("GET", "v2/api/site/{site}/traffic/applications"), ("GET", "v2/api/site/{site}/traffic/categories"))
LOGIN_BACKOFF = 60                                       # after a refused login, do not try again for this long
UNREACHABLE_FOR = 10                                      # after the console does not answer, every call fails at once for this long (then one real try)
CACHE_SECONDS = 5                                        # checks that run together share one fetch


class UnifiError(Exception):
    pass


class Client:
    def __init__(self, base_url, username, password, site="default", verify_tls=False, timeout=8):
        if not base_url:
            raise UnifiError("this connection has no 'host' or 'base_url'")
        if not username or not password:
            raise UnifiError("this connection needs a 'username' and 'password' (a read-only local account is best)")
        base = base_url if "://" in base_url else "https://" + base_url
        parts = urlsplit(base)
        self.base = f"{parts.scheme}://{parts.netloc}"
        self.username, self.password, self.site, self.timeout = username, password, site or "default", float(timeout)
        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler({}))
        self.lock = threading.Lock()
        self.cookie, self.prefix, self.login_failed, self.csrf = None, None, None, None     # prefix: "/proxy/network" on UniFi OS
        self.cache = {}
        self.unreachable = None      # (when, message) of the last time the controller did not answer

    def _request(self, method, path, body=None):
        if self.unreachable and time.time() - self.unreachable[0] < UNREACHABLE_FOR:
            raise UnifiError(self.unreachable[1])       # a console that just did not answer is not asked again by every check queued behind this one: each would wait out its own timeout
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        if self.csrf and method != "GET":
            req.add_header("X-Csrf-Token", self.csrf)       # UniFi OS answers 403 to a POST (even a read-only search) without the token it gave at login
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                self.unreachable = None
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            self.unreachable = None
            return e.code, e.read(), e.headers
        except (OSError, ValueError) as e:
            msg = f"cannot reach the UniFi controller at {self.base} ({getattr(e, 'reason', e)})"
            self.unreachable = (time.time(), msg)
            raise UnifiError(msg)

    def _login(self):
        if self.login_failed and time.time() - self.login_failed[0] < LOGIN_BACKOFF:
            raise UnifiError(self.login_failed[1] + " (not retrying for a minute, so the account is not locked out)")
        creds = {"username": self.username, "password": self.password}
        self.cookie = self.csrf = None
        status, raw, headers = self._request("POST", "/api/auth/login", dict(creds, remember=False))
        prefix = "/proxy/network"
        if status == 404:                                    # a classic controller
            status, raw, headers = self._request("POST", "/api/login", creds)
            prefix = ""
        if status != 200:
            why = {400: "the login was refused", 401: "the username or password was refused", 403: "the login was refused",
                   429: "the controller says too many login attempts"}.get(status, f"the controller answered HTTP {status}")
            self.login_failed = (time.time(), f"cannot log in to UniFi: {why}")
            raise UnifiError(self.login_failed[1])
        cookies = [c.split(";", 1)[0] for c in headers.get_all("Set-Cookie") or []]
        if not cookies:
            raise UnifiError("the UniFi controller accepted the login but sent no session")
        self.cookie, self.prefix, self.login_failed = "; ".join(cookies), prefix, None
        self.csrf = headers.get("X-Csrf-Token")

    def get(self, what):
        """what is one of READ_ONLY_PATHS. Returns the controller's 'data' list."""
        if what not in READ_ONLY_PATHS:
            raise UnifiError(f"refusing to fetch '{what}' (this module is read-only)")
        with self.lock:
            hit = self.cache.get(what)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
            for attempt in (1, 2):
                if not self.cookie:
                    self._login()
                if what == "v2/vpn/connections":                 # newer UniFi OS only; same read-only GET
                    if self.prefix != "/proxy/network":
                        raise UnifiError("this controller does not report VPN tunnel status")
                    url = f"{self.prefix}/v2/api/site/{self.site}/vpn/connections"
                else:
                    url = f"{self.prefix}/api/s/{self.site}/{what}"
                status, raw, _ = self._request("GET", url)
                if status in (401, 403) and attempt == 1:
                    self.cookie = None                       # session expired: log in again, once
                    continue
                break
            if status in (401, 403):
                raise UnifiError("the UniFi controller refused this account's access to the network data")
            if status == 404 and what == "v2/vpn/connections":
                raise UnifiError("this controller does not report VPN tunnel status")
            if status == 404:
                raise UnifiError(f"the controller has no site called '{self.site}' (or this is not a UniFi controller)")
            if status != 200:
                raise UnifiError(f"the UniFi controller answered HTTP {status}")
            try:
                doc = json.loads(raw)
                data = doc["connections"] if what == "v2/vpn/connections" else doc["data"]
            except (ValueError, KeyError, TypeError):
                raise UnifiError("the UniFi controller sent an answer this module cannot read")
            if (doc.get("meta") or {}).get("rc") not in (None, "ok"):
                raise UnifiError(f"the UniFi controller said: {(doc.get('meta') or {}).get('msg', 'error')}")
            self.cache[what] = (time.time(), data)
            return data

    def usage(self, seconds):
        """Per-client internet usage over the last `seconds` (GET v2/api/site/<site>/traffic: bytes up and down per client and application, counted at the gateway).
        A read like the others, with its own method because it takes a time window."""
        seconds = max(60, min(int(seconds), 3600))
        with self.lock:
            hit = self.cache.get(("usage", seconds))
            if hit and time.time() - hit[0] < CACHE_SECONDS * 2:
                return hit[1]
            now = int(time.time() * 1000)
            query = urlencode({"start": now - seconds * 1000, "end": now, "includeTrafficUsage": "true", "includeUnidentified": "true"})
            for attempt in (1, 2):
                if not self.cookie:
                    self._login()
                if self.prefix != "/proxy/network":
                    raise UnifiError("this controller does not report per-client internet usage")
                status, raw, _ = self._request("GET", f"{self.prefix}/v2/api/site/{self.site}/traffic?{query}")
                if status in (401, 403) and attempt == 1:
                    self.cookie = None
                    continue
                break
            if status in (401, 403):
                raise UnifiError("the UniFi controller refused this account's access to the traffic data")
            if status != 200:
                raise UnifiError(f"this controller does not report per-client internet usage (HTTP {status})")
            try:
                doc = json.loads(raw)
            except ValueError:
                raise UnifiError("the UniFi controller sent an answer this module cannot read")
            self.cache[("usage", seconds)] = (time.time(), doc)
            return doc

    FLOW_PAGE, FLOW_PAGES = 200, 10          # up to 2000 of the newest flows per question

    def flows(self, seconds):
        """The gateway's flow log for the last `seconds` (the search behind Insights, Flows: POST v2/api/site/<site>/traffic-flows, a read-only search; UniFi OS wants the
        login's CSRF token on it). Newest first, a page at a time. Returns the raw flow records; unifichecks.flow_summary boils them down."""
        seconds = max(60, min(int(seconds), 3600))
        with self.lock:
            hit = self.cache.get(("flows", seconds))
            if hit and time.time() - hit[0] < CACHE_SECONDS * 2:
                return hit[1]
            if ("POST", "v2/api/site/{site}/traffic-flows") not in LOOK_ALLOWED:
                raise UnifiError("refusing the flow search (this module is read-only)")
            now, rows, size, page = int(time.time() * 1000), [], self.FLOW_PAGE, 0
            while page < self.FLOW_PAGES:
                body = {"timestampFrom": now - seconds * 1000, "timestampTo": now, "pageNumber": page, "pageSize": size}
                for attempt in (1, 2):
                    if not self.cookie:
                        self._login()
                    if self.prefix != "/proxy/network":
                        raise UnifiError("this controller does not keep a flow log (the Flows page needs UniFi OS)")
                    status, raw, _ = self._request("POST", f"{self.prefix}/v2/api/site/{self.site}/traffic-flows", body)
                    if status == 401 and attempt == 1:
                        self.cookie = None                      # session expired: log in again, once
                        continue
                    break
                if status == 400 and size > 50:
                    size, rows, page = 50, [], 0                # this controller wants smaller pages: start again
                    continue
                if status in (401, 403):
                    raise UnifiError("the UniFi controller refused this account's access to the flow log")
                if status != 200:
                    raise UnifiError(f"this controller does not report flows (HTTP {status})")
                try:
                    doc = json.loads(raw)
                    data = doc["data"]
                except (ValueError, KeyError, TypeError):
                    raise UnifiError("the UniFi controller sent a flow answer this module cannot read")
                rows += [r for r in data if isinstance(r, dict)]
                page += 1
                if not doc.get("has_next") or not data:
                    break
            self.cache[("flows", seconds)] = (time.time(), rows)
            return rows

    def look(self):
        """For the flows look report only. UniFi does not publish the API behind Insights, Flows, so this asks the few read-only questions it may be built on and
        reports each answer's status and SHAPE (field names, types, counts and a couple of examples; see `shape`). Nothing is kept and nothing is changed."""
        now, hour = int(time.time() * 1000), 3600 * 1000
        window = {"start": now - hour, "end": now}
        plan = [("GET", "v2/api/site/{site}/traffic", dict(window, includeTrafficUsage="true", includeUnidentified="true"), None),
                ("GET", "v2/api/site/{site}/traffic-flows", None, None),
                ("POST", "v2/api/site/{site}/traffic-flows", None, {"timestampFrom": now - hour, "timestampTo": now, "pageNumber": 0, "pageSize": 5}),
                ("POST", "v2/api/site/{site}/traffic-flows", None, {}),
                ("GET", "v2/api/site/{site}/traffic/applications", None, None),
                ("GET", "v2/api/site/{site}/traffic/applications", window, None),
                ("GET", "v2/api/site/{site}/traffic/categories", None, None),
                ("GET", "v2/api/site/{site}/traffic/categories", window, None)]
        out = []
        with self.lock:
            for method, tpl, query, body in plan:
                if (method, tpl) not in LOOK_ALLOWED:
                    raise UnifiError(f"refusing {method} {tpl} (this module is read-only)")
                for attempt in (1, 2):
                    if not self.cookie:
                        self._login()
                    if self.prefix != "/proxy/network":
                        raise UnifiError("this is a classic controller; the Flows page needs UniFi OS")
                    path = f"{self.prefix}/{tpl.format(site=self.site)}" + ("?" + urlencode(query) if query else "")
                    status, raw, _ = self._request(method, path, body)
                    if status in (401, 403) and attempt == 1 and "traffic-flows" not in tpl:
                        self.cookie = None                  # the session may have expired; the flow search answers 403 for another reason
                        continue
                    break
                row = {"request": f"{method} {tpl.format(site=self.site)}", "status": status}
                if query:
                    row["query"] = sorted(query)
                if body is not None:
                    row["sent"] = sorted(body)
                try:
                    row["answer"] = shape(json.loads(raw))
                except ValueError:
                    row["text"] = mask(raw[:300].decode("utf-8", "replace"))      # an error message: it says what the controller wanted, so it is kept whole
                out.append(row)
        return out


_MAC, _IP4 = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", re.I), re.compile(r"^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$")


def mask(text):
    """Free text with any MAC address shortened and any public IPv4 address hidden."""
    text = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", lambda m: scrub(m.group(0)), text)
    return re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", lambda m: scrub(m.group(0)), text)


def scrub(v):
    """A string from the controller, made safe to share: MAC addresses are shortened to their last three bytes, public addresses are hidden (private ones stay, they are
    the owner's own LAN), long text is replaced by its length."""
    if _MAC.match(v):
        return "..:" + v[-8:]
    m = _IP4.match(v)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return v if a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) else "<public address>"
    return v if len(v) <= 40 else f"<text of {len(v)} characters>"


def shape(v, depth=0):
    """What an answer looks like, not what it says: objects keep their field names, lists show their size and the first two entries, strings go through scrub."""
    if depth > 6:
        return "<deeper>"
    if isinstance(v, dict):
        return {scrub(str(k)): shape(x, depth + 1) for k, x in list(v.items())[:40]}
    if isinstance(v, list):
        return {"count": len(v), "first": [shape(x, depth + 1) for x in v[:2]]}
    return scrub(v) if isinstance(v, str) else v
