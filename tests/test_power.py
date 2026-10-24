"""Power links: which UPS powers which system. Guessed from the UPS server's client list, overridden by the owner, applied by the engine."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import monconfig, monitor  # noqa: E402
from nut_fake import Upsd  # noqa: E402
from test_nut import ups, M as NUT  # noqa: E402
import test_sites as TS  # noqa: E402


def sysnode(i, name, target, **kw):
    return {"id": i, "name": name, "group": "Servers", "rule": "primary", "checks": [{"id": "ping", "type": "ping", "target": target}], **kw}


UPS_NODE = {"id": "ups-networkups", "name": "UPS networkups", "group": "Power", "rule": "primary",
            "checks": [{"id": "ups", "type": "module", "module": "nut", "connection": "nut-1", "check": "ups", "params": {"ups": "networkups"}}]}


class Config(unittest.TestCase):
    def test_powered_by_is_kept_checked_and_an_empty_list_is_an_answer(self):
        nodes = [UPS_NODE, sysnode("a", "A", "192.0.2.41", poweredBy=["ups-networkups"]), sysnode("b", "B", "192.0.2.42", poweredBy=[])]
        out, errs = monconfig.validate({"nodes": nodes}, {"nut-1"})
        self.assertEqual(errs, [])
        by = {n["id"]: n for n in out}
        self.assertEqual((by["a"]["poweredBy"], by["b"]["poweredBy"]), (["ups-networkups"], []))
        self.assertNotIn("poweredBy", by["ups-networkups"])
        _, errs = monconfig.validate({"nodes": [UPS_NODE, sysnode("a", "A", "192.0.2.41", poweredBy=["nosuch"])]}, {"nut-1"})
        self.assertTrue(any("poweredBy 'nosuch' does not exist" in e for e in errs), errs)
        _, errs = monconfig.validate({"nodes": [sysnode("a", "A", "192.0.2.41", poweredBy=["a"])]}, set())
        self.assertTrue(any("cannot be powered by itself" in e for e in errs), errs)
        _, errs = monconfig.validate({"nodes": [sysnode("a", "A", "192.0.2.41", poweredBy="ups")]}, set())
        self.assertTrue(any("poweredBy must be a list" in e for e in errs), errs)


UPS_TWO = {**UPS_NODE, "id": "ups-serverups", "name": "UPS serverups", "checks": [{**UPS_NODE["checks"][0], "params": {"ups": "serverups"}}]}


class Guess(unittest.TestCase):
    def box(self, clients, other=None):
        d = Upsd({"networkups": ups(), "serverups": ups()}, clients={"networkups": clients, "serverups": other or []})
        self.addCleanup(d.close)
        box = TS.Box(self, "fake-power-pw-93")
        box.app.lansampler.stopping.set()
        real = box.app.modules.call
        box.app.modules.call = lambda mod, meth, params, t=10: NUT.handle({"method": meth, "params": params}) if mod == "nut" else real(mod, meth, params, t)     # the nut module's own code, run in this process
        rev = box.get("/api/config/connections")["revision"]
        box.post("/api/config/connections", {"revision": rev, "connections": [{"id": "nut-1", "module": "nut", "host": "127.0.0.1", "port": d.port, "timeout": 1},
            {"id": "snmp-mon", "module": "snmp", "host": "192.0.2.34", "port": 161, "version": "2c", "community": "fake-comm-7714", "timeout": 1, "retries": 0}]})
        mon = box.get("/api/config/monitoring")
        nodes = [UPS_NODE, UPS_TWO, sysnode("nas", "Server-Nas", "192.0.2.31"), sysnode("mini", "Mini-Two", "192.0.2.32"), sysnode("local", "Nut-Host", "127.0.0.1"),
                 sysnode("twin-1", "Twin One", "192.0.2.33"), sysnode("twin-2", "Twin Two", "192.0.2.33"),
                 sysnode("mon-ping", "Monitor ping", "192.0.2.34"),
                 {"id": "mon-snmp", "name": "Monitor", "group": "Servers", "rule": "primary", "checks": [{"id": "up", "type": "module", "module": "snmp", "connection": "snmp-mon", "check": "reachable"}]}]
        box.post("/api/config/monitoring", {"revision": mon["revision"], "monitoring": {**mon["monitoring"], "nodes": nodes}})
        return box, d

    def test_a_client_that_is_exactly_one_watched_system_is_guessed_and_the_nut_hosts_own_machine_is_127_0_0_1(self):
        box, d = self.box(["192.0.2.31", "127.0.0.1", "192.0.2.99", "192.0.2.33", "192.0.2.34"])
        r = box.get("/api/power?refresh=1")
        self.assertEqual([u["id"] for u in r["ups"]], ["ups-networkups", "ups-serverups"])
        on = {x["id"]: (x["ups"], x["from"]) for x in r["systems"]}
        self.assertEqual({k: v for k, v in on.items() if v[0]}, {"nas": ("ups-networkups", "guess"), "local": ("ups-networkups", "guess"), "mon-snmp": ("ups-networkups", "guess")},
                         "an address nobody watches, and one two systems share, are not guessed; the system with the SNMP login is the server's own")
        self.assertIn("mon-ping", on, "a system watched only by ping is listed too, so it can be ticked")
        self.assertNotIn("ups-networkups", on)
        self.assertEqual(box.app.monitor.power_guess, {"nas": ["ups-networkups"], "local": ["ups-networkups"], "mon-snmp": ["ups-networkups"]})
        self.assertTrue(d.commands and all(c.startswith("LIST CLIENT ") for c in d.commands), d.commands)

    def test_a_server_that_will_not_say_is_a_note_not_a_failure(self):
        box, d = self.box(["192.0.2.31"])
        d.drop = True
        r = box.get("/api/power?refresh=1")
        self.assertEqual(([x for x in r["systems"] if x["ups"]], len(r["notes"])), ([], 2))

    def test_it_needs_a_sign_in(self):
        import urllib.request, urllib.error
        box = TS.Box(self, "fake-power-pw-94")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{box.port}/api/power")
        self.assertEqual(e.exception.code, 401)

    def test_two_ups_both_claiming_a_system_is_not_a_guess(self):
        box, d = self.box(["192.0.2.31", "192.0.2.32"], other=["192.0.2.31"])
        on = {x["id"]: x["ups"] for x in box.get("/api/power?refresh=1")["systems"]}
        self.assertEqual((on["nas"], on["mini"]), (None, "ups-networkups"), "nas is claimed by both UPSes: nothing is guessed; mini is claimed by one")

    def test_a_link_to_another_site_is_not_a_machine_that_a_ups_can_power(self):
        box, d = self.box([])
        mon = box.get("/api/config/monitoring")
        link = {"id": "site-tb", "name": "Tidewater link", "group": "Sites", "rule": "primary", "checks": [{"id": "link", "type": "site", "site": "tb"}]}
        names = lambda: {x["name"] for x in box.get("/api/power")["systems"]}
        self.assertIn("Mini-Two", names())
        st, out = box.post("/api/config/monitoring", {"revision": mon["revision"], "monitoring": {**mon["monitoring"], "nodes": mon["monitoring"]["nodes"] + [link]}})
        self.assertEqual(st, 200, out)
        self.assertIn("Tidewater link", {n["name"] for n in box.get("/api/config/monitoring")["monitoring"]["nodes"]})
        self.assertNotIn("Tidewater link", names())

    def test_the_owner_puts_a_system_on_one_ups_moves_it_and_takes_it_off(self):
        box, d = self.box(["192.0.2.31"])
        box.get("/api/power?refresh=1")
        node = lambda i: next(n for n in box.get("/api/config/monitoring")["monitoring"]["nodes"] if n["id"] == i)
        find = lambda r, i: next(x for x in r["systems"] if x["id"] == i)
        r = box.post("/api/power", {"system": "mini", "ups": "ups-serverups"})[1]
        self.assertEqual((find(r, "mini")["ups"], find(r, "mini")["from"], node("mini")["poweredBy"]), ("ups-serverups", "set", ["ups-serverups"]))
        r = box.post("/api/power", {"system": "mini", "ups": "ups-networkups"})[1]
        self.assertEqual(node("mini")["poweredBy"], ["ups-networkups"], "one UPS at a time: moving replaces")
        r = box.post("/api/power", {"system": "nas", "ups": None})[1]
        self.assertEqual((find(r, "nas")["ups"], node("nas")["poweredBy"]), (None, []), "unticking a guess is an answer: it stops the guess")
        self.assertEqual(box.post("/api/power", {"system": "mini", "ups": "nosuch"})[0], 400)

    def test_the_power_page_lists_by_ups_and_a_ticked_system_leaves_the_other_lists(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright not installed")
        box, d = self.box(["192.0.2.34"])
        box.get("/api/power?refresh=1")
        mine = lambda: next(n for n in box.get("/api/config/monitoring")["monitoring"]["nodes"] if n["id"] == "mon-snmp")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 1400})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", box.pw); pg.keyboard.press("Enter"); pg.wait_for_selector(".card, .box")
            pg.goto(f"http://127.0.0.1:{box.port}/#/settings/power"); pg.wait_for_selector("#pwset input[type=checkbox]")
            self.assertIn("best guess", pg.inner_text("#pwset"))
            first = pg.locator("#pwset label:has-text(\"Monitor ·\") input[type=checkbox]").first
            self.assertTrue(first.is_checked(), "pre-ticked where the box is confident")
            first.uncheck(); pg.wait_for_function("() => !document.getElementById('pwset').innerText.includes('best guess')", timeout=15000)
            self.assertEqual(mine()["poweredBy"], [])
            self.assertIn("Not on a backup yet", pg.inner_text("#pwset"), "an unticked system waits in one list, not under every UPS")
            pg.select_option("#pwset select[aria-label=\"Backup for Monitor\"]", "ups-serverups")
            for _ in range(40):
                if mine().get("poweredBy") == ["ups-serverups"]:
                    break
                __import__("time").sleep(0.25)
            self.assertEqual(mine()["poweredBy"], ["ups-serverups"])
            pg.wait_for_function("() => !document.querySelector('#pwset select[aria-label=\"Backup for Monitor\"]')", timeout=15000)
            self.assertEqual(pg.locator("#pwset label:has-text(\"Monitor ·\")").count(), 1, "ticked under one UPS, it is offered nowhere else")
            self.assertEqual(errs, [])
            b.close()

    def test_a_portainer_environment_follows_the_machine_it_runs_on_and_is_not_offered(self):
        box, d = self.box(["192.0.2.32"])
        rev = box.get("/api/config/connections")
        box.post("/api/config/connections", {"revision": rev["revision"], "connections": rev["connections"] + [
            {"id": "pt-1", "module": "portainer", "host": "192.0.2.50", "port": 9443, "token": "fake-token-5521"}]})
        env = lambda i, n: {"id": i, "name": n + " Portainer", "group": "Services", "rule": "primary",
                            "checks": [{"id": "env", "type": "module", "module": "portainer", "connection": "pt-1", "check": "environment", "params": {"name": n}}]}
        mon = box.get("/api/config/monitoring")
        st, out = box.post("/api/config/monitoring", {"revision": mon["revision"], "monitoring": {**mon["monitoring"], "nodes": mon["monitoring"]["nodes"] + [
            env("env-mini", "Fake - Mini"), env("env-lost", "Fake - Nowhere")]}})
        self.assertEqual(st, 200, out)
        box.app.pt_cache["pt-1"] = {"at": __import__("time").time(), "out": {"environments": [
            {"name": "Fake - Mini", "address": "192.0.2.32", "edge": False, "up": True}, {"name": "Fake - Nowhere", "address": "192.0.2.77", "edge": False, "up": True}]}}
        r = box.get("/api/power?refresh=1")
        names = {x["name"] for x in r["systems"]}
        self.assertNotIn("Fake - Mini Portainer", names, "it follows Mini-Two, so there is nothing to tick")
        self.assertIn("Fake - Nowhere Portainer", names, "an environment no watched system answers for is still offered")
        self.assertEqual(r["follows"], [{"name": "Fake - Mini Portainer", "host": "Mini-Two"}])
        lost = next(x for x in r["systems"] if x["name"] == "Fake - Nowhere Portainer")
        self.assertEqual(lost["why"], "Portainer says it is at 192.0.2.77; no watched system is at that address.", "an entry that cannot follow says why")
        box.post("/api/power", {"system": "mini", "ups": "ups-serverups"})
        nodes = {n["id"]: n for n in box.app.monitor._eval_nodes()}
        self.assertEqual((nodes["mini"]["poweredBy"], nodes["env-mini"]["poweredBy"]), (["ups-serverups"], ["ups-serverups"]), "the environment has its machine's power")
        self.assertNotIn("poweredBy", nodes["env-lost"])

    def test_an_environment_says_why_it_is_not_matched_yet(self):
        box, d = self.box([])
        rev = box.get("/api/config/connections")
        box.post("/api/config/connections", {"revision": rev["revision"], "connections": rev["connections"] + [
            {"id": "pt-1", "module": "portainer", "host": "192.0.2.50", "port": 9443, "token": "fake-token-5522"}]})
        env = {"id": "env-x", "name": "Fake - X Portainer", "group": "Services", "rule": "primary",
               "checks": [{"id": "env", "type": "module", "module": "portainer", "connection": "pt-1", "check": "environment", "params": {"name": "Fake - X"}}]}
        mon = box.get("/api/config/monitoring")
        box.post("/api/config/monitoring", {"revision": mon["revision"], "monitoring": {**mon["monitoring"], "nodes": mon["monitoring"]["nodes"] + [env]}})
        why = lambda: next(x for x in box.get("/api/power?refresh=1")["systems"] if x["id"] == "env-x")["why"]
        self.assertTrue(why().startswith("Waiting for Portainer"))
        T = __import__("time").time()
        box.app.pt_cache["pt-1"] = {"at": T, "out": {"environments": [{"name": "Fake - X", "address": "", "edge": True}]}}
        self.assertTrue(why().startswith("An edge agent"))
        box.app.pt_cache["pt-1"] = {"at": T, "out": {"environments": [{"name": "Fake - X", "address": "192.0.2.33", "edge": False}]}}
        self.assertIn("2 watched systems share 192.0.2.33", why())
        box.app.pt_cache["pt-1"] = {"at": T, "out": {"environments": [{"name": "Other", "address": "192.0.2.33", "edge": False}]}}
        self.assertIn("does not list an environment called 'Fake - X'", why())

    def test_a_follower_takes_its_hosts_power_even_over_an_old_answer_of_its_own(self):
        m = monitor.Monitor.__new__(monitor.Monitor)
        m.nodes = [sysnode("host", "H", "x", poweredBy=["ups-a"]), sysnode("env", "E", "x", poweredBy=["ups-b"]), sysnode("bare", "B", "x"), sysnode("env2", "E2", "x", poweredBy=["ups-b"])]
        m.power_guess = {}
        m.power_follow = {"env": "host", "env2": "bare"}
        got = {n["id"]: n.get("poweredBy") for n in m._eval_nodes()}
        self.assertEqual(got, {"host": ["ups-a"], "env": ["ups-a"], "bare": None, "env2": ["ups-b"]}, "a host with no power link gives the follower nothing: its own answer stays")

    def test_a_guess_applies_only_where_the_owner_has_not_answered(self):
        m = monitor.Monitor.__new__(monitor.Monitor)
        m.nodes = [sysnode("a", "A", "x"), sysnode("b", "B", "x", poweredBy=[]), sysnode("c", "C", "x", poweredBy=["ups-networkups"]), sysnode("d", "D", "x")]
        m.power_guess = {"a": ["ups-networkups"], "b": ["ups-networkups"], "c": ["other"]}
        m.power_follow = {}
        got = {n["id"]: n.get("poweredBy") for n in m._eval_nodes()}
        self.assertEqual(got, {"a": ["ups-networkups"], "b": [], "c": ["ups-networkups"], "d": None}, "b said 'nothing' and c named its own: neither is overridden")


if __name__ == "__main__":
    unittest.main()
