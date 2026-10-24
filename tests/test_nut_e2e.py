"""NUT end to end: real launcher, App and nut module against a fake upsd. A UPS appears in its own Power
group, a power cut reads Degraded, a flat battery reads Failed, and an unreachable server reads Unknown."""
import os, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402
from nut_fake import Upsd  # noqa: E402
from test_nut import ups  # noqa: E402


class NutE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_ups_through_re_detect_watch_and_a_power_cut(self):
        d = Upsd({"networkups": ups(), "qnapups": ups(desc="QNAP UPS")})
        self.addCleanup(d.close)
        c = self.start()
        self.configure(c, [{"id": "monitor-nut", "module": "nut", "host": "127.0.0.1", "port": d.port, "timeout": 1}],
                       [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        found = c.post("/api/detect", {"connection": "monitor-nut"})
        self.assertEqual([s["params"]["ups"] for s in found["suggest"]], ["networkups", "qnapups"])
        rev = c.post("/api/watch", {"connection": "monitor-nut", "items": [
            {k: s[k] for k in ("label", "check", "params", "node", "group")} for s in found["suggest"]]})
        self.assertEqual(rev["added"], 2)
        n = self.states(c, {"ups-networkups": "healthy", "ups-qnapups": "healthy", "pi": "healthy"})
        self.assertIn("online", n["ups-networkups"]["checks"][0]["detail"])
        cards = {x["name"]: x for x in c.get("/api/status")["cards"]}
        self.assertIn("Power", cards)                                       # its own group, not under the Pi
        # the lights go out
        d.ups["networkups"] = ups("OB DISCHRG", 80, 30, 1500)
        self.states(c, {"ups-networkups": "degraded", "ups-qnapups": "healthy"})
        self.assertEqual(c.get("/api/status")["banner"]["status"], "yellow")
        d.ups["networkups"] = ups("OB LB", 8, 30, 90)
        self.states(c, {"ups-networkups": "failed"})
        self.assertEqual(c.get("/api/status")["banner"]["status"], "red")      # down, though not critical: red, without the alarm
        # the NUT server goes away: cannot be checked, not failed
        d.drop = True
        self.states(c, {"ups-networkups": "unknown", "ups-qnapups": "unknown"}, timeout=60)
        self.assertEqual(c.get("/api/status")["banner"]["status"], "blue")
        for cmd in d.commands:
            self.assertRegex(cmd, r"^(LIST UPS|LIST VAR \S+|LIST CLIENT \S+)$")

    def test_a_server_that_asks_for_a_login_is_read_with_the_saved_login_and_the_password_stays_hidden(self):
        d = Upsd({"networkups": ups()}, users={"fake-nut-user": "fake-nut-pass-9"})
        self.addCleanup(d.close)
        c = self.start()
        self.configure(c, [{"id": "monitor-nut", "module": "nut", "host": "127.0.0.1", "port": d.port, "timeout": 1,
                            "username": "fake-nut-user", "password": "fake-nut-pass-9"}],
                       [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        found = c.post("/api/detect", {"connection": "monitor-nut"})
        self.assertEqual([s["params"]["ups"] for s in found["suggest"]], ["networkups"])
        conn = [x for x in c.get("/api/config/connections")["connections"] if x["id"] == "monitor-nut"][0]
        self.assertEqual(conn["username"], "fake-nut-user"); self.assertNotIn("fake-nut-pass-9", str(conn), "the editor never sees the password")
        for cmd in d.commands:
            self.assertRegex(cmd, r"^(USERNAME \S+|PASSWORD \S+|LIST UPS|LIST VAR \S+|LIST CLIENT \S+)$")


if __name__ == "__main__":
    unittest.main()
