"""#324: a silent site link is judged from outside the tunnel, with the other site's public address told over the link.
Addresses here are from the documentation ranges (203.0.113.0/24, 198.51.100.0/24), each different so a mix-up shows."""
import ipaddress, os, sys, tempfile, time, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import peer, wanaddr  # noqa: E402

THEIRS, MINE, OTHER = "203.0.113.41", "198.51.100.77", "203.0.113.99"
_real_classify = wanaddr.classify
_DOC = [ipaddress.ip_network("203.0.113.0/24"), ipaddress.ip_network("198.51.100.0/24")]


def _classify_docs_as_public(ip):
    """The real rule says the documentation ranges cannot be reached from the internet, which is right; the tests need fake addresses that pass, so those two ranges count as public here."""
    try:
        if any(ipaddress.ip_address(str(ip).strip()) in n for n in _DOC):
            return "public"
    except ValueError:
        pass
    return _real_classify(ip)


def setUpModule():
    global _patch
    _patch = mock.patch.object(wanaddr, "classify", _classify_docs_as_public)
    _patch.start()


def tearDownModule():
    _patch.stop()


class Classify(unittest.TestCase):
    def test_what_the_internet_can_reach_and_what_it_cannot(self):
        for ip in ("8.8.8.8", "1.1.1.1", "9.9.9.9"):
            self.assertEqual(_real_classify(ip), "public", ip)
        for ip in ("10.1.2.3", "172.16.0.9", "192.168.3.1", "100.64.0.5", "100.127.255.1", "127.0.0.1", "169.254.1.1", "0.0.0.0", "203.0.113.41", "198.51.100.77"):
            self.assertEqual(_real_classify(ip), "private", ip)         # the last two are the documentation ranges the other tests borrow
        for ip in ("", "not an address", "999.1.1.1", None):
            self.assertEqual(_real_classify(ip), "invalid", repr(ip))


class OwnAddress(unittest.TestCase):
    def own(self, ports, reflected=OTHER):
        self.calls = {"unifi": 0, "reflect": 0}
        self.now = [1000.0]

        def unifi():
            self.calls["unifi"] += 1
            if isinstance(ports, Exception):
                raise ports
            return ports

        def reflect():
            self.calls["reflect"] += 1
            return reflected
        return wanaddr.Own(unifi, reflect, clock=lambda: self.now[0])

    def test_a_public_address_from_the_gateway_is_used_and_nothing_is_asked_outside(self):
        o = self.own([{"ip": MINE, "up": True}])
        self.assertEqual(o.get(), {"ip": MINE, "state": "ok", "source": "unifi", "why": ""})
        self.assertEqual(self.calls["reflect"], 0)

    def test_a_private_address_from_the_gateway_is_treated_as_double_nat_and_not_shared_and_not_second_guessed_outside(self):
        for private in ("192.168.8.2", "100.64.7.7", "10.0.0.9"):
            o = self.own([{"ip": private, "up": True}], reflected=OTHER)
            got = o.get()
            self.assertEqual((got["ip"], got["state"], got["source"]), (None, "private", "unifi"), private)
            self.assertIn("double NAT", got["why"])
            self.assertEqual(self.calls["reflect"], 0, "the outside page is not asked: its answer could not be pinged back through a double NAT either")

    def test_the_glitch_clears_by_itself_within_a_minute(self):
        state = {"ports": [{"ip": "192.168.8.2"}]}
        o = wanaddr.Own(lambda: state["ports"], lambda: None, clock=lambda: self.now[0])
        self.now = [5000.0]
        self.assertEqual(o.get()["state"], "private")
        state["ports"] = [{"ip": MINE}]
        self.now[0] += wanaddr.TTL_PRIVATE - 1
        self.assertEqual(o.get()["state"], "private", "still the cached answer")
        self.now[0] += 2
        self.assertEqual((o.get()["ip"], o.get()["state"]), (MINE, "ok"))

    def test_with_two_wans_the_first_public_one_is_used(self):
        o = self.own([{"ip": "192.168.8.2"}, {"ip": MINE}, {"ip": OTHER}])
        self.assertEqual(o.get()["ip"], MINE)

    def test_without_a_unifi_gateway_one_outside_page_is_asked_and_the_answer_is_kept_for_a_while(self):
        o = self.own(None, reflected=OTHER)
        self.assertEqual((o.get()["ip"], o.get()["source"]), (OTHER, "reflector"))
        o.get(); o.get()
        self.assertEqual(self.calls["reflect"], 1, "kept, not asked again")
        self.now[0] += wanaddr.TTL_REFLECTOR + 1
        o.get()
        self.assertEqual(self.calls["reflect"], 2)

    def test_a_private_or_missing_reflected_address_is_never_shared(self):
        self.assertEqual(self.own(None, reflected="10.9.9.9").get()["state"], "unknown")
        self.assertEqual(self.own(None, reflected=None).get()["state"], "unknown")

    def test_a_gateway_that_cannot_be_asked_falls_back_to_the_outside_page(self):
        o = self.own(RuntimeError("the UniFi login did not answer"), reflected=OTHER)
        self.assertEqual((o.get()["ip"], o.get()["source"]), (OTHER, "reflector"))

    def test_invalidate_looks_again_at_once(self):
        state = {"ports": [{"ip": MINE}]}
        o = wanaddr.Own(lambda: state["ports"], lambda: None, clock=lambda: 1.0)
        self.assertEqual(o.get()["ip"], MINE)
        state["ports"] = [{"ip": OTHER}]
        self.assertEqual(o.get()["ip"], MINE)
        o.invalidate()
        self.assertEqual(o.get()["ip"], OTHER, "the line came back after an outage and the address changed")

    def test_the_reflector_page_is_read_for_the_ip_line_only(self):
        import http.server, threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b"fl=1\nh=example\nip=203.0.113.250\nts=1\n")

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.assertEqual(wanaddr.reflect(f"http://127.0.0.1:{srv.server_address[1]}/"), "203.0.113.250")
        self.assertIsNone(wanaddr.reflect("http://127.0.0.1:9/"), "a page that does not answer gives None, not an error")


class Verdict(unittest.TestCase):
    """What a silent link means, from the site's public address and a control pair of addresses."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.addCleanup(self.d.cleanup)
        self.p = peer.Peer(os.path.join(self.d.name, "sites.json"), 8080, "x", lambda: "1.2.3", clock=lambda: 1000.0)
        self.replies = {}
        self.asked = []

        def ping(host):
            self.asked.append(host)
            return self.replies.get(host, False), "", None
        self.p.ping = ping

    def silent_site(self, wan=THEIRS):
        c = self.p._cfg()
        c["sites"] = [{"id": "tb", "name": "Turnberry", "address": "192.0.2.5:8443", "mid": "m1", "key": "00" * 32, "since": 1, **({"wan": wan} if wan else {})}]
        self.p._write(c)
        self.p._note("tb", "unknown", "Turnberry could not be reached (OSError)")
        return self.p.link_check("tb")

    def test_the_address_replies_so_it_is_the_link_not_the_site_degraded(self):
        self.replies[THEIRS] = True
        ok, detail, _, extra = self.silent_site()
        self.assertEqual((ok, extra), (True, {"warn": True}))
        self.assertIn(THEIRS, detail); self.assertIn("internet is up", detail)

    def test_no_reply_from_the_address_while_this_boxs_own_internet_is_fine_is_down(self):
        self.replies["8.8.8.8"] = True
        ok, detail, _, _ = self.silent_site()
        self.assertIs(ok, False)
        self.assertIn(THEIRS, detail); self.assertIn("own internet is fine", detail)

    def test_the_control_pair_is_tried_in_order_and_stops_at_the_first_answer(self):
        self.replies["1.1.1.1"] = True
        self.silent_site()
        self.assertEqual(self.asked, [THEIRS, "1.1.1.1"])

    def test_if_this_boxs_own_internet_is_down_too_it_cannot_tell_and_says_unknown(self):
        ok, detail, _, _ = self.silent_site()
        self.assertIsNone(ok)
        self.assertIn("own internet is down", detail)

    def test_with_no_address_yet_it_stays_as_it_was_unknown(self):
        ok, detail, ms = self.silent_site(wan=None)
        self.assertEqual((ok, ms, detail), (None, None, "Turnberry could not be reached (OSError)"))
        self.assertEqual(self.asked, [], "nothing was pinged")

    def test_a_box_that_cannot_ping_stays_unknown(self):
        self.p.ping = lambda host: (None, "ping is not permitted here", None)
        ok, detail, ms = self.silent_site()
        self.assertEqual((ok, detail), (None, "Turnberry could not be reached (OSError)"))

    def test_a_linked_site_is_healthy_without_any_ping_and_shows_its_address(self):
        self.silent_site()
        self.asked.clear()
        self.p._note("tb", "linked", "", version="1.7.9")
        ok, detail, _ = self.p.link_check("tb")
        self.assertTrue(ok)
        self.assertIn("internet address " + THEIRS, detail)
        self.assertEqual(self.asked, [])

    def test_the_managing_box_going_quiet_is_judged_the_same_way_from_the_managed_side(self):
        c = self.p._cfg()
        c["managers"] = [{"id": "mgr", "name": "Broad Leaf", "key": "00" * 32, "since": 1, "wan": MINE}]
        self.p._write(c)
        self.p.seen["mgr"] = 1000.0 - 600
        self.replies[MINE] = True
        ok, detail, _, extra = self.p.manager_check("mgr")
        self.assertEqual((ok, extra), (True, {"warn": True}))
        self.replies[MINE] = False; self.replies["1.1.1.1"] = True
        self.assertIs(self.p.manager_check("mgr")[0], False)
        self.p.seen["mgr"] = 1000.0 - 20
        self.assertEqual(self.p.manager_check("mgr")[1], "in touch (20 s ago)")


class Exchange(unittest.TestCase):
    """Two real boxes over the site port: each tells the other its public address, with the address kept across a restart."""
    def test_each_side_learns_the_others_address_and_remembers_it(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_sites import Box, free
        main, tb = Box(self, "fake-main-pw-11"), Box(self, "fake-tb-pw-2222")
        main.app.wan.cached, main.app.wan.at, main.app.wan.ttl = {"ip": MINE, "state": "ok", "source": "unifi", "why": ""}, time.time(), 3600
        tb.app.wan.cached, tb.app.wan.at, tb.app.wan.ttl = {"ip": THEIRS, "state": "ok", "source": "unifi", "why": ""}, time.time(), 3600
        tport = free()
        tb.post("/api/sites/name", {"name": "Tidewater"})
        tb.post("/api/sites/listen", {"enabled": True, "port": tport})
        code = tb.post("/api/sites/pair/start")[1]["pairing"]["code"]
        main.post("/api/sites/name", {"name": "Bay Harbor"})
        main.post("/api/sites/add", {"address": f"127.0.0.1:{tport}", "code": code})
        for _ in range(50):
            main.app.peer.poll_once()
            if main.get("/api/sites")["sites"][0].get("wan"):
                break
            time.sleep(0.1)
        self.assertEqual(main.get("/api/sites")["sites"][0]["wan"], THEIRS, "the managing box learned the site's address from its hello")
        self.assertEqual(tb.get("/api/sites")["managers"][0]["wan"], MINE, "the managed box learned the manager's address from its poll")
        again = peer.Peer(main.app.peer.path, 1, "x", lambda: "1")
        self.assertEqual(again.get()["sites"][0]["wan"], THEIRS, "kept on disk with the pairing, so a restart while the link is down still knows it")

    def test_a_private_or_nonsense_address_in_a_header_is_ignored(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        p = peer.Peer(os.path.join(d.name, "sites.json"), 1, "x", lambda: "1")
        c = p._cfg(); c["managers"] = [{"id": "m", "name": "x", "key": "00" * 32}]; p._write(c)
        for bad in ("192.168.3.9", "100.64.1.1", "not-an-ip", "", "127.0.0.1"):
            p.manager_wan_in("m", bad)
            self.assertIsNone(p.get()["managers"][0]["wan"], bad)
        p.manager_wan_in("m", MINE)
        self.assertEqual(p.get()["managers"][0]["wan"], MINE)

    def test_a_site_that_shares_nothing_private_sends_no_address(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        p = peer.Peer(os.path.join(d.name, "sites.json"), 1, "x", lambda: "1")
        p.wan_info = lambda: {"ip": "192.168.8.2", "state": "private", "why": "double NAT"}
        self.assertEqual(p.hello()["wan"], {"ip": None, "state": "private"})
        p.wan_info = lambda: {"ip": MINE, "state": "ok"}
        self.assertEqual(p.hello()["wan"], {"ip": MINE, "state": "ok"})
        p.wan_info = None
        self.assertEqual(p.hello()["wan"], {"ip": None, "state": "unknown"})

    def test_a_link_that_comes_back_makes_the_own_address_be_read_again(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        p = peer.Peer(os.path.join(d.name, "sites.json"), 1, "x", lambda: "1")
        seen = []
        p.on_relink = lambda: seen.append(1)
        p._note("s", "linked"); self.assertEqual(seen, [], "the first answer is not a return")
        p._note("s", "unknown", "x"); p._note("s", "unknown", "x"); self.assertEqual(seen, [])
        p._note("s", "linked"); self.assertEqual(seen, [1])
        p._note("s", "linked"); self.assertEqual(seen, [1])


if __name__ == "__main__":
    unittest.main()


class OtherSiteDoesNotChangeThisSite(unittest.TestCase):
    """A paired site that is down must not turn this site's own banner or attention list red (#324)."""

    def test_banner_stays_green_when_a_paired_site_or_manager_is_down(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_engine import leaf, R
        from monitorbox_app import engine
        nodes = [leaf("nas", "NAS"), leaf("site-aa11", "Elsewhere link", group="Sites"), leaf("managed-by-bb22", "Managed by Other", group="Sites")]
        out = engine.evaluate(nodes, R(nas=True, **{"site-aa11": False, "managed-by-bb22": False}))
        self.assertEqual(out["banner"]["status"], "green")
        self.assertEqual(out["attention"], [])
        self.assertEqual(out["nodes"]["site-aa11"]["state"], "failed")          # the observed state is untouched

    def test_this_sites_own_trouble_still_counts(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_engine import leaf, R
        from monitorbox_app import engine
        out = engine.evaluate([leaf("nas", "NAS", critical=True), leaf("site-aa11", "Elsewhere link", group="Sites")], R(nas=False, **{"site-aa11": True}))
        self.assertNotEqual(out["banner"]["status"], "green")


class GatewayVerdict(Verdict):
    """With the other site's gateway known (and known to answer pings), a silent link says which part is down."""
    GW = "10.77.0.1"
    OWN_GW = "10.55.0.1"

    def setUp(self):
        super().setUp()
        self.p.gateway = lambda: self.OWN_GW

    def silent_with_gateway(self, learned=True):
        c = self.p._cfg()
        c["sites"] = [{"id": "tb", "name": "Turnberry", "address": "192.0.2.5:8443", "mid": "m1", "key": "00" * 32, "since": 1, "wan": THEIRS, "gw": self.GW, "gwok": learned}]
        self.p._write(c)
        self.p._note("tb", "unknown", "Turnberry could not be reached (OSError)")
        return self.p.link_check("tb")

    def test_internet_up_but_gateway_silent_means_the_vpn_is_down(self):
        self.replies[THEIRS] = True
        ok, detail, _, extra = self.silent_with_gateway()
        self.assertEqual((ok, extra), (False, {}))                 # a broken tunnel is a real outage: red
        self.assertIn("VPN between the sites is down", detail); self.assertIn(self.GW, detail)

    def test_internet_and_gateway_up_means_monitorbox_there_is_down(self):
        self.replies[THEIRS] = True; self.replies[self.GW] = True
        ok, detail, _, extra = self.silent_with_gateway()
        self.assertEqual((ok, extra), (True, {"warn": True}))
        self.assertIn("MonitorBox on that site may be down", detail)

    def test_a_gateway_that_never_answered_is_ignored_and_the_old_wording_stays(self):
        self.replies[THEIRS] = True
        ok, detail, _, _ = self.silent_with_gateway(learned=False)
        self.assertIn("The link, or MonitorBox there, may be down", detail)
        self.assertNotIn(self.GW, self.asked)

    def test_internet_down_is_still_site_down_whatever_the_gateway_says(self):
        self.replies["8.8.8.8"] = True
        self.assertIs(self.silent_with_gateway()[0], False)
        self.assertNotIn(self.GW, self.asked)

    def test_it_learns_once_that_the_gateway_answers_while_the_link_works(self):
        self.silent_with_gateway(learned=False)
        self.p._note("tb", "linked", "", version="1.7.9")
        self.replies[self.GW] = True
        self.p.link_check("tb")
        self.assertTrue(next(s for s in self.p._cfg()["sites"] if s["id"] == "tb")["gwok"])
        self.asked.clear(); self.p.link_check("tb")
        self.assertEqual(self.asked, [], "learned once, not pinged every time")

    def test_an_address_that_is_the_same_on_both_sides_proves_nothing(self):
        self.silent_with_gateway(learned=False)
        self.p._remember_gw("sites", "tb", self.OWN_GW)
        self.assertEqual(next(s for s in self.p._cfg()["sites"] if s["id"] == "tb")["gw"], self.GW)

    def test_only_private_addresses_are_kept_as_a_gateway(self):
        self.silent_with_gateway(learned=False)
        self.p._remember_gw("sites", "tb", THEIRS)
        self.assertEqual(next(s for s in self.p._cfg()["sites"] if s["id"] == "tb")["gw"], self.GW)

    def test_the_default_gateway_is_read_from_the_network_table(self):
        f = os.path.join(self.d.name, "route")
        with open(f, "w") as h:
            h.write("Iface\tDestination\tGateway\tFlags\n" "eth0\t00000000\t0100370A\t0003\n" "eth0\t0000370A\t00000000\t0001\n")
        self.assertEqual(wanaddr.default_gateway(f), "10.55.0.1")
        self.assertIsNone(wanaddr.default_gateway(os.path.join(self.d.name, "none")))
