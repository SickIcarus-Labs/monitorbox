"""UniFi end to end: real launcher, App and unifi module against a fake controller. Re-detect lists the devices,
Watch puts them in a UniFi node in the Network group, a dead switch reads Degraded, an unreachable controller
reads Unknown, and nothing but a login and reads ever reaches the controller."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402
from unifi_fake import Controller  # noqa: E402


class UnifiE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_devices_through_re_detect_watch_and_a_dead_switch(self):
        ctl = Controller()
        self.addCleanup(ctl.close)
        ctl.networks[3]["enabled"] = True                      # Ferndale (paused in the fake) is up for this test
        ctl.connections.append({"network_id": "t3", "status": "connected"})
        c = self.start()
        self.configure(c, [{"id": "unifi", "module": "unifi-network", "base_url": ctl.url, "username": ctl.username, "password": ctl.password, "timeout": 1}],
                       [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": self.port}]}])
        found = c.post("/api/detect", {"connection": "unifi"})
        self.assertIn("UniFi Garage", [s["label"] for s in found["suggest"]])
        self.assertIn("UniFi VPN Tidewater", [s["label"] for s in found["suggest"]])
        rev = c.post("/api/watch", {"connection": "unifi", "items": [
            {k: s[k] for k in ("label", "check", "params", "node", "group", "rule")} for s in found["suggest"]]})
        self.assertEqual(rev["added"], len(found["suggest"]))
        self.states(c, {"unifi": "healthy", "pi": "healthy"})
        cards = {x["name"]: x for x in c.get("/api/status")["cards"]}
        self.assertIn("Network", cards)
        # one switch dies: the node is Degraded (rule 'any'), not Failed
        ctl.devices[3]["state"] = 0
        self.states(c, {"unifi": "degraded"})
        ctl.devices[3]["state"] = 1
        self.states(c, {"unifi": "healthy"})
        # a tunnel drops: the UniFi node is Degraded and the sidebar says which one
        ctl.connections[1]["status"] = "disconnected"
        n = self.states(c, {"unifi": "degraded"})
        self.assertIn("Tidewater", str(n["unifi"]))
        ctl.connections[1]["status"] = "connected"
        self.states(c, {"unifi": "healthy"})
        # the controller goes away: cannot be checked, not failed
        ctl.close()
        self.states(c, {"unifi": "unknown"}, timeout=60)
        self.assertEqual(c.get("/api/status")["banner"]["status"], "blue")
        # Nothing but reads: the login, and (since 0.76.0, when the Busiest client began counting wifi clients) the flow log's search, which is a POST that only asks a question.
        self.assertLessEqual({r for r in ctl.requests if r[0] != "GET"}, {("POST", "/api/auth/login"), ("POST", "/proxy/network/v2/api/site/default/traffic-flows")})
        self.assertIn(("POST", "/api/auth/login"), ctl.requests)


if __name__ == "__main__":
    unittest.main()
