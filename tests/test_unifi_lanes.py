"""UniFi module under a slow console (tracker #339). 2026-11-14 10:24: slow flow searches took all four of the module's threads, every UniFi check
timed out and ~20 items went Unknown for four minutes. These run the real module process against the fake controller, the way the App does."""
import json, os, subprocess, sys, tempfile, threading, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
MOD = os.path.join(os.path.dirname(HERE), "modules", "unifi-network")
sys.path.insert(0, MOD)
from unifi_fake import Controller  # noqa: E402
import unifilib as U  # noqa: E402
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("unifi_main_lanes", os.path.join(MOD, "main.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
from monitorbox_app import server as S  # noqa: E402


def flow(n):
    now = int(time.time() * 1000)
    return {"flow_start_time": now - 5000, "flow_end_time": now - 1000, "direction": "outgoing", "service": "HTTPS",
            "source": {"ip": "192.168.77.115", "mac": "aa:bb:cc:da:8c:22", "client_name": "Fake Speaker"},
            "destination": {"ip": "203.0.113.50", "domains": [f"cdn{n}.example.test"]}, "traffic_data": {"bytes_rx": 1000, "bytes_tx": 100}}


def slow_search(per_page, ctl):
    """A flow log that never ends, each page taking per_page seconds: the worst a busy console does."""
    def search(body):
        ctl.searches = getattr(ctl, "searches", 0) + (body["pageNumber"] == 0)
        time.sleep(per_page)
        return (200, {"data": [flow(body["pageNumber"])], "has_next": True})
    return search


class Module:
    """The module as its own process, spoken to in JSON lines like the App does."""
    def __init__(self):
        self.p = subprocess.Popen([sys.executable, "main.py"], cwd=MOD, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.answers, self.n, self.lock = {}, 0, threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            msg = json.loads(line)
            self.answers[msg["id"]] = (time.monotonic(), msg)

    def send(self, method, params, timeout):
        with self.lock:
            self.n += 1
            self.p.stdin.write(json.dumps({"id": self.n, "method": method, "params": params, "timeout": timeout}) + "\n")
            self.p.stdin.flush()
            return self.n, time.monotonic()

    def wait(self, i, within):
        end = time.monotonic() + within
        while time.monotonic() < end:
            if i in self.answers:
                return self.answers[i]
            time.sleep(0.05)
        return None

    def close(self):
        self.p.stdin.close()
        self.p.kill()
        self.p.wait(5)


class SlowConsole(unittest.TestCase):
    def setUp(self):
        self.c = Controller()
        self.addCleanup(self.c.close)
        self.conn = self.c.conn(timeout=3)
        self.m = Module()
        self.addCleanup(self.m.close)

    def test_slow_flow_searches_never_starve_the_device_checks(self):
        self.c.flows = {"traffic": {}, "search": slow_search(2.5, self.c)}
        # more slow questions than the old pool had threads, each for a different window (no sharing), as the background loop, a side panel and the
        # Busiest client can ask
        flows = [self.m.send("flows", {"connection": self.conn, "seconds": 60 * (k + 1)}, 8) for k in range(6)]
        time.sleep(0.5)
        checks = [self.m.send("check", {"check": "device", "params": {"name": "Garage"}, "connection": self.conn}, 5) for _ in range(6)]
        for i, t0 in checks:
            got = self.m.wait(i, 4)
            self.assertIsNotNone(got, "a check answered while the flow log was busy")
            self.assertLess(got[0] - t0, 3)
            self.assertEqual(got[1]["result"]["state"], "healthy")
        busy = [self.m.wait(i, 1) for i, _ in flows[4:]]
        self.assertTrue(all(b and "busy" in b[1].get("error", "") for b in busy), "past one running and three waiting, a slow question is turned away at once")

    def test_a_flow_search_stops_in_time_and_says_what_it_has(self):
        self.c.flows = {"traffic": {}, "search": slow_search(1.0, self.c)}          # ten pages would take ten seconds
        i, t0 = self.m.send("flows", {"connection": self.conn, "seconds": 60}, 6)
        got = self.m.wait(i, 7)
        self.assertIsNotNone(got, "answered before the App stopped waiting")
        self.assertLess(got[0] - t0, 6)
        res = got[1]["result"]
        self.assertTrue(res.get("partial"))
        self.assertGreater(len(res["flows"]), 0, "the newest flows it had read")
        self.assertIn("took", got[1], "says how long it queued and ran")

    def test_the_same_question_asked_twice_is_asked_of_the_console_once(self):
        self.c.flows = {"traffic": {}, "search": lambda body: (time.sleep(0.5), (200, {"data": [flow(1)], "has_next": False}))[1]}
        a, _ = self.m.send("flows", {"connection": self.conn, "seconds": 60}, 10)
        b, _ = self.m.send("flows", {"connection": self.conn, "seconds": 60}, 10)
        ra, rb = self.m.wait(a, 5), self.m.wait(b, 5)
        self.assertTrue(ra and rb)
        self.assertEqual(ra[1]["result"], rb[1]["result"])
        posts = [r for r in self.c.requests if r == ("POST", "/proxy/network/v2/api/site/default/traffic-flows")]
        self.assertEqual(len(posts), 1)

    def test_work_nobody_is_waiting_for_any_more_is_not_done(self):
        self.c.flows = {"traffic": {}, "search": slow_search(2.0, self.c)}
        self.m.send("flows", {"connection": self.conn, "seconds": 60}, 3)           # runs, then gives up
        self.m.send("flows", {"connection": self.conn, "seconds": 120}, 1)          # waits behind it, past its own deadline
        time.sleep(5)
        self.assertEqual(self.c.searches, 1, "the question whose asker had gone was never sent to the console")


class FastFail(unittest.TestCase):
    def test_a_slow_flow_page_does_not_make_the_device_checks_read_unreachable(self):
        c = Controller()
        self.addCleanup(c.close)
        M.CLIENTS.clear()
        U.CACHE_SECONDS = 0
        conn = c.conn(timeout=1)
        self.assertEqual(M.run_check("device", {"name": "Garage"}, conn)["state"], "healthy")
        c.flows = {"traffic": {}, "search": lambda body: (time.sleep(2), (200, {"data": [], "has_next": False}))[1]}
        with self.assertRaises(U.UnifiError):
            M.handle({"method": "flows", "params": {"connection": conn, "seconds": 60}})
        self.assertEqual(M.run_check("device", {"name": "Garage"}, conn)["state"], "healthy", "the status reads still work, so they still answer")
        c.close()
        check = {"method": "check", "params": {"check": "device", "params": {"name": "Garage"}, "connection": conn}}
        self.assertEqual(M.answer(check)["result"]["state"], "unknown")
        t0 = time.monotonic()
        self.assertEqual(M.answer(check)["result"]["state"], "unknown")
        self.assertLess(time.monotonic() - t0, 0.5, "a status read that cannot reach the console still makes the next ones fail at once")


class AppSide(unittest.TestCase):
    CONN = {"id": "u", "module": "unifi-network", "host": "192.0.2.1"}

    def fake(self, call):
        app = mock.Mock()
        app.gw_cache, app.paths = {}, None
        app.modules.call = call
        return app

    def test_the_flow_log_is_asked_once_for_everyone_who_wants_it_at_the_same_time(self):
        calls = []
        def call(mid, method, params, timeout):
            calls.append(method)
            time.sleep(0.5)
            return {"flows": [{"n": 1}]}
        app = self.fake(call)
        out = []
        with mock.patch.object(S.monconfig, "load_config", return_value={"connections": [self.CONN]}):
            ts = [threading.Thread(target=lambda: out.append(S.App.flow_rows(app, 60))) for _ in range(3)]
            [t.start() for t in ts]
            [t.join(5) for t in ts]
        self.assertEqual(calls, ["flows"])
        self.assertEqual([o["rows"] for o in out], [[{"n": 1}]] * 3)

    def test_after_the_flow_log_times_out_the_side_panel_does_not_wait_again_for_usage(self):
        def call(mid, method, params, timeout):
            raise TimeoutError("unifi-network did not answer flows")
        app = self.fake(call)
        with mock.patch.object(S.monconfig, "load_config", return_value={"connections": [self.CONN]}):
            fr = S.App.flow_rows(app, 300)
        self.assertTrue(fr["timed_out"])
        with tempfile.TemporaryDirectory() as d:
            app.graphs_file = os.path.join(d, "graphs.json")
            with open(app.graphs_file, "w") as f:
                json.dump([{"id": "wan", "connection": "u"}], f)
            app.last_map = {"nodes": []}
            app.flow_rows = lambda win: fr
            app.flow_entries = S.App.flow_entries
            with mock.patch.object(S.monconfig, "load_config", return_value={"connections": [self.CONN]}):
                res = S.App.lan_flows(app, "wan", 300)
        app.gateway_usage.assert_not_called()
        self.assertIn("did not answer", res["why"])


if __name__ == "__main__":
    unittest.main()
