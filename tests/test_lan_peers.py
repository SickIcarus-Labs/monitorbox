"""Port history and "where does it go" end to end, with made-up devices: the sampler keys readings to the map's own ids, a switch that is also an
SNMP connection is read over SNMP, and the endpoint names the port that follows the focus port's traffic."""
import os, random, sys, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitorbox_app import lanmap, lansampler, portpeers
import test_lanmap as TL
import test_sites as TS


def bursts(n, seed):
    r = random.Random(seed)
    return [r.choice((0, 0, 60_000, 900_000, 3_000_000)) + r.randint(0, 5000) for _ in range(n)]


class Sampler(unittest.TestCase):
    def test_a_switch_that_is_an_snmp_connection_is_read_over_snmp_by_its_label_the_others_use_unifi_rates(self):
        t = [1000.0]
        series = portpeers.PortSeries(clock=lambda: t[0])
        calls = []
        devices = [{"name": "Core-B", "mac": "..:00:00:02", "type": "usw", "ip": "192.0.2.2", "ports": [{"port_idx": 1, "name": "Port 1", "inBps": 111, "outBps": 222}]},
                   {"name": "Rack-C", "mac": "..:00:00:03", "type": "usw", "ip": "192.0.2.3", "ports": [{"port_idx": 1, "name": "Port 1", "inBps": 333, "outBps": 444}]},
                   {"name": "AP-E", "mac": "..:00:00:04", "type": "uap", "ip": "192.0.2.5", "ports": [{"port_idx": 1, "name": "Port 1", "inBps": 1, "outBps": 1}]}]
        count = {"n": 0}

        def call(mod, method, params, timeout):
            calls.append((mod, method, params.get("clients")))
            if mod == "unifi-network":
                return {"devices": devices}
            count["n"] += 1                                          # SNMP counters grow 125,000 bytes in and 250,000 out per 10 s
            return {"ports": {"te1/0/1": {"in": count["n"] * 125_000, "out": count["n"] * 250_000, "bits": 64, "label": "Port 1"}, "stack-port": {"in": 5, "out": 5, "bits": 64}}}
        conns = [{"id": "u", "module": "unifi-network", "host": "192.0.2.1"}, {"id": "s", "module": "snmp", "host": "192.0.2.2"}, {"id": "nas", "module": "snmp", "host": "192.0.2.77"}]
        sm = lansampler.LanSampler(series, lambda: conns, call, clock=lambda: t[0])
        sm.tick(); t[0] += 10; sm.tick()
        self.assertEqual([m for m in calls if m[0] == "unifi-network"][0][2], True, "the client list too (changed on purpose, #241): Wi-Fi clients are candidates now")
        self.assertEqual([p[1:] for p in series.points[("..:00:00:02", "Port 1")]], [[100_000, 200_000]], "Core-B: SNMP counters by the port's label")
        self.assertEqual([p[1:] for p in series.points[("..:00:00:03", "Port 1")]], [[333, 444], [333, 444]], "Rack-C has no SNMP connection: UniFi's own rates")
        self.assertNotIn(("..:00:00:04", "Port 1"), series.points, "an access point has no switch ports to read")
        self.assertEqual(sm.status["snmp"], 1)
        self.assertEqual(len([c for c in calls if c[0] == "snmp"]), 2, "the NAS's address is not a switch: only the matching connection is asked, once a round")

    def test_wifi_clients_are_read_as_stand_in_ports_and_forgotten_when_they_leave(self):
        t = [1000.0]
        series = portpeers.PortSeries(clock=lambda: t[0])
        rows = [{"name": "Fake iPad", "ip": "192.0.2.50", "mac": "..:aa:bb:01", "wired": False, "ap": "AP-E", "rxBps": 1_000_000, "txBps": 4_000_000},
                {"name": "Fake Laptop", "ip": "192.0.2.51", "mac": "..:aa:bb:02", "wired": False, "ap": "AP-E", "rxBps": 10, "txBps": 20},
                {"name": "Fake Desktop", "ip": "192.0.2.52", "mac": "..:aa:bb:03", "wired": True, "switch": "Core-B", "port": 4, "rxBps": 7, "txBps": 8},
                {"name": "No rates", "ip": "192.0.2.53", "mac": "..:aa:bb:04", "wired": False, "ap": "AP-E"}]
        state = {"rows": rows}
        call = lambda mod, method, params, timeout: {"devices": [{"name": "Core-B", "mac": "..:00:00:02", "type": "usw", "ports": []}], "clients": state["rows"]}
        sm = lansampler.LanSampler(series, lambda: [{"id": "u", "module": "unifi-network"}], call, clock=lambda: t[0])
        sm.tick()
        self.assertEqual(sorted(sm.wifi), ["Fake Laptop|..:aa:bb:02", "Fake iPad|..:aa:bb:01"], "Wi-Fi only, and only with rates: the wired desktop has its switch port")
        self.assertEqual([p[1:] for p in series.points[(lansampler.WIFI, "Fake iPad|..:aa:bb:01")]], [[1_000_000, 4_000_000]], "kept as the controller names them (rx, tx)")
        t[0] += 10; state["rows"] = rows[:1]; sm.tick()
        self.assertEqual(list(sm.wifi), ["Fake iPad|..:aa:bb:01"])
        self.assertNotIn((lansampler.WIFI, "Fake Laptop|..:aa:bb:02"), series.points, "a client that left does not stay in the history")

    def test_a_source_that_does_not_answer_is_skipped_and_nothing_is_invented(self):
        series = portpeers.PortSeries()
        def call(*a):
            raise RuntimeError("down")
        sm = lansampler.LanSampler(series, lambda: [{"id": "u", "module": "unifi-network"}], call)
        sm.tick()
        self.assertEqual(series.points, {})


class Peers(unittest.TestCase):
    N = 60

    def setUp(self):
        self.box = TS.Box(self, "fake-peers-pw-58")
        self.T = 100_000.0
        a = self.box.app
        a.series = portpeers.PortSeries(clock=lambda: self.T)
        a.last_map = lanmap.build(TL.report())
        a.flow_rows = lambda seconds=300: {"seconds": seconds, "rows": [], "notes": []}       # the gateway's flow log: nothing unless a test says so

    def feed(self, dev, port, ins, outs):
        for i in range(self.N):
            self.box.app.series.feed_rates(dev, {port: {"in_bps": ins[i], "out_bps": outs[i]}}, now=self.T - (self.N - i) * 10 + 5)

    def test_the_port_that_follows_the_device_is_named_with_who_is_on_it_and_a_quiet_or_unrelated_one_is_not(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)                                  # TV-Three sends
        self.feed("Rack-C", "Port 5", [0] * self.N, [v // 2 for v in send]); self.feed("Rack-C", "Port 6", [0] * self.N, [v // 2 + 10 for v in send])   # the bonded NAS gets it
        self.feed("Rack-C", "Port 3", [0] * self.N, bursts(self.N, 91))                          # Mini-Two: busy, unrelated
        r = self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")
        self.assertEqual(r["why"], "")
        top = r["answer"][0]
        self.assertEqual((top["label"], top["direction"], top["confidence"]), ("Server-Nas (Rack-C port 5+6)", "from", "likely"))
        self.assertGreater(top["r"], 0.95)
        self.assertTrue(all(a["label"] != "Mini-Two and 1 more (Rack-C port 3)" or a["confidence"] == "possible" for a in r["answer"]))
        self.assertEqual(r["window"], 900); self.assertGreaterEqual(r["read"], 4)
        self.assertIn("Edge-D", r["unread"], "a switch with no readings is named, so the answer's completeness is visible")
        self.assertNotIn("Core-B", r["unread"], "a switch that has readings on some ports is not called silent"); self.assertNotIn("Rack-C", r["unread"])

    def wifi(self, name, rx, tx, mac="..:aa:bb:01"):
        key = f"{name}|{mac}"
        for i in range(self.N):
            self.box.app.series.feed_rates("wifi", {key: {"in_bps": rx[i], "out_bps": tx[i]}}, now=self.T - (self.N - i) * 10 + 5)
        self.box.app.lansampler.wifi = {**self.box.app.lansampler.wifi, key: {"name": name, "ap": "AP-E"}}

    def test_a_wifi_client_that_follows_the_port_is_named_whichever_way_the_controller_points_its_rates(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)                                  # TV-Three sends to the iPad
        for flip in (False, True):
            with self.subTest(controller_names_them_the_other_way=flip):
                self.box.app.lansampler.wifi = {}
                got = [v // 3 for v in send]                                                    # the AP reports a smaller rate than the real traffic: the match is about the shape
                self.wifi("Fake iPad", got, [2000] * self.N) if flip else self.wifi("Fake iPad", [2000] * self.N, got)      # (in, out) as fed: the iPad's received traffic in either column
                r = self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")
                top = next(a for a in r["answer"] if a["label"] == "Fake iPad (Wi-Fi)")
                self.assertEqual((top["direction"], top["confidence"]), ("from", "likely"))
                self.assertGreater(top["r"], 0.95)

    def test_a_wifi_client_that_does_not_follow_the_port_or_only_loosely_is_not_offered(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        self.wifi("Fake Laptop", bursts(self.N, 77), bursts(self.N, 78), "..:aa:bb:02")          # busy, unrelated
        self.wifi("Fake Phone", [v if i % 5 else 0 for i, v in enumerate(send)], [0] * self.N, "..:aa:bb:03")   # mostly follows
        r = self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")
        labels = [a["label"] for a in r["answer"]]
        self.assertNotIn("Fake Laptop (Wi-Fi)", labels)
        for a in r["answer"]:
            if a["label"].endswith("(Wi-Fi)"):
                self.assertEqual(a["confidence"], "likely", "a rate read from an access point must fit closely to count")

    def test_two_wifi_clients_with_the_same_name_are_told_apart(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        self.wifi("iPhone", [v // 2 for v in send], [0] * self.N, "..:aa:bb:11")
        self.wifi("iPhone", [v // 2 + 5 for v in send], [0] * self.N, "..:aa:bb:12")
        labels = [a["label"] for a in self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")["answer"] if "iPhone" in a["label"]]
        self.assertEqual(len(set(labels)), len(labels))

    def test_no_readings_yet_an_unknown_port_and_an_hour_limit_are_each_answered_plainly(self):
        r = self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")
        self.assertEqual(r["answer"], []); self.assertIn("No traffic readings", r["why"])
        r = self.box.get("/api/lan/peers?node=Nope&port=1&win=900")
        self.assertEqual(r["answer"], []); self.assertIn("not on the map", r["why"])
        self.feed("Core-B", "Port 13", bursts(self.N, 3), [1000] * self.N)
        self.assertEqual(self.box.get("/api/lan/peers?node=Core-B&port=13&win=999999")["window"], 3600, "an hour at most")

    def conns(self, *hosts):
        rev = self.box.get("/api/config/connections")["revision"]
        self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": cid, "module": "snmp", "name": cid, "host": host, "port": 9, "version": "2c", "community": f"fake-comm-{cid}", "timeout": 1, "retries": 0} for cid, host in hosts]})

    def graphs(self, *rows):
        from monitorbox_app.store import write_json
        write_json(self.box.app.graphs_file, list(rows))

    def test_a_graph_lists_where_its_traffic_goes_biggest_first_local_and_internet_together(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        self.feed("Rack-C", "Port 5", [0] * self.N, [v // 2 for v in send]); self.feed("Rack-C", "Port 6", [0] * self.N, [v // 2 + 10 for v in send])
        self.conns(("tv", "192.0.2.13"))                                       # TV-Three's own address, so the graph is matched to its port on the map
        self.graphs({"id": "tv-eth", "title": "TV Eth", "connection": "tv", "interface": "eth0"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:44:44:44", "name": "TV-Three", "wired": True, "down_bps": 8_000_000, "up_bps": 100_000},
            {"id": "..:77:77:77", "name": "Phone-Six", "wired": False, "down_bps": 50_000_000, "up_bps": 1_000_000}]}
        r = self.box.get("/api/lan/flows?graph=tv-eth&win=900")
        self.assertEqual(r["why"], "")
        labels = [f["label"] for f in r["flows"]]
        self.assertEqual(labels[0], "the internet and other networks", "8 Mbit/s of internet is the biggest")
        self.assertFalse([l for l in labels if "anything beyond" in l or "anything behind" in l], "'somewhere that way' rows are left out")
        self.assertIn("sends to Server-Nas (Rack-C port 5+6)", labels)
        sizes = [f["down_bps"] + f["up_bps"] for f in r["flows"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True), "biggest first")
        net = r["flows"][0]
        self.assertEqual((net["scope"], net["down_bps"], net["up_bps"]), ("internet", 8_000_000, 100_000), "only this device's own clients, not Phone-Six")
        nas = next(f for f in r["flows"] if f["label"].startswith("sends to Server-Nas"))
        self.assertEqual((nas["scope"], nas["confidence"], nas["down_bps"]), ("local", "likely", 0))
        self.assertGreater(nas["up_bps"], 0); self.assertLessEqual(nas["up_bps"], sum(send) // len(send) + 1, "never more than the device sent")
        self.assertEqual(r["focus"], "Core-B port 13")

    def test_a_long_download_the_flow_log_has_not_named_yet_is_still_counted_as_internet_not_left_unmatched(self):
        """Regression: a Steam download of 850 Mbit/s showed as 'not matched yet' because the gateway's flow log listed only small flows."""
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        self.conns(("tv", "192.0.2.13"))
        self.graphs({"id": "tv-eth", "title": "TV Eth", "connection": "tv", "interface": "eth0"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:44:44:44", "name": "TV-Three", "wired": True, "down_bps": 851_000_000, "up_bps": 15_000_000}]}
        self.box.app.flow_entries = lambda rows, win, ips=(), macs=(): [
            {"scope": "internet", "label": "cdn.example.invalid", "down_bps": 459_000, "up_bps": 67_000}]
        r = self.box.get("/api/lan/flows?graph=tv-eth&win=900")
        more = next(f for f in r["flows"] if f["label"].startswith("more internet traffic"))
        self.assertEqual((more["scope"], more["down_bps"], more["up_bps"]), ("internet", 851_000_000 - 459_000, 15_000_000 - 67_000))
        self.assertEqual(r["flows"][0], more, "the big one is listed first")
        self.assertFalse([f for f in r["flows"] if f["scope"] == "unmatched" and f["down_bps"] > 1_000_000], "the download is not 'unmatched'")

    def test_a_graph_of_the_gateway_is_found_by_the_unifi_logins_address_not_only_the_maps_wan_address(self):
        self.box.app.lansampler.stopping.set()                                  # no background map rebuild while this test sets the map by hand
        rev = self.box.get("/api/config/connections")["revision"]
        self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "u", "module": "unifi-network", "host": "192.0.2.254", "username": "reader-fake", "password": "pw-fake-9921", "site": "default"},
            {"id": "gwsnmp", "module": "snmp", "name": "gw", "host": "192.0.2.254", "port": 9, "version": "2c", "community": "fake-comm-gw", "timeout": 1, "retries": 0}]})
        self.graphs({"id": "wan", "title": "WAN", "connection": "gwsnmp", "interface": "eth8"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:77:77:77", "name": "Phone-Six", "wired": False, "down_bps": 50_000_000, "up_bps": 1_000_000}]}
        r = self.box.get("/api/lan/flows?graph=wan&win=900")                    # the map's gateway says 192.0.2.1 (its WAN side); the SNMP login is on the UniFi login's address
        self.assertEqual([f["label"] for f in r["flows"]], ["Phone-Six (wifi)"], r)

    def test_an_interface_graph_is_matched_by_that_interfaces_own_mac_so_the_second_nic_of_a_server_is_not_mistaken_for_the_first(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)                                  # TV-Three (..:44:44:44) is busy; Mini-Two (..:22:22:22) is not
        self.conns(("two", "192.0.2.13"))                                       # the connection's address is TV-Three's...
        self.box.app.last_sources = [{"connection": "two", "module": "snmp", "report": {"ports": [{"name": "eno3", "mac": "..:22:22:22"}, {"name": "eno4", "mac": "..:44:44:44"}]}}]
        self.graphs({"id": "a", "title": "A", "connection": "two", "interface": "eno3"}, {"id": "b", "title": "B", "connection": "two", "interface": "eno4"},
                    {"id": "c", "title": "C", "connection": "two", "interface": "unknown0"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": []}
        self.assertEqual(self.box.get("/api/lan/flows?graph=a&win=900")["focus"], "Rack-C port 3", "eno3 is Mini-Two's card, whatever address the connection uses")
        self.assertEqual(self.box.get("/api/lan/flows?graph=b&win=900")["focus"], "Core-B port 13")
        self.assertEqual(self.box.get("/api/lan/flows?graph=c&win=900")["focus"], "Core-B port 13", "an interface with no known MAC falls back to the connection's address")

    def test_a_graph_of_the_gateway_lists_who_uses_the_internet_most_and_one_it_cannot_match_says_so(self):
        self.conns(("gw", "192.0.2.1"), ("byname", "some-box.lan"), ("nobody", "198.51.100.9"))
        self.graphs({"id": "wan", "title": "WAN", "connection": "gw", "interface": "eth8"}, {"id": "n", "title": "N", "connection": "byname", "interface": "e"},
                    {"id": "x", "title": "X", "connection": "nobody", "interface": "e"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:77:77:77", "name": "Phone-Six", "wired": False, "down_bps": 50_000_000, "up_bps": 1_000_000},
            {"id": "..:44:44:44", "name": "TV-Three", "wired": True, "down_bps": 8_000_000, "up_bps": 100_000}]}
        r = self.box.get("/api/lan/flows?graph=wan&win=900")
        self.assertEqual([f["label"] for f in r["flows"]], ["Phone-Six (wifi)", "TV-Three (wired)"])
        self.assertTrue(all(f["scope"] == "internet" for f in r["flows"]))
        self.assertIn("set up by name", self.box.get("/api/lan/flows?graph=n&win=900")["why"])
        self.assertIn("could not be matched", self.box.get("/api/lan/flows?graph=x&win=900")["why"])
        self.assertIn("not on the main screen", self.box.get("/api/lan/flows?graph=gone&win=900")["why"])
        with self.assertRaises(Exception):
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{self.box.port}/api/lan/flows?graph=wan")

    def test_the_busiest_graph_follows_the_leader(self):
        from monitorbox_app import busiest
        a = self.box.app
        a.busiest = busiest.Busiest(a.series, clock=lambda: self.T)
        send = [3_000_000] * self.N
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        a.busiest.update(a.last_map, self.T)
        self.graphs({"id": "busiest", "kind": "busiest", "title": "Busiest client"})
        a.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": []}
        r = self.box.get("/api/lan/flows?graph=busiest&win=900")
        self.assertEqual(r["focus"], "Core-B port 13", r)

    def test_the_busiest_line_is_the_latest_reading_and_is_the_devices_own_graph_when_it_has_one(self):
        from monitorbox_app import busiest
        a = self.box.app
        a.busiest = busiest.Busiest(a.series, clock=lambda: self.T)
        a.graphs.clock = lambda: self.T
        self.feed("Core-B", "Port 13", [1_000_000] * (self.N - 1) + [9_000_000], [1000] * self.N)
        a.busiest.update(a.last_map, self.T)
        d = self.box.get("/api/lan/busiest?seconds=300")
        self.assertEqual(d["leader"]["name"], "TV-Three")
        self.assertEqual(d["points"][-1][2], 9_000_000, "drawn from the latest reading, not smoothed")
        self.assertLess(d["leader"]["up"], 9_000_000, "the figure in words is the 60 second average")
        self.assertNotIn("source", d)
        self.conns(("tv", "192.0.2.13"))
        self.graphs({"id": "tv-eth", "title": "TV Eth", "connection": "tv", "interface": "eth0"}, {"id": "busiest", "kind": "busiest", "title": "Busiest client"})
        a.graphs.points["tv-eth"] = [[self.T - 400, 1, 1], [self.T, 5_000_000, 100]]
        d = self.box.get("/api/lan/busiest?seconds=300")
        self.assertEqual((d["points"][-1], d["source"]), ([self.T, 5_000_000, 100], "TV Eth"), "the same readings as the graph of that device")
        self.assertEqual(d["leader"]["name"], "TV-Three")

    def test_a_busiest_wifi_client_lists_the_flows_the_gateway_logged_for_it(self):
        from monitorbox_app import busiest
        a = self.box.app
        a.busiest = busiest.Busiest(a.series, clock=lambda: self.T)
        row = lambda dst, down, up=0: {"src_ip": "192.0.2.77", "src_mac": "..:77:77:77", "src_name": "Phone-Six", "dst_ip": "203.0.113.5", "dst_mac": "", "dst_name": dst, "dst_zone": "External",
                                       "direction": "outgoing", "service": "HTTPS", "down": down, "up": up}
        rows = [row("video.example.test", 900_000_000, 9_000_000), row("chat.example.test", 9_000_000)]
        a.busiest.update(a.last_map, self.T, rows)
        self.graphs({"id": "busiest", "kind": "busiest", "title": "Busiest client"})
        a.flow_rows = lambda seconds=300: {"seconds": seconds, "rows": rows, "notes": []}
        r = self.box.get("/api/lan/flows?graph=busiest&win=900")
        self.assertEqual(r["focus"], "Phone-Six")
        self.assertEqual([f["label"] for f in r["flows"]], ["video.example.test", "chat.example.test"])
        self.assertEqual((r["flows"][0]["scope"], r["flows"][0]["down_bps"]), ("internet", 8_000_000))

    def test_while_the_history_is_shorter_than_the_window_the_list_says_so_instead_of_a_flat_not_matched_to_anything(self):
        """#262: right after a restart the box has only a minute or two of readings; the gap is not 'nothing', it is 'not learned yet'."""
        self.feed("Core-B", "Port 13", bursts(self.N, 5), [20_000_000] * self.N)       # a device that received far more than any listed flow explains
        self.conns(("tv", "192.0.2.13"))
        self.graphs({"id": "tv-eth", "title": "TV Eth", "connection": "tv", "interface": "eth0"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": []}
        short = self.box.get("/api/lan/flows?graph=tv-eth&win=3600")                      # an hour asked for, about ten minutes read
        self.assertTrue(short["young"])
        self.assertAlmostEqual(short["history"], self.N * 10 - 5, delta=15)
        rest = [f for f in short["flows"] if f["scope"] == "unmatched"]
        self.assertTrue(rest, "the test needs a row for the traffic nothing explains")
        self.assertEqual([f["label"] for f in rest], ["not matched yet"])
        full = self.box.get("/api/lan/flows?graph=tv-eth&win=300")                        # five minutes asked for, ten read: the window is full
        self.assertFalse(full["young"])
        self.assertEqual([f["label"] for f in full["flows"] if f["scope"] == "unmatched"], ["not matched to anything"])

    def test_signing_in_is_required(self):
        import urllib.request, urllib.error
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{self.box.port}/api/lan/peers?node=x&port=1")
        self.assertEqual(e.exception.code, 401)


    def test_a_device_lists_the_destinations_the_gateways_flow_log_names_and_they_replace_the_internet_total(self):
        send = bursts(self.N, 3)
        self.feed("Core-B", "Port 13", send, [1000] * self.N)
        self.conns(("tv", "192.0.2.13"))
        self.graphs({"id": "tv-eth", "title": "TV Eth", "connection": "tv", "interface": "eth0"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:44:44:44", "name": "TV-Three", "wired": True, "down_bps": 8_000_000, "up_bps": 100_000}]}
        row = lambda **k: {**{"src_ip": "192.0.2.13", "src_mac": "..:44:44:44", "src_name": "TV-Three", "dst_ip": "203.0.113.5", "dst_mac": "", "dst_name": "video.example.test",
                              "dst_zone": "External", "direction": "outgoing", "service": "HTTPS", "down": 0, "up": 0}, **k}
        self.box.app.flow_rows = lambda seconds=300: {"seconds": seconds, "notes": [], "rows": [
            row(down=900_000_000, up=9_000_000),                                                                       # 8 Mbit/s over 15 minutes
            row(dst_name="ads.example.test", dst_ip="203.0.113.6", down=90_000_000),
            row(dst_name="Server-Nas", dst_ip="192.0.2.50", dst_zone="Internal", direction="local", down=45_000_000, up=450_000_000),
            row(src_ip="192.0.2.99", src_mac="..:99:99:99", src_name="Phone-Six", dst_ip="192.0.2.13", dst_mac="..:44:44:44", dst_name="TV-Three", dst_zone="Internal", direction="local", down=1_000_000, up=9_000_000),
            row(src_ip="192.0.2.77", src_mac="..:77:77:77", src_name="Phone-Six", down=999_000_000),                  # someone else's: not this device
            row(dst_name="192.0.2.1", dst_ip="192.0.2.1", dst_zone="Gateway", direction="local", down=5_000_000_000, up=1)]}   # the device talking to its own gateway
        r = self.box.get("/api/lan/flows?graph=tv-eth&win=900")
        labels = [f["label"] for f in r["flows"]]
        self.assertEqual(labels[:2], ["video.example.test", "Server-Nas"], labels)
        self.assertNotIn("the internet and other networks", labels, "named destinations replace the total")
        self.assertNotIn("the gateway", labels); self.assertNotIn("192.0.2.1", labels)
        self.assertNotIn("Phone-Six", " ".join(l for l in labels if "from" not in l))
        video = r["flows"][0]
        self.assertEqual((video["scope"], video["down_bps"], video["up_bps"], video["seen"]), ("internet", 8_000_000, 80_000, True))
        nas = r["flows"][1]
        self.assertEqual((nas["scope"], nas["down_bps"], nas["up_bps"]), ("local", 400_000, 4_000_000))
        self.assertIn("from Phone-Six", labels, "a flow aimed at this device is listed too")
        into = next(f for f in r["flows"] if f["label"] == "from Phone-Six")
        self.assertEqual((into["down_bps"], into["up_bps"]), (80_000, 8_889), "what it sent is what this device received")
        sizes = [f["down_bps"] + f["up_bps"] for f in r["flows"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_the_gateway_graph_lists_internet_destinations_naming_who_uses_them_and_falls_back_to_clients_when_the_flow_log_is_silent(self):
        self.box.app.lansampler.stopping.set()
        rev = self.box.get("/api/config/connections")["revision"]
        self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "u", "module": "unifi-network", "host": "192.0.2.254", "username": "reader-fake", "password": "pw-fake-4417", "site": "default"},
            {"id": "gwsnmp", "module": "snmp", "name": "gw", "host": "192.0.2.254", "port": 9, "version": "2c", "community": "fake-comm-5503", "timeout": 1, "retries": 0}]})
        self.graphs({"id": "wan", "title": "WAN", "connection": "gwsnmp", "interface": "eth8"})
        self.box.app.gateway_usage = lambda seconds=300: {"seconds": seconds, "total": {}, "notes": [], "clients": [
            {"id": "..:77:77:77", "name": "Phone-Six", "wired": False, "down_bps": 50_000_000, "up_bps": 1_000_000}]}
        row = lambda who, dst, down, up=0, **k: {**{"src_ip": "192.0.2.1", "src_mac": "..:01:01:01", "src_name": who, "dst_ip": "203.0.113.9", "dst_mac": "", "dst_name": dst,
                                                    "dst_zone": "External", "direction": "outgoing", "service": "HTTPS", "down": down, "up": up}, **k}
        self.box.app.flow_rows = lambda seconds=300: {"seconds": seconds, "notes": [], "rows": [
            row("Phone-Six", "cdn.example.test", 450_000_000), row("TV-Three", "cdn.example.test", 225_000_000), row("Mini-Two", "cdn.example.test", 100_000, 0),
            row("TV-Three", "other.example.test", 45_000_000, 9_000_000), row("Phone-Six", "Server-Nas", 99_000_000_000, direction="local")]}
        r = self.box.get("/api/lan/flows?graph=wan&win=900")
        self.assertEqual([f["label"] for f in r["flows"]], ["cdn.example.test (Phone-Six, TV-Three and 1 more)", "other.example.test (TV-Three)"], "internet only, biggest first, with who")
        self.assertTrue(all(f["scope"] == "internet" for f in r["flows"]))
        self.assertEqual(r["flows"][0]["down_bps"], round(675_100_000 * 8 / 900))
        self.box.app.flow_rows = lambda seconds=300: {"seconds": seconds, "rows": [], "notes": ["u: this controller does not report flows (HTTP 404)"]}
        self.assertEqual([f["label"] for f in self.box.get("/api/lan/flows?graph=wan&win=900")["flows"]], ["Phone-Six (wifi)"])


if __name__ == "__main__":
    unittest.main()


class WhatTheListDoesNotExplain(unittest.TestCase):
    """The list under a graph names the gateway's flows and the ports that follow the device, which can leave much of its traffic unexplained;
    the rest is shown as its own row instead of being silently absent."""
    @staticmethod
    def unmatched(total, flows):
        from monitorbox_app.server import App
        return App.unmatched(total, flows)

    def test_the_part_nothing_explains_is_one_row_and_a_small_gap_or_no_total_adds_nothing(self):
        flows = [{"down_bps": 20_000_000, "up_bps": 0}, {"down_bps": 13_000_000, "up_bps": 0}, {"down_bps": 187, "up_bps": 116}]
        row, = self.unmatched({"down": 78_000_000, "up": 11_000_000}, flows)
        self.assertEqual((row["scope"], row["down_bps"], row["up_bps"]), ("unmatched", 78_000_000 - 33_000_187, 11_000_000 - 116))
        self.assertEqual(self.unmatched({"down": 34_000_000, "up": 0}, flows), [], "within a tenth of the total: nothing worth saying")
        self.assertEqual(self.unmatched(None, flows), [])
        self.assertEqual(self.unmatched({"down": 1_000_000, "up": 0}, flows), [], "the list explains more than the port carried (estimates overlap): never a negative row")

    def test_the_inference_reports_what_the_device_received_and_sent_even_when_it_names_nobody(self):
        quiet = ([5_000_000] * 12, [20_000_000] * 12)          # the port's in is what the device sent, its out what it received
        got = portpeers.likely(quiet, {})
        self.assertEqual(got["total"], {"down": 20_000_000, "up": 5_000_000})


class DevicesTogether(unittest.TestCase):
    """A box that receives many look-alike streams (cameras, VMs, sensors, anything): each alone follows its traffic only loosely, their total follows it closely."""
    N = 60

    def setUp(self):
        self.box = TS.Box(self, "fake-together-pw-61")
        self.T = 100_000.0
        a = self.box.app
        a.series = portpeers.PortSeries(clock=lambda: self.T)
        a.last_map = lanmap.build(TL.report())
        a.flow_rows = lambda seconds=300: {"seconds": seconds, "rows": [], "notes": []}
        self.a, self.b, self.c = bursts(self.N, 11), bursts(self.N, 12), bursts(self.N, 13)
        self.feed("Core-B", "Port 13", [1000] * self.N, [x + y + z for x, y, z in zip(self.a, self.b, self.c)])    # TV-Three (standing in for the recorder) receives all three
        self.feed("Rack-C", "Port 3", self.a, [10] * self.N)                                                         # Mini-Two, Printer-Four and Server-Spare send
        self.feed("Edge-D", "Port 2", self.b, [10] * self.N)
        self.feed("Rack-C", "Port 8", self.c, [10] * self.N)
        self.feed("Rack-C", "Port 5", [0] * self.N, bursts(self.N, 77))                                              # something else busy and unrelated
        a.camera_ids = lambda: (set(), set())

    def feed(self, dev, port, ins, outs):
        for i in range(self.N):
            self.box.app.series.feed_rates(dev, {port: {"in_bps": ins[i], "out_bps": outs[i]}}, now=self.T - (self.N - i) * 10 + 5)

    def answer(self):
        return self.box.get("/api/lan/peers?node=Core-B&port=13&win=900")["answer"]

    def test_with_nothing_known_about_them_the_devices_that_move_together_are_named_as_a_group(self):
        got = self.answer()
        group = next(a for a in got if "devices together" in a["label"])
        self.assertTrue(group["label"].startswith("3 devices together ("), group["label"])
        self.assertEqual((group["direction"], group["confidence"]), ("to", "likely"))
        self.assertGreater(group["r"], 0.95)
        self.assertFalse([a for a in got if a["label"].endswith(("(Rack-C port 3)", "(Edge-D port 2)", "(Rack-C port 8)"))], "its members are not listed again beside it")

    def test_ports_known_to_be_cameras_start_the_group_and_it_is_called_that(self):
        self.box.app.camera_ids = lambda: (set(), {"192.0.2.11", "192.0.2.14"})            # Mini-Two and Printer-Four are cameras; the third device joins them
        got = self.answer()
        self.assertTrue([a for a in got if a["label"].startswith(("3 devices together", "your cameras"))], [a["label"] for a in got])
        self.box.app.camera_ids = lambda: (set(), {"192.0.2.11", "192.0.2.14", "192.0.2.99"})
        self.assertTrue(any(a["label"].startswith(("3 devices together", "your cameras")) for a in self.answer()))

    def test_one_clear_match_is_not_turned_into_a_group_and_an_unrelated_busy_port_does_not_join(self):
        self.feed("Core-B", "Port 13", [1000] * self.N, self.a)                                # now the device receives only what Mini-Two sends
        got = self.answer()
        self.assertFalse([a for a in got if "together" in a["label"]], [a["label"] for a in got])
        self.assertTrue(any(a["label"].endswith("(Rack-C port 3)") or "Mini-Two" in a["label"] for a in got))

    def test_the_group_cannot_add_up_to_more_than_the_device_carried(self):
        self.feed("Core-B", "Port 13", [1000] * self.N, [x // 3 for x in self.a])              # far less than the three together would send
        self.assertFalse([a for a in self.answer() if "together" in a["label"]])

    def test_camera_addresses_are_read_from_the_camera_sources_and_matched_to_ports_by_mac_or_ip(self):
        a = self.box.app
        del a.camera_ids                                                                        # the real one, not this class's stub
        a.cameras = lambda: {"cameras": [{"mac": "AA:bb:CC:00:00:01", "host": "192.0.2.11 "}, {"mac": "aabbcc000002", "host": ""}, {"mac": "short", "host": None}], "errors": []}
        a._cam_ids = None
        self.assertEqual(a.camera_ids(), ({"aabbcc000001", "aabbcc000002"}, {"192.0.2.11"}), "colons and case do not matter; a malformed MAC is ignored")
        by = {n["id"]: n for n in a.last_map["nodes"]}
        me, row = by["Core-B"], next(p for p in by["Core-B"]["ports"] if str(p["port"]) == "13")
        a._cam_ids = (time.time(), ({"222222", "555555"}, set()))                              # the map's fake MACs are short; these normalize to the same digits
        self.assertEqual(len(a.camera_ports(by, me, row)), 2, "Mini-Two's and Printer-Four's ports")
        a._cam_ids = (time.time(), ({"222222"}, set()))
        self.assertEqual(a.camera_ports(by, me, row), [], "one camera port is not a group")
