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


if __name__ == "__main__":
    unittest.main()
