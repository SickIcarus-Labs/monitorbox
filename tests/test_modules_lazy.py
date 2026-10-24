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

    def state(self): return self._st
    def _save(self, st): pass

    def _start(self, mid, version):
        self.started.append(mid)
        class P:
            def alive(s): return True
            def call(s, *a, **k): return {"state": "healthy", "detail": "ok"}
        self.running[mid] = P()


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
