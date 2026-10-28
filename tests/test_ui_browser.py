"""Browser regression tests (skipped where Playwright/Chromium is not installed):
- the side drawer keeps its scroll position when live updates redraw it
- Pick what to watch (tick, Apply) puts the checks UNDER the device that already pings that host, not as separate entries"""
import json, os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T, snmp_fake as F
from unifi_fake import Controller
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

class UI(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_ping_can_be_added_by_hand_and_bound_to_a_server(self):
        c = self.start()
        self.configure(c, [], [])
        r = c.post("/api/ping", {"name": "Granite ping", "target": "192.0.2.13"})
        nodes = c.get("/api/config/monitoring")["monitoring"]["nodes"]
        self.assertTrue(any(k.get("target") == "192.0.2.13" and k["type"] == "ping" for n in nodes for k in n["checks"]), (r, nodes))

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_setup_is_one_page_servers_expand_in_place_and_the_summary_has_edit_and_launch(self):
        c = self.start()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .head")
            pg.goto(f"http://127.0.0.1:{self.port}/#/setup"); pg.wait_for_selector("#sx-host")
            row = lambda: pg.evaluate("setupRowHtml({host:'127.0.0.9',name:'x'},{module:'portainer',label:'Portainer',found:false,note:'Point MonitorBox at that server instead.'})")
            self.assertIn("Point MonitorBox at that server", row())                      # no Portainer server added yet: say what to do
            pg.evaluate("setupConns=[{id:'p',module:'portainer',base_url:'https://x'}]")
            self.assertIn("managed by the Portainer server you added", row())          # one is: the agent's box is already covered
            pg.evaluate("setupConns=[]")
            pg.fill("#sx-host", "127.0.0.2"); pg.click("#sx-form button:has-text('Add')")
            pg.wait_for_selector(".box[data-h='127.0.0.2']")
            T.wait(lambda: any(k.get("target") == "127.0.0.2" for n in c.get("/api/config/monitoring")["monitoring"]["nodes"] for k in n["checks"]), what="the new server's ping check")
            pg.fill("#nm-127_0_0_2", "Granite"); pg.press("#nm-127_0_0_2", "Tab")                     # a typed name sticks: on the card, and on the main screen
            T.wait(lambda: any(n["name"] == "Granite" for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]), what="the system renamed")
            self.assertNotIn("Add anyway", pg.inner_text(".box[data-h='127.0.0.2']"))     # what was not seen is not offered
            pg.select_option(".box[data-h='127.0.0.2'] select", "snmp")            # a service the scan missed, added by hand
            pg.wait_for_selector("#ied #devs")                                   # the form opens in place
            self.assertTrue(pg.url.endswith("#/setup"))                          # and the page never changed
            pg.click(".box[data-h='127.0.0.2'] button:has-text('Ping an address')")
            pg.click("#slot-m-127_0_0_2 button:has-text('Add')"); pg.wait_for_selector("#sx-msg:has-text('Added')")
            self.assertEqual(pg.input_value("#nm-127_0_0_2"), "Granite", "the name was not lost when the page redrew")
            pg.click("text=Save and finish"); pg.wait_for_selector("h1:has-text('Summary')")
            pg.wait_for_selector("#rvout:has-text('127.0.0.2')")                  # (the summary fills in once it has read the settings)
            pg.click("button:has-text('Edit')"); pg.wait_for_selector("#sx-host")
            self.assertTrue(pg.locator(".box[data-h='127.0.0.2']").count() >= 1)
            pg.click("text=Save and finish"); pg.wait_for_selector("h1:has-text('Summary')")
            pg.click("text=Save and launch"); pg.wait_for_selector(".head, .card")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_new_browser_gets_the_boxs_view_and_a_change_is_kept_on_the_box(self):
        c = self.start()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .head")
            pg.click("button:text-is('Detailed')")
            T.wait(lambda: c.get("/api/display").get("view") == "detail", what="the choice saved on the box")
            fresh = b.new_page(viewport={"width": 900, "height": 900})          # a browser that has never chosen
            fresh.goto(f"http://127.0.0.1:{self.port}/"); fresh.wait_for_selector("input[type=password]")
            fresh.fill("input[type=password]", T.PASSWORD); fresh.keyboard.press("Enter"); fresh.wait_for_selector(".card, .head")
            fresh.wait_for_function("localStorage.getItem('mb-view')==='detail'")      # filled in from the box, not chosen on this browser
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_watch_folds_into_the_device_and_the_drawer_keeps_its_scroll(self):
        a = F.Agent(community="fake-comm-zz"); self.addCleanup(a.close)
        a.mib = T.rows([(1, "/data", 100)])
        a.mib.update({"1.3.6.1.2.1.1.3.0": ("ticks", 5000), "1.3.6.1.2.1.1.5.0": "nas"})
        c = self.start()
        self.configure(c, [{"id": "nas", "module": "snmp", "host": "127.0.0.1", "port": a.port, "version": "2c", "community": "fake-comm-zz", "timeout": 1, "retries": 0}],
                       [{"id": "dev", "name": "Nas", "group": "Servers", "critical": True, "rule": "primary", "checks": [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 700})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.evaluate("pickFor('nas')"); pg.wait_for_selector("#detout input[type=checkbox]")
            pg.evaluate("$('#detid').value='NAS';detect()"); pg.wait_for_selector("#detout input[type=checkbox]")   # id typed in capitals
            self.assertEqual(pg.input_value("#detid"), "nas")
            applied = lambda: pg.wait_for_selector("#pickmsg:has-text('Saved')")
            # first time: sensible items are ticked already (interfaces are not), one Apply adds them all
            self.assertTrue(pg.locator("#detout div.row", has_text="Network interfaces").count() == 0 or
                            pg.locator("#detout label", has_text="Interface").locator("input:checked").count() == 0)
            self.assertIn("Apply (+", pg.inner_text("#pickapply"))
            pg.click("#pickapply"); applied()
            mon = c.get("/api/config/monitoring")["monitoring"]
            self.assertEqual(len(mon["nodes"]), 1); self.assertGreater(len(mon["nodes"][0]["checks"]), 1)
            # a device may carry far more than 8 checks (the Pi's Anchor3 hit that limit), and long names get valid ids
            long_name = "/" + "x" * 50
            for k in range(12):
                a.mib.update(T.rows([(10 + k, f"/disk{k}" if k else long_name, 5)]))
            pg.evaluate("detect()"); pg.wait_for_selector("#detout input[type=checkbox]")
            pg.on("dialog", lambda d: (errs.append("dialog: " + d.message), d.dismiss()))
            pg.locator("#detout div.row", has_text="Volumes").get_by_role("button", name="All").click()
            pg.click("#pickapply"); applied()
            mon = c.get("/api/config/monitoring")["monitoring"]
            self.assertGreater(len(mon["nodes"][0]["checks"]), 12)
            self.assertEqual(len(mon["nodes"]), 1)
            # untick one: it leaves the device, and Re-detect remembers what is watched
            before = len(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["checks"])
            watching = pg.locator("#detout label", has_text="watching").count()
            self.assertGreater(watching, 0)
            pg.locator("#detout label", has_text="watching").first.locator("input").uncheck()
            self.assertIn("\u22121", pg.inner_text("#pickapply"))
            pg.click("#pickapply"); applied()
            self.assertEqual(len(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["checks"]), before - 1)
            pg.evaluate("detect()"); pg.wait_for_selector("#detout input[type=checkbox]")
            self.assertEqual(pg.locator("#detout label", has_text="watching").count(), watching - 1)
            # a whole group in one tap (22 disks on a NAS): one saved revision for all of it
            rev0 = c.get("/api/config/monitoring")["revision"]
            vols = lambda: [x for x in c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["checks"] if x.get("check") == "volume"]
            self.assertGreater(len(vols()), 3)
            vrow = lambda: pg.locator("#detout div.row", has_text="Volumes")
            vrow().get_by_role("button", name="None").click(); pg.click("#pickapply"); applied()
            self.assertEqual(vols(), [])
            self.assertEqual(c.get("/api/config/monitoring")["revision"], rev0 + 1)
            vrow().get_by_role("button", name="All").click(); pg.click("#pickapply"); applied()
            self.assertGreater(len(vols()), 3)
            self.assertEqual(c.get("/api/config/monitoring")["revision"], rev0 + 2)
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector(".card"); pg.click(".card")
            pg.wait_for_selector(".drawer")
            self.assertIn("snmp Volume /data", pg.inner_text(".drawer"))
            # the 30-day strip: the device has been healthy for a while, so it shows a bar and a plain sentence
            pg.wait_for_selector(".drawer .hist .hbar")
            self.assertIn("available", pg.inner_text(".drawer .hist"))
            h = c.get("/api/history?node=dev")
            self.assertEqual(h["segments"][0][2], "healthy"); self.assertEqual(h["outages"], 0)
            self.assertEqual(c.get("/api/history?node=dev&seconds=3600")["window"], 3600)
            self.assertIn("Last 30 days", pg.inner_text(".drawer .hist"))
            # the length of history shown is a setting on this device and is remembered
            pg.evaluate("closeDrawer()")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/display"); pg.wait_for_selector('[aria-label="History length"]')
            pg.click('[aria-label="History length"] >> text=1 hour')
            pg.wait_for_selector('[aria-label="History length"] button[aria-pressed=true]:has-text("1 hour")')
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector(".card"); pg.click(".card"); pg.wait_for_selector(".drawer .hist .hbar")
            self.assertIn("Last hour", pg.inner_text(".drawer .hist"))
            pg.reload(); pg.wait_for_selector(".card"); pg.click(".card"); pg.wait_for_selector(".drawer .hist .hbar")
            self.assertIn("Last hour", pg.inner_text(".drawer .hist"))
            pg.set_viewport_size({"width": 1200, "height": 260})
            pg.evaluate("document.querySelector('.drawer').scrollTop=90")
            before = pg.evaluate("document.querySelector('.drawer').scrollTop")
            pg.evaluate("lastTouch=0;render()")     # what a live update does (when the panel is not being touched): rebuilds the whole page, side panel included
            after = pg.evaluate("document.querySelector('.drawer').scrollTop")
            print("scroll", before, after); self.assertGreater(before, 0); self.assertEqual(before, after)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_drawer_is_not_rebuilt_under_a_scrolling_finger(self):
        c = self.start()
        self.configure(c, [], [{"id": "dev", "name": "Nas", "group": "Servers", "critical": True, "rule": "primary",
                                "checks": [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 700})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.click(".card"); pg.wait_for_selector(".drawer")
            pg.evaluate("lastTouch=0; window.__d=document.querySelector('.drawer')")
            same = lambda: pg.evaluate("document.querySelector('.drawer')===window.__d")
            pg.evaluate("render()")
            self.assertTrue(same(), "a redraw must keep the very same panel element (replacing it made the panel blink every few seconds)")
            pg.evaluate("snap.cards[drawer.i].line='numbers that changed in the test'; render()")      # new content (a check's response time, say) goes into the same panel too
            self.assertTrue(same(), "when the content changes the panel must still be the same element, or it blinks whenever a number moves (and this test flaked on timing)")
            self.assertIn("numbers that changed in the test", pg.inner_text(".drawer"))
            pg.evaluate("document.querySelector('.drawer').dispatchEvent(new Event('touchmove',{bubbles:true}))")
            pg.evaluate("render()")                                  # a live update arrives mid-scroll
            self.assertTrue(same(), "the panel must not be replaced while a finger is on it")
            pg.wait_for_timeout(1000); self.assertTrue(same())             # and the deferred redraw afterwards leaves it alone too
            # a status update that differs only in each check's round-trip time is not worth a redraw
            sig = lambda a, b2: pg.evaluate("([a,b])=>statusSig(a)===statusSig(b)", [a, b2])
            self.assertTrue(sig('{"generatedAt":"1","ms":12.5,"x":1}', '{"generatedAt":"2","ms":99,"x":1}'))
            self.assertFalse(sig('{"ms":12.5,"state":"healthy"}', '{"ms":12.5,"state":"failed"}'))
            self.assertEqual(errs, [])
            b.close()


    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_every_check_view_works_on_a_big_screen_and_a_phone_and_is_remembered(self):
        c = self.start()
        self.configure(c, [], [
            {"id": "nas", "name": "Nas", "group": "Servers", "critical": True, "rule": "primary",
             "checks": [{"id": "up", "type": "tcp", "target": "127.0.0.1", "port": self.port, "label": "Web port"},
                        {"id": "dead", "type": "tcp", "target": "127.0.0.1", "port": 1, "timeout": 0.5, "label": "Closed port"}]},
            {"id": "pi", "name": "Pi", "group": "Servers", "rule": "primary",
             "checks": [{"id": "up", "type": "tcp", "target": "127.0.0.1", "port": self.port}]},
            {"id": "gol", "name": "Granite", "group": "Servers", "rule": "primary",
             "checks": [{"id": "a", "type": "tcp", "target": "127.0.0.1", "port": self.port, "label": "Disk A"},
                        {"id": "b", "type": "tcp", "target": "127.0.0.1", "port": self.port, "label": "Disk B"},
                        {"id": "c", "type": "tcp", "target": "127.0.0.1", "port": self.port, "label": "Disk C"},
                        {"id": "f", "type": "tcp", "target": "127.0.0.1", "port": self.port, "label": "Fan"}]},
            {"id": "gw", "name": "Gateway", "group": "Network", "rule": "primary", "checks": [{"id": "a", "type": "tcp", "target": "127.0.0.1", "port": self.port}]},
            {"id": "p1", "name": "Ping one", "group": "Servers", "rule": "primary", "checks": [{"id": "a", "type": "tcp", "target": "127.0.0.1", "port": self.port}]},
            {"id": "p2", "name": "Ping two", "group": "Servers", "rule": "primary", "checks": [{"id": "a", "type": "tcp", "target": "127.0.0.1", "port": self.port}]},
            {"id": "web", "name": "Web check", "group": "Servers", "rule": "primary", "dependsOn": ["pings"], "checks": [{"id": "a", "type": "tcp", "target": "127.0.0.1", "port": self.port}]},
            {"id": "pings", "name": "All pings", "group": "Servers", "kind": "aggregate", "children": ["p1", "p2"], "rule": "any"}])
        no_sideways = "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card")
            self.assertEqual(pg.locator(".card.det").count(), 0, "summary is the default")
            pg.click("text=Detailed"); pg.wait_for_selector(".card.det .rw")
            pg.wait_for_selector(".rw:has-text('Closed port')")      # Nas opens by itself once its closed port has answered
            text = pg.inner_text(".card.det")
            for want in ("Servers", "Nas", "Web port", "Closed port", "Pi", "Granite"):
                self.assertIn(want, text)
            self.assertEqual(pg.locator(".seg button[aria-pressed=true]").first.inner_text(), "Detailed")
            # a healthy device with several checks is one line with a roll-up; tapping it opens the list
            before = pg.locator(".rw.sub1").count()
            self.assertEqual(pg.locator(".rw", has_text="Disk A").count(), 0, "folded: the disks are not listed")
            self.assertEqual(pg.locator(".rw", has_text="Ping one").count(), 0, "folded: the aggregate's children are nested, not listed")
            self.assertEqual(pg.locator(".card.det .rw", has_text="Web check").count(), 0, "folded: dependents are nested, not listed")
            pg.locator(".rw[aria-expanded=false]", has_text="Granite").click()
            pg.wait_for_selector(".rw:has-text('Fan')")
            self.assertEqual(pg.locator(".rw", has_text="Disk A").count(), 0, "the Disks subgroup inside Granite is folded too")
            disks = pg.locator(".rw[aria-expanded=false]", has_text="Disks"); self.assertIn("3 checks", disks.inner_text()); disks.click()
            pg.wait_for_selector(".rw:has-text('Disk C')")
            pg.locator(".rw[aria-expanded=false]", has_text="All pings").click(); pg.wait_for_selector(".rw:has-text('Ping two')")
            self.assertEqual(pg.locator(".rw:has-text('Web check')").count(), 1, "a check that depends on the aggregate is nested under it")
            # opening folds must not move a card to another column
            cols = lambda: pg.evaluate("[...document.querySelectorAll('.col')].map(c=>[...c.querySelectorAll('.card')].map(x=>x.querySelector('.t').innerText))")
            opened = cols(); pg.locator(".rw[aria-expanded=true]", has_text="Granite").click(); self.assertEqual(cols(), opened)
            self.assertIn("rw two", pg.evaluate("line('go()','healthy','UPS networkups','online · battery 100% · load 28% · 24 min runtime',0)"), "long detail gets its own line")
            self.assertNotIn("rw two", pg.evaluate("line('go()','healthy','Gateway','reply from 192.168.77.1',0)"))
            self.assertEqual(pg.locator(".rw").evaluate_all("els=>els.filter(e=>e.scrollHeight>e.clientHeight+1).length"), 0, "rows stay one line")
            pg.locator(".rw", has_text="Closed port").click(); pg.wait_for_selector(".drawer")      # a row opens that item
            self.assertIn("Closed port", pg.inner_text(".drawer"))
            pg.reload(); pg.wait_for_selector(".card.det .rw")                                      # remembered on this device
            for width, height in ((390, 844), (768, 1024)):
                pg.set_viewport_size({"width": width, "height": height}); pg.wait_for_selector(".card.det .rw")
                self.assertTrue(pg.evaluate(no_sideways), f"every-check view overflows sideways at {width}px")
                pg.click(".seg button:has-text('Summarized')"); pg.wait_for_selector(".card:not(.det)")
                self.assertTrue(pg.evaluate(no_sideways), f"summary view overflows sideways at {width}px")
                pg.click(".seg button:has-text('Detailed')"); pg.wait_for_selector(".card.det .rw")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/display"); pg.wait_for_selector(".seg")     # the setting lives in Settings too
            self.assertEqual(pg.locator(".seg button[aria-pressed=true]").first.inner_text(), "Detailed")
            pg.locator(".seg button", has_text="Summarized").first.click(); pg.wait_for_function("document.querySelector('.seg button[aria-pressed=true]').innerText==='Summarized'")
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector(".card")
            self.assertEqual(pg.locator(".card.det").count(), 0)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_server_is_added_with_a_service_tested_edited_and_never_shows_its_password(self):
        ctl = Controller(); self.addCleanup(ctl.close)
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "localhost", "port": self.port}]}])
        no_sideways = "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
        cfgfile = os.path.join(self.cfg, "config", "monitorbox.json")
        def stored():
            with open(cfgfile) as f: return json.load(f)["connections"]
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a server")
            pg.fill("#n-name", "Fake network"); pg.fill("#n-host", ctl.url); pg.click("#devs button:text-is(\"Next\")")
            pg.wait_for_selector("#s-name"); self.assertIn("Not saved yet", pg.inner_text("#devs"))
            self.assertEqual(stored(), [], "a server with no service is not saved yet")
            pg.click("#devs >> text=UniFi Network controller"); pg.wait_for_selector("#f-username")
            pg.fill("#f-username", ctl.username)
            pg.fill("#f-password", "fake-wrong-pw-1"); pg.click("#devtestbtn"); pg.wait_for_selector(".badbox")
            self.assertIn("user name or password", pg.inner_text(".badbox"))
            pg.fill("#f-password", ctl.password); pg.click("#devtestbtn"); pg.wait_for_selector(".okbox")
            self.assertIn("It answered", pg.inner_text(".okbox"))
            pg.click("#devs button:text-is(\"Save, then pick what to watch\")"); pg.wait_for_selector("#pickapply"); pg.wait_for_selector("#devs .devrow")     # one Save: it saves, then offers the pick list
            self.assertEqual([(x["id"], x["module"], x["name"], x["username"], x["password"]) for x in stored()],
                             [("fake-network-unifi-network", "unifi-network", "Fake network", ctl.username, ctl.password)])
            pg.click("#devs button:text-is(\"Close\")"); pg.wait_for_selector("#devs .devrow")
            self.assertIn("Fake network", pg.inner_text("#devs")); self.assertIn("UniFi", pg.inner_text("#devs"))
            # editing the service shows dots, not the password, and testing with the dots still works
            pg.click("#devs .devrow:has-text(\"Fake network\") >> text=Open"); pg.wait_for_selector("#s-name"); pg.click("#devs .devrow >> text=Edit"); pg.wait_for_selector("#f-password")
            self.assertNotEqual(pg.input_value("#f-password"), ctl.password); self.assertNotIn(ctl.password, pg.content())
            pg.click("#devtestbtn"); pg.wait_for_selector(".okbox")
            pg.set_viewport_size({"width": 390, "height": 844}); self.assertTrue(pg.evaluate(no_sideways), "the service form overflows sideways on a phone")
            pg.click("#devs button:text-is(\"Cancel\")"); pg.wait_for_selector("#s-name"); self.assertTrue(pg.evaluate(no_sideways))
            # renaming the server renames it everywhere it is saved; the password is untouched
            pg.fill("#s-name", "Renamed box"); pg.click("text=Save name and address"); pg.wait_for_function("document.querySelector('#s-name').value==='Renamed box'")
            self.assertEqual((stored()[0]["name"], stored()[0]["password"]), ("Renamed box", ctl.password))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_servers_page_has_rescan_buttons_and_no_redetect_box(self):
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a server"); pg.fill("#n-name", "Nas"); pg.fill("#n-host", "192.0.2.50"); pg.click("#devs button:text-is(\"Next\")")
            pg.click("#devs button:text-is(\"Wake on LAN\")"); pg.wait_for_selector("#w-macs")
            pg.fill("#w-macs", "aa:bb:cc:dd:ee:01"); pg.click("#devs button:text-is(\"Save\")"); pg.wait_for_selector("#s-name")
            pg.click("#devs button:text-is(\"Close\")"); pg.wait_for_selector("#devs button:text-is(\"Rescan all servers\")")
            body = pg.inner_text("#m")
            self.assertNotIn("Re-detect", body); self.assertNotIn("Detect this box", body)
            pg.click("#devs .devrow >> text=Open"); pg.wait_for_selector("#s-name")
            pg.click("#devs button:text-is(\"Rescan this server\")")
            pg.wait_for_selector("#card-192_0_2_50")
            self.assertTrue(pg.url.endswith("#/setup"))
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_removing_a_server_removes_its_system_and_checks_too(self):
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        cfgfile = os.path.join(self.cfg, "config", "monitorbox.json")
        def ids():
            with open(cfgfile) as f: return [n["id"] for n in json.load(f)["monitoring"]["nodes"]]
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a server"); pg.fill("#n-name", "Nas"); pg.fill("#n-host", "192.0.2.50"); pg.click("#devs button:text-is(\"Next\")")
            pg.click("#devs button:text-is(\"Wake on LAN\")"); pg.wait_for_selector("#w-macs")
            pg.fill("#w-macs", "aa:bb:cc:dd:ee:01"); pg.click("#devs button:text-is(\"Save\")"); pg.wait_for_selector("#s-name")
            self.assertEqual(ids(), ["pi", "nas"])
            pg.click("text=Remove this server"); pg.click("#ask-ok")
            pg.wait_for_selector("#devs >> text=Add a server")
            T.wait(lambda: ids() == ["pi"])
            self.assertEqual(ids(), ["pi"], "only the removed server's system goes")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_wake_on_lan_is_added_edited_and_removed_on_the_servers_page(self):
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        cfgfile = os.path.join(self.cfg, "config", "monitorbox.json")
        def node(i):
            with open(cfgfile) as f: return {n["id"]: n for n in json.load(f)["monitoring"]["nodes"]}.get(i)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a server"); pg.fill("#n-name", "Nas"); pg.fill("#n-host", "192.0.2.50"); pg.click("#devs button:text-is(\"Next\")")
            pg.click("#devs button:text-is(\"Wake on LAN\")"); pg.wait_for_selector("#w-macs")
            pg.fill("#w-macs", "AA-BB-CC-DD-EE-01\n11.22.33.44.55.66"); pg.fill("#w-bc", "192.0.2.255"); pg.fill("#w-to", "90")
            pg.click("#devs button:text-is(\"Save\")"); pg.wait_for_selector("#s-name")
            nas = node("nas")
            self.assertEqual(nas["wake"], {"macs": ["aa:bb:cc:dd:ee:01", "11:22:33:44:55:66"], "broadcast": "192.0.2.255", "timeout": 90})
            self.assertEqual([k["target"] for k in nas["checks"]], ["192.0.2.50"], "a server made for waking gets a ping so MonitorBox can see it come up")
            self.assertTrue(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
            # a bad MAC is refused in words and nothing changes
            pg.click("#devs .devrow >> text=Edit"); pg.fill("#w-macs", "not-a-mac"); pg.click("#devs button:text-is(\"Save\")")
            pg.wait_for_selector("#wakemsg li"); self.assertIn("not a MAC address", pg.inner_text("#wakemsg"))
            self.assertEqual(node("nas")["wake"]["macs"][0], "aa:bb:cc:dd:ee:01")
            pg.fill("#w-macs", "aa:bb:cc:dd:ee:02"); pg.fill("#w-to", ""); pg.click("#devs button:text-is(\"Save\")"); pg.wait_for_selector("#s-name")
            self.assertEqual(node("nas")["wake"], {"macs": ["aa:bb:cc:dd:ee:02"], "broadcast": "192.0.2.255"})
            pg.click("#devs .devrow >> text=Edit"); pg.click("text=Remove wake settings"); pg.click("#ask-ok")
            pg.wait_for_selector("#devs >> text=Add a server")
            self.assertIsNone(node("nas").get("wake"))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_system_is_renamed_from_its_page(self):
        c = self.start()
        self.configure(c, [], [{"id": "old", "name": "Bay Harbor", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card"); pg.wait_for_selector(".drawer"); pg.click(".drawer >> text=Rename")
            pg.fill("#ask-in", "Monitor"); pg.click("#ask-ok")
            pg.wait_for_function("document.body.innerText.includes('Monitor')")
            self.assertEqual(c.get("/api/status")["nodes"]["old"]["name"], "Monitor")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_system_gets_its_own_grace_period_from_the_monitoring_editor_and_can_go_back_to_the_site_setting(self):
        c = self.start()
        self.configure(c, [], [{"id": "old", "name": "Bay Harbor", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        node = lambda: c.get("/api/config/monitoring")["monitoring"]["nodes"][0]
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card"); pg.wait_for_selector(".drawer")
            pg.click(".drawer >> text=Edit monitoring"); pg.wait_for_selector("#me-n")
            pg.fill("#me-n", "3"); pg.fill("#me-s", "90"); pg.click("#me-ok"); pg.wait_for_selector("#medit", state="detached")
            T.wait(lambda: node().get("confirmFailures") == 3, what="the failures saved")
            self.assertEqual((node()["confirmFailures"], node()["confirmSeconds"]), (3, 90))
            pg.click(".drawer >> text=Edit monitoring"); pg.wait_for_selector("#me-n"); self.assertEqual(pg.input_value("#me-n"), "3")   # shows what it is now
            pg.fill("#me-n", "2.5"); pg.click("#me-ok"); pg.wait_for_function("document.querySelector('#me-msg').textContent.length>0")  # a bad value is refused in the editor
            self.assertEqual(node()["confirmFailures"], 3)
            pg.fill("#me-n", ""); pg.fill("#me-s", ""); pg.click("#me-ok"); pg.wait_for_selector("#medit", state="detached")
            T.wait(lambda: "confirmFailures" not in node() and "confirmSeconds" not in node(), what="back to the site setting")
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_expected_down_quiets_the_banner_and_stop_watching_removes_the_system(self):
        c = self.start()
        self.configure(c, [], [{"id": "nas", "name": "NAS", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": 1}]},
                               {"id": "web", "name": "Web", "group": "Services", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.wait_for_function("document.querySelector('.head') && document.querySelector('.head').innerText.includes('down')")
            pg.click(".card >> text=NAS"); pg.wait_for_selector(".drawer")
            pg.click(".drawer >> text=Mark expected down")
            pg.wait_for_function("document.querySelector('.head').innerText.includes('Everything is fine')")
            self.assertIn("Down, expected", pg.inner_text(".drawer"))
            n = c.get("/api/status")["nodes"]["nas"]
            self.assertEqual((n["state"], n["expected"]), ("failed", True))          # observed state untouched
            pg.click(".drawer >> text=Clear expected down")
            pg.wait_for_function("!document.querySelector('.head').innerText.includes('Everything is fine')")
            self.assertEqual(c.get("/api/config/monitoring")["monitoring"].get("expectedDown"), None)
            pg.click(".drawer >> text=Stop watching"); pg.click("#ask-ok")
            pg.wait_for_function("document.querySelector('.head').innerText.includes('Everything is fine')")
            self.assertEqual([x["id"] for x in c.get("/api/config/monitoring")["monitoring"]["nodes"]], ["web"])
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_web_checks_address_can_be_edited_from_the_system_drawer(self):
        c = self.start()
        self.configure(c, [], [{"id": "ph", "name": "Pihole", "group": "Services", "checks": [{"id": "web", "type": "http", "url": f"http://127.0.0.1:{self.port}/nothing-here"}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card >> text=Pihole"); pg.wait_for_selector(".drawer")
            pg.click(".drawer >> text=Edit monitored address")
            pg.fill("#ask-in", f"http://127.0.0.1:{self.port}/admin/"); pg.click("#ask-ok")
            pg.wait_for_function("document.querySelector('.drawer').innerText.includes('/admin/')")
            url = c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["checks"][0]["url"]
            self.assertTrue(url.endswith("/admin/"), url)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_setup_detects_the_box_watches_the_network_and_hands_over_to_the_servers_page(self):
        c = self.start()
        self.configure(c, [], [{"id": "web", "name": "Web", "group": "Services", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        real = c.get("/api/thisbox")                                    # the real endpoint answers, whatever this machine is
        # (the scan now also reports whether the gateway is a UniFi console and a MAC address, for the Set up page's new steps)
        self.assertEqual({"hostname", "ip", "gateway", "dns", "services", "gatewayUnifi", "mac"}, set(real))
        fake = {"hostname": "pi-box", "ip": "192.0.2.5", "gateway": "192.0.2.1", "dns": ["192.0.2.53", "192.0.2.54"],
                "services": [{"module": "snmp", "label": "SNMP (health, disks, network ports)", "found": True, "port": 161, "note": ""},
                             {"module": "nut", "label": "Battery backup (NUT)", "found": False, "port": 3493, "note": ""},
                             {"module": "portainer", "label": "Portainer", "found": True, "port": 9443, "note": "Container monitoring comes in a later version."}]}
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.route("**/api/thisbox", lambda r: r.fulfill(json=fake))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/setup"); pg.wait_for_selector("#bx-name")
            self.assertEqual(pg.input_value("#bx-name"), "pi-box")
            body = pg.inner_text("#boxout")
            for want in ("192.0.2.5", "192.0.2.1", "192.0.2.53", "192.0.2.54", "Portainer", "later version"):
                self.assertIn(want, body)
            self.assertEqual(pg.locator("#boxout input[type=checkbox]:checked").count(), 3)
            pg.uncheck(".nw-dns[value='192.0.2.54']")
            pg.click("#nw-go"); pg.wait_for_selector("#boxout .box:has-text('Your network'):has-text('done')")      # it folds out of the way once saved
            self.assertEqual(pg.locator("#nw-go").count(), 0)
            ids = [n["id"] for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]]
            self.assertEqual(ids, ["web", "pi-box", "gateway", "dns-192-0-2-53"])         # (this box gets its own system first)
            pg.click("#boxout .box:has-text('Your network') button:has-text('Edit')"); pg.uncheck(".nw-dns[value='192.0.2.54']"); pg.click("#nw-go"); pg.wait_for_selector("#boxout .box:has-text('Your network'):has-text('done')")
            self.assertEqual([n["id"] for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]], ids, "pressing it again adds nothing")
            # SNMP is found: Set up opens the Servers page with a draft server for this box and the SNMP form
            pg.fill("#bx-name", "Monitor"); pg.click("#boxout .devrow:has-text('SNMP') button")      # the SNMP form opens in place, on this page
            pg.wait_for_selector("#ied #devs >> text=Add: SNMP")
            self.assertIn("192.0.2.5", pg.inner_text("#ied"))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_settings_is_a_hub_of_sections_that_works_on_a_phone(self):
        c = self.start()
        self.configure(c, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.10", "version": "2c", "community": "fake-comm-hub"}],
                       [{"id": "nas", "name": "NAS", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings"); pg.wait_for_selector(".hub")
            titles = [x.strip() for x in pg.locator(".hub b").all_inner_texts()]
            self.assertEqual(titles, ["Display", "History", "Servers", "Power", "Graphs", "Alerts", "Sites", "Sign-in and security", "Backups", "Updates and versions", "This box", "Advanced"])
            hub = pg.inner_text(".hubg")
            for want in ("Summarized", "1 server"):
                self.assertIn(want, hub)
            self.assertFalse(pg.evaluate("document.documentElement.scrollWidth > innerWidth"), "the hub scrolls sideways on a phone")
            for name, marker in (("Display", '[aria-label="History length"]'), ("History", "#hp-list"), ("Servers", "#devs .devrow"), ("Advanced", "#cfg"),
                                 ("Backups", "text=Back up settings now"), ("Updates and versions", "text=Check for updates automatically"), ("This box", "text=Sign out")):
                pg.click(f".hub:has(b:text-is('{name}'))"); pg.wait_for_selector(f"h1:has-text('{name}')"); pg.wait_for_selector(marker)
                self.assertFalse(pg.evaluate("document.documentElement.scrollWidth > innerWidth"), f"{name} scrolls sideways on a phone")
                self.assertEqual(pg.inner_text("h1").strip(), name)
                pg.click("text=← Settings"); pg.wait_for_selector(".hub")
            # the two JSON editors share the Advanced page and each must save without touching the other
            pg.on("dialog", lambda d: (errs.append("dialog: " + d.message), d.dismiss()))
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/advanced"); pg.wait_for_selector("#cfg")
            pg.click("button[onclick='saveMon()']"); pg.wait_for_selector("#monmsg:has-text('Saved')")
            pg.click("button[onclick='saveConn()']"); pg.wait_for_selector("#cmsg:has-text('Saved')")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/nonsense"); pg.wait_for_selector(".hub")      # an unknown section is just the hub
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_services_directory_groups_by_server_folds_stacks_and_links_open_in_a_new_window(self):
        c = self.start()
        tcp = lambda: [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]
        node = lambda i, title, env, **sv: {"id": i, "name": f"{title} ({env})", "group": "Services", "checks": tcp(),
                                            "service": {"title": title, "env": env, "container": i, **sv}}
        self.configure(c, [], [
            node("plex", "Plex", "Anchor3", icon="plex", url="http://192.0.2.9:32400/"),
            node("scrob", "Scrob", "Anchor3", stack="scrob", icon="scrob", url="http://192.0.2.9:8080/"),
            node("scrob-db", "Scrob Db", "Anchor3", stack="scrob"),
            node("solo", "Solo", "Anchor3", stack="alone"),
            node("zqx", "Zqx", "Granite")])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs, asked = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("request", lambda r: asked.append(r.url) if "/icons/" in r.url else None)
            pg.route("**/icons/scrob.svg", lambda r: r.abort())                                    # one icon that cannot load: initials stand in
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            import urllib.request, urllib.error
            def code(path):
                try:
                    return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}").status
                except urllib.error.HTTPError as e:
                    return e.code
            self.assertEqual([code("/icons/home-assistant.svg"), code("/icons/nope.svg"), code("/icons/..%2fVERSION.svg"), code("/icons/plex.png")], [200, 404, 404, 404])
            pg.wait_for_selector(".card"); self.assertEqual(pg.locator("#svcbtn").count(), 0); pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .svcrow")
            heads = pg.evaluate("[...document.querySelectorAll('.svcenv')].map(e=>e.firstChild.textContent.trim())")
            self.assertEqual([h.lower() for h in heads], ["anchor3", "granite"])
            # the two-container stack is one row; a stack of one is an ordinary row
            self.assertEqual(pg.locator("[data-stack]").count(), 1)
            self.assertIn("2 services", pg.inner_text("[data-stack]"))
            self.assertEqual(pg.locator("[data-n=scrob]").count(), 0)
            pg.click("[data-stack]"); pg.wait_for_selector("[data-n=scrob]")
            self.assertEqual(pg.locator("[data-n=scrob-db]").count(), 1)
            pg.click("[data-stack]"); self.assertEqual(pg.locator("[data-n=scrob]").count(), 0)
            # links open in a new window and never hand the page to the app; no url, no link
            a = pg.locator("[data-n=plex] a.open")
            self.assertEqual((a.get_attribute("href"), a.get_attribute("target")), ("http://192.0.2.9:32400/", "_blank"))
            self.assertIn("noopener", a.get_attribute("rel"))
            self.assertEqual(pg.locator("[data-n=zqx] a").count(), 0)
            # icons are looked up by name; when one cannot load the initials stand in
            self.assertTrue(any(u.endswith("/icons/plex.svg") for u in asked), asked)
            self.assertFalse([u for u in asked if not u.startswith(f"http://127.0.0.1:{self.port}/")])      # nothing is fetched from anywhere else
            pg.click("[data-stack]"); pg.wait_for_selector("[data-n=scrob]")
            pg.wait_for_function("document.querySelector('[data-n=scrob] .ini').offsetParent!==null")      # an icon that fails shows initials
            pg.click("[data-stack]")
            pg.wait_for_function("document.querySelector('[data-n=plex] img').naturalWidth>0")          # the bundled plex icon really draws
            self.assertEqual(pg.inner_text("[data-n=zqx] .ico").strip(), "Z")
            # tapping a row opens that service's checks right there, in the same panel (it used to jump to a second, flat panel)
            pg.click("[data-n=plex] .grow"); pg.wait_for_selector("[data-n=plex] + .node.inl:has-text('Check now')")
            self.assertTrue(pg.locator(".svcrow").count())
            self.assertEqual(pg.inner_text("[data-stack] b").strip(), "Scrob")                      # a stack gets the same tidy-up as a container
            # "Remove all" on an environment heading stops watching everything listed under it
            pg.click(".svcenv:has-text('Granite') button"); pg.click("#ask-ok")
            pg.wait_for_function("!document.querySelector('[data-n=zqx]')")
            self.assertEqual(pg.evaluate("[...document.querySelectorAll('.svcenv')].map(e=>e.firstChild.textContent.trim().toLowerCase())"), ["anchor3"])
            self.assertNotIn("zqx", [n["id"] for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]])
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_icons_match_by_container_name_stacks_wear_one_a_redraw_does_not_blink_and_a_link_can_be_set(self):
        c = self.start()
        tcp = lambda: [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]
        node = lambda i, title, **sv: {"id": i, "name": f"{title} (Anchor3)", "group": "Services", "checks": tcp(),
                                       "service": {"title": title, "env": "Anchor3", "container": i, **sv}}
        self.configure(c, [], [
            node("plex", "Plex", icon="pms-docker"),                                   # the image says nothing, the container name does
            node("scrob", "Scrob", stack="scrob", icon="scrob"), node("scrob-db", "Scrob db", stack="scrob", icon="mariadb"),
            node("ombi-web", "Ombi web", stack="ombi_mysql", icon="ombi"), node("ombi-db", "Ombi db", stack="ombi_mysql", icon="mysql"),
            node("zqx", "Zqx")])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .svcrow")
            pg.wait_for_selector("[data-n=plex] img")
            self.assertIn("/icons/plex.svg", pg.get_attribute("[data-n=plex] img", "src"))
            self.assertEqual(pg.locator("[data-n=zqx] img").count(), 0)                   # nothing fits: initials
            for stack, icon in (("scrob", "scrob"), ("ombi_mysql", "ombi")):               # a stack row shows its app's icon, not just its members
                self.assertIn(f"/icons/{icon}.svg", pg.get_attribute(f"[data-stack$='|{stack}'] img", "src"))
            tidy = lambda s: pg.evaluate("s=>tidy(s)", s)
            self.assertEqual([tidy("running · healthy"), tidy("running (Up 4 days)"), tidy("Healthy"), tidy("running · unhealthy"), tidy("exited (Exited (1) 2 hours ago)"), tidy("port 1 refused the connection")],
                             ["", "Up 4 days", "", "unhealthy", "exited (Exited (1) 2 hours ago)", "port 1 refused the connection"])
            # a status update redraws the page; the panel and its icons stay the very same elements (no blink)
            pg.evaluate("window.__p=document.querySelector('.drawer');window.__i=document.querySelector('[data-n=plex] img')")
            pg.evaluate("lastTouch=0;render()")
            self.assertTrue(pg.evaluate("document.querySelector('.drawer')===window.__p && document.querySelector('[data-n=plex] img')===window.__i"))
            # no link was found for Plex: set one by hand, and it appears and survives a reload
            pg.click("[data-n=plex] .grow"); pg.click("[data-n=plex] + .node button:has-text('Set opened link')")
            pg.fill("#ask-in", "http://192.0.2.9:32400/web"); pg.click("#ask-ok")
            pg.wait_for_selector("[data-n=plex] a.open")
            self.assertEqual(pg.get_attribute("[data-n=plex] a.open", "href"), "http://192.0.2.9:32400/web")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_each_setting_lives_on_the_page_about_it_and_still_loads_there(self):
        c = self.start()
        self.configure(c, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.10", "version": "2c", "community": "fake-comm-mv"}],
                       [{"id": "nas", "name": "NAS", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            titles = {"display": "Display", "history": "History", "alerts": "Alerts", "graphs": "Graphs", "box": "This box"}
            def go(sec):
                pg.goto(f"http://127.0.0.1:{self.port}/#/settings/{sec}"); pg.wait_for_selector(f"h1:has-text('{titles[sec]}')")
            moved = {"Traffic graphs": "graphs", "Time zone": "box", "Colours in the history bars": "history", "Confirm a failure first": "alerts"}
            for sec in titles:
                go(sec)
                for heading, home in moved.items():
                    n = pg.locator(f"h3:text-is('{heading}')").count()
                    self.assertEqual(n, 1 if home == sec else 0, f"{heading} belongs on {home}, checked on {sec}")
            go("box"); pg.wait_for_selector("#tz-sel option", state="attached"); self.assertTrue(pg.input_value("#tz-sel"))
            go("history"); pg.wait_for_selector("#bs-row input"); pg.wait_for_function("[...document.querySelectorAll('#bs-row input')].some(i=>i.checked)")
            go("alerts"); pg.wait_for_function("document.querySelector('#cf-n') && document.querySelector('#cf-n').value !== ''")
            go("graphs"); pg.wait_for_selector("[aria-label='Panel graph window']")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_developer_tools_live_on_the_advanced_page_and_nowhere_else(self):
        c = self.start()
        self.configure(c, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.10", "version": "2c", "community": "fake-comm-adv"}],
                       [{"id": "nas", "name": "NAS", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            self.assertEqual(pg.locator("button:text-is('Network map')").count(), 0, "the dashboard has no Network map button")
            go = lambda sec: (pg.goto(f"http://127.0.0.1:{self.port}/#/settings/{sec}"), pg.wait_for_selector(f"h1:has-text('{ {'advanced': 'Advanced', 'box': 'This box', 'display': 'Display', 'servers': 'Servers'}[sec] }')"))
            go("advanced")
            txt = pg.inner_text("#m, body")
            for want in ("Open the network map", "Monitoring (JSON)", "Connections (JSON)", "Measure this site", "Ask the switches", "Ask the gateway", "Preview the screens"):
                self.assertIn(want, txt)
            heads = pg.locator("h3").all_inner_texts()        # the page: intro, dragons line, the tool sections, and the two raw editors last
            self.assertEqual(heads, ["Advanced", "Network map", "Performance", "Switch report", "Flows look", "Preview the screens", "Monitoring (JSON)", "Connections (JSON)"])
            self.assertLess(pg.locator("text=Here there be dragons.").bounding_box()["y"], pg.locator("h3:has-text('Network map')").bounding_box()["y"])
            self.assertEqual(pg.locator(".box:has(button:has-text('Open the network map')):has-text('Troubleshooting tools')").count(), 0, "the page intro is not in the network map's box")
            for sec, gone in (("box", ("Measure this site", "Ask the switches", "Ask the gateway")), ("display", ("Preview the screens",)), ("servers", ("Connections (JSON)", "edit all connection settings"))):
                go(sec); here = pg.inner_text("body")
                for g in gone:
                    self.assertNotIn(g, here, f"{g} moved to Advanced, so it is not on {sec}")
            go("box"); self.assertIn("Sign out", pg.inner_text("body")); self.assertIn("Factory reset", pg.inner_text("body"))
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/watched"); pg.wait_for_selector("#cfg")
            self.assertTrue(pg.url.endswith("#/settings/advanced"), "an old link to What is watched lands on Advanced")
            pg.click("text=Open the network map"); pg.wait_for_selector("text=← Advanced")
            pg.click("text=← Advanced"); pg.wait_for_selector("#cfg")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_one_change_address_button_moves_both_the_watched_page_and_the_link(self):
        c = self.start()
        self.configure(c, [], [{"id": "ph", "name": "Pihole (Anchor3)", "group": "Services", "checks": [{"id": "web", "type": "http", "url": "http://192.0.2.9:80/"}],
                                "service": {"title": "Pihole", "env": "Anchor3", "container": "pihole", "url": "http://192.0.2.9:80/"}}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("dialog", lambda d: errs.append("dialog: " + d.message))      # no browser pop-ups: the box is in the page
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .svcrow")
            pg.click("[data-n=ph] .grow")
            self.assertEqual(pg.locator("[data-n=ph] + .node button:has-text('Change opened link')").count(), 0)      # one button, not two
            pg.click("[data-n=ph] + .node button:has-text('Change address')")
            self.assertEqual(pg.input_value("#ask-in"), "http://192.0.2.9:80/")           # starts from the current address
            pg.fill("#ask-in", "http://192.0.2.9:80/admin/"); pg.press("#ask-in", "Enter")
            pg.wait_for_function("document.querySelector('[data-n=ph] a.open') && document.querySelector('[data-n=ph] a.open').href.endsWith('/admin/')", timeout=5000)
            n = c.get("/api/config/monitoring")["monitoring"]["nodes"][0]
            self.assertEqual((n["checks"][0]["url"], n["service"]["url"]), ("http://192.0.2.9:80/admin/",) * 2)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_web_page_can_be_added_to_a_server_and_its_admin_link_opens_from_the_detail(self):
        c = self.start()
        self.configure(c, [], [{"id": "nas", "name": "Nas", "group": "Servers", "rule": "primary",
                                "checks": [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a web page"); pg.wait_for_selector("#w-name")
            pg.fill("#w-name", "Nas admin"); pg.fill("#w-url", f"http://127.0.0.1:{self.port}/healthz"); pg.select_option("#w-sys", "nas")
            pg.click("summary:has-text('More options')"); pg.fill("#w-link", "https://nas.example.test/")
            pg.click("#devs button:text-is('Add')"); pg.wait_for_selector("#devmsg:has-text('Added')")
            pg.goto(f"http://127.0.0.1:{self.port}/#/"); pg.wait_for_selector(".card")
            pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .node")
            a = pg.locator(".drawer .node a:has-text('Open')")
            self.assertEqual((a.get_attribute("href"), a.get_attribute("target")), ("https://nas.example.test/", "_blank"))
            self.assertIn("noopener", a.get_attribute("rel"))
            pg.wait_for_selector(".drawer .checks li:has-text('Nas admin')")                  # the page is watched as one more check of the server
            # a bad address is refused in plain words and nothing is added
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.click("#devs >> text=Add a web page"); pg.fill("#w-name", "Bad"); pg.fill("#w-url", "ftp://x/"); pg.click("#devs button:text-is('Add')")
            pg.wait_for_selector("#devmsg:has-text('http')")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_banner_is_honest_busy_is_a_heads_up_degraded_is_yellow_and_a_real_down_is_red(self):
        c = self.start()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card")
            look = lambda: (pg.evaluate("document.body.dataset.s"), pg.inner_text("h1.head"), pg.inner_text("p.lede"))
            def demo(name):
                pg.evaluate(f"demo('{name}')"); pg.wait_for_function(f"document.body.dataset.s && document.querySelector('.card')")
                pg.wait_for_timeout(400)
            demo("headsup"); s, h, lede = look()
            self.assertEqual((s, h), ("green", "Everything is fine")); self.assertIn("Heads-up: Anchor3: CPU 95% busy", lede)
            pg.click("text=Detailed"); pg.wait_for_selector(".rw.note")                      # the busy server's line is amber, its light stays green
            self.assertIn("CPU 95%", pg.inner_text(".rw.note"))
            demo("yellow"); s, h, lede = look()
            self.assertEqual((s, h, lede), ("yellow", "Something's not right", "Plex is having trouble. Nothing is down."))
            demo("down"); s, h, lede = look()
            self.assertEqual((s, h), ("red", "Something's down")); self.assertIn("Nothing critical is affected", lede)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_services_card_and_the_services_button_open_one_panel_that_keeps_its_place(self):
        c = self.start()
        tcp = lambda: [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]
        node = lambda i, **sv: {"id": i, "name": f"S{i} (Anchor3)", "group": "Services", "checks": tcp(),
                                "service": {"title": f"Svc {i}", "env": "Anchor3", "container": f"c{i}", **sv}}
        self.configure(c, [], [node(f"s{k}") for k in range(30)] + [node("ombi-mysql", stack="ombi_mysql"), node("ombi-web", stack="ombi_mysql")])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 700})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); self.assertEqual(pg.locator("#svcbtn").count(), 0); pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .svcrow")
            from_button = pg.inner_text(".drawer h2")
            pg.click(".drawer button:has-text('Close')")
            pg.click("button.card, .card.det .hd"); pg.wait_for_selector(".drawer .svcrow")      # the card opens the same panel
            self.assertEqual(from_button, pg.inner_text(".drawer h2"))
            self.assertIn("Ombi mysql", pg.inner_text(".drawer"))
            self.assertIn("Check everything now", pg.inner_text(".drawer"))
            # a redraw of the page (every status update does one) leaves the panel where the finger left it
            pg.evaluate("document.querySelector('.drawer').scrollTop=400")
            before = pg.evaluate("document.querySelector('.drawer').scrollTop")
            self.assertGreater(before, 100)
            pg.evaluate("lastTouch=0;render()")
            self.assertAlmostEqual(pg.evaluate("document.querySelector('.drawer').scrollTop"), before, delta=2)
            self.assertEqual(errs, [])
            b.close()

    def test_brand_assets_are_public_and_the_manifest_points_at_real_icons(self):
        import urllib.request
        c = self.start()
        get = lambda path: urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}")          # no sign-in: a browser asks before anyone is logged in
        for path, ctype in (("/favicon.svg", "image/svg+xml"), ("/favicon.ico", "image/png"), ("/apple-touch-icon.png", "image/png"),
                            ("/brand/icon-192.png", "image/png"), ("/brand/icon-512.png", "image/png"), ("/manifest.webmanifest", "application/manifest+json")):
            r = get(path)
            self.assertEqual((r.status, r.headers["Content-Type"]), (200, ctype), path)
        m = json.loads(get("/manifest.webmanifest").read())
        self.assertEqual((m["name"], m["display"], m["start_url"]), ("MonitorBox", "standalone", "/"))
        for ic in m["icons"]:
            self.assertEqual(get(ic["src"]).status, 200, ic["src"])
        png = get("/brand/icon-512.png").read()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        page = get("/").read().decode()
        for needle in ('rel=icon href=/favicon.svg', 'rel=apple-touch-icon', 'rel=manifest href=/manifest.webmanifest'):
            self.assertIn(needle, page)

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_saving_a_portainer_connection_offers_to_drop_what_was_watched_under_an_environment_that_is_gone(self):
        import portainer_fake as PF
        p = PF.Portainer(envs=[PF.environment(1, "Aurora")], containers={1: [PF.container("watchtower")]})
        self.addCleanup(p.close)
        c = self.start()
        mod = lambda i, name, env, **x: {"id": i, "name": name, "group": "Services", "service": {"title": name, "env": env, "container": i},
                                         "checks": [{"id": "c", "type": "module", "module": "portainer", "connection": "pt", "check": "container", "params": {"env": env, "name": i}}]}
        envnode = {"id": "old-env", "name": "Old environment", "group": "Services", "checks": [{"id": "e", "type": "module", "module": "portainer", "connection": "pt", "check": "environment", "params": {"name": "local"}}]}
        self.configure(c, [{"id": "pt", "module": "portainer", "name": "Aurora", "base_url": p.url, "token": PF.TOKEN, "timeout": 2}],
                       [envnode, mod("hb-local", "Homebridge", "local"), mod("wt-aurora", "Watchtower", "Aurora")])
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs, asked = [], []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.evaluate("(()=>{const x=servers().find(s=>s.conns.some(c=>c.id==='pt'));sv.page='server';sv.key=x.key;svcForm('portainer','pt');svcSave();return 1})()")
            pg.wait_for_selector("#ask"); asked.append(pg.inner_text("#ask")); pg.click("#ask-ok")      # the question is in the page, not a browser pop-up
            pg.wait_for_function("!(sv.mon.nodes||[]).some(n=>n.id==='hb-local')")
            ids = {n["id"] for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]}
            self.assertEqual(ids, {"wt-aurora"})                                  # what was under 'local' went when the connection was saved
            self.assertEqual(len(asked), 1)
            self.assertIn("'local'", asked[0]); self.assertIn("Aurora", asked[0])
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_pick_lists_environments_first_collapsed_and_ticks_their_services_together(self):
        import portainer_fake as PF
        web = PF.Site(200); self.addCleanup(web.close)
        p = PF.Portainer(envs=[PF.environment(1, "Granite"), PF.environment(2, "Anchor3")],
                         containers={1: [PF.container("watchtower")],
                                     2: [PF.container("plex", ports=[web.port]), PF.container("scrob", stack="scrob"), PF.container("old", state="exited", status="Exited (0) 1 day ago")]})
        self.addCleanup(p.close)
        c = self.start()
        self.configure(c, [{"id": "granite-portainer", "module": "portainer", "name": "Granite", "base_url": p.url, "token": PF.TOKEN, "timeout": 2}],
                       [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.wait_for_selector("#devs button")
            pg.evaluate("pickFor('granite-portainer')"); pg.wait_for_selector(".envrow")
            self.assertEqual([e.get_attribute("data-env") for e in pg.locator(".envrow").all()], ["Anchor3", "Granite"])
            self.assertIn("Environments 2 of 2", " ".join(pg.inner_text("#detout").split()))
            # every environment starts ticked and collapsed: no container rows are on screen
            self.assertEqual(pg.locator(".envrow input:checked").count(), 2)
            self.assertEqual(pg.locator("#detout label:has-text('Container')").count(), 0)
            self.assertIn("2 of 3 services", " ".join(pg.inner_text("[data-env=Anchor3]").split()))      # the stopped one is not ticked
            # open one: its services are nested under it, grouped as before
            pg.click("[data-env=Anchor3] button[aria-expanded]")
            pg.wait_for_selector("[data-env=Anchor3] label:has-text('Container plex')")
            self.assertEqual(pg.locator("[data-env=Granite] label").count(), 0)
            self.assertFalse(pg.locator("[data-env=Anchor3] label:has-text('Container old') input").is_checked())
            before = pg.inner_text("#pickapply")
            # unticking the environment unticks everything inside it
            pg.locator("[data-env=Anchor3] > .row > input").uncheck()
            self.assertEqual(pg.locator("[data-env=Anchor3] label input:checked").count(), 0)
            self.assertIn("Environments 1 of 2", " ".join(pg.inner_text("#detout").split()))
            self.assertNotEqual(pg.inner_text("#pickapply"), before)
            # ticking it again brings back the running ones (not the stopped one)
            pg.locator("[data-env=Anchor3] > .row > input").check()
            self.assertTrue(pg.locator("[data-env=Anchor3] label:has-text('Container plex') input").is_checked())
            self.assertFalse(pg.locator("[data-env=Anchor3] label:has-text('Container old') input").is_checked())
            # Apply adds only what is ticked: both environments, plex, scrob and watchtower
            pg.click("#pickapply"); pg.wait_for_selector("#pickmsg:has-text('Saved')")
            ids = {n["id"] for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]}
            self.assertEqual(ids, {"pi", "anchor3-portainer", "granite-portainer", "plex-anchor3", "scrob-anchor3", "watchtower-granite"})
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_updates_page_puts_update_settings_first_and_one_card_per_piece_of_software(self):
        c = self.start()
        mods = [m["id"] for m in c.get("/api/state")["modules"]]
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            heads = pg.locator("h3").all_inner_texts()
            self.assertEqual(heads, ["Updates", "Repositories", "Installed software"])   # the old separate Modules and Versions lists are one (and the Repositories box, #265, sits between)
            self.assertLess(pg.locator("h3:has-text('Updates')").bounding_box()["y"], pg.locator("[data-sw=app]").bounding_box()["y"])
            self.assertLess(pg.locator("#ch").bounding_box()["y"], pg.locator("[data-sw=app]").bounding_box()["y"])
            cards = [x.get_attribute("data-sw") for x in pg.locator("[data-sw]").all()]
            self.assertEqual(cards[0], "app")
            self.assertEqual(sorted(cards[1:]), sorted(mods))              # one card per installed module, none twice
            for m in mods:                                                # each has its description and its version picker together
                card = pg.locator(f"[data-sw={m}]")
                self.assertEqual(card.locator("select").count(), 1, m)
                self.assertIn("running", card.inner_text(), m)
            self.assertIn("Hello from module version", pg.inner_text("[data-sw=hello]"))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_update_all_shows_whenever_an_update_is_waiting_even_just_one(self):
        c = self.start()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            self.assertEqual(pg.locator("#upall").count(), 0, "nothing is waiting, so no button")
            self.publish(hello="0.3.1"); c.post("/api/check")                                    # one module update, nothing else
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("#upall")
            self.assertEqual(pg.inner_text("#upall"), "Update all (1)", "a single update gets the button too")
            self.publish(app="0.13.0", hello="0.3.1"); c.post("/api/check")                      # an App update and a module update
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("#upall")
            self.assertEqual(pg.inner_text("#upall"), "Update all (2)")
            self.assertTrue(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_detailed_services_card_folds_each_environment_and_opens_one_with_a_problem(self):
        c = self.start()
        up = lambda: [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": self.port}]
        down = lambda: [{"id": "tcp", "type": "tcp", "target": "127.0.0.1", "port": 1, "timeout": 1}]
        env = lambda i, name, chk: {"id": i, "name": f"{name} Portainer", "group": "Services", "checks": chk}
        svc = lambda i, title, e, chk, **sv: {"id": i, "name": f"{title} ({e})", "group": "Services", "checks": chk, "dependsOn": [("a-env" if e == "Bay Harbor - Anchor3" else "g-env")],
                                               "service": {"title": title, "env": e, "container": i, **sv}}
        A, G = "Bay Harbor - Anchor3", "Bay Harbor - Granite"
        self.configure(c, [], [env("a-env", A, up()), env("g-env", G, up()),
                               svc("plex", "Plex", A, up()), svc("ombi", "Ombi", A, up(), stack="ombi"), svc("ombi-db", "Ombi mariadb", A, up(), stack="ombi"),
                               svc("bazarr", "Bazarr", G, up()), svc("lidarr", "Lidarr", G, down())])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.click("button:has-text('Detailed')")
            pg.wait_for_selector(".card.det")
            # wait until Granite's failing service has been seen
            pg.wait_for_function("Object.values(snap.nodes).some(n=>n.id==='lidarr'&&n.state==='failed')", timeout=30000)
            card = pg.locator(".card.det", has_text="Services")
            txt = lambda: " ".join(card.inner_text().split())
            # one row per environment; the healthy one stays folded, the one with a problem opens by itself
            self.assertIn("Bay Harbor - Anchor3 3 services · all good", txt())
            self.assertIn("Bay Harbor - Granite 1 of 2 good · 1 need a look", txt())
            self.assertNotIn("Plex", txt())                                  # folded: no service rows from the healthy environment
            self.assertIn("Lidarr", txt()); self.assertIn("Bazarr", txt())
            self.assertNotIn("Lidarr (Bay Harbor", txt())                    # short names: the environment is already the heading
            # open the healthy one: services by title, a two-container stack folded once more
            card.locator("button[aria-expanded]", has_text="Bay Harbor - Anchor3").click()
            pg.wait_for_selector("text=Portainer environment")
            self.assertIn("Plex", txt()); self.assertIn("Ombi 2 services · all good", txt())
            self.assertNotIn("Ombi mariadb", txt())
            card.locator("button[aria-expanded]", has_text="2 services").click()
            pg.wait_for_selector("text=Ombi mariadb")
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
