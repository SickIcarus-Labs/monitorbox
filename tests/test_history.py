"""30-day history: state changes only, pruned to the window, gaps read Unknown, availability ignores Unknown."""
import os, sys, tempfile, unittest, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app.history import History, GAP_SECONDS

D = 86400


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


class H(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-hist-")
        self.path = os.path.join(self.tmp, "config", "history.jsonl")
        self.clk = Clock(1_800_000_000)
        self.h = History(self.path, clock=self.clk)

    def lines(self):
        with open(self.path) as f:
            return [json.loads(x) for x in f]

    def test_only_changes_are_written_and_pending_is_not_a_state(self):
        self.h.record({"a": "pending", "b": "healthy"})
        self.assertEqual(self.lines(), [{"t": self.clk.t, "n": "b", "s": "healthy"}])
        self.clk.t += 60; self.h.record({"a": "healthy", "b": "healthy"})
        self.clk.t += 60; self.h.record({"a": "healthy", "b": "failed"})
        self.assertEqual([(e["n"], e["s"]) for e in self.lines()], [("b", "healthy"), ("a", "healthy"), ("b", "failed")])

    def test_it_survives_a_restart_and_a_torn_last_line(self):
        self.h.record({"a": "healthy"}); self.clk.t += 10; self.h.record({"a": "failed"})
        with open(self.path, "a") as f: f.write('{"t": 12, "n": "a", "s"')   # power cut mid-write
        self.clk.t += 10
        again = History(self.path, clock=self.clk)
        again.record({"a": "failed"})                                         # unchanged: nothing new
        self.assertEqual(again.timeline("a")["segments"], [[1_800_000_000, 1_800_000_010, "healthy"], [1_800_000_010, 1_800_000_020, "failed"]])

    def test_availability_counts_failed_time_and_leaves_unknown_out(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy"})
        self.clk.t = t0 + 600; self.h.record({"a": "failed"})
        self.clk.t = t0 + 700; self.h.record({"a": "unknown"})      # a provider outage: not a failure
        self.clk.t = t0 + 1000; self.h.record({"a": "healthy"})
        self.clk.t = t0 + 1300
        tl = self.h.timeline("a")
        self.assertEqual(tl["seconds"], {"healthy": 900, "degraded": 0, "failed": 100, "unknown": 300})
        self.assertEqual(tl["availability"], 90.0)
        self.assertEqual(tl["outages"], 1)

    def test_the_app_being_off_reads_unknown_never_healthy_or_failed(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy", "b": "failed"})
        self.clk.t = t0 + 40; self.h.record({"a": "healthy", "b": "failed"})   # heartbeat at t0+40
        self.clk.t = t0 + 40 + GAP_SECONDS + 3600                              # off for an hour and a bit
        again = History(self.path, clock=self.clk)
        for n in ("a", "b"):
            segs = again.timeline(n)["segments"]
            self.assertEqual(segs[-1][2], "unknown", n)
            self.assertEqual(segs[-1][0], t0 + 40)
        again.record({"a": "healthy", "b": "failed"})
        self.clk.t += 10                                                       # the App is back and sees the truth again
        self.assertEqual(again.timeline("a")["segments"][-1][2], "healthy")
        self.assertEqual(again.timeline("b")["segments"][-1][2], "failed")

    def test_a_short_restart_is_not_a_gap(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy"})
        self.clk.t = t0 + 30; self.h.record({"a": "healthy"})
        self.clk.t = t0 + 60
        self.assertEqual(History(self.path, clock=self.clk).timeline("a")["segments"], [[t0, t0 + 60, "healthy"]])

    def test_old_history_is_pruned_but_the_state_at_the_window_start_is_kept(self):
        t0 = self.clk.t
        self.clk.t = t0 - 40 * D; self.h.record({"old": "failed", "steady": "healthy"})
        self.clk.t = t0 - 10 * D; self.h.record({"old": "healthy"})
        self.clk.t = t0; self.h.prune()
        self.assertEqual(sorted((e["n"], e["s"]) for e in self.lines()), [("old", "failed"), ("old", "healthy"), ("steady", "healthy")])
        tl = self.h.timeline("steady")
        self.assertEqual(tl["segments"], [[t0 - 30 * D, t0, "healthy"]])      # still known to be healthy across the whole window
        self.assertEqual(self.h.timeline("old")["segments"][0], [t0 - 30 * D, t0 - 10 * D, "failed"])
        # and a second prune changes nothing
        before = open(self.path).read(); self.h.prune(); self.assertEqual(open(self.path).read(), before)

    def test_a_shorter_window_clips_and_keeps_the_state_it_started_in(self):
        t0 = self.clk.t
        self.h.record({"a": "failed"})
        self.clk.t = t0 + 3 * 3600; self.h.record({"a": "healthy"})
        self.clk.t = t0 + 4 * 3600
        hour = self.h.timeline("a", 3600)
        self.assertEqual(hour["segments"], [[t0 + 3 * 3600, t0 + 4 * 3600, "healthy"]])
        self.assertEqual((hour["availability"], hour["outages"], hour["window"]), (100.0, 0, 3600))
        four = self.h.timeline("a", 4 * 3600)
        self.assertEqual(four["segments"], [[t0, t0 + 3 * 3600, "failed"], [t0 + 3 * 3600, t0 + 4 * 3600, "healthy"]])
        self.assertEqual(four["availability"], 25.0)
        # asking for more than is kept is the whole window, not an error
        self.assertEqual(self.h.timeline("a", 999 * D)["window"], 30 * D)

    def test_an_unknown_node_has_an_empty_timeline(self):
        tl = self.h.timeline("nope")
        self.assertEqual((tl["segments"], tl["availability"], tl["outages"]), ([], None, 0))


    def test_a_group_strip_shows_the_worst_state_hour_by_hour(self):
        h, c = self.h, self.clk; t0 = c.t
        h.record({"a": "healthy", "b": "healthy"})
        c.t = t0 + 3600 * 3; h.record({"b": "failed"})          # b down from hour 3 on
        c.t = t0 + 3600 * 5; h.record({"b": "degraded"})        # then degraded
        c.t = t0 + 3600 * 24
        r = h.strip(["a", "b"], hours=24, buckets=24)
        self.assertEqual(r["buckets"][:3], ["healthy"] * 3)
        self.assertEqual(r["buckets"][3:5], ["failed"] * 2)
        self.assertEqual(set(r["buckets"][5:]), {"degraded"})
        self.assertEqual(h.strip(["nobody"])["buckets"], [None] * 24, "no record yet is None, not healthy")
        c.t = t0 + 3600 * 30                                   # a day later nothing changed: the last state fills the window
        self.assertEqual(set(h.strip(["a"])["buckets"]), {"healthy"})


    def test_the_bar_filter_only_changes_what_is_shown_and_nothing_is_erased(self):
        h, c = self.h, self.clk; t0 = c.t
        h.record({"a": "healthy"})
        c.t = t0 + 3600 * 3; h.record({"a": "failed"})
        c.t = t0 + 3600 * 5; h.record({"a": "degraded"})
        c.t = t0 + 3600 * 7; h.record({"a": "unknown"})
        c.t = t0 + 3600 * 24
        full = h.strip(["a"])["buckets"]
        self.assertEqual((full[3], full[5], full[8]), ("failed", "degraded", "unknown"))
        only_down = h.strip(["a"], show=["failed"])["buckets"]
        self.assertEqual((only_down[3], only_down[5], only_down[8]), ("failed", "healthy", None), "degraded shows healthy, unknown shows no record")
        self.assertEqual(set(h.strip(["a"], show=[])["buckets"][3:]), {"healthy", None})
        self.assertEqual(h.strip(["a"])["buckets"], full, "nothing was erased: all ticked again brings everything back")
        self.assertEqual([x["state"] for x in h.trouble(["a"], t0, c.t, show=["degraded"])["items"]], ["degraded"])
        self.assertEqual(len(h.trouble(["a"], t0, c.t)["items"]), 3)

    def test_clear_forgets_everything_and_the_next_record_starts_fresh_and_the_page_keeps_the_newest(self):
        h, c = self.h, self.clk; t0 = c.t
        h.record({"a": "healthy", "b": "healthy"})
        for i in range(5):
            c.t = t0 + 100 * (2 * i + 1); h.record({"a": "failed"})
            c.t = t0 + 100 * (2 * i + 2); h.record({"a": "healthy"})
        r = h.trouble(h.node_ids(), t0, c.t, limit=2, newest_first=True)
        self.assertEqual([x["from"] for x in r["items"]], [t0 + 900, t0 + 700]); self.assertEqual(r["more"], 3)
        h.clear()
        self.assertEqual((h.node_ids(), h.trouble(["a"], t0, c.t)["items"], self.lines()), ([], [], []))
        c.t += 10; h.record({"a": "healthy", "b": "failed"})
        self.assertEqual([(e["n"], e["s"]) for e in self.lines()], [("a", "healthy"), ("b", "failed")])
        self.assertEqual(History(self.path, clock=self.clk).node_ids(), ["a", "b"], "a restart after a clear reads only the fresh start")

    def test_trouble_lists_what_was_not_healthy_inside_a_window_clipped_to_it(self):
        h, c = self.h, self.clk; t0 = c.t
        h.record({"a": "healthy", "b": "healthy"})
        c.t = t0 + 1000; h.record({"a": "failed"})
        c.t = t0 + 1600; h.record({"a": "healthy", "b": "degraded"})
        c.t = t0 + 7200
        r = h.trouble(["a", "b"], t0 + 900, t0 + 3600)
        self.assertEqual([(x["node"], x["state"], x["from"] - t0, x["to"] - t0) for x in r["items"]],
                         [("a", "failed", 1000, 1600), ("b", "degraded", 1600, 3600)])      # a window edge clips a stretch
        self.assertEqual(h.trouble(["a"], t0 + 2000, t0 + 3600)["items"], [], "a quiet hour lists nothing")
        self.assertEqual(h.trouble(["nobody"], t0, t0 + 3600)["items"], [])


class Why(H):
    """History also keeps what the check said when a stretch was not healthy, so a blip can be explained later."""
    def test_a_reason_is_kept_for_a_stretch_that_was_not_healthy_and_never_for_a_healthy_one(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy", "b": "healthy"}, {"a": "running", "b": "all good"})
        self.clk.t = t0 + 60; self.h.record({"a": "failed", "b": "degraded"}, {"a": "keeps restarting (Restarting (1) 5 seconds ago)", "b": "slow reply 4200 ms"})
        self.clk.t = t0 + 120; self.h.record({"a": "healthy", "b": "healthy"}, {"a": "running", "b": "all good"})
        lines = {(e["n"], e["s"]): e.get("w") for e in self.lines()}
        self.assertEqual(lines[("a", "failed")], "keeps restarting (Restarting (1) 5 seconds ago)")
        self.assertEqual(lines[("b", "degraded")], "slow reply 4200 ms")
        self.assertIsNone(lines[("a", "healthy")]); self.assertIsNone(lines[("b", "healthy")])
        self.clk.t = t0 + 200
        got = {r["node"]: r for r in self.h.trouble(["a", "b"], t0, t0 + 200)["items"]}
        self.assertEqual(got["a"]["why"], "keeps restarting (Restarting (1) 5 seconds ago)")
        self.assertEqual(got["b"]["why"], "slow reply 4200 ms")

    def test_the_reason_comes_back_after_a_restart_and_is_cut_to_a_sensible_length(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy"}); self.clk.t += 60
        self.h.record({"a": "failed"}, {"a": "x" * 500})
        self.assertEqual(self.lines()[-1]["w"], "x" * 399 + "…", "cut at the limit, and it says so")
        self.clk.t += 120
        again = History(self.path, clock=self.clk)
        self.assertEqual(again.trouble(["a"], t0, t0 + 300)["items"][0]["why"], "x" * 399 + "…")
        self.clk.t += 60
        self.h.record({"a": "healthy"}); self.clk.t += 60
        port = "Broad Leaf, SFP+ 2: errors rising (about 29,420 an hour: 29,420 receive, 0 transmit), carrying about 93.9 Mbit/s (peak 121.7 Mbit/s) · other end (Aggregation, SFP28 2): 0 receive, 0 transmit an hour"
        self.h.record({"a": "degraded"}, {"a": port})
        self.assertEqual(self.lines()[-1]["w"], port, "a real port alert is kept whole")

    def test_older_lines_without_a_reason_still_load_and_list_without_one(self):
        t0 = self.clk.t
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({"t": t0 - 600, "n": "a", "s": "healthy"}) + "\n" + json.dumps({"t": t0 - 300, "n": "a", "s": "failed"}) + "\n")
        old = History(self.path, clock=self.clk)
        item = old.trouble(["a"], t0 - 900, t0)["items"][0]
        self.assertEqual(item["state"], "failed"); self.assertNotIn("why", item)

    def test_a_trim_keeps_the_reasons_of_what_it_keeps(self):
        t0 = self.clk.t
        self.clk.t = t0 - 5 * D; self.h.record({"a": "healthy"})
        self.clk.t = t0 - 4 * D; self.h.record({"a": "failed"}, {"a": "distinct reason 41"})
        self.clk.t = t0 - 3 * D; self.h.record({"a": "healthy"})
        self.clk.t = t0 + 40 * D; self.h.record({"a": "failed"}, {"a": "distinct reason 42"}); self.h.prune()
        self.assertEqual([e.get("w") for e in self.lines() if e["s"] == "failed"], ["distinct reason 42"])


class Brief(H):
    """A Down or Degraded stretch shorter than the node's confirmation seconds is a brief blip: the bars treat it as healthy and the list can hide it."""
    def stretches(self):
        t0 = self.clk.t
        self.h.record({"a": "healthy", "b": "healthy"})
        self.clk.t = t0 + 600; self.h.record({"a": "failed", "b": "healthy"})        # a: down for 30 s
        self.clk.t = t0 + 630; self.h.record({"a": "healthy", "b": "degraded"})      # b: degraded for 20 minutes
        self.clk.t = t0 + 1830; self.h.record({"a": "healthy", "b": "healthy"})
        self.clk.t = t0 + 2000
        return t0

    def test_bars_show_a_long_stretch_and_not_a_short_one(self):
        self.stretches()
        sixty = lambda n: 60
        plain = self.h.strip(["a"], hours=1, buckets=6)
        self.assertIn("failed", plain["buckets"], "without a grace the 30 s blip shows")
        self.assertNotIn("failed", self.h.strip(["a"], hours=1, buckets=6, min_seconds=sixty)["buckets"])
        self.assertIn("degraded", self.h.strip(["b"], hours=1, buckets=6, min_seconds=sixty)["buckets"], "twenty minutes is not brief")
        self.assertIn("failed", self.h.strip(["a"], hours=1, buckets=6, min_seconds=lambda n: 0)["buckets"], "no wait: the bars match history exactly")
        self.assertIn("failed", self.h.strip(["a"], hours=1, buckets=6, min_seconds=lambda n: 20)["buckets"], "a node with a shorter wait of its own")

    def test_the_list_leaves_brief_ones_out_unless_asked_and_marks_them(self):
        t0 = self.stretches()
        sixty = lambda n: 60
        got = self.h.trouble(["a", "b"], t0, t0 + 2000, min_seconds=sixty)
        self.assertEqual([(x["node"], x["state"]) for x in got["items"]], [("b", "degraded")])
        got = self.h.trouble(["a", "b"], t0, t0 + 2000, min_seconds=sixty, brief=True)
        self.assertEqual([(x["node"], x.get("brief")) for x in got["items"]], [("a", True), ("b", None)])
        self.assertEqual(len(self.h.trouble(["a", "b"], t0, t0 + 2000)["items"]), 2, "no grace given: everything, as before")

    def test_a_stretch_that_is_still_going_and_younger_than_the_wait_is_brief_too(self):
        self.h.record({"a": "healthy"}); self.clk.t += 100; self.h.record({"a": "failed"}); self.clk.t += 30
        self.assertNotIn("failed", self.h.strip(["a"], hours=1, buckets=6, min_seconds=lambda n: 60)["buckets"])
        self.clk.t += 60
        self.assertIn("failed", self.h.strip(["a"], hours=1, buckets=6, min_seconds=lambda n: 60)["buckets"], "once it has lasted the wait it shows")

    def test_the_timeline_and_availability_still_count_every_second(self):
        self.stretches()
        self.assertEqual(self.h.timeline("a")["seconds"]["failed"], 30)


class MorePortsJoinAStretch(unittest.TestCase):
    """#311: Port errors stays degraded while any port rises, so ports that start rising later in the same stretch used to go unnamed."""

    setUp = H.setUp
    lines = H.lines

    def why(self, node="pe"):
        items = self.h.trouble([node], 0, self.clk.t + 10 * D)["items"]
        return [i.get("why") for i in items]

    def test_a_port_that_joins_the_stretch_is_added_to_its_reason(self):
        self.h.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising"}, {"pe": ["Bay A, Port 4"]})
        self.clk.t += 600; self.h.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising; Den, Port 8: drops rising"}, {"pe": ["Bay A, Port 4", "Den, Port 8"]})
        self.assertEqual(self.why(), ["Bay A, Port 4: errors rising; also Den, Port 8"], "a port the reason already names is not repeated")

    def test_ports_past_the_third_are_named_too_and_each_only_once(self):
        names = ["P1", "P2", "P3"]
        self.h.record({"pe": "degraded"}, {"pe": "P1: x; P2: x; P3: x (and 1 more)"}, {"pe": names})
        for extra in (["P4"], ["P4", "P5"], ["P4", "P5"]):
            self.clk.t += 300; self.h.record({"pe": "degraded"}, {"pe": "P1: x; P2: x; P3: x (and 2 more)"}, {"pe": names + extra})
        self.assertEqual(self.why(), ["P1: x; P2: x; P3: x (and 1 more); also P4; also P5"])

    def test_the_reason_stays_inside_the_limit_and_says_when_it_is_cut(self):
        first = "Bay A, Port 4: " + "x" * 380
        self.h.record({"pe": "degraded"}, {"pe": first}, {"pe": ["Bay A, Port 4"]})
        self.clk.t += 60; self.h.record({"pe": "degraded"}, {"pe": first}, {"pe": ["Bay A, Port 4", "Den, Port 8"]})
        w = self.why()[0]
        self.assertLessEqual(len(w), 400)
        self.assertTrue(w.endswith("…"))

    def test_the_added_ports_survive_a_restart(self):
        self.h.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising"}, {"pe": ["Bay A, Port 4"]})
        self.clk.t += 60; self.h.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising"}, {"pe": ["Bay A, Port 4", "Den, Port 8"]})
        again = History(self.path, clock=self.clk)
        self.assertEqual([i["why"] for i in again.trouble(["pe"], 0, self.clk.t + 10)["items"]], ["Bay A, Port 4: errors rising; also Den, Port 8"])
        self.assertEqual(sum(1 for e in again.events if e[1] == "pe"), 1, "the update is not a second event")
        self.clk.t += 60; again.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising"}, {"pe": ["Bay A, Port 4", "Den, Port 8", "Hall, Port 2"]})
        self.assertEqual([i["why"] for i in again.trouble(["pe"], 0, self.clk.t + 10)["items"]], ["Bay A, Port 4: errors rising; also Den, Port 8; also Hall, Port 2"])

    def test_a_new_stretch_starts_with_its_own_reason_not_the_old_ports(self):
        self.h.record({"pe": "degraded"}, {"pe": "Bay A, Port 4: errors rising"}, {"pe": ["Bay A, Port 4", "Den, Port 8"]})
        self.clk.t += 60; self.h.record({"pe": "healthy"}, {"pe": "all 45 ports look normal"}, {"pe": []})
        self.clk.t += 60; self.h.record({"pe": "degraded"}, {"pe": "Hall, Port 2: drops rising"}, {"pe": ["Hall, Port 2"]})
        self.clk.t += 60
        self.assertEqual(sorted(self.why()), ["Bay A, Port 4: errors rising", "Hall, Port 2: drops rising"])

    def test_a_healthy_or_unreasoned_stretch_gets_nothing_added(self):
        self.h.record({"pe": "healthy"}, {"pe": "fine"}, {"pe": ["Bay A, Port 4"]})
        self.clk.t += 60; self.h.record({"pe": "healthy"}, {"pe": "fine"}, {"pe": ["Bay A, Port 4", "Den, Port 8"]})
        self.assertEqual(self.h.trouble(["pe"], 0, self.clk.t + 10)["items"], [])
        self.assertEqual([e for e in self.lines() if "w" in e], [])


if __name__ == "__main__":
    unittest.main()
