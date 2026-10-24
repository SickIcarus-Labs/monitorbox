"""Throughput graphs end to end: save the list through the API, read a fake SNMP device's counters, get rates back."""
import json, os, sys, threading, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T, snmp_fake as F
from unifi_fake import Controller
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

N, HCI, HCO = "1.3.6.1.2.1.31.1.1.1.1", "1.3.6.1.2.1.31.1.1.1.6", "1.3.6.1.2.1.31.1.1.1.10"


class GraphsE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def start_device(self):
        agent = F.Agent(community="fake-comm-g1"); self.addCleanup(agent.close)
        agent.mib = {f"{N}.1": "bond0", f"{HCI}.1": ("c64", 1_000_000), f"{HCO}.1": ("c64", 2_000_000), "1.3.6.1.2.1.31.1.1.1.15.1": ("gauge", 2500)}
        c = self.start()
        self.configure(c, [{"id": "nas", "module": "snmp", "name": "Granite", "host": "127.0.0.1", "port": agent.port, "version": "2c",
                            "community": "fake-comm-g1", "timeout": 1, "retries": 0}],
                       [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        stop = threading.Event()
        def traffic():                      # the counters grow 125000 bytes/s in, 250000 out = 1 / 2 Mbit/s
            n = 0
            while not stop.wait(0.2):
                n += 1
                agent.mib[f"{HCI}.1"] = ("c64", 1_000_000 + n * 25_000); agent.mib[f"{HCO}.1"] = ("c64", 2_000_000 + n * 50_000)
        threading.Thread(target=traffic, daemon=True).start(); self.addCleanup(stop.set)
        return c

    def test_a_saved_graph_gets_rates_from_the_devices_counters(self):
        c = self.start_device()
        self.assertEqual(c.get("/api/graphs"), {"graphs": []})
        saved = c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "title": "Granite bond"}]})
        self.assertEqual(saved["graphs"][0]["id"], "nas-bond0")
        self.assertEqual(c.get("/api/graphs")["graphs"][0]["title"], "Granite bond")
        def pts():
            return c.get("/api/graphs/data?seconds=60")["graphs"][0]["points"]
        T.wait(lambda: len(pts()) >= 2, 20)
        rin, rout = pts()[-1][1:]
        self.assertTrue(800_000 < rin < 1_200_000 and 1_700_000 < rout < 2_300_000, (rin, rout))

    def test_the_gateways_wan_port_is_named_from_the_unifi_login_on_the_same_address(self):
        ctl = Controller(); self.addCleanup(ctl.close)
        ctl.devices[0].update({"wan1": {"ifname": "eth9", "name": "eth9", "ip": "203.0.113.9", "up": True, "speed": 5000},
                               "port_table": [{"ifname": "eth8", "name": "WAN 2", "network_name": "wan2", "up": False}, {"ifname": "eth0", "name": "Port 1"}]})
        c = self.start_device()
        rev = c.get("/api/config/connections")["revision"]
        conns = c.get("/api/config/connections")["connections"]
        conns.append({"id": "gw-unifi", "module": "unifi-network", "base_url": ctl.url.replace("localhost", "127.0.0.1"), "username": ctl.username, "password": ctl.password, "timeout": 1})
        self.assertIn("revision", c.post("/api/config/connections", {"connections": conns, "revision": rev}))
        got = c.post("/api/graphs/wan", {"connection": "nas"})["ports"]
        self.assertEqual([(p["ifname"], p["ip"], p["up"]) for p in got], [("eth8", "", False), ("eth9", "203.0.113.9", True)])
        self.assertEqual([(p["label"], p["speedMbps"]) for p in got], [("WAN 2", None), ("WAN", 5000)], "named WAN, not after the port; the speed it negotiated")
        self.assertEqual(c.post("/api/graphs/wan", {"connection": "nope"}), {"ports": []})

    def test_the_switch_report_asks_every_unifi_login_and_snmp_device_and_a_silent_one_does_not_stop_the_rest(self):
        ctl = Controller(); self.addCleanup(ctl.close)
        c = self.start_device()
        rev = c.get("/api/config/connections")["revision"]
        conns = c.get("/api/config/connections")["connections"]
        conns.append({"id": "gw-unifi", "module": "unifi-network", "base_url": ctl.url.replace("localhost", "127.0.0.1"), "username": ctl.username, "password": ctl.password, "timeout": 1})
        conns.append({"id": "dead-snmp", "module": "snmp", "name": "Dead", "host": "127.0.0.1", "port": 9, "version": "2c", "community": "fake-comm-g2", "timeout": 1, "retries": 0})
        self.assertIn("revision", c.post("/api/config/connections", {"connections": conns, "revision": rev}))
        got = c.get("/api/lan/report")
        by = {s["connection"]: s for s in got["sources"]}
        self.assertEqual(sorted(by), ["dead-snmp", "gw-unifi", "nas"])
        self.assertEqual([p["name"] for p in by["nas"]["report"]["ports"]], ["bond0"])
        self.assertIn("Aggregation", [d["name"] for d in by["gw-unifi"]["report"]["devices"]])
        self.assertIn("error", by["dead-snmp"]); self.assertNotIn("report", by["dead-snmp"])
        text = json.dumps(got)
        for secret in ("fake-comm-g1", "fake-comm-g2", ctl.password):
            self.assertNotIn(secret, text, "connection settings are never part of the report")

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_switch_report_button_summarises_each_source_and_offers_the_full_report_to_copy(self):
        c = self.start_device()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/advanced"); pg.wait_for_selector("text=Ask the switches")
            self.assertTrue(pg.is_hidden("#lancopy"))
            pg.click("text=Ask the switches")
            pg.wait_for_selector("#lanout >> text=1 ports in use", timeout=30000)
            self.assertIn("(SNMP", pg.inner_text("#lanout"))
            self.assertTrue(pg.is_visible("#lancopy"))
            rep = json.loads(pg.evaluate("LANTXT"))
            self.assertEqual([x["connection"] for x in rep["sources"]], ["nas"])
            self.assertNotIn("fake-comm-g1", json.dumps(rep))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_busiest_cards_filters_are_set_on_the_graphs_page_and_a_client_can_be_hidden_and_shown_again(self):
        c = self.start_device()
        c.post("/api/graphs", {"graphs": [{"kind": "busiest"}]})
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.wait_for_selector("text=Choose which devices this card may show")
            saved = lambda: c.get("/api/graphs")["graphs"][0].get("filter", {})
            def saved_is(want):                                                                  # a change is saved a moment after the click
                for _ in range(100):
                    if saved() == want:
                        return
                    time.sleep(0.05)
                self.assertEqual(saved(), want)
            self.assertEqual(saved(), {}, "nothing is stored until something differs from the defaults")
            pg.uncheck("text=Wi-Fi devices"); saved_is({"wifi": False})
            pg.fill("input[type=number][onchange^=bzFloor]", "2.5"); pg.keyboard.press("Tab")
            saved_is({"wifi": False, "floorMbps": 2.5})
            pg.evaluate("grCfg=[{kind:'busiest',title:'Busiest client'}]")                      # this page's memory is stale (another device changed the list): hiding must not undo the saved filters
            pg.evaluate("""async()=>{askYes=()=>Promise.resolve(true);bzPanel={leader:{name:'Fake Camera Box',mac:'AA:BB:CC:00:00:99',id:'Fake-Sw|9'}};await bzHide()}""")
            for _ in range(100):
                if "exclude" in saved():
                    break
                time.sleep(0.05)
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.reload(); pg.wait_for_selector("text=Hidden from this card")
            self.assertEqual(saved()["exclude"], [{"name": "Fake Camera Box", "mac": "AA:BB:CC:00:00:99"}])
            self.assertEqual((saved()["wifi"], saved()["floorMbps"]), (False, 2.5), "hiding added to the saved filters, not to a stale copy")
            self.assertIn("Fake Camera Box", pg.inner_text("#grset"))
            pg.click("text=Show again"); pg.wait_for_selector("text=Nothing is hidden")
            saved_is({"wifi": False, "floorMbps": 2.5})                                           # the exclusion is gone; the other filters stay
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_network_map_page_shows_the_tree_the_links_and_who_is_on_each_port(self):
        ctl = Controller(); self.addCleanup(ctl.close)
        d = {x["name"]: x for x in ctl.devices}
        d["Switch 2"].update({"port_table": [{"port_idx": 4, "name": "Port 4", "up": True, "speed": 10000, "rx_bytes-r": 125000, "tx_bytes-r": 250000},
                                             {"port_idx": 26, "name": "SFP28 26", "up": True, "is_uplink": True, "speed": 10000, "rx_bytes-r": 1250000, "tx_bytes-r": 625000}]})
        d["Switch 2"]["uplink"]["uplink_remote_port"] = 25; d["Switch 2"]["uplink"]["port_idx"] = 26
        ctl.clients = [{"name": "Distinct-Box-81", "ip": "192.0.2.81", "mac": "aa:bb:cc:00:00:81", "is_wired": True, "sw_mac": d["Switch 2"]["mac"], "sw_port": 4}]
        c = self.start_device()
        rev = c.get("/api/config/connections")["revision"]
        conns = c.get("/api/config/connections")["connections"]
        conns.append({"id": "gw-unifi", "module": "unifi-network", "base_url": ctl.url.replace("localhost", "127.0.0.1"), "username": ctl.username, "password": ctl.password, "timeout": 1})
        self.assertIn("revision", c.post("/api/config/connections", {"connections": conns, "revision": rev}))
        m = c.get("/api/lan/map")
        by = {n["name"]: n for n in m["nodes"]}                       # node ids are device addresses now (names can repeat), so look up by name
        self.assertEqual(by["Switch 2"]["parent"], by["Aggregation"]["id"])
        self.assertEqual((by["Switch 2"]["link"]["port"], by["Switch 2"]["link"]["parentPort"]), (26, 25))
        self.assertEqual((by["Switch 2"]["link"]["down"], by["Switch 2"]["link"]["up_bps"]), (10_000_000, 5_000_000))
        self.assertEqual([(p["port"], p["name"], p["down"], p["up_bps"]) for p in by["Switch 2"]["ports"]], [("4", "Distinct-Box-81", 2_000_000, 1_000_000)])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/map"); pg.wait_for_selector("#mapout .mnode", timeout=30000)
            txt = pg.inner_text("#mapout")
            for want in ("Bay Harbor", "Aggregation", "Switch 2", "Garage", "10 GbE to Aggregation (port 26 to 25)", "↓ 10 Mbit/s ↑ 5.0 Mbit/s", "10 GbE to Bay Harbor · no traffic figures"):
                self.assertIn(want, txt)
            pg.click("#mapout summary:has-text('1 port in use')")
            self.assertIn("Distinct-Box-81", pg.inner_text("#mapout"))
            pg.evaluate("mapLoad()"); pg.wait_for_timeout(1500)            # the page refreshes itself: an opened list must stay open
            self.assertIn("Distinct-Box-81", pg.inner_text("#mapout"))
            self.assertTrue(pg.evaluate("document.querySelector('#mapout details').open"))
            pg.click("#mapout summary:has-text('1 port in use')")          # and closing it sticks too
            pg.evaluate("mapLoad()"); pg.wait_for_timeout(1500)
            self.assertFalse(pg.evaluate("document.querySelector('#mapout details').open"))
            pg.click("#mapout summary:has-text('1 port in use')")
            pg.click("#mapout >> text=where does it go?"); pg.wait_for_selector("#mapout >> text=not a record of conversations", timeout=20000)
            self.assertIn("Where this port's traffic most likely goes", pg.inner_text("#mapout"))
            pg.evaluate("mapLoad()"); pg.wait_for_timeout(1500)                                    # the refresh keeps the answer open
            self.assertIn("not a record of conversations", pg.inner_text("#mapout"))
            pg.click("#mapout >> text=1 hour"); pg.wait_for_selector("#mapout >> text=not a record of conversations", timeout=20000)
            pg.click("#mapout >> text=hide"); self.assertNotIn("not a record of conversations", pg.inner_text("#mapout"))
            pg.click("text=← Advanced"); pg.wait_for_selector("#cfg")
            self.assertEqual(errs, [])
            b.close()

    def test_the_owner_can_set_the_top_of_a_graph_and_a_bad_value_is_refused(self):
        c = self.start_device()
        out = c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "maxMbps": 2500}]})
        self.assertEqual(out["graphs"][0]["maxMbps"], 2500)
        self.assertEqual(c.get("/api/graphs")["graphs"][0]["maxMbps"], 2500)
        for bad in (0, -5, "fast", 2.5, True, 10**7):
            self.assertEqual(c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "maxMbps": bad}]})["_status"], 400, bad)
        self.assertEqual(c.get("/api/graphs")["graphs"][0]["maxMbps"], 2500)

    def test_a_bad_list_is_refused_and_changes_nothing(self):
        c = self.start_device()
        c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0"}]})
        self.assertEqual(c.post("/api/graphs", {"graphs": [{"connection": "nope", "interface": "x"}]})["_status"], 400)
        self.assertEqual(len(c.get("/api/graphs")["graphs"]), 1)

    def test_the_graph_list_is_in_the_backup_folder(self):
        c = self.start_device()
        c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "title": "Distinct title 7"}]})
        with open(os.path.join(self.cfg, "config", "graphs.json")) as f:
            self.assertIn("Distinct title 7", f.read())

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_tapping_a_graph_time_at_the_bottom_of_the_graphs_page_stays_where_it_is(self):
        c = self.start_device()
        c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "title": "Granite bond"}, {"kind": "busiest"}]})
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 700, "height": 420})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.wait_for_selector("[aria-label='Panel graph window']")
            pg.add_style_tag(content="*{overflow-anchor:none!important}")                 # Safari (the iPad) does not hold the scroll position when a page is redrawn; Chromium does
            for label in ("Panel graph window", "Main screen graph window"):
                btn = pg.locator(f"[aria-label='{label}'] button[aria-pressed=false]").first
                btn.scroll_into_view_if_needed(); pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                before = pg.evaluate("window.scrollY"); self.assertGreater(before, 100, "the page is long enough to scroll")
                pg.evaluate("window._low = scrollY; addEventListener('scroll', () => { window._low = Math.min(window._low, scrollY) })")
                tapped = btn.inner_text(); btn.click(); pg.wait_for_timeout(1500)
                after = pg.evaluate("window.scrollY"); low = pg.evaluate("window._low")
                self.assertGreater(low, before - 5, f"tapping a time in '{label}' must not even flash to the top and back (was {before}, lowest {low})")
                self.assertEqual(pg.locator(f"[aria-label='{label}'] button[aria-pressed=true]").count(), 1, "the tapped time is the one lit")
                self.assertEqual(pg.locator(f"[aria-label='{label}'] button[aria-pressed=true]").inner_text(), tapped, "and it is the one that was tapped")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_graphs_are_chosen_in_settings_and_drawn_on_the_main_screen(self):
        c = self.start_device()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.wait_for_selector("#gp-conn")
            self.assertEqual(pg.inner_text("#gp-conn").strip(), "Granite", "the server's name, not its connection id")
            pg.click("text=Show its ports"); pg.wait_for_selector("#gp-list >> text=bond0")
            pg.click("#gp-list button:text-is(\"Add\")"); pg.fill("#ask-in", "Granite bond"); pg.click("#ask-ok")
            pg.wait_for_selector("#grset >> text=Granite bond")
            self.assertEqual([g["title"] for g in c.get("/api/graphs")["graphs"]], ["Granite bond"])
            pg.click("#grset button:text-is(\"Top speed\")"); pg.fill("#ask-in", "1000"); pg.click("#ask-ok")
            pg.wait_for_selector("#grset >> text=you set this")
            self.assertEqual(c.get("/api/graphs")["graphs"][0]["maxMbps"], 1000)
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector("#gr svg polyline", state="attached", timeout=30000)
            pg.wait_for_function("grData && grData.graphs[0] && grData.graphs[0].points.length >= 12", timeout=40000)   # it is a line, not a dot
            pg.wait_for_timeout(1200)
            self.assertIn("Mbit/s", pg.inner_text("#gr"))
            self.assertIn("1 Gbit/s", pg.inner_text("#gr"), "the top of the graph is the speed the owner set, not the port's 2.5 Gbit/s rating")
            self.assertIn("500 Mbit/s", pg.inner_text("#gr"), "with the half-way mark beside it")
            self.assertNotIn("2.5 Gbit/s", pg.inner_text("#gr"))
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "graphs.png"))
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.wait_for_selector("#grset >> text=Granite bond")
            pg.click("#grset button:text-is(\"Remove\")"); pg.click("#ask-ok")
            pg.wait_for_selector("#grset >> text=No graphs yet")
            self.assertEqual(c.get("/api/graphs")["graphs"], [])
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_tapping_a_graph_opens_a_longer_history_and_both_windows_are_chosen_in_settings(self):
        c = self.start_device()
        c.post("/api/graphs", {"graphs": [{"connection": "nas", "interface": "bond0", "title": "Granite bond"}]})
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.wait_for_selector("#gr [data-gp]", timeout=30000)
            self.assertEqual(pg.evaluate("grWin"), 300, "the main screen shows 5 minutes until told otherwise")
            self.assertEqual(pg.locator(".drawer.gp").count(), 0)
            pg.click("#gr [data-gp]")
            pg.wait_for_selector(".drawer.gp svg", timeout=30000)
            self.assertEqual(pg.evaluate("grPData && grPData.seconds"), 900, "the panel shows 15 minutes, three times the main screen")
            self.assertEqual(pg.get_attribute(".drawer.gp button:text-is('15 min')", "aria-pressed"), "true")
            txt = pg.inner_text(".drawer.gp")
            for want in ("Granite bond", "Now", "Average", "Peak", "one hour"):
                self.assertIn(want, txt)
            pg.wait_for_selector(".drawer.gp >> text=could not be matched", timeout=20000)       # the same list sits under every graph; this fake box has no map to match it to
            self.assertIn("Where its traffic goes", pg.inner_text(".drawer.gp"))
            pg.click(".drawer.gp button:text-is('1 hour')")
            T.wait(lambda: c.get("/api/display").get("gpanel") == 3600, what="the panel window saved on the box")
            pg.wait_for_function("grPData && grPData.seconds === 3600", timeout=15000)
            self.assertEqual(pg.get_attribute(".drawer.gp button:text-is('1 hour')", "aria-pressed"), "true")
            pg.click(".drawer.gp button:text-is('Close')")
            self.assertEqual(pg.locator(".drawer").count(), 0)
            self.assertIsNone(pg.evaluate("grPanel"))
            # Settings, Display: both windows, kept on the box and on this device
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/graphs"); pg.wait_for_selector("[aria-label='Panel graph window']")
            self.assertEqual(pg.get_attribute("[aria-label='Panel graph window'] button:text-is('1 hour')", "aria-pressed"), "true")
            pg.click("[aria-label='Main screen graph window'] button:text-is('15 min')")
            pg.click("[aria-label='Panel graph window'] button:text-is('30 min')")
            T.wait(lambda: c.get("/api/display").get("gwin") == 900 and c.get("/api/display").get("gpanel") == 1800, what="both windows saved on the box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector("#gr [data-gp]", timeout=30000)
            self.assertEqual(pg.evaluate("grWin"), 900)
            pg.click("#gr [data-gp]"); pg.wait_for_selector(".drawer.gp svg", timeout=30000)
            self.assertEqual(pg.get_attribute(".drawer.gp button:text-is('30 min')", "aria-pressed"), "true")
            # a device that has never chosen takes the box's choices
            fresh = b.new_page(viewport={"width": 1000, "height": 900})
            fresh.goto(f"http://127.0.0.1:{self.port}/"); fresh.wait_for_selector("input[type=password]")
            fresh.fill("input[type=password]", T.PASSWORD); fresh.keyboard.press("Enter"); fresh.wait_for_selector("#gr [data-gp]", timeout=30000)
            self.assertEqual(fresh.evaluate("grWin"), 900)
            self.assertEqual(fresh.evaluate("getGp()"), 1800)
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
