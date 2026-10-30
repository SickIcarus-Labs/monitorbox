import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from monitorbox_app import applog


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Engine(unittest.TestCase):
    def make(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        self.clock = Clock()
        return applog.Log(os.path.join(d.name, "logs"), self.clock), d.name

    def test_a_line_is_written_read_back_newest_first_and_ids_only_grow(self):
        log, _ = self.make()
        log.write("info", "alerts", "first")
        log.write("warning", "modules", "second")
        rows = log.entries()
        self.assertEqual([r["text"] for r in rows], ["second", "first"])
        self.assertLess(rows[1]["id"], rows[0]["id"])
        self.assertEqual(log.entries(since=rows[1]["id"])[0]["text"], "second")
        self.assertEqual(len(log.entries(since=rows[1]["id"])), 1, "only what is newer than the last one the page holds")

    def test_level_source_and_search_filters(self):
        log, _ = self.make()
        log.write("info", "alerts", "sent to Home Assistant")
        log.write("error", "modules", "snmp crashed")
        log.write("warning", "alerts", "retrying")
        self.assertEqual([r["text"] for r in log.entries(level="warning")], ["retrying", "snmp crashed"])
        self.assertEqual([r["text"] for r in log.entries(source="modules")], ["snmp crashed"])
        self.assertEqual([r["text"] for r in log.entries(q="HOME")], ["sent to Home Assistant"])

    def test_a_restart_still_shows_the_old_lines_and_ids_keep_growing(self):
        log, name = self.make()
        log.write("info", "app", "before")
        old = log.entries()[0]["id"]
        again = applog.Log(os.path.join(name, "logs"), self.clock)
        again.write("info", "app", "after")
        self.assertEqual([r["text"] for r in again.entries()], ["after", "before"])
        self.assertGreater(again.entries()[0]["id"], old)

    def test_the_log_is_cut_into_files_and_never_passes_its_size(self):
        log, name = self.make()
        spec = dict(applog.NORMAL, size=2000, files=3)
        applog.NORMAL, saved = spec, applog.NORMAL
        self.addCleanup(lambda: setattr(applog, "NORMAL", saved))
        for n in range(200):
            self.clock.t += 1
            log.write("info", f"s{n % 50}", "x" * 60)
        files = sorted(os.listdir(os.path.join(name, "logs")))
        self.assertEqual(files, ["mb.log", "mb.log.1", "mb.log.2"], "no more than the files allowed")
        for f in files:
            self.assertLessEqual(os.path.getsize(os.path.join(name, "logs", f)), 2000)

    def test_debug_lines_are_written_only_while_debug_is_on_and_it_switches_itself_off(self):
        log, _ = self.make()
        log.write("debug", "portwatch", "round 1")
        self.assertEqual(log.entries(level="debug"), [], "off by default: nothing written")
        until = log.set_debug(True)
        self.assertEqual(until, self.clock.t + 24 * 3600)
        log.write("debug", "portwatch", "round 2")
        self.assertEqual([r["text"] for r in log.entries(level="debug") if r["source"] == "portwatch"], ["round 2"])
        self.clock.t += 24 * 3600 + 1
        log.write("debug", "portwatch", "round 3")
        self.assertNotIn("round 3", [r["text"] for r in log.entries(level="debug")], "after 24 hours it is off again")
        self.assertIn("round 2", [r["text"] for r in log.entries(level="debug")], "switching off deletes nothing")

    def test_all_shows_debug_lines_while_debug_is_on_and_not_otherwise(self):
        log, _ = self.make()
        log.set_debug(True)
        log.write("debug", "portwatch", "round 1")
        self.assertIn("round 1", [r["text"] for r in log.entries(level="auto")], "debug is on: All includes it without changing the filter")
        log.set_debug(False)
        self.assertNotIn("round 1", [r["text"] for r in log.entries(level="auto")], "debug is off: All is the normal log")
        self.assertIn("round 1", [r["text"] for r in log.entries(level="debug")], "older debug lines are still reachable")

    def test_debug_is_kept_apart_so_it_cannot_push_the_normal_log_out(self):
        log, name = self.make()
        log.set_debug(True)
        log.write("info", "app", "normal")
        log.write("debug", "app", "debug")
        self.assertTrue(os.path.exists(os.path.join(name, "logs", "debug.log")))
        self.assertNotIn("debug", open(os.path.join(name, "logs", "mb.log")).read().split("normal")[-1])
        self.assertEqual([r["text"] for r in log.entries(level="info")].count("debug"), 0)

    def test_secrets_and_webhook_paths_never_reach_the_file(self):
        log, name = self.make()
        log.write("error", "alerts", "post to https://hooks.example.test/services/T0/B1/SECRETPATH?key=abc failed; password=hunter2 token: tok-123 Bearer abcdefghij123456")
        with open(os.path.join(name, "logs", "mb.log")) as f:
            text = f.read()
        for secret in ("SECRETPATH", "hunter2", "tok-123", "abcdefghij123456", "key=abc"):
            self.assertNotIn(secret, text)
        self.assertIn("hooks.example.test", text, "where it points is kept: that is what is useful")
        self.assertIn("password=***", text)

    def test_plain_words_are_not_blanked(self):
        self.assertEqual(applog.redact("password rejected by the UPS; session expired"), "password rejected by the UPS; session expired")

    def test_one_noisy_source_is_cut_off_for_the_minute_says_so_once_and_others_are_unharmed(self):
        log, _ = self.make()
        for n in range(applog.NORMAL["per_minute"] + 80):
            log.write("info", "noisy", f"line {n}")
        log.write("info", "quiet", "still written")
        self.assertEqual(len([r for r in log.entries(limit=10000) if r["source"] == "noisy"]), applog.NORMAL["per_minute"])
        self.clock.t += 61
        log.write("info", "noisy", "next minute")
        rows = log.entries(limit=10000)
        notes = [r for r in rows if "Suppressed 80 similar lines" in r["text"]]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["level"], "warning")
        self.assertIn("still written", [r["text"] for r in rows])
        self.assertIn("next minute", [r["text"] for r in rows])

    def test_counts_for_the_last_day_and_download(self):
        log, _ = self.make()
        log.write("error", "modules", "old")
        self.clock.t += 2 * 86400
        log.write("error", "modules", "new error")
        log.write("warning", "alerts", "new warning")
        self.assertEqual(log.counts(), {"warning": 1, "error": 1})
        text = log.download()
        self.assertLess(text.index("old"), text.index("new error"), "oldest first")

    def test_files_older_than_their_limit_are_removed_at_start(self):
        log, name = self.make()
        log.write("info", "app", "x")
        path = os.path.join(name, "logs", "mb.log")
        os.utime(path, (self.clock.t - 15 * 86400,) * 2)
        log.purge()
        self.assertFalse(os.path.exists(path))

    def test_a_log_that_cannot_be_written_does_not_stop_the_app(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        blocker = os.path.join(d.name, "logs")
        open(blocker, "w").close()                         # a file where the folder should be
        log = applog.Log(blocker, Clock())
        log.write("error", "app", "still fine")             # no exception

    def test_the_module_level_helpers_do_nothing_before_setup(self):
        applog._log = None
        applog.info("app", "x"); applog.debug("app", "y")  # no exception
        self.assertFalse(applog.debug_on())


if __name__ == "__main__":
    unittest.main()
