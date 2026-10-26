"""Cameras, end to end through the real launcher and App with a fake UniFi Protect console: the camera list and pictures come from the
connected camera sources only, one source being wrong does not hide the others, and the Cameras card shows a picture per camera."""
import base64, json, os, secrets, shutil, sys, time, unittest, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402
from protect_fake import Console  # noqa: E402
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")     # a 1 by 1 picture


class CamerasE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def setup_cameras(self):
        con = Console(); self.addCleanup(con.close)
        con.snapshot_type, con.snapshot_body = "image/png", PNG
        c = self.start()
        good = {"id": "nvr", "module": "unifi-protect", "base_url": con.url, "username": con.username, "password": con.password, "timeout": 2}
        wrong = {"id": "old-nvr", "module": "unifi-protect", "base_url": con.url, "username": con.username, "password": "fake-wrong-pw-5", "timeout": 2}
        other = {"id": "snmp-box", "module": "snmp", "host": "127.0.0.1", "version": "2c", "community": "fake-comm-cam"}
        node = {"id": "cameras", "name": "Cameras", "group": "Cameras", "rule": "any",
                "checks": [{"id": "all", "type": "module", "module": "unifi-protect", "connection": "nvr", "check": "cameras", "params": {}}]}
        self.configure(c, [good, wrong, other], [node])
        return c, con

    def test_the_list_and_the_pictures_come_only_from_camera_sources(self):
        c, con = self.setup_cameras()
        out = c.get("/api/cameras")
        self.assertEqual([(x["name"], x["connection"], x["source"]) for x in out["cameras"]],
                         [("Backyard", "nvr", "unifi-protect"), ("Driveway", "nvr", "unifi-protect"), ("Front Door", "nvr", "unifi-protect")])
        self.assertEqual([e["connection"] for e in out["errors"]], ["old-nvr"], "a source with a wrong password is named, and the others still show")
        self.assertNotIn("fake-wrong-pw-5", str(out))
        def raw(path):
            with c.op.open(c.base + path, timeout=10) as r:
                return r.headers["Content-Type"], r.read()
        self.assertEqual(raw("/api/camera-snapshot?conn=nvr&id=cam0001abc"), ("image/png", PNG))
        for bad in ("conn=snmp-box&id=cam0001abc", "conn=nope&id=cam0001abc", "conn=nvr&id=..%2F..%2Fetc", "conn=nvr&id=", "conn=nvr"):
            with self.assertRaises(urllib.error.HTTPError, msg=bad) as e:
                raw("/api/camera-snapshot?" + bad)
            self.assertEqual(e.exception.code, 404, bad)
        self.assertEqual({r[0] for r in con.requests}, {"GET", "POST"})       # reads and one login only

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_every_camera_keeps_getting_new_pictures_without_open_streams_and_the_panel_widens(self):
        """More cameras than a browser's six connections to one site: each still gets a picture, again and again, because pictures are asked for
        a few at a time and no connection is kept open (one open stream per camera once left most cameras blank)."""
        from protect_fake import cam as fake_cam
        c, con = self.setup_cameras()
        con.cameras += [fake_cam(f"cam{i:04d}xyz", f"Extra {i}") for i in range(4, 11)]                 # ten cameras in all
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.evaluate("window.__maxBusy=0; setInterval(()=>{window.__maxBusy=Math.max(window.__maxBusy,camBusy)},10)")
            pg.click(".card:has-text('Cameras')"); pg.wait_for_selector(".camgrid .cam img")
            self.assertEqual(pg.locator(".cam").count(), 10)
            pg.wait_for_function("[...document.querySelectorAll('.cam img')].length===10 && [...document.querySelectorAll('.cam img')].every(i=>i.naturalWidth===1)")
            n0 = len([x for x in con.requests if "snapshot" in x[1]])
            pg.wait_for_timeout(4000)
            n1 = len([x for x in con.requests if "snapshot" in x[1]])
            self.assertGreater(n1 - n0, 10, "pictures keep refreshing")
            self.assertLessEqual(pg.evaluate("window.__maxBusy"), 3, "at most a few pictures are asked for at a time")
            self.assertTrue(pg.evaluate("[...document.querySelectorAll('.cam img')].every(i=>i.naturalWidth===1)"))
            self.assertNotIn("camera-stream", pg.content())
            # a refresh of the panel leaves the pictures alone
            pg.evaluate("document.querySelector('.cam img').__same = 1; snap.cards[drawer.i].line = 'changed'; drawDrawer()")
            self.assertEqual(pg.evaluate("document.querySelector('.cam img').__same"), 1)
            pg.click(".cam >> nth=1"); self.assertTrue(pg.evaluate("document.querySelectorAll('.cam')[1].classList.contains('big')"))
            pg.click(".cam >> nth=1")
            # widening: the button makes the panel as wide as the screen, dragging the edge sets any width, the pictures grow
            w0 = pg.evaluate("document.querySelector('.drawer').getBoundingClientRect().width")
            cw0 = pg.evaluate("document.querySelector('.cam').getBoundingClientRect().width")
            self.assertLess(w0, 600)
            pg.click("text=Wider")
            pg.wait_for_function("document.querySelector('.drawer').getBoundingClientRect().width > 1100")
            cw1 = pg.evaluate("document.querySelector('.cam').getBoundingClientRect().width")
            self.assertGreater(cw1, cw0 * 1.4, (cw0, cw1))
            g = pg.locator(".dgrip").bounding_box()
            pg.mouse.move(g["x"] + 5, 300); pg.mouse.down(); pg.mouse.move(700, 300, steps=5); pg.mouse.up()
            w2 = pg.evaluate("document.querySelector('.drawer').getBoundingClientRect().width")
            self.assertTrue(480 <= w2 <= 520, w2)
            self.assertEqual(pg.evaluate("localStorage.getItem('mb-dw')"), str(round(w2)))
            pg.set_viewport_size({"width": 390, "height": 844})                          # a phone: the saved width never overflows the screen
            self.assertTrue(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
            self.assertTrue(pg.evaluate("document.querySelector('.drawer').getBoundingClientRect().width <= 390"))
            self.assertEqual(errs, [])
            b.close()

    def fake_scrypted(self, interfaces=("Camera", "VideoCamera")):
        """Put the fake Scrypted client where the module finds the real one (modules run with a bare environment). Returns (world file, call log)."""
        import json, tempfile
        d = tempfile.mkdtemp(prefix="mb-cam-scr-"); self.addCleanup(shutil.rmtree, d, True)
        world, log = os.path.join(d, "world.json"), os.path.join(d, "calls.log")
        dev = lambda i, n, t="Camera": {"id": i, "name": n, "type": t, "interfaces": list(interfaces), "online": True, "bytes": "JPEG-" + n}
        with open(world, "w") as f:
            json.dump({"username": "viewer-fake", "password": "pw-fake-6203", "devices": [dev("1", "Driveway"), dev("2", "Doorbell", "Doorbell"), dev("3", "Doorbell Package Camera")]}, f)
        pkg = os.path.join(self.src, "modules", "scrypted", "node_modules", "@scrypted", "client")
        os.makedirs(pkg)
        fake = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_scrypted_client.mjs")
        with open(os.path.join(pkg, "package.json"), "w") as f:
            json.dump({"name": "@scrypted/client", "version": "0.0.0-test", "type": "module", "main": "index.js"}, f)
        with open(os.path.join(pkg, "index.js"), "w") as f:
            f.write(f"process.env.MB_FAKE_SCRYPTED = {json.dumps(world)};\nprocess.env.MB_FAKE_SCRYPTED_LOG = {json.dumps(log)};\nexport * from {json.dumps('file://' + fake)};\n")
        open(log, "w").close()
        return world, log

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_live_video_setup_messages_pass_between_the_page_and_scrypted(self):
        import json, threading, time, urllib.request
        world, log = self.fake_scrypted(("Camera", "VideoCamera", "RTCSignalingChannel"))
        con = Console(); self.addCleanup(con.close)
        c = self.start()
        protect = {"id": "nvr", "module": "unifi-protect", "base_url": con.url, "username": con.username, "password": con.password, "timeout": 2}
        scr = {"id": "scr", "module": "scrypted", "host": "192.0.2.50", "username": "viewer-fake", "password": "pw-fake-6203", "timeout": 3}
        self.configure(c, [scr, protect], [])
        cams = {x["name"]: x for x in c.get("/api/cameras")["cameras"]}
        self.assertEqual(cams["Driveway"]["liveVia"], {"connection": "scr", "id": "1"})              # a Protect camera goes live through Scrypted
        self.assertTrue(cams["Doorbell"]["live"] and cams["Doorbell"]["liveVia"] == {"connection": "scr", "id": "2"})
        self.assertNotIn("liveVia", cams["Backyard"])
        def post(path, body):
            try:
                return c.post(path, body)
            except urllib.error.HTTPError as e:
                return json.loads(e.read())
        cid = "page-" + secrets.token_hex(6)
        self.assertIn("not open", str(post("/api/live/open", {"client": cid, "connection": "scr", "id": "1", "options": {}})))   # no channel yet
        events, got = [], threading.Condition()
        resp = c.op.open(urllib.request.Request(c.base + "/api/live/events?client=" + cid), timeout=20)
        self.addCleanup(resp.close)
        def pump():
            try:
                for raw in resp:
                    if raw.startswith(b"data: "):
                        with got:
                            events.append(json.loads(raw[6:])); got.notify_all()
            except Exception:
                pass
        threading.Thread(target=pump, daemon=True).start()
        def wait(kind, sid):
            with got:
                self.assertTrue(got.wait_for(lambda: any(e["session"] == sid and e["message"]["type"] == kind for e in events), timeout=15), (kind, events))
                return next(e["message"] for e in events if e["session"] == sid and e["message"]["type"] == kind)
        for bad in ({"connection": "nvr", "id": "cam0001abc"}, {"connection": "nope", "id": "1"}):
            self.assertIn("Scrypted only", str(post("/api/live/open", {"client": cid, "options": {}, **bad})))   # live video is for Scrypted connections only
        sid = post("/api/live/open", {"client": cid, "connection": "scr", "id": "1", "options": {"userAgent": "fake-browser"}})["session"]
        call = wait("call", sid)
        self.assertEqual((call["method"], call["args"][0]), ("createLocalDescription", "offer"))
        post("/api/live/input", {"session": sid, "message": {"type": "result", "callId": call["callId"], "value": {"type": "offer", "sdp": "v=0 fake offer"}}})
        wait("ready", sid)
        self.assertEqual(post("/api/live/input", {"session": "no-such-session-xyz", "message": {"type": "result"}}), {"ok": True})
        # the page goes away: its live views end on their own
        resp.close()
        deadline = time.time() + 10
        while time.time() < deadline and "endSession 1" not in open(log).read():
            time.sleep(0.2)
        self.assertIn("endSession 1", open(log).read())
        self.assertNotIn("FORBIDDEN", open(log).read())

    @unittest.skipIf(shutil.which("node") is None or sync_playwright is None, "node or playwright not installed")
    def test_live_video_in_the_panel_start_stop_limit_and_fallback_to_pictures(self):
        world, log = self.fake_scrypted(("Camera", "VideoCamera", "RTCSignalingChannel"))
        con = Console(); self.addCleanup(con.close)
        c = self.start()
        protect = {"id": "nvr", "module": "unifi-protect", "base_url": con.url, "username": con.username, "password": con.password, "timeout": 2}
        scr = {"id": "scr", "module": "scrypted", "host": "192.0.2.50", "username": "viewer-fake", "password": "pw-fake-6203", "timeout": 3}
        node = {"id": "cameras", "name": "Cameras", "group": "Cameras", "rule": "any",
                "checks": [{"id": "all", "type": "module", "module": "unifi-protect", "connection": "nvr", "check": "cameras", "params": {}}]}
        self.configure(c, [scr, protect], [node])
        calls = lambda: open(log).read().split("\n")
        def wait_log(what, n=1):
            deadline = time.time() + 15
            while time.time() < deadline and sum(1 for x in calls() if x.startswith(what)) < n:
                time.sleep(0.2)
            self.assertGreaterEqual(sum(1 for x in calls() if x.startswith(what)), n, (what, calls()))
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card:has-text('Cameras')"); pg.wait_for_selector(".camgrid .cam img")
            names = pg.evaluate("[...document.querySelectorAll('.cam figcaption b')].map(b=>b.textContent)")
            self.assertEqual(names, ["Backyard", "Doorbell", "Doorbell Package Camera", "Driveway", "Front Door"])
            # Snapshots (default): nothing live, a Go live button only where Scrypted can stream (not the two Protect-only cameras)
            self.assertEqual(pg.locator(".cam video").count(), 0)
            self.assertEqual(pg.locator(".cam .gl").count(), 3)
            self.assertFalse([x for x in calls() if x.startswith("startRTC")])
            # one camera goes live: a real WebRTC offer from this browser reaches Scrypted
            pg.click(".cam:has-text('Driveway') .gl")
            wait_log("startRTC 1"); wait_log("offer offer")
            self.assertGreater(int(next(x for x in calls() if x.startswith("offer offer")).split()[2]), 300, "a real session description")
            pg.wait_for_selector(".cam:has-text('Driveway') video")        # (waits: under load the page draws the video a moment after Scrypted sees the offer)
            self.assertEqual(pg.locator(".cam:has-text('Driveway') video").count(), 1)
            self.assertIn("Stop live", pg.inner_text(".cam:has-text('Driveway') .gl"))
            self.assertFalse(pg.locator(".cam.big").count(), "the button does not enlarge")
            pg.click(".cam:has-text('Driveway') .gl")                                           # stop: Scrypted is told to end the session
            wait_log("endSession 1"); pg.wait_for_function("document.querySelectorAll('.cam video').length===0")
            # Live for the whole panel: the three Scrypted cameras go live, the two Protect-only ones stay pictures
            pg.click(".camctl .seg button >> nth=1")
            wait_log("startRTC", 4)
            self.assertEqual(pg.locator(".cam video").count(), 3)
            self.assertEqual(pg.locator(".cam:has-text('Backyard') video").count(), 0)
            self.assertEqual(pg.evaluate("localStorage.getItem('mb-cammode')"), "live")
            pg.click(".cam >> nth=1"); self.assertTrue(pg.evaluate("document.querySelectorAll('.cam')[1].classList.contains('big')")); pg.click(".cam >> nth=1")
            # a camera that cannot start live video says why and keeps showing pictures
            with open(world) as f: w = json.load(f)
            w["rtcFails"] = True
            with open(world, "w") as f: json.dump(w, f)
            pg.click(".camctl .seg button >> nth=0"); pg.wait_for_function("document.querySelectorAll('.cam video').length===0")
            pg.click(".camctl .seg button >> nth=1")
            pg.wait_for_function("document.querySelectorAll('.cam .sub').length>0 && document.body.innerText.includes('Live video unavailable')", timeout=20000)
            self.assertIn("Permission denied", pg.inner_text(".camgrid"))
            self.assertGreater(pg.locator(".cam img").count(), 0)
            # picture quality: Light asks Scrypted for a small stream, Sharp for the whole screen's size, Balanced for a tile's; the choice is kept
            for q, want in (("Light", 640), ("Sharp", pg.evaluate("screen.width"))):
                pg.click(f".camctl .seg button:has-text('{q}')")
                self.assertEqual(pg.evaluate("cameraOptions().screen.width"), want)
            self.assertEqual(pg.evaluate("localStorage.getItem('mb-camq')"), "sharp")
            pg.click(".camctl .seg button:has-text('Balanced')")
            self.assertEqual(pg.evaluate("cameraOptions().screen.width"), pg.evaluate("document.querySelector('.cam .ph').clientWidth"))
            # Live details are shown in the panel; an alert would freeze the page and the videos with it
            popups = []; pg.on("dialog", lambda d: (popups.append(d.message), d.accept()))
            pg.click(".camctl button:has-text('Live details')"); pg.wait_for_selector("pre:has-text('live views')")
            self.assertEqual(popups, [])
            pg.click("button:has-text('Hide')"); pg.wait_for_function("!document.querySelector('pre.sub')")
            # closing the panel ends every live view
            pg.click("text=Snapshots"); pg.click("text=Close")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_refresh_of_the_main_page_never_takes_the_side_panel_out_of_the_page(self):
        """Every refresh of the main page used to pull the side panel out of the page and put it back, which stops a playing video and closes an
        open menu (the 'Live at once' list vanished and the cameras 'refreshed' every few seconds). The panel now lives outside the rebuilt page."""
        c, con = self.setup_cameras()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card:has-text('Cameras')"); pg.wait_for_selector(".camgrid .cam img")
            pg.evaluate("document.querySelector('.drawer').__same = 1; document.querySelector('#dr').__same = 1; window.__moves = 0;"
                        "new MutationObserver(l=>{for(const m of l)for(const n of [...m.addedNodes,...m.removedNodes])if(n.id==='dr'||(n.classList&&n.classList.contains('drawer')))window.__moves++})"
                        ".observe(document.body,{childList:true,subtree:true})")
            for _ in range(5):                                              # five full refreshes of the main page, as a status change makes
                pg.evaluate("render()"); pg.wait_for_timeout(100)
            self.assertEqual(pg.evaluate("window.__moves"), 0, "the side panel was taken out of the page")
            self.assertEqual(pg.evaluate("[document.querySelector('.drawer').__same, document.querySelector('#dr').__same]"), [1, 1])
            pg.click("text=Wider"); pg.click("text=Narrower")
            pg.click("text=Close"); self.assertEqual(pg.locator(".drawer").count(), 0)
            # a page that is not the main screen (Settings) is not left under an open panel
            pg.click(".card:has-text('Cameras')"); pg.wait_for_selector(".drawer")
            pg.evaluate("location.hash='#/settings'"); pg.wait_for_selector("text=Settings")
            self.assertEqual(pg.locator(".drawer").count(), 0)
            self.assertEqual(errs, [])
            b.close()

    def test_a_unifi_login_offers_protect_and_one_tap_adds_it_with_the_same_login_and_its_cameras(self):
        con = Console(); self.addCleanup(con.close)
        con.snapshot_type, con.snapshot_body = "image/png", PNG
        c = self.start()
        gw = {"id": "gw", "module": "unifi-network", "base_url": con.url, "username": con.username, "password": con.password, "verify_tls": False}
        self.configure(c, [gw], [{"id": "net", "name": "Network", "group": "Network", "rule": "any", "checks": [{"id": "up", "type": "ping", "target": "127.0.0.1"}]}])
        offered = [x for x in c.get("/api/followups")["suggestions"] if x["kind"] == "unifi-protect"]
        self.assertEqual([(x["how"], x["from"]) for x in offered], [("add", "gw")])
        self.assertNotIn(con.password, json.dumps(offered), "the login is never sent to the browser")
        c.post("/api/followups/dismiss", {"id": offered[0]["id"]})                       # an earlier "Not now" must not block pressing Add on the Set up page
        self.assertEqual([x for x in c.get("/api/followups")["suggestions"] if x["kind"] == "unifi-protect"], [])
        out = c.post("/api/followups/add", {"id": offered[0]["id"]})
        self.assertIn("watching", out["message"], out)
        conns = c.get("/api/config/connections")["connections"]
        protect = [x for x in conns if x["module"] == "unifi-protect"]
        self.assertEqual(len(protect), 1)
        self.assertEqual((protect[0]["base_url"], protect[0]["username"], protect[0]["password"]), (con.url, con.username, "••••••••"))
        self.assertNotEqual(protect[0]["id"], "gw")
        self.assertEqual(len(conns), 2, "the original connection is untouched")
        self.assertEqual([x["name"] for x in c.get("/api/cameras")["cameras"]], ["Backyard", "Driveway", "Front Door"])
        self.assertEqual([x for x in c.get("/api/followups")["suggestions"] if x["kind"] == "unifi-protect"], [], "not offered twice")
        self.assertEqual(c.post("/api/followups/add", {"id": offered[0]["id"]})["_status"], 400)

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_servers_page_shows_found_more_and_the_add_button_works(self):
        con = Console(); self.addCleanup(con.close)
        c = self.start()
        gw = {"id": "gw", "module": "unifi-network", "base_url": con.url, "username": con.username, "password": con.password, "verify_tls": False}
        self.configure(c, [gw], [{"id": "net", "name": "Network", "group": "Network", "rule": "any", "checks": [{"id": "up", "type": "ping", "target": "127.0.0.1"}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/servers")
            pg.wait_for_selector("text=Found more you can add"); pg.wait_for_selector("text=UniFi Protect on 127.0.0.1")
            self.assertEqual(pg.locator("#fu .devrow").count(), 1)
            pg.click("#fu button:has-text('Add')")
            pg.wait_for_selector("text=started watching")
            self.assertEqual(pg.locator("#fu .devrow").count(), 0, "gone once added")
            self.assertEqual(sum(1 for x in c.get("/api/config/connections")["connections"] if x["module"] == "unifi-protect"), 1)
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_scrypted_joins_protect_and_a_camera_both_report_shows_once(self):
        self.fake_scrypted()
        con = Console(); self.addCleanup(con.close)
        c = self.start()
        protect = {"id": "nvr", "module": "unifi-protect", "base_url": con.url, "username": con.username, "password": con.password, "timeout": 2}
        scr = {"id": "scr", "module": "scrypted", "host": "192.0.2.50", "username": "viewer-fake", "password": "pw-fake-6203", "timeout": 3}
        self.configure(c, [scr, protect], [])                 # the order they were added in does not matter
        out = c.get("/api/cameras")
        self.assertEqual(out["errors"], [])
        self.assertEqual([x["name"] for x in out["cameras"]], ["Backyard", "Doorbell", "Doorbell Package Camera", "Driveway", "Front Door"])
        by = {x["name"]: x for x in out["cameras"]}
        self.assertEqual((by["Driveway"]["connection"], by["Driveway"].get("alsoIn")), ("nvr", ["scrypted"]))       # one tile, from the preferred source
        self.assertEqual((by["Doorbell"]["connection"], by["Doorbell"]["source"]), ("scr", "scrypted"))
        with c.op.open(c.base + "/api/camera-snapshot?conn=scr&id=2", timeout=10) as r:
            self.assertEqual((r.headers["Content-Type"], r.read()), ("image/jpeg", b"JPEG-Doorbell"))
        t = c.post("/api/connections/test", {"connection": scr})
        self.assertEqual((t["ok"], {f["label"]: f["count"] for f in t["found"]}), (True, {"Overview": 1, "Cameras": 3}), t)
        t = c.post("/api/connections/test", {"connection": {**scr, "password": "fake-wrong-" + secrets.token_hex(4)}})
        self.assertFalse(t["ok"]); self.assertIn("user name or password", t["error"])

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_cameras_card_shows_a_picture_per_camera_and_says_which_is_offline(self):
        c, con = self.setup_cameras()
        con.cameras[1].update(state="DISCONNECTED", isConnected=False, isRecording=False)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card")
            pg.click(".card:has-text('Cameras')"); pg.wait_for_selector(".camgrid .cam")
            self.assertEqual(pg.locator(".cam").count(), 3)
            pg.wait_for_function("document.querySelectorAll('.cam img').length===2 && [...document.querySelectorAll('.cam img')].every(i=>i.naturalWidth===1)")
            txt = pg.inner_text(".camgrid")
            self.assertIn("Front Door", txt); self.assertIn("Offline", txt); self.assertIn("offline, last seen", txt)
            self.assertEqual(pg.locator(".cam.off img").count(), 0, "an offline camera is not asked for a picture")
            pg.click(".cam >> nth=0"); self.assertTrue(pg.evaluate("document.querySelector('.cam').classList.contains('big')"))
            pg.evaluate("loadCams()"); pg.wait_for_function("camT>0")                                    # the panel refreshes itself: a big picture stays big
            pg.evaluate("drawDrawer()")
            self.assertTrue(pg.evaluate("document.querySelector('.cam').classList.contains('big')"), "an enlarged camera shrank on refresh")
            pg.evaluate("document.querySelector('.cam img').__same = 1")                              # a changed number must not rebuild the pictures
            pg.evaluate("snap.cards[drawer.i].line = 'a brand new line'; drawDrawer()")
            self.assertIn("a brand new line", pg.inner_text(".drawer"))
            self.assertEqual(pg.evaluate("document.querySelector('.cam img').__same"), 1, "the pictures were rebuilt for a text change")
            pg.click(".cam >> nth=0"); pg.evaluate("drawDrawer()")
            self.assertFalse(pg.evaluate("document.querySelector('.cam').classList.contains('big')"))
            pg.click(".cam >> nth=0")
            pg.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
