import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from monitorbox_app import modules  # noqa: E402


class Fake(modules.Modules):
    def __init__(self, st):
        self.paths = None
        self.running, self.last_try, self.retry_after, self.cards = {}, {}, 0.0, {}
        import threading
        self.lock = threading.Lock()
        self.wanted = lambda: None
        self._st, self.started = st, []
        self.starting, self.boot = set(), 0.0       # the module list now also remembers which modules are coming up (a stand-in class, so it is set here)

    def state(self): return self._st
    def _save(self, st): pass

    def _start(self, mid, version):
        self.started.append(mid)
        class P:
            def alive(s): return True
            def call(s, *a, **k): return {"state": "healthy", "detail": "ok"}
        self.running[mid] = P()


class Together(unittest.TestCase):
    """The modules the app starts are started all at once, and a check for one that is still coming up waits instead of reporting it as not running."""
    def test_slow_modules_start_together_not_one_after_another(self):
        import time
        m = Fake({"a": {"active": "1"}, "b": {"active": "1"}, "c": {"active": "1"}})

        def slow(mid, version):
            time.sleep(0.4)
            m.started.append(mid)
            m.running[mid] = type("P", (), {"alive": lambda s: True})()
        m._start = slow
        t0 = time.monotonic()
        m.start_all()
        self.assertEqual(sorted(m.started), ["a", "b", "c"])
        self.assertLess(time.monotonic() - t0, 0.9, "three 0.4 s starts took about one, not three")
        self.assertEqual(m.starting, set(), "nothing is 'starting' once they are up")

    def test_a_check_for_a_module_that_is_coming_up_waits_and_a_failed_start_is_then_reported(self):
        m = Fake({"snmp": {"active": "1"}})
        m.mark_starting()
        self.assertEqual(m.starting, {"snmp"})
        got = m.check({"module": "snmp", "check": "x"}, {})
        self.assertEqual((got[0], got[3]), (None, {"starting": True}))
        self.assertIn("starting", got[1])
        m.starting.discard("snmp")                     # its start failed or finished: now a missing module is reported as before
        m._revive = lambda mid: None
        got = m.check({"module": "snmp", "check": "x"}, {})
        self.assertEqual((got[0], got[1], got[3]), (None, "the snmp module is not running", {}))
        m.starting.add("snmp"); m.boot = -1e9           # still "starting" long after boot: it must not wait forever
        self.assertIn("not running", m.check({"module": "snmp", "check": "x"}, {})[1])


    def test_no_more_than_a_few_modules_start_at_the_same_time(self):
        import threading, time
        m = Fake({f"m{i}": {"active": "1"} for i in range(8)})
        now, peak, lock = [0], [0], threading.Lock()

        def slow(mid, version):
            with lock:
                now[0] += 1; peak[0] = max(peak[0], now[0])
            time.sleep(0.15)
            with lock:
                now[0] -= 1
            m.running[mid] = type("P", (), {"alive": lambda s: True})()
        m._start = slow
        m.start_all()
        self.assertEqual(len(m.running), 8)
        self.assertGreater(peak[0], 1, "together, not one by one")
        self.assertLessEqual(peak[0], modules.START_AT_ONCE, "but not all eight at once (CI starved them on a small runner, #1.4.0)")


class LazyStart(unittest.TestCase):
    def setUp(self):
        self.m = Fake({"snmp": {"active": "1"}, "scrypted": {"active": "1"}, "wol": {"active": "1"}})

    def test_only_modules_a_connection_uses_start_with_the_app(self):
        self.m.wanted = lambda: {"snmp"}
        self.m.start_all()
        self.assertEqual(self.m.started, ["snmp"])

    def test_an_idle_module_starts_when_first_asked(self):
        self.m.wanted = lambda: {"snmp"}
        self.m.start_all()
        ok, *_ = self.m.check({"module": "wol", "check": "x"}, {})
        self.assertTrue(ok)
        self.assertEqual(self.m.started, ["snmp", "wol"])
        self.assertIsNotNone(self.m.call("scrypted", "describe", {}))
        self.assertIn("scrypted", self.m.started)

    def test_unreadable_config_starts_everything(self):
        self.m.start_all()
        self.assertEqual(sorted(self.m.started), ["scrypted", "snmp", "wol"])


if __name__ == "__main__":
    unittest.main()
