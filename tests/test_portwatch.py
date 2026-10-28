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

    def test_a_port_that_only_errors_under_a_big_transfer_is_not_flagged_each_time(self):
        # quiet, then a 10 GbE transfer at minute 20 (300 errors in 15 minutes), quiet, and the same again at minute 100: its normal
        vals, total = [], 0
        for m in range(0, 121, 5):
            if 20 <= m < 35 or 100 <= m < 115:
                total += 100
            vals.append((total, 0, 0))
        q = self.series(5, vals[:23])                                  # minute 110: mid-burst
        self.assertEqual(portwatch.judge(q)["rising"], [], "the same burst as last time is not news")
        louder = vals[:21] + [(vals[20][0] + 1500 * k, 0, 0) for k in range(1, 4)]      # five times the worst before: that is news
        self.assertEqual(portwatch.judge(self.series(5, louder))["rising"], ["errors"])

    def test_link_drops_count_only_on_uplinks_and_servers(self):
        q = self.series(5, [(0, 0, 0)] * 10 + [(0, 0, 1), (0, 0, 3), (0, 0, 6)])
        self.assertEqual(portwatch.judge(q, flaps=True)["rising"], ["flaps"])
        self.assertEqual(portwatch.judge(q, flaps=False)["rising"], [], "a laptop that sleeps drops its port: not news")

    def test_a_few_errors_an_hour_are_not_worth_a_line(self):
        q = self.series(5, [(0, 0, 0)] * 10 + [(2, 0, 0), (4, 0, 0), (6, 0, 0)])
        self.assertEqual(portwatch.judge(q)["rising"], [])

    def test_the_first_half_hour_only_learns(self):
        q = self.series(5, [(0, 0, 0), (100, 0, 0), (300, 0, 0), (900, 0, 0), (2000, 0, 0)])      # 20 minutes: loud, but nothing to compare with
        j = portwatch.judge(q)
        self.assertTrue(j["learning"])
        self.assertEqual(j["rising"], [])

    def test_a_client_port_never_alerts_on_drops_but_still_does_on_errors(self):
        # regression: both sites alerted at night on Apple TV client ports (transmit drops). Owner agreed: drops only matter on uplinks, links between switches and servers.
        drops = self.series(5, [(0, 0, 0)] * 10 + [(0, 40000, 0), (0, 80000, 0), (0, 120000, 0)])
        self.assertEqual(portwatch.judge(drops, False)["rising"], [])
        self.assertEqual(portwatch.judge(drops, True)["rising"], ["drops"])
        errors = self.series(5, [(0, 0, 0)] * 10 + [(40, 0, 0), (80, 0, 0), (120, 0, 0)])
        self.assertEqual(portwatch.judge(errors, False)["rising"], ["errors"])

    def test_drops_and_link_drops_have_their_own_floors(self):
        q = self.series(5, [(0, 0, 0)] * 10 + [(0, 4000, 1), (0, 8000, 2), (0, 12000, 4)])      # the drops minimum was raised from 1,000 to 10,000 per 15 minutes (owner request, after an Apple TV port tripped it)
        self.assertEqual(portwatch.judge(q)["rising"], ["drops", "flaps"])
        mid = self.series(5, [(0, 0, 0)] * 10 + [(0, 400, 0), (0, 900, 0), (0, 1500, 0)])
        self.assertEqual(portwatch.judge(mid)["rising"], [], "1,500 in 15 minutes is a trickle on a gigabit link: not news any more")
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
        self.assertIn("learning what is normal", detail)      # wording changed (owner approved): the line no longer says "half an hour"

    def test_a_flapping_client_port_is_quiet_and_a_flapping_server_port_is_not(self):
        self.w.set_enabled(True)
        laptop, server = self.w.key("sw1", "Port 3"), self.w.key("sw1", "Port 4")
        for m in range(0, 61):
            n = 0 if m < 45 else (m - 45) // 2
            self.w.feed([dev("Core switch", **{"Port 3": (0, 0, 0, 0, n), "Port 4": (0, 0, 0, 0, n)})], ["sw1"], now=m * 60)
        self.assertEqual(self.w.check()[3], {}, "no port is marked as an uplink or server yet, so nothing is flagged")
        self.w.set_flap_ports({server})
        self.assertEqual(self.w.state([laptop])["rising"], [])
        self.assertEqual(self.w.state([server])["rising"], ["flaps"])
        ok, detail, _, extra = self.w.check()
        self.assertTrue(extra.get("warn"))
        self.assertIn("Port 4", detail); self.assertNotIn("Port 3", detail)

    def test_the_line_says_receive_or_transmit_and_how_busy_the_link_was(self):
        busy = lambda keys, secs: {"avgBps": 4_100_000_000, "peakBps": 9_200_000_000}
        w = portwatch.PortWatch(self.paths, traffic=busy)
        w.set_enabled(True)
        for m in range(0, 61):
            rx = 0 if m < 45 else (m - 45) * 700            # receive errors climb, transmit errors stay a trickle
            w.feed([dev("Broad Leaf", **{"SFP+ 2": (rx, 0 if m < 45 else (m - 45) * 2, 0, 0, 0)})], ["gw"], now=m * 60)
        st = w.state([w.key("gw", "SFP+ 2")])
        self.assertEqual(st["split"]["errors"], {"rx": 42000, "tx": 120})
        self.assertEqual(st["traffic"], {"avgBps": 4_100_000_000, "peakBps": 9_200_000_000})
        ok, detail, _, extra = w.check()
        self.assertTrue(extra.get("warn"))
        self.assertIn("42,000 receive, 120 transmit", detail)
        self.assertIn("carrying about 4.1 Gbit/s (peak 9.2 Gbit/s)", detail)

    def test_a_port_says_what_the_other_end_of_its_link_is_doing(self):
        w = portwatch.PortWatch(self.paths)
        w.set_enabled(True)
        a, b = w.key("gw", "SFP+ 2"), w.key("agg", "Port 3")
        w.set_peers({a: (b, "Aggregation, Port 3"), b: (a, "Broad Leaf, SFP+ 2")})
        for m in range(0, 61):
            rx = 0 if m < 45 else (m - 45) * 700
            w.feed([dev("Broad Leaf", **{"SFP+ 2": (rx, 0, 0, 0, 0)}), dev("Aggregation", **{"Port 3": (0, 0, 0, 0, 0)})], ["gw", "agg"], now=m * 60)
        far = w.state([a])["other"]
        self.assertEqual((far["label"], far["state"], far["split"]["errors"]), ("Aggregation, Port 3", "figures", {"rx": 0, "tx": 0}))
        self.assertIn("other end (Aggregation, Port 3): 0 receive, 0 transmit an hour", w.check()[1])
        self.assertIsNone(w.state([w.key("gw", "SFP+ 1")]) and w.state([w.key("gw", "SFP+ 1")])["other"], "a port that is not one end of a link between devices has no other end")
        # the other end gave no counters at all
        w2 = portwatch.PortWatch(self.paths); w2.set_peers({a: (b, "Aggregation, Port 3")})
        for m in range(0, 61):
            w2.feed([dev("Broad Leaf", **{"SFP+ 2": (0 if m < 45 else (m - 45) * 700, 0, 0, 0, 0)})], ["gw"], now=m * 60)
        self.assertEqual(w2.state([a])["other"]["state"], "none")
        self.assertIn("other end (Aggregation, Port 3): no counters", w2.check()[1])

    def test_the_alert_names_what_is_plugged_into_the_port(self):
        w = portwatch.PortWatch(self.paths)
        w.set_enabled(True)
        tv, up = w.key("sw", "Port 2"), w.key("sw", "Port 9")
        w.set_flap_ports([tv])                                              # drops only alert on uplinks, links between switches and servers: pretend this one is a server
        w.set_attached({tv: "Apple TV", up: "Core"})
        w.set_peers({up: (w.key("agg", "Port 1"), "Aggregation, Port 1")})
        for m in range(0, 61):
            n = 0 if m < 45 else (m - 45) * 20000
            w.feed([dev("Theater", **{"Port 2": (0, 0, 0, n, 0)})], ["sw"], now=m * 60)
        detail = w.check()[1]
        self.assertIn("Theater, Port 2 (Apple TV): packet drops rising", detail)
        self.assertEqual(w.page()["rising"][0]["label"], "Theater, Port 2 (Apple TV)")
        self.assertEqual(w.named(up, "Theater, Port 9"), "Theater, Port 9", "a link between devices already says what is at the far end")
        w.set_attached({})
        self.assertIn("Theater, Port 2: packet drops rising", w.check()[1])

    def test_interfaces_the_map_does_not_show_are_forgotten_when_nothing_feeds_them_any_more(self):
        clock = [0.0]
        w = portwatch.PortWatch(self.paths, clock=lambda: clock[0])
        w.set_enabled(True)
        for m in range(0, 5):
            w.feed([dev("Agg", **{"Port 1": (0, 0, 0, 0, 0), "Po1": (0, 0, 0, 0, 0)}), dev("Other", **{"Port 1": (0, 0, 0, 0, 0)})], ["agg", "oth"], now=m * 30)
        w.set_shown({"agg|Port 1", "oth|Port 1"})
        clock[0] = 4 * 30
        self.assertEqual((w.page()["others"]["count"], w.page()["others"]["where"][0]["lastAgoMin"]), (1, 0))
        # a later source stops feeding Po1 (it is read as another device now): after the wait it goes, a shown port never does
        t = 4 * 30 + portwatch.STALE_OTHERS + 1
        clock[0] = t
        w.feed([dev("Agg", **{"Port 1": (0, 0, 0, 0, 0)}), dev("Other", **{"Port 1": (0, 0, 0, 0, 0)})], ["agg", "oth"], now=t)
        self.assertEqual(sorted(w.series), ["agg|Port 1", "oth|Port 1"])

    def test_a_server_network_card_alerts_on_packet_drops_as_well_as_errors(self):
        # regression (found after 1.6.13): only ports the map called servers counted drops; the cards read over SNMP as servers ("snmp:<connection>") never did
        w = portwatch.PortWatch(self.paths)
        w.set_enabled(True)
        for m in range(0, 61):
            w.feed([dev("goliath", **{"eth0": (0, 0, 0, 0 if m < 45 else (m - 45) * 20000, 0)})], ["snmp:g"], now=m * 60)
            w.feed([dev("Theater", **{"Port 2": (0, 0, 0, 0 if m < 45 else (m - 45) * 20000, 0)})], ["sw"], now=m * 60)
        kinds = {f["label"]: f["kinds"] for f in w.findings()}
        self.assertEqual(kinds, {"goliath, eth0": ["drops"]}, "the server's card alerts; the client's port (Theater) does not")

    def test_a_port_whose_device_sleeps_keeps_what_it_learned(self):
        # regression (#316, Office Port 2, a Mac that wakes for backups): the port leaves the map while its link is down, and its history was cleared 30 minutes later
        clock = [0.0]
        w = portwatch.PortWatch(self.paths, clock=lambda: clock[0])
        w.set_enabled(True)
        for m in range(0, 61):
            clock[0] = m * 60
            w.feed([dev("Office", **{"Port 2": (0, 0, 0, 0, 0), "Port 9": (0, 0, 0, 0, 0)})], ["off"], now=m * 60)
        w.set_shown({"off|Port 2", "off|Port 9"})
        asleep = lambda t: (clock.__setitem__(0, t), w.set_shown({"off|Port 9"}), w.feed([dev("Office", **{"Port 9": (0, 0, 0, 0, 0)})], ["off"], now=t))
        asleep(3600 + 40 * 60)                                             # 40 minutes later: the Mac is asleep, the map no longer shows its port
        self.assertIn("off|Port 2", w.series, "kept: it was in use a moment ago")
        self.assertGreaterEqual(len(w.series["off|Port 2"]), 60)
        w.save(clock[0], force=True)
        again = portwatch.PortWatch(self.paths, clock=lambda: clock[0])      # a restart in between keeps the rule
        self.assertIn("off|Port 2", again.used_at)
        asleep(3600 + 25 * 3600)                                           # a day and more with no sign of it: now it is forgotten
        self.assertNotIn("off|Port 2", w.series)

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


class FromSnmp(unittest.TestCase):
    """A switch that is also an SNMP connection gives its error and discard counters over SNMP; the others use UniFi's. Never mixed on one device."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name); os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.w = portwatch.PortWatch(self.paths); self.w.set_enabled(True)
        self.t = [1000.0]
        self.snmp_ok = [True]

    def sampler(self):
        from monitorbox_app import lansampler, portpeers
        uni = lambda name, mac, ip, errs: {"name": name, "mac": mac, "type": "usw", "ip": ip,
                                           "ports": [{"port_idx": 1, "name": "Port 1", "inBps": 1, "outBps": 1, "rx_errors": errs, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0, "link_down_count": 9}]}
        devices = [uni("Core-B", "..:00:00:02", "192.0.2.2", 1_000_000), uni("Rack-C", "..:00:00:03", "192.0.2.3", 2_000_000)]

        def call(mod, method, params, timeout):
            if mod == "unifi-network":
                return {"devices": devices}
            if not self.snmp_ok[0]:
                raise RuntimeError("no answer")
            return {"ports": {"te1/0/1": {"in": 1, "out": 1, "bits": 64, "label": "Port 1", "rxErr": 5, "txErr": 6, "rxDrop": 7, "txDrop": 8}}}
        conns = [{"id": "u", "module": "unifi-network", "host": "192.0.2.1"}, {"id": "s", "module": "snmp", "host": "192.0.2.2"}]
        return lansampler.LanSampler(portpeers.PortSeries(clock=lambda: self.t[0]), lambda: conns, call, clock=lambda: self.t[0], watch=self.w)

    def last(self, dev):
        return list(self.w.series[self.w.key(dev, "Port 1")])[-1][1:]

    def test_snmp_counters_replace_unifis_on_that_device_and_the_others_keep_theirs(self):
        sm = self.sampler()
        sm.tick()
        # errors 5+6, drops 7+8 from SNMP; link drops 9 still from UniFi's port table
        self.assertEqual(self.last("..:00:00:02"), [11, 15, 9, 5, 6, 7, 8])
        self.assertEqual(self.last("..:00:00:03"), [2_000_000, 0, 9, 2_000_000, 0, 0, 0], "Rack-C has no SNMP connection: UniFi's counters")

    def test_an_snmp_switch_that_did_not_answer_is_left_out_not_read_from_unifi(self):
        sm = self.sampler()
        sm.tick()
        self.snmp_ok[0] = False
        self.t[0] += 10
        sm.tick()
        self.assertEqual(self.last("..:00:00:02"), [11, 15, 9, 5, 6, 7, 8], "no mixing of two ways of counting: nothing new for it this round")
        self.assertEqual(self.last("..:00:00:03"), [2_000_000, 0, 9, 2_000_000, 0, 0, 0])


class Servers(unittest.TestCase):
    """The network cards of SNMP servers are watched too, and a server card is the other end of the switch port it plugs into."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name); os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.w = portwatch.PortWatch(self.paths); self.w.set_enabled(True)
        self.t = [1000.0]
        self.calls = []

    def sampler(self, answer=True):
        from monitorbox_app import lansampler, portpeers

        def call(mod, method, params, timeout):
            if mod == "unifi-network":
                return {"devices": [{"name": "Core-B", "mac": "..:00:00:02", "type": "usw", "ip": "192.0.2.2", "ports": []}]}
            self.calls.append(params["connection"]["id"])
            if not answer:
                raise RuntimeError("no answer")
            return {"ports": {"eth0": {"in": 1, "out": 1, "bits": 64, "rxErr": 10, "txErr": 20, "rxDrop": 30, "txDrop": 40}, "docker0": {"in": 1, "out": 1, "bits": 64}}}
        conns = [{"id": "u", "module": "unifi-network", "host": "192.0.2.1"}, {"id": "apollo", "module": "snmp", "host": "192.0.2.77"}]
        return lansampler.LanSampler(portpeers.PortSeries(clock=lambda: self.t[0]), lambda: conns, call, clock=lambda: self.t[0], watch=self.w)

    def device_sampler(self, unifi_names, conn_name="Core-B", conn_host="192.0.2.99"):
        from monitorbox_app import lansampler, portpeers
        port = {"name": "Port 1", "rx_errors": 1, "tx_errors": 1, "rx_dropped": 1, "tx_dropped": 1, "link_down_count": 0}
        devs = [{"name": n, "mac": f"..:00:00:0{i}", "type": "usw", "ip": f"192.0.2.{i + 2}", "ports": [dict(port)]} for i, n in enumerate(unifi_names)]
        bad = {"rxErr": 10, "txErr": 20, "rxDrop": 30, "txDrop": 40, "in": 1, "out": 1, "bits": 64}

        def call(mod, method, params, timeout):
            if mod == "unifi-network":
                return {"devices": devs}
            self.calls.append(params["connection"]["id"])
            return {"ports": {"Port 1": dict(bad), "Po1": dict(bad), "Po2": dict(bad)}}
        conns = [{"id": "u", "module": "unifi-network", "host": "192.0.2.1"}, {"id": "swc", "name": conn_name, "module": "snmp", "host": conn_host}]
        return lansampler.LanSampler(portpeers.PortSeries(clock=lambda: self.t[0]), lambda: conns, call, clock=lambda: self.t[0], watch=self.w)

    def test_an_snmp_connection_at_another_address_is_matched_to_the_switch_with_its_name(self):
        self.device_sampler(["Core-B"]).tick()
        self.assertEqual(sorted(self.w.series), ["..:00:00:00|Port 1"], "one reader for the switch: its UniFi port, with the SNMP counters; not a second set of interfaces")
        self.assertEqual(list(self.w.series["..:00:00:00|Port 1"])[-1][1:3], [30, 70], "the SNMP counters are the ones used")

    def card_sampler(self, reply):
        """A server whose answer is reply() (a dict of cards), read every round."""
        from unittest import mock
        from monitorbox_app import lansampler, portpeers
        mock.patch.object(lansampler, "SERVER_EVERY", 1).start(); self.addCleanup(mock.patch.stopall)
        other = {"name": "Other", "mac": "..:09:09:09", "type": "usw", "ip": "192.0.2.50", "ports": []}       # a UniFi device that is not the server
        call = lambda mod, method, params, timeout: {"devices": [other]} if mod == "unifi-network" else reply()
        conns = [{"id": "u", "module": "unifi-network", "host": "192.0.2.1"}, {"id": "nas", "name": "NAS", "module": "snmp", "host": "192.0.2.77"}]
        return lansampler.LanSampler(portpeers.PortSeries(clock=lambda: self.t[0]), lambda: conns, call, clock=lambda: self.t[0], watch=self.w)

    def test_a_server_card_with_a_link_is_a_counted_port_one_without_is_not_and_a_bond_is_skipped(self):
        card = lambda **kw: {"in": 1, "out": 1, "bits": 64, "rxErr": 0, "txErr": 0, "rxDrop": 0, "txDrop": 0, **kw}
        sm = self.card_sampler(lambda: {"ports": {"eth0": card(up=True, bond=["bond0"]), "eth1": card(up=True, bond=["bond0"]), "eth2": card(up=False), "bond0": card(up=True, stacked=True)}})
        sm.tick()
        page = self.w.page()
        self.assertEqual(sorted(w["label"] for w in page["watched"]), ["NAS, eth0", "NAS, eth1"], "the two cards with a link; the unused card is read quietly, the bond is not a port")
        self.assertEqual(page["cards"], 2)
        self.assertEqual(page["others"]["names"], ["NAS, eth2"])
        self.assertEqual(self.w.named(self.w.key("snmp:nas", "eth1"), "NAS, eth1"), "NAS, eth1 (in bond0)")
        self.assertNotIn(self.w.key("snmp:nas", "bond0"), self.w.series)

    def test_the_box_counts_link_drops_on_a_server_card_from_its_last_change_time(self):
        state = {"up": True, "ago": 5000, "uptime": 90000}
        reply = lambda: {"uptimeS": state["uptime"], "ports": {"eth0": {"in": 1, "out": 1, "bits": 64, "rxErr": 0, "txErr": 0, "rxDrop": 0, "txDrop": 0, "up": state["up"], "changedAgo": state["ago"]}}}
        sm = self.card_sampler(reply)
        key = self.w.key("snmp:nas", "eth0")
        flaps = lambda: list(self.w.series[key])[-1][3]
        step = lambda **kw: (state.update(kw), self.t.__setitem__(0, self.t[0] + 30), sm.tick())
        sm.tick(); self.assertEqual(flaps(), 0)
        step(up=False, ago=5, uptime=90030); self.assertEqual(flaps(), 1, "the link went down")
        step(up=True, ago=5, uptime=90060); self.assertEqual(flaps(), 1, "coming back up ends the drop, it is not another")
        step(up=True, ago=10, uptime=90090); self.assertEqual(flaps(), 2, "up before, up now, changed in between: down and up again")
        step(up=True, ago=40, uptime=90120); self.assertEqual(flaps(), 2, "no change, no drop")
        step(up=False, ago=3, uptime=100); self.assertEqual(flaps(), 2, "the whole device restarted: every link time started over, that is not a drop")
        self.w.save(self.t[0], force=True)
        again = portwatch.PortWatch(self.paths, clock=lambda: self.t[0])
        self.assertEqual(again.last_flaps(key), 2, "a restarted box carries on from the count it had")

    def test_a_connection_is_the_switch_whose_address_one_of_its_interfaces_has_whatever_it_is_called(self):
        sm = self.device_sampler(["Core A", "Core B"], conn_name="Unrelated", conn_host="192.0.2.99")      # UniFi addresses: ..:00:00:00 (Core A) and ..:00:00:01 (Core B)
        inner = sm.call
        sm.call = lambda mod, method, params, timeout: ({**inner(mod, method, params, timeout), "sysName": "Nothing-alike", "macs": ["..:aa:bb:cc", "..:00:00:01"]} if mod == "snmp" else inner(mod, method, params, timeout))
        sm.tick()
        self.assertEqual(sorted(k for k in self.w.series if k.startswith("snmp:")), [], "its first read told the box which switch it is")
        self.t[0] += 10; sm.tick()
        self.assertEqual(sorted(k for k in self.w.series if k.startswith("snmp:")), [], "not kept as a server")
        self.assertEqual(list(self.w.series["..:00:00:01|Port 1"])[-1][1:3], [30, 70], "Core B has the SNMP counters; Core A keeps UniFi's own")

    def test_a_round_where_unifi_gave_no_devices_changes_nothing(self):
        # regression (screenshots, 1.6.15): "matches 0 of 0 UniFi devices" - with no device list every SNMP switch was read as a server
        sm = self.device_sampler(["Core B"], conn_name="Core-B", conn_host="192.0.2.99")
        sm.tick()
        before = sorted(self.w.series)
        inner = sm.call
        sm.call = lambda mod, method, params, timeout: ({"devices": []} if mod == "unifi-network" else inner(mod, method, params, timeout))
        self.t[0] += 10; sm.tick()
        self.assertEqual(sorted(self.w.series), before, "nothing read as a server, nothing forgotten")
        self.assertTrue(sm.status["unifiEmpty"])
        sm.call = inner
        self.t[0] += 10; sm.tick()
        self.assertEqual(sorted(self.w.series), before)
        self.assertFalse(sm.status["unifiEmpty"])

    def test_bonds_teams_port_channels_and_vlan_sub_interfaces_are_not_ports_of_their_own(self):
        from monitorbox_app import lansampler
        for name in ("bond0", "Bond1", "team0", "vlan20", "Po12", "port-channel3", "eth0.100", "enp3s0.20", "ae0", "dummy0", "lxdbr0", "sit0", "virbr0", "docker0"):
            self.assertTrue(lansampler.stacked(name), name)
        for name in ("eth0", "eth1", "enp3s0", "Port 1", "SFP+ 2", "ens1f0np0", "lo", "br0"):
            self.assertFalse(lansampler.stacked(name), name)
        sm = self.device_sampler(["Core B"], conn_name="NAS", conn_host="192.0.2.99")
        real = {"in": 1, "out": 1, "bits": 64, "rxErr": 1, "txErr": 1, "rxDrop": 1, "txDrop": 1}
        other = {"name": "Other", "mac": "..:09:09:09", "type": "usw", "ip": "192.0.2.50", "ports": []}       # a UniFi device that is not the NAS (an empty list would now skip the round)
        sm.call = lambda mod, method, params, timeout: ({"devices": [other]} if mod == "unifi-network" else {"ports": {n: dict(real) for n in ("eth0", "eth1", "bond0", "eth0.100")}})
        sm.tick()
        self.assertEqual(sorted(k for k in self.w.series if k.startswith("snmp:")), ["snmp:swc|eth0", "snmp:swc|eth1"], "the two cards that make up the bond are watched; the bond and its VLAN are not")

    def test_interface_addresses_that_fit_two_devices_or_none_do_not_decide(self):
        sm = self.device_sampler(["Core A", "Core B"], conn_name="Unrelated", conn_host="192.0.2.99")
        inner = sm.call
        sm.call = lambda mod, method, params, timeout: ({**inner(mod, method, params, timeout), "macs": ["..:00:00:00", "..:00:00:01"]} if mod == "snmp" else inner(mod, method, params, timeout))
        sm.tick()
        self.assertEqual(sorted(k for k in self.w.series if k.startswith("snmp:")), ["snmp:swc|Port 1"], "two devices claim it: stays a server (its port-channels Po1 and Po2 are no longer listed as ports of their own)")

    def test_a_connection_whose_own_name_is_the_switchs_is_read_as_the_switch_from_the_next_round(self):
        from monitorbox_app import lansampler
        sm = self.device_sampler(["Core B"], conn_name="Primary link", conn_host="192.0.2.99")
        inner = sm.call
        sm.call = lambda mod, method, params, timeout: ({**inner(mod, method, params, timeout), "sysName": "CoreB"} if mod == "snmp" else inner(mod, method, params, timeout))
        sm.tick()
        self.assertEqual(sorted(k for k in self.w.series if k.startswith("snmp:")), [], "its first read told the box who it is: nothing is kept as a server")
        self.t[0] += 10; sm.tick()
        self.assertEqual(sorted(self.w.series), ["..:00:00:00|Port 1"])
        self.assertEqual(list(self.w.series["..:00:00:00|Port 1"])[-1][1:3], [30, 70], "from then on it is the switch, with its SNMP counters")
        self.assertEqual(lansampler.squash("Switch 2"), lansampler.squash("Switch2"))

    def test_a_device_read_as_a_server_says_why_and_what_unifi_calls_its_devices(self):
        sm = self.device_sampler(["Core B"], conn_name="Primary link", conn_host="192.0.2.99")
        inner = sm.call
        down = lambda r: {**r, "sysName": "Chassis-7", "ports": {n: {**v, "up": False} for n, v in r["ports"].items()}}       # cards with no link are the "other interfaces"; cards with a link are counted ports now
        sm.call = lambda mod, method, params, timeout: (down(inner(mod, method, params, timeout)) if mod == "snmp" else inner(mod, method, params, timeout))
        sm.tick()
        self.w.set_shown({"..:00:00:00|Port 1"})
        others = self.w.page()["others"]
        self.assertEqual(others["unifiNames"], ['Core B (as "coreb")'])
        why = others["where"][0]["why"]
        self.assertIn("name \"Primary link\" (compared as \"primarylink\") matches 0 of 1 UniFi devices", why)
        self.assertIn("its own name \"Chassis-7\" (compared as \"chassis7\") matches 0", why)

    def test_a_name_two_devices_share_does_not_match_so_nothing_is_merged_by_guess(self):
        self.device_sampler(["Core-B", "core-b"]).tick()
        self.assertIn("snmp:swc|Port 1", self.w.series, "read on its own, as a server")

    def test_a_servers_cards_are_read_every_third_round_and_only_the_ones_with_counters(self):
        sm = self.sampler()
        for _ in range(4):
            sm.tick(); self.t[0] += 10
        self.assertEqual(self.calls, ["apollo", "apollo"], "rounds 1 and 4: every third round, not every one")
        self.assertEqual(list(self.w.series), [self.w.key("snmp:apollo", "eth0")], "a card with no error counters has nothing to watch")
        self.assertEqual(self.w.labels[self.w.key("snmp:apollo", "eth0")], "apollo, eth0")
        self.assertEqual(list(self.w.series[self.w.key("snmp:apollo", "eth0")])[-1][1:], [30, 70, 0, 10, 20, 30, 40], "history is held between reads, not forgotten")

    def test_nothing_is_read_while_the_watch_is_off(self):
        self.w.set_enabled(False)
        self.sampler().tick()
        self.assertEqual(self.calls, [])

    def test_a_server_that_does_not_answer_keeps_what_was_learned(self):
        sm = self.sampler()
        sm.tick()
        sm2 = self.sampler(answer=False); sm2.rounds = 3
        self.t[0] += 30; sm2.tick()
        self.assertIn(self.w.key("snmp:apollo", "eth0"), self.w.series)

    def test_marking_a_switch_port_known_silences_its_server_card_too(self):
        sw, nic = self.w.key("sw1", "Port 5"), self.w.key("snmp:apollo", "eth0")
        self.w.set_peers({sw: (nic, "apollo, eth0"), nic: (sw, "Core, Port 5")})
        self.w.set_known([sw], True)
        self.assertEqual(self.w.known(), {sw, nic})
        self.w.set_known([sw], False)
        self.assertEqual(self.w.known(), set())

    def test_the_map_pairs_a_server_card_with_its_switch_port_by_hardware_address(self):
        from types import SimpleNamespace
        from monitorbox_app import server
        me = SimpleNamespace(portwatch=self.w, last_sources=[{"connection": "apollo", "module": "snmp", "report": {"ports": [{"name": "eth0", "mac": "AA:BB:CC:00:11:22"}, {"name": "eth1", "mac": "aa:bb:cc:00:11:33"}]}}])
        m = {"nodes": [{"id": "sw1", "name": "Core-B", "link": None, "ports": [{"port": "5", "keys": [["sw1", "Port 5"]], "macs": ["aa:bb:cc:00:11:22"], "server": True}, {"port": "6", "keys": [["sw1", "Port 6"]], "macs": ["de:ad:be:ef:00:01"]}]}]}
        server.App.annotate_ports(me, m)
        self.assertEqual(self.w.peers[self.w.key("sw1", "Port 5")], (self.w.key("snmp:apollo", "eth0"), "apollo, eth0"))
        self.assertEqual(self.w.peers[self.w.key("snmp:apollo", "eth0")], (self.w.key("sw1", "Port 5"), "Core-B, Port 5"))
        self.assertNotIn(self.w.key("sw1", "Port 6"), self.w.peers, "a port with something else on it has no server card at the other end")

    def test_the_map_counts_its_switch_ports_whether_or_not_the_watch_is_on(self):
        from types import SimpleNamespace
        from monitorbox_app import server
        me = SimpleNamespace(portwatch=self.w, last_sources=[])
        m = {"counts": {"devices": 2, "wired": 29, "wifi": 100},
             "nodes": [{"id": "agg", "name": "Agg", "link": None, "ports": [{"port": "1", "keys": [["agg", "Port 1"]]}, {"port": "2+3", "keys": [["agg", "Port 2"], ["agg", "Port 3"]]}]},
                       {"id": "sw", "name": "Sw", "link": {"to": "Agg", "keys": {"self": ["sw", "SFP 1"], "parent": ["agg", "Port 1"]}}, "ports": [{"port": "5", "keys": [["sw", "Port 5"]]}]}]}
        for on in (True, False):
            self.w.set_enabled(on)
            server.App.annotate_ports(me, m)
            self.assertEqual(m["counts"]["ports"], 5, "Port 1 on Agg is both a used port and a link end: counted once; a bonded pair is two ports, not one client")
            self.assertEqual(m["counts"]["wired"], 29)


class AccessPointUplinks(unittest.TestCase):
    def test_the_switch_end_of_an_access_points_cable_counts_even_though_the_access_point_reports_no_port(self):
        # regression (screenshots): Aggregation ports 7, 8 and 16 (Wi-Fi access points) were read but not counted: 50 on the map footer, 47 on the Port errors page
        from types import SimpleNamespace
        from monitorbox_app import server
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        paths = Paths(d.name); os.makedirs(os.path.dirname(paths.config), exist_ok=True)
        w = portwatch.PortWatch(paths)
        w.set_enabled(True)
        me = SimpleNamespace(portwatch=w, last_sources=[])
        m = {"nodes": [{"id": "agg", "name": "Agg", "link": None, "ports": []},
                       {"id": "ap", "name": "Hallway", "kind": "ap", "link": {"to": "Agg", "speedMbps": 2500, "keys": {"self": None, "parent": ["agg", "Port 8"]}}, "ports": []}]}
        server.App.annotate_ports(me, m)
        self.assertIn("agg|Port 8", w.shown)
        self.assertIn("agg|Port 8", w.flap_ports, "an uplink: link drops and packet drops count")
        self.assertEqual(w.speeds["agg|Port 8"], 2500)


class Busy(unittest.TestCase):
    def test_the_port_history_says_how_busy_a_port_was(self):
        from monitorbox_app import portpeers
        t = [1000.0]
        series = portpeers.PortSeries(clock=lambda: t[0])
        for i, (rin, rout) in enumerate([(100, 50), (300, 70), (200, 90)]):
            series.feed_rates("sw1", {"Port 1": {"in_bps": rin, "out_bps": rout}, "Port 2": {"in_bps": 10, "out_bps": 1000}}, 1000.0 - 20 + i * 10)
        one = series.recent([("sw1", "Port 1")], 900)
        self.assertEqual(one, {"avgBps": 200, "peakBps": 300})
        pair = series.recent([("sw1", "Port 1"), ("sw1", "Port 2")], 900)
        self.assertEqual(pair["avgBps"], 1070)             # the busier direction: out, 70 + 1000
        self.assertIsNone(series.recent([("sw9", "Port 1")], 900))
        self.assertEqual(portwatch.bps_words(9_200_000_000), "9.2 Gbit/s"); self.assertEqual(portwatch.bps_words(2_500_000), "2.5 Mbit/s")


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


class Restart(unittest.TestCase):
    """#297: after a restart the check must not report Unknown while the first readings are on their way, and what each port normally does is remembered."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.now = 1_000_000.0
        self.w = portwatch.PortWatch(self.paths, clock=lambda: self.now)
        self.w.set_enabled(True)

    def second(self):
        return portwatch.PortWatch(self.paths, clock=lambda: self.now)

    def feed(self, w, minutes, errs=lambda m: 0):
        for m in range(minutes + 1):
            self.now = 1_000_000.0 + m * 60
            w.feed([dev("Core switch", **{"Port 5": (errs(m), 0, 0, 0, 0)})], ["sw1"], now=self.now)

    def test_before_the_first_readings_the_check_is_starting_not_unknown(self):
        ok, detail, _, extra = self.w.check()
        self.assertIsNone(ok)
        self.assertTrue(extra.get("starting"))
        self.assertEqual(detail, "waiting for the first port readings")

    def test_if_no_readings_ever_come_it_is_unknown_after_the_wait(self):
        self.now += portwatch.FIRST_READINGS + 1
        ok, detail, _, extra = self.w.check()
        self.assertIsNone(ok)
        self.assertFalse(extra.get("starting"))
        self.assertEqual(detail, "no switch port counters to read yet")

    def test_which_ports_the_map_showed_survives_a_restart_so_the_count_is_right_at_once(self):
        self.feed(self.w, 40)
        self.w.feed([dev("Core switch", **{"Port 5": (0, 0, 0, 0, 0), "Port 6": (0, 0, 0, 0, 0)})], ["sw1"], now=self.now)
        self.assertEqual(len(self.w.series), 2)
        self.w.set_shown({"sw1|Port 5"}, {"sw1|Port 5"}, set())
        self.w.set_speeds({"sw1|Port 5": 10000})
        self.w.save(self.now, force=True)
        again = self.second()
        self.assertTrue(again.page()["ready"])
        self.assertEqual((again.page()["ports"], again.page()["inUse"]), (1, 1), "only the shown port, not the other one that is read")
        self.assertEqual(again.speeds, {"sw1|Port 5": 10000})
        self.assertEqual(again.only_for("sw1"), ["Port 5"])
        self.assertIsNone(again.only_for("nothing"))
        self.assertFalse(self.second().__class__(Paths(tempfile.mkdtemp()), clock=lambda: self.now).page()["ready"], "no map known yet says so")

    def test_the_learned_history_survives_a_restart(self):
        self.feed(self.w, 40)
        self.w.save(self.now, force=True)
        self.assertEqual(oct(os.stat(self.w.history_path).st_mode & 0o777), "0o600")
        again = self.second()
        self.assertEqual(again.restored, 1)
        self.now += 60
        self.assertTrue(again.check()[0] is None and again.check()[3].get("starting"), "readings not in yet: still starting")
        self.now += 30
        again.feed([dev("Core switch", **{"Port 5": (0, 0, 0, 0, 0)})], ["sw1"], now=self.now)
        ok, detail, _, extra = again.check()
        self.assertTrue(ok)
        self.assertNotIn("learning", detail, "forty minutes of history were kept: nothing to learn again")

    def test_a_rise_after_a_restart_is_still_caught(self):
        self.feed(self.w, 60, lambda m: 0 if m < 45 else (m - 45) * 40)
        self.w.save(self.now, force=True)
        again = self.second()
        self.assertEqual(again.restored, 1)
        self.now += 60
        again.feed([dev("Core switch", **{"Port 5": (600, 0, 0, 0, 0)})], ["sw1"], now=self.now)
        self.assertTrue(again.check()[3].get("warn") or again.check()[0] is True)

    def test_old_or_broken_history_is_ignored(self):
        self.feed(self.w, 40)
        self.w.save(self.now, force=True)
        self.now += portwatch.KEEP + 10
        self.assertEqual(self.second().restored, 0)
        with open(self.w.history_path, "w") as f:
            f.write("{not json")
        self.assertEqual(self.second().restored, 0)

    def test_turning_it_off_removes_the_saved_history(self):
        self.feed(self.w, 40)
        self.w.save(self.now, force=True)
        self.assertTrue(os.path.exists(self.w.history_path))
        self.w.set_enabled(False)
        self.w.forget()
        self.assertFalse(os.path.exists(self.w.history_path))
        self.assertEqual(self.second().restored, 0)


class OnByDefault(unittest.TestCase):
    """#295: Port errors is on by default where there is a switch to read, and stays off when switched off by hand."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.have = [True]
        self.w = portwatch.PortWatch(self.paths, available=lambda: self.have[0])

    def test_on_when_there_is_a_switch_to_read_and_nobody_chose(self):
        self.assertTrue(self.w.enabled())
        self.assertFalse(self.w.chosen())

    def test_off_when_there_is_nothing_to_read(self):
        self.have[0] = False
        self.assertFalse(self.w.enabled())

    def test_switching_it_off_by_hand_stays_off(self):
        self.w.set_enabled(False)
        self.assertFalse(self.w.enabled())
        self.assertTrue(self.w.chosen())
        self.assertFalse(portwatch.PortWatch(self.paths, available=lambda: True).enabled(), "a restart does not switch it back on")

    def test_the_page_lists_rising_ports_and_the_ones_not_alerting(self):
        for m in range(61):
            self.w.feed([dev("Core switch", **{"Port 5": (0 if m < 45 else (m - 45) * 40, 0, 0, 0, 0), "Port 6": (0, 0, 0, 0, 0)})], ["sw1"], now=m * 60)
        page = self.w.page()
        self.assertEqual([r["label"] for r in page["rising"]], ["Core switch, Port 5"])
        self.assertTrue(page["rising"][0]["alert"])
        self.w.set_known([page["rising"][0]["key"]], True)
        page = self.w.page()
        self.assertEqual(page["rising"], [])
        self.assertEqual([r["label"] for r in page["off"]], ["Core switch, Port 5"])
        self.assertFalse(page["off"][0]["alert"])
        self.w.set_known([page["off"][0]["key"]], False)
        self.assertEqual(len(self.w.page()["rising"]), 1, "ticking it again brings it back")


class Counted(unittest.TestCase):
    """The count on the Port errors page is the ports in use that the map shows, not every port a switch reports."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.w = portwatch.PortWatch(self.paths)
        self.w.set_enabled(True)
        self.w.feed([dev("Core switch", **{f"Port {i}": (0, 0, 0, 0, 0) for i in range(1, 9)})], ["sw1"], now=0)

    def test_every_port_is_counted_until_the_map_says_which_are_in_use(self):
        self.assertEqual(self.w.page()["ports"], 8)

    def test_only_the_ports_in_use_are_counted_once_the_map_says_so(self):
        self.w.set_shown({self.w.key("sw1", "Port 1"), self.w.key("sw1", "Port 2")})
        self.assertEqual(self.w.page()["ports"], 2)
        self.assertIn("(0 of 2 ports", self.w.check()[1])

    def test_a_map_that_matches_nothing_does_not_hide_every_port(self):
        self.w.set_shown({"other|Port 1"})
        self.assertEqual(self.w.page()["ports"], 8)


class Links(unittest.TestCase):
    """#293: a link that has been up for an hour is expected up; when it goes down that is a Degraded heads-up. Never for ordinary client ports."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.t = 1_000_000.0
        self.w = portwatch.PortWatch(self.paths, clock=lambda: self.t)
        self.w.set_enabled(True)
        self.up = {"Port 1": True, "Port 2": True, "Port 3": False}

    def round(self, minutes, **change):
        self.up.update(change)
        for _ in range(minutes):
            self.t += 60
            self.w.feed([{"name": "Core switch", "ports": [{"name": n, "up": u, "rx_errors": 0, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0} for n, u in self.up.items()]}],
                        ["sw1"], now=self.t)

    def uplinks(self, *names):
        self.w.set_flap_ports({self.w.key("sw1", n) for n in names})

    def test_a_link_up_for_an_hour_that_drops_is_a_heads_up_not_a_failure(self):
        self.uplinks("Port 1")
        self.round(65)
        self.assertEqual(self.w.downs(), [])
        self.round(3, **{"Port 1": False})
        ok, detail, _, extra = self.w.check()
        self.assertIs(ok, True)
        self.assertTrue(extra.get("warn"))
        self.assertIn("Core switch, Port 1: link is down (was up", detail)

    def test_a_link_that_has_not_been_up_an_hour_is_not_expected(self):
        self.uplinks("Port 1")
        self.round(30)
        self.round(3, **{"Port 1": False})
        self.assertEqual(self.w.downs(), [])

    def test_a_port_that_was_never_up_stays_quiet(self):
        self.uplinks("Port 1", "Port 3")
        self.round(120)
        self.assertEqual(self.w.downs(), [], "an unplugged card is not a problem")

    def test_an_ordinary_client_port_never_raises_it(self):
        self.uplinks("Port 1")                                  # Port 2 is a laptop's port
        self.round(65)
        self.round(5, **{"Port 2": False})
        self.assertEqual(self.w.downs(), [], "a laptop that sleeps is not news")

    def test_a_short_blip_waits_for_the_confirmation_time(self):
        self.uplinks("Port 1")
        self.round(65)
        self.up["Port 1"] = False
        self.t += 30
        self.w.feed([{"name": "Core switch", "ports": [{"name": "Port 1", "up": False, "rx_errors": 0, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0}]}], ["sw1"], now=self.t)
        self.assertEqual(self.w.downs(), [], "down for 30 seconds is not yet worth a line")

    def test_not_coming_back_forgets_it_until_the_link_lights_again(self):
        self.uplinks("Port 1")
        self.round(65)
        self.round(3, **{"Port 1": False})
        key = self.w.downs()[0]["key"]
        self.w.set_gone([key], True)
        self.assertEqual(self.w.downs(), [])
        self.round(3, **{"Port 1": True})
        self.assertNotIn(key, self.w._gone(), "it lit again, so the mark is gone")
        self.round(3, **{"Port 1": False})
        self.assertEqual(self.w.downs(), [], "and it is not expected again until it has been up for an hour")
        self.round(3, **{"Port 1": True})
        self.round(65)
        self.round(3, **{"Port 1": False})
        self.assertEqual(len(self.w.downs()), 1)

    def test_the_alert_tick_silences_it(self):
        self.uplinks("Port 1")
        self.round(65)
        self.round(3, **{"Port 1": False})
        self.w.set_known([self.w.downs()[0]["key"]], True)
        self.assertEqual(self.w.downs(), [])

    def test_both_ends_of_one_cable_are_one_line(self):
        w = self.w
        self.t = 2_000_000.0
        def feed(up):
            self.t += 60
            w.feed([{"name": "Core switch", "ports": [{"name": "Port 1", "up": up, "rx_errors": 0, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0}]},
                    {"name": "Goliath", "ports": [{"name": "eth0", "up": up, "rx_errors": 0, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0}]}], ["sw1", "snmp:srv"], now=self.t)
        a, b = w.key("sw1", "Port 1"), w.key("snmp:srv", "eth0")
        w.set_flap_ports({a})
        w.set_peers({a: (b, "Goliath, eth0"), b: (a, "Core switch, Port 1")})
        for _ in range(65):
            feed(True)
        for _ in range(3):
            feed(False)
        self.assertEqual(len(w.downs()), 1)

    def test_the_expectation_survives_a_restart(self):
        self.uplinks("Port 1")
        self.round(65)
        self.w.save(self.t, force=True)
        again = portwatch.PortWatch(self.paths, clock=lambda: self.t)
        self.assertTrue(again.links[again.key("sw1", "Port 1")]["expected"])


class Outage(unittest.TestCase):
    """A switch controller that answers with only some of its devices (a restart, a failed read) must not wipe what was learned about the others."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.paths = Paths(self.d.name)
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        self.w = portwatch.PortWatch(self.paths)
        self.w.set_enabled(True)

    def test_a_partial_answer_keeps_the_history_of_devices_that_did_not_answer(self):
        two = [dev("Core switch", **{"Port 1": (0, 0, 0, 0, 0)}), dev("Garage switch", **{"Port 1": (0, 0, 0, 0, 0)})]
        for m in range(40):
            self.w.feed(two, ["sw1", "sw2"], now=m * 60)
        self.w.feed(two[:1], ["sw1"], now=41 * 60)                      # only one device answered this time
        self.assertGreaterEqual(len(self.w.series[self.w.key("sw2", "Port 1")]), 2, "the device that did not answer keeps its history")
        self.w.feed(two, ["sw1", "sw2"], now=42 * 60)
        j = portwatch.judge(list(self.w.series[self.w.key("sw2", "Port 1")]))
        self.assertFalse(j["learning"], "and it is still not learning from scratch")

    def test_a_port_that_is_gone_from_a_device_that_answered_is_forgotten(self):
        for m in range(5):
            self.w.feed([dev("Core switch", **{"Port 1": (0, 0, 0, 0, 0), "Port 2": (0, 0, 0, 0, 0)})], ["sw1"], now=m * 60)
        self.w.feed([dev("Core switch", **{"Port 1": (0, 0, 0, 0, 0)})], ["sw1"], now=6 * 60)
        self.assertNotIn(self.w.key("sw1", "Port 2"), self.w.series)

    def test_a_device_not_seen_for_a_day_is_forgotten(self):
        self.w.feed([dev("Old switch", **{"Port 1": (0, 0, 0, 0, 0)})], ["old"], now=0)
        self.w.feed([dev("Core switch", **{"Port 1": (0, 0, 0, 0, 0)})], ["sw1"], now=portwatch.KEEP + 100)
        self.assertNotIn(self.w.key("old", "Port 1"), self.w.series)

    def test_an_unreadable_config_for_a_moment_does_not_count_as_switched_off(self):
        self.assertFalse(self.w.switched_off())
        self.w.set_enabled(False)
        self.assertTrue(self.w.switched_off())
        os.remove(self.paths.config)
        self.assertFalse(self.w.switched_off(), "no config is not 'switched off by hand'")


class CountedSplit(unittest.TestCase):
    def test_the_count_says_what_it_is_made_of(self):
        d = tempfile.TemporaryDirectory(); w = portwatch.PortWatch(Paths(d.name)); self.addCleanup(d.cleanup)
        os.makedirs(os.path.dirname(w.paths.config), exist_ok=True)
        w.set_enabled(True)
        w.feed([dev("Core", **{f"Port {i}": (0, 0, 0, 0, 0) for i in range(1, 7)})], ["sw1"], now=0)
        k = lambda n: w.key("sw1", f"Port {n}")
        w.set_shown({k(1), k(2), k(3), k(4)}, used={k(1), k(2), k(3)}, link_ends={k(4)})
        page = w.page()
        self.assertEqual((page["ports"], page["inUse"], page["onLinks"]), (4, 3, 1), "ports 5 and 6 are empty: read, not counted")
        self.assertEqual([x["label"] for x in page["watched"]], ["Core, Port 1", "Core, Port 2", "Core, Port 3", "Core, Port 4"], "the page can list exactly what it counts")
        self.assertEqual({k: page["others"][k] for k in ("count", "names")}, {"count": 2, "names": ["Core, Port 5", "Core, Port 6"]}, "and what it reads but does not count")
        self.assertEqual([(g["from"], g["id"], g["count"]) for g in page["others"]["where"]], [("Core", "sw1", 2)], "and which device they come from")

    def test_a_counter_going_backwards_is_counted_and_shown(self):
        d = tempfile.TemporaryDirectory(); w = portwatch.PortWatch(Paths(d.name)); self.addCleanup(d.cleanup)
        os.makedirs(os.path.dirname(w.paths.config), exist_ok=True)
        w.set_enabled(True)
        for t, v in ((0, 10), (60, 20), (120, 5), (180, 9)):            # the drop counter falls from 20 to 5
            w.feed([dev("Core", **{"Port 1": (0, 0, v, 0, 0)})], ["sw1"], now=t)
        row = w.page()["watched"][0]
        self.assertEqual((row["resets"], row["resetKind"]), (1, "packet drops"))
        self.assertEqual(row["minutes"], 1, "its history started again at the reset")


class BySpeed(unittest.TestCase):
    """The minimum for errors and drops scales with the link speed: the same count is a smaller share of a faster link."""
    def series(self, drops_last):
        return [[i * 300, 0, 0, 0] for i in range(10)] + [[(10 + i) * 300, 0, drops_last * (i + 1) // 3, 0] for i in range(3)]

    def test_the_floor_scales_with_speed_and_never_drops_below_the_minimum(self):
        f = portwatch.floor_for
        self.assertEqual((f("drops", 1000), f("drops", 10000), f("drops", 100), f("drops", None)), (10000, 100000, 1000, 10000))
        self.assertEqual((f("errors", 1000), f("errors", 10000), f("errors", 100), f("errors", None)), (20, 200, 20, 20))
        self.assertEqual(f("flaps", 10000), 3, "link drops are counted, not scaled")

    def test_a_burst_that_is_news_on_a_100_meg_camera_port_is_not_on_a_10_gig_link(self):
        q = self.series(20000)                                             # 20,000 drops in 15 minutes, from nothing
        self.assertEqual(portwatch.judge(q, True, 100)["rising"], ["drops"])
        self.assertEqual(portwatch.judge(q, True, 1000)["rising"], ["drops"])
        self.assertEqual(portwatch.judge(q, True, 10000)["rising"], [], "20,000 is a fifth of what a 10 Gbit port needs")
