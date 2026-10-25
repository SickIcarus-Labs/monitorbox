import json, os, smtplib, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
from monitorbox_app import alerts, mailer  # noqa: E402
from test_alerts import snap, node  # noqa: E402
from smtp_fake import FakeSmtp  # noqa: E402

USER, PW = "box@example.invalid", "fake-app-pw-7741"


class Email(unittest.TestCase):
    def setUp(self):
        self.smtp = FakeSmtp(USER, PW)
        self.d = tempfile.mkdtemp()
        self.now, self.sent, self.ha_fail = 1000.0, [], None
        self.a = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None, send=self.ha_send,
                               clock=lambda: self.now, hostname=lambda: "box-host")

    def tearDown(self):
        self.smtp.close()

    def ha_send(self, url, ev):
        if self.ha_fail:
            return self.ha_fail
        self.sent.append(ev)

    def mail(self, **kw):
        e = {"host": "127.0.0.1", "port": self.smtp.port, "security": "none", "user": USER, "password": PW, "from": "alerts@example.invalid",
             "to": "me@example.invalid, other@example.invalid"}
        e.update(kw)
        return self.a.set({"enabled": True, "delaySeconds": 0, "email": e})

    def go(self, s, secs=0):
        self.now += secs
        self.a.observe(s, self.now); self.a.flush(self.now)

    NODES = [node("a", "Anchor3")]

    def test_a_problem_and_its_recovery_are_emailed_to_every_address(self):
        self.mail()
        self.go(snap(self.NODES, a=False))
        self.assertEqual(len(self.smtp.messages), 1)
        m = self.smtp.messages[0]
        self.assertEqual(sorted(m["to"]), ["me@example.invalid", "other@example.invalid"])
        self.assertIn("Subject: box-host: Anchor3 is down", m["text"])
        self.go(snap(self.NODES, a=True), 1); self.go(snap(self.NODES, a=True), 60)
        self.assertIn("is back", self.smtp.messages[-1]["text"])

    def test_the_time_in_the_email_is_in_the_boxs_time_zone_not_utc(self):
        """Regression: alert emails said Time: 2026-10-25T18:36:49Z whatever time zone the box was set to."""
        import calendar
        old = os.environ.get("TZ")
        def restore():
            if old is None: os.environ.pop("TZ", None)
            else: os.environ["TZ"] = old
            time.tzset()
        self.addCleanup(restore)
        os.environ["TZ"] = "America/Chicago"; time.tzset()
        self.now = calendar.timegm((2026, 10, 25, 18, 36, 49))
        self.mail()
        self.go(snap(self.NODES, a=False))
        text = self.smtp.messages[0]["text"]
        self.assertIn("Time: Oct 25 at 1:36 PM CDT", text)
        self.assertNotIn("18:36", text)
        self.assertEqual(alerts._local("not a time"), "not a time", "unreadable text is left alone")

    def test_phone_alerts_say_the_time_at_the_site_as_well(self):
        """The phone shows when it received the alert; the message says what time it was at the site, so nobody has to do the sums."""
        old = os.environ.get("TZ")
        def restore():
            if old is None: os.environ.pop("TZ", None)
            else: os.environ["TZ"] = old
            time.tzset()
        self.addCleanup(restore)
        os.environ["TZ"] = "America/Chicago"; time.tzset()
        ev = {"id": "n1", "event": "problem", "state": "failed", "site": "Riverside", "title": "Anchor3 is down", "message": "Anchor3 stopped answering.", "at": "2026-10-25T18:36:49Z"}
        out = alerts.Alerts._ha_payload(ev)
        self.assertEqual(out["message"], "Anchor3 stopped answering. (1:36 PM CDT at Riverside)")
        self.assertEqual(ev["at"], "2026-10-25T18:36:49Z", "the event keeps its UTC time")
        self.assertEqual(alerts.Alerts._ha_payload(dict(ev, at="junk"))["message"], "Anchor3 stopped answering.")

    def test_the_password_never_leaves_the_box_and_a_save_without_one_keeps_it(self):
        out = self.mail()
        self.assertNotIn(PW, json.dumps(out))
        self.assertTrue(out["email"]["passwordSet"])
        out = self.a.set({"email": {"to": "me@example.invalid"}})                   # no password in this save
        self.assertTrue(out["email"]["passwordSet"])
        self.go(snap(self.NODES, a=False))
        self.assertEqual(len(self.smtp.messages), 1)                                # the kept password still logs in
        self.assertEqual(os.stat(os.path.join(self.d, "alerts.json")).st_mode & 0o777, 0o600)

    def test_a_wrong_password_is_said_plainly_and_the_message_keeps_waiting(self):
        self.mail(password="fake-wrong-pw-0001")
        r = self.a.test()
        self.assertFalse(r["ok"]); self.assertIn("refused the user name or password", r["message"]); self.assertNotIn("fake-wrong-pw-0001", r["message"])
        self.go(snap(self.NODES, a=False))
        self.assertEqual((len(self.smtp.messages), len(self.a.outbox)), (0, 1))
        self.a.set({"email": {"password": PW}})                                      # fixed: the waiting message goes out
        self.go(snap(self.NODES, a=False), 60)
        self.assertEqual((len(self.smtp.messages), len(self.a.outbox)), (1, 0))

    def test_gmail_gets_the_app_password_hint(self):
        why = mailer._why(smtplib.SMTPAuthenticationError(535, b"x"), {"host": "smtp.gmail.com", "port": 587, "from": "a@b.c"})
        self.assertIn("app password", why)

    def test_email_and_home_assistant_both_get_it_and_neither_gets_it_twice(self):
        self.mail()
        self.a.set({"homeAssistant": {"webhook": "http://ha.example.invalid:8123/api/webhook/fake-hook-id-9"}})
        self.ha_fail = "Home Assistant is unreachable"
        self.go(snap(self.NODES, a=False))
        self.assertEqual((len(self.smtp.messages), len(self.sent)), (1, 0))          # email went; HA is waiting
        self.ha_fail = None
        self.go(snap(self.NODES, a=False), 30)
        self.assertEqual((len(self.smtp.messages), len(self.sent)), (1, 1))          # HA caught up; the email was not repeated
        self.assertEqual(len(self.a.outbox), 0)

    def test_the_test_button_reports_each_way_separately(self):
        self.mail()
        r = self.a.test()
        self.assertTrue(r["ok"], r); self.assertIn("Email sent to me@example.invalid, other@example.invalid", r["message"])
        self.assertEqual(len(self.smtp.messages), 1)

    def test_bad_settings_are_explained_and_remove_forgets_everything(self):
        for e in ({"to": "not-an-address"}, {"port": "abc"}, {"security": "tls13"}, {"from": "a b@c.d"}, {"host": "smtp .x"}):
            with self.assertRaises(alerts.Invalid):
                self.a.set({"email": e})
        self.mail()
        out = self.a.set({"email": {"clear": True}})
        self.assertFalse(out["email"]["set"]); self.assertFalse(out["email"]["passwordSet"]); self.assertFalse(out["enabled"])   # last way to send removed

    def test_email_alone_is_enough_to_turn_alerts_on(self):
        with self.assertRaises(alerts.Invalid):
            self.a.set({"enabled": True})
        self.assertTrue(self.mail()["enabled"])


if __name__ == "__main__":
    unittest.main()
