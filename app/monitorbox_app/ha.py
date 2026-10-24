"""Home Assistant, signed in as its own user: list the phones and tablets that have the Home Assistant app, and send them notifications.

MonitorBox only ever calls two things on Home Assistant: GET /api/services (to find the notify targets) and POST
/api/services/notify/<device> (to send). Nothing else is called and no other service can be named, so the "monitoring is
read-only, nothing is controlled" rule is kept by this file, not just by policy. (A Home Assistant user token itself can do
more than that, which is why the guide asks for a user made only for MonitorBox, limited to the local network.)

Signing in uses Home Assistant's documented OAuth page flow: MonitorBox sends the owner to Home Assistant's own sign-in page
(/auth/authorize), the owner signs in there as the MonitorBox user, Home Assistant sends the browser back with a one-time code,
and MonitorBox trades the code for a refresh token (POST /auth/token). The password is never typed into or stored by MonitorBox.
Access tokens last 30 minutes and are renewed from the refresh token. A long-lived token pasted by the owner is also accepted.
"""
import json, socket, time, urllib.error, urllib.parse, urllib.request

TIMEOUT = 8.0
REFRESH_MARGIN = 60


class HAError(Exception):
    """A plain-language reason."""


class NeedsSignIn(HAError):
    """The stored sign-in no longer works; the owner has to connect again."""


def origin_of(raw):
    """http://host:port from whatever was pasted (a path, a trailing slash or spaces are dropped)."""
    u = urllib.parse.urlparse(str(raw or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname or any(c.isspace() for c in str(raw).strip()):
        raise HAError("The Home Assistant address must look like http://192.168.77.9:8123")
    return f"{u.scheme}://{u.netloc}"


def _call(method, url, headers=None, body=None, form=None, timeout=TIMEOUT):
    """Returns (status, json-or-None). Network trouble becomes an HAError in plain words; the address is never put in it."""
    data = None
    h = {"User-Agent": "MonitorBox"}
    h.update(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code = r.read(1 << 20), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(1 << 16), e.code
    except urllib.error.URLError as e:
        why = e.reason
        if isinstance(why, socket.timeout):
            raise HAError("Home Assistant did not answer in time")
        if isinstance(why, socket.gaierror):
            raise HAError("that address could not be found")
        if isinstance(why, ConnectionRefusedError):
            raise HAError("nothing is listening at that address and port")
        raise HAError("could not connect (" + (str(why) or "unknown")[:80] + ")")
    except (socket.timeout, TimeoutError):
        raise HAError("Home Assistant did not answer in time")
    except Exception as e:
        raise HAError("could not talk to Home Assistant (" + type(e).__name__ + ")")
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, None


def authorize_url(base, origin, state):
    q = urllib.parse.urlencode({"client_id": origin + "/", "redirect_uri": origin + "/ha-callback", "state": state})
    return f"{base}/auth/authorize?{q}"


def exchange_code(base, code, origin):
    """Trade the one-time code for tokens. Returns {"refresh","access","expires_in"}."""
    st, j = _call("POST", base + "/auth/token", form={"grant_type": "authorization_code", "code": code, "client_id": origin + "/"})
    if st == 403:
        raise HAError("Home Assistant says that user is not allowed to sign in (is the user switched on?)")
    if st != 200 or not isinstance(j, dict) or not j.get("refresh_token") or not j.get("access_token"):
        raise HAError("Home Assistant did not accept the sign-in. Try Connect again.")
    return {"refresh": j["refresh_token"], "access": j["access_token"], "expires_in": int(j.get("expires_in") or 1800)}


def revoke(base, refresh):
    try:
        _call("POST", base + "/auth/revoke", form={"token": refresh}, timeout=4)
    except HAError:
        pass                                    # best effort: the owner can also remove it in the user's profile


class Conn:
    """One signed-in Home Assistant. Holds the short-lived access token in memory only."""

    def __init__(self, base, origin=None, refresh=None, token=None, clock=time.time):
        self.base, self.origin, self.refresh, self.token, self.clock = base, origin, refresh, token, clock
        self.access, self.expires = token, float("inf")

    def seed(self, access, expires):
        self.access, self.expires = access, expires

    def bearer(self, force=False):
        if self.token:                          # a long-lived token never expires here
            return self.token
        if self.access and not force and self.clock() < self.expires - REFRESH_MARGIN:
            return self.access
        if not self.refresh:
            raise NeedsSignIn("MonitorBox is not signed in to Home Assistant. Connect it again.")
        st, j = _call("POST", self.base + "/auth/token", form={"grant_type": "refresh_token", "refresh_token": self.refresh, "client_id": (self.origin or "") + "/"})
        if st in (400, 401, 403) or (st == 200 and not (isinstance(j, dict) and j.get("access_token"))):
            raise NeedsSignIn("Home Assistant no longer accepts MonitorBox's sign-in (it was removed, or the user was changed). Connect it again.")
        if st != 200:
            raise HAError(f"Home Assistant answered HTTP {st} when renewing the sign-in")
        self.access, self.expires = j["access_token"], self.clock() + int(j.get("expires_in") or 1800)
        return self.access

    def _api(self, method, path, body=None):
        for attempt in (0, 1):
            st, j = _call(method, self.base + path, headers={"Authorization": "Bearer " + self.bearer(force=attempt == 1)}, body=body)
            if st == 401 and attempt == 0 and not self.token:
                continue                         # the access token may simply have expired early: renew once
            if st == 401:
                raise NeedsSignIn("Home Assistant no longer accepts MonitorBox's sign-in. Connect it again.")
            return st, j
        raise HAError("unreachable")

    # -- the only two things MonitorBox asks of Home Assistant ------------------------------------------
    def targets(self):
        """The Home Assistant app on each phone and tablet shows up as a notify service called mobile_app_<device>."""
        st, j = self._api("GET", "/api/services")
        if st == 403:
            raise HAError("Home Assistant refused to list its notify services for this user")
        if st != 200 or not isinstance(j, list):
            raise HAError(f"Home Assistant answered HTTP {st} when listing devices")
        out = []
        for d in j:
            if isinstance(d, dict) and d.get("domain") == "notify" and isinstance(d.get("services"), dict):
                for name in sorted(d["services"]):
                    if name.startswith("mobile_app_"):
                        out.append({"id": name, "name": pretty(name)})
        return out

    def notify(self, target, payload):
        if not isinstance(target, str) or not target.startswith("mobile_app_") or not target.replace("_", "").isalnum():
            raise HAError("that is not a phone or tablet notify service")
        st, j = self._api("POST", "/api/services/notify/" + target, body=payload)
        if st in (400, 404):
            raise HAError(f"Home Assistant has no device called {pretty(target)}. It may have been removed; pick the devices again.")
        if st != 200:
            raise HAError(f"Home Assistant answered HTTP {st}")


def pretty(target):
    return " ".join(w.capitalize() if not w.isdigit() else w for w in target.replace("mobile_app_", "", 1).split("_")) or target
