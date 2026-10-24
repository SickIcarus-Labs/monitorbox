"""Passkey sign-in (#245, step 2): the checker against a software authenticator, forged answers, and the real thing in a real browser."""
import hashlib, json, os, secrets, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import test_snmp_e2e as T  # noqa: E402
from monitorbox_app import passkeys as pk  # noqa: E402
from monitorbox_app.store import Paths  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

RP, ORIGIN = "monitorbox.example.test", "https://monitorbox.example.test"

# A real signature made by an independent library (the `cryptography` package) over a fixed message, for a fresh key; the last line of defence
# against the verifier and the test signer below being wrong in the same way.
VEC = {"x": "1ed0033d13e7e2e97e4298e27b335b2de1d6971a2b83c46b139c65cbaee4c20d", "y": "bce2f5cdc1206dce29dd5d1409227cd3e639ed810e742bda11f1bedb5d5ef497",
       "msg": "6d6f6e69746f72626f78207465737420766563746f72206f6e65",
       "sig": "3045022100bc89cad42c51ddf52bc6c073055c3edc902ea374b61db1dad4cd5da518ab884e02205c7592f45ab14873ef8abadeeeb7a5d1941a0d23ef7a146908db911863d7edd1"}


def enc(v):
    """Minimal CBOR writer for what a passkey carries."""
    def head(mt, n):
        if n < 24: return bytes([mt << 5 | n])
        if n < 256: return bytes([mt << 5 | 24, n])
        return bytes([mt << 5 | 25]) + n.to_bytes(2, "big")
    if isinstance(v, bool) or v is None: return bytes([0xF5 if v else 0xF4 if v is False else 0xF6])
    if isinstance(v, int): return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes): return head(2, len(v)) + v
    if isinstance(v, str): return head(3, len(v.encode())) + v.encode()
    if isinstance(v, list): return head(4, len(v)) + b"".join(enc(x) for x in v)
    if isinstance(v, dict): return head(5, len(v)) + b"".join(enc(k) + enc(x) for k, x in v.items())
    raise TypeError(v)


def sign(d, msg):
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = secrets.randbelow(pk.N - 1) + 1
        r = pk._mul(k, pk.G)[0] % pk.N
        s = pow(k, -1, pk.N) * (e + r * d) % pk.N
        if r and s: break
    der = lambda n: (lambda b: b"\x00" + b if b[0] & 0x80 else b)(n.to_bytes((n.bit_length() + 7) // 8, "big"))
    body = b"\x02" + bytes([len(der(r))]) + der(r) + b"\x02" + bytes([len(der(s))]) + der(s)
    return b"\x30" + bytes([len(body)]) + body


class Device:
    """A software authenticator: one passkey, made and used the way a phone would."""
    def __init__(self, count=0, uv=True, alg=-7):
        self.d = secrets.randbelow(pk.N - 1) + 1
        self.pub = pk._mul(self.d, pk.G)
        self.cid, self.count, self.uv, self.alg = os.urandom(24), count, uv, alg

    def flags(self, extra=0):
        return 0x01 | (0x04 if self.uv else 0) | extra

    def create(self, challenge, origin=ORIGIN, rp=RP, kind="webauthn.create"):
        cose = {1: 2, 3: self.alg, -1: 1, -2: self.pub[0].to_bytes(32, "big"), -3: self.pub[1].to_bytes(32, "big")}
        ad = hashlib.sha256(rp.encode()).digest() + bytes([self.flags(0x40)]) + struct.pack(">I", self.count) + bytes(16) + struct.pack(">H", len(self.cid)) + self.cid + enc(cose)
        cd = json.dumps({"type": kind, "challenge": challenge, "origin": origin}).encode()
        return {"id": pk.b64u(self.cid), "rawId": pk.b64u(self.cid),
                "response": {"clientDataJSON": pk.b64u(cd), "attestationObject": pk.b64u(enc({"fmt": "none", "attStmt": {}, "authData": ad}))}}

    def get(self, challenge, origin=ORIGIN, rp=RP, kind="webauthn.get", bump=1, sign_challenge=None):
        self.count += bump
        ad = hashlib.sha256(rp.encode()).digest() + bytes([self.flags()]) + struct.pack(">I", self.count)
        cd = json.dumps({"type": kind, "challenge": challenge, "origin": origin}).encode()
        signed = json.dumps({"type": kind, "challenge": sign_challenge, "origin": origin}).encode() if sign_challenge else cd
        sig = sign(self.d, ad + hashlib.sha256(signed).digest())
        return {"id": pk.b64u(self.cid), "rawId": pk.b64u(self.cid),
                "response": {"clientDataJSON": pk.b64u(cd), "authenticatorData": pk.b64u(ad), "signature": pk.b64u(sig)}}


class Checker(unittest.TestCase):
    def setUp(self):
        self.p = pk.Passkeys(Paths(tempfile.mkdtemp()))

    def register(self, dev=None, **kw):
        dev = dev or Device()
        o = self.p.register_options(RP)
        self.p.register_finish(o["handle"], dev.create(o["publicKey"]["challenge"], **kw), RP, ORIGIN, "Test phone")
        return dev

    def login(self, dev, **kw):
        o = self.p.login_options(RP)
        return self.p.login_finish(o["handle"], dev.get(o["publicKey"]["challenge"], **kw), RP, ORIGIN)

    def refused(self, fn, why):
        with self.assertRaises(ValueError, msg=why):
            fn()

    def test_signature_maths_matches_an_independent_library_and_refuses_changes(self):
        x, y, msg, sig = int(VEC["x"], 16), int(VEC["y"], 16), bytes.fromhex(VEC["msg"]), bytes.fromhex(VEC["sig"])
        self.assertTrue(pk.verify_es256(x, y, msg, sig))
        self.assertFalse(pk.verify_es256(x, y, msg + b"!", sig), "another message")
        self.assertFalse(pk.verify_es256(x, y, msg, sig[:-1] + bytes([sig[-1] ^ 1])), "one bit of the signature")
        self.assertFalse(pk.verify_es256(x + 1, y, msg, sig), "a point that is not on the curve")
        self.assertFalse(pk.verify_es256(*pk.G, msg, sig), "another key")
        self.assertFalse(pk.verify_es256(x, y, msg, b"\x30\x06\x02\x01\x00\x02\x01\x00"), "r and s of zero")
        self.assertFalse(pk.verify_es256(x, y, msg, sig + b"\x00"), "trailing bytes")
        self.assertFalse(pk.verify_es256(x, y, msg, b""), "nothing")

    def test_a_software_authenticators_signatures_pass_and_forged_ones_do_not(self):
        d = Device()
        for _ in range(3):
            m = os.urandom(40)
            self.assertTrue(pk.verify_es256(*d.pub, m, sign(d.d, m)))
            self.assertFalse(pk.verify_es256(*d.pub, m + b"x", sign(d.d, m)))
            self.assertFalse(pk.verify_es256(*Device().pub, m, sign(d.d, m)))

    def test_register_then_sign_in(self):
        dev = self.register()
        self.assertEqual([k["name"] for k in self.p.listing()], ["Test phone"])
        self.assertTrue(self.login(dev))
        self.assertTrue(self.login(dev), "and again: the counter moves on")
        self.assertIsNotNone(self.p.listing()[0]["lastUsed"])

    def test_registering_refuses_the_wrong_site_origin_kind_challenge_person_and_key_type(self):
        for kw, why in (({"origin": "https://evil.example.test"}, "origin"), ({"rp": "evil.example.test"}, "site name"), ({"kind": "webauthn.get"}, "kind")):
            self.refused(lambda: self.register(**kw), why)
        o = self.p.register_options(RP)
        self.refused(lambda: self.p.register_finish(o["handle"], Device().create("not-the-challenge"), RP, ORIGIN, "x"), "challenge")
        self.refused(lambda: self.register(Device(uv=False)), "not verified (no Face ID / PIN)")
        self.refused(lambda: self.register(Device(alg=-257)), "a key type we do not support")
        o = self.p.register_options(RP); body = Device().create(o["publicKey"]["challenge"])
        self.p.register_finish(o["handle"], body, RP, ORIGIN, "once")
        self.refused(lambda: self.p.register_finish(o["handle"], body, RP, ORIGIN, "twice"), "a challenge works once")
        self.assertEqual(len(self.p.listing()), 1)
        self.refused(lambda: self.p.register_finish("nope", body, RP, ORIGIN, "x"), "unknown request")

    def test_sign_in_refuses_forgeries_replays_and_copies(self):
        dev = self.register()
        self.refused(lambda: self.login(Device()), "a passkey nobody added")
        self.refused(lambda: self.login(dev, origin="https://evil.example.test"), "origin")
        self.refused(lambda: self.login(dev, rp="evil.example.test"), "site name")
        self.refused(lambda: self.login(dev, kind="webauthn.create"), "kind")
        self.refused(lambda: self.login(dev, sign_challenge="another-challenge"), "signed something else")
        dev.uv = False
        self.refused(lambda: self.login(dev), "not verified")
        dev.uv = True
        o = self.p.login_options(RP); good = dev.get(o["publicKey"]["challenge"])
        self.assertTrue(self.p.login_finish(o["handle"], good, RP, ORIGIN))
        self.refused(lambda: self.p.login_finish(o["handle"], good, RP, ORIGIN), "the same answer again")
        o = self.p.login_options(RP)
        self.refused(lambda: self.p.login_finish(o["handle"], dev.get(o["publicKey"]["challenge"], bump=-5), RP, ORIGIN), "a counter that went backwards (a copy)")
        o = self.p.login_options(RP); bad = dev.get(o["publicKey"]["challenge"])
        sig = bytearray(pk.unb64u(bad["response"]["signature"])); sig[10] ^= 0x40; bad["response"]["signature"] = pk.b64u(bytes(sig))
        self.refused(lambda: self.p.login_finish(o["handle"], bad, RP, ORIGIN), "a damaged signature")

    def test_passkeys_that_keep_their_counter_at_zero_still_work(self):
        dev = self.register(Device(count=0))
        self.assertTrue(self.login(dev, bump=0)); self.assertTrue(self.login(dev, bump=0))

    def test_garbage_is_refused_not_crashed_on(self):
        o = self.p.login_options(RP) if self.register() else None
        for body in ({}, {"response": {}}, {"response": "x"}, {"rawId": 5, "response": {"clientDataJSON": 5}}, {"response": {"clientDataJSON": "!!!"}}, None):
            o = self.p.login_options(RP)
            self.refused(lambda: self.p.login_finish(o["handle"], body or {}, RP, ORIGIN), repr(body))
            o = self.p.register_options(RP)
            self.refused(lambda: self.p.register_finish(o["handle"], body or {}, RP, ORIGIN, "x"), repr(body))
        for raw in (b"", b"\xff", b"\x9f", b"\xbf\x00", b"\x5b" + b"\xff" * 8):
            with self.assertRaises((ValueError, IndexError)):
                pk.cbor(raw)

    def test_removing_and_the_limit(self):
        dev = self.register()
        cid = self.p.listing()[0]["id"]
        self.assertEqual(self.p.remove(cid), 0)
        self.refused(lambda: self.p.remove(cid), "already gone")
        self.refused(lambda: self.login(dev), "a removed passkey no longer works") if self.p.count() else None


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class RealBrowser(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_a_virtual_face_id_registers_signs_in_and_the_internet_can_be_made_passkey_only(self):
        c = self.start()
        self.assertEqual(c.post("/api/passkeys/register/options").get("_status"), 400, "no public name yet: refused with a reason")
        c.post("/api/security", {"publicHost": "localhost"})
        self.assertEqual(c.post("/api/security", {"internetNeedsPasskey": True}).get("_status"), 400, "needs a passkey first")
        url = f"http://localhost:{self.port}/"
        with sync_playwright() as p:
            b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 420, "height": 900}); pg = ctx.new_page()
            cdp = ctx.new_cdp_session(pg); cdp.send("WebAuthn.enable")
            cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True, "isUserVerified": True, "automaticPresenceSimulation": True}})
            pg.goto(url); pg.wait_for_selector("input[type=password]")
            self.assertEqual(pg.locator("text=Sign in with a passkey").count(), 0, "no button until a passkey exists")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(url + "#/settings/security"); pg.wait_for_selector("text=Add a passkey on this device")
            pg.click("text=Add a passkey on this device"); pg.fill("#ask-in", "Fake iPad"); pg.click("#ask-ok")
            pg.wait_for_selector("text=Fake iPad")
            self.assertEqual(len(c.get("/api/security")["passkeys"]), 1)
            # a second registration on the same device is refused (the browser sees the existing one), and the list stays at one
            pg.evaluate("api('logout',{})"); pg.goto(url); pg.reload(); pg.wait_for_selector("text=Sign in with a passkey")
            pg.click("text=Sign in with a passkey"); pg.wait_for_selector(".card")
            self.assertEqual(pg.evaluate("api('state').then(()=>'in')"), "in", "the passkey signed us in")
            pg.goto(url + "#/settings/security"); pg.wait_for_selector("text=Fake iPad")
            self.assertIn("last used", pg.inner_text("#secset"))
            self.assertIn("If you lose a device", pg.inner_text("#secset"))
            self.assertEqual(pg.locator("#secset button:text-is('Sign out this device')").count(), 1, "this device can sign itself out from here too")
            b.close()
        out = c.post("/api/signout-others")
        self.assertGreaterEqual(out["signedOut"], 1, "the browser's sign-in is gone"); self.assertEqual(out["signedIn"], 1)
        self.assertEqual(c.get("/api/security")["signedIn"], 1, "this device is still signed in")
        # the internet-only rule: now possible, and a password sign-in through the proxy is refused while home stays open
        self.assertEqual(c.post("/api/security", {"trustedProxies": ["127.0.0.1"], "internetNeedsPasskey": True})["internetNeedsPasskey"], True)
        import urllib.request, urllib.error
        def login(headers):
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/login", json.dumps({"password": T.PASSWORD}).encode(), {"X-MB": "1", "Content-Type": "application/json", **headers})
            try:
                return urllib.request.urlopen(req, timeout=15).status
            except urllib.error.HTTPError as e:
                return e.code
        self.assertEqual(login({"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https", "Host": "localhost"}), 403)
        self.assertEqual(login({}), 200, "at home the password still works")
        h = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/api/health", headers={"X-Forwarded-For": "203.0.113.9", "Host": "localhost"})).read())
        self.assertEqual((h["passkeys"], h["passkeyOnly"]), (True, True))
        # a forged answer is refused and counts as a wrong try
        c2 = T.Client(self.port)
        o = c2.post("/api/passkeys/login/options")
        self.assertEqual(o.get("_status"), 400, "from 127.0.0.1 without the public name's host, no ceremony")
        # removing the last passkey switches the rule off, so the internet is never left with nothing that works
        pid = c.get("/api/security")["passkeys"][0]["id"]
        out = c.post("/api/passkeys/remove", {"id": pid})
        self.assertEqual((out["passkeys"], out["internetNeedsPasskey"]), ([], False))


if __name__ == "__main__":
    unittest.main()
