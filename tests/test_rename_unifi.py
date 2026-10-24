"""The UniFi module was renamed unifi -> unifi-network. An existing config keeps working without anything being re-entered."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import monconfig  # noqa: E402
from monitorbox_app.modules import Modules  # noqa: E402
from monitorbox_app.store import Paths, write_json, read_json  # noqa: E402


class Rename(unittest.TestCase):
    def setUp(self):
        self.paths = Paths(tempfile.mkdtemp(prefix="mb-rename-"))
        os.makedirs(os.path.dirname(self.paths.config), exist_ok=True)
        old = {"schema": 4, "revision": 3,
               "connections": [{"id": "gateway", "module": "unifi", "base_url": "https://192.0.2.1", "username": "fake-user-1", "password": "fake-pass-1"},
                               {"id": "nas", "module": "snmp", "host": "192.0.2.13", "community": "fake-comm-1"}],
               "monitoring": {"builtinInternet": False, "nodes": [
                   {"id": "gw", "name": "Gateway", "group": "Servers",
                    "checks": [{"id": "dev", "type": "module", "module": "unifi", "connection": "gateway", "check": "device", "params": {"name": "Switch 2"}},
                               {"id": "p", "type": "module", "module": "snmp", "connection": "nas", "check": "uptime"}]}]}}
        write_json(self.paths.config, old)

    def test_an_old_config_reads_with_the_new_module_name_and_nothing_else_changes(self):
        cfg = monconfig.load_config(self.paths)
        self.assertEqual([c["module"] for c in cfg["connections"]], ["unifi-network", "snmp"])
        self.assertEqual([k["module"] for k in cfg["monitoring"]["nodes"][0]["checks"]], ["unifi-network", "snmp"])
        self.assertEqual((cfg["connections"][0]["username"], cfg["connections"][0]["password"]), ("fake-user-1", "fake-pass-1"))
        self.assertEqual(cfg["revision"], 3)
        self.assertEqual(monconfig.connection(self.paths, "gateway")["module"], "unifi-network")
        nodes, err = monconfig.all_nodes(self.paths)
        self.assertIsNone(err)
        self.assertEqual({k.get("module") for n in nodes for k in n["checks"] if k.get("type") == "module"}, {"unifi-network", "snmp"})

    def test_the_file_keeps_the_old_name_until_the_next_save_so_a_rollback_still_works(self):
        monconfig.load_config(self.paths)
        self.assertEqual(read_json(self.paths.config)["connections"][0]["module"], "unifi")
        mon = monconfig.get_monitoring(self.paths)
        monconfig.save_monitoring(self.paths, mon["monitoring"], mon["revision"])
        saved = read_json(self.paths.config)
        self.assertEqual(saved["connections"][0]["module"], "unifi-network")
        self.assertEqual(saved["monitoring"]["nodes"][0]["checks"][0]["module"], "unifi-network")

    def test_the_retired_module_is_not_started_again(self):
        m = Modules(self.paths, lambda *a: None)
        write_json(self.paths.modules_state, {"unifi": {"active": "0.1.2", "failed": []}, "unifi-network": {"active": "0.2.0", "failed": []}})
        started = []
        m._start = lambda mid, version: started.append((mid, version))
        m.start_all()
        self.assertEqual(started, [("unifi-network", "0.2.0")])
        self.assertEqual(list(read_json(self.paths.modules_state)), ["unifi-network"])      # and its record is gone, so it is not listed or updated

    def test_the_release_pointer_still_naming_the_old_module_does_not_bring_it_back(self):
        from monitorbox_app.modules import current
        self.assertEqual(current(["hello", "unifi", "unifi-network", "snmp"]), ["hello", "unifi-network", "snmp"])
        m = Modules(self.paths, lambda *a: self.fail("must not install the retired module"))
        self.assertIn("renamed to unifi-network", m.apply_one("unifi", {"version": "0.1.2", "url": "x", "sha256": "y"}))
        self.assertNotIn("unifi", read_json(self.paths.modules_state, {}))


if __name__ == "__main__":
    unittest.main()
