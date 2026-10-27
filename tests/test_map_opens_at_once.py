"""The map page opens at once (#294): the last map is served without waiting for a scan, rebuilt in the background when it is a minute old, and kept across a restart."""
import os, shutil, sys, tempfile, threading, time, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "app"))
from monitorbox_app import server  # noqa: E402


class MapAtOnce(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-map-")
        self.root = os.path.join(self.tmp, "box")
        self.app = self.make()

    def make(self):
        app = server.App(self.root, "file:///nowhere", "dev", 0)
        app.scans, app.release = 0, threading.Event()

        def slow_report(wait=None):
            app.scans += 1
            app.release.wait(5)
            return {"sources": []}
        app.lan_report = slow_report
        return app

    def tearDown(self):
        self.app.release.set()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_first_ever_page_waits_for_one_scan_then_later_ones_do_not(self):
        self.app.release.set()
        self.app.map_now()
        self.assertEqual(self.app.scans, 1)
        self.app.release.clear()
        t = time.time()
        m = self.app.map_now()
        self.assertLess(time.time() - t, 1, "a fresh map is served without scanning")
        self.assertIsInstance(m, dict)
        self.assertEqual(self.app.scans, 1)

    def test_an_old_map_is_served_at_once_and_rebuilt_in_the_background(self):
        self.app.release.set()
        self.app.map_now()
        self.app.release.clear()                       # the next scan is slow
        self.app.map_at = time.time() - 3600
        t = time.time()
        m = self.app.map_now()
        self.assertLess(time.time() - t, 1, "must not wait for the slow scan")
        self.assertIsInstance(m, dict)
        for _ in range(50):
            if self.app.scans == 2:
                break
            time.sleep(0.1)
        self.assertEqual(self.app.scans, 2, "the rebuild was started")
        self.app.map_now()
        self.assertEqual(self.app.scans, 2, "only one rebuild at a time")
        self.app.release.set()

    def test_the_map_survives_a_restart(self):
        self.app.release.set()
        self.app.map_now()
        path = self.app._map_file()
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        again = self.make()
        self.assertIsNotNone(again.last_map, "the saved map is loaded")
        again.release.clear()
        t = time.time()
        again.map_now()
        self.assertLess(time.time() - t, 1)
        again.release.set()


if __name__ == "__main__":
    unittest.main()
