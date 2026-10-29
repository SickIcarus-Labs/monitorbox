"""Automatic updating works the same on dev, beta and stable: the channel only decides what is on offer. (Owner requirement, 0.80.6.)"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from monitorbox_app import server


class AutoUpdateOnEveryChannel(unittest.TestCase):
    def step(self, channel, auto_update=True, pin="latest", failed=(), installed=True):
        app = server.App.__new__(server.App)
        app.infos = {"x": {}}          # (was app.info: the box now keeps one release answer per repository)
        done = []
        app.cfg = lambda: {"channel": channel, "auto_check": True, "auto_update": auto_update}
        app.refresh = lambda: None
        item = lambda: {"pin": pin, "needsApply": True, "target": "9.9.9", "failed": list(failed), "running": "9.0.0" if installed else None, "installed": installed, "fromDefault": True}
        app.view = lambda: {"modules": {"fake-module": item()}, "app": item()}
        app.apply = lambda kind, mid=None: done.append((kind, mid))
        app.auto_step()
        return done

    def test_dev_beta_and_stable_all_install_what_is_on_offer(self):
        for ch in ("dev", "beta", "stable"):
            self.assertEqual(self.step(ch), [("module", "fake-module"), ("app", None)], ch)

    def test_a_module_that_is_not_installed_is_never_installed_unasked(self):
        for ch in ("dev", "beta", "stable"):
            self.assertEqual(self.step(ch, installed=False), [("app", None)], ch)

    def test_it_still_leaves_alone_what_is_pinned_failed_or_switched_off(self):
        for ch in ("dev", "beta", "stable"):
            self.assertEqual(self.step(ch, auto_update=False), [], ch)
            self.assertEqual(self.step(ch, pin="0.1.0"), [], ch)
            self.assertEqual(self.step(ch, failed=["9.9.9"]), [], ch)


if __name__ == "__main__":
    unittest.main()
