import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import graphs as G  # noqa: E402

GOOD = [{"connection": "nas", "interface": "bond0", "title": "Granite bond"}]


class Clock:
    t = 1_700_000_000.0
    def __call__(self): return self.t


class Rates(unittest.TestCase):
    def make(self, readings, graphs=GOOD):
        clock, it = Clock(), iter(readings)
        saved = G.clean_list(graphs, lambda c: True)
        g = G.Graphs(lambda: saved, lambda cid, names: {n: next(it) for n in names}, clock)
        return g, clock

    def test_two_readings_make_a_rate_in_bits_per_second(self):
        g, clock = self.make([{"in": 1000, "out": 5000, "bits": 64}, {"in": 3000, "out": 5500, "bits": 64}])
        g.tick(); clock.t += 2; g.tick()
        self.assertEqual(g.data()["graphs"][0]["points"][0][1:], [8000, 2000])

    def test_the_links_rated_speed_comes_through_for_the_top_of_the_graph(self):
        g, clock = self.make([{"in": 1, "out": 1, "bits": 64, "speedMbps": 2500}, {"in": 9, "out": 9, "bits": 64, "speedMbps": 2500}])
        g.tick(); clock.t += 1; g.tick()
        self.assertEqual(g.data()["graphs"][0]["speedMbps"], 2500)

    def test_a_32_bit_rollover_is_a_rate_but_a_counter_reset_is_skipped(self):
        r = lambda i, o, b=32: {"in": i, "out": o, "bits": b}
        g, clock = self.make([r(2**32 - 100, 10), r(300, 10), r(5, 5)])
        g.tick(); clock.t += 1; g.tick(); clock.t += 1; g.tick()
        pts = g.data()["graphs"][0]["points"]
        self.assertEqual([p[1] for p in pts], [3200], "rollover counted, the reset to a small number skipped")

    def test_a_missing_interface_shows_why_and_draws_nothing(self):
        g, clock = self.make([{"error": "interface 'bond0' is not on the device any more"}])
        g.tick()
        d = g.data()["graphs"][0]
        self.assertEqual(d["points"], [])
        self.assertIn("not on the device", d["error"])

    def test_the_pace_is_fast_only_while_someone_is_looking(self):
        g, clock = self.make([])
        self.assertEqual(g.interval(), G.SLOW)
        g.viewing(); self.assertEqual(g.interval(), G.FAST)
        clock.t += G.WATCHING_FOR + 1; self.assertEqual(g.interval(), G.SLOW)

    def test_points_older_than_an_hour_and_removed_graphs_are_dropped(self):
        g, clock = self.make([{"in": i * 100, "out": 0, "bits": 64} for i in range(6)])
        g.tick(); clock.t += 1; g.tick()
        clock.t += G.KEEP_SECONDS + 5; g.tick(); clock.t += 1; g.tick()
        self.assertEqual(len(g.points["nas-bond0"]), 2, "the first point aged out; the two new ones stay")
        self.assertTrue(all(p[0] > clock.t - G.KEEP_SECONDS for p in g.points["nas-bond0"]))
        g.load = lambda: []; g.tick()
        self.assertEqual(g.points, {})


class Validation(unittest.TestCase):
    def test_ids_are_made_and_made_unique(self):
        out = G.clean_list(GOOD + GOOD, lambda c: True)
        self.assertEqual([x["id"] for x in out], ["nas-bond0", "nas-bond0-2"])

    def test_bad_lists_are_refused_in_words(self):
        for bad, msg in (("x", "list"), ([{"connection": "nope", "interface": "e"}], "not an SNMP"),
                         ([{"connection": "nas", "interface": ""}], "pick an interface"), (GOOD * 13, "at most")):
            with self.assertRaises(G.Invalid) as cm:
                G.clean_list(bad, lambda c: c == "nas")
            self.assertIn(msg, str(cm.exception))

    def test_title_defaults_to_the_interface_name(self):
        self.assertEqual(G.clean_list([{"connection": "nas", "interface": " eth0 "}], lambda c: True)[0]["title"], "eth0")

    def test_busiest_client_is_a_graph_you_add_once_and_needs_no_interface(self):
        out = G.clean_list([{"kind": "busiest"}], lambda c: False)
        self.assertEqual(out, [{"id": "busiest", "kind": "busiest", "title": "Busiest client"}])
        self.assertEqual(G.clean_list([{"kind": "busiest", "title": " Chatty "}] + GOOD, lambda c: True)[0]["title"], "Chatty")
        with self.assertRaises(G.Invalid) as cm:
            G.clean_list([{"kind": "busiest"}, {"kind": "busiest"}], lambda c: True)
        self.assertIn("only be on the main screen once", str(cm.exception))

    def test_the_busiest_filters_keep_only_what_differs_from_the_defaults_and_are_checked(self):
        full = {"kind": "busiest", "filter": {"wired": True, "wifi": False, "servers": False, "cameras": False, "iot": False, "blacklist": " Fake Ring, aa:bb:cc ", "blacklistOn": False, "floorMbps": 2.5,
                                              "exclude": [{"mac": "AA:BB:CC:00:00:01", "name": "Fake Switch One"}, {"id": "Fake-Sw|7", "name": "Fake Port Seven"}]}}
        got = G.clean_list([full], lambda c: True)[0]["filter"]
        self.assertEqual(got, {"wifi": False, "servers": False, "cameras": False, "iot": False, "blacklist": "Fake Ring, aa:bb:cc", "blacklistOn": False, "floorMbps": 2.5,
                               "exclude": [{"name": "Fake Switch One", "mac": "AA:BB:CC:00:00:01"}, {"name": "Fake Port Seven", "id": "Fake-Sw|7"}]}, "every value comes back; defaults are not stored")
        self.assertNotIn("filter", G.clean_list([{"kind": "busiest", "filter": {"wired": True, "floorMbps": 1, "exclude": []}}], lambda c: True)[0])
        for bad, why in (({"wifi": "no"}, "on or off"), ({"iot": 0}, "on or off"), ({"blacklistOn": "no"}, "on or off"), ({"blacklist": "x" * 501}, "up to 500"), ({"blacklist": 5}, "up to 500"), ({"cameras": "off"}, "on or off"), ({"floorMbps": 0}, "number of Mbit/s"), ({"floorMbps": True}, "number of Mbit/s"), ({"exclude": [{"name": "x"}]}, "MAC address or an id"),
                         ({"exclude": [{"mac": "m"}] * 3 + [{"mac": str(i)} for i in range(60)]}, "up to 50"), ("x", "must be an object")):
            with self.assertRaises(G.Invalid, msg=str(bad)) as cm:
                G.clean_list([{"kind": "busiest", "filter": bad}], lambda c: True)
            self.assertIn(why, str(cm.exception))

    def test_the_sampler_skips_it_and_still_reads_the_interface_graphs_beside_it(self):
        clock, asked = Clock(), []
        saved = G.clean_list([{"kind": "busiest"}] + GOOD, lambda c: True)
        g = G.Graphs(lambda: saved, lambda cid, names: asked.append((cid, names)) or {n: {"in": 1, "out": 1, "bits": 64} for n in names}, clock)
        g.tick()
        self.assertEqual(asked, [("nas", ["bond0"])])
        self.assertEqual([x["id"] for x in g.data()["graphs"]], ["busiest", "nas-bond0"])


if __name__ == "__main__":
    unittest.main()
