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


class StartedOnce(unittest.TestCase):
    """#334: at every restart the LAN sampler (or the graphs) asked for a module before the start-up batch got to it, started its
    own copy, and the batch then started it again and stopped the first, so its checks blinked Unknown. Each module starts once."""
    def test_a_call_while_the_batch_is_starting_it_waits_and_the_module_starts_once(self):
        import threading, time
        m = Fake({"unifi-network": {"active": "1"}})
        real = m._start

        def slow(mid, version):
            time.sleep(0.3)
            real(mid, version)
        m._start = slow
        m.mark_starting()                                   # as the app does, before anything runs
        got = []
        early = threading.Thread(target=lambda: got.append(m.call("unifi-network", "status", {})), name="lansampler")
        early.start()                                       # asks before the batch has launched it
        time.sleep(0.05)
        m.start_all()
        early.join(5)
        self.assertEqual(m.started, ["unifi-network"], "started once, by the batch")
        self.assertEqual(got, [{"state": "healthy", "detail": "ok"}], "the early caller got its answer once the module was up")

    def test_the_batch_leaves_a_module_alone_that_is_already_running(self):
        m = Fake({"snmp": {"active": "1"}})
        m._start("snmp", "1")                               # already up, started on demand
        m.start_all()
        self.assertEqual(m.started, ["snmp"])


class ShuttingDown(unittest.TestCase):
    def test_a_module_stopped_for_a_restart_is_not_started_again(self):
        """At every update the log said "snmp stopped unexpectedly; starting it again": a graph still finishing found the module
        the app had just stopped and started a fresh copy. Once the app is closing, nothing is started again."""
        m = Fake({"snmp": {"active": "1"}})
        m.start_all()
        m.stop_all = modules.Modules.stop_all.__get__(m)
        m.running["snmp"].stop = lambda: None
        m.stop_all()
        m.running["snmp"].alive = lambda: False
        self.assertIsNone(m._revive("snmp"))
        self.assertEqual(m.started, ["snmp"], "not started a second time")


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
