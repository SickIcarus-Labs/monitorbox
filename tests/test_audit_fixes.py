"""Fixes from the documentation pass (#328): a Portainer redirect never carries the token on, and one garbled line does not end the SNMP module."""
import http.server, json, os, subprocess, sys, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules", "portainer"))
import portainerlib as P


class Redirect(unittest.TestCase):
    def test_a_redirect_is_refused_and_the_token_never_reaches_the_other_address(self):
        seen = []

        class Elsewhere(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get("X-API-Key"))
                self.send_response(200); self.end_headers(); self.wfile.write(b"[]")
            def log_message(self, *a): pass
        other = http.server.HTTPServer(("127.0.0.1", 0), Elsewhere)
        target = f"http://127.0.0.1:{other.server_port}/api/endpoints"

        class Front(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302); self.send_header("Location", target); self.end_headers()
            def log_message(self, *a): pass
        front = http.server.HTTPServer(("127.0.0.1", 0), Front)
        for s in (other, front):
            threading.Thread(target=s.serve_forever, daemon=True).start()
            self.addCleanup(s.shutdown)
        c = P.Client(f"http://127.0.0.1:{front.server_port}", "example-token-7731", verify_tls=False, timeout=3)
        with self.assertRaises(P.PortainerError) as cm:
            c.endpoints()
        self.assertIn("redirected", str(cm.exception))
        self.assertEqual(seen, [], "the redirect target must not have been asked at all")


class SnmpBadLine(unittest.TestCase):
    def test_a_garbled_line_is_skipped_and_the_module_keeps_answering(self):
        mod = os.path.join(HERE, "..", "modules", "snmp")
        p = subprocess.Popen([sys.executable, "main.py"], cwd=mod, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.kill)
        p.stdin.write("this is not json\n[1,2]\n" + json.dumps({"id": 7, "method": "hello", "params": {}}) + "\n"); p.stdin.flush()
        reply = json.loads(p.stdout.readline())
        self.assertEqual(reply["id"], 7)
        self.assertIn("result", reply)



class UpsMostSeriousWord(unittest.TestCase):
    def test_on_battery_and_low_battery_together_is_announced_as_low_battery(self):
        sys.path.insert(0, os.path.join(HERE, "..", "app"))
        from monitorbox_app import alerts, engine
        node = {"checks": [{"type": "nut", "state": "degraded", "detail": "UPS Example · on battery · low battery · 4 min left"}]}
        self.assertEqual(alerts.Alerts._urgent(node), "low battery")
        self.assertEqual(engine.POWER_URGENT["low battery"], "has a low battery")



class SecondBatch(unittest.TestCase):
    """The next set of fixes from #328."""
    def test_wake_broadcast_must_be_ipv4_because_the_packet_goes_out_over_ipv4(self):
        sys.path.insert(0, os.path.join(HERE, "..", "app"))
        from monitorbox_app import monconfig
        _, errs = monconfig.validate_wake({"macs": ["02:00:5e:00:53:01"], "broadcast": "2001:db8::ffff"})
        self.assertTrue(any("IPv4" in e for e in errs), errs)
        w, errs = monconfig.validate_wake({"macs": ["02:00:5e:00:53:01"], "broadcast": "192.0.2.255"})
        self.assertEqual((errs, w["broadcast"]), ([], "192.0.2.255"))

    def test_the_protect_suggestion_does_not_copy_the_network_consoles_port(self):
        sys.path.insert(0, os.path.join(HERE, "..", "app"))
        from monitorbox_app import followups
        src = {"id": "gw", "module": "unifi-network", "host": "192.0.2.1", "port": 8443, "username": "example-reader", "password": "example-pass-4417"}
        self.assertNotIn("port", followups.protect_from(src, {"gw"}))

    def test_a_login_that_returns_no_session_is_backed_off_like_any_failed_login(self):
        sys.path.insert(0, os.path.join(HERE, "..", "modules", "unifi-protect"))
        import protectlib
        c = protectlib.Client("192.0.2.1", "example-reader", "example-pass-4417")
        calls = []

        class Headers:
            def get_all(self, name): return []
        c._request = lambda *a, **k: (calls.append(1), (200, b"{}", Headers()))[1]
        for _ in range(2):
            with self.assertRaises(protectlib.ProtectError):
                c._login()
        self.assertEqual(len(calls), 1, "the second try must wait out the back-off, not ask the console again")

    def test_a_nut_server_that_accepts_but_never_answers_says_it_did_not_answer(self):
        import socket
        sys.path.insert(0, os.path.join(HERE, "..", "modules", "nut"))
        import nutlib
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        self.addCleanup(srv.close)
        port = srv.getsockname()[1]
        c = nutlib.Client("127.0.0.1", port, timeout=0.5)
        with self.assertRaises(nutlib.NutError) as cm:
            c.list_ups()
        self.assertIn("did not answer in time", str(cm.exception))



class ConsoleThatStopsAnswering(unittest.TestCase):
    """On Oct 29 a UniFi console went quiet for six minutes and every UniFi and Protect check read 'module did not answer': each call waited out its own
    timeout behind the one before it. After one real failure the rest must fail at once with the real reason."""
    def silent_server(self):
        import socket
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(50)
        self.addCleanup(srv.close)
        return srv.getsockname()[1]

    def test_unifi_network_calls_queued_behind_a_silent_console_fail_at_once(self):
        import time
        sys.path.insert(0, os.path.join(HERE, "..", "modules", "unifi-network"))
        import unifilib
        c = unifilib.Client(f"https://127.0.0.1:{self.silent_server()}", "example-reader", "example-pass-4417", "default", False, 0.5)
        t0 = time.time()
        for _ in range(6):
            with self.assertRaises(unifilib.UnifiError) as cm:
                c.get("stat/device")
            self.assertIn("cannot reach the UniFi controller", str(cm.exception))
        self.assertLess(time.time() - t0, 2.0, "six calls must cost about one timeout, not six")

    def test_protect_calls_queued_behind_a_silent_console_fail_at_once(self):
        import time
        sys.path.insert(0, os.path.join(HERE, "..", "modules", "unifi-protect"))
        import protectlib
        c = protectlib.Client(f"https://127.0.0.1:{self.silent_server()}", "example-reader", "example-pass-4417", False, 0.5)
        t0 = time.time()
        for _ in range(6):
            with self.assertRaises(protectlib.ProtectError) as cm:
                c._request("GET", "/proxy/protect/api/bootstrap")
            self.assertIn("cannot reach UniFi Protect", str(cm.exception))
        self.assertLess(time.time() - t0, 2.0)


if __name__ == "__main__":
    unittest.main()
