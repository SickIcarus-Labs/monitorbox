"""A module is installed when something needs it, not before (#98). Made-up repositories, nothing real."""
import os, shutil, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitorbox_app import server, modules  # noqa: E402
import test_repos as R  # noqa: E402


class InstallOnNeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-need-")
        self.main = os.path.join(self.tmp, "main")
        R.release_repo(self.main, {"alpha": [("0.1.0", R.SHA["a"])], "wol": [("0.2.0", R.SHA["b"])], "hello": [("0.3.0", R.SHA["c"])]})
        self.app = server.App(os.path.join(self.tmp, "box"), f"file://{self.main}", "dev", 0)
        self.app.reload_monitoring = lambda: None
        self.started = []
        self.app.modules.apply_one = lambda mid, ent: (self.started.append(mid), self._fake_install(mid, ent))[1]

    def _fake_install(self, mid, ent):
        st = self.app.modules.state()
        st[mid] = {"active": ent["version"], "failed": [], "sha256": ent["sha256"]}
        self.app.modules._save(st)
        return "updated"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_default_is_wake_on_lan_only(self):
        os.environ.pop("MB_ALWAYS_MODULES", None)
        self.assertEqual(modules.always(), ("wol",))

    def test_a_new_box_installs_only_the_modules_nothing_can_detect(self):
        self.app.first_run_sync()
        self.assertEqual(sorted(self.app.modules.state()), ["wol"])

    def test_needing_a_module_installs_it_once_and_a_later_need_does_not_repeat_it(self):
        self.app.refresh()
        self.app.modules.on_need("alpha")
        self.assertIn("alpha", self.app.modules.state())
        self.assertEqual(self.started.count("alpha"), 1)
        self.app.modules._ensure("alpha")
        self.assertEqual(self.started.count("alpha"), 1)

    def test_a_call_for_a_module_that_is_not_installed_installs_it_first(self):
        self.app.refresh()
        try:
            self.app.modules.call("alpha", "discover", {}, 1)
        except RuntimeError:
            pass                                    # the fake install has no process to answer; what matters is that the install was asked for
        self.assertIn("alpha", self.app.modules.state())

    def test_a_failed_install_is_not_retried_for_a_minute(self):
        self.app.refresh()
        self.app.apply = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
        for _ in range(3):
            self.app.modules._ensure("alpha")
        self.assertEqual(self.app.modules.install_tried.get("alpha") is not None, True)
        calls = []
        self.app.modules.on_need = lambda mid: calls.append(mid)
        self.app.modules._ensure("alpha")
        self.assertEqual(calls, [], "tried a moment ago, so not again yet")

    def test_the_sample_module_is_never_installed_for_a_need_off_dev(self):
        self.app.refresh()
        from monitorbox_app import updates
        updates.set_update_cfg(self.app.paths, channel="beta")
        self.app.install_needed("hello")
        self.assertNotIn("hello", self.app.modules.state())

    def test_an_uninstalled_module_comes_back_when_a_device_of_its_kind_is_added(self):
        self.app.refresh()
        st = self.app.modules.state(); st["alpha"] = {"active": "0.1.0", "failed": [], "sha256": R.SHA["a"]}; self.app.modules._save(st)
        self.app.uninstall("alpha")
        self.assertIn("alpha", self.app.cfg()["uninstalled"])
        self.app.install_needed("alpha")
        self.assertIn("alpha", self.app.modules.state())
        self.assertNotIn("alpha", self.app.cfg()["uninstalled"])


if __name__ == "__main__":
    unittest.main()
