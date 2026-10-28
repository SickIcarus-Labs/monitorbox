"""The bell's notes about updates MonitorBox applied by itself. Made-up versions and module names."""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import autonotes, store


class Notes(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.paths = store.Paths(self.d.name)

    def tearDown(self):
        self.d.cleanup()

    def test_a_module_update_says_which_module_and_both_versions(self):
        autonotes.add(self.paths, "module", "widget-probe", "0.4.1", "0.4.2", 1000)
        n = autonotes.current(self.paths, "9.1.0", 1001)
        self.assertEqual([x["text"] for x in n], ["widget-probe updated itself from 0.4.1 to 0.4.2."])

    def test_the_app_note_waits_until_the_app_runs_the_new_version(self):
        autonotes.add(self.paths, "app", "MonitorBox", "9.1.0", "9.2.7", 1000)
        self.assertEqual(autonotes.current(self.paths, "9.1.0", 1001), [], "still the old version: the install has not happened (or failed)")
        self.assertEqual([x["text"] for x in autonotes.current(self.paths, "9.2.7", 1002)], ["MonitorBox updated itself from 9.1.0 to 9.2.7."])

    def test_an_app_install_that_never_happened_is_dropped_once_it_is_clear(self):
        autonotes.add(self.paths, "app", "MonitorBox", "9.1.0", "9.2.7", 1000)
        autonotes.current(self.paths, "9.3.3", 1001)                   # running something else entirely
        self.assertEqual(autonotes.current(self.paths, "9.2.7", 1002), [])

    def test_tapping_a_note_removes_only_that_note(self):
        autonotes.add(self.paths, "module", "widget-probe", "0.4.1", "0.4.2", 1000)
        autonotes.add(self.paths, "module", "gadget-feed", "1.0.0", "1.0.1", 1001)
        autonotes.dismiss(self.paths, ["module:widget-probe:0.4.2"])
        self.assertEqual([x["name"] for x in autonotes.current(self.paths, "9.1.0", 1002)], ["gadget-feed"])

    def test_notes_are_newest_first_kept_a_week_and_capped(self):
        autonotes.add(self.paths, "module", "old-one", "1", "2", 0)
        for i in range(12):
            autonotes.add(self.paths, "module", f"m{i}", "1", "2", 700000 + i)
        n = autonotes.current(self.paths, "9.1.0", 700100)
        self.assertEqual(len(n), 10)
        self.assertEqual(n[0]["name"], "m11")
        self.assertNotIn("old-one", [x["name"] for x in n])

    def test_nothing_is_said_when_nothing_happened(self):
        self.assertEqual(autonotes.current(self.paths, "9.1.0", 5), [])


if __name__ == "__main__":
    unittest.main()


class OnlyTheAutomaticPathSays(unittest.TestCase):
    """The notes are written by auto_step only; apply() (a person tapping Update) does not write one, so a hand update says nothing."""

    def fake(self, paths, applied):
        from types import SimpleNamespace
        from monitorbox_app import server
        comp = {"pin": "latest", "needsApply": True, "target": "0.4.2", "running": "0.4.1", "failed": [], "fromDefault": True}
        app_c = {"pin": "latest", "needsApply": True, "target": "9.2.7", "failed": []}
        me = SimpleNamespace(paths=paths, infos={"x": 1}, refresh=lambda: None, cfg=lambda: {"auto_check": True, "auto_update": True},
                             view=lambda: {"modules": {"widget-probe": comp}, "app": app_c},
                             apply=lambda *a: applied.append(a) or {"message": "ok"})
        me.note_update = lambda *a: server.App.note_update(me, *a)
        return server, me

    def test_automatic_updates_leave_notes(self):
        with tempfile.TemporaryDirectory() as d:
            paths, applied = store.Paths(d), []
            server, me = self.fake(paths, applied)
            self.assertEqual(autonotes.current(paths, "9.1.0", 1), [], "nothing before the automatic path runs")
            server.App.auto_step(me)
            self.assertEqual(applied, [("module", "widget-probe"), ("app",)])
            ids = sorted(n["id"] for n in autonotes._load(paths))
            self.assertEqual(ids, ["app:MonitorBox:9.2.7", "module:widget-probe:0.4.2"])

    def test_an_app_install_that_fails_leaves_no_note(self):
        with tempfile.TemporaryDirectory() as d:
            paths = store.Paths(d)
            server, me = self.fake(paths, [])
            me.apply = lambda *a: (_ for _ in ()).throw(RuntimeError("no")) if a[0] == "app" else {"message": "ok"}
            with self.assertRaises(RuntimeError):
                server.App.auto_step(me)
            self.assertEqual([n["id"] for n in autonotes._load(paths)], ["module:widget-probe:0.4.2"])

    def test_a_note_that_cannot_be_written_never_stops_an_update(self):
        from types import SimpleNamespace
        server, me = self.fake(SimpleNamespace(p=None), [])        # paths that cannot be used to write anything
        applied = []
        me.apply = lambda *a: applied.append(a) or {"message": "ok"}
        server.App.auto_step(me)
        self.assertEqual(applied, [("module", "widget-probe"), ("app",)])
