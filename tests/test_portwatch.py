"""Port errors, drops and link drops (#194): the change is watched, not the lifetime total; it is off until ticked; a known port never raises anything."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import portwatch, monconfig  # noqa: E402
from monitorbox_app.store import Paths  # noqa: E402


def dev(name, **ports):
    """A controller device whose ports carry the given counters: dev("Core", **{"Port 5": (rx_err, tx_err, rx_drop, tx_drop, link_down)})"""
    return {"name": name, "ports": [{"name": n, "rx_errors": v[0], "tx_errors": v[1], "rx_dropped": v[2], "tx_dropped": v[3], "link_down_count": v[4]} for n, v in ports.items()]}


class Judge(unittest.TestCase):
    def series(self, step_minutes, values):
        """Readings every `step_minutes`: values are (errors, drops, flaps) lifetime totals."""
        return [[i * step_minutes * 60, *v] for i, v in enumerate(values)]

    def test_a_port_with_a_steady_trickle_is_not_news(self):
        # 60 minutes, 30 errors every 5 minutes the whole time: always like this
        q = self.series(5, [(30 * i, 0, 0) for i in range(13)])
        j = portwatch.judge(q)
        self.assertFalse(j["learning"])
        self.assertEqual(j["rising"], [])
        self.assertEqual(j["perHour"]["errors"], 360)

    def test_a_quiet_port_that_suddenly_throws_errors_is_rising(self):
        # 45 quiet minutes, then 400 errors in the last 15
        q = self.series(5, [(0, 0, 0)] * 10 + [(150, 0, 0), (300, 0, 0), (400, 0, 0)])
        j = portwatch.judge(q)
        self.assertEqual(j["rising"], ["errors"])
        self.assertEqual(j["perHour"]["errors"], 1600)
        self.assertEqual(j["was"]["errors"], 0)

    def test_a_steady_trickle_that_gets_much_worse_is_rising_but_a_little_worse_is_not(self):
        base = [(30 * i, 0, 0) for i in range(10)]                         # 6 an hour... then
        worse = base + [(270 + 150 * k, 0, 0) for k in range(1, 4)]       # 150 per 5 min: five times the old pace and more
        self.assertEqual(portwatch.judge(self.series(5, worse))["rising"], ["errors"])
        slight = base + [(270 + 45 * k, 0, 0) for k in range(1, 4)]       # 45 per 5 min: only 1.5 times the old pace
        self.assertEqual(portwatch.judge(self.series(5, slight))["rising"], [])

    def test_a_few_errors_an_hour_are_not_worth_a_line(self):
        q = self.series(5, [(0, 0, 0)] * 10 + [(2, 0, 0), (4, 0, 0), (6, 0, 0)])
        self.assertEqual(portwatch.judge(q)["rising"], [])

    def test_the_first_half_hour_only_learns(self):
        q = self.series(5, [(0, 0, 0), (100, 0, 0), (300, 0, 0), (900, 0, 0), (2000, 0, 0)])      # 20 minutes: loud, but nothing to compare with
        j = portwatch.judge(q)
        self.assertTrue(j["learning"])
        self.assertEqual(j["rising"], [])

    def test_drops_and_link_drops_have_their_own_floors(self):
        q = self.series(5, [(0, 0, 0)] * 10 + [(0, 400, 1), (0, 900, 2), (0, 1500, 4)])
        self.assertEqual(portwatch.judge(q)["rising"], ["drops", "flaps"])
        small = self.series(5, [(0, 0, 0)] * 10 + [(0, 100, 0), (0, 200, 1), (0, 300, 2)])
        self.assertEqual(portwatch.judge(small)["rising"], [])


class Watch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.w = portwatch.PortWatch(self.paths)

    def run_minutes(self, minutes, errs_at, port="Port 5", start=0, step=1):
        """Feeds one reading a minute; errs_at(minute) gives the lifetime error total."""
        for m in range(start, minutes + 1, step):
            self.w.feed([dev("Core switch", **{port: (errs_at(m), 0, 0, 0, 0)})], ["sw1"], now=m * 60)

    def test_it_is_off_until_ticked_and_says_nothing(self):
        self.assertFalse(self.w.enabled())
        self.assertEqual(self.w.check()[0], None)
        self.w.set_enabled(True)
        self.assertTrue(self.w.enabled())
        self.w.set_enabled(False)
        self.assertFalse(self.w.enabled())

    def test_a_port_that_gets_worse_makes_the_check_degraded_never_failed(self):
        self.w.set_enabled(True)
        self.run_minutes(60, lambda m: 0 if m < 45 else (m - 45) * 40)
        ok, detail, ms, extra = self.w.check()
        self.assertIs(ok, True, "a rising port is a warning, never a failure")
        self.assertTrue(extra.get("warn"))
        self.assertIn("Core switch, Port 5", detail)
        self.assertIn("errors rising", detail)

    def test_a_quiet_network_is_fine_and_a_new_box_says_it_is_still_learning(self):
        self.w.set_enabled(True)
        self.run_minutes(10, lambda m: 0)
        ok, detail, _, extra = self.w.check()
        self.assertTrue(ok)
        self.assertFalse(extra.get("warn"))
        self.assertIn("half an hour", detail)

    def test_a_known_port_keeps_its_numbers_but_never_raises_anything(self):
        self.w.set_enabled(True)
        key = self.w.key("sw1", "Port 5")
        self.w.set_known([key], True)
        self.run_minutes(60, lambda m: 0 if m < 45 else (m - 45) * 40)
        ok, detail, _, extra = self.w.check()
        self.assertFalse(extra.get("warn"), "a known issue must not warn")
        st = self.w.state([key])
        self.assertTrue(st["known"])
        self.assertEqual(st["rising"], ["errors"], "the numbers are still observed, only the alerting is suppressed")
        self.w.set_known([key], False)
        self.assertTrue(self.w.check()[3].get("warn"))

    def test_a_counter_going_backwards_means_a_restart_and_starts_again(self):
        self.w.set_enabled(True)
        self.run_minutes(40, lambda m: m * 1000)               # lots of errors so far
        self.w.feed([dev("Core switch", **{"Port 5": (3, 0, 0, 0, 0)})], ["sw1"], now=41 * 60)     # the switch restarted
        self.assertEqual(len(self.w.series[self.w.key("sw1", "Port 5")]), 1)
        st = self.w.state([self.w.key("sw1", "Port 5")])
        self.assertEqual(st["rising"], [])
        self.assertTrue(st["learning"])

    def test_a_bonded_pair_adds_its_ports_and_a_missing_counter_is_not_invented(self):
        self.w.set_enabled(True)
        for m in range(0, 61):
            self.w.feed([dev("Core switch", **{"Port 1": (0 if m < 45 else (m - 45) * 20, 0, 0, 0, 0), "Port 2": (0 if m < 45 else (m - 45) * 20, 0, 0, 0, 0)}),
                         {"name": "No counters", "ports": [{"name": "Port 1"}]}], ["sw1", "sw2"], now=m * 60)
        self.assertNotIn(self.w.key("sw2", "Port 1"), self.w.series)
        pair = self.w.state([self.w.key("sw1", "Port 1"), self.w.key("sw1", "Port 2")])
        one = self.w.state([self.w.key("sw1", "Port 1")])
        self.assertEqual(pair["perHour"]["errors"], 2 * one["perHour"]["errors"])

    def test_settings_survive_a_save_and_each_port_keeps_its_own_mark(self):
        a, b, c = self.w.key("sw-aaa", "Port 1"), self.w.key("sw-bbb", "Port 2"), self.w.key("sw-ccc", "Port 3")
        self.w.set_enabled(True)
        self.w.set_known([a, b, c], True)
        self.w.set_known([b], False)
        again = portwatch.PortWatch(self.paths)
        self.assertTrue(again.enabled())
        self.assertEqual(again.known(), {a, c})


class AsASystem(unittest.TestCase):
    def test_the_built_in_check_is_a_valid_system_in_the_monitoring_config(self):
        with tempfile.TemporaryDirectory() as d:
            paths = Paths(d)
            os.makedirs(os.path.dirname(paths.config), exist_ok=True)
            node = {"id": "port-errors", "name": "Port errors", "group": "Network", "checks": [{"id": "ports", "type": "ports", "interval": 30}]}
            monconfig.sync_nodes(paths, "port-errors", [node])
            nodes, err = monconfig.all_nodes(paths)
            self.assertFalse(err)
            got = next(n for n in nodes if n["id"] == "port-errors")
            self.assertEqual(got["checks"][0]["type"], "ports")
            monconfig.sync_nodes(paths, "port-errors", [])
            self.assertFalse(any(n["id"] == "port-errors" for n in monconfig.all_nodes(paths)[0]))


if __name__ == "__main__":
    unittest.main()
