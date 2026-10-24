"""Likely destinations from port rates (#191): the port whose outgoing traffic follows the device's incoming traffic is the likely
destination; noise, flat ports and too little history are not guessed at."""
import os, random, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import portpeers as P  # noqa: E402


def bursts(n, seed):
    r = random.Random(seed)
    return [r.choice((0, 0, 50_000, 800_000, 3_000_000)) + r.randint(0, 5000) for _ in range(n)]


class Series(unittest.TestCase):
    def test_counters_become_rates_a_restart_is_skipped_and_a_32_bit_rollover_is_counted(self):
        t = [1000.0]
        s = P.PortSeries(clock=lambda: t[0])
        s.feed_counters("sw", {"p1": {"in": 0, "out": 0, "bits": 64}, "p2": {"in": (1 << 32) - 1000, "out": 5, "bits": 32}})
        t[0] += 10
        s.feed_counters("sw", {"p1": {"in": 12_500, "out": 25_000, "bits": 64}, "p2": {"in": 500, "out": 5, "bits": 32}})
        t[0] += 10
        s.feed_counters("sw", {"p1": {"in": 100, "out": 100, "bits": 64}, "p2": {"in": 500, "out": 5, "bits": 32}})      # p1 restarted its counters
        self.assertEqual([p[1:] for p in s.points[("sw", "p1")]], [[10_000, 20_000]], "bytes x 8 / seconds; the restart gave no point")
        self.assertEqual(list(s.points[("sw", "p2")])[0][1:], [1200, 0], "1500 bytes across the 32-bit wrap")

    def test_the_grid_puts_every_port_on_the_same_bins_and_leaves_gaps_unknown(self):
        t = [5000.0]
        s = P.PortSeries(clock=lambda: t[0])
        for i in range(20):
            s._add(("a", "1"), 4800 + i * 10, 1000 * i, 0)
        s._add(("b", "1"), 4999, 7, 9)
        g = s.grid([("a", "1"), ("b", "1"), ("c", "1")], 200, now=5000.0)
        self.assertEqual({len(v[0]) for v in g.values()}, {20})
        self.assertEqual(g[("a", "1")][0][0], 0); self.assertEqual(g[("a", "1")][0][19], 19000)
        self.assertEqual(g[("b", "1")][0][-1], 7); self.assertEqual(g[("b", "1")][0][0], None)
        self.assertEqual(g[("c", "1")][0], [None] * 20, "no readings at all is all unknown, not zero")

    def test_a_bonded_pair_is_one_series_and_a_bin_either_member_missed_is_unknown(self):
        a = ([1, 2, None, 4], [10, 20, 30, 40]); b = ([1, 1, 1, 1], [1, 1, None, 1])
        self.assertEqual(P.add_groups([a, b]), ([2, 3, None, 5], [11, 21, None, 41]))
        self.assertIs(P.add_groups([a]), a)


class Likely(unittest.TestCase):
    N = 60

    def test_the_port_that_follows_the_device_is_likely_noise_is_not_and_a_flat_port_is_not_mentioned(self):
        send = bursts(self.N, 1)
        focus = (send, [1000] * self.N)
        cands = {"Port B": ([0] * self.N, [int(v * 0.9) + 40 for v in send]),                  # what B sends out follows what the device sends in
                 "Port C": ([0] * self.N, bursts(self.N, 99)),                                  # busy but unrelated
                 "Port D": ([0] * self.N, [5000] * self.N)}                                      # flat
        got = P.likely(focus, cands)
        self.assertEqual([x["label"] for x in got["answer"]][:1], ["Port B"])
        b = got["answer"][0]
        self.assertEqual((b["direction"], b["confidence"]), ("from", "likely")); self.assertGreater(b["r"], 0.95); self.assertAlmostEqual(b["share"], 0.9, delta=0.1)
        self.assertNotIn("Port D", [x["label"] for x in got["answer"]])
        self.assertTrue(all(x["label"] != "Port C" or x["confidence"] == "possible" for x in got["answer"]))

    def test_a_sharp_copy_still_matches_when_the_other_port_is_read_one_reading_late_or_early(self):
        """Found on the real box (#241 check): a 30 GB server-to-server copy that stalls and bursts matched nothing, because the two ports' readings were one reading apart."""
        import random
        rnd = random.Random(7)
        quiet = lambda: [rnd.randint(1_000_000, 3_000_000) for _ in range(90)]
        burst = [0] * 72 + [rnd.choice([9e9, 8e9, 2e9, 9.3e9, 1e8, 7e9]) for _ in range(18)]
        sent = [q + b for q, b in zip(quiet(), burst)]
        for name, shifted in (("in step", burst), ("a reading late", [0] + burst[:-1]), ("a reading early", burst[1:] + [0])):
            got = [q + b for q, b in zip(quiet(), shifted)]
            r = P.likely(([float(v) for v in sent], [2e6] * 90), {"Fake Server (Fake-Sw port 4)": ([5e6] * 90, [float(v) for v in got])})
            self.assertEqual([(x["label"], x["confidence"]) for x in r["answer"]], [("Fake Server (Fake-Sw port 4)", "likely")], name)
        elsewhere = [0] * 30 + burst[:60]            # the same shape, but half an hour of readings away: only look-alike, not the same traffic
        r = P.likely(([float(v) for v in sent], [2e6] * 90), {"Fake Server (Fake-Sw port 4)": ([5e6] * 90, [float(q + b) for q, b in zip(quiet(), elsewhere)])})
        self.assertEqual(r["answer"], [], "a copy happening at a different time is not matched (a reading either way is tolerated, not more)")

    def test_traffic_toward_the_device_is_matched_the_other_way_round(self):
        down = bursts(self.N, 5)
        got = P.likely(([100] * self.N, down), {"NAS": (list(down), [0] * self.N)})
        self.assertEqual([(x["label"], x["direction"]) for x in got["answer"]], [("NAS", "to")])

    def test_a_quiet_port_too_little_history_and_no_match_each_say_so_instead_of_guessing(self):
        quiet = P.likely(([10] * self.N, [10] * self.N), {"x": (bursts(self.N, 2), bursts(self.N, 3))})
        self.assertEqual(quiet["answer"], []); self.assertIn("too quiet", quiet["why"])
        short = P.likely((bursts(5, 1), [1000] * 5), {"x": ([0] * 5, bursts(5, 1))})
        self.assertEqual(short["answer"], []); self.assertIn("Not enough history", short["why"])
        none = P.likely((bursts(self.N, 1), [1000] * self.N), {"x": ([0] * self.N, bursts(self.N, 77))})
        self.assertTrue(all(a["confidence"] == "possible" for a in none["answer"]), "unrelated traffic is never called likely")

    def test_gaps_are_ignored_not_counted_as_zero(self):
        send = bursts(self.N, 7)
        follow = [None if i % 5 == 0 else v for i, v in enumerate(send)]
        got = P.likely((send, [1000] * self.N), {"B": ([0] * self.N, follow)})
        self.assertEqual(got["answer"][0]["confidence"], "likely")


class Tuned(unittest.TestCase):
    N = 60

    def test_a_port_carrying_a_sliver_of_a_big_transfer_is_not_named_however_well_the_shapes_match(self):
        big = bursts(self.N, 11)
        got = P.likely((big, [1000] * self.N), {"Real": ([0] * self.N, [int(v * 0.97) for v in big]), "Tiny": ([0] * self.N, [v // 100_000 + 3000 for v in big])})
        self.assertEqual([x["label"] for x in got["answer"]], ["Real"], "the tiny port moves with it but cannot be where 4 Gbit/s goes")

    def test_the_same_traffic_showing_up_in_full_on_many_ports_is_called_broadcast_not_named_port_by_port(self):
        chatter = bursts(self.N, 21)
        cands = {f"Player {i}": ([0] * self.N, [v + 50 * i for v in chatter]) for i in range(4)}
        cands["Unrelated"] = ([0] * self.N, bursts(self.N, 5))
        got = P.likely((chatter, [1000] * self.N), cands)["answer"]
        flood = [x for x in got if x.get("kind") == "flood"]
        self.assertEqual(len(flood), 1); self.assertEqual(flood[0]["direction"], "from")
        self.assertEqual(sorted(flood[0]["ports"]), ["Player 0", "Player 1", "Player 2", "Player 3"])
        self.assertFalse([x for x in got if x["label"].startswith("Player")], "the ports are listed inside the one broadcast line, not each as a destination")

    def test_traffic_split_between_two_destinations_is_not_mistaken_for_a_broadcast(self):
        send = bursts(self.N, 31)
        cands = {"Half A": ([0] * self.N, [v // 2 for v in send]), "Half B": ([0] * self.N, [v // 2 + 7 for v in send])}
        got = P.likely((send, [1000] * self.N), cands)["answer"]
        self.assertEqual(sorted(x["label"] for x in got), ["Half A", "Half B"]); self.assertFalse([x for x in got if x.get("kind") == "flood"])

    def test_a_link_that_carries_everything_is_not_part_of_a_broadcast(self):
        chatter = bursts(self.N, 41)
        cands = {f"Player {i}": ([0] * self.N, list(chatter)) for i in range(3)}
        cands["anything beyond the link to Core"] = ([0] * self.N, [v * 3 for v in chatter])
        got = P.likely((chatter, [1000] * self.N), cands)["answer"]
        self.assertIn("anything beyond the link to Core", [x["label"] for x in got])


if __name__ == "__main__":
    unittest.main()


class Together(unittest.TestCase):
    def series(self, seed, n=90):
        r = random.Random(seed)
        return [r.choice((0, 0, 60_000, 900_000, 3_000_000)) + r.randint(0, 5000) for _ in range(n)]

    def test_unrelated_ports_never_form_a_group_however_many_there_are(self):
        for trial in range(20):
            focus = ([5000] * 90, self.series(1000 + trial))
            pool = {f"p{i}": (self.series(trial * 100 + i), [10] * 90) for i in range(40)}
            self.assertEqual(P.together(focus, pool), [], f"trial {trial}")

    def test_the_real_parts_are_found_among_unrelated_ports(self):
        parts = [self.series(i) for i in (1, 2, 3, 4)]
        total = [sum(v) for v in zip(*parts)]
        pool = {f"part{i}": (p, [10] * 90) for i, p in enumerate(parts)}
        pool.update({f"noise{i}": (self.series(500 + i), [10] * 90) for i in range(30)})
        got = P.together(([5000] * 90, total), pool)
        self.assertEqual([sorted(g["members"]) for g in got], [["part0", "part1", "part2", "part3"]])
        self.assertGreater(got[0]["r"], 0.99)


class HistoryLength(unittest.TestCase):
    def test_how_long_the_box_has_been_reading_a_port_is_the_oldest_reading_of_any_of_its_keys(self):
        t = [1000.0]
        s = P.PortSeries(clock=lambda: t[0])
        self.assertEqual(s.history_seconds([("sw", "Port 1")]), 0.0, "nothing read yet")
        s.feed_rates("sw", {"Port 1": {"in_bps": 5, "out_bps": 5}}, now=940.0)
        s.feed_rates("sw", {"Port 2": {"in_bps": 5, "out_bps": 5}}, now=970.0)
        self.assertEqual(s.history_seconds([("sw", "Port 1")]), 60.0)
        self.assertEqual(s.history_seconds([("sw", "Port 2")]), 30.0)
        self.assertEqual(s.history_seconds([("sw", "Port 2"), ("sw", "Port 1")]), 60.0, "a bonded pair: the older of the two")
