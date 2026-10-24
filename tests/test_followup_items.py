"""Adding the 'new things' a Portainer connection offers must keep the whole item (#284): a container's web check stays a web check with its
address, and the container keeps its service details and its link to the environment check. Every value below is made up and distinct."""
import json, os, shutil, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "app"))
from monitorbox_app import server, monconfig  # noqa: E402


def put(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


ENV = {"label": "Environment Anchor3 Env", "check": "environment", "params": {"name": "Anchor3 Env"}, "node": "Anchor3 Env Portainer",
       "group": "Services", "batch": "Environments", "env": "Anchor3 Env"}
SVC = {"title": "Cedarhut 1", "env": "Anchor3 Env", "container": "cedarhut-1", "icon": "cedarhut", "stack": "cedar-hut", "url": "http://192.0.2.77:7777/"}
CONTAINER = {"label": "Container cedarhut-1 on Anchor3 Env", "check": "container", "params": {"env": "Anchor3 Env", "name": "cedarhut-1"},
             "node": "Cedarhut 1 (Anchor3 Env)", "group": "Services", "batch": "Anchor3 Env · cedar-hut", "service": SVC, "requires": ENV, "env": "Anchor3 Env"}
WEB = {"label": "Web cedarhut-1 on Anchor3 Env", "type": "http", "url": "http://192.0.2.77:7777/health", "expect": list(range(200, 400)) + [401], "insecure": True,
       "node": "Cedarhut 1 (Anchor3 Env)", "group": "Services", "batch": "Anchor3 Env · cedar-hut", "service": SVC, "requires": ENV, "env": "Anchor3 Env"}


class NewItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-items-")
        self.app = server.App(os.path.join(self.tmp, "box"), "file:///nowhere", "dev", 0)
        self.app.reload_monitoring = lambda: None
        put(self.app.paths.config, {"schema": 4, "revision": 1, "monitoring": {"builtinInternet": False, "nodes": []},
                                    "connections": [{"id": "portainer-1", "module": "portainer", "name": "Portainer", "host": "192.0.2.10", "apiKey": "fake-key-0001"}]})
        self.app.sweep["out"]["portainer-1"] = {"suggest": [ENV, CONTAINER, WEB]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def nodes(self):
        return {n["name"]: n for n in monconfig.load_config(self.app.paths)["monitoring"]["nodes"]}

    def add(self):
        return self.app.add_new_items({"from": "portainer-1", "labels": [CONTAINER["label"], WEB["label"]]})

    def test_the_web_check_keeps_its_address_and_the_container_keeps_its_service_and_environment(self):
        self.assertGreaterEqual(self.add()["added"], 1)
        nodes = self.nodes()
        n = nodes["Cedarhut 1 (Anchor3 Env)"]
        kinds = {c["label"]: c for c in n["checks"]}
        web = kinds[WEB["label"]]
        self.assertEqual((web["type"], web["url"], web.get("expect"), web.get("insecure")), ("http", "http://192.0.2.77:7777/health", ["200-399", 401], True))
        box = kinds[CONTAINER["label"]]
        self.assertEqual((box["type"], box["check"], box["params"]), ("module", "container", {"env": "Anchor3 Env", "name": "cedarhut-1"}))
        self.assertEqual((n["service"]["container"], n["service"]["icon"], n["service"]["env"]), ("cedarhut-1", "cedarhut", "Anchor3 Env"))
        env_node = nodes["Anchor3 Env Portainer"]
        self.assertEqual(n["dependsOn"], [env_node["id"]])                      # grouped under its Portainer environment, not 'Other'

    def test_an_empty_web_check_saved_by_the_old_version_is_replaced_by_the_real_one(self):
        cfg = monconfig.load_config(self.app.paths)
        cfg["monitoring"]["nodes"] = [{"id": "cedarhut-1-anchor3-env", "name": "Cedarhut 1 (Anchor3 Env)", "group": "Services", "rule": "primary",
                                       "checks": [{"id": monconfig.check_id(WEB["label"]), "type": "module", "module": "portainer", "connection": "portainer-1",
                                                   "check": "", "params": {}, "label": WEB["label"]}]}]
        put(self.app.paths.config, cfg)
        self.add()
        web = [c for c in self.nodes()["Cedarhut 1 (Anchor3 Env)"]["checks"] if c["label"] == WEB["label"]]
        self.assertEqual([(c["type"], c["url"]) for c in web], [("http", "http://192.0.2.77:7777/health")])      # one check, and it is the real one

    def test_watch_item_keeps_every_part_that_matters(self):
        self.assertEqual(set(monconfig.watch_item(WEB)), {"label", "type", "url", "expect", "insecure", "node", "group", "service", "requires"})
        self.assertEqual(set(monconfig.watch_item(CONTAINER)), {"label", "check", "params", "node", "group", "service", "requires"})


if __name__ == "__main__":
    unittest.main()
