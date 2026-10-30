"""One SNMP device must not take workers from the others (#327), and a device with many checks must not have its own refused (#330)."""
import contextlib, io, json, os, sys, threading, time, unittest

import importlib.util  # noqa: E402
MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "snmp")
sys.path.insert(0, MOD)
_spec = importlib.util.spec_from_file_location("snmp_main_for_cap", os.path.join(MOD, "main.py"))     # not "import main": other modules have a main.py too
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

HUNG, OTHER = "198.51.100.1", "198.51.100.2"


def req(i, host, method="check"):
    return {"id": i, "method": method, "params": {"connection": {"host": host, "port": 161}}}


class PerDevice(unittest.TestCase):
    def setUp(self):
        self.gate = threading.Event()
        self.real, self.wait = M.handle, M.WAIT
        def handle(r):
            if r["params"]["connection"]["host"] == HUNG:
                self.gate.wait(10)
            return {"state": "healthy", "detail": "ok"}
        M.handle = handle
        M._pools.clear(); M._pending.clear(); M._queued.clear()
        self.addCleanup(self.restore)

    def restore(self):
        self.gate.set()                                    # a stuck call from this test must finish before the next test redirects the output
        with contextlib.redirect_stdout(io.StringIO()):
            M.reap()
            for _ in range(100):
                if not M._pending: break
                time.sleep(0.05)
        M.handle, M.WAIT = self.real, self.wait

    def out(self, buf):
        return [json.loads(x) for x in buf.getvalue().splitlines()]

    def test_forty_checks_sent_at_once_to_one_device_all_get_a_real_answer_none_are_refused(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for i in range(40):
                M.dispatch(req(i, OTHER))
            for _ in range(100):
                if len(self.out(buf)) == 40: break
                time.sleep(0.05)
        got = self.out(buf)
        self.assertEqual(len(got), 40)
        self.assertEqual({o["result"]["state"] for o in got}, {"healthy"}, "every check was answered by the device, none turned away as busy")

    def test_no_more_than_four_calls_run_at_once_for_one_device(self):
        running, peak, lock = [0], [0], threading.Lock()
        def handle(r):
            with lock:
                running[0] += 1; peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1
            return {"state": "healthy", "detail": "ok"}
        M.handle = handle
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for i in range(20):
                M.dispatch(req(i, OTHER))
            for _ in range(100):
                if len(self.out(buf)) == 20: break
                time.sleep(0.05)
        self.assertEqual(len(self.out(buf)), 20)
        self.assertLessEqual(peak[0], M.PER_DEVICE)

    def test_a_hung_device_answers_busy_after_the_wait_and_another_device_is_untouched(self):
        M.WAIT = 0.4
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for i in range(1, 9):
                M.dispatch(req(i, HUNG))                    # four stuck, four waiting
            M.dispatch(req(9, OTHER))
            time.sleep(0.2); M.reap()
            early = {o["id"]: o for o in self.out(buf)}
            self.assertEqual(set(early), {9}, "the waiting calls are not answered before the wait is up; the other device is not held up")
            time.sleep(0.5); M.reap()
            late = {o["id"]: o for o in self.out(buf)}
            self.assertEqual({5, 6, 7, 8} | {9}, set(late), "after the wait the waiting calls are answered busy")
            for i in (5, 6, 7, 8):
                self.assertEqual(late[i]["result"]["state"], "unknown"); self.assertIn("still busy", late[i]["result"]["detail"])
            self.gate.set(); time.sleep(0.3)
            self.assertEqual(sorted(o["id"] for o in self.out(buf)), list(range(1, 10)), "each call answered exactly once")

    def test_a_non_check_call_that_waited_too_long_is_an_error_not_a_result(self):
        M.WAIT = 0.2
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for i in range(1, 6):
                M.dispatch(req(i, HUNG, "lan_report"))
            time.sleep(0.3); M.reap()
            got = self.out(buf)
        self.assertEqual(got[0]["id"], 5); self.assertIn("error", got[0])

    def test_a_queue_that_is_far_too_long_is_refused_at_once(self):
        M.MAX_QUEUE = 6
        self.addCleanup(lambda: setattr(M, "MAX_QUEUE", 300))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for i in range(1, 9):
                M.dispatch(req(i, HUNG))
            got = self.out(buf)
        self.assertEqual(sorted(o["id"] for o in got), [7, 8])

    def test_the_counts_go_back_to_zero_so_the_device_works_again(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            M.dispatch(req(1, OTHER))
            for _ in range(100):
                if self.out(buf): break
                time.sleep(0.05)
        time.sleep(0.1)
        self.assertEqual(M._pending, {})


if __name__ == "__main__":
    unittest.main()
