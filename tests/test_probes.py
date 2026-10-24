import http.server, os, socket, struct, sys, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import probes  # noqa: E402


class FakeDNS:
    """A resolver on loopback. mode: 'ok' answers 203.0.113.7, 'servfail', 'empty', 'silent'."""
    def __init__(self, mode):
        self.mode = mode
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.2)
        self.stop = False
        self.t = threading.Thread(target=self.loop, daemon=True)
        self.t.start()

    def loop(self):
        while not self.stop:
            try:
                data, addr = self.sock.recvfrom(512)
            except OSError:
                continue
            if self.mode == "silent":
                continue
            qid, question = data[:2], data[12:]
            if self.mode == "servfail":
                self.sock.sendto(qid + struct.pack("!HHHHH", 0x8182, 1, 0, 0, 0) + question, addr)
            elif self.mode == "empty":
                self.sock.sendto(qid + struct.pack("!HHHHH", 0x8180, 1, 0, 0, 0) + question, addr)
            else:
                ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + bytes([203, 0, 113, 7])
                self.sock.sendto(qid + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + question + ans, addr)

    def close(self):
        self.stop = True
        self.t.join(1)
        self.sock.close()


class DnsTests(unittest.TestCase):
    def check(self, mode, **kw):
        f = FakeDNS(mode)
        try:
            return probes.dns("127.0.0.1", "google.com", timeout=kw.get("timeout", 1.0), port=f.port)
        finally:
            f.close()

    def test_answers(self):
        ok, detail, ms = self.check("ok")
        self.assertTrue(ok)
        self.assertEqual(detail, "google.com → 203.0.113.7")
        self.assertIsNotNone(ms)

    def test_servfail_is_a_failure_that_names_the_error(self):
        ok, detail, _ = self.check("servfail")
        self.assertFalse(ok)
        self.assertIn("SERVFAIL", detail)

    def test_answer_without_address_is_a_failure(self):
        ok, detail, _ = self.check("empty")
        self.assertFalse(ok)
        self.assertIn("no address", detail)

    def test_silent_server_is_a_failure(self):
        ok, detail, _ = self.check("silent", timeout=0.4)
        self.assertFalse(ok)
        self.assertIn("did not answer", detail)

    def test_each_server_is_judged_on_its_own(self):
        good, dead = FakeDNS("ok"), FakeDNS("silent")
        try:
            a = probes.dns("127.0.0.1", port=good.port, timeout=0.5)
            b = probes.dns("127.0.0.1", port=dead.port, timeout=0.4)
        finally:
            good.close()
            dead.close()
        self.assertEqual((a[0], b[0]), (True, False))


class TcpTests(unittest.TestCase):
    def test_open_and_closed(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        self.assertTrue(probes.tcp("127.0.0.1", port, 1)[0])
        srv.close()
        ok, detail, _ = probes.tcp("127.0.0.1", port, 1)
        self.assertFalse(ok)
        self.assertIn("refused", detail)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                code = {"/ok": 200, "/gone": 404, "/boom": 500, "/moved": 301, "/login": 401}.get(self.path, 200)
                body = {"/ok": b"<title>Radarr</title>", "/login": b"Sign in to Sonarr", "/big": b"x" * 400000 + b"Needle"}.get(self.path, b"")
                self.send_response(code)
                if code == 301:
                    self.send_header("Location", "/ok")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_codes(self):
        self.assertTrue(probes.http(self.base + "/ok")[0])
        self.assertFalse(probes.http(self.base + "/boom")[0])
        self.assertFalse(probes.http(self.base + "/gone")[0])
        self.assertTrue(probes.http(self.base + "/gone", expect=[404])[0])   # 404 is what we expect here
        self.assertTrue(probes.http(self.base + "/moved")[0])                # redirect followed to /ok

    def test_contains_tells_the_right_app_from_any_page(self):
        ok, detail, _ = probes.http(self.base + "/ok", contains="Radarr")
        self.assertTrue(ok, detail)
        self.assertTrue(probes.http(self.base + "/ok", contains="radarr")[0])             # case does not matter
        ok, detail, _ = probes.http(self.base + "/ok", contains="Sonarr")                  # status is fine, wrong app
        self.assertEqual((ok, detail), (False, "HTTP 200 but the page does not contain 'Sonarr'"))
        self.assertTrue(probes.http(self.base + "/login", expect=[401], contains="Sonarr")[0])   # a login page can be the healthy answer
        self.assertFalse(probes.http(self.base + "/boom", contains="x")[0])                # a bad status is still bad
        self.assertFalse(probes.http(self.base + "/big", contains="Needle")[0])            # only the first 256 KB is searched
        self.assertTrue(probes.http(self.base + "/ok")[0])                                 # no `contains`: unchanged
        self.assertEqual(probes.run({"type": "http", "url": self.base + "/ok", "contains": "Sonarr"})[0], False)   # reaches the probe from a check

    def test_refused(self):
        ok, detail, _ = probes.http("http://127.0.0.1:1/", timeout=1)
        self.assertFalse(ok)


class PingTests(unittest.TestCase):
    def test_loopback_or_not_permitted(self):
        ok, detail, _ = probes.ping("127.0.0.1", 1)
        self.assertIn(ok, (True, None))   # None where the environment forbids ICMP; never False for loopback
        if ok is None:
            self.assertIn("NET_RAW", detail)

    def test_unresolvable_name_is_a_failure_not_a_crash(self):
        self.assertFalse(probes.ping("no-such-host.invalid", 1)[0])


class RunTests(unittest.TestCase):
    def test_unknown_type_is_unknown_not_a_crash(self):
        self.assertIsNone(probes.run({"type": "carrier-pigeon"})[0])

    def test_dispatch(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.assertTrue(probes.run({"type": "tcp", "target": "127.0.0.1", "port": srv.getsockname()[1]})[0])
        srv.close()


class SelfSignedLan(unittest.TestCase):
    """Regression: a LAN admin page on its own self-signed certificate (https://192.168.x.x/) read as Degraded with CERTIFICATE_VERIFY_FAILED."""
    def test_a_bare_lan_ip_is_checked_without_certificate_verification_but_a_name_is_not(self):
        import shutil, ssl, subprocess, tempfile
        if not shutil.which("openssl"):
            self.skipTest("openssl not installed")
        d = tempfile.mkdtemp()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{d}/k.pem", "-out", f"{d}/c.pem",
                        "-days", "1", "-subj", "/CN=fake-admin"], check=True, capture_output=True)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(f"{d}/c.pem", f"{d}/k.pem")
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        self.assertTrue(probes._lan_ip_host(f"https://127.0.0.1:{port}/"))
        self.assertTrue(probes.http(f"https://127.0.0.1:{port}/")[0])                      # an IP address: accepted
        self.assertFalse(probes._lan_ip_host("https://example.com/"))
        self.assertFalse(probes._lan_ip_host("https://8.8.8.8/"))                           # a public IP keeps full verification
        self.assertFalse(probes.http(f"https://localhost:{port}/")[0] is True)              # a name is still verified


if __name__ == "__main__":
    unittest.main()
