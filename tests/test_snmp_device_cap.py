"""One SNMP device that stops answering must not take every worker from the others (#327)."""
import contextlib, io, json, os, sys, threading, time, unittest

import importlib.util  # noqa: E402
MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "snmp")
sys.path.insert(0, MOD)
_spec = importlib.util.spec_from_file_location("snmp_main_for_cap", os.path.join(MOD, "main.py"))     # not "import main": other modules have a main.py too
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


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
        early, final = self.run_in_threads([req(i, "198.51.100.1") for i in range(1, 6)] + [req(6, "198.51.100.2")])
        by = {o["id"]: o for o in early}
        self.assertEqual(set(by), {5, 6}, "only the rejected call and the other device's call answered while the hung ones were stuck")
        self.assertEqual(by[5]["result"]["state"], "unknown")
        self.assertIn("still busy", by[5]["result"]["detail"])
        self.assertEqual(by[6]["result"]["state"], "healthy")
        self.assertEqual(len(final), 6)

    def test_a_rejected_non_check_call_is_an_error_not_a_result(self):
        early, _ = self.run_in_threads([req(i, "198.51.100.1", "lan_report") for i in range(1, 6)])
        self.assertIn("error", early[0]); self.assertEqual(early[0]["id"], 5)

    def test_a_slow_switch_with_a_report_a_counter_read_and_a_check_in_flight_is_not_rejected(self):
        early, _ = self.run_in_threads([req(1, "198.51.100.1", "lan_report"), req(2, "198.51.100.1", "counters"), req(3, "198.51.100.1")])
        self.assertEqual(early, [], "three overlapping calls to one slow device are normal and must all be accepted")

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
