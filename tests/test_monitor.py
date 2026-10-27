import json, os, sys, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import engine, monitor  # noqa: E402


def node(i, target="x", **kw):
    return {"id": i, "name": i, "group": "Servers", "critical": True, "dependsOn": [], "rule": "primary",
            "checks": [{"id": "ping", "type": "ping", "target": target, **kw}]}


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0
    def __call__(self):
        return self.t


class Fake:
    """Programmable probe results per target."""
    def __init__(self):
        self.answers, self.calls = {}, []
    def __call__(self, check):
        self.calls.append(check["target"])
        a = self.answers.get(check["target"], (True, "ok", 1.0))
        if isinstance(a, Exception):
            raise a
        return a


class ExtrasTests(unittest.TestCase):
    def test_warn_from_a_module_check_is_kept_and_a_change_of_warn_is_news(self):
        answers = [(True, "fine", 1.0, {}), (True, "battery", 1.0, {"warn": True}), (True, "fine", 1.0, {})]
        clock = Clock()
        m = monitor.Monitor(runner=lambda c: answers.pop(0), clock=clock, inline=True)
        m.configure([node("ups", "u")], None, {"failures": 1, "seconds": 0})        # no wait: this test is about the warn flag itself
        seen = []
        for _ in range(3):
            m.run_due()
            seen.append((m.snapshot()["nodes"]["ups"]["state"], m.version))
            clock.t += 20
        self.assertEqual([s for s, _ in seen], ["healthy", "degraded", "healthy"])
        self.assertEqual(len({v for _, v in seen}), 3)  # every flip bumped the version, so screens update

    def test_a_notice_is_kept_and_never_changes_the_state(self):
        answers = [(True, "CPU 30% busy", 1.0, {}), (True, "CPU 95% busy", 1.0, {"notice": True}), (True, "CPU 30% busy", 1.0, {})]
        clock = Clock()
        m = monitor.Monitor(runner=lambda c: answers.pop(0), clock=clock, inline=True)
        m.configure([node("a3", "a")])
        seen = []
        for _ in range(3):
            m.run_due()
            n = m.snapshot()["nodes"]["a3"]
            seen.append((n["state"], n["notice"], m.version))
            clock.t += 20
        self.assertEqual([(s, nt) for s, nt, _ in seen], [("healthy", ""), ("healthy", "CPU 95% busy"), ("healthy", "")])
        self.assertEqual(len({v for _, _, v in seen}), 3)                     # the heads-up line appears and disappears on screen

    def test_a_slow_ping_is_a_heads_up_only_after_three_slow_answers_in_a_row(self):
        ms = [50.0, 300.0, 300.0, 300.0, 40.0]
        clock = Clock()
        m = monitor.Monitor(runner=lambda c: (True, "reply", ms.pop(0)), clock=clock, inline=True)
        m.configure([node("vpn", "v")])
        seen = []
        for _ in range(5):
            m.run_due()
            n = m.snapshot()["nodes"]["vpn"]
            seen.append((n["state"], bool(n["notice"])))
            clock.t += 20
        self.assertEqual(seen, [("healthy", False), ("healthy", False), ("healthy", False), ("healthy", True), ("healthy", False)])

    def test_old_three_item_runners_still_work(self):
        m = monitor.Monitor(runner=lambda c: (True, "ok", 1.0), clock=Clock(), inline=True)
        m.configure([node("a", "a")])
        m.run_due()
        self.assertEqual(m.snapshot()["nodes"]["a"]["state"], "healthy")


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.fake = Clock(), Fake()
        self.m = monitor.Monitor(runner=self.fake, clock=self.clock, inline=True)
        self.m.configure([node("a3", "a3"), node("go", "go")], None, {"failures": 1, "seconds": 0})     # these tests are about hold-down and timing, not the grace period

    def state(self, i="a3"):
        return self.m.snapshot()["nodes"][i]["state"]

    def test_first_results_and_pending_before(self):
        self.assertEqual(self.state(), "pending")
        self.m.run_due()
        self.assertEqual((self.state("a3"), self.state("go")), ("healthy", "healthy"))

    def test_a_single_failure_is_not_shown_but_two_are(self):
        self.m.run_due()
        self.fake.answers["a3"] = (False, "no reply", None)
        self.clock.t += 10
        self.m.run_due()                      # first failure: held back
        self.assertEqual(self.state(), "healthy")
        self.clock.t += 1
        self.m.run_due()                      # not due yet (rechecks after 2 s)
        self.assertEqual(self.state(), "healthy")
        self.clock.t += 1.5
        self.m.run_due()                      # second failure: confirmed
        self.assertEqual(self.state(), "failed")

    def test_a_blip_that_recovers_never_shows(self):
        self.m.run_due()
        self.fake.answers["a3"] = (False, "no reply", None)
        self.clock.t += 10
        self.m.run_due()
        self.fake.answers.pop("a3")
        self.clock.t += 2.5
        self.m.run_due()
        self.assertEqual(self.state(), "healthy")
        v = self.m.version
        self.clock.t += 10
        self.m.run_due()
        self.assertEqual(self.m.version, v)   # nothing changed, nothing pushed

    def test_recovery_shows_immediately(self):
        self.fake.answers["a3"] = (False, "no reply", None)
        self.m.run_due(); self.clock.t += 2.5; self.m.run_due()
        self.assertEqual(self.state(), "failed")
        self.fake.answers.pop("a3")
        self.clock.t += 10
        self.m.run_due()
        self.assertEqual(self.state(), "healthy")

    def test_unknown_shows_at_once_and_is_not_failed(self):
        self.fake.answers["a3"] = (None, "ping is not permitted here", None)
        self.m.run_due()
        self.assertEqual(self.state(), "unknown")

    def test_check_now_skips_hold_down(self):
        self.m.run_due()
        self.fake.answers["go"] = (False, "no reply", None)
        self.m.check_now("go")
        self.assertEqual(self.state("go"), "failed")
        self.assertEqual(self.state("a3"), "healthy")

    def test_a_crashing_probe_becomes_unknown(self):
        self.fake.answers["a3"] = RuntimeError("boom")
        self.m.run_due()
        self.assertEqual(self.state(), "unknown")
        self.assertIn("boom", self.m.snapshot()["nodes"]["a3"]["detail"])

    def test_since_changes_only_when_the_state_changes(self):
        self.m.run_due()
        s1 = self.m.snapshot()["nodes"]["a3"]["checks"][0]
        self.clock.t += 60
        self.m.run_due()
        s2 = self.m.snapshot()["nodes"]["a3"]["checks"][0]
        self.assertEqual((s1["state"], s2["state"]), ("healthy", "healthy"))
        self.fake.answers["a3"] = (False, "x", None)
        self.m.check_now("a3")
        self.assertEqual(self.m.snapshot()["nodes"]["a3"]["since"], monitor._iso(self.clock.t))

    def test_checks_run_on_their_interval(self):
        self.m.run_due()
        n = len(self.fake.calls)
        self.clock.t += 3
        self.m.run_due()
        self.assertEqual(len(self.fake.calls), n)       # ping interval is 5 s
        self.clock.t += 2.1
        self.m.run_due()
        self.assertEqual(len(self.fake.calls), n + 2)

    def test_a_down_check_is_watched_closely_so_recovery_shows_quickly(self):
        self.fake.answers["a3"] = (False, "no reply", None)
        self.m.run_due(); self.clock.t += 2.5; self.m.run_due()
        self.assertEqual(self.state(), "failed")
        self.fake.answers.pop("a3")
        self.clock.t += 3.1                              # not the full 5 s interval
        self.m.run_due()
        self.assertEqual(self.state(), "healthy")

    def test_reconfigure_keeps_unchanged_results_and_drops_changed_ones(self):
        self.m.run_due()
        self.m.configure([node("a3", "a3"), node("go", "go-new-address")])
        self.assertEqual(self.state("a3"), "healthy")   # same check: result kept
        self.assertEqual(self.state("go"), "pending")   # different check: starts fresh
        self.m.configure([node("a3", "a3")])
        self.assertNotIn("go", self.m.snapshot()["nodes"])

    def test_wait_for_change_wakes_on_a_new_result(self):
        v = self.m.version
        got = []
        t = threading.Thread(target=lambda: got.append(self.m.wait_for_change(v, 5)))
        t.start()
        time.sleep(0.2)
        self.m.run_due()
        t.join(2)
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0], v)


class ThreadedTests(unittest.TestCase):
    def test_runs_for_real_with_workers(self):
        fake = Fake()
        m = monitor.Monitor(runner=fake)
        m.configure([node("a", "a"), node("b", "b")])
        m.start()
        try:
            end = time.time() + 5
            while time.time() < end and m.snapshot()["banner"]["status"] != "green":
                time.sleep(0.1)
            self.assertEqual(m.snapshot()["banner"]["status"], "green")
        finally:
            m.stop()


class GraceTests(unittest.TestCase):
    def run_series(self, answers, confirm=None, **nodekw):
        clock, out = Clock(), []
        it = iter(answers)
        m = monitor.Monitor(runner=lambda c: next(it), clock=clock, inline=True)
        n = node("fs", "f"); n.update(nodekw)
        m.configure([n], None, confirm)
        for _ in answers:
            m.run_due(); out.append(m.snapshot()["nodes"]["fs"]["state"]); clock.t += 6
        return out

    def test_with_no_wait_set_a_confirmed_failure_shows_down_as_before(self):
        down = (False, "no answer", None)
        self.assertEqual(self.run_series([(True, "ok", 1.0), down, down, down], confirm={"failures": 1, "seconds": 0})[-1], "failed")

    def test_the_default_is_two_failures_lasting_sixty_seconds(self):
        self.assertEqual(monitor.DEFAULT_CONFIRM, (2, 60))
        down = (False, "no answer", None)
        run = self.run_series([(True, "ok", 1.0)] + [down] * 14)       # 6 s apart: 60 s of failing needs about 11 looks
        self.assertNotEqual(run[2], "failed", "two failures in a row are not enough on their own")
        self.assertEqual(run[-1], "failed", "a failure that lasts is shown")
        self.assertEqual(self.run_series([(True, "ok", 1.0), down, down, (True, "ok", 1.0)])[-1], "healthy", "a blip of two failures that clears never shows")

    def test_a_blip_shorter_than_the_grace_never_turns_red_and_a_long_one_does(self):
        ok, down = (True, "ok", 1.0), (False, "unhealthy", None)
        # 3 failures in a row needed; the hold-down look and the grace both count runs
        blip = self.run_series([ok, down, down, ok, ok], confirm={"failures": 6, "seconds": 0})
        self.assertNotIn("failed", blip)
        self.assertNotIn("degraded", blip)
        long = self.run_series([ok] + [down] * 10, confirm={"failures": 4, "seconds": 0})
        self.assertEqual(long[-1], "failed"); self.assertNotEqual(long[1], "failed")

    def test_seconds_must_also_pass_and_a_node_value_beats_the_site_default(self):
        ok, down = (True, "ok", 1.0), (False, "unhealthy", None)
        run = self.run_series([ok] + [down] * 12, confirm={"failures": 1, "seconds": 20})
        self.assertNotEqual(run[3], "failed"); self.assertEqual(run[-1], "failed")
        mixed = self.run_series([ok] + [down] * 6, confirm={"failures": 20, "seconds": 0}, confirmFailures=2)
        self.assertEqual(mixed[-1], "failed")                                   # the node asks for 2, the site default of 20 is overridden

    def test_during_the_wait_the_thing_stays_healthy_with_a_heads_up(self):
        clock = Clock(); answers = iter([(True, "ok", 1.0), (False, "unhealthy", None), (False, "unhealthy", None)])
        m = monitor.Monitor(runner=lambda c: next(answers), clock=clock, inline=True)
        m.configure([node("fs", "f")], None, {"failures": 9})
        for _ in range(3):
            m.run_due(); clock.t += 6
        n = m.snapshot()["nodes"]["fs"]
        self.assertEqual(n["state"], "healthy"); self.assertIn("confirming", n["notice"])
        self.assertEqual(engine.plain_notice(n["notice"]), "unhealthy, confirming", "the line under the banner is plain and carries no counts, whatever the monitor wrote")

    def test_unknown_is_never_held_back(self):
        self.assertEqual(self.run_series([(True, "ok", 1.0), (None, "cannot check", None)], confirm={"failures": 9})[-1], "unknown")


class Truth(unittest.TestCase):
    """History records what the checks answered; the grace period only changes what is shown."""
    def build(self, answers, confirm=None, **nodekw):
        import tempfile
        from monitorbox_app.history import History
        self.clock = Clock()
        self.hist = History(os.path.join(tempfile.mkdtemp(prefix="mb-truth-"), "config", "history.jsonl"), clock=self.clock)
        it = iter(answers)
        self.m = monitor.Monitor(runner=lambda c: next(it), clock=self.clock, inline=True, history=self.hist)
        self.m.started = self.clock.t - 1000                                    # past the quiet start-up
        n = node("fs", "f"); n.update(nodekw)
        self.m.configure([n], None, confirm)

    def step(self, secs=6):
        self.m.run_due(); self.m.record_history(); self.clock.t += secs
        return self.m.snapshot()["nodes"]["fs"]["state"]

    def kinds(self):
        return [s for _t, _n, s in self.hist.events]

    def test_a_failure_that_clears_inside_the_grace_is_in_history_but_never_on_screen(self):
        ok, down = (True, "ok", 1.0), (False, "unhealthy", None)
        self.build([ok, down, down, ok, ok])
        shown = [self.step() for _ in range(5)]
        self.assertNotIn("failed", shown)
        self.assertIn("failed", self.kinds(), "history has the truth")

    def test_history_keeps_why_a_blip_failed_even_though_the_screen_never_showed_it(self):
        ok, down = (True, "ok", 1.0), (False, "running, but Docker's health check says unhealthy (Up 2 hours (unhealthy))", None)
        self.build([ok, down, ok, ok])
        shown = [self.step() for _ in range(4)]
        self.assertNotIn("failed", shown)
        why = [w for (_t, n), w in self.hist.why.items() if n == "fs"]
        self.assertEqual(why, ["running, but Docker's health check says unhealthy (Up 2 hours (unhealthy))"])

    def test_a_degraded_warning_is_held_like_a_failure_and_shows_once_it_lasts(self):
        ok, warn = (True, "ok", 1.0), (True, "battery", 1.0, {"warn": True})
        self.build([ok] + [warn] * 14)
        shown = [self.step() for _ in range(15)]
        self.assertEqual(shown[1], "healthy"); self.assertNotEqual(shown[2], "degraded")
        self.assertEqual(shown[-1], "degraded", "a warning that lasts is shown")
        self.build([ok, warn, warn, ok, ok])
        self.assertNotIn("degraded", [self.step() for _ in range(5)], "a blip of a warning never shows")
        self.assertIn("degraded", self.kinds())

    def test_with_no_wait_the_screen_matches_history(self):
        ok, down = (True, "ok", 1.0), (False, "unhealthy", None)
        self.build([ok, down, down, down], confirm={"failures": 1, "seconds": 0})
        shown = [self.step() for _ in range(4)]
        self.assertIn("failed", shown); self.assertIn("failed", self.kinds())

    def test_grace_seconds_come_from_the_system_else_the_site(self):
        self.build([(True, "ok", 1.0)], confirm={"failures": 2, "seconds": 45})
        self.assertEqual(self.m.grace_seconds("fs"), 45)
        self.build([(True, "ok", 1.0)], confirm={"failures": 2, "seconds": 45}, confirmSeconds=5)
        self.assertEqual(self.m.grace_seconds("fs"), 5)
        self.assertEqual(self.m.grace_seconds("nobody"), 45)


class QuietStart(unittest.TestCase):
    def test_unknown_is_not_written_to_history_while_modules_log_in_but_is_afterwards(self):
        import tempfile
        from monitorbox_app.history import History
        clock = Clock()
        hist = History(os.path.join(tempfile.mkdtemp(prefix="mb-quiet-"), "config", "history.jsonl"), clock=clock)
        answers = iter([(None, "module is not running", None)] * 20)
        m = monitor.Monitor(runner=lambda c: next(answers), clock=clock, inline=True, history=hist)
        m.configure([node("fs", "f")])
        m.run_due(); m.record_history()
        self.assertEqual(hist.events, [], "the first minute after a start")
        clock.t += monitor.STARTUP_QUIET + 5
        m.run_due(); m.record_history()
        self.assertEqual([s for _t, _n, s in hist.events], ["unknown"], "a thing still unreachable after that is recorded")


class FastStart(unittest.TestCase):
    """A restart opens with the readings from before it (marked as old), and a check whose module is still coming up shows "checking", not "unknown"."""
    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory(); self.addCleanup(self.dir.cleanup)
        self.cache = os.path.join(self.dir.name, "data", "app", "last-readings.json")

    def box(self, runner, clock):
        m = monitor.Monitor(runner=runner, clock=clock, inline=True, cache_path=self.cache)
        m.configure([node("nas", "n"), node("pi", "p")], None, {"failures": 1, "seconds": 0})
        return m

    def before_restart(self, answers):
        clock = Clock()
        m = self.box(lambda c: answers[c["target"]], clock)
        m.run_due()
        clock.t += 3; m.run_due()                        # a first failure is confirmed by a second look before it is shown
        clock.t += 200                                   # past the first two minutes, when saving starts
        m.version += 1
        m.save_cache()
        return clock

    def test_a_check_whose_module_is_coming_up_stays_checking_and_leaves_no_trace(self):
        clock, answers = Clock(), [(None, "the snmp module is starting", None, {"starting": True})] * 2 + [(True, "ok", 1.0, {})]
        m = monitor.Monitor(runner=lambda c: answers.pop(0), clock=clock, inline=True)
        m.configure([node("nas", "n")], None, {"failures": 1, "seconds": 0})
        for _ in range(2):
            m.run_due()
            self.assertEqual(m.snapshot()["nodes"]["nas"]["state"], "pending", "still checking, not unknown")
            self.assertEqual(m.raw, {}, "nothing recorded for history")
            clock.t += 1.5
        m.run_due()
        self.assertEqual(m.snapshot()["nodes"]["nas"]["state"], "healthy", "asked again every second or so, answered as soon as the module was up")

    def test_the_page_opens_with_the_old_readings_marked_and_fresh_ones_replace_them(self):
        old = self.before_restart({"n": (True, "ok", 1.0), "p": (False, "no reply", None)})
        clock = Clock(); clock.t = old.t + 30                        # thirty seconds later: the box is back
        answers = {"n": (None, "the snmp module is starting", None, {"starting": True}), "p": (None, "the snmp module is starting", None, {"starting": True})}
        m = self.box(lambda c: answers[c["target"]], clock)
        self.assertEqual(m.restore(), 2)
        snap = m.snapshot()["nodes"]
        self.assertEqual((snap["nas"]["state"], snap["pi"]["state"]), ("healthy", "failed"), "the page opens as it was")
        self.assertIn("(last reading before the restart)", snap["nas"]["detail"] or snap["nas"]["checks"][0]["detail"])
        self.assertEqual(m.snapshot(fresh=True)["nodes"]["nas"]["state"], "pending", "alerts never see the old readings")
        since = m.results["nas/ping"]["since"]
        v0 = m.version
        answers["n"] = (True, "ok", 2.0)                             # its module is up: the real answer, the same as before
        clock.t += 1; m.run_due()
        self.assertNotIn("stale", m.results["nas/ping"]); self.assertEqual(m.results["nas/ping"]["since"], since, "'since' still says when it became healthy")
        self.assertGreater(m.version, v0, "the screens are told the mark is gone")
        self.assertNotIn("before the restart", json.dumps(m.snapshot()["nodes"]["nas"]))
        answers["p"] = (False, "still no reply", None)               # a down one confirmed fresh: also no longer marked
        clock.t += 1; m.run_due()
        self.assertNotIn("stale", m.results["pi/ping"])

    def test_old_readings_that_nothing_replaces_are_dropped_after_two_minutes(self):
        old = self.before_restart({"n": (True, "ok", 1.0), "p": (True, "ok", 1.0)})
        clock = Clock(); clock.t = old.t + 30
        starting = (None, "the snmp module is starting", None, {"starting": True})
        m = self.box(lambda c: starting, clock)
        m.restore()
        clock.t += 60; m.expire_stale()
        self.assertEqual(m.snapshot()["nodes"]["nas"]["state"], "healthy", "still inside the first two minutes")
        clock.t += 61; m.expire_stale()
        self.assertEqual(m.snapshot()["nodes"]["nas"]["state"], "pending", "nobody answered: it is simply not known")

    def test_a_cache_is_not_used_when_old_or_for_unknowns_or_for_checks_that_no_longer_exist_and_is_not_written_in_the_first_two_minutes(self):
        old = self.before_restart({"n": (True, "ok", 1.0), "p": (None, "could not ask", None, {})})
        m = monitor.Monitor(runner=lambda c: (True, "ok", 1.0), clock=lambda: old.t + 30, inline=True, cache_path=self.cache)
        m.configure([node("nas", "n"), node("pi", "p")], None, {"failures": 1, "seconds": 0})
        self.assertEqual(m.restore(), 1, "an unknown tells nothing")
        late = monitor.Monitor(runner=lambda c: (True, "ok", 1.0), clock=lambda: old.t + 900, inline=True, cache_path=self.cache)
        late.configure([node("nas", "n")], None, {})
        self.assertEqual(late.restore(), 0, "saved more than ten minutes ago: not 'just a restart'")
        gone = monitor.Monitor(runner=lambda c: (True, "ok", 1.0), clock=lambda: old.t + 30, inline=True, cache_path=self.cache)
        gone.configure([node("other", "o")], None, {})
        self.assertEqual(gone.restore(), 0)
        read = lambda: open(self.cache).read()
        before = read()
        young = monitor.Monitor(runner=lambda c: (True, "ok", 1.0), clock=lambda: old.t + 30, inline=True, cache_path=self.cache)
        young.configure([node("nas", "n")], None, {})
        young.version += 1; young.save_cache(force=False)
        self.assertEqual(read(), before, "the old file is not replaced by a half-empty one while the box is still starting")


if __name__ == "__main__":
    unittest.main()
