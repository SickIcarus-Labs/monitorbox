import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import engine  # noqa: E402


def leaf(i, name=None, group="Servers", critical=False, dep=(), checks=1, rule="primary"):
    return {"id": i, "name": name or i, "group": group, "critical": critical, "dependsOn": list(dep),
            "checks": [{"id": f"c{k}", "type": "ping", "target": "x"} for k in range(checks)], "rule": rule}


def agg(i, children, name=None, group="Internet", critical=False, rule="any", dep=()):
    return {"id": i, "name": name or i, "group": group, "critical": critical, "kind": "aggregate",
            "children": list(children), "rule": rule, "dependsOn": list(dep)}


def R(**states):
    """R(a=True, b=False, c=None) -> results for each node's first check."""
    return {f"{k}/c0": {"ok": v, "detail": f"{k} detail", "ms": 1.0, "at": "t", "since": "s"} for k, v in states.items()}


class AttentionNames(unittest.TestCase):
    def test_a_system_with_several_checks_names_the_one_that_is_failing(self):
        n = leaf("nas", "NAS", checks=3, rule="primary")
        n["checks"][2]["label"] = "Disk 2"
        n["checks"][1]["label"] = "Fan"
        res = R(nas=True)
        res["nas/c1"] = {"ok": True, "detail": "fine", "ms": 1.0, "at": "t", "since": "s"}
        res["nas/c2"] = {"ok": False, "detail": "99% full", "warn": True, "ms": 1.0, "at": "t", "since": "s"}
        a = engine.evaluate([n], res)["attention"][0]
        self.assertEqual((a["name"], a["check"], a["detail"]), ("NAS", "Disk 2", "99% full"))

    def test_a_one_check_system_has_no_extra_label(self):
        n = leaf("web", "Web")
        n["checks"][0]["label"] = "Ping"
        self.assertEqual(engine.evaluate([n], R(web=False))["attention"][0]["check"], "")


class ExpectedDown(unittest.TestCase):
    """Marked down on purpose: quiet on the banner and cards, observed state untouched, dependents quiet with it."""
    def nodes(self, **mark):
        nas = {**leaf("nas", "NAS", "Servers"), **mark}
        return [nas, leaf("backup", "Backup job", "Services", dep=["nas"]), leaf("web", "Web", "Services")]

    def test_the_banner_is_green_and_the_observed_state_is_not_rewritten(self):
        s = engine.evaluate(self.nodes(expectedDown=True), R(nas=False, backup=False, web=True))
        self.assertEqual((s["banner"]["status"], s["attention"]), ("green", []))
        self.assertIn("2 expected down", s["banner"]["subline"])
        self.assertEqual(s["nodes"]["nas"]["state"], "failed")                       # observed, as ever
        self.assertEqual(s["nodes"]["backup"]["state"], "failed")
        self.assertEqual((s["nodes"]["nas"]["expected"], s["nodes"]["nas"]["muted"]), (True, True))
        self.assertEqual((s["nodes"]["backup"]["expected"], s["nodes"]["backup"]["muted"]), (False, True))   # quiet because of nas
        self.assertEqual(s["nodes"]["nas"]["label"], "Down, expected")

    def test_a_group_that_is_all_expected_down_says_so_and_a_mixed_group_counts_the_rest(self):
        s = engine.evaluate(self.nodes(expectedDown=True), R(nas=False, backup=False, web=True))
        cards = {c["name"]: c for c in s["cards"]}
        self.assertEqual((cards["Servers"]["state"], cards["Servers"]["big"]), ("expected", "Expected down"))
        self.assertEqual(cards["Services"]["state"], "healthy")
        self.assertIn("Backup job expected down", cards["Services"]["line"])

    def test_something_else_failing_still_counts(self):
        s = engine.evaluate(self.nodes(expectedDown=True), R(nas=False, backup=False, web=False))
        self.assertEqual(s["banner"]["status"], "red")                       # an actual down is red, critical or not
        self.assertEqual([a["name"] for a in s["attention"]], ["Web"])

    def test_a_system_marked_expected_that_is_up_is_just_healthy(self):
        s = engine.evaluate(self.nodes(expectedDown=True), R(nas=True, backup=True, web=True))
        self.assertEqual((s["banner"]["status"], s["nodes"]["nas"]["state"], s["nodes"]["nas"]["muted"]), ("green", "healthy", False))
        self.assertEqual(s["banner"]["subline"], "All 3 items are reporting normally.")

    def test_unknown_stays_unknown_and_is_quiet_when_expected(self):
        s = engine.evaluate(self.nodes(expectedDown=True), R(nas=None, backup=True, web=True))
        self.assertEqual((s["nodes"]["nas"]["state"], s["banner"]["status"]), ("unknown", "green"))

    def test_without_the_mark_nothing_changes(self):
        s = engine.evaluate(self.nodes(), R(nas=False, backup=False, web=True))
        self.assertEqual((s["banner"]["status"], [a["name"] for a in s["attention"]]), ("red", ["NAS"]))


class Banner(unittest.TestCase):
    def test_green(self):
        nodes = [leaf("a3", critical=True), leaf("granite", critical=True)]
        s = engine.evaluate(nodes, R(a3=True, granite=True))
        self.assertEqual(s["banner"]["status"], "green")
        self.assertEqual(s["banner"]["headline"], "Everything is fine")
        self.assertEqual(s["attention"], [])

    def test_red_for_any_actual_down_but_without_the_alarm_when_nothing_critical_is_affected(self):
        nodes = [leaf("a3", critical=True), leaf("tautulli", "Tautulli", "Services", dep=["a3"]), leaf("cam", "Pool camera", "Cameras")]
        s = engine.evaluate(nodes, R(a3=True, tautulli=False, cam=False))
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual(s["banner"]["headline"], "Something's down")
        self.assertEqual(s["banner"]["subline"], "Pool camera and Tautulli are down. Nothing critical is affected.")
        self.assertEqual({a["name"] for a in s["attention"]}, {"Tautulli", "Pool camera"})
        self.assertTrue(all(a["label"] == "Down" for a in s["attention"]))

    def test_blue_cannot_be_checked_and_is_never_red(self):
        nodes = [leaf("ups", "UPS", "Power", critical=True), leaf("web")]
        s = engine.evaluate(nodes, R(ups=None, web=True))
        self.assertEqual(s["banner"]["status"], "blue")          # critical but unknown: not "down"
        self.assertEqual(s["banner"]["headline"], "Something needs a look")
        self.assertEqual(s["attention"][0]["label"], "Unknown")

    def test_red_critical_down(self):
        nodes = [leaf("granite", "Granite", critical=True), leaf("agg", "Aggregation switch", "Network", critical=True)]
        s = engine.evaluate(nodes, R(granite=False, agg=False))
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual(s["banner"]["headline"], "Everything is fucked.")
        sub = s["banner"]["subline"]
        self.assertIn("Granite", sub)
        self.assertIn("Aggregation switch", sub)
        self.assertIn("are down", sub)

    def test_yellow_is_only_for_something_degraded_and_says_nothing_is_down(self):
        nodes = [leaf("a3", critical=True), leaf("plex", "Plex", "Services")]
        r = R(a3=True, plex=True); r["plex/c0"]["warn"] = True
        s = engine.evaluate(nodes, r)
        self.assertEqual((s["banner"]["status"], s["banner"]["headline"]), ("yellow", "Something's not right"))
        self.assertEqual(s["banner"]["subline"], "Plex is having trouble. Nothing is down.")
        r["a3/c0"] = {**r["a3/c0"], "ok": False}                               # a real down on top of it
        s = engine.evaluate(nodes, r)
        self.assertEqual((s["banner"]["status"], s["banner"]["headline"]), ("red", "Everything is fucked."))

    def test_a_busy_server_is_a_heads_up_line_under_a_green_banner(self):
        nodes = [leaf("a3", "Anchor3", critical=True), leaf("nas", "Granite", critical=True)]
        r = R(a3=True, nas=True); r["a3/c0"].update(detail="CPU 95% busy, memory 45% used", notice=True)
        s = engine.evaluate(nodes, r)
        self.assertEqual((s["banner"]["status"], s["banner"]["headline"], s["attention"]), ("green", "Everything is fine", []))
        self.assertIn("Heads-up: Anchor3: CPU 95% busy, memory 45% used.", s["banner"]["subline"])
        self.assertEqual(s["nodes"]["a3"]["state"], "healthy")              # observed state is never rewritten
        self.assertTrue(s["nodes"]["a3"]["checks"][0]["notice"])
        self.assertEqual([c["state"] for c in s["cards"] if c["name"] == "Servers"], ["healthy"])
        r["a3/c0"]["ok"] = False                                              # once it is really down, the note is gone from the banner
        self.assertNotIn("Heads-up", engine.evaluate(nodes, r)["banner"]["subline"])

    def test_a_confirming_notice_is_said_once_in_plain_words_without_the_counts(self):
        raw = "warning just now, confirming (2 of 2 in a row, 16 s of 60 s): Aggregation provisioning"
        nodes = [leaf("unifi", "UniFi"), leaf("agg", "Aggregation"), leaf("a3", "Anchor3")]
        r = R(unifi=True, agg=True, a3=True)
        r["unifi/c0"].update(detail=raw, notice=True); r["agg/c0"].update(detail=raw, notice=True); r["a3/c0"].update(detail="CPU 95% busy", notice=True)
        sub = engine.evaluate(nodes, r)["banner"]["subline"]
        self.assertIn("Heads-up: UniFi and Aggregation: Aggregation provisioning, confirming; Anchor3: CPU 95% busy.", sub, "the same thing said once, the counts gone")
        self.assertNotIn("in a row", sub)
        self.assertEqual(engine.heads_up([("A", "one; one; two")]), ["A: one", "A: two"], "a repeat inside one system is dropped")

    def test_precedence_red_over_yellow_over_blue(self):
        nodes = [leaf("crit", critical=True), leaf("minor"), leaf("odd")]
        self.assertEqual(engine.evaluate(nodes, R(crit=False, minor=False, odd=None))["banner"]["status"], "red")
        self.assertEqual(engine.evaluate(nodes, R(crit=True, minor=False, odd=None))["banner"]["status"], "red")      # down, though nothing critical is
        self.assertEqual(engine.evaluate(nodes, R(crit=True, minor=True, odd=None))["banner"]["status"], "blue")

    def test_starting_until_first_results(self):
        nodes = [leaf("a"), leaf("b")]
        self.assertEqual(engine.evaluate(nodes, {})["banner"]["status"], "starting")
        s = engine.evaluate(nodes, R(a=True))                    # one answered, one pending: not blue
        self.assertEqual(s["banner"]["status"], "green")
        self.assertEqual(s["nodes"]["b"]["state"], "pending")


class RootCause(unittest.TestCase):
    def nodes(self):
        return [leaf("a3", "Anchor3", critical=True),
                leaf("plex", "Plex", "Services", dep=["a3"]), leaf("scrypted", "Scrypted", "Services", dep=["a3"]),
                leaf("cam", "Garage camera", "Cameras", dep=["scrypted"]), leaf("granite", "Granite", critical=True)]

    def test_one_alert_for_a_root_cause(self):
        s = engine.evaluate(self.nodes(), R(a3=False, plex=False, scrypted=False, cam=False, granite=True))
        self.assertEqual([a["id"] for a in s["attention"]], ["a3"])
        self.assertEqual(s["attention"][0]["affects"], ["Garage camera", "Plex", "Scrypted"])
        self.assertIn("Anchor3 is down", s["banner"]["subline"])
        self.assertIn("3 other items are affected", s["banner"]["subline"])

    def test_observed_state_is_not_rewritten(self):
        s = engine.evaluate(self.nodes(), R(a3=False, plex=False, scrypted=True, cam=True, granite=True))
        self.assertEqual(s["nodes"]["plex"]["state"], "failed")            # still shown as what was observed
        self.assertEqual(s["nodes"]["plex"]["affectedBy"], ["a3"])
        self.assertEqual(s["nodes"]["scrypted"]["state"], "healthy")        # works even though host "down"
        self.assertEqual(s["nodes"]["scrypted"]["affectedBy"], [])

    def test_root_is_the_topmost_failure(self):
        s = engine.evaluate(self.nodes(), R(a3=False, plex=True, scrypted=False, cam=False, granite=True))
        self.assertEqual(s["nodes"]["cam"]["affectedBy"], ["a3"])           # not "scrypted"
        self.assertEqual(s["nodes"]["scrypted"]["affectedBy"], ["a3"])

    def test_independent_failures_are_both_reported(self):
        s = engine.evaluate(self.nodes(), R(a3=False, plex=False, scrypted=True, cam=True, granite=False))
        self.assertEqual({a["id"] for a in s["attention"]}, {"a3", "granite"})

    def test_unknown_under_a_failed_root_is_explained_by_it(self):
        s = engine.evaluate(self.nodes(), R(a3=False, plex=None, scrypted=None, cam=None, granite=True))
        self.assertEqual([a["id"] for a in s["attention"]], ["a3"])
        self.assertEqual(s["banner"]["status"], "red")

    def test_unknown_behind_an_unreachable_provider_is_one_question_not_many(self):
        nodes = [leaf("scrypted", "Scrypted", "Services"), leaf("c1", "Front", "Cameras", dep=["scrypted"]),
                 leaf("c2", "Pool", "Cameras", dep=["scrypted"])]
        s = engine.evaluate(nodes, R(scrypted=None, c1=None, c2=None))
        self.assertEqual([a["id"] for a in s["attention"]], ["scrypted"])
        self.assertEqual(s["attention"][0]["affects"], ["Front", "Pool"])
        self.assertEqual(s["banner"]["status"], "blue")

    def test_critical_node_down_because_of_noncritical_root_is_red(self):
        nodes = [leaf("sw", "Switch", "Network"), leaf("srv", "Server", critical=True, dep=["sw"])]
        s = engine.evaluate(nodes, R(sw=False, srv=False))
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual([a["id"] for a in s["attention"]], ["sw"])         # one alert, on the switch

    def test_dependency_cycle_does_not_hang(self):
        nodes = [leaf("a", dep=["b"]), leaf("b", dep=["a"])]
        s = engine.evaluate(nodes, R(a=False, b=False))
        self.assertEqual(s["banner"]["status"], "red")


class Rules(unittest.TestCase):
    def test_primary_failed_vs_secondary_failed(self):
        n = [leaf("srv", checks=2)]
        self.assertEqual(engine.evaluate(n, {"srv/c0": R(srv=False)["srv/c0"]})["nodes"]["srv"]["state"], "failed")
        both = {"srv/c0": R(srv=True)["srv/c0"], "srv/c1": R(srv=False)["srv/c1".replace("c1", "c0")]}
        self.assertEqual(engine.evaluate(n, both)["nodes"]["srv"]["state"], "degraded")

    def test_any_rule(self):
        n = [leaf("wan", checks=2, rule="any")]
        ok, bad = R(wan=True)["wan/c0"], R(wan=False)["wan/c0"]
        st = lambda a, b: engine.evaluate(n, {"wan/c0": a, "wan/c1": b})["nodes"]["wan"]["state"]
        self.assertEqual(st(ok, ok), "healthy")
        self.assertEqual(st(ok, bad), "degraded")
        self.assertEqual(st(bad, bad), "failed")

    def test_aggregate_any_down_only_when_all_children_down(self):
        nodes = [leaf("d1", group="Internet"), leaf("d2", group="Internet"), leaf("d3", group="Internet"),
                 agg("dns", ["d1", "d2", "d3"], "DNS", critical=True)]
        one = engine.evaluate(nodes, R(d1=False, d2=True, d3=True))
        self.assertEqual(one["nodes"]["dns"]["state"], "degraded")
        self.assertEqual(one["banner"]["status"], "red")                    # one resolver is down (the aggregate is only degraded)
        self.assertEqual([a["id"] for a in one["attention"]], ["d1"])       # the aggregate adds no second alert
        allbad = engine.evaluate(nodes, R(d1=False, d2=False, d3=False))
        self.assertEqual(allbad["nodes"]["dns"]["state"], "failed")
        self.assertEqual(allbad["banner"]["status"], "red")
        self.assertIn("DNS", [a["name"] for a in allbad["attention"]])

    def test_internet_story(self):
        """gateway ok, both public pings fail -> WAN down (red, one alert); local DNS still fine."""
        nodes = [leaf("gw", "Gateway", "Network", critical=True),
                 leaf("wan-a", "1.1.1.1", "Internet", dep=["gw"]), leaf("wan-b", "8.8.8.8", "Internet", dep=["gw"]),
                 agg("internet", ["wan-a", "wan-b"], "Internet", critical=True, dep=["gw"]),
                 leaf("pdns", "Public DNS", "Internet", dep=["internet"])]
        s = engine.evaluate(nodes, R(gw=True, **{"wan-a": False, "wan-b": False}, pdns=False))
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual([a["name"] for a in s["attention"] if a["state"] == "failed" and a["critical"]], ["Internet"])
        # the same failure with the gateway down: the gateway is the single root cause
        s = engine.evaluate(nodes, R(gw=False, **{"wan-a": False, "wan-b": False}, pdns=False))
        self.assertEqual([a["id"] for a in s["attention"]], ["gw"])


    def test_failed_aggregate_explains_its_children_but_defers_to_a_known_host(self):
        hosts = [leaf("h1", "Host 1", critical=True), leaf("h2", "Host 2", critical=True)]
        dns = [leaf("d1", "DNS 1", "Internet", dep=["h1"]), leaf("d2", "DNS 2", "Internet", dep=["h2"]), agg("dns", ["d1", "d2"], "DNS", critical=True)]
        s = engine.evaluate(hosts + dns, R(h1=False, h2=False, d1=False, d2=False))
        self.assertEqual({a["id"] for a in s["attention"]}, {"h1", "h2"})   # hosts are the causes; "DNS down" is a consequence
        self.assertEqual(s["nodes"]["dns"]["affectedBy"], ["h1", "h2"])
        s = engine.evaluate(hosts + dns, R(h1=True, h2=True, d1=False, d2=False))
        self.assertEqual([a["id"] for a in s["attention"]], ["dns"])        # DNS itself is the problem; no host to blame
        self.assertEqual(s["attention"][0]["affects"], ["DNS 1", "DNS 2"])


class Cards(unittest.TestCase):
    def test_cards_follow_groups_and_worst_state(self):
        nodes = [leaf("a3", "Anchor3", "Servers", True), leaf("go", "Granite", "Servers", True), leaf("gw", "Gateway", "Network", True),
                 leaf("odd", "Odd thing", "Zeta")]
        s = engine.evaluate(nodes, R(a3=True, go=False, gw=True, odd=True))
        names = [c["name"] for c in s["cards"]]
        self.assertEqual(names, ["Servers", "Network", "Zeta"])            # known groups first, in house order
        srv = s["cards"][0]
        self.assertEqual((srv["state"], srv["big"]), ("failed", "1 of 2 up"))
        self.assertIn("Granite", srv["line"])
        self.assertEqual(s["cards"][1]["big"], "Up")                       # single item reads as a word


def ups_node(i="ups", name="Rack UPS"):
    return {"id": i, "name": name, "group": "Power", "critical": False, "dependsOn": [], "rule": "primary", "checks": [{"id": "c0", "type": "module", "module": "nut", "check": "ups"}]}


def ups_res(detail, ok=True, warn=True):
    return {"ups/c0": {"ok": ok, "warn": warn, "detail": detail, "ms": 1.0, "at": "t", "since": "s"}}


class PoweredBy(unittest.TestCase):
    def servers(self, **extra):
        return [ups_node(), {**leaf("a", "Anchor3"), "poweredBy": ["ups"]}, {**leaf("b", "Granite"), "poweredBy": ["ups"]}, leaf("c", "Camera"), *extra.get("more", [])]

    def test_servers_that_go_down_while_their_ups_runs_on_battery_are_explained_by_it(self):
        res = {**ups_res("on battery, 80%"), **R(a=False, b=False, c=False)}
        out = engine.evaluate(self.servers(), res, "t")
        self.assertEqual([a["id"] for a in out["attention"]], ["c", "ups"], "the camera nobody explained (down sorts first) and the UPS")
        ups = next(a for a in out["attention"] if a["id"] == "ups")
        self.assertEqual(sorted(ups["affects"]), ["Anchor3", "Granite"])
        self.assertEqual(out["nodes"]["a"]["affectedBy"], ["ups"])
        self.assertEqual(out["nodes"]["a"]["state"], "failed", "what is observed is not rewritten")

    def test_a_ups_that_is_down_explains_them_too_and_a_healthy_one_explains_nothing(self):
        out = engine.evaluate(self.servers(), {**ups_res("low battery", ok=False, warn=False), **R(a=False)}, "t")
        self.assertEqual([a["id"] for a in out["attention"]], ["ups"])
        out = engine.evaluate(self.servers(), {**ups_res("online", warn=False), **R(a=False)}, "t")
        self.assertEqual([a["id"] for a in out["attention"]], ["a"], "the power is fine, so this is its own problem")

    def test_a_ups_that_is_only_degraded_for_another_reason_does_not_explain_a_server_going_down(self):
        out = engine.evaluate(self.servers(), {**ups_res("replace battery"), **R(a=False)}, "t")
        self.assertIn("a", [x["id"] for x in out["attention"]])

    def test_only_a_server_that_is_actually_unwell_is_marked(self):
        out = engine.evaluate(self.servers(), {**ups_res("on battery"), **R(a=True, b=True, c=True)}, "t")
        self.assertEqual([a["id"] for a in out["attention"]], ["ups"])
        self.assertEqual(out["nodes"]["a"]["affectedBy"], [])

    def test_the_urgent_words_are_the_nut_modules_own(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "nut"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("nut_main_for_engine", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "nut", "main.py"))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        for w in engine.POWER_URGENT:
            self.assertIn(w, m.STATUS_WORDS.values())


class CameraCount(unittest.TestCase):
    """Regression: a Cameras card said '19 of 19 up' for nine cameras, because UniFi Protect and Scrypted both list the same cameras."""
    def cam(self, i, name, source):
        return {"id": i, "name": name, "group": "Cameras", "critical": False, "dependsOn": [], "rule": "primary",
                "checks": [{"id": "c0", "type": "module", "module": source, "check": "camera", "params": {"name": name}}]}

    def test_one_camera_seen_by_two_sources_counts_once_and_is_named_once_when_down(self):
        nodes = [self.cam("p-patio", "Camera Patio", "unifi-protect"), self.cam("s-patio", "Camera Patio", "scrypted"),
                 self.cam("p-pool", "Camera Pool", "unifi-protect"), self.cam("s-pool", "Camera Pool", "scrypted"),
                 self.cam("s-pkg", "Camera Doorbell Package", "scrypted")]
        card = lambda res: next(c for c in engine.evaluate(nodes, res)["cards"] if c["name"] == "Cameras")
        up = {f"{n['id']}/c0": {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "s"} for n in nodes}
        self.assertEqual(card(up)["big"], "3 of 3 up")
        down = dict(up, **{"p-patio/c0": {"ok": False, "detail": "offline", "ms": 1, "at": "t", "since": "s"},
                           "s-patio/c0": {"ok": False, "detail": "offline", "ms": 1, "at": "t", "since": "s"}})
        c = card(down)
        self.assertEqual(c["big"], "2 of 3 up")
        self.assertEqual(c["line"], "Camera Patio is down", "named once, not 'Camera Patio and Camera Patio are down'")

    def test_sources_that_disagree_make_a_camera_degraded_and_agreeing_makes_it_down_with_one_attention_entry(self):
        nodes = [self.cam("p-patio", "Camera Patio", "unifi-protect"), self.cam("s-patio", "Camera Patio", "scrypted"), self.cam("p-pool", "Camera Pool", "unifi-protect")]
        ok = {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "s"}
        bad = {"ok": False, "detail": "offline", "ms": 1, "at": "t", "since": "s"}
        # only UniFi Protect says it is down: Degraded, yellow, one entry; each source keeps what it observed
        out = engine.evaluate(nodes, {"p-patio/c0": bad, "s-patio/c0": ok, "p-pool/c0": ok})
        self.assertEqual([(a["name"], a["state"]) for a in out["attention"]], [("Camera Patio", "degraded")])
        self.assertIn("the other source reports it fine", out["attention"][0]["detail"])
        self.assertEqual((out["nodes"]["p-patio"]["state"], out["nodes"]["s-patio"]["state"]), ("failed", "healthy"))
        self.assertEqual(out["banner"]["status"], "yellow")
        # the other way round (Scrypted says down, Protect fine): the same
        out = engine.evaluate(nodes, {"p-patio/c0": ok, "s-patio/c0": bad, "p-pool/c0": ok})
        self.assertEqual([(a["name"], a["state"]) for a in out["attention"]], [("Camera Patio", "degraded")])
        # both say it is down: Down, red, still one entry
        out = engine.evaluate(nodes, {"p-patio/c0": bad, "s-patio/c0": bad, "p-pool/c0": ok})
        self.assertEqual([(a["name"], a["state"]) for a in out["attention"]], [("Camera Patio", "failed")])
        self.assertEqual(out["banner"]["status"], "red")
        # one source cannot be asked (unknown) while the other says down: that is Down, not a disagreement
        unk = {"ok": None, "detail": "cannot ask", "ms": None, "at": "t", "since": "s"}
        out = engine.evaluate(nodes, {"p-patio/c0": bad, "s-patio/c0": unk, "p-pool/c0": ok})
        self.assertEqual([(a["name"], a["state"]) for a in out["attention"]], [("Camera Patio", "failed")])

class SitesCard(unittest.TestCase):
    def test_the_sites_card_counts_its_sites_even_when_there_is_only_one(self):
        link = lambda i, name: {"id": i, "name": name, "group": "Sites", "critical": False, "dependsOn": [], "rule": "primary", "checks": [{"id": "c0", "type": "site", "site": i}]}
        ok = {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "s"}
        bad = {"ok": False, "detail": "no answer", "ms": 1, "at": "t", "since": "s"}
        card = lambda nodes, res: next(c for c in engine.evaluate(nodes, res)["cards"] if c["name"] == "Sites")
        one = [link("site-a", "Tidewater link")]
        self.assertEqual((card(one, {"site-a/c0": ok})["big"], card(one, {"site-a/c0": ok})["line"]), ("1 of 1 up", "Tidewater link"))
        self.assertEqual(card(one, {"site-a/c0": bad})["big"], "0 of 1 up")
        two = one + [link("site-b", "Riverside link")]
        self.assertEqual(card(two, {"site-a/c0": ok, "site-b/c0": bad})["big"], "1 of 2 up")
        other = [{"id": "x", "name": "Only one", "group": "Servers", "critical": False, "dependsOn": [], "rule": "primary", "checks": [{"id": "c0", "type": "ping", "target": "x"}]}]
        self.assertEqual(next(c for c in engine.evaluate(other, {"x/c0": ok})["cards"])["big"], "Up", "other cards with one item still say Up")

if __name__ == "__main__":
    unittest.main()


class DemoScenarios(unittest.TestCase):
    """The demo uses the real engine, so these double as a check of the four screens' copy and logic."""
    def snap(self, name):
        from monitorbox_app import demo
        nodes, res = demo.build(name)
        return engine.evaluate(nodes, res)

    def test_green(self):
        s = self.snap("green")
        self.assertEqual((s["banner"]["status"], s["attention"]), ("green", []))
        self.assertEqual([c["name"] for c in s["cards"]], ["Servers", "Network", "Internet", "Power", "Cameras", "Services"])

    def test_yellow(self):
        s = self.snap("yellow")
        self.assertEqual((s["banner"]["status"], s["banner"]["headline"]), ("yellow", "Something's not right"))
        self.assertEqual({a["name"] for a in s["attention"]}, {"Plex"})

    def test_down(self):
        s = self.snap("down")
        self.assertEqual((s["banner"]["status"], s["banner"]["headline"]), ("red", "Something's down"))
        self.assertEqual({a["name"] for a in s["attention"]}, {"Pool Equipment camera", "Tautulli"})

    def test_headsup(self):
        s = self.snap("headsup")
        self.assertEqual((s["banner"]["status"], s["attention"]), ("green", []))
        self.assertIn("Heads-up: Anchor3", s["banner"]["subline"])

    def test_blue(self):
        s = self.snap("blue")
        self.assertEqual(s["banner"]["status"], "blue")
        self.assertEqual({a["name"] for a in s["attention"]}, {"Rack UPS", "Scrypted"})      # cameras fold under Scrypted

    def test_red(self):
        s = self.snap("red")
        self.assertEqual(s["banner"]["status"], "red")
        self.assertEqual({a["name"] for a in s["attention"]}, {"Granite", "Aggregation switch"})
        self.assertIn("5 other items are affected", s["banner"]["subline"])


class Warn(unittest.TestCase):
    """A module check can say 'it answers, but not properly' (UPS on battery, disk nearly full): yellow, not red."""
    @staticmethod
    def W(**states):
        return {f"{k}/c0": {"ok": True, "warn": v, "detail": f"{k} warning", "ms": 1.0, "at": "t", "since": "s"} for k, v in states.items()}

    def test_warn_is_degraded_not_failed(self):
        s = engine.evaluate([leaf("ups", "UPS", "Power", critical=True)], self.W(ups=True))
        self.assertEqual(s["nodes"]["ups"]["state"], "degraded")
        self.assertEqual(s["banner"]["status"], "yellow")  # degraded is never red, even when critical
        self.assertEqual(s["nodes"]["ups"]["checks"][0]["state"], "degraded")

    def test_warn_false_is_healthy(self):
        s = engine.evaluate([leaf("ups")], self.W(ups=False))
        self.assertEqual(s["nodes"]["ups"]["state"], "healthy")

    def test_warn_on_a_secondary_check_degrades_a_primary_rule_node(self):
        n = leaf("srv", checks=2)
        res = {**R(srv=True), "srv/c1": {"ok": True, "warn": True, "detail": "disk 95% full", "ms": 1, "at": "t", "since": "s"}}
        s = engine.evaluate([n], res)
        self.assertEqual(s["nodes"]["srv"]["state"], "degraded")
        self.assertEqual(s["nodes"]["srv"]["detail"], "disk 95% full")

    def test_any_rule_with_only_warnings_is_degraded(self):
        n = leaf("pair", checks=2, rule="any")
        res = {f"pair/c{i}": {"ok": True, "warn": True, "detail": "w", "ms": 1, "at": "t", "since": "s"} for i in range(2)}
        self.assertEqual(engine.evaluate([n], res)["nodes"]["pair"]["state"], "degraded")
