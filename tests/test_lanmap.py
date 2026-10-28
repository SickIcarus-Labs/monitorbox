"""The LAN map: built from the switch report. Made-up names and addresses throughout."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import lanmap


def port(idx, **kw):
    return dict({"port_idx": idx, "name": f"Port {idx}", "up": True, "speed": 1000, "inBps": 0, "outBps": 0}, **kw)


def report():
    devices = [
        {"name": "Gate-A", "model": "UDMX", "type": "udm", "state": "connected", "ip": "192.0.2.1", "uplink": {"type": "wire", "to": None, "port": 10}, "downPorts": 0,
         "ports": [port(1, inBps=400, outBps=300), port(10, is_uplink=True), port(11, speed=10000, inBps=9_000_000, outBps=7_000_000, rx_errors=21)]},
        {"name": "Core-B", "model": "SWX", "type": "usw", "state": "connected", "ip": "192.0.2.2",
         "uplink": {"type": "wire", "to": "Gate-A", "speedMbps": 10000, "up": True, "remotePort": 11, "port": 26}, "downPorts": 3,
         "ports": [port(7, speed=2500), port(9, speed=10000), port(13), port(25, speed=10000), port(26, is_uplink=True, speed=10000, inBps=8_000_000, outBps=6_500_000, tx_dropped=5)]},
        {"name": "Rack-C", "model": "SWY", "type": "usw", "state": "connected", "ip": "192.0.2.3",
         "uplink": {"type": "wire", "to": "Core-B", "speedMbps": 10000, "up": True, "remotePort": 25, "port": 26}, "downPorts": 18,
         "ports": [port(3, speed=10000, inBps=1000, outBps=5000), port(5, speed=10000, op_mode="aggregate", inBps=100, outBps=2000, rx_errors=2),
                   port(6, speed=10000, aggregated_by=5, inBps=300, outBps=4000, tx_errors=1), port(8, lastMac="..:aa:bb:cc"), port(26, is_uplink=True, speed=10000)]},
        {"name": "Edge-D", "model": "SWZ", "type": "usw", "state": "provisioning", "ip": "192.0.2.4",
         "uplink": {"type": "wire", "to": "Core-B", "speedMbps": 10000, "up": True, "remotePort": 9, "port": 9}, "downPorts": 7, "ports": [port(2), port(9, is_uplink=True, speed=10000)]},
        {"name": "AP-E", "model": "APX", "type": "uap", "state": "connected", "ip": "192.0.2.5", "uplink": {"type": "wire", "to": "Core-B", "speedMbps": 2500, "up": True, "remotePort": 7, "port": 1}, "ports": []},
    ]
    clients = [
        {"name": "NAS-One", "ip": "192.0.2.10", "mac": "..:11:11:11", "wired": True, "switch": "Rack-C", "port": 6},
        {"name": "Mini-Two", "ip": "192.0.2.11", "mac": "..:22:22:22", "wired": True, "switch": "Rack-C", "port": 3},
        {"name": "Mini-Two slow", "ip": "192.0.2.12", "mac": "..:33:33:33", "wired": True, "switch": "Rack-C", "port": 3},
        {"name": "TV-Three", "ip": "192.0.2.13", "mac": "..:44:44:44", "wired": True, "switch": "Core-B", "port": 13},
        {"name": "Printer-Four", "ip": "192.0.2.14", "mac": "..:55:55:55", "wired": True, "switch": "Edge-D", "port": 2},
        {"name": "Phone-Five", "ip": "192.0.2.15", "mac": "..:66:66:66", "wired": False, "ap": "AP-E"},
        {"name": "Phone-Six", "ip": "192.0.2.16", "mac": "..:77:77:77", "wired": False, "ap": "AP-E"},
    ]
    snmp = {"sysName": "Server-Nas", "ports": [{"name": "bond0", "mac": "..:11:11:11"}, {"name": "eno1", "mac": "..:88:88:88"}]}
    snmp2 = {"sysName": "Server-Spare", "ports": [{"name": "eth0", "mac": "..:aa:bb:cc"}]}
    return [{"connection": "u", "module": "unifi-network", "report": {"devices": devices, "clients": clients}},
            {"connection": "s1", "module": "snmp", "report": snmp}, {"connection": "s2", "module": "snmp", "report": snmp2},
            {"connection": "dead", "module": "snmp", "error": "no answer"}]


class LanMap(unittest.TestCase):
    def setUp(self):
        self.m = lanmap.build(report())
        self.n = {x["id"]: x for x in self.m["nodes"]}

    def test_the_tree_comes_from_the_uplinks_with_the_gateway_first(self):
        self.assertEqual(self.m["nodes"][0]["id"], "Gate-A")
        self.assertEqual({k: v["parent"] for k, v in self.n.items()}, {"Gate-A": None, "Core-B": "Gate-A", "Rack-C": "Core-B", "Edge-D": "Core-B", "AP-E": "Core-B"})

    def test_a_link_names_both_ports_and_reads_the_child_ports_own_counters(self):
        l = self.n["Rack-C"]["link"]
        self.assertEqual((l["to"], l["port"], l["parentPort"], l["speedMbps"]), ("Core-B", 26, 25, 10000))
        c = self.n["Core-B"]["link"]
        self.assertEqual((c["down"], c["up_bps"], c["drops"], c["errors"]), (8_000_000, 6_500_000, 5, 0), "down is what the switch receives from above")

    def test_a_link_with_no_port_counters_is_unknown_not_zero(self):
        self.assertEqual((self.n["Edge-D"]["link"]["down"], self.n["Edge-D"]["link"]["up_bps"]), (0, 0), "the port is there and reads zero")
        self.assertIsNone(self.n["AP-E"]["link"]["down"], "the access point reports no ports at all")

    def test_the_gateways_way_out_is_a_port_of_its_own_with_its_speed(self):
        # regression (Broad Leaf SFP+ 1, the modem): UniFi marks the WAN port "uplink", a gateway has no parent switch, so it was listed nowhere and its speed was unknown
        wan = next(p for p in self.n["Gate-A"]["ports"] if p["port"] == "10")
        self.assertEqual((wan["name"], wan["infra"], wan["server"], wan["speedMbps"]), ("Internet (WAN)", True, False, 1000))
        self.assertEqual(wan["keys"], [["" + self.n["Gate-A"]["id"], "Port 10"]])

    def test_a_ports_that_lead_to_other_devices_and_the_uplink_are_not_listed_as_endpoints(self):
        self.assertEqual([p["port"] for p in self.n["Core-B"]["ports"]], ["13"], "7 is the access point, 9 and 25 lead to switches, 26 is the way up")
        self.assertEqual(self.n["Core-B"]["ports"][0]["name"], "TV-Three")

    def test_bonded_ports_are_one_endpoint_with_their_traffic_added_and_a_server_is_named_by_its_card(self):
        by = {p["port"]: p for p in self.n["Rack-C"]["ports"]}
        lag = by["5+6"]
        self.assertEqual((lag["name"], lag["server"], lag["speedMbps"]), ("Server-Nas", True, 20000), "the client sits on port 6 but the pair is one link")
        self.assertEqual((lag["down"], lag["up_bps"], lag["errors"]), (6000, 400, 3), "what the switch sends to it, and what it sends")

    def test_several_clients_on_one_port_and_a_server_found_only_by_the_last_address_seen(self):
        by = {p["port"]: p for p in self.n["Rack-C"]["ports"]}
        self.assertEqual(by["3"]["name"], "Mini-Two and 1 more")
        self.assertEqual((by["8"]["name"], by["8"]["server"]), ("Server-Spare", True))

    def test_a_switch_found_over_snmp_is_marked_so_it_is_not_taken_for_a_server(self):
        r = report()
        for d in r[0]["report"]["devices"]:
            if d["name"] == "Rack-C":
                d["ports"].append(port(9, lastMac="..:cc:dd:ee"))
        r.append({"connection": "s3", "module": "snmp", "report": {"sysName": "Agg-Switch", "ports": [{"name": "1", "mac": "..:cc:dd:ee", "learned": 12, "lldp": {"name": "Rack-C"}}]}})
        by = {p["port"]: p for p in {x["id"]: x for x in lanmap.build(r)["nodes"]}["Rack-C"]["ports"]}
        self.assertEqual((by["9"]["name"], by["9"]["infra"]), ("Agg-Switch", True))
        self.assertFalse(by["8"]["infra"], "an ordinary server on a port is not marked")

    def test_an_access_point_counts_its_wifi_clients_and_a_device_that_is_not_settled_is_degraded(self):
        self.assertEqual(self.n["AP-E"]["wifi"], 2)
        self.assertEqual((self.n["Edge-D"]["state"], self.n["Edge-D"]["stateWord"]), ("degraded", "provisioning"))
        self.assertEqual(self.n["Core-B"]["state"], "healthy")
        self.assertEqual(self.m["counts"], {"devices": 5, "wired": 5, "wifi": 2})

    def test_with_nothing_to_map_it_says_so_and_a_login_that_cannot_read_clients_is_noted(self):
        self.assertEqual(lanmap.build([])["nodes"], [])
        self.assertIn("UniFi", lanmap.build([])["notes"][0])
        self.assertIn("SNMP switches", lanmap.build([])["notes"][0])      # wording changed (owner approved): the map can be built from SNMP switches alone
        src = report(); src[0]["report"].pop("clients"); src[0]["report"]["clientsNote"] = "refused"
        out = lanmap.build(src)
        self.assertTrue(any("client list" in n for n in out["notes"]))
        self.assertEqual({x["id"]: x for x in out["nodes"]}["Core-B"]["ports"][0]["name"], "", "without the client list a port is listed but not named")


class SameNames(unittest.TestCase):
    """A switch and an access point can both be called "Lobby" (real sites do this). The map ties devices together by address, not name."""
    def build(self, with_macs=True):
        mk = lambda m: m if with_macs else ""
        devs = [
            {"name": "Gate-A", "mac": mk("..:00:00:01"), "type": "udm", "state": "connected", "uplink": {"type": "wire"}, "ports": [port(11)]},
            {"name": "Lobby", "mac": mk("..:00:00:02"), "model": "SW", "type": "usw", "state": "connected",
             "uplink": {"type": "wire", "to": "Gate-A", "toMac": mk("..:00:00:01"), "speedMbps": 10000, "up": True, "remotePort": 11, "port": 9}, "ports": [port(9, is_uplink=True), port(4)]},
            {"name": "Lobby", "mac": mk("..:00:00:03"), "model": "APX", "type": "uap", "state": "connected",
             "uplink": {"type": "wire", "to": "Lobby", "toMac": mk("..:00:00:02"), "speedMbps": 2500, "up": True, "remotePort": 4, "port": 1}, "ports": []},
            {"name": "Yard", "mac": mk("..:00:00:04"), "model": "APX", "type": "uap", "state": "connected",
             "uplink": {"type": "wire", "to": "Lobby", "toMac": mk("..:00:00:02"), "speedMbps": 1000, "up": True, "remotePort": 5, "port": 1}, "ports": []},
        ]
        return lanmap.build([{"connection": "u", "module": "unifi-network", "report": {"devices": devs}}])["nodes"]

    def test_same_named_devices_are_separate_nodes_with_the_right_parents_and_no_node_is_its_own_parent(self):
        nodes = self.build()
        self.assertEqual(len({n["id"] for n in nodes}), 4, "every device has its own id")
        by_kind = {(n["name"], n["kind"]): n for n in nodes}
        sw, ap, yard = by_kind[("Lobby", "switch")], by_kind[("Lobby", "ap")], by_kind[("Yard", "ap")]
        self.assertEqual((sw["parent"], ap["parent"], yard["parent"]), (by_kind[("Gate-A", "gateway")]["id"], sw["id"], sw["id"]))
        self.assertTrue(all(n["parent"] != n["id"] for n in nodes))
        self.assertEqual(ap["link"]["to"], "Lobby"); self.assertEqual(ap["link"]["parentPort"], 4)
        self.assertEqual([p["port"] for p in sw["ports"]], [], "the access point's port is not listed as a device on the switch")

    def test_without_addresses_a_name_that_is_not_unique_is_left_unattached_rather_than_looped(self):
        nodes = self.build(with_macs=False)
        for n in nodes:
            self.assertNotEqual(n["parent"], n["id"])
        ap = [n for n in nodes if n["kind"] == "ap" and n["name"] == "Lobby"][0]
        self.assertIsNone(ap["parent"], "two devices share the name and no address says which: not guessed")


if __name__ == "__main__":
    unittest.main()


def sw(cid, sysname, host, ports):
    return {"connection": cid, "module": "snmp", "name": cid.upper(), "host": host, "report": {"sysName": sysname, "ports": ports}}


def sp(idx, learned=0, lldp=None, label=None, speed=1000, **kw):
    return dict({"ifIndex": str(idx), "name": f"Gi1/0/{idx}", "state": "up", "speedMbps": speed, "learned": learned, **({"lldp": lldp} if lldp else {}), **({"label": label} if label else {})}, **kw)


class SnmpSwitchesOnTheMap(unittest.TestCase):
    """SNMP switches UniFi does not know are map nodes too (#292): ports, speeds, the link between switches from LLDP, and what is behind each port from what it learned."""
    def two(self):
        a = sw("a", "swa", "192.0.2.51", [sp(1, 10, {"name": "swb", "port": "Gi1/0/1"}, speed=10000), sp(2, 1, label="Desk"), sp(3, 3)])
        b = sw("b", "swb", "192.0.2.52", [sp(1, 9, {"name": "swa", "port": "Gi1/0/1"}, speed=10000), sp(2, 0, {"name": "AP-One"}), sp(5, 1)])
        return [a, b]

    def test_with_no_unifi_the_switches_are_nodes_and_the_one_with_most_learned_is_the_top(self):
        m = lanmap.build(self.two())
        n = {x["id"]: x for x in m["nodes"]}
        self.assertEqual(sorted(n), ["snmp:a", "snmp:b"], "ids are the ones the port watch reads them under")
        self.assertIsNone(n["snmp:a"]["parent"])
        self.assertEqual(n["snmp:b"]["parent"], "snmp:a")
        link = n["snmp:b"]["link"]
        self.assertEqual((link["to"], link["speedMbps"], link["port"], link["parentPort"]), ("swa", 10000, 1, 1))
        self.assertEqual(link["keys"], {"self": ["snmp:b", "Gi1/0/1"], "parent": ["snmp:a", "Gi1/0/1"]})
        self.assertEqual(m["counts"]["devices"], 2)

    def test_what_is_behind_a_port_comes_from_the_neighbour_and_the_addresses_learned(self):
        n = {x["id"]: x for x in lanmap.build(self.two())["nodes"]}
        a = {p["port"]: p["name"] for p in n["snmp:a"]["ports"]}
        self.assertEqual(a, {"2": "Desk", "3": "unnamed device and 2 more"}, "the link to swb is not listed as an endpoint")
        b = {p["port"]: p["name"] for p in n["snmp:b"]["ports"]}
        self.assertEqual(b, {"2": "AP-One", "5": "unnamed device"})

    def test_a_switch_unifi_also_knows_is_drawn_once_by_address_by_name_and_by_the_samplers_answer(self):
        unifi = {"connection": "u", "module": "unifi-network", "report": {"devices": [
            {"name": "Core-B", "type": "usw", "state": "connected", "ip": "192.0.2.2", "mac": "..:00:00:02", "ports": [port(1)]},
            {"name": "Rack-C", "type": "usw", "state": "connected", "ip": "192.0.2.3", "mac": "..:00:00:03", "ports": [port(1)]},
            {"name": "Edge-D", "type": "usw", "state": "connected", "ip": "192.0.2.4", "mac": "..:00:00:04", "ports": [port(1)]}], "clients": []}}
        by_ip = sw("x1", "whatever", "192.0.2.2", [sp(1, 3)])
        by_name = sw("x2", "Rack C", "192.0.2.99", [sp(1, 3)])
        by_sampler = sw("x3", "other", "192.0.2.98", [sp(1, 3)])
        own = sw("x4", "Lone-Switch", "192.0.2.97", [sp(1, 3)])
        m = lanmap.build([unifi, by_ip, by_name, by_sampler, own], matched={"x3": "..:00:00:04"})
        self.assertEqual(sorted(x["name"] for x in m["nodes"]), ["Core-B", "Edge-D", "Lone-Switch", "Rack-C"], "four nodes, not seven")

    def test_a_switch_below_a_unifi_device_hangs_off_it(self):
        unifi = {"connection": "u", "module": "unifi-network", "report": {"devices": [
            {"name": "Core-B", "type": "usw", "state": "connected", "ip": "192.0.2.2", "mac": "..:00:00:02", "ports": [port(9)]}], "clients": []}}
        below = sw("x", "swx", "192.0.2.60", [sp(1, 20, {"name": "Core-B", "port": "9"}), sp(2, 1)])
        n = {x["id"]: x for x in lanmap.build([unifi, below])["nodes"]}
        self.assertEqual(n["snmp:x"]["parent"], "..:00:00:02")
        self.assertEqual(n["snmp:x"]["link"]["to"], "Core-B")

    def test_a_server_that_learns_nothing_is_not_a_node(self):
        server = sw("s", "nas", "192.0.2.70", [{"ifIndex": "2", "name": "eth0", "state": "up", "mac": "..:aa:aa:aa"}])
        self.assertEqual(lanmap.build([server] + self.two())["counts"]["devices"], 2)
        self.assertEqual(lanmap.build([server])["nodes"], [])
