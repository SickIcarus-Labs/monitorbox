"""#337: what a stranger can make the box do before signing in.

Before: a POST was read in full (any Content-Length) before anyone checked who was asking, and a silent connection was held open for good,
so a visitor on the internet could fill the Pi's memory or its threads. Junk passkey answers also counted towards the internet-wide pause,
so anyone could keep the owner's passkey sign-in paused. And /icons/ would serve any .svg file on the box."""
import http.client, json, os, socket, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box  # noqa: E402
from monitorbox_app import server, security  # noqa: E402


def raw(port, data, wait=5):
    s = socket.create_connection(("127.0.0.1", port), timeout=wait)
    s.sendall(data)
    out = b""
    try:
        while True:
            b = s.recv(65536)
            if not b:
                break
            out += b
            if b"\r\n\r\n" in out:
                break
    finally:
        s.close()
    return out


class BeforeSignIn(unittest.TestCase):
    def setUp(self):
        self.box = Box(self, "fake-limits-pw-61")

    def test_a_huge_body_is_refused_without_being_read(self):
        t0 = time.monotonic()
        got = raw(self.box.port, b"POST /api/login HTTP/1.1\r\nHost: x\r\nX-MB: 1\r\nContent-Length: 4000000000\r\n\r\n{")
        self.assertIn(b" 413 ", got.split(b"\r\n")[0])
        self.assertLess(time.monotonic() - t0, 3, "answered at once, not after waiting for 4 GB")

    def test_a_stranger_gets_nothing_read_on_other_calls(self):
        got = raw(self.box.port, b"POST /api/alerts HTTP/1.1\r\nHost: x\r\nX-MB: 1\r\nContent-Length: 50000000\r\n\r\n{")
        self.assertIn(b" 401 ", got.split(b"\r\n")[0])

    def test_a_bad_length_is_refused(self):
        got = raw(self.box.port, b"POST /api/login HTTP/1.1\r\nHost: x\r\nX-MB: 1\r\nContent-Length: -5\r\n\r\n")
        self.assertIn(b" 400 ", got.split(b"\r\n")[0])

    def test_a_signed_in_owner_still_posts_normally(self):
        self.assertEqual(self.box.req("POST", "/api/display", {})[0], 200)

    def test_a_silent_connection_is_not_held_for_good(self):
        self.assertEqual(server.SOCKET_WAIT, 60)
        self.assertIsNotNone(self.box.app.httpd.RequestHandlerClass.timeout)

    def test_icons_serve_only_bare_names(self):
        import tempfile
        d = tempfile.mkdtemp(); self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        with open(os.path.join(d, "outside.svg"), "w") as f:
            f.write("<svg>not an icon</svg>")
        c = http.client.HTTPConnection("127.0.0.1", self.box.port, timeout=10)
        c.request("GET", "/icons/" + "../" * 20 + d.lstrip("/") + "/outside.svg")
        self.assertEqual(c.getresponse().status, 404, "a file outside the icons folder is not served")
        c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.box.port, timeout=10)
        c.request("GET", "/icons/index.json")
        r = c.getresponse(); names = json.loads(r.read())["icons"]; c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.box.port, timeout=10)
        c.request("GET", f"/icons/{names[0]}.svg")
        self.assertEqual(c.getresponse().status, 200, "a real icon still loads")
        c.close()


class PasskeyChallenges(unittest.TestCase):
    def test_asking_over_and_over_never_pushes_out_someone_elses_sign_in(self):
        import tempfile
        from monitorbox_app import passkeys
        from monitorbox_app.store import Paths
        p = passkeys.Passkeys(Paths(tempfile.mkdtemp()))
        mine, _ = p._challenge("login", "203.0.113.9")                       # the owner starts a sign-in
        for i in range(passkeys.MAX_PENDING * 3):
            p._challenge("login", f"198.51.100.{i % 7}")                     # strangers ask hundreds of times
        self.assertIn(mine, p.pending, "the owner's challenge is still there")
        self.assertLessEqual(len(p.pending), passkeys.MAX_PENDING)
        self.assertLessEqual(sum(1 for v in p.pending.values() if v[3] == "198.51.100.1"), passkeys.PER_ASKER)


class PasskeyPause(unittest.TestCase):
    def test_junk_passkey_answers_do_not_pause_everyone(self):
        lk = security.Lockout(clock=lambda: 1000.0)
        for i in range(security.SPRAY_TRIES + 5):
            lk.failed(f"198.51.100.{i}", False)        # how the passkey path now counts a failure
        self.assertEqual(lk.wait("203.0.113.9", False), 0, "the owner, from a new address, is not paused")
        self.assertEqual(lk.wait("203.0.113.9", True), 0)


if __name__ == "__main__":
    unittest.main()
