"""Uninstalling a module and removing a repository together with its modules (#266, part of #264).
Every secret below is made up and different from every other, and each is looked for after the round trip."""
import json, os, shutil, sys, tarfile, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitorbox_app import server, updates, monconfig, backups  # noqa: E402
import test_repos as R  # noqa: E402


class Uninstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-un-")
        self.main, self.test = os.path.join(self.tmp, "main"), os.path.join(self.tmp, "test")
        R.release_repo(self.main, {"alpha": [("0.1.0", R.SHA["a"])], "bravo": [("0.2.0", R.SHA["b"])]})
        R.release_repo(self.test, {"hello": [("0.3.0", R.SHA["c"])], "extra": [("1.0.0", R.SHA["d"])]})
        self.app = server.App(os.path.join(self.tmp, "box"), f"file://{self.main}", "dev", 0)
        self.app.reload_monitoring = lambda: None
        self.rid = "owner/test-repo"
        updates.set_update_cfg(self.app.paths, repos=[{"id": self.rid, "name": self.rid, "url": f"file://{self.test}", "enabled": True}])
        self.stopped = []
        m = self.app.modules
        orig = m.uninstall
        m.uninstall = lambda mid: (self.stopped.append(mid), orig(mid))[1]
        os.makedirs(os.path.join(self.app.paths.root, "data", "app"), exist_ok=True)
        R.put(os.path.join(self.app.paths.root, "data", "app", "auth.json"), {"x": 1})      # a backup needs the sign-in file to exist

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, mid, ver, sha, source):
        st = self.app.modules.state()
        st[mid] = {"active": ver, "failed": [], "sha256": sha}
        self.app.modules._save(st)
        d = self.app.modules.dir(mid, ver)
        os.makedirs(d, exist_ok=True)
        R.put(os.path.join(d, "manifest.json"), {"id": mid, "version": ver})
        cfg = self.app.cfg()
        updates.set_update_cfg(self.app.paths, module_sources={**cfg["module_sources"], mid: source}, module_pins={**cfg["module_pins"], mid: "latest"})

    def connections(self, conns):
        raw = {"schema": 4}
        if os.path.exists(self.app.paths.config):
            with open(self.app.paths.config) as f:
                raw = json.load(f)
        raw["connections"] = conns
        R.put(self.app.paths.config, raw)

    # -- one module ----------------------------------------------------------
    def test_uninstall_removes_the_module_its_files_its_choices_and_remembers_it_was_declined(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        out = self.app.uninstall("hello")
        self.assertIn("uninstalled", out["message"])
        self.assertNotIn("hello", self.app.modules.state())
        self.assertFalse(os.path.exists(os.path.join(self.app.paths.module_releases, "hello")))
        cfg = self.app.cfg()
        self.assertNotIn("hello", cfg["module_pins"])
        self.assertNotIn("hello", cfg["module_sources"])
        self.assertEqual(cfg["uninstalled"], ["hello"])
        self.assertEqual(self.stopped, ["hello"])
        with self.assertRaises(ValueError):
            self.app.uninstall("hello")                             # twice

    def test_only_that_modules_connections_go_and_each_other_connection_keeps_its_own_secret(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        self.install("alpha", "0.1.0", R.SHA["a"], "default")
        self.connections([{"id": "hello-1", "module": "hello", "token": "fake-token-1111"},
                          {"id": "hello-2", "module": "hello", "token": "fake-token-2222"},
                          {"id": "alpha-1", "module": "alpha", "token": "fake-token-3333"},
                          {"id": "alpha-2", "module": "alpha", "token": "fake-token-4444"}])
        self.assertEqual(self.app.module_connections("hello"), ["hello-1", "hello-2"])
        out = self.app.uninstall("hello")
        self.assertIn("2 connections", out["message"])
        left = {c["id"]: c["token"] for c in monconfig.load_config(self.app.paths)["connections"]}
        self.assertEqual(left, {"alpha-1": "fake-token-3333", "alpha-2": "fake-token-4444"})
        self.assertIn("alpha", self.app.modules.state())

    def test_a_backup_asked_for_is_made_first_and_holds_what_is_about_to_go(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        self.connections([{"id": "hello-1", "module": "hello", "token": "fake-token-5555"}])
        self.app.uninstall("hello", backup="config")
        d = os.path.join(self.app.paths.root, "backups")
        names = [n for n in os.listdir(d) if n.endswith(".tgz")]
        self.assertEqual(len(names), 1)
        with tarfile.open(os.path.join(d, names[0])) as tf:
            body = b"".join(tf.extractfile(m).read() for m in tf.getmembers() if m.isfile() and m.name.endswith("monitorbox.json"))
        self.assertIn(b"fake-token-5555", body)                      # taken before the connection was deleted
        self.assertEqual(self.app.module_connections("hello"), [])

    def test_if_the_backup_cannot_be_made_nothing_is_deleted(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        self.connections([{"id": "hello-1", "module": "hello", "token": "fake-token-6666"}])
        real = backups.lib
        backups.lib = lambda: (_ for _ in ()).throw(ValueError("no backups here"))
        try:
            with self.assertRaises(ValueError):
                self.app.uninstall("hello", backup="full")
        finally:
            backups.lib = real
        self.assertIn("hello", self.app.modules.state())
        self.assertEqual(self.app.module_connections("hello"), ["hello-1"])

    def test_bad_backup_choice_is_refused(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        with self.assertRaises(ValueError):
            self.app.uninstall("hello", backup="everything")
        self.assertIn("hello", self.app.modules.state())

    # -- a repository with modules ----------------------------------------------
    def test_removing_a_repo_with_modules_asks_for_the_uninstall_and_then_removes_both(self):
        self.install("hello", "0.3.0", R.SHA["c"], self.rid)
        self.install("extra", "1.0.0", R.SHA["d"], self.rid)
        self.install("alpha", "0.1.0", R.SHA["a"], "default")
        with self.assertRaises(ValueError) as cm:
            self.app.remove_repo(self.rid)
        self.assertIn("uninstalls them", str(cm.exception))
        self.assertIn("hello", self.app.modules.state())             # nothing happened
        out = self.app.remove_repo(self.rid, uninstall=True, backup="config")
        self.assertIn("extra, hello", out["message"])
        self.assertEqual(sorted(self.app.modules.state()), ["alpha"])
        self.assertEqual([r["id"] for r in self.app.repos()], ["default"])
        names = [n for n in os.listdir(os.path.join(self.app.paths.root, "backups")) if n.endswith(".tgz")]
        self.assertEqual(len(names), 1)                              # one backup for the whole removal, not one per module

    def test_removing_an_empty_repo_needs_no_uninstall(self):
        self.app.remove_repo(self.rid)
        self.assertEqual([r["id"] for r in self.app.repos()], ["default"])

    # -- an uninstalled module stays uninstalled -----------------------------------
    def test_an_uninstalled_default_module_is_not_brought_back_by_updates_or_a_restart(self):
        self.install("alpha", "0.1.0", R.SHA["a"], "default")
        self.app.uninstall("alpha")
        self.app.refresh()
        c = self.app.view()["modules"]["alpha"]
        self.assertTrue(c["declined"])
        self.assertIsNone(c["running"])
        applied = []
        self.app.apply = lambda kind, mid=None: applied.append(mid)
        updates.set_update_cfg(self.app.paths, auto_update=True, auto_check=True)
        real_refresh, self.app.refresh = self.app.refresh, lambda: None
        self.app.auto_step()
        self.app.apply_all()
        self.assertNotIn("alpha", applied)
        self.assertIn("bravo", applied)                               # others still come as before
        installed = []
        self.app.modules.apply_one = lambda mid, ent: installed.append(mid) or "updated"
        self.app.refresh = real_refresh
        self.app.first_run_sync()
        self.assertNotIn("alpha", installed)

    def test_installing_it_again_by_hand_clears_the_mark(self):
        self.install("alpha", "0.1.0", R.SHA["a"], "default")
        self.app.uninstall("alpha")
        self.app.refresh()
        self.app.modules.apply_one = lambda mid, ent: "updated"
        self.app.apply("module", "alpha")
        self.assertEqual(self.app.cfg()["uninstalled"], [])


if __name__ == "__main__":
    unittest.main()


class DevOnly(unittest.TestCase):
    """The sample module belongs to the dev channel only: leaving dev removes it, and going back to dev brings it back (not "declined")."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-dev-")
        self.main = os.path.join(self.tmp, "main")
        R.release_repo(self.main, {"alpha": [("0.1.0", R.SHA["a"])], "hello": [("0.3.0", R.SHA["c"])]})
        self.app = server.App(os.path.join(self.tmp, "box"), f"file://{self.main}", "dev", 0)
        self.app.reload_monitoring = lambda: None
        for mid, ver, sha in (("hello", "0.3.0", R.SHA["c"]), ("alpha", "0.1.0", R.SHA["a"])):
            st = self.app.modules.state()
            st[mid] = {"active": ver, "failed": [], "sha256": sha}
            self.app.modules._save(st)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dev_keeps_hello(self):
        self.assertEqual(self.app.drop_dev_only(), [])
        self.assertIn("hello", self.app.modules.state())

    def test_beta_and_stable_remove_hello_only_and_do_not_mark_it_declined(self):
        for ch in ("beta", "stable"):
            st = self.app.modules.state()
            st["hello"] = {"active": "0.3.0", "failed": [], "sha256": R.SHA["c"]}
            self.app.modules._save(st)
            updates.set_update_cfg(self.app.paths, channel=ch)
            self.assertEqual(self.app.drop_dev_only(), ["hello"], ch)
            self.assertNotIn("hello", self.app.modules.state())
            self.assertIn("alpha", self.app.modules.state())
            self.assertEqual(self.app.cfg()["uninstalled"], [], ch)
            self.assertEqual(self.app.drop_dev_only(), [], ch)               # nothing left to remove
