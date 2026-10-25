"""The busiest client: who is chattiest on the wired LAN, with the name held steady (made-up devices)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitorbox_app import busiest as B, portpeers as P, lanmap
import test_lanmap as TL
import test_sites as TS

M = lanmap.build(TL.report())
A, N, T = ("Rack-C", "Port 3"), ("Rack-C", "Port 5"), ("Core-B", "Port 13")      # Mini-Two, the bonded NAS (Port 5 + Port 6), TV-Three


class Leader(unittest.TestCase):
    def setUp(self):
        self.t = 50_000.0
        self.s = P.PortSeries(clock=lambda: self.t)
        self.b = B.Busiest(self.s, clock=lambda: self.t)

    def tick(self, rates):
        """rates: {(device, port): (to_device_bps, from_device_bps)}; one 10-second step, then the leader is worked out."""
        self.t += 10
        for (dev, port), (down, up) in rates.items():
            self.s.feed_rates(dev, {port: {"in_bps": up, "out_bps": down}}, now=self.t - 5)
        self.b.update(M, self.t)

    def who(self):
        return (self.b.data(300, self.t)["leader"] or {}).get("name")

    def test_the_chattiest_wired_device_is_named_with_where_it_is_and_both_directions(self):
        for _ in range(3):
            self.tick({A: (200_000, 5_000_000), N: (100_000, 100_000)})
        d = self.b.data(300, self.t)
        self.assertEqual((d["leader"]["name"], d["leader"]["where"], d["leader"]["down"], d["leader"]["up"]), ("Mini-Two and 1 more", "Rack-C port 3", 200_000, 5_000_000))
        self.assertEqual((d["leader"]["node"], d["leader"]["port"]), ("Rack-C", "3")); self.assertFalse(d["quiet"])

    def test_a_slow_lan_has_no_leader_and_nobody_is_crowned_for_a_whisper(self):
        for _ in range(4):
            self.tick({A: (3_000, 2_000), N: (500, 100)})
        d = self.b.data(300, self.t)
        self.assertIsNone(d["leader"]); self.assertTrue(d["quiet"]); self.assertTrue(d["available"])

    def test_a_challenger_must_stay_clearly_busier_for_thirty_seconds_before_the_name_changes(self):
        for _ in range(3):
            self.tick({A: (0, 4_000_000), T: (0, 100_000)})
        self.assertEqual(self.who(), "Mini-Two and 1 more")
        self.tick({A: (0, 4_000_000), T: (0, 5_000_000)})                  # barely busier, for one reading: no change
        self.assertEqual(self.who(), "Mini-Two and 1 more")
        for _ in range(7):                                                  # clearly busier and staying there
            self.tick({A: (0, 1_000_000), T: (0, 9_000_000)})
        self.assertEqual(self.who(), "TV-Three")
        d = self.b.data(300, self.t)
        self.assertEqual([b["name"] for b in d["before"]], ["Mini-Two and 1 more"], "who it was before, so a switch is not a mystery")

    def test_a_short_spike_does_not_steal_the_crown(self):
        for _ in range(3):
            self.tick({A: (0, 4_000_000), T: (0, 100_000)})
        self.tick({A: (0, 4_000_000), T: (0, 30_000_000)})
        for _ in range(8):
            self.tick({A: (0, 4_000_000), T: (0, 100_000)})
        self.assertEqual(self.who(), "Mini-Two and 1 more")

    def test_the_leader_keeps_the_crown_through_a_short_lull_and_loses_it_after_a_minute_of_quiet(self):
        for _ in range(3):
            self.tick({A: (0, 4_000_000)})
        for _ in range(3):
            self.tick({A: (0, 400_000)})                                    # below the floor but above half of it
        self.assertEqual(self.who(), "Mini-Two and 1 more")
        for _ in range(14):
            self.tick({A: (0, 1_000)})
        self.assertIsNone(self.who())

    def test_a_bonded_pair_is_one_device_with_both_ports_added(self):
        for _ in range(3):
            self.tick({("Rack-C", "Port 5"): (0, 3_000_000), ("Rack-C", "Port 6"): (0, 4_000_000)})
        d = self.b.data(300, self.t)["leader"]
        self.assertEqual((d["name"], d["port"], d["up"]), ("Server-Nas", "5+6", 7_000_000))


    def test_a_wifi_client_the_gateways_flow_log_names_can_take_the_lead_and_a_wired_device_is_left_to_its_port(self):
        row = lambda mac, name, down, up=0: {"src_mac": mac, "src_name": name, "dst_mac": "", "dst_name": "cdn.example.test", "direction": "outgoing", "down": down, "up": up}
        phone = row("..:77:77:77", "Phone-Six", 600_000_000, 6_000_000)                          # 80 Mbit/s over the 60 second window
        tv = row("..:44:44:44", "TV-Three", 6_000_000_000)                                       # TV-Three is on a port: its flows must not count twice
        def tick(rates, flows):
            self.t += 10
            for (dev, port), (down, up) in rates.items():
                self.s.feed_rates(dev, {port: {"in_bps": up, "out_bps": down}}, now=self.t - 5)
            self.b.update(M, self.t, flows)
        for _ in range(3):
            tick({A: (0, 4_000_000), T: (0, 100_000)}, [phone, tv])
        d = self.b.data(300, self.t)
        self.assertEqual(d["leader"]["name"], "Phone-Six", d["leader"])
        self.assertEqual((d["leader"]["node"], d["leader"]["port"], d["leader"]["mac"]), (None, None, "..:77:77:77"))
        self.assertEqual((d["leader"]["down"], d["leader"]["up"]), (80_000_000, 800_000))
        self.assertNotIn("TV-Three", [x["name"] for x in d["before"]])
        for _ in range(3):                                                                       # the phone goes quiet: the wired device is back on top
            tick({A: (0, 4_000_000), T: (0, 100_000)}, [])
        self.assertEqual(self.who(), "Mini-Two and 1 more")


class Endpoint(unittest.TestCase):
    def test_the_front_page_reads_it_signed_in_only_and_without_unifi_it_is_simply_not_available(self):
        import urllib.request, urllib.error
        box = TS.Box(self, "fake-busy-pw-62")
        self.assertEqual(box.get("/api/lan/busiest")["available"], False)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{box.port}/api/lan/busiest")
        self.assertEqual(e.exception.code, 401)
        a = box.app
        a.last_map = M
        a.series = P.PortSeries(); a.busiest = B.Busiest(a.series)
        for i in range(8):
            a.series.feed_rates("Core-B", {"Port 13": {"in_bps": 6_000_000, "out_bps": 100_000}}, now=a.busiest.clock() - 80 + i * 10)
        a.busiest.update(M)
        d = box.get("/api/lan/busiest?seconds=300")
        self.assertEqual(d["leader"]["name"], "TV-Three"); self.assertEqual(d["leader"]["up"], 6_000_000)
        self.assertEqual(box.get("/api/lan/busiest?seconds=999999")["seconds"], 3600, "an hour at most")


class FrontPage(unittest.TestCase):
    def test_the_front_page_names_the_busiest_client_and_one_tap_says_where_it_is_going(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        import random, time
        box = TS.Box(self, "fake-front-pw-73")
        a = box.app
        a.last_map = M
        a.series = P.PortSeries(); a.busiest = B.Busiest(a.series)
        r = random.Random(4)
        send = [r.choice((0, 0, 60_000, 900_000, 3_000_000)) + r.randint(0, 5000) + 2_000_000 for _ in range(80)]
        now = time.time()
        for i, v in enumerate(send):
            t = now - (80 - i) * 10
            a.series.feed_rates("Core-B", {"Port 13": {"in_bps": v, "out_bps": 1000}}, now=t)              # TV-Three sends
            a.series.feed_rates("Rack-C", {"Port 5": {"in_bps": 0, "out_bps": v // 2}, "Port 6": {"in_bps": 0, "out_bps": v // 2 + 10}}, now=t)   # the NAS receives it
        a.busiest.update(M)
        a.gateway_usage = lambda seconds=300: {"seconds": seconds, "clients": [{"id": "..:44:44:44", "name": "TV-Three", "wired": True, "down_bps": 20_000_000, "up_bps": 150_000}], "total": {"down_bps": 20_000_000, "up_bps": 150_000}, "notes": []}
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", box.pw); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            self.assertEqual(pg.locator("#bz").count(), 0, "nothing on the front page until it is added as a graph")
            pg.goto(f"http://127.0.0.1:{box.port}/#/settings/graphs"); pg.wait_for_selector("#grset >> text=Busiest client")
            pg.click("#grset .devrow >> text=Add"); pg.wait_for_selector("#grset >> text=Remove")
            self.assertEqual([g["kind"] for g in box.get("/api/graphs")["graphs"]], ["busiest"])
            self.assertEqual(pg.locator("#grset button:text-is(\"Add\")").count(), 0, pg.inner_text("#grset"))
            pg.goto(f"http://127.0.0.1:{box.port}/#/"); pg.reload()
            pg.wait_for_selector("#bz >> text=TV-Three", timeout=20000)
            txt = pg.inner_text("#bz")
            self.assertIn("busiest client", txt.lower()); self.assertIn("Core-B port 13", txt)
            self.assertEqual(pg.locator(".drawer.gp").count(), 0)
            pg.click("#bz"); pg.wait_for_selector(".drawer.gp >> text=not a record of conversations", timeout=20000)
            panel = pg.inner_text(".drawer.gp")
            self.assertIn("sends to Server-Nas (Rack-C port 5+6)", panel, "the flows are listed without a second tap")
            self.assertIn("TV-Three", panel)
            gw = pg.inner_text(".drawer.gp")
            self.assertIn("the internet and other networks", gw)
            self.assertLess(gw.index("the internet and other networks"), gw.index("sends to Server-Nas"), "biggest first, local and internet in one list")
            self.assertNotIn("Through the gateway", gw, "no separate section")
            self.assertIn("up to", gw, "a local rate is an upper bound and says so")
            pg.click(".drawer.gp >> text=1 hour"); pg.wait_for_selector(".drawer.gp >> text=not a record of conversations", timeout=20000)
            self.assertIn("sends to Server-Nas", pg.inner_text(".drawer.gp"))
            pg.click(".drawer.gp >> text=Close"); self.assertEqual(pg.locator(".drawer.gp").count(), 0)
            box.post("/api/graphs", {"graphs": []}); pg.reload(); pg.wait_for_selector(".card, .box")
            self.assertEqual(pg.locator("#bz").count(), 0, "taken off, it is gone")
            self.assertEqual(errs, [])
            b.close()


class Cadence(unittest.TestCase):
    def test_the_front_page_asks_for_the_busiest_client_every_second_like_the_other_graphs_one_request_at_a_time(self):
        import urllib.request
        box = TS.Box(self, "fake-cadence-pw-91")
        html = urllib.request.urlopen(f"http://127.0.0.1:{box.port}/").read().decode()
        self.assertIn("setInterval(pollBusiest,1000)", html)
        self.assertIn("setInterval(pollGraphs,1000)", html)
        self.assertRegex(html, r"async function pollBusiest\(\)\{[^}]*bzBusy\)return")


if __name__ == "__main__":
    unittest.main()


class Filters(Leader):
    """#232: what the card may show. Only the card changes; the readings stay."""
    def go(self, opts, flows=None, rates=None, n=3):
        self.b = B.Busiest(self.s, clock=lambda: self.t)                   # a fresh card each time: a leader already crowned stays down to half the floor
        for _ in range(n):
            self.t += 10
            for (dev, port), (down, up) in (rates or {A: (200_000, 5_000_000), N: (100_000, 300_000), T: (100_000, 100_000)}).items():
                self.s.feed_rates(dev, {port: {"in_bps": up, "out_bps": down}}, now=self.t - 5)
            if N in (rates or {A: 1, N: 1, T: 1}):
                self.s.feed_rates("Rack-C", {"Port 6": {"in_bps": 0, "out_bps": 0}}, now=self.t - 5)          # the bonded NAS is Port 5 + Port 6
            self.b.update(M, self.t, flows, opts)
        return self.who()

    PHONE = {"src_mac": "..:77:77:77", "src_name": "Phone-Six", "dst_mac": "", "dst_name": "cdn.example.test", "direction": "outgoing", "down": 6_000_000_000, "up": 0}

    def test_the_wired_and_wifi_ticks_choose_a_side(self):
        self.assertEqual(self.go({}, [self.PHONE]), "Phone-Six", "both sides by default")
        self.assertEqual(self.go({"wifi": False}, [self.PHONE]), "Mini-Two and 1 more", "no wifi: the wired leader")
        self.assertEqual(self.go({"wired": False}, [self.PHONE]), "Phone-Six", "wifi only")
        self.assertIsNone(self.go({"wired": False, "wifi": False}, [self.PHONE]), "nothing allowed: nobody is crowned")

    def test_the_gateway_and_other_network_gear_are_never_the_busiest_client(self):
        """Regression: the card crowned '192.168.3.1', the gateway itself, which shows in its own flow log."""
        gw = {"src_mac": "..:aa:aa:aa", "src_name": "", "src_ip": "192.0.2.254", "dst_mac": "", "dst_name": "cdn.example.test", "direction": "outgoing", "down": 9_000_000_000, "up": 0}
        quiet = {A: (1_000, 1_000), N: (1_000, 1_000), T: (1_000, 1_000)}
        self.assertEqual(self.go({}, [gw], rates=quiet), "unnamed device", "without knowing the gear it looks like a wifi client")
        self.assertIsNone(self.go({"_infraIps": ["192.0.2.254"]}, [gw], rates=quiet), "known by its address")
        self.assertIsNone(self.go({"_infraMacs": ["aa:bb:cc:aa:aa:aa"]}, [gw], rates=quiet), "known by its hardware address, in any notation")
        self.assertEqual(self.go({"_infraIps": ["192.0.2.254"]}, [gw, self.PHONE], rates=quiet), "Phone-Six", "a real client still takes the card")

    def test_servers_can_be_left_out_with_one_tick(self):
        busy_nas = {A: (1_000_000, 2_000_000), N: (9_000_000, 9_000_000), T: (100_000, 100_000)}
        self.assertEqual(self.go({}, rates=busy_nas), "Server-Nas")
        self.assertEqual(self.go({"servers": False}, rates=busy_nas), "Mini-Two and 1 more", "the monitored server steps aside for the next device")

    def test_cameras_and_iot_ticks_hide_only_those_devices(self):
        cam = {**self.PHONE, "src_ip": "10.0.9.9"}
        for key, ips in (("cameras", "_cameraIps"), ("iot", "_iotIps")):
            self.assertEqual(self.go({}, [cam]), "Phone-Six", "ticked by default")
            self.assertEqual(self.go({key: False, ips: ["10.0.9.9"]}, [cam]), "Mini-Two and 1 more", f"unticking {key} hides the device on that list")
            self.assertEqual(self.go({key: False, ips: ["10.0.9.10"]}, [cam]), "Phone-Six", f"a device not on the {key} list stays")
            self.assertEqual(self.go({ips: ["10.0.9.9"]}, [cam]), "Phone-Six", f"{key} ticked: the list changes nothing")
        self.assertEqual(self.go({"cameras": False, "_iotIps": ["10.0.9.9"]}, [cam]), "Phone-Six", "the two lists are not mixed up")

    def test_a_camera_is_found_by_its_mac_or_its_name_when_its_address_does_not_match(self):
        """Regression (#289): the Cameras tick only knew a camera's address, so a camera listed under another address, a name, or only by MAC took the card."""
        cam = {"id": "x|1", "name": "Porch Cam", "ips": ["10.0.9.50"], "macs": ["..:dd:ee:ff"], "node": "sw", "port": "1"}
        off = {"cameras": False}
        self.assertFalse(B.allowed(cam, {**off, "_cameraIps": ["10.0.9.99"], "_cameraMacs": ["a1b2c3ddeeff"]}), "by the last three pairs of its MAC")
        self.assertFalse(B.allowed(cam, {**off, "_cameraNames": ["porch cam"]}), "by name, capitals ignored")
        self.assertFalse(B.allowed(cam, {**off, "_cameraIps": ["10.0.9.50"]}), "by address, as before")
        self.assertTrue(B.allowed(cam, {**off, "_cameraIps": ["10.0.9.99"], "_cameraMacs": ["a1b2c3ddee00"], "_cameraNames": ["back door"]}), "a different camera does not hide it")
        self.assertTrue(B.allowed(cam, {"_cameraNames": ["porch cam"]}), "Cameras ticked: nothing is hidden")

    def test_a_port_that_leads_to_another_switch_is_never_a_client(self):
        m = {"nodes": [{"id": "sw", "name": "Switch-A", "ports": [
            {"port": "1", "name": "Aggregation", "keys": [["sw", "Port 1"]], "infra": True, "macs": [], "ips": []},
            {"port": "2", "name": "Desk-PC", "keys": [["sw", "Port 2"]], "macs": [], "ips": []}]}]}
        self.assertEqual([e["name"] for e in B.endpoints(m)], ["Desk-PC"])

    def test_the_hide_list_matches_name_mac_or_maker_and_can_be_switched_off(self):
        ph = {**self.PHONE, "src_ip": "10.0.9.9"}
        mk = {"_makers": {"10.0.9.9": "Fake Maker Co"}}
        for text, hit in (("phone-six", True), ("nothing, PHONE", True), ("..:77:77:77", True), ("aa:bb:cc:77:77:77", True), ("77:77:77", True), ("fake maker", True), ("maker co , x", True),
                          ("10.0.9.9", True), ("10.0.9.", True), ("10.0.9", False), ("10.0.9.99", False), ("10.0.", True), ("other", False), ("77:77:78", False), ("77", False), (" , ,", False), ("tv", False)):
            got = self.go({"blacklist": text, **mk}, [ph])
            self.assertEqual(got != "Phone-Six", hit, f"{text!r} {'hides' if hit else 'leaves'} the device")
        self.assertEqual(self.go({"blacklist": "phone", "blacklistOn": False, **mk}, [ph]), "Phone-Six", "unticked: the list is kept but does nothing")

    def test_a_client_is_iot_by_the_name_of_its_network_or_wifi(self):
        self.assertTrue(lanmap.is_iot({"network": "Home IoT"})); self.assertTrue(lanmap.is_iot({"essid": "smart-iot"}))
        self.assertFalse(lanmap.is_iot({"network": "Default", "essid": "Home"})); self.assertFalse(lanmap.is_iot({}))
        m = lanmap.build([{"connection": "u", "module": "unifi-network", "report": {"devices": [], "clients": [{"name": "Plug", "ip": "10.0.5.5", "wired": False, "network": "IoT"}, {"name": "Laptop", "ip": "10.0.1.5", "wired": False, "network": "Default"}]}}])
        self.assertEqual(m["iotIps"], ["10.0.5.5"])

    def test_the_minimum_bandwidth_is_editable(self):
        quiet = {A: (300_000, 400_000), N: (10_000, 10_000), T: (10_000, 10_000)}            # 0.7 Mbit/s: under today's fixed 1 Mbit/s
        self.assertIsNone(self.go({}, rates=quiet))
        self.assertEqual(self.go({"floorMbps": 0.5}, rates=quiet), "Mini-Two and 1 more", "a lower floor crowns a quieter device")
        loud = {A: (1_500_000, 1_500_000), N: (10_000, 10_000), T: (10_000, 10_000)}          # 3 Mbit/s
        self.assertIsNone(self.go({"floorMbps": 5}, rates=loud), "a higher floor ignores the chatter")

    def test_an_excluded_device_never_takes_part_by_mac_in_any_notation_or_by_port_id_and_the_next_one_leads(self):
        rates = {A: (200_000, 5_000_000), N: (1_000_000, 1_500_000), T: (100_000, 100_000)}
        self.assertEqual(self.go({}, rates=rates), "Mini-Two and 1 more")
        self.assertEqual(self.go({"exclude": [{"mac": "22:22:22", "name": "Mini-Two"}]}, rates=rates), "Server-Nas", "by MAC (the fixture's MACs are short)")
        self.assertEqual(self.go({"exclude": [{"mac": "..:22:22:22"}]}, rates=rates), "Server-Nas", "colons, dots and case do not matter")
        self.assertEqual(self.go({"exclude": [{"id": "Rack-C|3", "name": "Mini-Two"}]}, rates=rates), "Server-Nas", "a port with no MAC is excluded by its id")
        self.assertEqual(self.go({"exclude": [{"mac": "..:77:77:77"}]}, [self.PHONE], rates=rates), "Mini-Two and 1 more", "a wifi client by MAC leaves the wired leader")
        self.assertEqual(self.go({}, [self.PHONE], rates=rates), "Phone-Six")

    def test_filtering_changes_only_the_card_the_readings_stay_in_the_history(self):
        self.go({"exclude": [{"id": "Rack-C|3"}]})
        grid = self.s.grid({A}, 60, self.t)
        self.assertTrue(any(v is not None for v in grid[A][0]), "the port's own history is untouched")
