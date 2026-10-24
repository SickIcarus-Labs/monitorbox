"""A module can say 'healthy, but worth a line' (a busy CPU): the App keeps it as a notice, never as a problem."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app.modules import Modules  # noqa: E402


class Fake:
    def __init__(self, result):
        self.result = result
    def alive(self):
        return True
    def call(self, method, params=None, timeout=5):
        return self.result


class Notice(unittest.TestCase):
    def check(self, result):
        m = Modules(None, None)
        m.running["snmp"] = Fake(result)
        return m.check({"module": "snmp", "check": "resources"}, {})

    def test_a_notice_is_healthy_with_a_flag(self):
        ok, detail, _ms, extra = self.check({"state": "healthy", "detail": "CPU 95% busy", "notice": True})
        self.assertEqual((ok, detail, extra), (True, "CPU 95% busy", {"notice": True}))

    def test_plain_healthy_and_degraded_are_as_before(self):
        self.assertEqual(self.check({"state": "healthy", "detail": "x"})[3], {})
        self.assertEqual(self.check({"state": "degraded", "detail": "x"})[3], {"warn": True})
        self.assertEqual(self.check({"state": "degraded", "detail": "x", "notice": True})[3], {"warn": True})     # a problem is never softened by a notice


if __name__ == "__main__":
    unittest.main()
