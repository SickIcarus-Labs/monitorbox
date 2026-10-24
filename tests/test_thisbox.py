"""Looking at the box itself: routing table, resolv.conf, TCP and SNMPv3 discovery. All read-only, no credentials."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import thisbox as T
import snmp_fake as F, nut_fake, portainer_fake as PF

ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eth0\t00000000\t014DA8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0
eth0\t004DA8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0
"""


class Reading(unittest.TestCase):
    def test_the_gateway_is_the_default_routes_next_hop(self):
        self.assertEqual(T.gateway(ROUTE), "192.168.77.1")

    def test_no_default_route_means_no_gateway(self):
        self.assertIsNone(T.gateway(ROUTE.split("\n")[0] + "\n" + ROUTE.split("\n")[2] + "\n"))
        self.assertIsNone(T.gateway(""))

    def test_a_route_that_is_down_is_not_a_gateway(self):
        self.assertIsNone(T.gateway(ROUTE.replace("0003", "0001", 1)))

    def test_dns_servers_skip_loopback_ipv6_and_repeats(self):
        txt = "nameserver 127.0.0.11\nnameserver 192.168.77.1\nnameserver 192.168.77.1\nnameserver fe80::1\nnameserver 192.168.77.2\nnameserver junk\nsearch lan\n"
        self.assertEqual(T.dns_servers(txt), ["192.168.77.1", "192.168.77.2"])

    def test_own_address_is_always_some_ip(self):
        ip = T.own_ip(None)
        self.assertRegex(ip, r"^\d+\.\d+\.\d+\.\d+$")


class Probing(unittest.TestCase):
    def test_snmp_v3_discovery_sees_an_agent_and_not_an_empty_port(self):
        a = F.Agent(community="fake-comm-q"); self.addCleanup(a.close)
        self.assertTrue(T.snmp_v3_answers("127.0.0.1", a.port))
        self.assertFalse(T.snmp_v3_answers("127.0.0.1", 9, 0.3))

    def test_the_discovery_message_carries_no_credentials(self):
        pkt = T.discovery_packet()
        self.assertEqual(pkt[0], 0x30)
        self.assertNotIn(b"public", pkt)            # no community guessed
        self.assertTrue(T._is_v3_reply(pkt))        # it is a well-formed v3 message

    def test_scan_reports_what_answers_and_what_does_not(self):
        a = F.Agent(community="fake-comm-q"); self.addCleanup(a.close)
        u = nut_fake.Upsd({"ups": {"desc": "x", "vars": {}}}); self.addCleanup(u.close)
        r = T.scan(host="127.0.0.1", snmp_port=a.port, nut_port=u.port, portainer_ports=(1,), route_text=ROUTE,
                   resolv_text="nameserver 192.168.77.1\nnameserver 192.168.77.2\n")
        self.assertEqual((r["ip"], r["gateway"], r["dns"]), ("127.0.0.1", "192.168.77.1", ["192.168.77.1", "192.168.77.2"]))
        found = {s["module"]: s["found"] for s in r["services"]}
        # (the list grew by three entries that only show when found: Scrypted, UniFi Network, UniFi Protect)
        self.assertEqual(found, {"snmp": True, "nut": True, "portainer": False, "scrypted": False, "web": False, "unifi-network": False, "unifi-protect": False})

    def test_scan_on_a_quiet_box_finds_nothing_and_does_not_fail(self):
        r = T.scan(host="127.0.0.1", snmp_port=9, nut_port=1, portainer_ports=(2,), route_text="", resolv_text="")
        self.assertEqual((r["gateway"], r["dns"]), (None, []))
        self.assertFalse(any(s["found"] for s in r["services"]))
        self.assertIn("v2c", next(s for s in r["services"] if s["module"] == "snmp")["note"])

    def test_a_portainer_server_is_recognised_by_its_status_page(self):
        p = PF.Portainer(); self.addCleanup(p.close)
        self.assertEqual(T.portainer_server("127.0.0.1", (p.port,)), (p.port, "2.21.0"))
        self.assertEqual([r[0] for r in p.requests if r[0] != "GET"], [])      # only reads, and no token is sent
        self.assertTrue(all(r[2] is None for r in p.requests))

    def test_an_agent_is_not_mistaken_for_a_server_and_is_pointed_at_its_server(self):
        agent = PF.Silent(); self.addCleanup(agent.close)                  # accepts the connection, speaks no status page
        self.assertIsNone(T.portainer_server("127.0.0.1", (agent.port,)))
        r = T.scan(host="127.0.0.1", snmp_port=9, nut_port=1, portainer_ports=(agent.port,), agent_port=agent.port, route_text="", resolv_text="")
        ptr = next(s for s in r["services"] if s["module"] == "portainer")
        self.assertFalse(ptr["found"])
        self.assertIn("another Portainer server", ptr["note"])

    def test_scan_reports_a_portainer_server_with_its_version(self):
        p = PF.Portainer(); self.addCleanup(p.close)
        r = T.scan(host="127.0.0.1", snmp_port=9, nut_port=1, portainer_ports=(p.port,), agent_port=1, route_text="", resolv_text="")
        ptr = next(s for s in r["services"] if s["module"] == "portainer")
        self.assertEqual((ptr["found"], ptr["port"]), (True, p.port))
        self.assertIn("2.21.0", ptr["note"])


class MoreToFind(unittest.TestCase):
    ARP = ("IP address       HW type     Flags       HW address            Mask     Device\n"
           "192.0.2.13       0x1         0x2         AA:BB:CC:DD:EE:0F     *        eth0\n"
           "192.0.2.14       0x1         0x0         00:00:00:00:00:00     *        eth0\n")

    def test_the_mac_address_comes_from_the_arp_table_only_when_the_entry_is_complete(self):
        self.assertEqual(T.neighbor_mac("192.0.2.13", self.ARP), "aa:bb:cc:dd:ee:0f")
        self.assertIsNone(T.neighbor_mac("192.0.2.14", self.ARP))
        self.assertIsNone(T.neighbor_mac("192.0.2.99", self.ARP))

    def test_a_unifi_console_and_scrypted_are_recognised_on_a_named_machine_and_a_plain_web_server_is_not(self):
        console, plain = PF.Site(200), PF.Site(200)
        self.addCleanup(console.close); self.addCleanup(plain.close)
        console.srv.RequestHandlerClass.do_GET = lambda h: (h.send_response(200), h.end_headers(), h.wfile.write(b"<title>UniFi OS</title>"))
        scr = PF.Silent(); self.addCleanup(scr.close)
        r = T.scan("127.0.0.1", snmp_port=1, nut_port=1, portainer_ports=(1,), agent_port=1, scrypted_port=scr.port,
                   console_ports=(console.port,), console_schemes=("http",), arp_text=self.ARP)
        got = {s["module"]: s["found"] for s in r["services"]}
        self.assertTrue(got["unifi-network"] and got["unifi-protect"] and got["scrypted"])
        self.assertNotEqual(r["hostname"], "this-box-name-is-never-reported-for-a-named-machine"); self.assertEqual(r["ip"], "127.0.0.1")   # (its name, when it has one, comes from a reverse lookup)
        r = T.scan("127.0.0.1", snmp_port=1, nut_port=1, portainer_ports=(1,), agent_port=1, scrypted_port=1,
                   console_ports=(plain.port,), console_schemes=("http",))
        self.assertFalse({s["module"]: s["found"] for s in r["services"]}["unifi-network"])

    def test_a_machines_web_page_is_found_even_behind_a_login_wall_and_a_closed_port_is_not(self):
        site = PF.Site(200); self.addCleanup(site.close)
        self.assertEqual(T.web_page("127.0.0.1", ports=((site.port, "http"),)), f"http://127.0.0.1:{site.port}/")
        gate = PF.Site(401); self.addCleanup(gate.close)
        self.assertEqual(T.web_page("127.0.0.1", ports=((gate.port, "http"),)), f"http://127.0.0.1:{gate.port}/")
        self.assertIsNone(T.web_page("127.0.0.1", ports=((1, "http"),)))

    def test_a_machines_name_comes_from_a_netbios_answer(self):
        import socket, struct, threading
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); srv.bind(("127.0.0.1", 0)); srv.settimeout(5)
        self.addCleanup(srv.close)
        def answer():
            q, addr = srv.recvfrom(512)
            name = lambda n, flags: n.ljust(15).encode() + b"\x00" + struct.pack("!H", flags)
            rdata = bytes([2]) + name("WORKGROUP", 0x8000) + name("GRANITE", 0x0400)
            srv.sendto(q[:2] + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0) + b"\x20" + b"CK" + b"A" * 30 + b"\x00" + struct.pack("!HHIH", 0x21, 1, 0, len(rdata)) + rdata, addr)
        t = threading.Thread(target=answer, daemon=True); t.start()
        self.assertEqual(T.netbios_name("127.0.0.1", port=srv.getsockname()[1]), "granite")
        self.assertIsNone(T.netbios_name("127.0.0.1", port=9, timeout=0.2))


class IdentifyWeb(unittest.TestCase):
    """identify_web against a real local web server: a Pi-hole answers /admin/, a plain page is named by its title, and nothing is sent but GETs."""
    def serve(self, pages):
        import http.server, threading
        seen = []
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                seen.append((h.command, h.path))
                body = pages.get(h.path)
                h.send_response(200 if body is not None else 404); h.send_header("Content-Type", "text/html"); h.end_headers()
                h.wfile.write((body or "<title>Not found</title>").encode())
            def do_POST(h): seen.append(("POST", h.path)); h.send_response(500); h.end_headers()
            def log_message(h, *a): pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(srv.shutdown); self.addCleanup(srv.server_close)
        return srv.server_address[1], seen

    def test_a_pihole_is_recognised_at_its_admin_path(self):
        port, seen = self.serve({"/admin/": "<title>Pi-hole pi4</title><body>Pi-hole</body>", "/": "<title>x</title>"})
        w = T.identify_web("127.0.0.1", ports=((port, "http"),))
        self.assertEqual((w["kind"], w["url"]), ("pihole", f"http://127.0.0.1:{port}/admin/"))
        self.assertTrue(all(m == "GET" for m, _ in seen))

    def test_a_plain_page_is_named_by_its_title_and_an_error_page_still_counts_as_a_page(self):
        port, _ = self.serve({"/": "<html><title>\n  RouterOS   login </title></html>"})
        w = T.identify_web("127.0.0.1", ports=((port, "http"),))
        self.assertEqual((w["kind"], w["title"], w["url"]), (None, "RouterOS login", f"http://127.0.0.1:{port}/"))
        port2, _ = self.serve({})                     # every path 404: something still answers
        self.assertEqual(T.identify_web("127.0.0.1", ports=((port2, "http"),))["title"], "Not found")

    def test_a_unifi_page_is_recognised_and_a_closed_port_is_no_page(self):
        port, _ = self.serve({"/": "<title>UniFi OS</title>"})
        self.assertEqual(T.identify_web("127.0.0.1", ports=((port, "http"),))["kind"], "unifi")
        self.assertIsNone(T.identify_web("127.0.0.1", ports=((1, "http"),)))


if __name__ == "__main__":
    unittest.main()
