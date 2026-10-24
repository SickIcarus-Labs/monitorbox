"""Alerts through a Home Assistant account: sign-in tokens, device list, direct sending, partial failures, expired sign-ins."""
import os, sys, tempfile, unittest, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import alerts, ha, engine  # noqa: E402
from ha_fake import FakeHA  # noqa: E402

ORIGIN = "http://192.0.2.5:8099"


def snap(down):
    nodes = [{"id": "a", "name": "Anchor3", "group": "Servers", "critical": False, "checks": [{"id": "c", "type": "ping", "target": "x"}], "rule": "primary", "dependsOn": []}]
    return engine.evaluate(nodes, {"a/c": {"ok": not down, "detail": "no answer" if down else "", "ms": 1, "at": "t", "since": "t"}}, "t")


class Account(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHA(); self.addCleanup(self.fake.close)
        self.d = tempfile.mkdtemp()
        self.now = 5000.0
        self.a = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None, clock=lambda: self.now, hostname=lambda: "box-host")

    def connect(self):
        url = self.a.begin_connect(self.fake.url + "/ignored/path", ORIGIN)
        state = dict(x.split("=", 1) for x in url.split("?", 1)[1].split("&"))["state"]
        self.assertTrue(url.startswith(self.fake.url + "/auth/authorize?"), url)
        ok, msg = self.a.complete_connect(self.fake.code, state)
        self.assertTrue(ok, msg)
        return url, state

    def test_sign_in_page_address_carries_the_apps_own_address_and_a_one_time_state(self):
        url, state = self.connect()
        q = dict(__import__("urllib.parse").parse.parse_qsl(url.split("?", 1)[1]))
        self.assertEqual((q["client_id"], q["redirect_uri"]), (ORIGIN + "/", ORIGIN + "/ha-callback"))
        ok, msg = self.a.complete_connect(self.fake.code, state)
        self.assertFalse(ok, "a state value works once")
        self.assertFalse(self.a.complete_connect(self.fake.code, "made-up")[0])

    def test_connecting_stores_a_refresh_token_never_shows_it_and_ticks_every_device(self):
        self.connect()
        g = self.a.get()["homeAssistant"]
        self.assertEqual((g["connected"], g["kind"], g["url"], g["devices"]), (True, "account", self.fake.url, ["mobile_app_phone_one", "mobile_app_tablet_two"]))
        self.assertNotIn("fake-refresh-222", json.dumps(self.a.get()))
        self.assertNotIn("fake-access", json.dumps(self.a.get()))
        self.assertEqual(self.fake.token_calls[0]["client_id"], ORIGIN + "/")
        self.assertEqual(oct(os.stat(os.path.join(self.d, "alerts.json")).st_mode & 0o777), "0o600")
        self.assertEqual([(d["id"], d["name"], d["on"]) for d in self.a.devices()], [("mobile_app_phone_one", "Phone One", True), ("mobile_app_tablet_two", "Tablet Two", True)])

    def test_the_device_list_only_offers_phones_and_tablets_not_other_notify_services_or_other_domains(self):
        self.connect()
        self.assertEqual({d["id"] for d in self.a.devices()}, {"mobile_app_phone_one", "mobile_app_tablet_two"})

    def test_a_test_alert_goes_to_each_ticked_device_only(self):
        self.connect()
        self.a.set_devices(["mobile_app_tablet_two"])
        r = self.a.test()
        self.assertTrue(r["ok"], r)
        self.assertEqual([n for n, _ in self.fake.sent], ["mobile_app_tablet_two"])
        body = self.fake.sent[0][1]
        self.assertEqual((body["title"], body["message"]), ("box-host: test alert", "This is a test alert from MonitorBox."))
        self.assertIn("Tablet Two", r["message"])

    def test_nothing_ticked_says_so(self):
        self.connect()
        self.a.set_devices([])
        r = self.a.test()
        self.assertFalse(r["ok"])
        self.assertIn("Tick", r["message"])

    def test_a_real_problem_goes_to_every_ticked_device_with_a_tag_and_time_sensitive_on_failure(self):
        self.connect()
        self.a.set({"enabled": True, "delaySeconds": 0})
        self.a.observe(snap(True), self.now); self.a.flush(self.now)
        self.assertEqual(sorted(n for n, _ in self.fake.sent), ["mobile_app_phone_one", "mobile_app_tablet_two"])
        data = self.fake.sent[0][1]["data"]
        self.assertEqual((data["tag"], data["push"]["interruption-level"]), ("monitorbox-a", "time-sensitive"))
        self.now += 100
        self.a.observe(snap(False), self.now); self.now += 40; self.a.observe(snap(False), self.now); self.a.flush(self.now)
        back = [b for n, b in self.fake.sent if "is back" in b["title"]]
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0]["data"]["tag"], "monitorbox-a", "the all-clear replaces the problem on the phone")
        self.assertNotIn("push", back[0]["data"])

    def test_when_one_device_fails_only_that_one_is_retried(self):
        self.connect()
        self.a.set({"enabled": True, "delaySeconds": 0})
        self.fake.devices.discard("mobile_app_tablet_two")           # the tablet was removed in Home Assistant
        self.a.observe(snap(True), self.now); self.a.flush(self.now)
        self.assertEqual([n for n, _ in self.fake.sent], ["mobile_app_phone_one"])
        g = self.a.get()
        self.assertEqual(g["waiting"], 1)
        self.assertIn("Tablet Two", g["last"]["error"])
        self.assertIn("no device called", g["last"]["error"])
        self.fake.devices.add("mobile_app_tablet_two")
        self.now += 10; self.a.flush(self.now)
        self.assertEqual(sorted(n for n, _ in self.fake.sent), ["mobile_app_phone_one", "mobile_app_tablet_two"], "the phone did not get it twice")
        self.assertEqual(self.a.get()["waiting"], 0)

    def test_an_expired_access_token_is_renewed_quietly_from_the_refresh_token(self):
        self.connect()
        self.fake.expire_access()                                     # Home Assistant forgot the 30 minute token early
        r = self.a.test()
        self.assertTrue(r["ok"], r)
        self.assertEqual([c["grant_type"] for c in self.fake.token_calls], ["authorization_code", "refresh_token"])

    def test_the_access_token_is_renewed_before_it_runs_out(self):
        self.connect()
        self.now += 1800 - 30
        self.a.test()
        self.assertEqual(self.fake.token_calls[-1]["grant_type"], "refresh_token")

    def test_a_sign_in_home_assistant_no_longer_accepts_asks_to_connect_again_and_alerts_keep_waiting(self):
        self.connect()
        self.a.set({"enabled": True, "delaySeconds": 0})
        self.fake.expire_access(); self.fake.reject_refresh = True    # the user was deleted, or the token revoked in its profile
        self.a.observe(snap(True), self.now); self.a.flush(self.now)
        g = self.a.get()
        self.assertTrue(g["homeAssistant"]["needsSignIn"])
        self.assertEqual(g["waiting"], 1, "the message is kept, not dropped")
        self.assertIn("Connect it again", g["last"]["error"])
        self.fake.reject_refresh = False
        self.now += 10; self.a.flush(self.now)
        self.assertEqual(self.a.get()["waiting"], 0)
        self.assertFalse(self.a.get()["homeAssistant"]["needsSignIn"])

    def test_home_assistant_being_down_is_a_plain_reason_not_a_crash(self):
        self.connect()
        self.fake.down = True
        r = self.a.test()
        self.assertFalse(r["ok"])
        self.assertNotIn("127.0.0.1", r["message"])

    def test_disconnect_revokes_the_token_and_forgets_everything(self):
        self.connect()
        self.a.set({"enabled": True})
        g = self.a.disconnect()
        self.assertEqual(self.fake.revoked, ["fake-refresh-222"])
        self.assertEqual((g["enabled"], g["homeAssistant"]["connected"], g["homeAssistant"]["devices"]), (False, False, []))
        with open(os.path.join(self.d, "alerts.json")) as f:
            self.assertNotIn("fake-refresh-222", f.read())

    def test_a_pasted_long_lived_token_works_and_is_never_shown_back(self):
        g = self.a.connect_token(self.fake.url + "/", " " + self.fake.long_lived + " ")["homeAssistant"]
        self.assertEqual((g["connected"], g["kind"], len(g["devices"])), (True, "token", 2))
        self.assertNotIn("fake-long-lived-333", json.dumps(self.a.get()))
        self.assertTrue(self.a.test()["ok"])
        self.assertEqual(self.fake.token_calls, [], "a long-lived token needs no renewing")
        with self.assertRaises(alerts.Invalid):
            self.a.connect_token(self.fake.url, "fake-wrong-token-444")
        with self.assertRaises(alerts.Invalid):
            self.a.connect_token(self.fake.url, "two words")

    def test_a_denied_sign_in_and_a_bad_address_are_explained(self):
        with self.assertRaises(alerts.Invalid):
            self.a.begin_connect("not an address", ORIGIN)
        url = self.a.begin_connect(self.fake.url, ORIGIN)
        state = dict(x.split("=", 1) for x in url.split("?", 1)[1].split("&"))["state"]
        ok, msg = self.a.complete_connect("", state, "access_denied")
        self.assertFalse(ok)
        self.assertIn("Connect again", msg)

    def test_only_phone_and_tablet_services_can_ever_be_called(self):
        self.connect()
        conn = self.a._conn()
        for bad in ("light/turn_on", "../x", "notify", "mobile_app_x/../../light", "lock_unlock", ""):
            with self.assertRaises(ha.HAError):
                conn.notify(bad, {})
        self.assertEqual(self.fake.sent, [])

    def test_enabling_needs_a_way_to_send(self):
        with self.assertRaises(alerts.Invalid):
            self.a.set({"enabled": True})
        self.connect()
        self.assertTrue(self.a.set({"enabled": True})["enabled"])


if __name__ == "__main__":
    unittest.main()
