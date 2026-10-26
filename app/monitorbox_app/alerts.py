"""Alerts: tell the owner when something is down or degraded, and when it is back.

What counts is exactly what the main screen's attention list shows, so the rules stay in one place (engine.py): one alert per
root cause, nothing for what is marked expected down, nothing for "unknown" (we could not look, which is not a failure) and
nothing for heads-up notices. Observed state is never changed here; alerts only read it.

  - a problem is announced after it has lasted `delaySeconds` (default 60), so a blip never reaches a phone
  - when it clears, one "back" message follows after RECOVER_AFTER seconds of staying healthy
  - going from degraded to down (or back) while open sends an update
  - open alerts and anything not yet delivered are kept in config/alerts-state.json, so an App restart or update
    does not announce the same problem again and does not lose a message that is still waiting to go out
  - a storm: three or more new problems within a minute are one message ("6 things went down at once") instead of six, and one message when they are all back
  - a flapping thing (down three times in ten minutes) is one message, then one more when it has been steady for ten minutes
  - a UPS running on battery (or low, or shutting down) is announced at once; while that alert is open (even if the UPS then goes unreachable because its own host shut
    down) and for POWER_GRACE after it clears, the systems it powers (poweredBy) do not alert for being down: the UPS alert already says why, and is never held back by the storm or flap rules: power is the case where the alert may not get out
  - a message that cannot be delivered is tried again (5 s, 15 s, 45 s ... up to 5 minutes apart) for 30 minutes

Two ways to reach Home Assistant (ha.py, webhook below):
  - connected as a Home Assistant user (preferred): MonitorBox lists the phones and tablets that have the Home Assistant app,
    the owner ticks which should get alerts, and MonitorBox sends to each one directly. Real errors come back (a wrong device,
    a sign-in that no longer works). A message to several devices that only partly got through is retried for the rest only.
  - a webhook (no account): one JSON POST to http(s)://<ha>/api/webhook/<id>. Home Assistant answers 200 to any id, so a typo
    shows no error. Used only when Home Assistant is not connected.
Everything secret (the refresh or long-lived token, the webhook address) lives in config/alerts.json (mode 0600), is shown to
the signed-in owner only where the owner needs it (the webhook address, so a typo can be found; tokens never), and is never
written to a log or an error message.
"""
import calendar, json, os, re, secrets, socket, threading, time, urllib.error, urllib.request
from urllib.parse import urlparse

from . import engine, ha, mailer
from .store import read_json, write_json

RECOVER_AFTER = 30
GIVE_UP_AFTER = 1800
MAX_BACKOFF = 300
DEFAULT_DELAY = 60
LOOP_EVERY = 2.0
STATES = ("failed", "degraded")
TRIGGERS = {"down": True, "degraded": True, "unknown": False, "restored": True}      # what the owner can tick; Unknown is off until asked for
TRIGGER_STATE = {"down": "failed", "degraded": "degraded", "unknown": "unknown"}
POWER_GRACE = 600                                       # after a UPS that announced "on battery" is healthy again, the systems it powers get this long to boot before they can alert
STORM_COUNT, STORM_WINDOW, STORM_HOLD = 3, 60, 300      # this many new problems within this many seconds are one storm; later ones within STORM_HOLD join it
FLAP_COUNT, FLAP_WINDOW, FLAP_QUIET = 3, 600, 600       # this many times down within this long is flapping; steady this long ends it
URGENT = engine.POWER_URGENT           # words of the NUT module's UPS status (checked in tests)


class Invalid(ValueError):
    pass


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _clock(iso):
    """Just the time of day, in this box's time zone, such as '1:36 PM CDT' (for a phone notification, which already shows the date)."""
    try:
        t = time.localtime(calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")))
    except (ValueError, OverflowError):
        return ""
    return f"{t.tm_hour % 12 or 12}:{t.tm_min:02d} {'AM' if t.tm_hour < 12 else 'PM'} {time.strftime('%Z', t)}"


def _local(iso):
    """An event's UTC time (as sent to Home Assistant) in words, in this box's own time zone, such as 'Oct 25 at 1:36 PM CDT'. Unreadable text is left as it is."""
    try:
        t = time.localtime(calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")))
    except (ValueError, OverflowError):
        return str(iso)
    return f"{time.strftime('%b', t)} {t.tm_mday} at {t.tm_hour % 12 or 12}:{t.tm_min:02d} {'AM' if t.tm_hour < 12 else 'PM'} {time.strftime('%Z', t)}"


def post_json(url, payload, timeout=8.0):
    """POST one JSON object. Returns None on success or a plain-language reason. The address never appears in the reason."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "MonitorBox"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(256)
        return None
    except urllib.error.HTTPError as e:
        return f"Home Assistant answered HTTP {e.code}"
    except urllib.error.URLError as e:
        why = e.reason
        if isinstance(why, socket.timeout):
            return "Home Assistant did not answer in time"
        if isinstance(why, socket.gaierror):
            return "that address could not be found"
        if isinstance(why, ConnectionRefusedError):
            return "nothing is listening at that address and port"
        return "could not connect (" + (str(why) or "unknown")[:80] + ")"
    except (socket.timeout, TimeoutError):
        return "Home Assistant did not answer in time"
    except Exception as e:          # a bad address that slipped through, a dropped connection
        return "could not send (" + type(e).__name__ + ")"


def _clean_url(raw):
    u = str(raw or "").strip()
    while u.lower().endswith("%20"):        # a copied address on an iPad can carry its trailing space as the letters %20, which is a different webhook ID
        u = u[:-3].rstrip()
    if not u:
        return ""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or len(u) > 500 or any(c.isspace() for c in u):
        raise Invalid("The webhook address must start with http:// or https:// and look like http://homeassistant.local:8123/api/webhook/<id>")
    return u


def _camera_key(n):
    """A camera node's identity (one camera two sources both report is one camera), or None. Read from the snapshot's own shape."""
    cs = n.get("checks") or []
    if n.get("kind") != "aggregate" and len(cs) == 1 and cs[0].get("target") == "camera":
        return "camera:" + re.sub(r"^camera\s+", "", str(n.get("name", "")), flags=re.I).strip().lower()
    return None


def _one_per_camera(snap):
    """A camera that UniFi Protect and Scrypted both watch alerts ONCE, as one thing: it is down when either says so (the worse word wins) and back only when both
    are fine. The screen still shows both sources; only the alerting reads them as one."""
    nodes = snap.get("nodes") or {}
    groups = {}
    for nid, n in nodes.items():
        k = _camera_key(n)
        if k:
            groups.setdefault(k, []).append(nid)
    groups = {k: ids for k, ids in groups.items() if len(ids) > 1}
    if not groups:
        return snap
    sev = {"failed": 3, "degraded": 2, "unknown": 1, "healthy": 0, "pending": 0}
    out_nodes, attention = dict(nodes), list(snap.get("attention") or [])
    for k, ids in groups.items():
        worst = max(sorted(ids), key=lambda i: sev.get(nodes[i].get("state"), 0))
        merged = dict(nodes[worst], id=k, muted=all(nodes[i].get("muted") for i in ids), critical=any(nodes[i].get("critical") for i in ids))
        for i in ids:
            out_nodes.pop(i, None)
        out_nodes[k] = merged
        mine = [a for a in attention if a.get("id") in ids]
        attention = [a for a in attention if a.get("id") not in ids]
        if mine:
            top = max(mine, key=lambda a: sev.get(a.get("state"), 0))
            attention.append(dict(top, id=k))
    return dict(snap, nodes=out_nodes, attention=attention)


class Alerts:
    def __init__(self, cfg_path, state_path, snapshot, send=post_json, clock=time.time, hostname=socket.gethostname):
        self.cfg_path, self.state_path, self.snapshot, self.send, self.clock = cfg_path, state_path, snapshot, send, clock
        self.hostname = hostname
        self.lock = threading.RLock()
        self.stopped = False
        st = read_json(state_path, {}) or {}
        self.open = {k: v for k, v in (st.get("open") or {}).items() if isinstance(v, dict)}
        self.outbox = [e for e in (st.get("outbox") or []) if isinstance(e, dict)]
        self.last = st.get("last") if isinstance(st.get("last"), dict) else None
        self.storm = st.get("storm") if isinstance(st.get("storm"), dict) else None
        self.flaps = {k: v for k, v in (st.get("flaps") or {}).items() if isinstance(v, dict)}
        self.holds = {k: v for k, v in (st.get("holds") or {}).items() if isinstance(v, dict)}     # UPS id -> {"until": None while its alert is open, else when the grace ends}
        self.opens = []                 # [time, id] of every new problem lately (memory only: a restart starts counting afresh)
        self.pending = {}               # state nonce -> {"base","origin","t"} for a sign-in in progress (memory only)
        self.conn, self._conn_key = None, None
        self.needs_sign_in = False

    # -- settings ----------------------------------------------------------
    def _cfg(self):
        c = read_json(self.cfg_path, {}) or {}
        h = c.get("homeAssistant") if isinstance(c.get("homeAssistant"), dict) else {}
        d = c.get("delaySeconds")
        devs = h.get("devices")
        em = c.get("email") if isinstance(c.get("email"), dict) else {}
        port = em.get("port")
        email = {"host": str(em.get("host") or ""), "port": port if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536 else 587,
                 "security": em.get("security") if em.get("security") in mailer.SECURITY else "starttls", "user": str(em.get("user") or ""),
                 "password": str(em.get("password") or ""), "from": str(em.get("from") or ""), "to": mailer.addresses(em.get("to"))}
        tr = c.get("triggers") if isinstance(c.get("triggers"), dict) else {}
        triggers = {k: (bool(tr[k]) if k in tr else d) for k, d in TRIGGERS.items()}
        return {"email": email, "triggers": triggers, "enabled": bool(c.get("enabled")), "site": str(c.get("site") or "")[:60],
                "delaySeconds": d if isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 3600 else DEFAULT_DELAY,
                "webhook": str(h.get("webhook") or ""), "url": str(h.get("url") or ""), "origin": str(h.get("origin") or ""),
                "refresh": str(h.get("refresh") or ""), "token": str(h.get("token") or ""),
                "devices": [x for x in devs if isinstance(x, str)] if isinstance(devs, list) else []}

    def _write(self, c):
        write_json(self.cfg_path, {"enabled": c["enabled"], "site": c["site"], "delaySeconds": c["delaySeconds"],
                                   "homeAssistant": {"webhook": c["webhook"], "url": c["url"], "origin": c["origin"], "refresh": c["refresh"],
                                                     "token": c["token"], "devices": c["devices"]},
                                   "email": c["email"], "triggers": c["triggers"]})

    @staticmethod
    def _connected(c):
        return bool(c["url"] and (c["refresh"] or c["token"]))

    def _ready(self, c):
        return self._connected(c) or bool(c["webhook"]) or mailer.ready(c["email"])

    @staticmethod
    def _ha_ready(c):
        return Alerts._connected(c) or bool(c["webhook"])

    def get(self):
        """What the Alerts screen shows. The webhook address is shown to the signed-in owner (so a typo can be found); tokens never leave the box."""
        c = self._cfg()
        host = urlparse(c["webhook"]).netloc if c["webhook"] else ""
        with self.lock:
            return {"enabled": c["enabled"], "site": c["site"], "siteDefault": self._site(""), "delaySeconds": c["delaySeconds"], "triggers": c["triggers"],
                    "homeAssistant": {"set": bool(c["webhook"]), "host": host, "webhook": c["webhook"],
                                      "connected": self._connected(c), "url": c["url"], "kind": ("account" if c["refresh"] else "token") if self._connected(c) else None,
                                      "devices": c["devices"], "needsSignIn": self.needs_sign_in and self._connected(c)},
                    "email": {"set": mailer.ready(c["email"]), "host": c["email"]["host"], "port": c["email"]["port"], "security": c["email"]["security"],
                              "user": c["email"]["user"], "passwordSet": bool(c["email"]["password"]), "from": c["email"]["from"], "to": c["email"]["to"]},
                    "last": self.last, "waiting": len(self.outbox), "open": len([1 for v in self.open.values() if v.get("sent")])}

    def set(self, body):
        """Save. A missing/null webhook keeps the one already stored; an empty string clears it."""
        if not isinstance(body, dict):
            raise Invalid("expected an object")
        c = self._cfg()
        if "enabled" in body:
            c["enabled"] = bool(body["enabled"])
        if "site" in body:
            c["site"] = str(body["site"] or "").strip()[:60]
        if "delaySeconds" in body:
            d = body["delaySeconds"]
            if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 3600:
                raise Invalid("The delay must be a whole number of seconds, from 0 to 3600.")
            c["delaySeconds"] = d
        if isinstance(body.get("triggers"), dict):
            for k in TRIGGERS:
                if k in body["triggers"]:
                    c["triggers"][k] = bool(body["triggers"][k])
        h = body.get("homeAssistant")
        if isinstance(h, dict) and h.get("webhook") is not None:
            c["webhook"] = _clean_url(h["webhook"])
        if isinstance(body.get("email"), dict):
            c["email"] = self._email_from(c["email"], body["email"])
        if c["enabled"] and not self._ready(c):
            if body.get("enabled"):
                raise Invalid("Connect Home Assistant or set up email first, then turn alerts on.")
            c["enabled"] = False                           # the last way to send was just removed: alerts turn themselves off
        with self.lock:
            self._write(c)
            if not c["enabled"]:
                self.open.clear()          # turned off: turning it back on announces whatever is wrong at that moment
                self.outbox.clear()
                self._save()
        return self.get()

    @staticmethod
    def _email_from(cur, e):
        """Apply an email save. A missing password keeps the stored one; {"clear": true} forgets the whole email setup."""
        if e.get("clear"):
            return {"host": "", "port": 587, "security": "starttls", "user": "", "password": "", "from": "", "to": []}
        new = dict(cur)
        if "host" in e:
            h = str(e["host"] or "").strip()
            if " " in h or len(h) > 253 or "/" in h:
                raise Invalid("The mail server must be a name or address like smtp.gmail.com.")
            new["host"] = h
        if "port" in e:
            try:
                p = int(e["port"])
            except (TypeError, ValueError):
                p = 0
            if not 0 < p < 65536:
                raise Invalid("The mail server port must be a number such as 587 or 465.")
            new["port"] = p
        if "security" in e:
            if e["security"] not in mailer.SECURITY:
                raise Invalid("Security must be STARTTLS, SSL or none.")
            new["security"] = e["security"]
        if "user" in e:
            new["user"] = str(e["user"] or "").strip()[:254]
        if e.get("password") is not None:
            new["password"] = str(e["password"])[:200]
        if "from" in e:
            f = str(e["from"] or "").strip()
            if f and not mailer.valid_address(f):
                raise Invalid("The from-address does not look like an email address.")
            new["from"] = f
        if "to" in e:
            to = mailer.addresses(e["to"])
            bad = [a for a in to if not mailer.valid_address(a)]
            if bad or len(to) > 10:
                raise Invalid("Each to-address must look like name@example.com (up to 10, separated by commas)." if bad else "Up to 10 to-addresses.")
            new["to"] = to
        if new["host"] and not new["from"]:
            new["from"] = new["user"] if mailer.valid_address(new["user"]) else ""
        return new

    # -- Home Assistant account ------------------------------------------------
    def _conn(self, c=None):
        c = c or self._cfg()
        if not self._connected(c):
            return None
        key = (c["url"], c["origin"], c["refresh"], c["token"])
        with self.lock:
            if self.conn is None or self._conn_key != key:
                self.conn, self._conn_key = ha.Conn(c["url"], c["origin"] or None, c["refresh"] or None, c["token"] or None, self.clock), key
            return self.conn

    def begin_connect(self, url, origin):
        """Start signing in: returns the Home Assistant sign-in page address to send the browser to."""
        try:
            base, org = ha.origin_of(url), ha.origin_of(origin)
        except ha.HAError as e:
            raise Invalid(str(e))
        now = self.clock()
        with self.lock:
            for k in [k for k, v in self.pending.items() if now - v["t"] > 600]:
                del self.pending[k]
            if len(self.pending) >= 8:
                self.pending.pop(min(self.pending, key=lambda k: self.pending[k]["t"]))
            state = secrets.token_urlsafe(24)
            self.pending[state] = {"base": base, "origin": org, "t": now}
        return ha.authorize_url(base, org, state)

    def complete_connect(self, code, state, error=""):
        """The browser is back from Home Assistant's sign-in page. Returns (ok, plain message)."""
        with self.lock:
            p = self.pending.pop(state or "", None)
        if not p or self.clock() - p["t"] > 600:
            return False, "That sign-in link has expired or was not started here. Press Connect again."
        if error or not code:
            return False, "Home Assistant did not give MonitorBox access. Press Connect again and approve it."
        try:
            t = ha.exchange_code(p["base"], code, p["origin"])
        except ha.HAError as e:
            return False, str(e)
        conn = ha.Conn(p["base"], p["origin"], t["refresh"], None, self.clock)
        conn.seed(t["access"], self.clock() + t["expires_in"])
        try:
            ids = [x["id"] for x in conn.targets()]
        except ha.HAError:
            ids = []                                         # connected, but the list can be fetched again from the screen
        c = self._cfg()
        c.update({"url": p["base"], "origin": p["origin"], "refresh": t["refresh"], "token": "", "devices": ids})
        with self.lock:
            self._write(c)
            self.conn, self._conn_key = conn, (c["url"], c["origin"], c["refresh"], c["token"])
            self.needs_sign_in = False
        return True, "Connected."

    def connect_token(self, url, token):
        """The no-sign-in-page way: a long-lived access token made in the Home Assistant user's profile."""
        try:
            base = ha.origin_of(url)
        except ha.HAError as e:
            raise Invalid(str(e))
        token = str(token or "").strip()
        if not token or any(ch.isspace() for ch in token) or len(token) > 2000:
            raise Invalid("Paste the whole token, with no spaces.")
        conn = ha.Conn(base, token=token, clock=self.clock)
        try:
            ids = [x["id"] for x in conn.targets()]
        except ha.HAError as e:
            raise Invalid("Home Assistant did not accept that: " + str(e))
        c = self._cfg()
        c.update({"url": base, "origin": "", "refresh": "", "token": token, "devices": ids})
        with self.lock:
            self._write(c)
            self.conn, self._conn_key = None, None
            self.needs_sign_in = False
        return self.get()

    def disconnect(self):
        c = self._cfg()
        if c["refresh"]:
            ha.revoke(c["url"], c["refresh"])
        c.update({"url": "", "origin": "", "refresh": "", "token": "", "devices": []})
        if not c["webhook"]:
            c["enabled"] = False
        with self.lock:
            self._write(c)
            self.conn, self._conn_key = None, None
            self.needs_sign_in = False
            if not c["enabled"]:
                self.open.clear(); self.outbox.clear(); self._save()
        return self.get()

    def devices(self):
        """The phones and tablets Home Assistant knows, each marked on or off. Raises Invalid with a plain reason."""
        c = self._cfg()
        conn = self._conn(c)
        if conn is None:
            raise Invalid("Home Assistant is not connected.")
        try:
            found = conn.targets()
            self.needs_sign_in = False
        except ha.NeedsSignIn as e:
            self.needs_sign_in = True
            raise Invalid(str(e))
        except ha.HAError as e:
            raise Invalid(str(e))
        return [{**d, "on": d["id"] in c["devices"]} for d in found]

    def set_devices(self, ids):
        if not isinstance(ids, list) or len(ids) > 30 or any(not isinstance(i, str) or not i.startswith("mobile_app_") or len(i) > 120 for i in ids):
            raise Invalid("expected a list of devices")
        c = self._cfg()
        if not self._connected(c):
            raise Invalid("Home Assistant is not connected.")
        c["devices"] = sorted(set(ids))
        with self.lock:
            self._write(c)
        return self.get()

    def _site(self, configured):
        return configured or str(self.hostname() or "MonitorBox")

    # -- the rules ---------------------------------------------------------
    @staticmethod
    def _urgent(node):
        """The words that make a UPS problem urgent (running on battery, low, shutting down), or None. Only the NUT module's own UPS checks count."""
        for ch in (node or {}).get("checks", []):
            if ch.get("type") == "nut" and ch.get("state") in STATES:
                low = str(ch.get("detail") or "").lower()
                for w in URGENT:
                    if w in low:
                        return w
        return None

    def observe(self, snap, now=None):
        """Read one snapshot; queue the messages that are due. Returns the events queued (for tests)."""
        c = self._cfg()
        now = self.clock() if now is None else now
        if not c["enabled"] or not self._ready(c):
            return []
        site = self._site(c["site"])
        out = []
        snap = _one_per_camera(snap)
        with self.lock:
            nodes = snap.get("nodes", {})
            allowed = {st for k, st in TRIGGER_STATE.items() if c["triggers"][k]}
            bad = {a["id"]: a for a in snap.get("attention", [])
                   if a["state"] in allowed or a["state"] in STATES and self._urgent(nodes.get(a["id"]))}           # a UPS on battery is always announced
            bad = {nid: a for nid, a in bad.items() if not any(self._held(p, now) for p in (nodes.get(nid) or {}).get("poweredBy", []))}      # explained by a UPS that is on battery
            urgent = {nid: self._urgent(nodes.get(nid)) for nid in bad}
            self.opens = [o for o in self.opens if now - o[0] <= FLAP_WINDOW]
            fresh = []
            for nid, a in bad.items():
                rec = self.open.get(nid)
                if rec is None or rec.get("state") != a["state"]:
                    old = rec or {}
                    rec = {"state": a["state"], "seen": now, "sent": old.get("sent")}
                    if old.get("grouped"):
                        rec["grouped"] = True
                    self.open[nid] = rec
                    if not old and not urgent[nid] and a["state"] != "unknown":        # "could not look" is not a pile-up or a flap
                        fresh.append(nid)
                        self.opens.append([now, nid])
                        if nid in self.flaps:
                            self.flaps[nid]["last"] = now
                rec.pop("ok_since", None)
            self._storm_watch(bad, urgent, fresh, now)
            for nid, a in bad.items():
                rec = self.open[nid]
                urg = urgent[nid]
                if rec.get("sent") == a["state"] or rec.get("grouped") and not urg:
                    continue
                if not urg and now - rec["seen"] < c["delaySeconds"]:
                    continue
                if urg:
                    out.append(self._event("problem", site, a, now, urgent=urg))
                    self.holds[nid] = {"until": None}
                elif nid in self.flaps:
                    pass                                    # already announced as flapping: stay quiet until it is steady
                elif sum(1 for o in self.opens if o[1] == nid) >= FLAP_COUNT:
                    self.flaps[nid] = {"name": a["name"], "last": now}
                    out.append(self._flap_event(site, a, now))
                else:
                    out.append(self._event("problem", site, a, now))
                rec["sent"] = a["state"]
            for nid in list(self.open):
                if nid in bad:
                    continue
                rec, node = self.open[nid], nodes.get(nid)
                if node is None:
                    del self.open[nid]                      # taken off the list
                elif node["state"] == "healthy":
                    if not rec.get("sent"):
                        del self.open[nid]                  # cleared before anyone was told
                        continue
                    rec.setdefault("ok_since", now)
                    if now - rec["ok_since"] >= RECOVER_AFTER:
                        if not rec.get("grouped") and nid not in self.flaps:
                            out.append(self._event("recovered", site, {"id": nid, "name": node["name"], "group": node["group"],
                                                                       "state": "healthy", "critical": node["critical"], "detail": "", "affects": []}, now))
                        del self.open[nid]
                elif node["state"] in ("failed", "degraded"):
                    del self.open[nid]                      # now muted or explained by another root cause: that one speaks for it
                else:                                       # unknown / still checking: could not look, so neither alarm nor all-clear
                    rec.pop("ok_since", None)
                    if not rec.get("sent"):
                        del self.open[nid]
            out += self._storm_messages(bad, nodes, site, c, now)
            for nid in list(self.flaps):                    # steady again: one message
                fl = self.flaps[nid]
                node = nodes.get(nid)
                if nid not in bad and nid not in self.open and (node is None or node["state"] == "healthy") and now - fl["last"] >= FLAP_QUIET:
                    if node is not None:
                        out.append(self._event("recovered", site, {"id": nid, "name": node["name"], "group": node["group"], "state": "healthy",
                                                                   "critical": node["critical"], "detail": "steady again", "affects": []}, now, steady=True))
                    del self.flaps[nid]
            for uid in list(self.holds):                    # a UPS whose alert has closed: its systems get a grace period to boot, then the hold ends
                h = self.holds[uid]
                if h.get("until") is None and uid not in self.open:
                    h["until"] = now + POWER_GRACE
                elif h.get("until") is not None and now >= h["until"]:
                    del self.holds[uid]
            if not c["triggers"]["restored"]:
                out = [e for e in out if e["event"] != "recovered"]
            for e in out:
                self.outbox.append({"event": e, "tries": 0, "first": now, "next": now})
            if out or fresh:
                self._save()
        return out

    def _held(self, uid, now):
        h = self.holds.get(uid)
        return bool(h) and (h.get("until") is None or now < h["until"])

    # -- storms ------------------------------------------------------------
    def _storm_watch(self, bad, urgent, fresh, now):
        """Three new problems within a minute start a storm; new ones within STORM_HOLD of the last join it. Members are not announced one by one."""
        st = self.storm
        if st is None:
            recent = sorted({o[1] for o in self.opens if now - o[0] <= STORM_WINDOW and o[1] in bad and not urgent.get(o[1]) and bad[o[1]]["state"] != "unknown"})
            if len(recent) >= STORM_COUNT:
                st = self.storm = {"start": now, "until": now + STORM_HOLD, "ids": recent, "sent": False, "names": [], "upd": False}
        elif fresh and now <= st["until"]:
            st["ids"] = sorted(set(st["ids"]) | set(fresh))
            st["until"] = now + STORM_HOLD
        if st:
            for nid in st["ids"]:
                if nid in self.open and not urgent.get(nid):
                    self.open[nid]["grouped"] = True

    def _storm_messages(self, bad, nodes, site, c, now):
        st = self.storm
        if not st:
            return []
        out = []
        live = [n for n in st["ids"] if n in bad and n in self.open]
        names = lambda ids: [bad[n]["name"] for n in sorted(ids, key=lambda n: (not bad[n].get("critical"), bad[n]["name"].lower()))]
        if not st["sent"]:
            if now - st["start"] >= c["delaySeconds"]:
                if len(live) >= STORM_COUNT:
                    st["sent"], st["names"] = True, names(live)
                    for n in live:
                        self.open[n]["sent"] = bad[n]["state"]
                    out.append(self._storm_event("problem", site, st["names"], now))
                else:                                       # most of them cleared on their own: announce what is left the ordinary way
                    for n in st["ids"]:
                        if n in self.open:
                            self.open[n].pop("grouped", None)
                    self.storm = None
            return out
        for n in live:
            if self.open[n].get("sent") != bad[n]["state"]:
                self.open[n]["sent"] = bad[n]["state"]
        if now > st["until"] and not st["upd"]:
            st["upd"] = True
            if names(live) != st["names"] and live:
                st["names"] = names(live)
                out.append(self._storm_event("problem", site, st["names"], now, update=True))
        if not any(n in self.open for n in st["ids"]):
            out.append(self._storm_event("recovered", site, st["names"], now))
            self.storm = None
        return out

    def _storm_event(self, kind, site, names, now, update=False):
        n = len(names)
        shown = ", ".join(names[:8]) + (f" and {n - 8} more" if n > 8 else "")
        if kind == "recovered":
            title, msg, state = f"{site}: everything is back", f"All {n} things that went down together are back: {shown}.", "healthy"
        elif update:
            title, msg, state = f"{site}: {n} things are still down", f"Still down: {shown}.", "failed"
        else:
            title = f"{site}: {n} things went down at once"
            msg, state = f"{n} things went down within a minute of each other, so they are probably one cause: {shown}.", "failed"
        return {"source": "monitorbox", "event": kind, "site": site, "id": "storm", "name": f"{n} things", "group": "", "state": state, "critical": True,
                "detail": "", "title": title, "message": msg, "at": _iso(now), "atLocal": _local(_iso(now)), "count": n}

    def _flap_event(self, site, a, now):
        name = a["name"]
        return {"source": "monitorbox", "event": "problem", "site": site, "id": a["id"], "name": name, "group": a.get("group", ""), "state": a["state"], "critical": bool(a.get("critical")),
                "detail": a.get("detail", ""), "title": f"{site}: {name} keeps going down and coming back",
                "message": f"{name} has gone down {FLAP_COUNT} times in {FLAP_WINDOW // 60} minutes. No more messages until it has been steady for {FLAP_QUIET // 60} minutes.", "at": _iso(now), "atLocal": _local(_iso(now)), "flapping": True}

    def _event(self, kind, site, a, now, urgent=None, steady=False):
        name, st = a["name"], a["state"]
        verb = {"failed": "is down", "degraded": "is degraded", "healthy": "is back", "unknown": "can't be checked"}.get(st, st)
        if urgent:
            verb = URGENT[urgent]
        if steady:
            verb = "is steady again"
        msg = f"{name} {verb}."
        if kind == "problem" and a.get("detail"):
            msg += " " + str(a["detail"])
        if kind == "problem" and a.get("affects"):
            msg += " Also affected: " + ", ".join(a["affects"][:5]) + "."
        return {"source": "monitorbox", "event": kind, "site": site, "id": a["id"], "name": name, "group": a.get("group", ""),
                "state": st, "critical": bool(a.get("critical")), "detail": a.get("detail", ""),
                "title": f"{site}: {name} {verb}", "message": msg, "at": _iso(now), "atLocal": _local(_iso(now)), **({"urgent": True} if urgent else {})}

    # -- delivery ----------------------------------------------------------
    @staticmethod
    def _ha_payload(ev):
        data = {"tag": "monitorbox-" + str(ev["id"])}               # the "back" message replaces the "down" one on the phone
        if ev["event"] == "problem" and (ev["state"] == "failed" or ev.get("urgent")):
            data.update({"push": {"interruption-level": "time-sensitive"}, "ttl": 0, "priority": "high"})
        when = _clock(ev.get("at"))
        return {"title": ev["title"], "message": ev["message"] + (f" ({when} at {ev['site']})" if when else ""), "data": data}

    def _send_ha(self, c, ev, done):
        """Send to every ticked device not already done. Returns None, or a plain reason naming what failed."""
        if not c["devices"]:
            return "No devices are ticked. Tick the phones and tablets that should get alerts."
        conn = self._conn(c)
        errs = []
        for t in c["devices"]:
            if t in done:
                continue
            try:
                conn.notify(t, self._ha_payload(ev))
                done.append(t)
                self.needs_sign_in = False
            except ha.NeedsSignIn as e:
                self.needs_sign_in = True
                return str(e)
            except ha.HAError as e:
                errs.append(f"{ha.pretty(t)}: {e}")
        return "; ".join(errs) or None

    def _send_email(self, c, ev):
        e = c["email"]
        body = ev["message"] + f"\n\nSite: {ev['site']}\nTime: {_local(ev['at'])}\n"
        return mailer.send(e, ev["title"], body)

    def _deliver(self, c, item):
        """Every configured way to send gets the message once; a way that already took it is not asked again. None when all took it."""
        via = item.setdefault("via", [])
        errs = []
        if self._ha_ready(c) and "ha" not in via:
            err = self._send_ha(c, item["event"], item.setdefault("done", [])) if self._connected(c) else self.send(c["webhook"], item["event"])
            if err is None:
                via.append("ha")
            else:
                errs.append(err)
        if mailer.ready(c["email"]) and "email" not in via:
            err = self._send_email(c, item["event"])
            if err is None:
                via.append("email")
            else:
                errs.append("Email: " + err)
        if not self._ready(c):
            return "Nothing is set up to send alerts."
        return "; ".join(errs) or None

    def flush(self, now=None):
        """Try to deliver what is waiting. Safe to call often."""
        now = self.clock() if now is None else now
        c = self._cfg()
        with self.lock:
            due = [e for e in self.outbox if e["next"] <= now]
        for item in due:
            err = self._deliver(c, item)
            with self.lock:
                if err is None:
                    self.outbox.remove(item)
                    self.last = {"at": _iso(now), "ok": True, "what": item["event"]["title"], "error": None}
                else:
                    item["tries"] += 1
                    item["next"] = now + min(5 * 3 ** (item["tries"] - 1), MAX_BACKOFF)
                    self.last = {"at": _iso(now), "ok": False, "what": item["event"]["title"], "error": err}
                    if now - item["first"] >= GIVE_UP_AFTER:
                        self.outbox.remove(item)
                self._save()

    def test(self):
        """Send a test message through every way that is set up and say plainly what happened."""
        c = self._cfg()
        if not self._ready(c):
            return {"ok": False, "message": "Connect Home Assistant or set up email first."}
        now = self.clock()
        site = self._site(c["site"])
        ev = {"source": "monitorbox", "event": "test", "site": site, "id": "test", "name": "Test", "group": "", "state": "healthy",
              "critical": False, "detail": "", "title": f"{site}: test alert", "message": "This is a test alert from MonitorBox.", "at": _iso(now), "atLocal": _local(_iso(now))}
        ok, parts, why = True, [], []
        if self._ha_ready(c):
            if self._connected(c):
                done = []
                err = self._send_ha(c, ev, done)
                names = ", ".join(ha.pretty(t) for t in done)
                if err:
                    ok = False
                    why.append(err)
                    parts.append("Home Assistant: not delivered: " + err + (f" It did reach {names}." if done else ""))
                else:
                    parts.append(f"Sent to {names}. If one does not show it, open the Home Assistant app on that device and check that notifications are allowed.")
            else:
                err = self.send(c["webhook"], ev)
                if err:
                    ok = False
                    why.append(err)
                    parts.append("Home Assistant could not be reached: " + err)
                else:
                    parts.append("Sent. Home Assistant accepted it. If nothing shows on your phone, open the automation in Home Assistant, choose Traces (top right) and see whether it ran: no trace means the webhook ID does not match, a trace with a red step means the phone name is wrong.")
        if mailer.ready(c["email"]):
            err = self._send_email(c, ev)
            if err:
                ok = False
                why.append("Email: " + err)
                parts.append("Email not delivered: " + err)
            else:
                parts.append("Email sent to " + ", ".join(c["email"]["to"]) + ". If it does not arrive, check the spam folder.")
        with self.lock:
            self.last = {"at": _iso(now), "ok": ok, "what": ev["title"], "error": "; ".join(why) or None}
            self._save()
        return {"ok": ok, "message": " ".join(parts)}

    def _save(self):
        try:
            write_json(self.state_path, {"open": self.open, "outbox": self.outbox, "last": self.last, "storm": self.storm, "flaps": self.flaps, "holds": self.holds})
        except OSError:
            pass                                            # alerts must never stop the monitor

    # -- the loop ----------------------------------------------------------
    def step(self):
        try:
            self.observe(self.snapshot())
            self.flush()
        except Exception:
            pass

    def start(self):
        def loop():
            while not self.stopped:
                self.step()
                time.sleep(LOOP_EVERY)
        threading.Thread(target=loop, daemon=True, name="alerts").start()

    def stop(self):
        self.stopped = True
