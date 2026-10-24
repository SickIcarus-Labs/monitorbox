"""Automatic backups: not for an empty box (a wiped box once buried the real backup under two empty ones)."""
import os, shutil, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
from monitorbox_app import backups  # noqa: E402
from monitorbox_app.store import write_json  # noqa: E402


class Auto(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mb-auto-")
        self.cfg = os.path.join(self.root, "config", "monitorbox.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_empty_box_makes_none(self):
        self.assertEqual(backups.run_auto(self.root, "0.6.1"), [])  # no config file at all
        write_json(self.cfg, {"schema": 4, "monitoring": {"builtinInternet": True, "nodes": []}})
        self.assertEqual(backups.run_auto(self.root, "0.6.1"), [])  # defaults only
        self.assertFalse(os.path.isdir(os.path.join(self.root, "backups")))

    def test_configured_box_makes_config_and_full_once(self):
        write_json(self.cfg, {"schema": 4, "monitoring": {"nodes": [{"id": "gw"}]}})
        self.assertEqual(len(backups.run_auto(self.root, "0.6.1")), 2)
        self.assertEqual(backups.run_auto(self.root, "0.6.1"), [])  # nothing is due yet

    def test_connections_alone_count(self):
        write_json(self.cfg, {"schema": 4, "connections": [{"id": "nut-0"}]})
        self.assertEqual(len(backups.run_auto(self.root, "0.6.1")), 2)


if __name__ == "__main__":
    unittest.main()
