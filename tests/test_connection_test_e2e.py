"""Test connection, end to end: the settings typed into the form (not saved yet) are tried against a fake controller and a
fake SNMP device. A wrong password says so in words, a secret still shown as dots is filled in from the saved copy,
and no password ever comes back to the browser."""
import json, os, secrets, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402
import snmp_fake as F  # noqa: E402
from unifi_fake import Controller  # noqa: E402
from protect_fake import Console  # noqa: E402

MASK = "•" * 8


class ConnectionTestE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_the_form_can_try_a_device_before_it_is_saved(self):
        ctl = Controller(); self.addCleanup(ctl.close)
        agent_comm = "fake-comm-" + secrets.token_hex(4)
        agent = F.Agent(community=agent_comm); self.addCleanup(agent.close)
        agent.mib = T.rows([(1, "/data", 100), (2, "/scratch", 990)])
        c = self.start()
        good = {"id": "ctl", "module": "unifi-network", "base_url": ctl.url, "username": ctl.username, "password": ctl.password, "timeout": 1}
        out = c.post("/api/connections/test", {"connection": good})
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["found"], "says what it found")
        self.assertNotIn(ctl.password, json.dumps(out))
        # a wrong password is said in words
        bad_pw = "fake-wrong-" + secrets.token_hex(5)
        out = c.post("/api/connections/test", {"connection": {**good, "password": bad_pw}})
        self.assertFalse(out["ok"])
        self.assertIn("user name or password", out["error"])
        self.assertNotIn(bad_pw, json.dumps(out))
        # UniFi Protect: the cameras it can see come back as ready-made checks, and it never answers with the password
        cons = Console(); self.addCleanup(cons.close)
        cam = {"id": "nvr", "module": "unifi-protect", "base_url": cons.url, "username": cons.username, "password": cons.password, "timeout": 1}
        out = c.post("/api/connections/test", {"connection": cam})
        self.assertTrue(out["ok"], out)
        self.assertEqual({f["label"]: f["count"] for f in out["found"]}, {"Overview": 2, "Cameras": 3, "Drives": 2})
        self.assertNotIn(cons.password, json.dumps(out))
        out = c.post("/api/connections/test", {"connection": {**cam, "password": "fake-wrong-" + secrets.token_hex(5)}})
        self.assertFalse(out["ok"])
        # SNMP: the right community answers, a wrong one gets nothing back
        snmp = {"id": "box", "module": "snmp", "host": "127.0.0.1", "port": agent.port, "version": "2c", "community": agent_comm}
        out = c.post("/api/connections/test", {"connection": snmp})
        self.assertTrue(out["ok"], out)
        out = c.post("/api/connections/test", {"connection": {**snmp, "community": "fake-nope-" + secrets.token_hex(4)}})
        self.assertFalse(out["ok"])
        self.assertIn("Nothing answered", out["error"])
        # a secret shown as dots is filled in from the saved copy of the same connection...
        self.configure(c, [{**good}], [])
        out = c.post("/api/connections/test", {"connection": {**good, "password": MASK}})
        self.assertTrue(out["ok"], out)
        # ...but dots for a device that was never saved cannot be tested
        out = c.post("/api/connections/test", {"connection": {**snmp, "id": "unsaved", "community": MASK}})
        self.assertEqual(out["_status"], 400)
        self.assertEqual(c.post("/api/connections/test", {"connection": {"id": "x", "module": "unifi-network"}})["_status"], 400)   # no address


if __name__ == "__main__":
    unittest.main()
