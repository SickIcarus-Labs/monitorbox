"""Safe to open over the internet (#245, step 1): who is really asking, lockout, Secure cookie, setup and health from outside, headers."""
import json, os, sys, unittest, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import test_snmp_e2e as T  # noqa: E402
from monitorbox_app import security  # noqa: E402

PROXY = "192.168.77.9"          # fake, like every value in tests
OUT = "203.0.113.77"           # a documentation address: "somebody on the internet"
OUT2 = "198.51.100.5"


class Hdr(dict):
    def get(self, k, d=None):
        return super().get(k, d)


class Unit(unittest.TestCase):
    def sec(self, proxies=(PROXY,), host=""):
        import tempfile
        from monitorbox_app.store import Paths
        s = security.Security(Paths(tempfile.mkdtemp()))
        s.save({"trustedProxies": list(proxies), "publicHost": host})
        return s

    def test_forwarded_headers_are_believed_only_from_the_listed_proxy(self):
        s = self.sec()
        via = s.request(PROXY, Hdr({"X-Forwarded-For": OUT, "X-Forwarded-Proto": "https", "Host": "monitorbox.example.test"}))
        self.assertEqual((via.ip, via.via_proxy, via.https), (OUT, True, True))
        liar = s.request("192.168.77.77", Hdr({"X-Forwarded-For": OUT, "X-Forwarded-Proto": "https"}))      # anyone else claiming to be forwarded
        self.assertEqual((liar.ip, liar.via_proxy, liar.https), ("192.168.77.77", False, False))

    def test_only_the_address_the_proxy_itself_added_counts(self):
        s = self.sec()
        r = s.request(PROXY, Hdr({"X-Forwarded-For": f"{OUT2}, {OUT}"}))        # the visitor wrote the first one; the proxy added the last
        self.assertEqual(r.ip, OUT)
        self.assertEqual(s.request("::ffff:" + PROXY, Hdr({"X-Forwarded-For": OUT})).via_proxy, True)

    def test_a_proxy_visit_without_a_usable_address_is_never_a_home_visit(self):
        # changed for #337: this used to expect via_proxy False for the garbage address, which made an unreadable forwarded visit count as
        # coming from the home network (password sign-in, first-time setup). A visit the proxy passed on is now always an outside one.
        s = self.sec()
        self.assertFalse(s.request(PROXY, Hdr({})).via_proxy, "no forwarding headers at all: the proxy's own machine, visiting directly")
        r = s.request(PROXY, Hdr({"X-Forwarded-For": "not-an-address", "X-Forwarded-Proto": "https"}))
        self.assertTrue(r.via_proxy)
        self.assertEqual(r.ip, PROXY)
        self.assertTrue(s.request(PROXY, Hdr({"X-Real-IP": "198.51.100.7"})).via_proxy, "forwarded some other way: still outside")

    def test_forwarded_visits_from_an_unlisted_proxy_are_noticed(self):
        s = self.sec()
        self.assertTrue(s.forwarded(Hdr({"X-Forwarded-For": OUT})))
        self.assertFalse(s.forwarded(Hdr({})))

    def test_public_name_is_enforced_only_through_the_proxy(self):
        s = self.sec(host="monitorbox.example.test")
        ok = s.request(PROXY, Hdr({"X-Forwarded-For": OUT, "Host": "monitorbox.example.test"}))
        bad = s.request(PROXY, Hdr({"X-Forwarded-For": OUT, "Host": "other.example.test"}))
        direct = s.request("192.168.77.50", Hdr({"Host": "192.168.77.5:8090"}))
        self.assertEqual((s.host_ok(ok), s.host_ok(bad), s.host_ok(direct)), (True, False, True))

    def test_settings_are_checked_and_tidy(self):
        self.assertEqual(security.clean({"trustedProxies": ["192.168.77.9", "::ffff:192.168.77.9"], "publicHost": " MonitorBox.Example.Test "}),
                         {"trustedProxies": ["192.168.77.9"], "publicHost": "monitorbox.example.test", "internetNeedsPasskey": False})
        for bad in ({"trustedProxies": ["nope"]}, {"publicHost": "https://x.example.test"}, {"trustedProxies": [f"10.0.0.{i}" for i in range(1, 8)]}):
            with self.assertRaises(ValueError):
                security.clean(bad)

    def test_lockout_grows_forgets_and_does_not_block_other_addresses(self):
        now = [1000.0]
        lo = security.Lockout(lambda: now[0])
        for _ in range(security.FREE_TRIES - 1):
            lo.failed(OUT, True)
        self.assertEqual(lo.wait(OUT, True), 0, "a few slips are free")
        lo.failed(OUT, True)
        first = lo.wait(OUT, True)
        self.assertTrue(0 < first <= security.BASE_LOCK)
        self.assertEqual(lo.wait(OUT2, True), 0, "another address is not affected")
        now[0] += first + 1
        self.assertEqual(lo.wait(OUT, True), 0, "the lock ends")
        lo.failed(OUT, True)
        self.assertGreater(lo.wait(OUT, True), first, "each further wrong try waits longer")
        now[0] += security.FORGET + security.MAX_LOCK + 5
        lo.failed(OUT, True)
        self.assertEqual(lo.wait(OUT, True), 0, "a quiet address starts again")
        lo.ok(OUT); self.assertEqual(lo.wait(OUT, True), 0)

    def test_many_addresses_guessing_at_once_pauses_outside_sign_in_but_not_the_home_network(self):
        now = [1000.0]
        lo = security.Lockout(lambda: now[0])
        for i in range(security.SPRAY_TRIES):
            lo.failed(f"198.51.100.{i + 1}", True)
        self.assertGreater(lo.wait("198.51.100.200", True), 0)
        self.assertEqual(lo.wait("192.168.77.50", False), 0, "the owner at home is never locked out by strangers")


class Wire(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def raw(self, method, path, body=None, headers=None, cookie=None):
        h = {"X-MB": "1", "Content-Type": "application/json", **(headers or {})}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", json.dumps(body).encode() if body is not None else None, h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.headers, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, json.loads(e.read() or b"{}")

    def through_proxy(self, **extra):
        return {"X-Forwarded-For": OUT, "X-Forwarded-Proto": "https", "Host": "monitorbox.example.test", **extra}

    def test_outside_visits_are_hardened_and_home_visits_are_not_disturbed(self):
        c = self.start()                                                 # signed in directly (home network)
        self.assertEqual(c.post("/api/security", {"trustedProxies": ["127.0.0.1"], "publicHost": "monitorbox.example.test"})["trustedProxies"], ["127.0.0.1"])
        self.assertEqual(c.get("/api/security")["you"]["viaProxy"], False, "a direct visit is not a proxy visit, even with the proxy listed")

        # a stranger: health says nothing about the box; first-time setup is refused; headers are set
        st, hd, body = self.raw("GET", "/api/health", headers=self.through_proxy())
        self.assertEqual(body, {"ok": True, "passwordSet": True, "passkeys": False, "passkeyOnly": False})      # nothing about the box itself
        self.assertEqual(hd["X-Frame-Options"], "DENY"); self.assertEqual(hd["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", hd["Content-Security-Policy"]); self.assertIn("max-age", hd["Strict-Transport-Security"])
        self.assertEqual(self.raw("POST", "/api/setup", {"password": "fake-claim-1234"}, self.through_proxy())[0], 403)
        self.assertEqual(self.raw("GET", "/api/health")[2]["version"], "0.12.0", "at home the health page is as before")
        self.assertNotIn("Strict-Transport-Security", self.raw("GET", "/api/health")[1])

        # the wrong name is refused, only through the proxy
        self.assertEqual(self.raw("GET", "/", headers=self.through_proxy(Host="other.example.test"))[0], 421)
        self.assertEqual(self.raw("GET", "/api/health")[0], 200)

        # signing in through the proxy over https gives a Secure cookie; at home it does not
        st, hd, _ = self.raw("POST", "/api/login", {"password": T.PASSWORD}, self.through_proxy())
        self.assertEqual(st, 200); self.assertIn("Secure", hd["Set-Cookie"]); self.assertIn("HttpOnly", hd["Set-Cookie"]); self.assertIn("SameSite=Strict", hd["Set-Cookie"])
        cookie = hd["Set-Cookie"].split(";")[0]
        self.assertIn("version", self.raw("GET", "/api/health", headers=self.through_proxy(), cookie=cookie)[2], "once signed in, the version shows")
        st, hd, _ = self.raw("POST", "/api/login", {"password": T.PASSWORD})
        self.assertEqual(st, 200); self.assertNotIn("Secure", hd["Set-Cookie"])

        # guessing: five wrong tries lock that address (even the right password waits), another address is untouched, home is untouched
        for _ in range(security.FREE_TRIES):
            self.assertEqual(self.raw("POST", "/api/login", {"password": "wrong-guess-0000"}, self.through_proxy())[0], 401)
        st, hd, body = self.raw("POST", "/api/login", {"password": T.PASSWORD}, self.through_proxy())
        self.assertEqual(st, 429); self.assertIn("Too many wrong passwords", body["error"]); self.assertGreater(body["retryAfter"], 0)
        self.assertEqual(self.raw("POST", "/api/login", {"password": T.PASSWORD}, self.through_proxy(**{"X-Forwarded-For": OUT2}))[0], 200)
        self.assertEqual(self.raw("POST", "/api/login", {"password": T.PASSWORD})[0], 200)

        # someone who is not the proxy cannot pretend to be a forwarded visit (or to be somebody else)
        self.assertEqual(c.post("/api/security", {"trustedProxies": ["192.168.77.9"]})["trustedProxies"], ["192.168.77.9"])
        st, hd, body = self.raw("GET", "/api/health", headers={"X-Forwarded-For": OUT, "X-Forwarded-Proto": "https"})
        self.assertIn("version", body); self.assertNotIn("Strict-Transport-Security", hd)
        self.assertEqual(c.post("/api/security", {"trustedProxies": ["not an address"]}).get("_status"), 400)


if __name__ == "__main__":
    unittest.main()
