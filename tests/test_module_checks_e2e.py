"""A module supplies checks, end to end through the real launcher and App (hello is the reference module).
Covers every way a check can end, that the right connection's secret reaches the module, and the editor's
masking. A module problem must read 'cannot be checked' (blue), never 'down'."""
import json, os, secrets, sys, time, unittest

import test_e2e as base

Client, wait = base.Client, base.wait
PASSWORD = "correct horse"


def node(i, name, **check):
    return {"id": i, "name": name, "group": "Services", "checks": [{"type": "module", "module": "hello", "connection": "c1", **check}]}


class ModuleChecks(unittest.TestCase):
    setUp, tearDown = base.E2E.setUp, base.E2E.tearDown
    write_json, read_json = staticmethod(base.E2E.write_json), staticmethod(base.E2E.read_json)
    publish, health_version, mod_version = base.E2E.publish, base.E2E.health_version, base.E2E.mod_version

    def start(self, **env):
        self.publish(app="0.7.0", hello="0.3.0")
        os.environ.update({k: v for k, v in env.items()})
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in env])
        base.E2E.start_launcher(self)
        c = Client(self.port)
        wait(lambda: c.get("/api/health")["version"], what="App up")
        self.assertTrue(c.post("/api/setup", {"password": PASSWORD})["ok"])
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])
        wait(lambda: self.mod_version(c) == "0.3.0", what="hello module running")
        return c

    def conns(self, c, conns):
        rev = c.get("/api/config/connections")["revision"]
        return c.post("/api/config/connections", {"connections": conns, "revision": rev})

    def mon(self, c, nodes):
        rev = c.get("/api/config/monitoring")["revision"]
        out = c.post("/api/config/monitoring", {"monitoring": {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": nodes}, "revision": rev})
        self.assertIn("revision", out, out)

    def states(self, c, want):
        def look():
            n = c.get("/api/status")["nodes"]
            return n if all(n[k]["state"] == v for k, v in want.items()) else None
        return wait(look, timeout=30, what=f"states {want}")

    def test_every_way_a_check_can_end(self):
        c = self.start()
        self.conns(c, [{"id": "c1", "module": "hello", "host": "192.0.2.1", "password": "fake-pw-" + secrets.token_hex(4)}])
        self.mon(c, [node("up", "Up", params={"state": "healthy"}),
                     node("warn", "Warn", params={"state": "degraded", "detail": "on battery"}),
                     node("down", "Down", params={"state": "failed", "detail": "no answer from the device"}),
                     node("unk", "Unknown", params={"state": "unknown", "detail": "login refused"}),
                     node("err", "Library error", params={"raise": True}),
                     {"id": "gone", "name": "No such module", "group": "Services",
                      "checks": [{"type": "module", "module": "nosuch"}]}])
        n = self.states(c, {"up": "healthy", "warn": "degraded", "down": "failed", "unk": "unknown", "err": "unknown", "gone": "unknown"})
        self.assertEqual(n["warn"]["detail"], "on battery")
        self.assertIn("not running", n["gone"]["detail"])
        self.assertIn("simulated device library error", n["err"]["detail"])   # shown, but as 'cannot be checked'
        self.assertEqual(c.get("/api/status")["banner"]["status"], "red")      # down + degraded, nothing critical: an actual down is red

    def test_a_module_that_crashes_reads_unknown_and_comes_back(self):
        c = self.start(MB_MODULE_RETRY_SECONDS="1")
        self.conns(c, [{"id": "c1", "module": "hello"}])
        self.mon(c, [node("a", "A", params={"crash": True}), node("b", "B", params={"state": "healthy"}, interval=2)])
        self.states(c, {"a": "unknown"})
        self.states(c, {"b": "healthy"})   # revived within a few seconds, the other check works again
        self.assertEqual(c.get("/api/status")["banner"]["status"], "blue")

    def test_the_right_connections_secret_reaches_the_module(self):
        c = self.start()
        pws = {i: f"fake-{i}-{secrets.token_hex(6)}" for i in ("c1", "c2", "c3")}
        self.conns(c, [{"id": i, "module": "hello", "password": pw} for i, pw in pws.items()])
        self.mon(c, [{"id": f"n-{i}", "name": i, "group": "Services",
                      "checks": [{"type": "module", "module": "hello", "connection": i, "params": {"echo": "password"}}]}
                     for i in pws])
        n = self.states(c, {"n-c1": "healthy", "n-c2": "healthy", "n-c3": "healthy"})
        for i, pw in pws.items():
            got = json.loads(n[f"n-{i}"]["checks"][0]["detail"])
            self.assertEqual(got["value"], pw, f"{i} received another connection's password")
            self.assertEqual(got["fields"], ["id", "module", "password"])

    def test_two_connections_may_genuinely_share_a_credential(self):
        c = self.start()
        shared = "fake-shared-" + secrets.token_hex(6)
        self.conns(c, [{"id": "a3", "module": "hello", "authKey": shared}, {"id": "granite", "module": "hello", "authKey": shared}])
        self.mon(c, [{"id": f"n-{i}", "name": i, "group": "Services",
                      "checks": [{"type": "module", "module": "hello", "connection": i, "params": {"echo": "authKey"}}]} for i in ("a3", "granite")])
        n = self.states(c, {"n-a3": "healthy", "n-granite": "healthy"})
        self.assertEqual({json.loads(n[k]["checks"][0]["detail"])["value"] for k in n if k.startswith("n-")}, {shared})

    def test_the_editor_never_sees_secrets_and_keeps_them_on_save(self):
        c = self.start()
        pw = "fake-pw-" + secrets.token_hex(6)
        self.conns(c, [{"id": "c1", "module": "hello", "password": pw, "host": "192.0.2.1"}])
        shown = c.get("/api/config/connections")
        self.assertNotIn(pw, json.dumps(shown))
        shown["connections"][0]["host"] = "192.0.2.77"
        self.assertIn("revision", c.post("/api/config/connections", shown))
        with open(os.path.join(self.cfg, "config", "monitorbox.json")) as f:
            stored = json.load(f)["connections"][0]
        self.assertEqual((stored["password"], stored["host"]), (pw, "192.0.2.77"))
        # a check pointing at a connection that does not exist is refused, and so is deleting one that is in use
        rev = c.get("/api/config/monitoring")["revision"]
        bad = c.post("/api/config/monitoring", {"revision": rev, "monitoring": {"builtinInternet": False, "nodes": [node("x", "X", connection="zzz")]}})
        self.assertEqual(bad["_status"], 400)
        self.mon(c, [node("x", "X")])
        crev = c.get("/api/config/connections")["revision"]
        gone = c.post("/api/config/connections", {"connections": [], "revision": crev})
        self.assertEqual(gone["_status"], 400)
        # but "Remove this service" never refuses: its checks go with it
        out = c.post("/api/config/connection/remove", {"id": c.get("/api/config/connections")["connections"][0]["id"]})
        self.assertEqual(out["removed"], ["x"])
        self.assertEqual(c.get("/api/config/connections")["connections"], [])
        self.assertEqual(c.post("/api/config/connection/remove", {"id": "nope"})["_status"], 400)


if __name__ == "__main__":
    unittest.main()
