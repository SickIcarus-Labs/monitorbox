"""#321: a big switch lists hundreds of interfaces that are not ports (empty stack slots, tunnels). They must not be read, and nothing real may be lost."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snmp_fake as F  # noqa: E402
import snmplib as L  # noqa: E402
import checks as C  # noqa: E402

X, T = "1.3.6.1.2.1.31.1.1.1", "1.3.6.1.2.1.2.2.1"


def conn(agent, cid):
    return {"id": cid, "host": "127.0.0.1", "port": agent.port, "version": "2c", "community": "fake-community", "timeout": 2, "retries": 0}


def switch(empty=91, tunnels=5):
    """Indexes 1-3 real ports (up, up, down), 4 a port-channel, 5.. empty slots (notPresent), then tunnels. Every value differs."""
    m = {}
    def iface(i, name, typ, oper, hc=True):
        m.update({f"{X}.1.{i}": name, f"{T}.3.{i}": typ, f"{T}.8.{i}": oper})
        if hc:
            m.update({f"{X}.6.{i}": ("c64", 1000 + i), f"{X}.10.{i}": ("c64", 5000 + i), f"{X}.15.{i}": ("gauge", 100 * i), f"{X}.18.{i}": f"label {i}",
                      f"{T}.14.{i}": 10 + i, f"{T}.20.{i}": 20 + i, f"{T}.13.{i}": 30 + i, f"{T}.19.{i}": 40 + i})
    iface(1, "gi1/0/1", 6, 1); iface(2, "gi1/0/2", 6, 1); iface(3, "gi1/0/3", 6, 2); iface(4, "Po1", 161, 1)
    for i in range(5, 5 + empty):
        iface(i, f"gi2/0/{i}", 6, 6)
    for i in range(5 + empty, 5 + empty + tunnels):
        iface(i, f"Tunnel{i}", 131, 1)
    return m


class Phantom(unittest.TestCase):
    def agent(self, mib):
        a = F.Agent(community="fake-community"); self.addCleanup(a.close)
        a.mib = mib
        return a

    def asked_indexes(self, a, cols):
        return {int(o.rsplit(".", 1)[1]) for t, oids in a.requests if t == L.GET for o in oids if o.rsplit(".", 1)[0] in cols}

    def test_counters_first_read_skips_empty_slots_and_tunnels_and_keeps_the_real_ports_and_the_port_channel(self):
        a = self.agent(switch())
        got = C.counters(conn(a, "ph1"))["ports"]
        self.assertEqual(set(got), {"gi1/0/1", "gi1/0/2", "gi1/0/3", "Po1"}, "a down port and a port-channel are real")
        self.assertEqual((got["gi1/0/2"]["in"], got["gi1/0/2"]["out"], got["gi1/0/2"]["rxErr"], got["gi1/0/2"]["txDrop"]), (1002, 5002, 12, 42))
        self.assertEqual((got["Po1"]["in"], got["Po1"]["label"]), (1004, "label 4"))
        asked = self.asked_indexes(a, {f"{X}.6", f"{X}.10"})
        self.assertTrue(asked and asked <= {1, 2, 3, 4}, f"counters were asked for {sorted(asked)}")

    def test_the_first_reading_asks_for_addresses_only_of_real_ports_and_reads_the_types_once(self):
        m = switch()
        for i in range(1, 101):
            m[f"{T}.6.{i}"] = bytes([0xaa, 0xbb, 0xcc, 0x00, 0x01, i])
        a = self.agent(m)
        r = C.counters(conn(a, "ph8"))
        self.assertEqual(set(r["macs"]), {f"..:00:01:{i:02x}" for i in (1, 2, 3, 4)}, "the addresses of the four real interfaces, none from empty slots")
        self.assertEqual(self.asked_indexes(a, {f"{T}.6"}), {1, 2, 3, 4})
        walks = [oids[0] for t, oids in a.requests if t != L.GET]
        first_type_walk = [i for i, w in enumerate(walks) if w == f"{T}.3"]
        self.assertEqual(len(first_type_walk), 1, "the interface types were walked once, not again for the stack")

    def test_lan_report_reads_only_the_real_ports_by_index_and_says_how_many_it_left_out(self):
        a = self.agent(switch())
        r = C.lan_report(conn(a, "ph2"), wait=0)
        self.assertEqual([p["name"] for p in r["ports"]], ["gi1/0/1", "gi1/0/2", "Po1"])      # the down port is only counted, as before
        self.assertEqual((r["downPorts"], r["hiddenPorts"]), (1, 96))
        self.assertEqual(r["ports"][1]["speedMbps"], 200); self.assertEqual(r["ports"][2]["label"], "label 4"); self.assertEqual(r["ports"][1]["inErrors"], 12)
        self.assertTrue(any("96 interfaces" in n for n in r["notes"]), r["notes"])
        every = self.asked_indexes(a, {f"{T}.14", f"{T}.20", f"{X}.15", f"{X}.18", f"{X}.6", f"{X}.10"})
        self.assertTrue(every <= {1, 2, 3, 4}, "no column of a left-out interface was asked for")
        walks = [oids[0] for t, oids in a.requests if t != L.GET]
        self.assertFalse([w for w in walks if w.startswith((f"{T}.14", f"{X}.15", f"{X}.6"))], "the big columns were not walked")

    def test_everything_asked_for_reads_every_interface(self):
        a = self.agent(switch())
        r = C.lan_report(conn(a, "ph3"), wait=0, everything=True)
        self.assertEqual(r["hiddenPorts"], 0)
        self.assertEqual(len(r["ports"]) + r["downPorts"], 100, "all 100 interfaces are there")

    def test_a_small_device_is_read_exactly_as_before(self):
        a = self.agent(switch(empty=10, tunnels=0))      # 14 interfaces: under the limit
        r = C.lan_report(conn(a, "ph4"), wait=0)
        self.assertEqual(r["hiddenPorts"], 0)
        self.assertEqual(len(r["ports"]) + r["downPorts"], 14)

    def test_a_device_that_gives_no_type_or_state_hides_nothing(self):
        m = {k: v for k, v in switch().items() if not k.startswith((f"{T}.3.", f"{T}.8."))}
        a = self.agent(m)
        self.assertEqual(C.lan_report(conn(a, "ph5"), wait=0)["hiddenPorts"], 0)
        self.assertEqual(len(C.counters(conn(a, "ph5b"))["ports"]), 100)

    def test_if_every_interface_looks_absent_nothing_is_hidden(self):
        m = switch()
        for i in range(1, 101):
            m[f"{T}.8.{i}"] = 6
        a = self.agent(m)
        self.assertEqual(C.lan_report(conn(a, "ph6"), wait=0)["hiddenPorts"], 0)

    def test_discover_does_not_offer_empty_slots_and_can_be_told_to(self):
        a = self.agent(switch())
        names = lambda d: [i["name"] for i in d["interfaces"]]
        d = C.discover(conn(a, "ph7"))
        self.assertEqual(names(d), ["gi1/0/1", "gi1/0/2", "gi1/0/3", "Po1"])
        self.assertEqual(d["hiddenInterfaces"], 96)
        self.assertEqual([i["status"] for i in d["interfaces"]], ["up", "up", "down", "up"])
        self.assertEqual(d["interfaces"][1]["speedMbps"], 200)
        self.assertEqual(len(names(C.discover(conn(a, "ph7b"), {"everything": True}))), 100)


if __name__ == "__main__":
    unittest.main()
