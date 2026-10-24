"""Offering new things to watch from every connection (#183): what each connection can see is asked for in the background, compared with what is
watched, and only things that appear after the first look are proposed. Two real Apps are not needed: one App with a scripted module."""
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import test_sites as TS


class Sweep(unittest.TestCase):
    def setUp(self):
        self.box = TS.Box(self, "fake-sweep-pw-31")
        self.offer = [{"label": "Volume /", "check": "volume", "params": {"mount": "/"}, "node": None, "group": "Servers"}]
        self.up = True
        outer = self

        def call(mid, method, params, timeout=10):
            if method != "discover":
                raise RuntimeError("not used here")
            if not outer.up:
                raise RuntimeError("the snmp module is not running")
            return {"suggest": [dict(x) for x in outer.offer]}
        self.box.app.modules.call = call
        rev = self.box.get("/api/config/connections")["revision"]
        sc, out = self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "nas", "name": "The NAS", "module": "snmp", "host": "192.0.2.50", "version": "2c", "community": "fake-comm-sweep"}]})
        self.assertEqual(sc, 200, out)

    def fu(self):
        return [x for x in self.box.get("/api/followups")["suggestions"] if x["kind"] == "new-items"]

    def sweep(self):
        self.box.app.sweep["at"] = 0.0
        self.box.get("/api/followups")                          # starts the background look
        for _ in range(100):
            if not self.box.app.sweep["running"] and self.box.app.sweep["at"]:
                return
            time.sleep(0.05)
        self.fail("the look did not finish")

    def test_the_first_look_is_taken_as_known_a_later_arrival_is_offered_and_accepting_watches_it(self):
        self.sweep()
        self.assertEqual(self.fu(), [], "what was there at the first look is not 'new'")
        self.offer.append({"label": "Pool tank", "check": "volume", "params": {"mount": "/tank"}, "node": None, "group": "Servers"})
        self.sweep()
        got = self.fu()
        self.assertEqual([(x["from"], x["labels"], x["how"]) for x in got], [("nas", ["Pool tank"], "items")])
        sc, r = self.box.post("/api/followups/add", {"id": got[0]["id"]})
        self.assertEqual(sc, 200, r); self.assertEqual(r["added"], 1)
        mon = self.box.get("/api/config/monitoring")["monitoring"]
        self.assertIn("pool-tank", [c["id"] for n in mon["nodes"] for c in n.get("checks", [])])
        self.assertEqual(self.fu(), [], "watched now, so not offered again")

    def test_dismissing_remembers_those_items_and_only_later_ones_come_back(self):
        self.sweep()
        self.offer.append({"label": "Pool a", "check": "volume", "params": {"mount": "/a"}, "node": None, "group": "Servers"}); self.sweep()
        first = self.fu()[0]
        self.assertEqual(self.box.post("/api/followups/dismiss", {"id": first["id"]})[0], 200)
        self.sweep(); self.assertEqual(self.fu(), [])
        self.offer.append({"label": "Pool b", "check": "volume", "params": {"mount": "/b"}, "node": None, "group": "Servers"}); self.sweep()
        self.assertEqual([x["labels"] for x in self.fu()], [["Pool b"]], "only the later arrival, not the dismissed one again")

    def test_a_connection_that_cannot_be_reached_proposes_nothing_and_keeps_what_it_had(self):
        self.sweep()
        self.offer.append({"label": "Pool tank", "check": "volume", "params": {"mount": "/tank"}, "node": None, "group": "Servers"}); self.sweep()
        self.assertEqual(len(self.fu()), 1)
        self.up = False; self.sweep()
        self.assertEqual(len(self.fu()), 1, "a silent source does not wipe or invent anything")


class SwitchSweep(unittest.TestCase):
    def setUp(self):
        self.box = TS.Box(self, "fake-switch-pw-47")
        self.answers = {"192.0.2.21": "Core 10G", "192.0.2.23": "Rack Two"}       # the switch at .22 refuses the login
        self.probed = []
        outer = self

        def call(mid, method, params, timeout=10):
            c = params.get("connection") or {}
            if method == "discover" and mid == "unifi-network":
                return {"suggest": [], "devices": [
                    {"name": "Core Gate", "type": "udm", "ip": "192.0.2.1"}, {"name": "Core 10G", "type": "usw", "ip": "192.0.2.21"},
                    {"name": "Edge A", "type": "usw", "ip": "192.0.2.22"}, {"name": "Roof AP", "type": "uap", "ip": "192.0.2.31"}, {"name": "Rack Two", "type": "usw", "ip": "192.0.2.23"}]}
            if method == "discover":
                return {"suggest": []}
            if method == "probe":
                outer.probed.append((c.get("host"), c.get("community")))
                return {"ok": True, "sysName": outer.answers[c["host"]]} if c.get("host") in outer.answers and c.get("community") == "fake-comm-gate" else {"ok": False, "error": "no answer"}
            raise RuntimeError("not used here")
        self.box.app.modules.call = call
        rev = self.box.get("/api/config/connections")["revision"]
        sc, out = self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "unifi", "name": "UniFi", "module": "unifi-network", "host": "192.0.2.1", "username": "fake-user-sw", "password": "fake-pass-sw"},
            {"id": "gate", "name": "Gateway", "module": "snmp", "host": "192.0.2.1", "version": "2c", "community": "fake-comm-gate"},
            {"id": "nas", "name": "The NAS", "module": "snmp", "host": "192.0.2.50", "version": "2c", "community": "fake-comm-nas"}]})
        self.assertEqual(sc, 200, out)

    def offers(self):
        self.box.app.sweep["at"] = 0.0
        self.box.get("/api/followups")
        for _ in range(100):
            if not self.box.app.sweep["running"] and self.box.app.sweep["at"]:
                break
            time.sleep(0.05)
        for _ in range(100):                                          # the switches are tried in the background after the look; the page is told to ask again
            r = self.box.get("/api/followups")
            if not r["pending"] and not self.box.app.sw_cache["running"]:
                return [x for x in r["suggestions"] if x["kind"] == "snmp-switches"]
            time.sleep(0.05)
        self.fail("the switches were not tried")

    def test_switches_that_answer_the_gateways_login_are_offered_and_nothing_is_added_until_the_owner_says_so(self):
        got = self.offers()
        self.assertEqual(len(got), 1); x = got[0]
        self.assertEqual([(s["name"], s["ip"]) for s in x["switches"]], [("Core 10G", "192.0.2.21"), ("Rack Two", "192.0.2.23")], "the one that refused, the AP and the gateway are not offered")
        self.assertEqual({c for _h, c in self.probed}, {"fake-comm-gate"}, "only the gateway's login was tried, never the NAS's")
        self.assertNotIn("fake-comm-gate", str(self.box.get("/api/followups")), "the login never reaches the browser")
        ids = lambda: [c["id"] for c in self.box.get("/api/config/connections")["connections"]]
        self.assertEqual(ids(), ["unifi", "gate", "nas"], "offered, not added")
        sc, r = self.box.post("/api/followups/add", {"id": x["id"]})
        self.assertEqual(sc, 200, r); self.assertEqual(r["added"], 2)
        self.assertEqual(ids(), ["unifi", "gate", "nas", "snmp-core-10g", "snmp-rack-two"])
        from monitorbox_app import monconfig
        full = {c["id"]: c for c in monconfig.load_config(self.box.app.paths)["connections"]}
        for cid, ip, nm in (("snmp-core-10g", "192.0.2.21", "Core 10G"), ("snmp-rack-two", "192.0.2.23", "Rack Two")):
            self.assertEqual((full[cid]["host"], full[cid]["name"], full[cid]["version"], full[cid]["community"], full[cid]["module"]), (ip, nm, "2c", "fake-comm-gate", "snmp"))
        self.assertEqual(self.offers(), [], "connected now, so not offered again")

    def test_dismissing_hides_the_offer_and_a_second_snmp_login_with_no_match_is_never_tried(self):
        x = self.offers()[0]
        self.assertEqual(self.box.post("/api/followups/dismiss", {"id": x["id"]})[0], 200)
        self.assertEqual(self.offers(), [])
        # no SNMP login sits on the gateway or the console any more, and there are two: nothing may be guessed
        rev = self.box.get("/api/config/connections")["revision"]
        sc, out = self.box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "unifi", "name": "UniFi", "module": "unifi-network", "host": "192.0.2.1", "username": "fake-user-sw", "password": "fake-pass-sw"},
            {"id": "nas", "name": "The NAS", "module": "snmp", "host": "192.0.2.50", "version": "2c", "community": "fake-comm-nas"},
            {"id": "nas2", "name": "Other", "module": "snmp", "host": "192.0.2.51", "version": "2c", "community": "fake-comm-nas2"}]})
        self.assertEqual(sc, 200, out)
        self.probed.clear()
        self.assertEqual(self.offers(), []); self.assertEqual(self.probed, [])


if __name__ == "__main__":
    unittest.main()


class PortainerOfferNames(unittest.TestCase):
    """End to end: new containers a Portainer server reports for another machine are offered under that machine's name, not the Portainer server's
    (found only by running the real path: the unit tests had one container, the real offer has several)."""
    ENV = "Fake Site - Fake Runner"

    def run_case(self, address, edge):
        box = TS.Box(self, "fake-offer-pw-58")
        item = lambda n: {"label": f"Container {n} on {self.ENV}", "check": "container", "params": {"env": self.ENV, "name": n}, "env": self.ENV,
                          "service": {"title": n, "env": self.ENV, "container": n}, "node": f"{n} ({self.ENV})", "group": "Services"}
        offer = [item("fake-old")]
        box.app.modules.call = lambda mid, method, params, timeout=10: (
            {"environments": [{"name": self.ENV, "address": address, "edge": edge}], "suggest": [dict(x) for x in offer]} if mid == "portainer" else {"suggest": []})
        rev = box.get("/api/config/connections")["revision"]
        sc, out = box.post("/api/config/connections", {"revision": rev, "connections": [
            {"id": "gol", "name": "Fake Portainer Box", "module": "portainer", "base_url": "https://192.0.2.50:9443", "token": "fake-tok-offer"},
            {"id": "run", "name": "Fake Runner", "module": "snmp", "host": "192.0.2.60", "version": "2c", "community": "fake-comm-offer"}]})
        self.assertEqual(sc, 200, out)

        def sweep():
            box.app.pt_cache.clear(); box.app.sweep["at"] = 0.0; box.get("/api/followups")
            for _ in range(200):
                if not box.app.sweep["running"] and box.app.sweep["at"]:
                    return
                time.sleep(0.05)
        sweep(); offer.extend([item("fake-new-1"), item("fake-new-2")]); sweep()
        return [(x["title"], x["on"]) for x in box.get("/api/followups")["suggestions"] if x["kind"] == "new-items"]

    def test_by_address_and_for_an_edge_agent_with_none(self):
        self.assertEqual(self.run_case("192.0.2.60", False), [("2 new things on Fake Runner", "Fake Runner")])
        self.assertEqual(self.run_case("", True), [("2 new things on Fake Runner", "Fake Runner")], "matched by the server's name appearing in the environment's")
