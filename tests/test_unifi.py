"""UniFi module: device/health/topology checks, discovery, login behaviour, and the guarantee that it only reads."""
import json, os, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "unifi-network")
sys.path.insert(0, MOD)
from unifi_fake import Controller  # noqa: E402
import unifilib as U  # noqa: E402
import unifichecks as C  # noqa: E402
import importlib.util  # noqa: E402
# every module's entry file is called main.py, so load this one under its own name
_spec = importlib.util.spec_from_file_location("unifi_main", os.path.join(MOD, "main.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


class UnifiChecks(unittest.TestCase):
    def setUp(self):
        self.c = Controller()
        self.addCleanup(self.c.close)
        self.conn = self.c.conn()
        M.CLIENTS.clear()
        U.CACHE_SECONDS = 0

    def run_check(self, kind, **params):
        return M.run_check(kind, params, self.conn)

    def test_the_module_calls_itself_unifi_network(self):
        self.assertEqual(M.handle({"method": "describe", "params": {}})["title"], "UniFi Network")

    def test_device_healthy_with_uptime_and_topology(self):
        r = self.run_check("device", name="Garage")
        self.assertEqual(r["state"], "healthy", r)
        self.assertEqual(r["detail"], "connected · up 1 d · via Switch 2 at 1 Gbps")

    def test_the_lan_report_copies_chosen_fields_counts_unused_ports_shortens_addresses_and_leaves_secrets_out(self):
        agg = next(d for d in self.c.devices if d["name"] == "Aggregation")
        agg.update({"x_authkey": "fake-authkey-71", "x_ssh_override": "fake-sshpw-72",
                    "lldp_table": [{"local_port_idx": 4, "chassis_id": "aa:bb:cc:11:22:33", "port_id": "gi1/0/1"}],
                    "port_table": [{"port_idx": 1, "name": "Granite", "up": True, "speed": 10000, "rx_bytes-r": 125000, "tx_bytes-r": 250, "x_port_secret": "fake-portsecret-73",
                                    "mac_table": [{"mac": "02:00:00:00:00:01", "hostname": "host-one"}, {"mac": "02:00:00:00:00:02"}]},
                                   {"port_idx": 2, "name": "Empty", "up": False},
                                   {"port_idx": 3, "name": "To core", "up": True, "is_uplink": True}]})
        r = M.handle({"method": "lan_report", "params": {"connection": self.conn}})
        self.assertEqual([d["name"] for d in r["devices"]], ["Aggregation", "Bay Harbor", "Garage", "Switch 2"])
        a = r["devices"][0]
        self.assertEqual([p["port_idx"] for p in a["ports"]], [1, 3], "a port with nothing on it is counted, not listed")
        self.assertEqual(a["downPorts"], 1)
        g = a["ports"][0]
        self.assertEqual((g["inBps"], g["outBps"], g["learned"], g["learnedNames"], g["speed"]), (1_000_000, 2_000, 2, ["host-one"], 10000))
        self.assertEqual(a["lldp"], [{"port": 4, "chassis": "..:11:22:33", "remotePort": "gi1/0/1"}])
        self.assertEqual((a["uplink"]["to"], a["uplink"]["speedMbps"]), ("Bay Harbor", 10000))
        self.assertTrue(a["uplink"]["toMac"].startswith("..:") and len(a["uplink"]["toMac"]) == 11, a["uplink"]["toMac"])
        self.assertTrue(a["mac"].startswith("..:") and len(a["mac"]) == 11 and "f4:e2" not in a["mac"], "each device carries its own shortened address, so same-named devices can be told apart")
        self.assertIn("x_authkey", a["deviceKeys"], "the names of the other fields are listed, so we can see what else there is")
        self.assertIn("x_port_secret", a["portKeys"])
        text = json.dumps(r)
        for secret in ("fake-authkey-71", "fake-sshpw-72", "fake-portsecret-73", "aa:bb:cc:11", self.c.password, self.c.username):
            self.assertNotIn(secret, text)

    def test_the_lan_report_names_who_is_plugged_into_which_port_and_still_works_when_the_login_may_not_read_clients(self):
        agg = next(d for d in self.c.devices if d["name"] == "Aggregation")
        garage = next(d for d in self.c.devices if d["name"] == "Garage")
        agg["port_table"] = [{"port_idx": 5, "name": "Port 5", "up": True, "mac_table_count": 3, "link_down_count": 4, "stp_role": "designated",
                              "last_connection": {"mac": "aa:bb:cc:01:02:03", "last_seen": 1}}]
        self.c.clients = [{"name": "Granite", "hostname": "granite-host", "ip": "192.0.2.50", "mac": "aa:bb:cc:01:02:03", "is_wired": True, "sw_mac": agg["mac"], "sw_port": 5,
                           "wired-rx_bytes-r": 1000, "wired-tx_bytes-r": 2500, "x_client_secret": "fake-clientsecret-81"},
                          {"hostname": "phone-one", "ip": "192.0.2.51", "mac": "aa:bb:cc:04:05:06", "is_wired": False, "ap_mac": garage["mac"], "essid": "Fake-Net", "network": "Fake-IoT-Net", "oui": "Fake Maker Co", "rx_bytes-r": 125, "tx_bytes-r": 250}]
        r = M.handle({"method": "lan_report", "params": {"connection": self.conn}})
        wired, wifi = r["clients"]
        self.assertEqual((wired["name"], wired["switch"], wired["port"], wired["rxBps"], wired["txBps"], wired["mac"]), ("Granite", "Aggregation", 5, 8000, 20000, "..:01:02:03"))
        self.assertEqual((wifi["name"], wifi["ap"], wifi["wired"], wifi["rxBps"], wifi["txBps"]), ("phone-one", "Garage", False, 1000, 2000))
        self.assertEqual((wifi.get("network"), wired.get("network")), ("Fake-IoT-Net", None), "the network a client is on is reported, so the app can tell IoT devices apart")
        self.assertEqual((wifi.get("oui"), wired.get("oui")), ("Fake Maker Co", None), "the maker is reported for the hide list")
        p5 = next(d for d in r["devices"] if d["name"] == "Aggregation")["ports"][0]
        self.assertEqual((p5["mac_table_count"], p5["link_down_count"], p5["lastMac"]), (3, 4, "..:01:02:03"), "the port also says what it last saw and how often the link dropped")
        self.assertIn("x_client_secret", r["clientKeys"])
        text = json.dumps(r)
        for secret in ("fake-clientsecret-81", "aa:bb:cc:01", "aa:bb:cc:04"):
            self.assertNotIn(secret, text)
        self.c.clients = None                                  # this login may not read the client list
        M.CLIENTS.clear(); U.CACHE_SECONDS = 0
        r = M.handle({"method": "lan_report", "params": {"connection": self.conn}})
        self.assertNotIn("clients", r); self.assertIn("refused", r["clientsNote"])
        self.assertTrue(r["devices"], "the devices still come back")

    def test_device_names_match_without_caring_about_case_and_mac_works(self):
        self.assertEqual(self.run_check("device", name="switch 2")["state"], "healthy")
        self.assertEqual(self.run_check("device", mac="F4-E2-C6-00-00-03")["state"], "healthy")

    def test_every_device_state(self):
        for code, want in [(1, "healthy"), (0, "failed"), (9, "failed"), (10, "failed"), (4, "degraded"), (5, "degraded"),
                           (6, "degraded"), (2, "degraded"), (11, "degraded"), (99, "degraded")]:
            self.c.devices[3]["state"] = code
            self.assertEqual(self.run_check("device", name="Garage")["state"], want, code)

    def test_a_slow_uplink_or_a_down_uplink_is_degraded(self):
        self.assertEqual(self.run_check("device", name="Garage", min_uplink_mbps=1000)["state"], "healthy")
        r = self.run_check("device", name="Garage", min_uplink_mbps=2500)
        self.assertEqual(r["state"], "degraded")
        self.assertIn("expected at least 2.5 Gbps", r["detail"])
        self.c.devices[3]["uplink"]["up"] = False
        r = self.run_check("device", name="Garage")
        self.assertEqual((r["state"], "uplink to Switch 2 is down" in r["detail"]), ("degraded", True))

    def test_an_available_update_is_information_not_a_problem(self):
        self.c.devices[3]["upgradable"] = True
        r = self.run_check("device", name="Garage")
        self.assertEqual(r["state"], "healthy")
        self.assertIn("update available", r["detail"])

    def test_unknown_device_or_missing_name_is_unknown_and_helpful(self):
        r = self.run_check("device", name="Nope")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("Aggregation", r["detail"])
        self.assertEqual(self.run_check("device")["state"], "unknown")

    def test_roll_up_of_all_devices(self):
        self.assertEqual(self.run_check("devices")["detail"], "4 of 4 devices connected")
        self.c.devices[3]["state"] = 0
        r = self.run_check("devices")
        self.assertEqual((r["state"], r["detail"]), ("failed", "3 of 4 devices connected · disconnected: Garage"))
        self.c.devices[3]["state"] = 4
        self.assertEqual(self.run_check("devices")["state"], "degraded")
        self.assertEqual(self.run_check("devices", names=["Bay Harbor"])["state"], "healthy")     # only those named

    def test_internet_verdict_shows_what_it_is_based_on(self):
        www = next(h for h in self.c.health if h["subsystem"] == "www")
        www.update({"status": "warning", "latency": 0, "drops": 7, "uptime": 0, "speedtest_status": "Idle", "gw_mac": "aa:bb:cc:00:11:22", "xput_up": 5.5})
        r = self.run_check("health", subsystem="www")
        self.assertEqual(r["state"], "unknown", "a warning with no latency and no uptime behind it is not counted")
        self.assertIn("no measurements", r["detail"])
        self.assertIn("so this is not counted", r["detail"])
        gw = self.c.devices[0]
        gw["wan1"] = {"ifname": "eth9", "up": True, "ip": "203.0.113.9"}; gw["uptime_stats"] = {"WAN": {"latency_average": 11}}
        r = self.run_check("health", subsystem="www")
        self.assertEqual(r["state"], "healthy", "an empty summary falls back to what the gateway reports")
        self.assertIn("gateway says WAN up · 11 ms", r["detail"])
        gw["wan1"]["up"] = False
        self.assertEqual(self.run_check("health", subsystem="www")["state"], "failed")
        gw.pop("wan1"); gw.pop("uptime_stats")
        www.update({"latency": 0, "uptime": 8123})
        self.assertEqual(self.run_check("health", subsystem="www")["state"], "degraded", "a warning with uptime behind it still counts")
        www.update({"latency": 15, "uptime": 0})
        self.assertEqual(self.run_check("health", subsystem="www")["state"], "degraded")
        www.update({"status": "error", "latency": 0, "uptime": 0})
        self.assertEqual(self.run_check("health", subsystem="www")["state"], "failed", "an error is never softened")
        www.update({"status": "warning", "latency": 0, "uptime": 8123})
        r = self.run_check("health", subsystem="www")
        for want in ("Internet warning", "0 ms", "drops 7", "uptime 8123", "speedtest status Idle"):
            self.assertIn(want, r["detail"])
        self.assertNotIn("aa:bb", r["detail"])

    def test_health_subsystems(self):
        r = self.run_check("health", subsystem="wan")
        self.assertEqual((r["state"], r["detail"]), ("healthy", "WAN ok · 203.0.113.9 · 1 of 1 devices connected"))
        self.assertIn("12 ms", self.run_check("health", subsystem="www")["detail"])
        for status, want in [("warning", "degraded"), ("error", "failed"), ("unknown", "unknown"), ("mystery", "unknown")]:
            self.c.health[0]["status"] = status
            self.assertEqual(self.run_check("health", subsystem="wan")["state"], want, status)
        self.assertEqual(self.run_check("health", subsystem="nope")["state"], "unknown")
        self.assertEqual(self.run_check("health")["state"], "unknown")

    def test_a_gateway_uplink_to_a_device_outside_unifi_is_not_shown_as_a_mac_address(self):
        self.c.devices[0]["uplink"] = {"type": "wire", "uplink_mac": "ce:ab:2c:fb:69:3e", "speed": 5000, "up": True}
        r = self.run_check("device", name="Bay Harbor")
        self.assertEqual(r["detail"], "connected · up 1 d · via a device outside UniFi at 5 Gbps")
        self.assertNotIn("ce:ab", r["detail"])

    def test_vpn_health_shows_what_it_is_based_on(self):
        self.c.health[3] = {"subsystem": "vpn", "status": "error", "remote_user_enabled": True, "site_to_site_num_inactive": 1,
                            "site_to_site_num_active": 0, "remote_user_rx_bytes": 99, "gw_name": "Bay Harbor"}
        r = self.run_check("health", subsystem="vpn")
        self.assertEqual(r["state"], "failed")
        self.assertIn("site to site num inactive 1", r["detail"])
        self.assertIn("remote user enabled True", r["detail"])
        self.assertNotIn("bytes", r["detail"])                        # traffic counters are noise

    def test_tunnels_follow_what_the_controller_has_not_a_fixed_list(self):
        r = self.run_check("tunnel", name="pia cali")                        # name match ignores case
        self.assertEqual((r["state"], r["detail"]), ("healthy", "OpenVPN · tunnel 10.24.112.134/32 · connected"))
        self.assertEqual(self.run_check("tunnel", name="Tidewater")["detail"], "WireGuard · tunnel 192.168.4.4/32 · connected")
        r = self.run_check("tunnel", name="Ferndale")
        self.assertEqual((r["state"], "paused" in r["detail"]), ("failed", True))
        for status, want in [("disconnected", "failed"), ("down", "failed"), ("connecting", "unknown"), ("", "unknown")]:
            self.c.connections[0]["status"] = status
            self.assertEqual(self.run_check("tunnel", name="PIA Cali")["state"], want, status)
        self.c.connections = []                                              # controller lists no status for it
        self.assertEqual(self.run_check("tunnel", name="PIA Cali")["state"], "unknown")
        # a new tunnel appears on the next Re-detect and can be checked; a removed one reads Unknown, not Failed
        self.c.networks.append({"_id": "t4", "name": "PIA Texas", "purpose": "vpn-client", "vpn_type": "openvpn-client", "enabled": True})
        self.c.connections.append({"network_id": "t4", "status": "connected"})
        d = M.handle({"method": "discover", "params": {"connection": self.conn}})
        self.assertIn("UniFi VPN PIA Texas", [s["label"] for s in d["suggest"]])
        self.assertEqual(self.run_check("tunnel", name="PIA Texas")["state"], "healthy")
        self.c.networks[:] = [n for n in self.c.networks if n["name"] != "PIA Texas"]
        r = self.run_check("tunnel", name="PIA Texas")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("PIA Cali", r["detail"])                               # says which tunnels do exist
        self.assertEqual(self.run_check("tunnel")["state"], "unknown")

    def test_a_controller_without_vpn_status_gives_unknown_not_a_false_green(self):
        self.c.vpn_status = False
        r = self.run_check("tunnel", name="PIA Cali")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("did not report", r["detail"])
        self.assertEqual(self.run_check("tunnel", name="Ferndale")["state"], "failed")      # paused is known from the settings
        self.assertEqual(self.run_check("devices")["state"], "healthy")
        self.c.os_style = False                                              # a classic controller has no such endpoint either
        M.CLIENTS.clear()
        self.assertEqual(self.run_check("tunnel", name="PIA Cali")["state"], "unknown")

    def test_discover_lists_devices_topology_and_checks(self):
        d = M.handle({"method": "discover", "params": {"connection": self.conn}})
        topo = {t["name"]: t for t in d["devices"]}
        self.assertEqual((topo["Garage"]["uplink"], topo["Garage"]["uplink_mbps"]), ("Switch 2", 1000))
        self.assertIsNone(topo["Bay Harbor"]["uplink"])
        labels = [s["label"] for s in d["suggest"]]
        self.assertEqual(labels[:4], ["UniFi devices", "UniFi WAN", "UniFi LAN", "UniFi Internet"])   # the coarse vpn summary is not offered
        self.assertNotIn("UniFi VPN", labels)
        self.assertEqual([s["label"] for s in d["suggest"] if s["batch"] == "VPN tunnels"],
                         ["UniFi VPN Ferndale", "UniFi VPN PIA Cali", "UniFi VPN Tidewater"])   # sorted; the plain network is not a tunnel
        self.assertEqual({t["name"]: t["status"] for t in d["tunnels"]}, {"Ferndale": "paused", "PIA Cali": "connected", "Tidewater": "connected"})
        self.assertIn("UniFi Garage", labels)
        self.assertEqual({(s["node"], s["group"], s["rule"]) for s in d["suggest"]}, {("UniFi", "Network", "any")})
        self.assertEqual({s["batch"] for s in d["suggest"]}, {"Overview", "Devices", "VPN tunnels"})
        for s in d["suggest"]:                                  # every suggestion is a check that really runs
            want = "failed" if s["params"].get("name") == "Ferndale" else "healthy"       # Ferndale is paused in the fake
            self.assertEqual(self.run_check(s["check"], **s["params"])["state"], want, s)

    def test_classic_controller_paths_and_a_named_site(self):
        self.c.os_style = False
        self.assertEqual(self.run_check("devices")["state"], "healthy")
        self.assertIn(("POST", "/api/login"), self.c.requests)

    def test_wrong_site_is_unknown_with_a_reason(self):
        M.CLIENTS.clear()
        self.conn["site"] = "other"
        with self.assertRaises(U.UnifiError) as cm:
            M.run_check("devices", {}, self.conn)
        self.assertIn("no site called 'other'", str(cm.exception))

    def test_unreachable_controller_and_bad_login_are_errors_main_turns_into_unknown(self):
        with self.assertRaises(U.UnifiError):
            M.run_check("devices", {}, {"base_url": "http://127.0.0.1:1", "username": "u", "password": "p", "timeout": 0.5})
        with self.assertRaises(U.UnifiError):
            M.run_check("devices", {}, self.c.conn(password="wrong-pw-0001"))
        with self.assertRaises(U.UnifiError):
            M.run_check("devices", {}, {"base_url": self.c.url, "username": "x"})          # no password

    def test_a_refused_login_is_not_retried_every_poll(self):
        bad = self.c.conn(password="wrong-pw-0002")
        for _ in range(5):
            with self.assertRaises(U.UnifiError):
                M.run_check("devices", {}, bad)
        self.assertEqual(self.c.logins, 1)                      # one attempt, then it backs off (no account lock-out)

    def test_session_is_reused_and_renewed_when_it_expires(self):
        for _ in range(3):
            self.run_check("devices")
        self.assertEqual(self.c.logins, 1)
        self.c.expire_next = True
        self.assertEqual(self.run_check("devices")["state"], "healthy")
        self.assertEqual(self.c.logins, 2)

    def test_it_only_ever_logs_in_and_reads(self):
        self.run_check("devices"); self.run_check("health", subsystem="wan"); self.run_check("device", name="Garage")
        M.handle({"method": "discover", "params": {"connection": self.conn}})
        posts = [r for r in self.c.requests if r[0] == "POST"]
        self.assertEqual(posts, [("POST", "/api/auth/login")])
        for method, path in self.c.requests:
            if method == "GET":
                self.assertRegex(path, r"^/proxy/network/(api/s/default/(stat/(device|health|sta)|rest/networkconf)|v2/api/site/default/vpn/connections)$")
        with self.assertRaises(U.UnifiError):                    # the client refuses anything else outright
            M.client(self.conn).get("rest/user")

    def test_client_usage_adds_up_each_client_biggest_first_shortens_addresses_and_only_reads(self):
        app = lambda b, d, u: {"application": b, "category": 3, "bytes_received": d, "bytes_transmitted": u, "total_bytes": d + u}
        self.c.flows = {"traffic": {"client_usage_by_app": [
            {"client": {"mac": "aa:bb:cc:00:00:01", "name": "Kid iPhone", "is_wired": False}, "usage_by_app": [app(1, 3_000_000, 100_000), app(2, 1_000_000, 50_000)]},
            {"client": {"mac": "aa:bb:cc:00:00:02", "hostname": "nas-box", "is_wired": True}, "usage_by_app": [app(1, 9_000_000, 9_000_000)]},
            {"client": {"mac": "aa:bb:cc:00:00:03", "name": "Idle thing"}, "usage_by_app": [app(1, 0, 0)]},
            {"client": {"mac": "aa:bb:cc:00:00:04", "oui": "Fake Vendor"}, "usage_by_app": []}], "total_usage_by_app": []}}
        r = M.handle({"method": "client_usage", "params": {"connection": self.conn, "seconds": 600}})
        self.assertEqual(r["seconds"], 600)
        self.assertEqual([(x["name"], x["wired"], x["down"], x["up"]) for x in r["clients"]], [("nas-box", True, 9_000_000, 9_000_000), ("Kid iPhone", False, 4_000_000, 150_000)])
        self.assertEqual(r["clients"][1]["id"], "..:00:00:01")
        self.assertEqual((r["count"], r["total"]), (2, {"down": 13_000_000, "up": 9_150_000}), "clients with no bytes are left out")
        self.assertNotIn("aa:bb:cc:00:00:01", json.dumps(r))
        self.assertEqual([m for m, _ in self.c.requests if m == "POST"], ["POST"], "only the login")
        self.assertRegex(self.c.requests[-1][1], r"^/proxy/network/v2/api/site/default/traffic\?start=\d+&end=\d+")
        self.c.os_style = False
        M.CLIENTS.clear()
        with self.assertRaises(U.UnifiError):
            M.handle({"method": "client_usage", "params": {"connection": self.c.conn()}})

    def test_the_flows_look_reports_status_and_shape_hides_public_addresses_and_adds_only_one_kind_of_search(self):
        self.c.flows = {"traffic": {"client_usage_by_app": [{"client": {"mac": "aa:bb:cc:dd:ee:ff"}, "usage_by_app": [{"application": 1, "category": 2, "total_bytes": 123}]}], "total_usage_by_app": []},
                        "search": lambda body: (400, {"code": "api.err.InvalidPayload", "message": "timestampFrom is required"}) if not body else
                        (200, {"data": [{"src": {"ip": "192.168.77.9", "mac": "aa:bb:cc:11:22:33"}, "dst": {"ip": "198.51.100.7", "domain": "example.test"}, "bytes": 4096}], "total": 1}),
                        "names": {"/proxy/network/v2/api/site/default/traffic/applications": (400, "start and end are required, not 198.51.100.7 or aa:bb:cc:dd:ee:ff"),
                                  "/proxy/network/v2/api/site/default/traffic/categories": (200, {"data": [{"id": 20, "name": "Fake category"}]})}}
        got = M.handle({"method": "flows_look", "params": {"connection": self.conn}})["attempts"]
        self.assertEqual([(a["request"], a["status"]) for a in got], [
            ("GET v2/api/site/default/traffic", 200), ("GET v2/api/site/default/traffic-flows", 404),
            ("POST v2/api/site/default/traffic-flows", 200), ("POST v2/api/site/default/traffic-flows", 400),
            ("GET v2/api/site/default/traffic/applications", 400), ("GET v2/api/site/default/traffic/applications", 400),
            ("GET v2/api/site/default/traffic/categories", 200), ("GET v2/api/site/default/traffic/categories", 200)])
        self.assertEqual(got[4]["text"], "start and end are required, not <public address> or ..:dd:ee:ff", "an error message is kept whole, addresses masked")
        self.assertEqual(got[7]["query"], ["end", "start"])
        self.assertEqual(got[6]["answer"]["data"]["first"][0], {"id": 20, "name": "Fake category"})
        self.assertEqual(got[0]["query"], ["end", "includeTrafficUsage", "includeUnidentified", "start"])
        self.assertEqual(got[0]["answer"]["client_usage_by_app"]["first"][0]["client"]["mac"], "..:dd:ee:ff")
        self.assertEqual(got[2]["sent"], ["pageNumber", "pageSize", "timestampFrom", "timestampTo"])
        row = got[2]["answer"]["data"]["first"][0]
        self.assertEqual((row["src"]["ip"], row["src"]["mac"], row["dst"]["ip"], row["bytes"]), ("192.168.77.9", "..:11:22:33", "<public address>", 4096))
        self.assertEqual(got[3]["answer"]["message"], "timestampFrom is required", "a refusal says what it wanted")
        blob = json.dumps(got)
        for secret in ("pw-fake-7731", "aa:bb:cc:dd:ee:ff", "198.51.100.7"):
            self.assertNotIn(secret, blob)
        self.assertEqual([r for r in self.c.requests if r[0] == "POST"], [("POST", "/api/auth/login")] + [("POST", "/proxy/network/v2/api/site/default/traffic-flows")] * 2)
        for method, path in self.c.requests[1:]:
            self.assertRegex(path, r"^/proxy/network/v2/api/site/default/traffic", (method, path))

    def test_flows_come_back_named_by_domain_prorated_to_the_window_paged_and_masked(self):
        now = int(time.time() * 1000)
        fl = lambda **k: {"flow_start_time": k.get("began", now - 5000), "flow_end_time": k.get("end", now - 1000), "direction": k.get("d", "outgoing"), "service": "HTTPS",
                          "source": {"ip": k.get("sip", "192.168.77.115"), "mac": "aa:bb:cc:da:8c:22", "client_name": "Fake Speaker"},
                          "destination": k.get("dst", {"ip": "203.0.113.50", "domains": ["cdn.example.test"]}), "traffic_data": {"bytes_rx": k.get("rx", 1000), "bytes_tx": k.get("tx", 100)}}
        pages = {0: {"data": [fl(), fl(rx=500, tx=50), fl(began=now - 7_200_000, end=now - 4_000_000, rx=9_000_000)], "has_next": True},      # the last one ended before the one-hour window
                 1: {"data": [fl(d="local", dst={"ip": "192.168.77.1", "zone_name": "Gateway", "mac": "aa:bb:cc:fe:79:e8"}, rx=40, tx=20),
                              fl(dst={"ip": "203.0.113.77"}, rx=7, tx=3),
                              fl(began=now - 7_200_000, end=now + 1000, rx=7_200_000, tx=0)], "has_next": False}}      # began two hours ago: only the last hour of it counts
        seen = []
        def search(body):
            seen.append(body)
            return (200, pages[body["pageNumber"]])
        self.c.flows = {"search": search}
        r = M.handle({"method": "flows", "params": {"connection": self.conn, "seconds": 3600}})
        rows = {(x["dst_name"], x["direction"]): x for x in r["flows"]}
        cdn = rows[("cdn.example.test", "outgoing")]
        self.assertEqual((cdn["down"], cdn["src_name"], cdn["src_mac"], cdn["service"]), (150, "Fake Speaker", "..:da:8c:22", "HTTPS"), "what the source received is the record's bytes_tx")
        self.assertAlmostEqual(cdn["up"], 1500 + 3_600_500, delta=2000, msg="the two small flows add up (the record's bytes_rx is what the source sent); the one that began two hours ago counts only for its last hour")
        self.assertEqual(rows[("203.0.113.77", "outgoing")]["dst_name"], "203.0.113.77", "no domain: named by address")
        gw = rows[("192.168.77.1", "local")]
        self.assertEqual((gw["dst_zone"], gw["dst_mac"]), ("Gateway", "..:fe:79:e8"))
        self.assertEqual(len(seen), 2, "followed has_next to the second page")
        self.assertEqual(sorted(seen[0]), ["pageNumber", "pageSize", "timestampFrom", "timestampTo"])
        self.assertNotIn("aa:bb:cc:da:8c:22", json.dumps(r))
        self.assertEqual([x for x in self.c.requests if x[0] == "POST"], [("POST", "/api/auth/login")] + [("POST", "/proxy/network/v2/api/site/default/traffic-flows")] * 2)

    def test_a_download_reads_as_down_for_the_device_that_pulled_it(self):
        """Regression: a Usenet-style download (the device asks, the far end sends the data) showed as UP. The gateway's record names its two byte counts from the far end's
        side: bytes_tx is what the far end sent, which is what the device received."""
        now = int(time.time() * 1000)
        flow = {"flow_start_time": now - 5000, "flow_end_time": now - 1000, "direction": "outgoing", "service": "NNTPS",
                "source": {"ip": "192.168.77.9", "mac": "aa:bb:cc:00:00:09", "client_name": "Fake Downloader"},
                "destination": {"ip": "203.0.113.60", "domains": ["news.example.test"]},
                "traffic_data": {"bytes_rx": 50_000, "bytes_tx": 5_000_000}}
        self.c.flows = {"search": lambda body: (200, {"data": [flow], "has_next": False})}
        row = M.handle({"method": "flows", "params": {"connection": self.conn, "seconds": 3600}})["flows"][0]
        self.assertEqual((row["dst_name"], row["down"], row["up"]), ("news.example.test", 5_000_000, 50_000), "the device pulled five megabytes and sent fifty thousand")

    def test_flows_ask_again_with_smaller_pages_when_the_controller_refuses_big_ones_and_say_when_they_cannot_be_read(self):
        sizes = []
        def search(body):
            sizes.append(body["pageSize"])
            return (400, {}) if body["pageSize"] > 50 else (200, {"data": [], "has_next": False})
        self.c.flows = {"search": search}
        self.assertEqual(M.handle({"method": "flows", "params": {"connection": self.conn}})["flows"], [])
        self.assertEqual(sizes, [200, 50])
        self.c.flows = {"search": lambda body: (403, {})}
        M.CLIENTS.clear()
        with self.assertRaises(U.UnifiError) as cm:
            M.handle({"method": "flows", "params": {"connection": self.conn, "seconds": 120}})
        self.assertIn("refused", str(cm.exception))

    def test_the_flows_look_needs_unifi_os_and_the_normal_reads_still_refuse_it(self):
        self.c.os_style = False
        with self.assertRaises(U.UnifiError) as cm:
            M.handle({"method": "flows_look", "params": {"connection": self.c.conn()}})
        self.assertIn("needs UniFi OS", str(cm.exception))
        with self.assertRaises(U.UnifiError):
            M.client(self.conn).get("traffic-flows")

    def test_main_turns_errors_into_unknown_for_checks_but_errors_for_discover(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            M.serve({"id": 1, "method": "check", "params": {"check": "devices", "connection": {"base_url": "http://127.0.0.1:1", "username": "u", "password": "p", "timeout": 0.5}}})
            M.serve({"id": 2, "method": "discover", "params": {"connection": {"base_url": "http://127.0.0.1:1", "username": "u", "password": "p", "timeout": 0.5}}})
        import json
        a, b = [json.loads(x) for x in buf.getvalue().splitlines()]
        self.assertEqual(a["result"]["state"], "unknown")
        self.assertIn("error", b)

    def test_https_with_a_self_signed_certificate(self):
        import shutil, ssl, subprocess, tempfile, threading
        if not shutil.which("openssl"):
            self.skipTest("openssl not installed")
        d = tempfile.mkdtemp()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{d}/k.pem", "-out", f"{d}/c.pem",
                        "-days", "1", "-subj", "/CN=fake-controller"], check=True, capture_output=True)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(f"{d}/c.pem", f"{d}/k.pem")
        self.c.srv.socket = ctx.wrap_socket(self.c.srv.socket, server_side=True)
        conn = self.c.conn(base_url=f"https://127.0.0.1:{self.c.port}")
        self.assertEqual(M.run_check("devices", {}, conn)["state"], "healthy")             # self-signed accepted by default
        M.CLIENTS.clear()
        with self.assertRaises(U.UnifiError):
            M.run_check("devices", {}, dict(conn, verify_tls=True))                        # but not when asked to verify


if __name__ == "__main__":
    unittest.main()
