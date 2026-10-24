"""Modules.describe feeds the Settings page: busy modules must not make it wait, and a card is asked for once."""
import os, sys, threading, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from monitorbox_app import modules  # noqa: E402


class Proc:
    def __init__(self, delay, calls):
        self.delay, self.calls = delay, calls
    def alive(self): return True
    proc = type("X", (), {"pid": 1})()
    def call(self, method, params=None, timeout=5):
        self.calls.append(method)
        if self.delay > timeout:                 # a module in the middle of a long check answers after the caller gave up
            time.sleep(timeout); raise TimeoutError("did not answer describe")
        time.sleep(self.delay)
        return {"title": "T-" + str(id(self) % 97), "status": "healthy"}


class Fake(modules.Modules):
    def __init__(self, st, procs):
        self.running, self.cards, self._st = procs, {}, st
    def state(self): return self._st


class Describe(unittest.TestCase):
    def test_busy_modules_are_asked_together_and_do_not_hold_the_page_for_5_seconds_each(self):
        calls = []
        m = Fake({k: {"active": "1"} for k in ("a-busy", "b-busy", "c-busy", "d-fast")},
                 {"a-busy": Proc(30, calls), "b-busy": Proc(30, calls), "c-busy": Proc(30, calls), "d-fast": Proc(0, calls)})
        t = time.monotonic(); res = m.describe(); took = time.monotonic() - t
        self.assertLess(took, 3.5, f"three busy modules were asked one after another ({took:.1f} s)")
        by = {r["id"]: r for r in res}
        self.assertIsNotNone(by["d-fast"]["card"], "the fast module's card is there"); self.assertIsNone(by["a-busy"]["card"])
        self.assertTrue(by["a-busy"]["error"] and by["a-busy"]["running"], "a busy module is running, just late: it says so")

    def test_a_card_is_asked_for_once_per_version(self):
        calls = []
        m = Fake({"snmp": {"active": "1"}}, {"snmp": Proc(0, calls)})
        first = m.describe()[0]["card"]
        self.assertEqual(m.describe()[0]["card"], first); self.assertEqual(len(calls), 1, "the second look used the kept card")
        m._st = {"snmp": {"active": "2"}}; m.describe()
        self.assertEqual(len(calls), 2, "a new version is asked again")


if __name__ == "__main__":
    unittest.main()
