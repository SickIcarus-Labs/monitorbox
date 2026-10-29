"""One SNMP device that stops answering must not take every worker from the others (#327)."""
import contextlib, io, json, os, sys, threading, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "snmp"))
import main as M  # noqa: E402


def req(i, host, method="check"):
    return {"id": i, "method": method, "params": {"connection": {"host": host, "port": 161}}}


class PerDeviceCap(unittest.TestCase):
    def setUp(self):
        self.gate = threading.Event()
        self.real = M.handle
        def handle(r):
            if r["params"]["connection"]["host"] == "198.51.100.1":
                self.gate.wait(10)
            return {"state": "healthy", "detail": "ok"}
        M.handle = handle
        self.addCleanup(lambda: setattr(M, "handle", self.real))
        self.addCleanup(self.gate.set)
        M._busy.clear()

    def run_in_threads(self, reqs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ts = [threading.Thread(target=M.serve, args=(r,)) for r in reqs]
            for t in ts:
                t.start()
            time.sleep(0.3)
            early = [json.loads(x) for x in buf.getvalue().splitlines()]
            self.gate.set()
            for t in ts:
                t.join(5)
        return early, [json.loads(x) for x in buf.getvalue().splitlines()]

    def test_a_third_call_to_a_hung_device_is_answered_at_once_and_other_devices_are_untouched(self):
        early, final = self.run_in_threads([req(1, "198.51.100.1"), req(2, "198.51.100.1"), req(3, "198.51.100.1"), req(4, "198.51.100.2")])
        by = {o["id"]: o for o in early}
        self.assertEqual(set(by), {3, 4}, "only the rejected call and the other device's call answered while the hung ones were stuck")
        self.assertEqual(by[3]["result"]["state"], "unknown")
        self.assertIn("still busy", by[3]["result"]["detail"])
        self.assertEqual(by[4]["result"]["state"], "healthy")
        self.assertEqual(len(final), 4)

    def test_a_rejected_non_check_call_is_an_error_not_a_result(self):
        early, _ = self.run_in_threads([req(1, "198.51.100.1", "lan_report"), req(2, "198.51.100.1", "lan_report"), req(3, "198.51.100.1", "lan_report")])
        self.assertIn("error", early[0]); self.assertEqual(early[0]["id"], 3)

    def test_the_count_goes_back_to_zero_so_the_device_works_again(self):
        self.run_in_threads([req(1, "198.51.100.1"), req(2, "198.51.100.1")])
        self.assertEqual(M._busy, {})
        self.gate.set()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            M.serve(req(9, "198.51.100.1"))
        self.assertEqual(json.loads(buf.getvalue())["result"]["state"], "healthy")


if __name__ == "__main__":
    unittest.main()
