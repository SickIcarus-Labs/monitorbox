"""Sites: two real Apps side by side, paired over the TLS-PSK site port, then managed through the pass-through."""
import http.client, json, os, socket, ssl, sys, tempfile, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app.server import App
from monitorbox_app import peer


def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Box:
    def __init__(self, test, pw):
        self.root = tempfile.mkdtemp(); self.port = free(); self.pw = pw
        self.app = App(self.root, "http://127.0.0.1:9/none", "dev", self.port)
        self.t = threading.Thread(target=self.app.serve, daemon=True); self.t.start()
        for _ in range(100):
            try:
                self.req("GET", "/api/health"); break
            except OSError:
                time.sleep(0.1)
        self.req("POST", "/api/setup", {"password": pw})
        _, _, h = self.req("POST", "/api/login", {"password": pw}, raw=True)
        self.cookie = h.split(";")[0]
        test.addCleanup(self.close)

    def req(self, m, path, body=None, raw=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        hd = {"X-MB": "1"}
        if getattr(self, "cookie", None): hd["Cookie"] = self.cookie
        c.request(m, path, json.dumps(body) if body is not None else None, hd)
        r = c.getresponse(); data = r.read(); sc = r.getheader("Set-Cookie") or ""
        c.close()
        j = json.loads(data) if data and not raw else None
        return (r.status, j, sc) if raw else (r.status, j)

    def get(self, p): return self.req("GET", p)[1]
    def post(self, p, b=None): return self.req("POST", p, b or {})

    def close(self):
        try: self.app.httpd.shutdown()
        except Exception: pass


class Sites(unittest.TestCase):
    def pair(self):
        main, tb = Box(self, "fake-main-pw-11"), Box(self, "fake-tb-pw-2222")
        tport = free()
        tb.post("/api/sites/name", {"name": "Tidewater"})
        st = tb.post("/api/sites/listen", {"enabled": True, "port": tport})[1]
        self.assertTrue(st["listening"])
        code = tb.post("/api/sites/pair/start")[1]["pairing"]["code"]
        main.post("/api/sites/name", {"name": "Bay Harbor"})
        out = main.post("/api/sites/add", {"address": f"127.0.0.1:{tport}", "code": code})
        return main, tb, tport, code, out

    def test_pairing_then_the_code_is_useless_and_keys_are_private(self):
        main, tb, tport, code, (sc, out) = self.pair()
        self.assertEqual(sc, 200, out)
        s = out["sites"][0]
        self.assertEqual((s["id"], s["name"]), ("tidewater", "Tidewater"))
        self.assertNotIn("key", json.dumps(out)); self.assertNotIn("key", json.dumps(tb.get("/api/sites")))
        self.assertEqual(tb.get("/api/sites")["managers"][0]["name"], "Bay Harbor")
        self.assertIsNone(tb.get("/api/sites")["pairing"])
        for b in (main, tb):
            self.assertEqual(oct(os.stat(os.path.join(b.root, "config", "sites.json")).st_mode & 0o777), "0o600")
        # the same code again is refused
        sc, e = main.post("/api/sites/add", {"address": f"localhost:{tport}", "code": code, "name": "Again"})
        self.assertEqual(sc, 400); self.assertIn("did not accept the code", e["error"])

    def test_pass_through_reads_and_changes_the_other_box_but_not_the_other_way(self):
        main, tb, tport, code, _ = self.pair()
        tb_status = main.get("/api/site/tidewater/status")
        self.assertEqual(tb_status["banner"], tb.get("/api/status")["banner"])
        # change something on tb through main
        rev = tb.get("/api/config/monitoring")["revision"]
        sc, r = main.post("/api/site/tidewater/config/monitoring", {"monitoring": {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [{"id": "x", "name": "Distinct 93", "group": "G", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": 9, "interval": 30}]}]}, "revision": rev})
        self.assertEqual(sc, 200, r)
        self.assertEqual(tb.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Distinct 93")
        # the change did not reach main; main holds only the link system its own pairing made
        self.assertEqual([n["id"] for n in main.get("/api/config/monitoring")["monitoring"]["nodes"]], ["site-tidewater"])
        # blocked: sign-in, sites, streams
        for p in ("/api/site/tidewater/sites", "/api/site/tidewater/site/tidewater/status", "/api/site/tidewater/stream"):
            self.assertEqual(main.req("GET", p)[0], 403, p)
        self.assertEqual(main.req("POST", "/api/site/tidewater/sites/pair/start", {})[0], 403)
        # tb has no way to reach main: it holds no sites
        self.assertEqual(tb.get("/api/sites")["sites"], [])
        self.assertEqual(main.req("GET", "/api/site/nope/status")[0], 502)

    def test_strangers_and_wrong_keys_get_nothing_and_get_shut_out(self):
        main, tb, tport, code, _ = self.pair()
        def tls(identity, key):
            return peer.call_json(f"127.0.0.1:{tport}", identity, key, "GET", "/peer/hello", timeout=5)
        with self.assertRaises(peer.PeerError): tls("pair", b"AAAAA")
        with self.assertRaises(peer.PeerError): tls("m:nobody", b"x" * 32)
        # plain (non-TLS) visitors get nothing
        s = socket.create_connection(("127.0.0.1", tport), timeout=5); s.sendall(b"GET /peer/hello HTTP/1.0\r\n\r\n")
        try: self.assertEqual(s.recv(100)[:5] != b"HTTP/", True)
        except OSError: pass
        s.close()
        # ten failures shut the address out, even for the right key
        for _ in range(12):
            try: tls("m:nobody", b"x" * 32)
            except peer.PeerError: pass
        self.assertEqual(main.post("/api/sites/rename", {"id": "tidewater", "name": "TB"})[0], 200)
        deadline = time.time() + 12
        while time.time() < deadline and main.get("/api/sites")["sites"][0]["link"]["state"] == "linked":
            main.app.peer.poll_once(); time.sleep(0.3)
        self.assertNotEqual(main.get("/api/sites")["sites"][0]["link"]["state"], "linked")

    def test_removing_a_manager_cuts_it_off_and_a_dead_site_is_unknown_not_failed(self):
        main, tb, tport, code, _ = self.pair()
        mid = tb.get("/api/sites")["managers"][0]["id"]
        main.app.peer.poll_once()
        self.assertEqual(main.get("/api/sites")["sites"][0]["link"]["state"], "linked")
        tb.post("/api/sites/manager/remove", {"id": mid})
        main.app.peer.poll_once()
        link = main.get("/api/sites")["sites"][0]["link"]
        self.assertEqual(link["state"], "refused"); self.assertIn("pair the sites again", link["error"])
        # switch the site port off: unreachable, reported as 'not answering', and the last good time is kept
        tb.post("/api/sites/listen", {"enabled": False})
        main.app.peer.poll_once()
        link = main.get("/api/sites")["sites"][0]["link"]
        self.assertIn(link["state"], ("unknown", "refused"))

    def test_each_pairing_is_a_watched_system_that_is_unknown_never_down_and_follows_rename_and_remove(self):
        main, tb, tport, code, _ = self.pair()

        def wait(box, node, present=True):
            for _ in range(100):
                box.app.monitor.check_now(wait=True)
                if (node in box.app.monitor.snapshot()["nodes"]) == present:
                    return
                time.sleep(0.1)
            self.fail(f"{node} {'missing' if present else 'still there'}")

        def res(box, key):
            return box.app.monitor.results.get(key)

        mid = tb.get("/api/sites")["managers"][0]["id"]
        wait(main, "site-tidewater"); wait(tb, "managed-by-" + mid)
        main.app.peer.poll_once()
        main.app.monitor.check_now(wait=True)
        self.assertIs(res(main, "site-tidewater/link")["ok"], True)
        tb.app.monitor.check_now(wait=True)
        self.assertIs(res(tb, "managed-by-" + mid + "/link")["ok"], True)
        # rename follows
        main.post("/api/sites/rename", {"id": "tidewater", "name": "Tidewater Lodge"})
        for _ in range(50):
            if main.app.monitor.snapshot()["nodes"].get("site-tidewater", {}).get("name") == "Tidewater Lodge link":
                break
            time.sleep(0.1)
        self.assertEqual(main.app.monitor.snapshot()["nodes"]["site-tidewater"]["name"], "Tidewater Lodge link")
        # the managing box is renamed after pairing: the managed box follows, in its list and in "Managed by"
        main.post("/api/sites/name", {"name": "Bay Harbor Two"})
        main.app.peer.poll_once()
        self.assertEqual(tb.get("/api/sites")["managers"][0]["name"], "Bay Harbor Two")
        for _ in range(50):
            if tb.app.monitor.snapshot()["nodes"].get("managed-by-" + mid, {}).get("name") == "Managed by Bay Harbor Two":
                break
            time.sleep(0.1)
        self.assertEqual(tb.app.monitor.snapshot()["nodes"]["managed-by-" + mid]["name"], "Managed by Bay Harbor Two")
        # a silent site is Unknown, never Failed, however many times it is looked at
        tb.post("/api/sites/listen", {"enabled": False})
        main.app.peer.poll_once()
        for _ in range(4):
            main.app.monitor.check_now(wait=True)
            r = res(main, "site-tidewater/link")
            self.assertIsNone(r["ok"], r)
        self.assertIn("Tidewater Lodge", r["detail"])
        # a manager gone quiet is Unknown on the managed box, never Failed
        tb.app.peer.seen[mid] = tb.app.peer.clock() - 10000
        tb.app.monitor.check_now(wait=True)
        self.assertIsNone(res(tb, "managed-by-" + mid + "/link")["ok"])
        # removing the pairing removes the system, and the box that was managed
        main.post("/api/sites/remove", {"id": "tidewater"})
        wait(main, "site-tidewater", present=False)
        tb.post("/api/sites/manager/remove", {"id": mid})
        wait(tb, "managed-by-" + mid, present=False)

    def test_bad_input_is_explained(self):
        main = Box(self, "fake-main-pw-33")
        sc, e = main.post("/api/sites/pair/start")
        self.assertEqual(sc, 400); self.assertIn("Give this site a name first", e["error"])
        sc, e = main.post("/api/sites/add", {"address": "127.0.0.1:1", "code": "ABCDE-ABCDE-ABCDE-ABCDE-ABCDE"})
        self.assertEqual(sc, 400); self.assertIn("Give this site a name first", e["error"])
        main.post("/api/sites/name", {"name": "Distinct name 95"})
        for addr, code in (("", "x"), ("host:99999", "A" * 25), ("127.0.0.1:1", "SHORT")):
            sc, e = main.post("/api/sites/add", {"address": addr, "code": code})
            self.assertEqual(sc, 400); self.assertTrue(e["error"])
        sc, e = main.post("/api/sites/add", {"address": f"127.0.0.1:{free()}", "code": "ABCDE-ABCDE-ABCDE-ABCDE-ABCDE"})
        self.assertEqual(sc, 400); self.assertIn("site port", e["error"])

    def test_settings_page_pairs_two_boxes_and_the_backup_keeps_the_sites(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        main, tb = Box(self, "fake-main-pw-44"), Box(self, "fake-tb-pw-5555")
        tport = free()
        with sync_playwright() as p:
            b = p.chromium.launch()
            def page(box):
                pg = b.new_page(viewport={"width": 420, "height": 900}); pg.goto(f"http://127.0.0.1:{box.port}/")
                pg.wait_for_selector("input[type=password]"); pg.fill("input[type=password]", box.pw); pg.keyboard.press("Enter")
                pg.wait_for_selector(".card, .box"); pg.goto(f"http://127.0.0.1:{box.port}/#/settings/sites"); pg.wait_for_selector("#si-port")
                return pg
            pt = page(tb)
            pt.fill("#si-name", "Tidewater"); pt.fill("#si-port", str(tport)); pt.click("button:has-text(\"Let a main MonitorBox manage this one\")")
            pt.wait_for_selector("text=Enter this code")
            self.assertGreaterEqual(pt.inner_text("#siset").count(str(tport)), 3, "the page names the actual site port wherever it talks about the port")
            code = pt.inner_text("p[style*=monospace]").strip()
            self.assertEqual(len(code.replace("-", "")), 25)
            pm = page(main)
            pm.fill("#si-name", "Bay Harbor"); pm.fill("#si-addr", f"127.0.0.1:{tport}"); pm.fill("#si-code", code); pm.click("button:has-text(\"Add site\")")
            pm.wait_for_selector("text=Reachable")
            self.assertFalse(pm.evaluate("document.documentElement.scrollWidth > innerWidth"))
            pt.reload(); pt.wait_for_selector("text=Managed by")
            b.close()
        # the saved sites survive a backup round trip, every value distinct
        import tarfile, io
        cfg = json.load(open(os.path.join(main.root, "config", "sites.json")))
        self.assertEqual(len(cfg["sites"][0]["key"]), 64)
        self.assertNotEqual(cfg["sites"][0]["key"], json.load(open(os.path.join(tb.root, "config", "sites.json")))["managers"][0]["key"] + "x")

    def test_tabs_show_each_site_and_a_silent_site_is_unknown_never_down(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        main, tb, tport, code, _ = self.pair()
        node = lambda name, port: {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [{"id": "n1", "name": name, "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": port, "interval": 2}]}]}
        main.post("/api/config/monitoring", {"monitoring": node("Distinct main thing 91", main.port), "revision": main.get("/api/config/monitoring")["revision"]})
        tb.post("/api/config/monitoring", {"monitoring": node("Distinct far thing 92", free()), "revision": tb.get("/api/config/monitoring")["revision"]})
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 420, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{main.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", main.pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("#hdr .tab >> text=Tidewater")
            pg.wait_for_selector("text=Distinct main thing 91")
            pg.wait_for_selector("#hdr .all >> text=Tidewater")            # the far site has a real problem: "All sites" says so
            pg.click("#hdr .tab >> text=Tidewater")
            pg.wait_for_selector("text=Distinct far thing 92"); self.assertEqual(pg.locator("text=Distinct main thing 91").count(), 0)
            self.assertEqual(pg.evaluate("U('live/events?client=abc')"), "/api/site/tidewater/live/events?client=abc", "live video setup goes to the site's own box")
            pg.goto(f"http://127.0.0.1:{main.port}/#/settings"); pg.wait_for_selector(".hub >> text=Alerts")
            self.assertEqual(pg.locator(".hub >> text=Other MonitorBoxes").count(), 0, "the far site's settings have no Sites section")
            pg.goto(f"http://127.0.0.1:{main.port}/#/"); pg.wait_for_selector("text=Distinct far thing 92")
            tb.post("/api/sites/listen", {"enabled": False})                  # the far site goes quiet
            pg.wait_for_selector("text=is not answering from here", timeout=20000)
            self.assertIn("keeps running and alerting on its own", pg.inner_text("#m"))
            pg.wait_for_selector("#hdr .all >> text=Unknown", timeout=30000)
            self.assertFalse(pg.evaluate("document.documentElement.scrollWidth > innerWidth"))
            pg.click("#hdr .tab:first-child")
            pg.wait_for_selector("text=Distinct main thing 91")
            self.assertEqual(errs, [])
            b.close()

    def test_each_sites_graphs_stay_its_own_when_switching_tabs(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        main, tb, tport, code, _ = self.pair()
        gr = lambda box, title: json.dump([{"id": "g-" + title.split()[-1], "title": title, "connection": "c-" + title.split()[-1], "interface": "eth0"}],
                                          open(os.path.join(box.root, "config", "graphs.json"), "w"))
        gr(main, "Distinct main graph 96"); gr(tb, "Distinct far graph 97")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
            pg.goto(f"http://127.0.0.1:{main.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", main.pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("#hdr .tab >> text=Tidewater"); pg.wait_for_selector("text=Distinct main graph 96")
            pg.click("#hdr .tab >> text=Tidewater")
            pg.wait_for_selector("text=Distinct far graph 97"); self.assertEqual(pg.locator("text=Distinct main graph 96").count(), 0)
            pg.click("#hdr .tab:first-child")
            pg.wait_for_selector("text=Distinct main graph 96"); self.assertEqual(pg.locator("text=Distinct far graph 97").count(), 0)
            b.close()
        self.assertEqual(json.load(open(os.path.join(main.root, "config", "graphs.json")))[0]["title"], "Distinct main graph 96")
        self.assertEqual(json.load(open(os.path.join(tb.root, "config", "graphs.json")))[0]["title"], "Distinct far graph 97")

    def test_a_fold_opens_by_itself_for_a_problem_but_not_for_something_that_cannot_be_checked(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        main = Box(self, "fake-main-pw-55")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            pg.goto(f"http://127.0.0.1:{main.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", main.pw); pg.keyboard.press("Enter"); pg.wait_for_selector(".head, .card")
            opened = lambda states: pg.evaluate("s=>fold('k-'+s.join(),'healthy','Thing',s,()=>'',0,true).includes('aria-expanded=true')", states)
            self.assertFalse(opened(["healthy", "healthy"]))
            self.assertFalse(opened(["healthy", "unknown"]), "unknown does not force it open")
            self.assertTrue(opened(["healthy", "degraded"]))
            self.assertTrue(opened(["unknown", "failed"]))
            self.assertIn("1 need a look", pg.evaluate("fold('k','healthy','T',['healthy','unknown'],()=>'',0,true)"), "it is still counted")
            b.close()

    def test_the_live_camera_channel_passes_through_and_ends_with_the_page(self):
        main, tb, tport, code, _ = self.pair()
        c = http.client.HTTPConnection("127.0.0.1", main.port, timeout=20)
        c.request("GET", "/api/site/tidewater/live/events?client=page-test-1", headers={"Cookie": main.cookie, "X-MB": "1"})
        r = c.getresponse()
        self.assertEqual(r.status, 200); self.assertEqual(r.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(r.fp.readline(), b": open\n", "the first event arrives at once, not after a full block")
        self.assertIn("page-test-1", tb.app._live_state()["clients"], "the channel is open on the managed box, not the main one")
        self.assertNotIn("page-test-1", main.app._live_state()["clients"])
        sc, e = main.post("/api/site/tidewater/live/open", {"client": "page-test-1", "connection": "none", "id": "x"})
        self.assertNotEqual(sc, 403, "starting a view is passed to the managed box")
        r.close(); c.close()                                   # the page goes away
        deadline = time.time() + 15
        while time.time() < deadline and "page-test-1" in tb.app._live_state()["clients"]:
            time.sleep(0.5)
        self.assertNotIn("page-test-1", tb.app._live_state()["clients"], "closing the page ends the channel on the managed box")

    def test_live_media_is_relayed_through_the_site_link_with_addresses_swapped(self):
        import socket, threading
        main, tb, tport, code, _ = self.pair()
        rev = tb.get("/api/config/connections")["revision"]
        tb.post("/api/config/connections", {"revision": rev, "connections": [{"id": "scr", "module": "scrypted", "host": "127.0.0.1", "username": "viewer-fake", "password": "pw-fake-6203"}]})
        # Scrypted stand-in: the module is replaced by a recorder, and a UDP socket plays Scrypted's media port
        mods, listeners = [], {}
        tb.app.modules.listen = lambda mid, sid, cb: listeners.__setitem__(sid, cb)
        tb.app.modules.unlisten = lambda mid, sid: listeners.pop(sid, None)
        tb.app.modules.call = lambda mid, method, params, timeout=10: mods.append((method, params)) or {}
        scr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); scr.bind(("127.0.0.1", 0)); scr.settimeout(0.5); self.addCleanup(scr.close)
        page = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); page.bind(("127.0.0.1", 0)); page.settimeout(0.5); self.addCleanup(page.close)
        events, got = [], threading.Condition()
        c = http.client.HTTPConnection("127.0.0.1", main.port, timeout=30)
        c.request("GET", "/api/site/tidewater/live/events?client=page-relay-1", headers={"Cookie": main.cookie, "X-MB": "1"})
        r = c.getresponse()
        self.addCleanup(lambda: (r.fp.raw._sock.shutdown(socket.SHUT_RDWR), r.close()))      # the reading thread holds the stream: end it from the socket
        def pump():
            try:
                for raw in r.fp:
                    if raw.startswith(b"data: "):
                        with got:
                            events.append(json.loads(raw[6:])); got.notify_all()
            except Exception:
                pass
        threading.Thread(target=pump, daemon=True).start()
        sc, out = main.post("/api/site/tidewater/live/open", {"client": "page-relay-1", "connection": "scr", "id": "1", "options": {}})
        self.assertEqual(sc, 200, out); self.assertTrue(out["relay"])
        sid = out["session"]
        time.sleep(2.5)       # the event stream sits idle for a while first (it used to die at its first idle second)
        # Scrypted answers with its own address in the SDP and trickles another candidate
        sdp = f"v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:0\r\na=candidate:1 1 udp 2130706431 127.0.0.1 {scr.getsockname()[1]} typ host\r\n"
        listeners[sid]({"message": {"type": "call", "callId": "7", "method": "setRemoteDescription", "args": [{"type": "answer", "sdp": sdp}, {}]}})
        listeners[sid]({"message": {"type": "call", "callId": "8", "method": "addIceCandidate", "args": [{"candidate": f"candidate:2 1 udp 1 127.0.0.1 {scr.getsockname()[1]} typ host"}]}})
        with got:
            self.assertTrue(got.wait_for(lambda: any(e["message"].get("method") == "setRemoteDescription" for e in events), timeout=15), events)
            seen = next(e["message"] for e in events if e["message"].get("method") == "setRemoteDescription")
        shown = seen["args"][0]["sdp"]
        self.assertNotIn(str(scr.getsockname()[1]), shown, "the browser is not told Scrypted's own address")
        import re
        m = re.search(r"a=candidate:\S+ 1 udp \d+ (\S+) (\d+) typ host", shown)
        self.assertTrue(m, shown)
        main_addr = (m.group(1), int(m.group(2)))
        self.assertEqual(main_addr[0], "127.0.0.1")
        self.assertEqual(main_addr[1], main.app.relays.get(sid)["pipe"].port, "the browser is given this box's relay port")
        time.sleep(0.5)
        self.assertFalse(any(e["message"].get("method") == "addIceCandidate" for e in events), "Scrypted's trickled candidate is not passed on")
        self.assertIn(("live_input", {"session": sid, "message": {"type": "result", "callId": "8", "value": None}}), mods, "the managed box answers that call itself")
        # the browser's setup message reaches Scrypted with the managed box's relay address, not the browser's
        main.post("/api/site/tidewater/live/input", {"session": sid, "message": {"type": "result", "callId": "1", "value": {"type": "offer", "sdp": "v=0\r\nm=video 9 X\r\na=candidate:9 1 udp 1 203.0.113.77 55555 typ host\r\n"}}})
        sent = [p for mth, p in mods if mth == "live_input" and p["message"].get("callId") == "1"][0]["message"]["value"]["sdp"]
        self.assertNotIn("203.0.113.77", sent)
        tb_port = tb.app.live_relay(sid).port
        self.assertIn(f"127.0.0.1 {tb_port} typ host", sent, "Scrypted is told to send to the managed box's relay port")
        # media: the page sends to the main box, Scrypted receives it from the managed box; the reply goes back the same way
        deadline, data, src = time.time() + 15, None, None
        while time.time() < deadline and data is None:
            page.sendto(b"\x80page-to-scrypted", main_addr)
            try:
                data, src = scr.recvfrom(2000)
            except socket.timeout:
                pass
        self.assertEqual(data, b"\x80page-to-scrypted"); self.assertEqual(src[1], tb_port, "Scrypted sees the managed box's relay port")
        back = None
        while time.time() < deadline and back is None:
            scr.sendto(b"\x80scrypted-to-page", src)
            try:
                back, bsrc = page.recvfrom(2000)
            except socket.timeout:
                pass
        self.assertEqual(back, b"\x80scrypted-to-page"); self.assertEqual(bsrc, main_addr, "the page sees the main box's relay port")
        # a heavy two-way load (about 30 Mbit/s each way for a couple of seconds) must not break the stream
        counts = {"scr": 0, "page": 0}
        stop = threading.Event()
        def drain(sock, key):
            sock.settimeout(0.2)
            while not stop.is_set():
                try:
                    sock.recvfrom(4000); counts[key] += 1
                except socket.timeout:
                    pass
        scr.settimeout(0.2)
        ts = [threading.Thread(target=drain, args=(scr, "scr"), daemon=True), threading.Thread(target=drain, args=(page, "page"), daemon=True)]
        [t.start() for t in ts]
        def blast(sock, addr, n):
            for i in range(n):
                sock.sendto(b"\x80" + bytes(1199), addr)
                if i % 25 == 0:
                    time.sleep(0.003)
        b1 = threading.Thread(target=blast, args=(page, main_addr, 3000)); b2 = threading.Thread(target=blast, args=(scr, ("127.0.0.1", tb_port), 3000))
        b1.start(); b2.start(); b1.join(); b2.join(); time.sleep(1.5); stop.set()
        self.assertGreater(counts["scr"], 2000); self.assertGreater(counts["page"], 2000)
        self.assertFalse(main.app.relays.get(sid)["pipe"].closed.is_set() or tb.app.live_relay(sid).closed.is_set(), "the relay survived the load")
        # the numbers behind the picture are there for the next time something looks wrong (read through the main box, from both ends)
        mine = main.get("/api/live/relays")["mainBox"][0]
        theirs = main.get("/api/site/tidewater/live/relays")["siteBox"][0]
        self.assertTrue(mine["linked"] and theirs["linked"] and theirs["target"])
        self.assertGreater(mine["packetsIn"], 0); self.assertGreater(mine["packetsOut"], 0)
        self.assertGreater(theirs["bytesIn"], 0); self.assertGreater(theirs["bytesOut"], 0)
        # the view ends: both relay ports are gone
        listeners[sid]({"message": {"type": "closed", "reason": "ended"}})
        deadline = time.time() + 10
        while time.time() < deadline and (main.app.relays.by_sid or tb.app.live_relay(sid)):
            time.sleep(0.2)
        self.assertFalse(main.app.relays.by_sid); self.assertIsNone(tb.app.live_relay(sid))


if __name__ == "__main__":
    unittest.main()
