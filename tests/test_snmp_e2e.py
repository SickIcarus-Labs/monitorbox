"""SNMP end to end through the real launcher, App and snmp module, against a fake device.
Covers #10: the drive layout changes while MonitorBox is running and the check keeps reading the right volume."""
import json, os, secrets, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_e2e as base  # noqa: E402
import snmp_fake as F  # noqa: E402

Client, wait = base.Client, base.wait
PASSWORD = "correct horse"
HR, FIXED = "1.3.6.1.2.1.25.2.3.1", "1.3.6.1.2.1.25.2.1.4"


def rows(layout):
    mib = {}
    for i, name, used in layout:
        mib.update({f"{HR}.2.{i}": ("oid", FIXED), f"{HR}.3.{i}": name, f"{HR}.4.{i}": 4096, f"{HR}.5.{i}": 1000, f"{HR}.6.{i}": used})
    return mib


class SnmpE2E(unittest.TestCase):
    setUp, tearDown = base.E2E.setUp, base.E2E.tearDown
    write_json, read_json = staticmethod(base.E2E.write_json), staticmethod(base.E2E.read_json)
    publish, health_version, mod_version = base.E2E.publish, base.E2E.health_version, base.E2E.mod_version
    wait_all_modules = base.E2E.wait_all_modules

    def start(self):
        self.publish(app="0.12.0", hello="0.3.0")
        base.E2E.start_launcher(self)
        c = Client(self.port)
        wait(lambda: c.get("/api/health")["version"], what="App up")
        self.assertTrue(c.post("/api/setup", {"password": PASSWORD})["ok"])
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])
        wait(lambda: self.mod_version(c) == "0.3.0", what="modules running")
        self.wait_all_modules(c)
        return c

    def configure(self, c, conns, nodes):
        rev = c.get("/api/config/connections")["revision"]
        self.assertIn("revision", c.post("/api/config/connections", {"connections": conns, "revision": rev}))
        rev = c.get("/api/config/monitoring")["revision"]
        out = c.post("/api/config/monitoring", {"monitoring": {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": nodes}, "revision": rev})
        self.assertIn("revision", out, out)

    def states(self, c, want, timeout=40):
        def look():
            n = c.get("/api/status")["nodes"]
            return n if all(n[k]["state"] == v for k, v in want.items()) else None
        return wait(look, timeout=timeout, what=f"states {want}")

    def test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it(self):
        community, user_pw = "fake-comm-" + secrets.token_hex(4), "fake-v3-" + secrets.token_hex(6)
        old = F.Agent(community=community)
        v3 = F.Agent(users={"watcher": {"auth": "sha", "authpw": user_pw, "priv": True, "privpw": user_pw + "-priv"}})
        self.addCleanup(old.close); self.addCleanup(v3.close)
        old.mib = rows([(1, "/data", 100), (2, "/scratch", 990)])
        v3.mib = {"1.3.6.1.2.1.1.3.0": ("ticks", 123456), "1.3.6.1.2.1.1.5.0": "gateway"}
        chk = lambda cid, kind, **p: [{"type": "module", "module": "snmp", "connection": cid, "check": kind, "params": p, "interval": 2}]
        self.configure(c := self.start(), [
            {"id": "nas", "module": "snmp", "host": "127.0.0.1", "port": old.port, "version": "2c", "community": community, "timeout": 1, "retries": 0},
            {"id": "gw", "module": "snmp", "host": "127.0.0.1", "port": v3.port, "version": "3", "user": "watcher", "auth": "sha",
             "authPassword": user_pw, "priv": "aes", "privPassword": user_pw + "-priv", "timeout": 1, "retries": 0},
            {"id": "dead", "module": "snmp", "host": "127.0.0.1", "port": 9, "version": "2c", "community": "fake-none", "timeout": 0.3, "retries": 0}],
            [{"id": "data", "name": "Data volume", "group": "Servers", "checks": chk("nas", "volume", name="/data")},
             {"id": "gw", "name": "Gateway", "group": "Servers", "checks": chk("gw", "uptime")},
             {"id": "off", "name": "Unreachable", "group": "Servers", "checks": chk("dead", "uptime")}])
        n = self.states(c, {"data": "healthy", "gw": "healthy", "off": "unknown"})
        self.assertIn("10%", n["data"]["checks"][0]["detail"])
        self.assertEqual(c.get("/api/status")["banner"]["status"], "blue")      # cannot-check, never red
        # the layout changes under a running MonitorBox: the indexes swap
        old.mib = rows([(1, "/scratch", 990), (2, "/data", 100)])
        time.sleep(5)
        n = self.states(c, {"data": "healthy"})
        self.assertIn("10%", n["data"]["checks"][0]["detail"], "monitoring read the wrong volume after the indexes moved")
        # Re-detect shows the current names; the secret never comes back
        d = c.post("/api/detect", {"connection": "nas"})
        self.assertEqual(sorted(v["name"] for v in d["volumes"]), ["/data", "/scratch"])
        self.assertNotIn(community, json.dumps(d))
        self.assertIn("error", c.post("/api/detect", {"connection": "nope"}))

    def test_the_editor_masks_the_community_and_keeps_it_on_save(self):
        c = self.start()
        secret = "fake-comm-" + secrets.token_hex(5)
        rev = c.get("/api/config/connections")["revision"]
        c.post("/api/config/connections", {"connections": [{"id": "nas", "module": "snmp", "host": "192.0.2.5", "community": secret}], "revision": rev})
        got = c.get("/api/config/connections")
        self.assertNotIn(secret, json.dumps(got))
        c.post("/api/config/connections", {"connections": got["connections"], "revision": got["revision"]})
        self.assertEqual(self.read_json(os.path.join(self.cfg, "config", "monitorbox.json"))["connections"][0]["community"], secret)


if __name__ == "__main__":
    unittest.main()
