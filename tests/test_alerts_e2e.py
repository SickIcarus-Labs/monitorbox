"""Alerts end to end through the real launcher and App: save the Home Assistant webhook, test it, and get a real problem message."""
import http.server, json, os, socket, sys, threading, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T
from ha_fake import FakeHA
from smtp_fake import FakeSmtp
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


class Receiver:
    def __init__(self):
        self.got = []
        me = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                me.got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(200); self.end_headers()

            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class AlertsE2E(unittest.TestCase):
    setUp, tearDown = T.base.E2E.setUp, T.base.E2E.tearDown
    write_json, read_json = staticmethod(T.base.E2E.write_json), staticmethod(T.base.E2E.read_json)
    publish, health_version, mod_version = T.base.E2E.publish, T.base.E2E.health_version, T.base.E2E.mod_version
    wait_all_modules = T.base.E2E.wait_all_modules
    start, configure = T.SnmpE2E.start, T.SnmpE2E.configure

    def closed_port(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
        return p

    def test_save_test_and_a_real_problem_reach_the_webhook(self):
        rx = Receiver(); self.addCleanup(rx.close)
        c = self.start()
        self.assertEqual(c.get("/api/alerts")["enabled"], False)
        self.assertEqual(c.post("/api/alerts/test", {})["ok"], False)
        hook = f"http://127.0.0.1:{rx.port}/api/webhook/fake-e2e-hook-71"
        got = c.post("/api/alerts", {"enabled": True, "site": "Distinct site 72", "delaySeconds": 0, "homeAssistant": {"webhook": hook}})
        self.assertEqual({k: got["homeAssistant"][k] for k in ("set", "host", "webhook")}, {"set": True, "host": f"127.0.0.1:{rx.port}", "webhook": hook})
        self.assertEqual(c.post("/api/alerts", {"delaySeconds": -3}).get("error", "")[:9], "The delay")
        r = c.post("/api/alerts/test", {})
        self.assertTrue(r["ok"], r)
        self.assertEqual(rx.got[0][0], "/api/webhook/fake-e2e-hook-71")
        self.assertEqual((rx.got[0][1]["event"], rx.got[0][1]["title"]), ("test", "Distinct site 72: test alert"))
        self.configure(c, [], [{"id": "dead", "name": "Dead thing", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.closed_port(), "interval": 2}]}])
        ev = T.wait(lambda: next((b for _p, b in rx.got if b["event"] == "problem"), None), 60, what="the problem message")
        self.assertEqual((ev["name"], ev["state"], ev["site"], ev["title"]), ("Dead thing", "failed", "Distinct site 72", "Distinct site 72: Dead thing is down"))
        self.assertIn("Dead thing is down", ev["message"])
        self.assertEqual(c.get("/api/alerts")["last"]["ok"], True)
        T.wait(lambda: c.get("/api/alerts")["open"] == 1, 10, what="one open alert")
        mode = os.stat(os.path.join(self.cfg, "config", "alerts.json")).st_mode & 0o777
        self.assertEqual(oct(mode), "0o600")

    def test_alerts_use_the_name_given_to_this_site_not_the_computer_name(self):
        """Regression: alerts said "Apollo" (the computer's name) while the tabs said the site name set in Settings, Sites."""
        rx = Receiver(); self.addCleanup(rx.close)
        c = self.start()
        c.post("/api/sites/name", {"name": "Distinct site name 73"})
        self.assertEqual(c.get("/api/alerts")["siteDefault"], "Distinct site name 73")
        hook = f"http://127.0.0.1:{rx.port}/api/webhook/fake-e2e-hook-73"
        c.post("/api/alerts", {"enabled": True, "site": "", "delaySeconds": 0, "homeAssistant": {"webhook": hook}})
        self.assertTrue(c.post("/api/alerts/test", {})["ok"])
        self.assertEqual(rx.got[0][1]["title"], "Distinct site name 73: test alert")

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_alerts_are_set_up_in_settings_and_the_test_button_says_what_happened(self):
        rx = Receiver(); self.addCleanup(rx.close)
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings"); pg.wait_for_selector(".hub >> text=Alerts")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/alerts"); pg.wait_for_selector("#al-hook", state="attached")
            self.assertTrue(pg.is_disabled("button:text-is(\"Send a test alert\")"))
            self.assertTrue(pg.is_disabled("#al-on"), "alerts cannot be turned on before an address is saved")
            hook = f"http://127.0.0.1:{rx.port}/api/webhook/fake-ui-hook-81"
            pg.click("summary:has-text(\"Other ways to connect\")")
            pg.fill("#al-hook", hook)
            pg.click("button:text-is(\"Save address\")"); pg.wait_for_selector("text=Saved. Send a test alert")
            self.assertEqual(pg.input_value("#al-hook"), hook, "the address stays readable so a typo can be found")
            self.assertEqual(pg.get_attribute("#al-hook", "type"), "text")
            order = pg.evaluate("[...document.querySelectorAll('#alset h3')].map(h=>h.textContent).filter(t=>/^[0-9]/.test(t))")
            self.assertEqual([x[:2] for x in order], ["1.", "2.", "3.", "4."], "connect, email, then try it, then turn on")
            self.assertFalse(pg.is_disabled("#al-on"))
            self.assertIn("0.07", pg.evaluate("getComputedStyle(document.querySelector('#al-delay')).backgroundColor"), "the number box is dark like the others, so its text can be read")
            for w in (1000, 768, 420):
                pg.set_viewport_size({"width": w, "height": 900}); pg.wait_for_timeout(200)
                self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), w + 1, f"the Alerts page fits at {w}px wide")
            pg.set_viewport_size({"width": 1000, "height": 900})
            pg.click("#al-on"); pg.wait_for_function("alCfg && alCfg.enabled")
            self.assertEqual(c.get("/api/alerts")["enabled"], True)
            self.assertTrue(pg.is_visible("#al-hook"), "the webhook box stays open after saving")
            pg.fill("#al-hook", hook + "-b")                       # a changed address is used by the test button without a separate save
            pg.click("button:text-is(\"Send a test alert\")"); pg.wait_for_selector("text=Home Assistant accepted it")
            self.assertEqual(rx.got[0][0], "/api/webhook/fake-ui-hook-81-b")
            self.assertEqual(rx.got[0][1]["event"], "test")
            pg.wait_for_selector("text=Last message delivered")
            self.assertEqual(errs, [])
            b.close()


    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_email_is_set_up_on_the_alerts_screen_and_the_test_button_sends_a_real_message(self):
        smtp = FakeSmtp("ui-user@example.invalid", "fake-ui-app-pw-5521"); self.addCleanup(smtp.close)
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/alerts"); pg.wait_for_selector("#em-host")
            pg.click("button:text-is(\"Gmail\")")
            self.assertEqual((pg.input_value("#em-host"), pg.input_value("#em-port"), pg.input_value("#em-sec")), ("smtp.gmail.com", "587", "starttls"))
            pg.fill("#em-host", "127.0.0.1"); pg.fill("#em-port", str(smtp.port)); pg.select_option("#em-sec", "none")
            pg.fill("#em-user", "ui-user@example.invalid"); pg.fill("#em-pw", "fake-ui-app-pw-5521")
            pg.fill("#em-from", "ui-user@example.invalid"); pg.fill("#em-to", "me@example.invalid")
            pg.click("button:text-is(\"Save email\")"); pg.wait_for_selector("text=Saved. Send a test alert")
            self.assertNotIn("fake-ui-app-pw-5521", pg.content())                  # the password is not shown back
            self.assertIn("saved, shown as dots", pg.inner_text("#alset"))
            pg.click("button:text-is(\"Send a test alert\")"); pg.wait_for_selector("text=Email sent to me@example.invalid")
            self.assertEqual(len(smtp.messages), 1)
            self.assertFalse(pg.is_disabled("#al-on"))                              # email alone is enough
            pg.fill("#em-pw", "fake-ui-wrong-pw-0"); pg.click("button:text-is(\"Save email\")"); pg.wait_for_selector("text=Saved. Send a test alert")
            pg.click("button:text-is(\"Send a test alert\")"); pg.wait_for_selector("text=refused the user name or password")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_connecting_a_home_assistant_account_in_the_browser_ticks_devices_and_sends_to_them(self):
        fake = FakeHA(); self.addCleanup(fake.close)
        c = self.start()
        self.configure(c, [], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/alerts"); pg.wait_for_selector("#al-ha")
            self.assertTrue(pg.is_disabled("#al-on"), "cannot turn alerts on before anything is connected")
            pg.fill("#al-ha", fake.url + "/")
            pg.click("button:text-is(\"Connect\")")
            pg.wait_for_selector("#al-devs input[data-dev]", timeout=20000)                      # signed in on the fake sign-in page and back again
            self.assertEqual(fake.authorize_calls[0]["client_id"], f"http://127.0.0.1:{self.port}/")
            self.assertEqual(fake.authorize_calls[0]["redirect_uri"], f"http://127.0.0.1:{self.port}/ha-callback")
            self.assertIn("Connected to", pg.inner_text("#alset"))
            self.assertEqual(pg.locator("#al-devs input[data-dev]:checked").count(), 2, "every phone and tablet starts ticked")
            self.assertIn("Phone One", pg.inner_text("#al-devs"))
            pg.uncheck("#al-devs input[data-dev=mobile_app_tablet_two]"); pg.wait_for_selector("#al-dm:has-text(\"Saved\")")
            self.assertEqual(c.get("/api/alerts")["homeAssistant"]["devices"], ["mobile_app_phone_one"])
            pg.click("button:text-is(\"Send a test alert\")"); pg.wait_for_selector("text=Sent to Phone One")
            self.assertEqual([n for n, _ in fake.sent], ["mobile_app_phone_one"])
            self.assertFalse(pg.is_disabled("#al-on"))
            pg.click("#al-on"); pg.wait_for_function("alCfg && alCfg.enabled")
            self.assertNotIn("fake-refresh-222", json.dumps(c.get("/api/alerts")))
            self.assertNotIn("fake-refresh-222", pg.content())
            # the owner takes the account away in Home Assistant: the screen says so and offers to connect again
            fake.expire_access(); fake.reject_refresh = True
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/alerts"); pg.reload(); pg.wait_for_selector("#al-devs")
            pg.wait_for_selector("text=no longer accepts MonitorBox's sign-in")
            self.assertTrue(pg.is_visible("#al-devs button:text-is(\"Connect again\")"), "the screen offers to connect again")
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "alerts-ha.png"))
            fake.reject_refresh = False
            pg.click("button:text-is(\"Disconnect\")"); pg.click("#ask-ok")
            pg.wait_for_selector("#al-ha")
            self.assertIn("fake-refresh-222", fake.revoked)
            self.assertEqual(c.get("/api/alerts")["enabled"], False)
            self.assertEqual(errs, [])
            b.close()

    def test_the_sign_in_return_page_needs_no_session_but_does_need_the_state_value_we_started(self):
        fake = FakeHA(); self.addCleanup(fake.close)
        c = self.start()
        import urllib.request, urllib.parse
        r = c.post("/api/alerts/ha/begin", {"url": fake.url})
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r["url"]).query))
        self.assertEqual(q["client_id"], f"http://127.0.0.1:{self.port}/")
        def hit(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:      # no cookie, like a browser arriving from another address
                return resp.read().decode()
        self.assertIn("expired or was not started here", hit("/ha-callback?code=fake-code-111&state=made-up"))
        self.assertFalse(c.get("/api/alerts")["homeAssistant"]["connected"])
        self.assertIn("Connected.", hit(f"/ha-callback?code=fake-code-111&state={q['state']}"))
        self.assertTrue(c.get("/api/alerts")["homeAssistant"]["connected"])
        self.assertIn("expired or was not started here", hit(f"/ha-callback?code=fake-code-111&state={q['state']}"))
        self.assertEqual(c.post("/api/alerts/ha/begin", {"url": "nope"}).get("_status"), 400)


if __name__ == "__main__":
    unittest.main()
