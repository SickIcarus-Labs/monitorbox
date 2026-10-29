"""#322: a restart (an update, a container stop) must not start a port's learning again when its 16-bit counter went round since the last periodic save."""
import inspect, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitorbox_app import server, portwatch  # noqa: E402
from test_portwatch import dev  # noqa: E402


class SaveOnTheWayOut(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.app = server.App(os.path.join(self.tmp, "box"), "file:///nowhere", "dev", 0)
        self.now = [1_000_000.0]
        self.app.portwatch.clock = lambda: self.now[0]
        self.app.portwatch.set_enabled(True)

    def feed(self, w, raws, t0):
        for i, v in enumerate(raws):
            self.now[0] = t0 + i * 10
            w.feed([dev("Core", **{"Port 1": (0, 0, v, 0, 0)})], ["sw1"], now=self.now[0])

    def restarted(self):
        w = portwatch.PortWatch(self.app.paths, clock=lambda: self.now[0]); w.set_enabled(True); w.restore()
        return w

    def test_a_lap_between_the_last_periodic_save_and_the_restart_is_kept(self):
        w = self.app.portwatch
        self.feed(w, [60000, 60700, 61400], 1_000_000.0)
        w.save(now=self.now[0], force=True)                                  # the periodic save, then the counter goes round before the restart
        self.feed(w, [62100, 62800, 63500, 64200, 64900, 65500, 400, 1100, 1800], 1_000_030.0)
        before = w.series["sw1|Port 1"][-1][2]
        self.assertEqual(before, 1800 + 65536)
        self.app._save_history()                                             # what serve() does on the way out
        again = self.restarted()
        self.feed(again, [2500, 3200], 1_000_200.0)
        self.assertNotIn("sw1|Port 1", again.resets, "not taken for a reset")
        q = list(again.series["sw1|Port 1"])
        self.assertEqual(q[-1][2], 3200 + 65536, "the total carries on, still counting the lap")
        self.assertGreater(len(q), 1, "the learned history is still there")

    def test_the_stale_save_alone_would_lose_it(self):
        w = self.app.portwatch
        self.feed(w, [60000, 60700, 61400], 1_000_000.0)
        w.save(now=self.now[0], force=True)
        self.feed(w, [65500, 400, 1100], 1_000_030.0)                        # no save on the way out
        again = self.restarted()
        self.feed(again, [1800], 1_000_100.0)
        self.assertTrue(again.resets, "this is the bug the shutdown save closes")

    def test_serve_saves_on_every_way_out_and_catches_a_container_stop(self):
        src = inspect.getsource(server.App.serve)
        self.assertIn("self._save_history()", src.rsplit("finally:", 1)[1], "in the finally block, so an update or restart saves")
        self.assertIn("signal.SIGTERM", src, "a container stop leaves through the same door")


if __name__ == "__main__":
    unittest.main()
