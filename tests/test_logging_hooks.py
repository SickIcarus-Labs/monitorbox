"""Where the log meets the rest of the App: the bell, alerts, checks, backups and the page's data. Every value here is made up and different."""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
os.environ.setdefault("MB_LAUNCHER_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "launcher"))
from monitorbox_app import alerts, applog, autonotes, backups, engine, store  # noqa: E402


class Clock:
    t = 1_800_000_000.0
    def __call__(self): return self.t


class Hooks(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.addCleanup(self.d.cleanup)
        self.paths = store.Paths(self.d.name)
        self.log = applog.setup(os.path.join(self.d.name, "logs"), "9.9.9", "dev")
        self.addCleanup(lambda: setattr(applog, "_log", None))

    def texts(self, **k):
        return [r["text"] for r in self.log.entries(**k)]

    def test_the_start_line_names_the_build(self):
        self.assertTrue(any("9.9.9" in t and "dev" in t for t in self.texts()))

    def test_an_error_puts_one_note_on_the_bell_with_a_link_and_the_same_trouble_does_not_pile_up(self):
        self.log.on_error = lambda s, t: autonotes.add_problem(self.paths, s, t, 1000)
        applog.error("modules", "widget-probe did not start")
        applog.error("modules", "widget-probe did not start")
        applog.warning("checks", "a monitored thing failing is not the App's trouble")
        n = autonotes.current(self.paths, "9.9.9", 1001)
        self.assertEqual([x["text"] for x in n], ["widget-probe did not start"])
        self.assertEqual(n[0]["kind"], "problem")
        self.assertEqual(n[0]["go"], "#/logs?source=modules&level=error")
        autonotes.dismiss(self.paths, [n[0]["id"]])
        self.assertEqual(autonotes.current(self.paths, "9.9.9", 1002), [])

    def test_a_broken_bell_callback_never_stops_the_log(self):
        def boom(s, t): raise RuntimeError("x")
        self.log.on_error = boom
        applog.error("alerts", "gave up")
        self.assertIn("gave up", self.texts())

    def test_a_failed_then_delivered_alert_is_logged_without_the_address_path(self):
        d = tempfile.mkdtemp(); now = [1000.0]; fail = ["nothing is listening"]
        a = alerts.Alerts(os.path.join(d, "a.json"), os.path.join(d, "s.json"), lambda: None,
                          send=lambda url, ev: fail[0], clock=lambda: now[0], hostname=lambda: "box-host")
        a.set({"enabled": True, "homeAssistant": {"webhook": "http://ha.example.invalid:8123/api/webhook/fake-secret-path-7"}, "delaySeconds": 60})
        nodes = [{"id": "a", "name": "Anchor3", "group": "G", "critical": False, "checks": [{"id": "c", "type": "ping", "target": "x"}], "rule": "primary", "dependsOn": []}]
        bad = engine.evaluate(nodes, {"a/c": {"ok": False, "detail": "no answer", "ms": 1, "at": "t", "since": "t"}}, "t")
        a.observe(bad, now[0]); now[0] += 61; a.observe(bad, now[0]); a.flush(now[0])
        fail[0] = None; now[0] += 30; a.flush(now[0])
        text = self.log.download()
        self.assertIn("Not delivered", text)
        self.assertIn("Sent:", text)
        self.assertNotIn("fake-secret-path-7", text)

    def test_the_weekly_full_backup_carries_the_normal_log_and_never_the_debug_log(self):
        self.log.set_debug(True)
        applog.info("app", "line for the backup")
        applog.debug("app", "debug detail that stays out")
        backups.copy_log(self.d.name)
        copy = os.path.join(self.d.name, "data", "app", "log-copy")
        self.assertEqual(os.listdir(copy), ["mb.log"])
        self.assertIn("line for the backup", open(os.path.join(copy, "mb.log")).read())
        self.assertNotIn("debug detail", open(os.path.join(copy, "mb.log")).read())

    def test_a_real_full_backup_holds_the_log_and_a_settings_backup_does_not(self):
        os.makedirs(os.path.join(self.d.name, "config"))
        open(os.path.join(self.d.name, "config", "monitorbox.json"), "w").write("{}")
        applog.info("app", "line that must travel")
        b = backups.lib()
        import tarfile
        def names(kind):
            n = b.create(self.d.name, kind, "test", app_version="9.9.9")
            with tarfile.open(os.path.join(self.d.name, "backups", n)) as tf:
                return tf.getnames()
        self.assertIn("data/app/log-copy/mb.log", names("full"))
        self.assertFalse([x for x in names("config") if "log" in x])


if __name__ == "__main__":
    unittest.main()


class CallLines(unittest.TestCase):
    def test_a_debug_call_line_names_the_device_but_never_its_address_or_login(self):
        from monitorbox_app import modules
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        log = applog.setup(os.path.join(d.name, "logs"), "9.9.9", "dev"); self.addCleanup(lambda: setattr(applog, "_log", None))
        log.set_debug(True)
        import threading

        class M(modules.Modules):
            def __init__(self):
                self.running, self.cards = {}, {}
                self.lock = threading.Lock(); self.on_need = None
                self.running["snmp"] = type("P", (), {"alive": lambda s: True, "call": lambda s, *a, **k: {}})()
            def state(self): return {"snmp": {"active": "1"}}
        m = M()
        m.call("snmp", "counters", {"connection": {"name": "Goliath", "host": "10.9.8.7", "community": "fake-secret-1"}})
        m.call("snmp", "discover", {"nothing": 1})
        text = "\n".join(r["text"] for r in log.entries(source="modules", level="debug"))
        self.assertIn("call snmp.counters for Goliath took", text)
        self.assertIn("call snmp.discover took", text, "a call without a device is unchanged")
        self.assertNotIn("10.9.8.7", text); self.assertNotIn("fake-secret-1", text)
