"""SNMP checks by NAME (issue #10). The headline regression: the server's drive layout changes, the
numeric indexes move, and monitoring must still read the volume it was told to watch."""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snmp_fake as F  # noqa: E402
import snmplib as L  # noqa: E402
import checks as C  # noqa: E402

HR = "1.3.6.1.2.1.25.2.3.1"
FIXED = "1.3.6.1.2.1.25.2.1.4"


def volume_rows(layout):
    """layout: [(index, name, used_units, total_units)] -> hrStorage rows (4 KiB units)."""
    mib = {}
    for i, name, used, total in layout:
        mib.update({f"{HR}.2.{i}": ("oid", FIXED), f"{HR}.3.{i}": name, f"{HR}.4.{i}": 4096, f"{HR}.5.{i}": total, f"{HR}.6.{i}": used})
    return mib


def conn(agent, cid):
    return {"id": cid, "host": "127.0.0.1", "port": agent.port, "version": "2c", "community": "fake-community", "timeout": 1, "retries": 0}


class LanReport(unittest.TestCase):
    def test_ports_rates_labels_learned_addresses_and_neighbours_are_reported_and_down_ports_are_only_counted(self):
        import threading, time
        X = "1.3.6.1.2.1.31.1.1.1"
        N, ALIAS, SPD, HCI, HCO, OPER = f"{X}.1", f"{X}.18", f"{X}.15", f"{X}.6", f"{X}.10", "1.3.6.1.2.1.2.2.1.8"
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {"1.3.6.1.2.1.1.5.0": "switch-one", "1.3.6.1.2.1.1.1.0": "Fake switch OS 1.2",
                     f"{N}.1": "port1", f"{N}.2": "port2", f"{N}.3": "port3", f"{N}.4": "veth9f3", f"{OPER}.1": 1, f"{OPER}.2": 1, f"{OPER}.3": 2, f"{OPER}.4": 1,
                     "1.3.6.1.2.1.2.2.1.6.2": bytes([0xaa, 0xbb, 0xcc, 0x10, 0x20, 0x30]),
                     f"{ALIAS}.2": "Uplink to core", f"{SPD}.1": ("gauge", 1000), f"{SPD}.2": ("gauge", 10000),
                     f"{HCI}.1": ("c64", 1000), f"{HCO}.1": ("c64", 1000), f"{HCI}.2": ("c64", 5000), f"{HCO}.2": ("c64", 9000),
                     "1.3.6.1.2.1.17.1.4.1.2.11": 1, "1.3.6.1.2.1.17.1.4.1.2.12": 2,
                     "1.3.6.1.2.1.17.4.3.1.2.2.0.0.0.0.1": 12, "1.3.6.1.2.1.17.4.3.1.2.2.0.0.0.0.2": 12, "1.3.6.1.2.1.17.4.3.1.2.2.0.0.0.0.3": 11,
                     f"{C.LLDP_REM}.9.0.2.1": "core-one", f"{C.LLDP_REM}.5.0.2.1": bytes([0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff]), f"{C.LLDP_REM}.7.0.2.1": "gi1/0/9"}
        stop = threading.Event(); self.addCleanup(stop.set)
        def traffic():
            n = 0
            while not stop.wait(0.05):
                n += 1; agent.mib[f"{HCI}.2"] = ("c64", 5000 + n * 12_500); agent.mib[f"{HCO}.2"] = ("c64", 9000 + n * 25_000)
        threading.Thread(target=traffic, daemon=True).start()
        r = C.lan_report(conn(agent, "sw"), wait=0.4)
        self.assertEqual((r["sysName"], r["sysDescr"]), ("switch-one", "Fake switch OS 1.2"))
        self.assertEqual([p["name"] for p in r["ports"]], ["port1", "port2"])
        self.assertEqual((r["downPorts"], r["virtualPorts"]), (1, 1), "a container's interface is not part of the LAN")
        p2 = r["ports"][1]
        self.assertEqual(p2["mac"], "..:10:20:30", "the card's address, shortened, so a server can be matched to its switch port")
        self.assertEqual((p2["label"], p2["speedMbps"], p2["state"]), ("Uplink to core", 10000, "up"))
        self.assertGreater(p2["inBps"], 0); self.assertGreater(p2["outBps"], p2["inBps"], "more went out than came in")
        self.assertEqual(r["ports"][0].get("inBps"), 0)
        self.assertEqual((r["ports"][1]["learned"], r["ports"][0]["learned"]), (2, 1), "addresses are counted per port, through the bridge-port to interface map")
        self.assertEqual(p2["lldp"], {"name": "core-one", "chassis": "..:dd:ee:ff", "port": "gi1/0/9"})
        self.assertNotIn("aa:bb", json.dumps(r)); self.assertNotIn("veth", json.dumps(r)); self.assertNotIn("fake-community", json.dumps(r))

    def test_a_device_that_offers_less_says_so_in_notes_instead_of_failing(self):
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {"1.3.6.1.2.1.31.1.1.1.1.1": "eth0", "1.3.6.1.2.1.2.2.1.8.1": 1}
        r = C.lan_report(conn(agent, "plain"), wait=0.01)
        self.assertEqual([p["name"] for p in r["ports"]], ["eth0"])
        self.assertTrue(any("LLDP" in n for n in r["notes"]) and any("traffic counters" in n for n in r["notes"]) and any("learned" in n for n in r["notes"]), r["notes"])


class Probe(unittest.TestCase):
    def test_a_device_that_answers_with_this_login_is_ok_and_a_wrong_login_or_no_device_is_not_and_nothing_raises(self):
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {"1.3.6.1.2.1.1.5.0": "switch-probe"}
        self.assertEqual(C.probe(conn(agent, "p")), {"ok": True, "sysName": "switch-probe"})
        bad = C.probe({**conn(agent, "p"), "community": "fake-wrong-community"})
        self.assertFalse(bad["ok"]); self.assertNotIn("fake-wrong-community", json.dumps(bad))
        dead = F.Agent(community="fake-community"); port = dead.port; dead.close()
        self.assertFalse(C.probe({**conn(agent, "p"), "port": port})["ok"])
        self.assertFalse(C.probe({"id": "x"})["ok"], "no host is an answer, not a crash")


class Counters(unittest.TestCase):
    def test_every_real_interface_is_read_in_one_go_virtual_ones_are_left_out_and_32_bit_devices_are_marked(self):
        X = "1.3.6.1.2.1.31.1.1.1"
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {f"{X}.1.1": "port1", f"{X}.1.2": "port2", f"{X}.1.3": "veth9", f"{X}.6.1": ("c64", 111), f"{X}.10.1": ("c64", 222), f"{X}.15.1": ("gauge", 1000),
                     f"{X}.6.2": ("c64", 333), f"{X}.10.2": ("c64", 444), f"{X}.6.3": ("c64", 1), f"{X}.10.3": ("c64", 2), f"{X}.18.1": "Port 1"}
        self.assertEqual(C.counters(conn(agent, "cnt")), {"ports": {"port1": {"in": 111, "out": 222, "bits": 64, "speedMbps": 1000, "label": "Port 1"}, "port2": {"in": 333, "out": 444, "bits": 64}}, "sysName": "", "macs": []})
        old = F.Agent(community="fake-community"); self.addCleanup(old.close)
        old.mib = {f"{X}.1.1": "eth0", "1.3.6.1.2.1.2.2.1.10.1": 7, "1.3.6.1.2.1.2.2.1.16.1": 8}
        self.assertEqual(C.counters(conn(old, "cnt2")), {"ports": {"eth0": {"in": 7, "out": 8, "bits": 32}}, "sysName": "", "macs": []})


    def test_error_and_discard_counters_come_along_when_the_device_has_them(self):
        X, T = "1.3.6.1.2.1.31.1.1.1", "1.3.6.1.2.1.2.2.1"
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {f"{X}.1.1": "port1", f"{X}.6.1": ("c64", 111), f"{X}.10.1": ("c64", 222), f"{T}.14.1": 31, f"{T}.20.1": 42, f"{T}.13.1": 53, f"{T}.19.1": 64,
                     f"{X}.1.2": "port2", f"{X}.6.2": ("c64", 333), f"{X}.10.2": ("c64", 444), f"{T}.14.2": 7}
        got = C.counters(conn(agent, "cnt3"))["ports"]
        self.assertEqual({k: got["port1"][k] for k in ("rxErr", "txErr", "rxDrop", "txDrop")}, {"rxErr": 31, "txErr": 42, "rxDrop": 53, "txDrop": 64}, "each counter keeps its own value")
        self.assertEqual({k: got["port2"][k] for k in got["port2"] if k.endswith(("Err", "Drop"))}, {"rxErr": 7}, "only what the device answered")

    def test_packet_counts_come_along_as_the_sum_of_unicast_multicast_and_broadcast_each_with_its_own_value(self):
        X = "1.3.6.1.2.1.31.1.1.1"
        agent = F.Agent(community="fake-community"); self.addCleanup(agent.close)
        agent.mib = {f"{X}.1.1": "port1", f"{X}.6.1": ("c64", 111), f"{X}.10.1": ("c64", 222),
                     f"{X}.7.1": ("c64", 1001), f"{X}.8.1": ("c64", 2002), f"{X}.9.1": ("c64", 3004),      # received: unicast, multicast, broadcast
                     f"{X}.11.1": ("c64", 4008), f"{X}.12.1": ("c64", 5016), f"{X}.13.1": ("c64", 6032),    # sent
                     f"{X}.1.2": "port2", f"{X}.6.2": ("c64", 333), f"{X}.10.2": ("c64", 444), f"{X}.7.2": ("c64", 9), f"{X}.8.2": ("c64", 8)}  # port2 answers only some
        got = C.counters(conn(agent, "cnt4"))["ports"]
        self.assertEqual((got["port1"]["rxPkts"], got["port1"]["txPkts"]), (1001 + 2002 + 3004, 4008 + 5016 + 6032))
        self.assertNotIn("rxPkts", got["port2"], "a device that gives only some of the six counters gives no total: a wrong share is worse than none")


class CountersQuick(unittest.TestCase):
    """#299: after the first reading the counters ask for the real interfaces by index instead of walking every table again."""
    X, T = "1.3.6.1.2.1.31.1.1.1", "1.3.6.1.2.1.2.2.1"

    def agent(self):
        a = F.Agent(community="fake-community"); self.addCleanup(a.close)
        X, T = self.X, self.T
        a.mib = {f"{X}.1.1": "port1", f"{X}.1.2": "port2", f"{X}.1.3": "veth9", f"{X}.6.1": ("c64", 111), f"{X}.10.1": ("c64", 222), f"{X}.15.1": ("gauge", 1000),
                 f"{X}.6.2": ("c64", 333), f"{X}.10.2": ("c64", 444), f"{X}.6.3": ("c64", 1), f"{X}.10.3": ("c64", 2), f"{X}.18.1": "Port 1",
                 f"{T}.14.1": 31, f"{T}.20.1": 42, f"{T}.13.1": 53, f"{T}.19.1": 64}
        return a

    def test_the_second_reading_gives_the_same_shape_with_new_numbers_and_does_not_walk(self):
        a = self.agent(); c = conn(a, "quick1")
        first = C.counters(c)
        walks = sum(1 for t, _ in a.requests if t != L.GET)
        self.assertGreater(walks, 0)
        a.mib[f"{self.X}.6.1"] = ("c64", 999); a.mib[f"{self.T}.14.1"] = 77
        second = C.counters(c)
        self.assertEqual(sum(1 for t, _ in a.requests if t != L.GET), walks, "no table walk the second time")
        self.assertEqual(set(second["ports"]), set(first["ports"]))
        self.assertEqual((second["ports"]["port1"]["in"], second["ports"]["port1"]["rxErr"]), (999, 77))
        self.assertEqual(second["ports"]["port1"]["txErr"], 42, "each counter keeps its own value")
        self.assertEqual(second["ports"]["port1"]["label"], "Port 1")
        self.assertNotIn("veth9", second["ports"])

    def test_the_interface_addresses_come_with_the_counters_shortened_and_remembered(self):
        a = self.agent(); c = conn(a, "quick11")
        a.mib[f"{self.T}.6.1"] = bytes([0x11, 0x22, 0x33, 0xaa, 0xbb, 0xcc])
        a.mib[f"{self.T}.6.2"] = bytes([0x11, 0x22, 0x33, 0xaa, 0xbb, 0xcd])
        self.assertEqual(C.counters(c)["macs"], ["..:aa:bb:cc", "..:aa:bb:cd"])
        self.assertEqual(C.counters(c)["macs"], ["..:aa:bb:cc", "..:aa:bb:cd"], "kept with the layout")

    def test_a_link_says_how_long_ago_it_last_changed(self):
        a = self.agent(); c = conn(a, "quick12")
        a.mib["1.3.6.1.2.1.1.3.0"] = 100_000                              # up for 1,000 seconds
        a.mib[f"{self.T}.9.1"] = 70_000                                   # port1 changed at 700 s: 300 s ago
        first = C.counters(c)
        self.assertEqual(first["ports"]["port1"]["changedAgo"], 300)
        self.assertEqual(first["uptimeS"], 1000)
        self.assertNotIn("changedAgo", first["ports"]["port2"], "no last-change time: nothing invented")
        a.mib["1.3.6.1.2.1.1.3.0"] = 100_500; a.mib[f"{self.T}.9.1"] = 100_000
        self.assertEqual(C.counters(c)["ports"]["port1"]["changedAgo"], 5, "a link that just changed")

    def test_a_bond_and_a_vlan_are_stacked_and_the_cards_under_a_bond_say_so(self):
        a = self.agent(); c = conn(a, "quick13")
        X, T, S = self.X, self.T, "1.3.6.1.2.1.31.1.2.1.3"
        a.mib.update({f"{X}.1.4": "bond0", f"{X}.6.4": ("c64", 5), f"{X}.10.4": ("c64", 6), f"{X}.1.5": "port2.100", f"{X}.6.5": ("c64", 7), f"{X}.10.5": ("c64", 8),
                      f"{S}.4.1": 1, f"{S}.4.2": 1, f"{S}.5.2": 1, f"{S}.0.4": 1, f"{S}.0.5": 1, f"{S}.0.1": 1})        # bond0 (4) over port1 and port2; a VLAN (5) over port2 alone
        got = C.counters(c)["ports"]
        self.assertTrue(got["bond0"]["stacked"] and got["port2.100"]["stacked"])
        self.assertEqual(got["port1"]["bond"], ["bond0"])
        self.assertEqual(got["port2"]["bond"], ["bond0"], "a VLAN over a single card is not a bond: only the bond is named")
        self.assertNotIn("stacked", got["port1"])
        self.assertEqual(C.counters(c)["ports"]["port1"]["bond"], ["bond0"], "remembered with the layout")

    def test_the_devices_own_name_comes_with_the_counters_first_read_and_after(self):
        a = self.agent(); c = conn(a, "quick10")
        a.mib["1.3.6.1.2.1.1.5.0"] = "Switch2"
        self.assertEqual(C.counters(c)["sysName"], "Switch2")
        before = len(a.requests)
        self.assertEqual(C.counters(c)["sysName"], "Switch2", "remembered with the layout: no extra request on the quick reads")
        self.assertTrue(all(o != "1.3.6.1.2.1.1.5.0" for t, oids in a.requests[before:] if t == L.GET for o in oids))

    def test_only_the_asked_for_ports_are_read_after_the_first_reading(self):
        a = self.agent(); c = conn(a, "quick9")
        full = C.counters(c)["ports"]
        self.assertEqual(set(full), {"port1", "port2"})
        before = len(a.requests)
        got = C.counters(c, only=["Port 1"])["ports"]                    # by the label, as the App knows the port
        self.assertEqual(set(got), {"port1"})
        asked = [o for t, oids in a.requests[before:] if t == L.GET for o in oids if o != "1.3.6.1.2.1.1.3.0"]       # the device's uptime is asked on every read (it dates link changes): not a port
        self.assertTrue(asked and all(o.rsplit(".", 1)[1] == "1" for o in asked), "port2 was not asked for")
        self.assertEqual(set(C.counters(c, only=["no such port"])["ports"]), {"port1", "port2"}, "nothing matched: read them all")

    def test_a_server_with_hundreds_of_container_interfaces_is_not_walked_column_by_column(self):
        a = self.agent(); c = conn(a, "quick5")
        for i in range(10, 410):
            a.mib[f"{self.X}.1.{i}"] = f"veth{i:x}"
            a.mib[f"{self.X}.6.{i}"] = ("c64", i); a.mib[f"{self.X}.10.{i}"] = ("c64", i)
        got = C.counters(c)["ports"]
        self.assertEqual(set(got), {"port1", "port2"})
        asked = [oid for t, oids in a.requests for oid in oids if t == L.GET]
        self.assertTrue(all(int(o.rsplit(".", 1)[1]) < 10 for o in asked), "only the real interfaces' counters were asked for")
        bulks = [t for t, _ in a.requests if t != L.GET]
        self.assertLessEqual(len(bulks), 40, "one walk of the names, not one per column")

    def test_interfaces_without_counters_are_only_asked_for_their_counters_on_the_first_read(self):
        a = self.agent(); c = conn(a, "quick6")
        for i in range(10, 210):
            a.mib[f"{self.X}.1.{i}"] = f"sw0.{i}"                       # a name that is not "virtual" but has no counters
        got = C.counters(c)["ports"]
        self.assertEqual(set(got), {"port1", "port2"})
        asked = [o for t, oids in a.requests if t == L.GET for o in oids]
        extra = [o for o in asked if int(o.rsplit(".", 1)[1]) >= 10]
        self.assertTrue(all(o.startswith((f"{self.X}.6.", f"{self.X}.10.")) for o in extra), "only the two counters were tried on them")

    def test_the_link_state_comes_along_each_time(self):
        a = self.agent(); c = conn(a, "quick4")
        OPER = "1.3.6.1.2.1.2.2.1.8"
        a.mib[f"{OPER}.1"] = 1; a.mib[f"{OPER}.2"] = 2
        got = C.counters(c)["ports"]
        self.assertEqual((got["port1"]["up"], got["port2"]["up"]), (True, False))
        a.mib[f"{OPER}.1"] = 2; a.mib[f"{OPER}.2"] = 1
        got = C.counters(c)["ports"]
        self.assertEqual((got["port1"]["up"], got["port2"]["up"]), (False, True), "the quick reading sees the change")

    def test_a_link_that_negotiates_down_shows_at_once(self):
        a = self.agent(); c = conn(a, "quick2")
        self.assertEqual(C.counters(c)["ports"]["port1"]["speedMbps"], 1000)
        a.mib[f"{self.X}.15.1"] = ("gauge", 100)
        self.assertEqual(C.counters(c)["ports"]["port1"]["speedMbps"], 100)

    def test_an_interface_that_disappears_makes_it_read_the_list_again(self):
        a = self.agent(); c = conn(a, "quick3")
        C.counters(c)
        for k in [k for k in a.mib if k.endswith(".2") and k.startswith(self.X)]:
            del a.mib[k]
        self.assertEqual(set(C.counters(c)["ports"]), {"port1"})


class ByName(unittest.TestCase):
    def setUp(self):
        self.agent = F.Agent(community="fake-community")
        self.addCleanup(self.agent.close)

    def vol(self, cid, name="/data", **p):
        return C.run_check("volume", {"name": name, **p}, conn(self.agent, cid))

    def test_traffic_counters_are_read_by_interface_name_64_bit_first_then_32_bit(self):
        N, HCI, HCO, LI, LO = "1.3.6.1.2.1.31.1.1.1.1", "1.3.6.1.2.1.31.1.1.1.6", "1.3.6.1.2.1.31.1.1.1.10", "1.3.6.1.2.1.2.2.1.10", "1.3.6.1.2.1.2.2.1.16"
        self.agent.mib = {f"{N}.1": "bond0", f"{HCI}.1": ("c64", 5_000_000_000_001), f"{HCO}.1": ("c64", 7_000_000_000_002),
                          f"1.3.6.1.2.1.31.1.1.1.15.1": ("gauge", 10000), f"{N}.2": "eth9", f"{LI}.2": ("c32", 111), f"{LO}.2": ("c32", 222), f"{N}.3": "silent"}
        got = C.sample(conn(self.agent, "t"), ["bond0", "eth9", "silent", "gone"])
        self.assertEqual(got["bond0"], {"in": 5_000_000_000_001, "out": 7_000_000_000_002, "bits": 64, "speedMbps": 10000})
        self.assertEqual(got["eth9"], {"in": 111, "out": 222, "bits": 32})
        self.assertIn("traffic counters", got["silent"]["error"])
        self.assertIn("not on the device", got["gone"]["error"])

    def test_a_filling_volume_is_a_heads_up_first_then_degraded_then_failed(self):
        got = []
        for used in (500, 760, 860, 960):
            self.agent.mib = volume_rows([(1, "/data", used, 1000)])
            r = self.vol("heads")
            got.append((r["state"], bool(r.get("notice"))))
        self.assertEqual(got, [("healthy", False), ("healthy", True), ("degraded", False), ("failed", False)])

    def test_volume_moves_to_a_new_index_and_monitoring_follows_it(self):
        # the #10 regression: /data is index 1 and nearly empty, /scratch is index 2 and full
        self.agent.mib = volume_rows([(1, "/data", 100, 1000), (2, "/scratch", 990, 1000)])
        r = self.vol("reg")
        self.assertEqual(r["state"], "healthy", r)
        self.assertIn("10%", r["detail"])
        # the drive layout changes: the indexes swap places
        self.agent.mib = volume_rows([(1, "/scratch", 990, 1000), (2, "/data", 100, 1000)])
        r = self.vol("reg")
        self.assertEqual(r["state"], "healthy", f"read the wrong disk after the indexes moved: {r}")
        self.assertIn("10%", r["detail"])
        self.assertEqual(self.vol("reg", "/scratch")["state"], "failed")

    def test_a_new_disk_inserted_ahead_shifts_every_index(self):
        self.agent.mib = volume_rows([(1, "/data", 100, 1000)])
        self.assertEqual(self.vol("shift")["state"], "healthy")
        self.agent.mib = volume_rows([(1, "/boot", 990, 1000), (7, "/data", 100, 1000)])
        self.assertEqual(self.vol("shift")["state"], "healthy")

    def test_the_cached_index_is_confirmed_with_one_small_request(self):
        self.agent.mib = volume_rows([(1, "/data", 100, 1000), (2, "/x", 5, 1000)])
        self.vol("cache")
        before = len(self.agent.requests)
        self.vol("cache")
        self.assertEqual(len(self.agent.requests) - before, 1, "should be a single GET, not a walk")

    def test_a_volume_that_is_gone_is_unknown_and_lists_what_exists(self):
        self.agent.mib = volume_rows([(1, "/data", 100, 1000)])
        r = self.vol("gone", "/nope")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("/data", r["detail"])
        self.assertIn("Pick what to watch", r["detail"])      # the message now names the real button (#328)

    def test_thresholds(self):
        self.agent.mib = volume_rows([(1, "/a", 860, 1000), (2, "/b", 960, 1000)])
        self.assertEqual(self.vol("th", "/a")["state"], "degraded")
        self.assertEqual(self.vol("th", "/b")["state"], "failed")
        self.assertEqual(self.vol("th", "/a", warn=90)["state"], "healthy")

    def test_unreachable_device_is_unknown_not_failed(self):
        self.agent.mib = volume_rows([(1, "/data", 1, 1000)])
        self.agent.drop = True
        with self.assertRaises(L.SnmpError):   # main.py turns this into state=unknown
            self.vol("down")

    def test_interface_by_name(self):
        ifn, oper, hs = "1.3.6.1.2.1.31.1.1.1.1", "1.3.6.1.2.1.2.2.1.8", "1.3.6.1.2.1.31.1.1.1.15"
        self.agent.mib = {f"{ifn}.2": "lo", f"{ifn}.3": "eno3", f"{oper}.2": 1, f"{oper}.3": 1, f"{hs}.2": ("gauge", 0), f"{hs}.3": ("gauge", 1000)}
        r = C.run_check("interface", {"name": "eno3"}, conn(self.agent, "if"))
        self.assertEqual(r["state"], "healthy", r)
        self.assertIn("1000 Mbit/s", r["detail"])
        self.assertEqual(C.run_check("interface", {"name": "eno3", "min_speed_mbps": 2500}, conn(self.agent, "if"))["state"], "degraded")
        self.agent.mib[f"{oper}.3"] = 2
        self.assertEqual(C.run_check("interface", {"name": "eno3"}, conn(self.agent, "if"))["state"], "failed")

    def test_uptime_and_resources(self):
        self.agent.mib = {"1.3.6.1.2.1.1.3.0": ("ticks", 8640000 + 360000 + 6000), "1.3.6.1.2.1.1.5.0": "anchor3",
                          "1.3.6.1.4.1.2021.11.11.0": 70, "1.3.6.1.4.1.2021.4.5.0": 1000, "1.3.6.1.4.1.2021.4.6.0": 100,
                          "1.3.6.1.4.1.2021.4.14.0": 50, "1.3.6.1.4.1.2021.4.15.0": 50}
        c = conn(self.agent, "up")
        self.assertIn("up 1d 1h 1m", C.run_check("uptime", {}, c)["detail"])
        r = C.run_check("resources", {}, c)
        self.assertEqual(r["state"], "healthy", r)
        self.assertIn("CPU 30%", r["detail"])
        busy = C.run_check("resources", {"cpu_warn": 20}, c)           # a busy server is doing its job: fine, with a note, never degraded
        self.assertEqual((busy["state"], busy.get("notice")), ("healthy", True))
        self.assertTrue(C.run_check("resources", {}, c).get("notice") is None)

    def test_row_preset_qnap_pool_and_unrecognised_status(self):
        Q = C.Q
        pool = lambda st: {f"{Q}.7.1.2.1": "Pool 1", f"{Q}.7.1.3.1": 1000, f"{Q}.7.1.4.1": 600, f"{Q}.7.1.5.1": st}
        c = conn(self.agent, "q")
        self.agent.mib = pool(0)
        self.assertEqual(C.run_check("row", {"preset": "qnap-pool", "name": "Pool 1"}, c)["state"], "healthy")
        self.agent.mib = pool(-1)
        self.assertEqual(C.run_check("row", {"preset": "qnap-pool", "name": "Pool 1"}, c)["state"], "degraded")
        self.agent.mib = pool(-3)
        self.assertEqual(C.run_check("row", {"preset": "qnap-pool", "name": "Pool 1"}, c)["state"], "failed")
        self.agent.mib = pool(42)
        r = C.run_check("row", {"preset": "qnap-pool", "name": "Pool 1"}, c)
        self.assertEqual(r["state"], "degraded")          # never silently green for a status we do not know
        self.assertIn("unrecognised", r["detail"])

    def disk(self, temp, model="ST20000NM007D", iface="SATA", **params):
        Q = C.Q
        self.agent.mib = {f"{Q}.2.1.5.1": "S7YCNJ0L231814Z", f"{Q}.2.1.7.1": "Good", f"{Q}.2.1.8.1": temp,
                          f"{Q}.2.1.3.1": "Samsung" if "SSD" in model else "Seagate", f"{Q}.2.1.4.1": model, f"{Q}.2.1.6.1": iface}
        return C.run_check("row", {"preset": "qnap-disk", "name": "S7YCNJ0L231814Z", **params}, conn(self.agent, "q"))

    def test_a_warm_hard_drive_says_why_it_is_degraded(self):
        r = self.disk(57)
        self.assertEqual(r["state"], "degraded")
        self.assertEqual(r["detail"], "S7YCNJ0L231814Z: status Good, 57 °C (hot, limit 55 °C)")
        self.assertEqual(self.disk(54)["detail"], "S7YCNJ0L231814Z: status Good, 54 °C")

    def test_an_ssd_gets_a_higher_limit(self):
        # 2026-10-30: Goliath's SSD went Degraded at 55-57 °C with "status Good" during a heavy download
        r = self.disk(57, model="Samsung SSD 870 EVO 4TB")
        self.assertEqual((r["state"], r["detail"]), ("healthy", "S7YCNJ0L231814Z: status Good, SSD, 57 °C"))
        self.assertEqual(self.disk(70, model="Samsung SSD 870 EVO 4TB")["state"], "degraded")
        self.assertEqual(self.disk(60, model="WD Red SN700", iface="NVMe")["state"], "healthy", "an NVMe disk is an SSD whatever its model says")

    def test_a_disks_own_limit_wins(self):
        self.assertEqual(self.disk(57, model="Samsung SSD 870 EVO 4TB", max_c=50)["detail"], "S7YCNJ0L231814Z: status Good, SSD, 57 °C (hot, limit 50 °C)")
        self.assertEqual(self.disk(60, max_c=65)["state"], "healthy")

    def test_no_temperature_reading_is_not_shown(self):
        self.assertEqual(self.disk(-1)["detail"], "S7YCNJ0L231814Z: status Good")

    def test_discover_lists_current_names(self):
        self.agent.mib = volume_rows([(3, "/data", 100, 1000), (9, "/scratch", 5, 1000)])
        ifn, oper = "1.3.6.1.2.1.31.1.1.1.1", "1.3.6.1.2.1.2.2.1.8"
        self.agent.mib.update({f"{ifn}.1": "lo", f"{ifn}.2": "eno3", f"{ifn}.3": "veth61b3eaf", f"{ifn}.4": "br-af895ed7cbb8",
                               f"{oper}.1": 1, f"{oper}.2": 1, f"{oper}.3": 1, f"{oper}.4": 1})
        self.agent.mib.update(volume_rows([(20, "/run", 0, 1000), (21, "/mnt/HDA_ROOT", 5, 1000), (22, "/share/ZFS2_DATA/Public/@Recently-Snapshot", 0, 1000)]))
        d = C.discover(conn(self.agent, "disc"))
        self.assertEqual(sorted(v["name"] for v in d["volumes"]), ["/data", "/mnt/HDA_ROOT", "/scratch", "/share/ZFS2_DATA/Public/@Recently-Snapshot"])   # /run is dropped
        self.assertEqual([i["name"] for i in d["interfaces"]], ["eno3"])                      # containers and loopback are noise
        sysnames = {x["label"] for x in d["suggest"] if x.get("system")}
        self.assertEqual(sysnames, {"Volume /mnt/HDA_ROOT", "Volume /share/ZFS2_DATA/Public/@Recently-Snapshot"})   # tucked away, not lost
        labels = [x["label"] for x in d["suggest"]]
        self.assertEqual(labels[0], "Reachable (uptime)")
        self.assertIn("Interface eno3", labels)
        self.assertIn("Volume /data", labels)
        one = next(x for x in d["suggest"] if x["label"] == "Volume /data")
        self.assertEqual((one["check"], one["params"]), ("volume", {"name": "/data"}))   # runs as-is through run_check
        self.assertEqual(C.run_check(one["check"], one["params"], conn(self.agent, "disc"))["state"], "healthy")


if __name__ == "__main__":
    unittest.main()
