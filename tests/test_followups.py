"""Follow-up proposals: a UniFi Network controller suggests Protect (same console, same login), a declared server answering on Scrypted's
port suggests Scrypted, and nothing is proposed twice."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import followups as F  # noqa: E402

UNIFI = {"id": "gw", "module": "unifi-network", "base_url": "https://192.0.2.1", "username": "fake-user-a", "password": "fake-pass-a", "verify_tls": False}
SNMP = {"id": "nas", "module": "snmp", "host": "192.0.2.13", "community": "fake-comm-z"}


class Followups(unittest.TestCase):
    def test_a_unifi_controller_suggests_protect_once_and_scrypted_only_where_the_port_answers(self):
        asked = []
        def port_open(h, p):
            asked.append((h, p)); return h == "192.0.2.13"
        got = F.suggest([UNIFI, SNMP], port_open)
        self.assertEqual([(x["kind"], x["how"], x["host"]) for x in got], [("unifi-protect", "add", "192.0.2.1"), ("scrypted", "setup", "192.0.2.13")])
        self.assertEqual(sorted(asked), [("192.0.2.1", 10443), ("192.0.2.13", 10443)], "only declared addresses, only Scrypted's port")

    def test_a_login_made_in_the_forms_with_a_host_instead_of_an_address_still_offers_protect_and_copies_it(self):
        form = {"id": "gw", "module": "unifi-network", "host": "192.0.2.1", "username": "fake-user-b", "password": "fake-pass-b", "site": "default"}
        got = F.suggest([form], lambda h, p: False)
        self.assertEqual([(x["kind"], x["host"]) for x in got], [("unifi-protect", "192.0.2.1")])
        new = F.protect_from(form, {"gw"})
        self.assertEqual((new["host"], new["username"], new["password"]), ("192.0.2.1", "fake-user-b", "fake-pass-b"))

    def test_nothing_is_suggested_that_is_already_connected(self):
        have = [UNIFI, SNMP, {"id": "gw-protect", "module": "unifi-protect", "base_url": "https://192.0.2.1"},
                {"id": "scr", "module": "scrypted", "host": "192.0.2.13"}]
        self.assertEqual(F.suggest(have, lambda h, p: h == "192.0.2.13"), [])      # the only open port is on a host that already has Scrypted

    def test_the_protect_connection_reuses_the_login_and_gets_its_own_id(self):
        new = F.protect_from(UNIFI, {"gw", "gw-protect"})
        self.assertEqual((new["module"], new["base_url"], new["username"], new["password"], new["verify_tls"]),
                         ("unifi-protect", UNIFI["base_url"], "fake-user-a", "fake-pass-a", False))
        self.assertNotIn(new["id"], {"gw", "gw-protect"})

    def test_edge_agents_are_not_proposed_as_servers_but_are_mentioned(self):
        disc = {"environments": [{"name": "Cabin", "address": "", "edge": True}, {"name": "Shed", "address": "", "edge": True}, {"name": "A3", "address": "192.0.2.9", "edge": False}], "suggest": []}
        self.assertEqual([x["host"] for x in F.from_portainer([disc], [])], ["192.0.2.9"])
        self.assertEqual(len(F.notes_from_portainer([disc])), 1)
        self.assertIn("Cabin, Shed", F.notes_from_portainer([disc])[0])
        self.assertEqual(F.notes_from_portainer([{"environments": [{"name": "A3", "address": "192.0.2.9"}]}]), [])

    def test_a_watchtower_container_named_after_scrypted_is_not_scrypted(self):
        disc = {"environments": [{"name": "Anchor3", "address": "192.0.2.9"}], "suggest": [
            {"check": "container", "env": "Anchor3", "service": {"title": "Scrypted watchtower", "env": "Anchor3", "container": "scrypted-watchtower", "icon": "watchtower"}}]}
        self.assertEqual([x for x in F.from_portainer([disc], []) if x["kind"] != "server"], [])

    def test_a_scrypted_container_in_portainer_is_proposed_with_the_host_it_answers_on_and_never_twice(self):
        disc = {"environments": [{"name": "Anchor3", "address": "192.0.2.9"}], "suggest": [
            {"check": "environment", "env": "Anchor3"},
            {"check": "container", "env": "Anchor3", "service": {"title": "Scrypted", "env": "Anchor3", "container": "scrypted", "icon": "scrypted", "url": "https://192.0.2.9:10443/"}},
            {"check": "container", "env": "Anchor3", "service": {"title": "Plex", "env": "Anchor3", "container": "plex", "icon": "plex"}},
            {"check": "container", "env": "Anchor3", "service": {"title": "Unifi", "env": "Anchor3", "container": "unifi", "icon": "unifi"}}]}
        allgot = F.from_portainer([disc], [])
        self.assertEqual([x["host"] for x in allgot if x["kind"] == "server"], ["192.0.2.9"], "the machine Portainer manages is offered as a server")
        got = [x for x in allgot if x["kind"] != "server"]
        self.assertEqual([(x["kind"], x["host"], x["how"]) for x in got], [("scrypted", "192.0.2.9", "setup"), ("unifi-network", "192.0.2.9", "setup")])
        self.assertEqual([x for x in F.from_portainer([disc], [{"id": "s", "module": "scrypted", "host": "192.0.2.9"}, {"id": "u", "module": "unifi-network", "base_url": "https://192.0.2.9"}]) if x["kind"] != "server"], [])
        both = F.merge(F.suggest([SNMP], lambda h, p: True), got)
        self.assertEqual(sorted(x["id"] for x in both), ["scrypted:192.0.2.13", "scrypted:192.0.2.9", "unifi-network:192.0.2.9"])
        self.assertEqual(len([x for x in F.merge(got, got)]), 2)


class WebPages(unittest.TestCase):
    PIHOLE = {"url": "http://192.168.1.4/admin/", "kind": "pihole", "title": "Pi-hole", "insecure": False}
    NODES = [{"id": "gateway", "name": "Gateway", "checks": [{"id": "ping", "type": "ping", "target": "192.168.1.1"}]},
             {"id": "dns-192-168-1-4", "name": "DNS 192.168.1.4", "checks": [{"id": "dns", "type": "dns", "server": "192.168.1.4"}]},
             {"id": "pub", "name": "Public DNS", "checks": [{"id": "d", "type": "dns", "server": "1.1.1.1"}]}]

    def test_targets_are_the_gateway_dns_servers_and_declared_servers_never_public_addresses(self):
        t = F.web_targets(self.NODES, [SNMP], "192.168.1.1", ["192.168.1.9", "8.8.8.8"])
        self.assertEqual(t, [("192.0.2.13", "server"), ("192.168.1.1", "gateway"), ("192.168.1.4", "dns"), ("192.168.1.9", "dns")])

    def test_a_pihole_a_plain_router_and_a_titled_page_each_get_a_proposal_and_the_watched_page_is_skipped(self):
        pages = {"192.168.1.4": self.PIHOLE, "192.168.1.1": {"url": "https://192.168.1.1/", "kind": None, "title": "Login", "insecure": True},
                 "192.168.1.9": None, "192.0.2.13": {"url": "http://192.0.2.13/", "kind": None, "title": "Synology", "insecure": False}}
        t = F.web_targets(self.NODES, [SNMP], "192.168.1.1", ["192.168.1.9"])
        got = F.web_suggestions(t, {("192.0.2.13", 80)}, lambda h: pages[h])
        self.assertEqual([(x["host"], x["title"], x["url"], x["insecure"], x["how"]) for x in got],
                         [("192.168.1.1", "Router admin page", "https://192.168.1.1/", True, "webpage"),
                          ("192.168.1.4", "Pi-hole admin (192.168.1.4)", "http://192.168.1.4/admin/", False, "webpage")])
        self.assertEqual(F.web_suggestions([], set(), lambda h: None), [])

    def test_a_machine_with_other_pages_watched_is_still_offered_its_pihole(self):
        """The bug: Aurora had Portainer and Scrypted watched, so its Pi-hole on port 80 was never offered."""
        nodes = [{"id": "aurora", "link": "https://192.168.1.9:9443/", "service": {"url": "https://192.168.1.9:10443"}}]
        covered = F.watched_origins(nodes)
        self.assertEqual(covered, {("192.168.1.9", 9443), ("192.168.1.9", 10443)})
        got = F.web_suggestions([("192.168.1.9", "dns")], covered, lambda h: self.PIHOLE | {"url": "http://192.168.1.9/admin/"})
        self.assertEqual([x["title"] for x in got], ["Pi-hole admin (192.168.1.9)"])
        done = F.watched_origins(nodes + [{"id": "p", "checks": [{"type": "http", "url": "http://192.168.1.9/admin/"}]}])
        self.assertEqual(F.web_suggestions([("192.168.1.9", "dns")], done, lambda h: self.PIHOLE | {"url": "http://192.168.1.9/admin/"}), [], "the very page that is watched is not offered again")

    def test_origins_that_already_have_a_web_check_a_link_or_a_service_url_count_as_watched(self):
        nodes = [{"id": "a", "checks": [{"type": "http", "url": "http://192.168.1.4/admin/"}]}, {"id": "b", "link": "https://192.168.1.1/"},
                 {"id": "c", "service": {"url": "http://192.0.2.7:8123"}}, {"id": "d", "checks": [{"type": "tcp", "target": "192.0.2.99"}]}]
        self.assertEqual(F.watched_origins(nodes), {("192.168.1.4", 80), ("192.168.1.1", 443), ("192.0.2.7", 8123)})


class AddingWebPages(unittest.TestCase):
    def test_router_and_dns_pages_join_their_system_and_other_pages_become_their_own(self):
        import shutil, tempfile
        from types import SimpleNamespace
        from monitorbox_app import monconfig, server
        from monitorbox_app.store import Paths
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        paths = Paths(tmp)
        monconfig.add_network(paths, "192.168.1.1", ["192.168.1.4", "192.168.1.9"])
        sugs = [{"id": "web:192.168.1.1", "host": "192.168.1.1", "role": "gateway", "url": "https://192.168.1.1/", "insecure": True, "title": "Router admin page"},
                {"id": "web:192.168.1.4", "host": "192.168.1.4", "role": "dns", "url": "http://192.168.1.4/admin/", "insecure": False, "title": "Pi-hole admin (192.168.1.4)"},
                {"id": "web:192.0.2.13", "host": "192.0.2.13", "role": "server", "url": "http://192.0.2.13/", "insecure": False, "title": "Synology (192.0.2.13)"}]
        stub = SimpleNamespace(paths=paths, web_cache={"at": 1.0, "out": list(sugs), "running": False}, reload_monitoring=lambda: None)
        for sg in sugs:
            self.assertIn("Now watching", server.App.add_web_followup(stub, sg)["message"])
        nodes = {n["id"]: n for n in monconfig.get_monitoring(paths)["monitoring"]["nodes"]}
        self.assertEqual([c["type"] for c in nodes["gateway"]["checks"]], ["ping", "http"], "router: ping first, then its page, so a silent page reads Degraded")
        self.assertTrue(nodes["gateway"]["checks"][1]["insecure"] and nodes["gateway"]["link"] == "https://192.168.1.1/")
        self.assertEqual([c["type"] for c in nodes["dns-192-168-1-4"]["checks"]], ["dns", "http"])
        self.assertEqual([c["type"] for c in nodes["dns-192-168-1-9"]["checks"]], ["dns"], "the other DNS server is untouched")
        own = next(n for n in nodes.values() if n["name"] == "Synology (192.0.2.13)")
        self.assertEqual((own["group"], [c["type"] for c in own["checks"]]), ("Services", ["http"]))
        self.assertEqual(stub.web_cache["out"], [], "what was added is no longer offered")
        self.assertTrue(F.watched_origins(list(nodes.values())) >= {("192.168.1.1", 443), ("192.168.1.4", 80), ("192.0.2.13", 80)})


class OneContainerOneOffer(unittest.TestCase):
    """Regression: a Portainer server and the Portainer agent on the machine where a stack runs both listed its containers, so one new stack
    was offered twice (once on each connection)."""
    SERVER = {"id": "pt-server", "module": "portainer", "base_url": "https://192.0.2.50:9443"}
    AGENT = {"id": "pt-agent", "module": "portainer", "base_url": "https://192.0.2.60:9443"}

    def found(self, env, address):
        svc = lambda n: {"title": n, "env": env, "container": n}
        return {"environments": [{"name": env, "address": address}],
                "suggest": [{"label": f"Container {n} on {env}", "check": "container", "service": svc(n), "env": env} for n in ("fake-app-1", "fake-app-2")]
                           + [{"label": f"Web fake-app-1 on {env}", "type": "http", "service": svc("fake-app-1"), "env": env}]}

    def run_it(self, server_known=(), agent_known=()):
        fs, fa = self.found("Remote Box", "192.0.2.60"), self.found("local", "192.0.2.60")
        mine = lambda found, known: [x for x in found["suggest"] if x["label"] not in known]
        per = [(self.SERVER, fs, mine(fs, server_known), lambda it: it["label"] in server_known),
               (self.AGENT, fa, mine(fa, agent_known), lambda it: it["label"] in agent_known)]
        return {c["id"]: [x["label"] for x in items] for c, items in F.one_home(per)}

    def test_a_container_both_connections_can_see_is_offered_once_on_the_machine_it_runs_on(self):
        got = self.run_it()
        self.assertEqual(got["pt-server"], [], "the server only sees it through the agent")
        self.assertEqual(len(got["pt-agent"]), 3, "the machine's own connection offers both containers and the web page")

    def test_what_one_connection_already_watches_is_not_offered_by_the_other(self):
        agent_known = [f"Container fake-app-{i} on local" for i in (1, 2)] + ["Web fake-app-1 on local"]
        self.assertEqual(self.run_it(agent_known=agent_known), {"pt-server": [], "pt-agent": []})

    def test_a_container_only_one_connection_sees_is_still_offered(self):
        fs = self.found("Remote Box", "192.0.2.77")
        per = [(self.SERVER, fs, fs["suggest"], lambda it: False)]
        self.assertEqual(len(F.one_home(per)[0][1]), 3)


class NewThingsWording(unittest.TestCase):
    def test_the_offer_names_the_machine_once_and_the_things_without_repeating_it(self):
        conn = {"id": "pt-agent", "name": "Anchor3"}
        got = F.new_items_proposal(conn, [{"label": "Container fake-a on Remote Box"}, {"label": "Container fake-b on Remote Box"}, {"label": "Web fake-a on Remote Box"}])
        self.assertEqual(got["on"], "Anchor3")
        self.assertEqual(got["why"], "Anchor3 now offers Container fake-a, Container fake-b, Web fake-a. Add them to watch them (reading only).")
        mixed = F.new_items_proposal(conn, [{"label": "Container fake-a on Remote Box"}, {"label": "Pool tank"}])
        self.assertIn("Container fake-a on Remote Box", mixed["why"], "a label that does not share the ending is left whole")


class NamedByTheMachine(unittest.TestCase):
    """Regression: the offer said 'on Granite' (the Portainer server that reported it) when the containers run on Anchor3."""
    SERVER = {"id": "pt", "module": "portainer", "name": "Fake Portainer Box", "base_url": "https://192.0.2.50:9443"}
    BOX = {"id": "box", "module": "snmp", "name": "Fake Runner", "host": "192.0.2.60"}

    def items(self, env="Remote Env", address="192.0.2.60"):
        found = {"environments": [{"name": env, "address": address}]}
        return found, [{"label": f"Container fake-a on {env}", "service": {"container": "fake-a", "env": env}}]

    def test_the_machine_is_the_server_declared_at_the_address_the_things_run_at(self):
        found, items = self.items()
        self.assertEqual(F.machine_of(self.SERVER, found, items, [self.SERVER, self.BOX]), "Fake Runner")
        self.assertEqual(F.new_items_proposal(self.SERVER, items, "Fake Runner")["title"], "1 new thing on Fake Runner")

    def test_several_things_on_one_machine_are_named_by_it_the_case_that_was_missed(self):
        found, one = self.items()
        more = one + [{"label": "Container fake-b on Remote Env", "service": {"container": "fake-b", "env": "Remote Env"}}]
        self.assertEqual(F.machine_of(self.SERVER, found, more, [self.SERVER, self.BOX]), "Fake Runner")

    def test_without_a_declared_server_the_environment_name_is_used_and_mixed_machines_name_the_reporter(self):
        found, items = self.items()
        self.assertEqual(F.machine_of(self.SERVER, found, items, [self.SERVER]), "Remote Env")
        found2 = {"environments": [{"name": "A", "address": "192.0.2.61"}, {"name": "B", "address": "192.0.2.62"}]}
        two = [{"label": "Container x on A", "service": {"container": "x", "env": "A"}}, {"label": "Container y on B", "service": {"container": "y", "env": "B"}}]
        self.assertIsNone(F.machine_of(self.SERVER, found2, two, [self.SERVER]))


class EdgeAgentContainers(unittest.TestCase):
    """Regression: containers on an edge agent (no address of its own) were said to run on the Portainer server's machine."""
    SERVER = {"id": "pt", "module": "portainer", "name": "Fake Portainer Box", "base_url": "https://192.0.2.50:9443"}
    RUNNER = {"id": "r", "module": "snmp", "name": "Fake Runner", "host": "192.0.2.60"}
    BOX = {"id": "b", "module": "snmp", "name": "Fake Portainer Box", "host": "192.0.2.50"}

    def test_an_environment_with_no_address_is_not_taken_for_the_portainer_servers_machine(self):
        found = {"environments": [{"name": "Site - Fake Runner", "address": "", "edge": True}]}
        items = [{"label": "Container fake-a on Site - Fake Runner", "service": {"container": "fake-a", "env": "Site - Fake Runner"}}]
        self.assertEqual(F.machine_of(self.SERVER, found, items, [self.SERVER, self.BOX, self.RUNNER]), "Fake Runner", "named by the declared server whose name the environment contains")
        self.assertEqual(F.machine_of(self.SERVER, found, items, [self.SERVER, self.BOX]), "Site - Fake Runner", "else Portainer's own name for it, never the server that reports it")
        self.assertNotEqual(F.runs_at(self.SERVER, found, items[0])[0], "192.0.2.50")


class NewThings(unittest.TestCase):
    ITEMS = [{"label": "Volume /", "check": "volume", "batch": "Disks"}, {"label": "eth0", "check": "interface", "batch": "Network interfaces"},
             {"label": "Fan 2", "check": "sensor", "default": False}, {"label": "Whole box", "check": "x", "system": True}, {"label": "Pool tank", "check": "pool"}]

    def test_only_unwatched_unknown_default_items_count(self):
        got = F.new_items({"suggest": self.ITEMS}, lambda label: label == "Volume /", set())
        self.assertEqual([x["label"] for x in got], ["Pool tank"], "watched, interface, opt-in and system-level items are not proposed")
        self.assertEqual(F.new_items({"suggest": self.ITEMS}, lambda l: False, {"Pool tank", "Volume /"}), [], "known items are not proposed")
        for bad in (None, {}, {"suggest": None}, "x"):
            self.assertEqual(F.new_items(bad, lambda l: False, set()), [])

    def test_the_proposal_says_what_and_where_and_its_id_follows_the_set(self):
        conn = {"id": "nas", "name": "NAS", "module": "snmp"}
        one = F.new_items_proposal(conn, [{"label": "Pool tank"}])
        self.assertEqual((one["how"], one["from"], one["labels"], one["title"]), ("items", "nas", ["Pool tank"], "1 new thing on NAS"))
        many = F.new_items_proposal(conn, [{"label": f"Disk {i}"} for i in range(7)])
        self.assertEqual(many["title"], "7 new things on NAS"); self.assertIn("and 3 more", many["why"])
        self.assertNotEqual(one["id"], F.new_items_proposal(conn, [{"label": "Pool tank"}, {"label": "Pool b"}])["id"], "a later arrival is a new proposal")
        self.assertEqual(one["id"], F.new_items_proposal(conn, [{"label": "Pool tank"}])["id"])


SW_UNIFI = {"id": "gw", "module": "unifi-network", "host": "192.0.2.1", "username": "fake-user-c", "password": "fake-pass-c"}
SW_SWEEP = {"gw": {"devices": [
    {"name": "Core Gate", "type": "udm", "ip": "192.0.2.1"}, {"name": "Core 10G", "type": "usw", "ip": "192.0.2.21"},
    {"name": "Edge A", "type": "usw", "ip": "192.0.2.22"}, {"name": "Roof AP", "type": "uap", "ip": "192.0.2.31"}, {"name": "Rack Two", "type": "usw", "ip": "192.0.2.23"}]}}
GW_SNMP = {"id": "gate", "name": "Gateway", "module": "snmp", "host": "192.0.2.1", "version": "3", "port": 1161, "user": "fake-snmp-user", "auth": "sha",
           "authPassword": "fake-auth-pw-1", "priv": "aes", "privPassword": "fake-priv-pw-2", "timeout": 3, "retries": 2}


class SwitchesFromUnifi(unittest.TestCase):
    def test_the_login_on_the_gateway_is_the_one_tried_and_with_several_unmatched_logins_none_is(self):
        other = {**GW_SNMP, "id": "nas", "host": "192.0.2.50"}
        self.assertEqual(F.snmp_source([SW_UNIFI, other, GW_SNMP], SW_SWEEP)["id"], "gate")
        self.assertEqual(F.snmp_source([SW_UNIFI, other], SW_SWEEP)["id"], "nas", "the only SNMP login there is")
        self.assertIsNone(F.snmp_source([SW_UNIFI, other, {**other, "id": "nas2", "host": "192.0.2.51"}], SW_SWEEP), "guessing a login on devices can lock accounts")
        self.assertIsNone(F.snmp_source([SW_UNIFI], SW_SWEEP))

    def test_only_switches_not_already_connected_are_candidates_never_the_gateway_or_access_points(self):
        have = {"id": "rack", "module": "snmp", "host": "192.0.2.23"}
        self.assertEqual(F.switch_candidates([SW_UNIFI, GW_SNMP, have], SW_SWEEP), [("Core 10G", "192.0.2.21"), ("Edge A", "192.0.2.22")])
        self.assertEqual(F.switch_candidates([GW_SNMP], SW_SWEEP), [], "no UniFi connection, nothing to read the switches from")

    def test_the_proposal_changes_with_the_set_so_a_dismissed_set_does_not_hide_a_new_switch(self):
        a = F.switches_proposal(GW_SNMP, [{"name": "Edge A", "ip": "192.0.2.22"}])
        b = F.switches_proposal(GW_SNMP, [{"name": "Edge A", "ip": "192.0.2.22"}, {"name": "Core 10G", "ip": "192.0.2.21"}])
        self.assertNotEqual(a["id"], b["id"]); self.assertEqual((b["how"], b["from"], len(b["switches"])), ("snmp-switches", "gate", 2))
        self.assertIn("2 switches", b["title"]); self.assertIn("1 switch answer", a["title"])
        self.assertNotIn("fake-auth-pw-1", str(b))

    def test_each_new_connection_copies_every_part_of_the_login_gets_its_own_address_and_name_and_a_free_id(self):
        n = F.switch_connection(GW_SNMP, {"name": "Core 10G", "ip": "192.0.2.21"}, {"snmp-core-10g"})
        self.assertEqual(n, {"id": "snmp-core-10g-2", "module": "snmp", "name": "Core 10G", "host": "192.0.2.21", "version": "3", "port": 1161,
                             "user": "fake-snmp-user", "auth": "sha", "authPassword": "fake-auth-pw-1", "priv": "aes", "privPassword": "fake-priv-pw-2", "timeout": 3, "retries": 2})
        c2 = F.switch_connection({"id": "g", "module": "snmp", "host": "192.0.2.1", "version": "2c", "community": "fake-comm-9"}, {"name": "!!", "ip": "192.0.2.9"}, set())
        self.assertEqual((c2["id"], c2["community"], "user" in c2), ("snmp-192-0-2-9", "fake-comm-9", False))


if __name__ == "__main__":
    unittest.main()
