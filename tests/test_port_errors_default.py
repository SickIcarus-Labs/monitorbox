"""#295: a box with a switch login gets the Port errors system by itself, once; switching it off by hand keeps it off."""
import json, os, shutil, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "app"))
from monitorbox_app import server, monconfig  # noqa: E402


class Default(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-pe-")
        self.app = server.App(os.path.join(self.tmp, "box"), "file:///nowhere", "dev", 0)
        self.app.reload_monitoring = lambda: None
        os.makedirs(os.path.dirname(self.app.paths.config), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, conns):
        with open(self.app.paths.config, "w") as f:
            json.dump({"schema": 4, "revision": 1, "monitoring": {"builtinInternet": False, "nodes": []}, "connections": conns}, f)

    def has(self):
        return any(n.get("id") == "port-errors" for n in monconfig.all_nodes(self.app.paths)[0])

    def test_no_switch_no_system(self):
        self.put([{"id": "nut-1", "module": "nut", "name": "UPS", "host": "192.0.2.5"}])
        self.app.ensure_port_node()
        self.assertFalse(self.has())

    def test_a_switch_login_brings_it_once(self):
        self.put([{"id": "unifi-1", "module": "unifi-network", "name": "Controller", "host": "192.0.2.6", "apiKey": "fake-key-0002"}])
        self.app.ensure_port_node()
        self.assertTrue(self.has())
        self.app.ensure_port_node()
        self.assertEqual(sum(1 for n in monconfig.all_nodes(self.app.paths)[0] if n.get("id") == "port-errors"), 1)

    def test_switched_off_by_hand_it_does_not_come_back(self):
        self.put([{"id": "unifi-1", "module": "unifi-network", "name": "Controller", "host": "192.0.2.6", "apiKey": "fake-key-0002"}])
        self.app.ensure_port_node()
        self.app.set_portwatch({"on": False})
        self.assertFalse(self.has())
        self.app.ensure_port_node()
        self.assertFalse(self.has())


if __name__ == "__main__":
    unittest.main()
