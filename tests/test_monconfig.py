import re, json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import monconfig, engine  # noqa: E402
from monitorbox_app.store import Paths  # noqa: E402


def good():
    return {"builtinInternet": True, "nodes": [
        {"id": "gateway", "name": "Gateway", "group": "Network", "critical": True,
         "checks": [{"type": "ping", "target": "192.0.2.1"}]},
        {"id": "a3", "name": "Anchor3", "group": "Servers", "critical": True,
         "checks": [{"type": "ping", "target": "192.0.2.9"}, {"id": "ssh", "type": "tcp", "target": "192.0.2.9", "port": 22}]},
        {"id": "dns-a3", "name": "DNS .9", "group": "Internet", "dependsOn": ["a3"],
         "checks": [{"type": "dns", "server": "192.0.2.9", "name": "example.com"}]},
        {"id": "dns", "name": "DNS", "group": "Internet", "critical": True, "kind": "aggregate", "children": ["dns-a3"]},
    ]}


def modcheck(**kw):
    return {"builtinInternet": False, "nodes": [{"id": "ups", "name": "UPS", "group": "Power",
            "checks": [{"type": "module", "module": "nut", "connection": "ups-1", "check": "status", **kw}]}]}


class ModuleChecks(unittest.TestCase):
    def test_good(self):
        nodes, errs = monconfig.validate(modcheck(params={"x": 1}), {"ups-1"})
        self.assertEqual(errs, [])
        self.assertEqual(nodes[0]["checks"][0]["id"], "module")

    def test_connection_must_exist(self):
        self.assertIn("connection 'ups-1' does not exist", " ".join(monconfig.validate(modcheck(), set())[1]))
        self.assertEqual(monconfig.validate(modcheck(), None)[1], [])  # not checked when the caller has no list

    def test_bad_fields(self):
        for bad, text in ((dict(module="Bad Id"), "module id"), (dict(params=[1]), "params must be an object"),
                          (dict(check=5), "check must be text"), (dict(bogus=1), "unknown field")):
            m = modcheck()
            m["nodes"][0]["checks"][0].update(bad)
            self.assertIn(text, " ".join(monconfig.validate(m, {"ups-1"})[1]), bad)


class Connections(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-conn-")
        self.paths = Paths(self.d)
        self.old = [{"id": "ups-1", "module": "nut", "host": "192.0.2.5", "password": "fake-nut-pw-1"},
                    {"id": "snmp-1", "module": "snmp", "host": "192.0.2.6", "authKey": "fake-auth-2", "privKey": "fake-priv-3", "user": "monitor"}]
        monconfig.save_connections(self.paths, [dict(c) for c in self.old], 0)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_removing_a_connection_works_even_when_checks_use_it(self):
        mc = lambda i, conn: {"id": i, "type": "module", "module": "nut", "connection": conn, "check": "ups", "params": {}}
        nodes = [{"id": "ups", "name": "UPS", "group": "Power", "checks": [mc("a", "ups-1")]},
                 {"id": "mixed", "name": "Mixed", "group": "Power", "checks": [mc("b", "ups-1"), {"id": "p", "type": "ping", "target": "192.0.2.9"}]},
                 {"id": "both", "name": "Both", "group": "Power", "kind": "aggregate", "children": ["ups"], "rule": "any"},
                 {"id": "other", "name": "Other", "group": "Power", "checks": [mc("c", "snmp-1")], "dependsOn": ["ups"]}]
        monconfig.save_monitoring(self.paths, {"builtinInternet": True, "nodes": nodes}, monconfig.get_monitoring(self.paths)["revision"])
        with self.assertRaises(monconfig.Invalid):                              # the JSON editor still refuses to orphan checks
            monconfig.save_connections(self.paths, [self.old[1]], monconfig.get_connections(self.paths)["revision"])
        out = monconfig.remove_connection(self.paths, "ups-1")
        self.assertEqual((out["removed"], out["checksDropped"]), (["both", "ups"], 2))     # the system left with nothing goes, and the group it emptied
        m = monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]
        self.assertEqual([n["id"] for n in m], ["mixed", "other"])
        self.assertEqual([k["type"] for k in m[0]["checks"]], ["ping"])         # a system with other checks keeps them
        self.assertEqual(m[1]["dependsOn"], [])
        self.assertEqual([c["id"] for c in monconfig.get_connections(self.paths)["connections"]], ["snmp-1"])
        with self.assertRaises(monconfig.Invalid):
            monconfig.remove_connection(self.paths, "ups-1")

    def test_secrets_are_masked_for_the_browser_but_stored_in_full(self):
        shown = monconfig.get_connections(self.paths)["connections"]
        self.assertEqual(shown[0]["password"], monconfig.MASK)
        self.assertEqual(shown[1]["authKey"], monconfig.MASK)
        self.assertEqual(shown[1]["privKey"], monconfig.MASK)
        self.assertEqual(shown[1]["user"], "monitor")        # not a secret
        self.assertNotIn("fake-", json.dumps(shown))
        self.assertEqual(monconfig.connection(self.paths, "ups-1")["password"], "fake-nut-pw-1")

    def test_sending_the_dots_back_keeps_the_stored_secret(self):
        rev = monconfig.get_connections(self.paths)["revision"]
        edited = monconfig.get_connections(self.paths)["connections"]
        edited[0]["host"] = "192.0.2.55"                      # change the host, leave the password as dots
        monconfig.save_connections(self.paths, edited, rev)
        got = monconfig.connection(self.paths, "ups-1")
        self.assertEqual((got["host"], got["password"]), ("192.0.2.55", "fake-nut-pw-1"))
        self.assertEqual(monconfig.connection(self.paths, "snmp-1")["privKey"], "fake-priv-3")

    def test_a_new_secret_replaces_the_old_one_and_dots_on_a_new_entry_are_refused(self):
        rev = monconfig.get_connections(self.paths)["revision"]
        edited = monconfig.get_connections(self.paths)["connections"]
        edited[0]["password"] = "fake-new-pw-9"
        edited.append({"id": "new-one", "module": "nut", "password": monconfig.MASK})
        with self.assertRaises(monconfig.Invalid) as cm:
            monconfig.save_connections(self.paths, edited, rev)
        self.assertIn("enter a real value", cm.exception.errors[0])
        self.assertEqual(monconfig.connection(self.paths, "ups-1")["password"], "fake-nut-pw-1")  # nothing changed
        edited.pop()
        monconfig.save_connections(self.paths, edited, rev)
        self.assertEqual(monconfig.connection(self.paths, "ups-1")["password"], "fake-new-pw-9")

    def test_revision_conflict_and_validation(self):
        with self.assertRaises(monconfig.Conflict):
            monconfig.save_connections(self.paths, [dict(c) for c in self.old], 0)  # stale
        rev = monconfig.get_connections(self.paths)["revision"]
        for bad in ([{"id": "A", "module": "nut"}], [{"id": "x", "module": "nut"}, {"id": "x", "module": "nut"}],
                    [{"id": "x"}], ["nope"], {"id": "x"}):
            with self.assertRaises(monconfig.Invalid, msg=bad):
                monconfig.save_connections(self.paths, bad, rev)

    def test_removing_a_connection_a_check_uses_is_refused(self):
        rev = monconfig.get_connections(self.paths)["revision"]
        rev = monconfig.save_monitoring(self.paths, modcheck(), rev)
        with self.assertRaises(monconfig.Invalid) as cm:
            monconfig.save_connections(self.paths, [c for c in monconfig.get_connections(self.paths)["connections"] if c["id"] != "ups-1"], rev)
        self.assertIn("does not exist", cm.exception.errors[0])

    def test_history_copies_hold_no_secrets(self):
        rdir = os.path.join(self.d, "config", "revisions")
        for f in os.listdir(rdir):
            with open(os.path.join(rdir, f)) as fh:
                self.assertNotIn("fake-", fh.read())


class Validate(unittest.TestCase):
    def test_good_config(self):
        nodes, errs = monconfig.validate(good())
        self.assertEqual(errs, [])
        self.assertEqual(nodes[1]["checks"][0]["id"], "ping")      # default check ids
        self.assertEqual(nodes[1]["checks"][1]["id"], "ssh")

    def errors(self, mutate):
        c = good()
        mutate(c)
        return " | ".join(monconfig.validate(c)[1])

    def test_each_mistake_is_named(self):
        self.assertIn("unknown field 'colour'", self.errors(lambda c: c["nodes"][0].update(colour="red")))
        self.assertIn("port must be 1 to 65535", self.errors(lambda c: c["nodes"][1]["checks"][1].update(port=99999)))
        self.assertIn("dependsOn 'nope' does not exist", self.errors(lambda c: c["nodes"][1].update(dependsOn=["nope"])))
        self.assertIn("child 'nope' does not exist", self.errors(lambda c: c["nodes"][3].update(children=["nope"])))
        self.assertIn("id used more than once", self.errors(lambda c: c["nodes"][1].update(id="gateway")))
        self.assertIn("type must be one of", self.errors(lambda c: c["nodes"][0]["checks"][0].update(type="pigeon")))
        self.assertIn("needs 'target'", self.errors(lambda c: c["nodes"][0]["checks"][0].pop("target")))
        self.assertIn("url must start with", self.errors(lambda c: c["nodes"][0]["checks"].append({"type": "http", "url": "ftp://x"})))
        self.assertIn("interval must be", self.errors(lambda c: c["nodes"][0]["checks"][0].update(interval=0)))
        self.assertIn("name is required", self.errors(lambda c: c["nodes"][0].update(name="")))
        self.assertIn("unknown setting", self.errors(lambda c: c.update(surprise=1)))

    def test_all_mistakes_are_listed_at_once(self):
        c = good()
        c["nodes"][0]["name"] = ""
        c["nodes"][1]["dependsOn"] = ["nope"]
        self.assertEqual(len(monconfig.validate(c)[1]), 2)

    def test_dependency_loop_is_refused(self):
        c = good()
        c["nodes"][0]["dependsOn"] = ["a3"]
        c["nodes"][1]["dependsOn"] = ["gateway"]
        self.assertIn("dependency loop", " | ".join(monconfig.validate(c)[1]))

    def test_validated_nodes_run_through_the_engine(self):
        nodes, _ = monconfig.validate(good())
        res = {f"{n['id']}/{c['id']}": {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "s"} for n in nodes for c in n.get("checks", [])}
        self.assertEqual(engine.evaluate(nodes, res)["banner"]["status"], "green")


class Builtin(unittest.TestCase):
    def test_builtin_internet_is_valid_and_hangs_under_the_gateway(self):
        nodes = monconfig.builtin_internet({"gateway"})
        _, errs = monconfig.validate({"nodes": nodes, "builtinInternet": False})
        self.assertEqual([e for e in errs if "dependsOn 'gateway'" not in e], [])    # gateway is not in this list
        self.assertEqual(nodes[0]["dependsOn"], ["gateway"])
        self.assertEqual(monconfig.builtin_internet(set())[0]["dependsOn"], [])      # no gateway declared: no link
        targets = sorted(c.get("target") or c.get("server") or c["url"] for n in nodes for c in n.get("checks", []))
        self.assertEqual(targets, ["1.1.1.1", "1.1.1.1", "8.8.8.8", "8.8.8.8", "https://www.google.com/"])

    def test_the_internet_story_splits_local_from_public(self):
        """ping works, public DNS works, but the web check fails -> only "google.com" is flagged;
        ping fails and gateway fine -> Internet is the single critical alert."""
        user, _ = monconfig.validate(good())
        nodes = monconfig.builtin_internet({"gateway"}) + user
        ok = lambda: {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "s"}
        bad = lambda: {"ok": False, "detail": "down", "ms": None, "at": "t", "since": "s"}
        res = {f"{n['id']}/{c['id']}": ok() for n in nodes for c in n.get("checks", [])}
        res["inet-web-google/http"] = bad()
        s = engine.evaluate(nodes, res)
        self.assertEqual([a["name"] for a in s["attention"]], ["google.com"])
        self.assertEqual(s["banner"]["status"], "red")
        res["inet-ping-cloudflare/ping"], res["inet-ping-google/ping"] = bad(), bad()
        res["inet-dns-cloudflare/dns"], res["inet-dns-google/dns"], res["inet-web-google/http"] = bad(), bad(), bad()
        s = engine.evaluate(nodes, res)
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual([a["name"] for a in s["attention"]], ["Internet"])          # one alert, public DNS and web explained by it


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = Paths(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_apply_bumps_revision_and_keeps_history(self):
        self.assertEqual(monconfig.get_monitoring(self.paths)["revision"], 0)
        r1 = monconfig.save_monitoring(self.paths, good(), 0)
        self.assertEqual(r1, 1)
        c = good()
        c["nodes"][0]["name"] = "Router"
        self.assertEqual(monconfig.save_monitoring(self.paths, c, 1), 2)
        self.assertEqual(monconfig.get_monitoring(self.paths)["monitoring"]["nodes"][0]["name"], "Router")
        with open(os.path.join(self.tmp, "config", "revisions", "000001.json")) as f:
            self.assertEqual(json.load(f)["monitoring"]["nodes"][0]["name"], "Gateway")   # the old one is still there

    def test_stale_edit_is_refused(self):
        monconfig.save_monitoring(self.paths, good(), 0)
        with self.assertRaises(monconfig.Conflict):
            monconfig.save_monitoring(self.paths, good(), 0)

    def test_bad_edit_changes_nothing(self):
        monconfig.save_monitoring(self.paths, good(), 0)
        before = monconfig.get_monitoring(self.paths)
        bad = good()
        bad["nodes"][0]["dependsOn"] = ["nope"]
        with self.assertRaises(monconfig.Invalid):
            monconfig.save_monitoring(self.paths, bad, 1)
        self.assertEqual(monconfig.get_monitoring(self.paths), before)

    def test_reserved_ids_are_refused(self):
        c = good()
        c["nodes"][0]["id"] = "internet"
        with self.assertRaises(monconfig.Invalid):
            monconfig.save_monitoring(self.paths, c, 0)

    def test_history_is_trimmed(self):
        rev = 0
        for i in range(monconfig.KEEP_REVISIONS + 5):
            c = good()
            c["nodes"][0]["name"] = f"G{i}"
            rev = monconfig.save_monitoring(self.paths, c, rev)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "config", "revisions"))), monconfig.KEEP_REVISIONS)

    def test_a_broken_stored_config_never_takes_the_app_down(self):
        monconfig.save_monitoring(self.paths, good(), 0)
        with open(self.paths.config) as f:
            cfg = json.load(f)
        cfg["monitoring"]["nodes"][1]["dependsOn"] = ["ghost"]       # hand-edited into something invalid
        with open(self.paths.config, "w") as f:
            json.dump(cfg, f)
        nodes, err = monconfig.all_nodes(self.paths)
        self.assertIn("ghost", err)
        self.assertTrue(nodes and all(n["id"].startswith("inet") or n["id"] == "internet" for n in nodes))  # built-in checks still run

    def test_builtin_can_be_turned_off(self):
        c = good()
        c["builtinInternet"] = False
        monconfig.save_monitoring(self.paths, c, 0)
        ids = [n["id"] for n in monconfig.all_nodes(self.paths)[0]]
        self.assertNotIn("internet", ids)
        self.assertIn("gateway", ids)


class ExpectedAndStop(unittest.TestCase):
    """Expected down and Stop watching, both saved through the same revisioned config."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-exp-")
        self.paths = Paths(self.d)
        ck = lambda t: [{"type": "ping", "target": t}]
        nodes = [{"id": "nas", "name": "NAS", "group": "Servers", "checks": ck("192.0.2.10")},
                 {"id": "pi", "name": "Pi", "group": "Servers", "checks": ck("192.0.2.11"), "dependsOn": ["nas"]},
                 {"id": "dns-a", "name": "DNS A", "group": "DNS", "checks": ck("192.0.2.12")},
                 {"id": "dns-b", "name": "DNS B", "group": "DNS", "checks": ck("192.0.2.13")},
                 {"id": "dns", "name": "DNS", "group": "DNS", "kind": "aggregate", "children": ["dns-a", "dns-b"], "rule": "any"}]
        monconfig.save_monitoring(self.paths, {"builtinInternet": True, "nodes": nodes}, 0)

    def mon(self):
        return monconfig.get_monitoring(self.paths)["monitoring"]

    def test_expected_down_is_saved_stamped_on_the_node_and_cleared(self):
        monconfig.set_expected(self.paths, "nas", True)
        self.assertEqual(self.mon()["expectedDown"], ["nas"])
        nodes, err = monconfig.all_nodes(self.paths)
        self.assertIsNone(err)
        self.assertEqual({n["id"] for n in nodes if n.get("expectedDown")}, {"nas"})
        monconfig.set_expected(self.paths, "nas", False)
        self.assertNotIn("expectedDown", self.mon())

    def test_a_builtin_check_can_be_marked_expected_down(self):
        builtin = next(n["id"] for n in monconfig.all_nodes(self.paths)[0] if n.get("builtin"))
        monconfig.set_expected(self.paths, builtin, True)
        self.assertTrue(next(n for n in monconfig.all_nodes(self.paths)[0] if n["id"] == builtin).get("expectedDown"))

    def test_an_unknown_system_is_refused(self):
        with self.assertRaises(monconfig.Invalid):
            monconfig.set_expected(self.paths, "nope", True)

    def test_stop_watching_removes_the_system_and_what_pointed_at_it(self):
        monconfig.set_expected(self.paths, "nas", True)
        out = monconfig.remove_node(self.paths, "nas")
        self.assertEqual(out["removed"], ["nas"])
        m = self.mon()
        self.assertEqual([n["id"] for n in m["nodes"]], ["pi", "dns-a", "dns-b", "dns"])
        self.assertEqual(m["nodes"][0]["dependsOn"], [])
        self.assertNotIn("expectedDown", m)
        self.assertIsNone(monconfig.all_nodes(self.paths)[1])

    def test_a_group_with_nothing_left_goes_with_its_last_member(self):
        monconfig.remove_node(self.paths, "dns-a")
        self.assertEqual(next(n for n in self.mon()["nodes"] if n["id"] == "dns")["children"], ["dns-b"])
        out = monconfig.remove_node(self.paths, "dns-b")
        self.assertEqual(out["removed"], ["dns", "dns-b"])
        self.assertEqual([n["id"] for n in self.mon()["nodes"]], ["nas", "pi"])

    def test_removing_a_group_can_take_the_systems_inside_it(self):
        out = monconfig.remove_node(self.paths, "dns", with_children=True)
        self.assertEqual(out["removed"], ["dns", "dns-a", "dns-b"])
        self.assertEqual([n["id"] for n in self.mon()["nodes"]], ["nas", "pi"])
        out = monconfig.remove_node(self.paths, "nas", with_children=True)       # a plain system is just itself
        self.assertEqual(out["removed"], ["nas"])

    def test_builtin_checks_cannot_be_stopped_here_and_unknown_is_refused(self):
        builtin = next(n["id"] for n in monconfig.all_nodes(self.paths)[0] if n.get("builtin"))
        with self.assertRaises(monconfig.Invalid) as e:
            monconfig.remove_node(self.paths, builtin)
        self.assertIn("built-in", e.exception.errors[0])
        with self.assertRaises(monconfig.Invalid):
            monconfig.remove_node(self.paths, "nope")


class FirstRunNetwork(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-net-")
        self.paths = Paths(self.d)

    def nodes(self):
        return {n["id"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"].get("nodes", [])}

    def test_gateway_and_dns_are_added_and_valid(self):
        out = monconfig.add_network(self.paths, "192.0.2.1", ["192.0.2.53", "192.0.2.54"])
        n = self.nodes()
        self.assertEqual(out["added"], ["gateway", "dns-192-0-2-53", "dns-192-0-2-54", "dns"])
        self.assertEqual(n["gateway"]["checks"][0]["target"], "192.0.2.1")
        self.assertEqual(n["dns-192-0-2-54"]["checks"][0]["server"], "192.0.2.54")
        self.assertEqual(n["dns-192-0-2-53"]["dependsOn"], ["gateway"])
        self.assertEqual((n["dns"]["kind"], n["dns"]["children"], n["dns"]["rule"]), ("aggregate", ["dns-192-0-2-53", "dns-192-0-2-54"], "any"))
        self.assertIsNone(monconfig.all_nodes(self.paths)[1])
        # the built-in internet checks now hang under the gateway
        self.assertEqual(next(x for x in monconfig.all_nodes(self.paths)[0] if x["id"] == "internet")["dependsOn"], ["gateway"])

    def test_running_it_twice_changes_nothing(self):
        monconfig.add_network(self.paths, "192.0.2.1", ["192.0.2.53"])
        rev = monconfig.get_monitoring(self.paths)["revision"]
        out = monconfig.add_network(self.paths, "192.0.2.1", ["192.0.2.53"])
        self.assertEqual((out["added"], monconfig.get_monitoring(self.paths)["revision"]), ([], rev))

    def test_one_dns_server_has_no_group_and_nothing_at_all_is_fine(self):
        self.assertEqual(monconfig.add_network(self.paths, None, ["192.0.2.53"])["added"], ["dns-192-0-2-53"])
        self.assertEqual(monconfig.add_network(self.paths, None, [])["added"], [])

    def test_bad_addresses_are_refused_in_plain_words(self):
        for gw, dns in (("not-an-ip", []), (None, ["2001:db8::1"]), (None, ["192.0.2.1; rm"])):
            with self.assertRaises(monconfig.Invalid):
                monconfig.add_network(self.paths, gw, dns)


class PortainerWatches(unittest.TestCase):
    """Containers go in as their own systems, depend on their environment's check, carry service details and an optional
    web check; stopping them tidies every reference."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-ptr-")
        self.paths = Paths(self.d)
        monconfig.save_connections(self.paths, [{"id": "granite-portainer", "module": "portainer", "host": "192.0.2.13", "token": "fake-ptr-tok-1", "name": "Granite"}], 0)
        self.env = {"label": "Environment Anchor3", "check": "environment", "params": {"name": "Anchor3"}, "node": "Anchor3 Portainer", "group": "Services"}
        self.svc = {"title": "Plex", "env": "Anchor3", "container": "plex", "icon": "plex", "url": "http://192.0.2.9:32400/"}
        self.items = [
            {"label": "Container plex on Anchor3", "check": "container", "params": {"env": "Anchor3", "name": "plex"}, "node": "Plex (Anchor3)",
             "group": "Services", "service": self.svc, "requires": self.env},
            {"label": "Web plex on Anchor3", "type": "http", "url": "http://192.0.2.9:32400/", "expect": [200, 401], "insecure": True,
             "node": "Plex (Anchor3)", "group": "Services", "service": self.svc, "requires": self.env}]

    def nodes(self):
        return {n["id"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]}

    def test_long_status_lists_are_saved_as_ranges_and_still_mean_the_same(self):
        from monitorbox_app import probes
        web = {**self.items[1], "expect": list(range(200, 400)) + [404]}
        monconfig.add_watches(self.paths, "granite-portainer", [self.items[0], web])
        saved = [c for c in self.nodes()["plex-anchor3"]["checks"] if c["type"] == "http"][0]["expect"]
        self.assertEqual(saved, ["200-399", 404])
        self.assertEqual(probes.status_codes(saved), set(range(200, 400)) | {404})
        self.assertEqual(probes.status_codes([200, 401]), {200, 401})                       # the older plain lists still work
        mon = monconfig.get_monitoring(self.paths)
        for bad in ([99], ["a-b"], ["200-700"], "200", []):
            m = __import__("copy").deepcopy(mon["monitoring"])
            [c for c in m["nodes"][1]["checks"] if c["type"] == "http"][0]["expect"] = bad
            with self.assertRaises(monconfig.Invalid, msg=str(bad)): monconfig.save_monitoring(self.paths, m, mon["revision"])

    def test_settings_saved_before_ranges_existed_still_load(self):
        """Regression: 0.28.0 capped a status list at 60 entries, so every web check saved earlier (all 200 codes from 200 to 399 listed one by one)
        made the whole saved config invalid and the dashboard fell back to the built-in checks only."""
        monconfig.add_watches(self.paths, "granite-portainer", [self.items[0], self.items[1]])
        mon = monconfig.get_monitoring(self.paths)
        m = __import__("copy").deepcopy(mon["monitoring"])
        [c for c in m["nodes"][1]["checks"] if c["type"] == "http"][0]["expect"] = list(range(200, 400)) + [401]
        monconfig.save_monitoring(self.paths, m, mon["revision"])
        again = monconfig.get_monitoring(self.paths)
        self.assertNotIn("error", str(again.get("problem", "")))

    def test_picking_again_saves_a_link_found_for_a_service_that_is_already_watched(self):
        bare = {k: v for k, v in self.svc.items() if k != "url"}
        first = [{**self.items[0], "service": bare}]
        monconfig.add_watches(self.paths, "granite-portainer", first)
        self.assertNotIn("url", self.nodes()["plex-anchor3"]["service"])
        out = monconfig.add_watches(self.paths, "granite-portainer", [{**self.items[0], "service": self.svc}])      # same checks, now with a link
        self.assertEqual(out["added"], 0)
        self.assertEqual(self.nodes()["plex-anchor3"]["service"]["url"], "http://192.0.2.9:32400/")
        monconfig.set_service_link(self.paths, "plex-anchor3", "http://192.0.2.9:32400/web")                      # the owner's own edit...
        monconfig.add_watches(self.paths, "granite-portainer", [{**self.items[0], "service": self.svc}])
        self.assertEqual(self.nodes()["plex-anchor3"]["service"]["url"], "http://192.0.2.9:32400/web")           # ...is never overwritten

    def test_a_services_link_can_be_set_changed_and_removed(self):
        monconfig.add_watches(self.paths, "granite-portainer", [{**self.items[0], "service": {k: v for k, v in self.svc.items() if k != "url"}}])
        self.assertNotIn("url", self.nodes()["plex-anchor3"]["service"])
        monconfig.set_service_link(self.paths, "plex-anchor3", "http://192.0.2.9:32400/web")
        self.assertEqual(self.nodes()["plex-anchor3"]["service"]["url"], "http://192.0.2.9:32400/web")
        monconfig.set_service_link(self.paths, "plex-anchor3", "")
        self.assertNotIn("url", self.nodes()["plex-anchor3"]["service"])
        for bad in ("javascript:alert(1)", "192.0.2.9:32400", "http://a b/"):
            with self.assertRaises(monconfig.Invalid): monconfig.set_service_link(self.paths, "plex-anchor3", bad)
        with self.assertRaises(monconfig.Invalid): monconfig.set_service_link(self.paths, "no-such-system", "http://192.0.2.9/")
        monconfig.set_service_link(self.paths, "anchor3-portainer", "http://192.0.2.9/admin")        # a system that is not a service keeps its link on the system
        n = self.nodes()["anchor3-portainer"]
        self.assertEqual((n.get("link"), "service" in n), ("http://192.0.2.9/admin", False))
        monconfig.set_service_link(self.paths, "anchor3-portainer", "")
        self.assertNotIn("link", self.nodes()["anchor3-portainer"])

    def test_a_container_and_its_web_check_share_a_node_that_depends_on_the_environment(self):
        out = monconfig.add_watches(self.paths, "granite-portainer", self.items)
        self.assertEqual(out["added"], 3)                           # environment, container, web
        n = self.nodes()
        self.assertEqual(sorted(n), ["anchor3-portainer", "plex-anchor3"])
        plex = n["plex-anchor3"]
        self.assertEqual(plex["dependsOn"], ["anchor3-portainer"])
        self.assertEqual([c["type"] for c in plex["checks"]], ["module", "http"])        # the container first: "is it there", then "is it working"
        self.assertEqual(plex["checks"][1], {"id": "web-plex-on-anchor3", "type": "http", "url": "http://192.0.2.9:32400/", "label": "Web plex on Anchor3",
                                             "connection": "granite-portainer", "expect": [200, 401], "insecure": True})
        self.assertEqual(plex["service"], self.svc)
        self.assertIsNone(monconfig.all_nodes(self.paths)[1])
        self.assertEqual(monconfig.watched_ids(self.paths, "granite-portainer"),
                         {"environment-anchor3", "container-plex-on-anchor3", "web-plex-on-anchor3"})

    def test_adding_twice_changes_nothing_and_an_edited_service_url_survives(self):
        monconfig.add_watches(self.paths, "granite-portainer", self.items)
        mon = monconfig.get_monitoring(self.paths)
        mon["monitoring"]["nodes"][1]["service"]["url"] = "https://plex.example.test/"
        monconfig.save_monitoring(self.paths, mon["monitoring"], mon["revision"])
        out = monconfig.add_watches(self.paths, "granite-portainer", self.items)
        self.assertEqual(out["added"], 0)
        self.assertEqual(self.nodes()["plex-anchor3"]["service"]["url"], "https://plex.example.test/")

    def test_stopping_a_container_removes_its_node_and_every_reference_to_it(self):
        monconfig.add_watches(self.paths, "granite-portainer", self.items)
        other = {"label": "Container sonarr on Anchor3", "check": "container", "params": {"env": "Anchor3", "name": "sonarr"}, "node": "Sonarr (Anchor3)",
                 "group": "Services", "requires": self.env}
        monconfig.add_watches(self.paths, "granite-portainer", [other])
        mon = monconfig.get_monitoring(self.paths)
        mon["monitoring"]["nodes"].append({"id": "later", "name": "Later", "group": "Services", "dependsOn": ["plex-anchor3"],
                                           "checks": [{"type": "ping", "target": "192.0.2.50"}]})
        monconfig.save_monitoring(self.paths, mon["monitoring"], mon["revision"])
        monconfig.remove_watches(self.paths, "granite-portainer", ["Container plex on Anchor3", "Web plex on Anchor3"])
        n = self.nodes()
        self.assertNotIn("plex-anchor3", n)
        self.assertEqual(n["later"]["dependsOn"], [])
        self.assertIsNone(monconfig.all_nodes(self.paths)[1])        # nothing dangling: the config still validates

    def test_long_names_get_valid_distinct_ids_and_adding_again_changes_nothing(self):
        """Found on the Pi: 'Homebridge Homebridge 1 (Bay Harbor - Anchor3)' made a node id longer than 31 characters and Apply failed."""
        env = {"label": "Environment Bay Harbor - Anchor3", "check": "environment", "params": {"name": "Bay Harbor - Anchor3"},
               "node": "Bay Harbor - Anchor3 Portainer", "group": "Services"}
        names = ["Homebridge Homebridge 1 (Bay Harbor - Anchor3)", "Media Preview Generator (Bay Harbor - Anchor3)",
                 "Media Preview Generator Worker (Bay Harbor - Anchor3)", "Media Preview Generator Worker (Bay Harbor - Granite)"]
        items = [{"label": f"Container {i} on Bay Harbor - Anchor3", "check": "container", "params": {"env": "Bay Harbor - Anchor3", "name": f"c{i}"},
                  "node": n, "group": "Services", "requires": env} for i, n in enumerate(names)]
        monconfig.add_watches(self.paths, "granite-portainer", items)
        nodes = monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]
        ids = [n["id"] for n in nodes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 5)                                          # four services and the environment
        self.assertTrue(all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", i) for i in ids), ids)
        self.assertEqual(sorted(n["name"] for n in nodes if n["name"] in names), sorted(names))
        self.assertIsNone(monconfig.all_nodes(self.paths)[1])
        before = monconfig.get_monitoring(self.paths)["revision"]
        self.assertEqual(monconfig.add_watches(self.paths, "granite-portainer", items)["added"], 0)      # the same long name finds its own node again
        self.assertEqual(len(monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]), 5)
        self.assertEqual(monconfig.node_slug("Short"), "short")

    def test_a_service_with_a_bad_field_or_url_is_refused(self):
        for svc in ({"title": "x", "secret": "y"}, {"url": "ftp://example.test"}, {"title": 5}):
            bad = [{**self.items[0], "service": svc}]
            with self.assertRaises(monconfig.Invalid):
                monconfig.add_watches(self.paths, "granite-portainer", bad)

    def test_a_check_may_name_its_connection_but_only_a_real_one(self):
        mon = monconfig.get_monitoring(self.paths)["monitoring"]
        mon["nodes"] = [{"id": "w", "name": "W", "group": "Services", "checks": [{"type": "http", "url": "http://192.0.2.1/", "connection": "nope"}]}]
        with self.assertRaises(monconfig.Invalid) as e:
            monconfig.save_monitoring(self.paths, mon, 0)
        self.assertIn("does not exist", str(e.exception))



class WebPages(unittest.TestCase):
    """A web page can be watched by hand: on a system that exists (its admin page) or as a system of its own."""
    def setUp(self):
        self.paths = Paths(tempfile.mkdtemp(prefix="mb-web-"))
        cur = monconfig.get_monitoring(self.paths)
        monconfig.save_monitoring(self.paths, {"nodes": [
            {"id": "granite", "name": "Granite", "group": "Servers", "rule": "primary", "checks": [{"id": "ping", "type": "ping", "target": "192.0.2.13"}]}]}, cur["revision"])

    def nodes(self):
        return {n["id"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]}

    def test_a_page_joins_an_existing_system_and_gives_it_an_open_link(self):
        out = monconfig.add_web_page(self.paths, "Granite admin", "https://192.0.2.13:443", system="granite", insecure=True, link="https://admin.example.test/")
        g = self.nodes()["granite"]
        self.assertEqual(out["node"], "granite")
        self.assertEqual([c["type"] for c in g["checks"]], ["ping", "http"])
        web = g["checks"][1]
        self.assertEqual((web["url"], web["insecure"], web["label"]), ("https://192.0.2.13:443", True, "Granite admin"))
        self.assertEqual(g["link"], "https://admin.example.test/")                       # the link people tap can differ from the address that is checked
        monconfig.add_web_page(self.paths, "Granite second", "http://192.0.2.13:8080/", system="granite")
        self.assertEqual(self.nodes()["granite"]["link"], "https://admin.example.test/")  # an existing link is never replaced by a later check

    def test_a_page_can_be_a_system_of_its_own_with_the_wanted_status_and_text(self):
        monconfig.add_web_page(self.paths, "Pi-hole API", "http://192.0.2.9:8081/api/auth", group="Internet", contains='"valid":false', expect=["401"])
        n = self.nodes()["pi-hole-api"]
        self.assertEqual((n["group"], n["link"]), ("Internet", "http://192.0.2.9:8081/api/auth"))
        c = n["checks"][0]
        self.assertEqual((c["expect"], c["contains"]), ([401], '"valid":false'))
        self.assertNotIn("insecure", c)                                                  # only https can be told to trust an unknown certificate
        monconfig.add_web_page(self.paths, "Pi-hole API", "http://192.0.2.9:8081/api/auth")
        self.assertIn("pi-hole-api-2", self.nodes())                                     # the same name twice stays distinct

    def test_bad_input_is_refused_with_reasons(self):
        for kw in ({"name": ""}, {"url": "ftp://x/"}, {"url": "http://a b/"}, {"link": "javascript:alert(1)"}, {"expect": ["abc"]}, {"expect": [99]},
                   {"contains": "x" * 101}, {"system": "no-such"}):
            args = dict(name="Page", url="http://192.0.2.9/"); args.update(kw)
            with self.assertRaises(monconfig.Invalid, msg=str(kw)): monconfig.add_web_page(self.paths, **args)
        self.assertEqual(list(self.nodes()), ["granite"])                                # nothing half-saved


class EnsureServer(unittest.TestCase):
    """A server starts with a system and a reachability check: ping, or a TCP port when it does not answer pings."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-srv-")
        self.paths = Paths(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def nodes(self):
        return monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]

    def test_a_new_server_gets_a_ping_check_once(self):
        a = monconfig.ensure_server(self.paths, "Granite", "192.0.2.13", lambda h: True, lambda h, p: True)
        b = monconfig.ensure_server(self.paths, "Granite again", "192.0.2.13", lambda h: True, lambda h, p: True)
        self.assertEqual((a["created"], b["created"], b["id"]), (True, False, a["id"]))
        self.assertEqual([(n["name"], n["checks"][0]["type"], n["checks"][0]["target"]) for n in self.nodes()], [("Granite", "ping", "192.0.2.13")])

    def test_a_machine_that_ignores_pings_gets_a_tcp_check_on_the_first_port_that_answers(self):
        monconfig.ensure_server(self.paths, "Quiet", "192.0.2.14", lambda h: False, lambda h, p: p == 22)
        c = self.nodes()[0]["checks"][0]
        self.assertEqual((c["type"], c["target"], c["port"]), ("tcp", "192.0.2.14", 22))

    def test_when_pinging_is_not_possible_or_nothing_answers_the_ping_check_stays(self):
        monconfig.ensure_server(self.paths, "A", "192.0.2.15", lambda h: None, lambda h, p: True)
        monconfig.ensure_server(self.paths, "B", "192.0.2.16", lambda h: False, lambda h, p: False)
        self.assertEqual([n["checks"][0]["type"] for n in self.nodes()], ["ping", "ping"])

    def test_one_server_can_hold_a_hundred_picks_but_not_a_runaway_number(self):
        monconfig.save_connections(self.paths, [{"id": "nas", "module": "snmp", "name": "Big NAS", "host": "192.0.2.20", "community": "fake-comm-q"}], 0)
        items = [{"label": f"Volume / shared folder S{i}", "check": "volume", "params": {"name": f"/share/S{i}"}} for i in range(120)]
        self.assertEqual(monconfig.add_watches(self.paths, "nas", items)["added"], 120)
        self.assertEqual([len(n["checks"]) for n in self.nodes()], [120])
        with self.assertRaises(monconfig.Invalid):
            monconfig.add_watches(self.paths, "nas", [{"label": f"Volume / shared folder T{i}", "check": "volume", "params": {"name": f"/share/T{i}"}} for i in range(200)])

    def test_a_bad_address_is_refused(self):
        with self.assertRaises(monconfig.Invalid):
            monconfig.ensure_server(self.paths, "X", "bad address!", None, None)


class ConfirmSettings(unittest.TestCase):
    def test_site_default_and_per_system_values_are_checked_and_kept(self):
        n = {"id": "a", "name": "A", "group": "Servers", "confirmFailures": 3, "confirmSeconds": 90.5, "checks": [{"id": "p", "type": "ping", "target": "x"}]}
        nodes, errs = monconfig.validate({"confirm": {"failures": 4, "seconds": 30}, "nodes": [n]}, None)
        self.assertEqual(errs, []); self.assertEqual((nodes[0]["confirmFailures"], nodes[0]["confirmSeconds"]), (3, 90.5))
        for bad in ({"confirm": {"failures": 0}}, {"confirm": {"failures": True}}, {"confirm": {"seconds": -1}}, {"confirm": {"x": 1}}):
            self.assertTrue(monconfig.validate(dict(bad, nodes=[]), None)[1], bad)
        self.assertTrue(monconfig.validate({"nodes": [dict(n, confirmFailures=99)]}, None)[1])



class OneItemPerCamera(unittest.TestCase):
    """An earlier version watched every camera as a check inside one shared 'Cameras' item, so one camera off only made it Degraded. Watching again gives each camera its own item."""
    def test_the_shared_cameras_item_is_split_and_the_old_summary_check_goes(self):
        d = tempfile.mkdtemp(prefix="mb-cam-"); paths = Paths(d)
        monconfig.save_connections(paths, [{"id": "nvr", "module": "unifi-protect", "base_url": "https://192.0.2.71", "username": "fake-reader-1", "password": "fake-pw-77", "name": "Protect"}], 0)
        chk = lambda label, check, **p: {"id": monconfig.check_id(label), "type": "module", "module": "unifi-protect", "connection": "nvr", "check": check, "params": p, "label": label}
        mon = {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [
            {"id": "cameras", "name": "Cameras", "group": "Cameras", "rule": "any", "checks": [chk("Protect cameras", "cameras"), chk("Protect recorder", "nvr"), chk("Camera Patio", "camera", name="Patio"), chk("Camera Garage", "camera", name="Garage")]}]}
        monconfig.save_monitoring(paths, mon, monconfig.get_monitoring(paths)["revision"])
        items = [{"label": "Protect recorder", "check": "nvr", "params": {}, "node": "UniFi Protect", "group": "Cameras", "rule": "primary"},
                 {"label": "Camera Patio", "check": "camera", "params": {"name": "Patio"}, "node": "Camera Patio", "group": "Cameras", "rule": "primary"},
                 {"label": "Camera Garage", "check": "camera", "params": {"name": "Garage"}, "node": "Camera Garage", "group": "Cameras", "rule": "primary"}]
        self.assertTrue(monconfig.split_shared_cameras(paths))
        self.assertFalse(monconfig.split_shared_cameras(paths), "the second time there is nothing left to split")
        monconfig.add_watches(paths, "nvr", items)             # and watching again from the detect list leaves it as it is
        nodes = {n["name"]: n for n in monconfig.get_monitoring(paths)["monitoring"]["nodes"]}
        self.assertEqual(sorted(nodes), ["Camera Garage", "Camera Patio", "UniFi Protect"], "the shared item is gone, the old all-cameras check with it")
        self.assertEqual({n["rule"] for n in nodes.values()}, {"primary"})
        self.assertEqual([c["params"].get("name") for c in nodes["Camera Patio"]["checks"]], ["Patio"])
        self.assertEqual([c["label"] for c in nodes["UniFi Protect"]["checks"]], ["Protect recorder"])
        self.assertTrue(all(n["rule"] == "primary" for n in nodes.values()))
        before = monconfig.get_monitoring(paths)["revision"]
        monconfig.add_watches(paths, "nvr", items)                        # doing it again changes nothing
        self.assertEqual(monconfig.get_monitoring(paths)["revision"], before)


if __name__ == "__main__":
    unittest.main()


class WakeSettings(unittest.TestCase):
    def node(self, wake):
        return {"builtinInternet": False, "nodes": [{"id": "granite", "name": "Granite", "group": "Servers",
                "checks": [{"type": "ping", "target": "192.0.2.13"}], "wake": wake}]}

    def test_good_and_normalized(self):
        nodes, errs = monconfig.validate(self.node({"macs": ["AA-BB-CC-DD-EE-01", "aabbccddee02"], "broadcast": "192.0.2.255", "timeout": 90}))
        self.assertEqual(errs, [])
        self.assertEqual(nodes[0]["wake"]["macs"], ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"])

    def test_errors(self):
        for wake, text in (({}, "needs 'macs'"), ({"macs": []}, "needs 'macs'"), ({"macs": ["nope"]}, "not a MAC"),
                           ({"macs": ["aa:bb:cc:dd:ee:01", "AA-BB-CC-DD-EE-01"]}, "listed twice"),
                           ({"macs": ["aa:bb:cc:dd:ee:01"], "broadcast": "x"}, "broadcast must be an IP"),
                           ({"macs": ["aa:bb:cc:dd:ee:01"], "timeout": 1}, "timeout must be"),
                           ({"macs": ["aa:bb:cc:dd:ee:01"], "port": 0}, "port must be"),
                           ({"macs": ["aa:bb:cc:dd:ee:01"], "x": 1}, "unknown field"), ("aa:bb", "must be an object")):
            self.assertIn(text, " ".join(monconfig.validate(self.node(wake))[1]), wake)

    def test_an_aggregate_cannot_be_woken(self):
        m = {"builtinInternet": False, "nodes": [
            {"id": "a", "name": "A", "group": "S", "checks": [{"type": "ping", "target": "x"}]},
            {"id": "g", "name": "G", "group": "S", "kind": "aggregate", "children": ["a"], "wake": {"macs": ["aa:bb:cc:dd:ee:01"]}}]}
        self.assertIn("only a system with its own checks", " ".join(monconfig.validate(m)[1]))


class HttpCheckOptions(unittest.TestCase):
    def test_contains_expect_and_insecure_are_accepted_and_unknown_options_are_not(self):
        node = lambda **c: {"nodes": [{"id": "web", "name": "Web", "group": "Services", "checks": [dict({"type": "http", "url": "http://192.0.2.1/"}, **c)]}]}
        nodes, errs = monconfig.validate(node(contains="Radarr", expect=[200, 401], insecure=True))
        self.assertEqual(errs, [])
        self.assertEqual(nodes[0]["checks"][0]["contains"], "Radarr")
        self.assertTrue(monconfig.validate(node(containz="Radarr"))[1])


class AddWatch(unittest.TestCase):
    """Re-detect's Watch button: checks go under the device that pings the connection's host."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-watch-")
        self.paths = Paths(self.d)
        monconfig.save_connections(self.paths, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.9", "community": "fake-comm-1"}], 0)
        mon = {"builtinInternet": False, "nodes": [
            {"id": "nas", "name": "Nas", "group": "Servers", "checks": [{"type": "ping", "target": "192.0.2.9"}]},
            # what an earlier version made: one node per item
            {"id": "nas-snmp-volume-plexdata", "name": "x", "group": "Servers",
             "checks": [{"type": "module", "module": "snmp", "connection": "nas-snmp", "check": "volume", "params": {"name": "/PlexData"}}]}]}
        monconfig.save_monitoring(self.paths, mon, monconfig.get_monitoring(self.paths)["revision"])

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def watch(self, label, check="volume", **p):
        return monconfig.add_watch(self.paths, "nas-snmp", label, check, p)

    def test_a_new_device_is_named_as_the_owner_typed_it_not_by_its_id(self):
        monconfig.save_connections(self.paths, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.9", "community": "fake-comm-1"},
                                                {"id": "monitor", "module": "snmp", "host": "192.0.2.77", "name": "Monitor Box", "community": "fake-comm-2"}],
                                   monconfig.get_monitoring(self.paths)["revision"])
        monconfig.add_watch(self.paths, "monitor", "Interface eth0", "interface", {"name": "eth0"})
        names = [n["name"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]]
        self.assertIn("Monitor Box", names)

    def test_a_name_typed_for_a_server_wins_over_the_old_name_of_the_system_it_joins(self):
        """The owner named the device Monitor; its checks joined an older system that pings the same address (Bay Harbor)."""
        monconfig.save_connections(self.paths, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.9", "name": "Monitor", "community": "fake-comm-1"}],
                                   monconfig.get_monitoring(self.paths)["revision"])
        monconfig.add_watch(self.paths, "nas-snmp", "Interface eth0", "interface", {"name": "eth0"})
        names = [n["name"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]]
        self.assertIn("Monitor", names); self.assertNotIn("Nas", names)

    def test_renaming_a_server_renames_its_system_but_not_an_ambiguous_one(self):
        self.watch("Volume /a", name="/a")
        mon = monconfig.get_monitoring(self.paths)
        mon["monitoring"]["nodes"] = [n for n in mon["monitoring"]["nodes"] if n["id"] != "nas-snmp-volume-plexdata"]    # drop the fixture's old per-item node
        monconfig.save_monitoring(self.paths, mon["monitoring"], mon["revision"])
        conns = [dict(monconfig.connection(self.paths, "nas-snmp"), name="Granite")]
        monconfig.save_connections(self.paths, conns, monconfig.get_monitoring(self.paths)["revision"])
        names = [n["name"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]]
        self.assertIn("Granite", names)
        # checks of the same connection spread over two systems: neither is renamed behind the owner's back
        mon = monconfig.get_monitoring(self.paths)
        nodes = mon["monitoring"]["nodes"]
        nodes.append({"id": "other", "name": "Other", "group": "Servers", "checks": [
            {"id": "z", "type": "module", "module": "snmp", "connection": "nas-snmp", "check": "uptime", "params": {}}]})
        monconfig.save_monitoring(self.paths, mon["monitoring"], mon["revision"])
        conns = [dict(monconfig.connection(self.paths, "nas-snmp"), name="Renamed")]
        monconfig.save_connections(self.paths, conns, monconfig.get_monitoring(self.paths)["revision"])
        names = [n["name"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]]
        self.assertNotIn("Renamed", names); self.assertIn("Other", names)

    def test_a_system_can_be_renamed_and_keeps_its_checks_and_id(self):
        out = monconfig.rename_node(self.paths, "nas", "  Bay Harbor  ")
        mon = monconfig.get_monitoring(self.paths)
        self.assertEqual(mon["revision"], out["revision"])
        node = next(n for n in mon["monitoring"]["nodes"] if n["id"] == "nas")
        self.assertEqual((node["name"], len(node["checks"])), ("Bay Harbor", 1))
        for bad in ("", "   ", "x" * 61):
            with self.assertRaises(monconfig.Invalid): monconfig.rename_node(self.paths, "nas", bad)
        with self.assertRaises(monconfig.Invalid): monconfig.rename_node(self.paths, "nope", "A")

    def test_a_system_gets_its_own_grace_values_and_none_means_the_site_default_again(self):
        def node(): return next(n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"] if n["id"] == "nas")
        monconfig.set_confirm(self.paths, "nas", 4, 75)
        self.assertEqual((node()["confirmFailures"], node()["confirmSeconds"]), (4, 75))
        monconfig.set_confirm(self.paths, "nas", None, 30)                      # only one of them: the other goes back to the default
        self.assertEqual((node().get("confirmFailures"), node()["confirmSeconds"]), (None, 30))
        monconfig.set_confirm(self.paths, "nas", None, None)
        self.assertNotIn("confirmSeconds", node()); self.assertNotIn("confirmFailures", node())
        for bad in ((0, None), (21, None), (2.5, None), (None, -1), (None, "x")):
            with self.assertRaises(monconfig.Invalid): monconfig.set_confirm(self.paths, "nas", *bad)
        self.assertNotIn("confirmFailures", node())                              # a refused change leaves nothing behind
        with self.assertRaises(monconfig.Invalid): monconfig.set_confirm(self.paths, "nope", 2, 2)

    def test_a_suggestion_can_ask_for_an_any_rule_node(self):
        monconfig.add_watches(self.paths, "nas-snmp", [{"label": "A", "check": "x", "params": {}, "node": "UniFi", "group": "Network", "rule": "any"},
                                        {"label": "B", "check": "x", "params": {}, "node": "UPS b", "group": "Power"}])
        nodes = {n["name"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]}
        self.assertEqual((nodes["UniFi"]["rule"], nodes["UPS b"]["rule"]), ("any", "primary"))

    def test_many_checks_long_names_and_earlier_per_item_nodes(self):
        for i in range(15):
            self.assertTrue(self.watch(f"Volume /disk{i}", name=f"/disk{i}")["added"])
        self.assertTrue(self.watch("Volume /PlexData", name="/PlexData")["added"])          # folds the old node in
        self.assertTrue(self.watch("Volume /" + "x" * 80, name="/" + "x" * 80)["added"])     # id is shortened to stay valid
        self.assertFalse(self.watch("Volume /disk3", name="/disk3")["added"])               # second tap is a no-op
        nodes = monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]
        self.assertEqual([n["id"] for n in nodes], ["nas"])
        self.assertEqual(len(nodes[0]["checks"]), 1 + 15 + 1 + 1)

    def test_unknown_connection_and_new_device(self):
        with self.assertRaises(ValueError):
            monconfig.add_watch(self.paths, "nope", "x", "uptime", {})
        monconfig.save_connections(self.paths, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.9", "community": "fake-comm-1"},
                                                {"id": "other", "module": "snmp", "host": "192.0.2.77"}],
                                   monconfig.get_connections(self.paths)["revision"])
        out = monconfig.add_watch(self.paths, "other", "Reachable (uptime)", "uptime", {})
        self.assertEqual(out["node"], "other")           # no node pings that host yet, so one is made

    def test_stop_watching_removes_only_that_check(self):
        self.watch("Volume /a", name="/a"); self.watch("Volume /b", name="/b")
        self.assertEqual(monconfig.watched_ids(self.paths, "nas-snmp") >= {"volume-a", "volume-b"}, True)
        out = monconfig.remove_watch(self.paths, "nas-snmp", "Volume /a")
        self.assertTrue(out["removed"])
        checks = monconfig.get_monitoring(self.paths)["monitoring"]["nodes"][0]["checks"]
        ids = [c.get("id") for c in checks]
        self.assertIn("volume-b", ids); self.assertNotIn("volume-a", ids); self.assertTrue(any(c.get("type") == "ping" for c in checks))   # the ping stays
        self.assertFalse(monconfig.remove_watch(self.paths, "nas-snmp", "Volume /a")["removed"])        # second time: nothing to do

    def test_a_node_that_watch_made_goes_away_with_its_last_check(self):
        monconfig.save_connections(self.paths, [{"id": "nas-snmp", "module": "snmp", "host": "192.0.2.9", "community": "fake-comm-1"},
                                                {"id": "other", "module": "snmp", "host": "192.0.2.77"}],
                                   monconfig.get_connections(self.paths)["revision"])
        monconfig.add_watch(self.paths, "other", "Reachable (uptime)", "uptime", {})
        monconfig.remove_watch(self.paths, "other", "Reachable (uptime)")
        self.assertNotIn("other", [n["id"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]])

    def test_a_batch_in_one_save_and_a_named_node_in_its_own_group(self):
        revs_before = monconfig.get_monitoring(self.paths)["revision"]
        items = [{"label": f"Disk {i}", "check": "row", "params": {"preset": "qnap-disk", "name": f"S{i}"}} for i in range(22)]
        out = monconfig.add_watches(self.paths, "nas-snmp", items)
        self.assertEqual(out["added"], 22)
        self.assertEqual(monconfig.get_monitoring(self.paths)["revision"], revs_before + 1)      # 22 disks, one saved revision
        out = monconfig.add_watches(self.paths, "nas-snmp", [{"label": "UPS networkups", "check": "ups", "params": {"ups": "networkups"},
                                                               "node": "UPS networkups", "group": "Power"}])
        nodes = {n["id"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]}
        self.assertEqual(nodes["ups-networkups"]["group"], "Power")
        self.assertEqual(len(nodes["nas"]["checks"]), 1 + 22)        # the ping plus the 22 disks; the UPS did not land under the server


class SyncNodes(unittest.TestCase):
    """Systems that follow a pairing: added, renamed, removed; the owner's own systems are never touched."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-sync-")
        self.paths = Paths(self.d)
        mon = {"builtinInternet": False, "nodes": [{"id": "nas", "name": "Nas", "group": "Servers", "checks": [{"type": "ping", "target": "192.0.2.9"}]}]}
        monconfig.save_monitoring(self.paths, mon, monconfig.get_monitoring(self.paths)["revision"])

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def node(self, sid, name):
        return {"id": "site-" + sid, "name": name, "group": "Sites", "checks": [{"id": "link", "type": "site", "site": sid, "interval": 15}]}

    def ids(self):
        return [n["id"] for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]]

    def test_follows_add_rename_remove_and_leaves_the_owners_systems_alone(self):
        monconfig.sync_nodes(self.paths, "site-", [self.node("tb", "Tidewater link"), self.node("bl", "Bay Harbor link")])
        self.assertEqual(sorted(self.ids()), ["nas", "site-bl", "site-tb"])
        rev = monconfig.get_monitoring(self.paths)["revision"]
        self.assertIsNone(monconfig.sync_nodes(self.paths, "site-", [self.node("tb", "Tidewater link"), self.node("bl", "Bay Harbor link")]))
        self.assertEqual(monconfig.get_monitoring(self.paths)["revision"], rev)       # nothing changed: nothing written
        monconfig.sync_nodes(self.paths, "site-", [self.node("tb", "Tidewater Lodge link")])
        nodes = {n["id"]: n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"]}
        self.assertEqual(sorted(nodes), ["nas", "site-tb"])
        self.assertEqual(nodes["site-tb"]["name"], "Tidewater Lodge link")
        self.assertEqual(nodes["nas"]["checks"][0]["target"], "192.0.2.9")


class CheckUrl(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-url-")
        self.paths = Paths(self.d)
        mon = {"builtinInternet": False, "nodes": [{"id": "ph", "name": "Pihole", "group": "Services", "checks": [
            {"id": "web", "type": "http", "url": "http://192.0.2.5:80/", "expect": [200, 404]}, {"id": "p", "type": "ping", "target": "192.0.2.5"}]}]}
        monconfig.save_monitoring(self.paths, mon, monconfig.get_monitoring(self.paths)["revision"])

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_the_address_changes_and_the_rest_of_the_check_stays(self):
        monconfig.set_check_url(self.paths, "ph", "web", " http://192.0.2.5:80/admin/ ")
        chk = monconfig.get_monitoring(self.paths)["monitoring"]["nodes"][0]["checks"]
        self.assertEqual(chk[0]["url"], "http://192.0.2.5:80/admin/")
        self.assertEqual(chk[0]["expect"], [200, 404])
        self.assertEqual(chk[1]["target"], "192.0.2.5")

    def test_bad_addresses_and_non_web_checks_are_refused_with_a_sentence(self):
        for args in (("ph", "web", "192.0.2.5/admin"), ("ph", "web", "http://a b/"), ("ph", "p", "http://192.0.2.5/"), ("nope", "web", "http://192.0.2.5/")):
            with self.assertRaises(monconfig.Invalid):
                monconfig.set_check_url(self.paths, *args)
        self.assertEqual(monconfig.get_monitoring(self.paths)["monitoring"]["nodes"][0]["checks"][0]["url"], "http://192.0.2.5:80/")
