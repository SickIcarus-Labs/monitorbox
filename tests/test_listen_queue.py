"""#336: the web server's queue of waiting connections was Python's default of 5. On the owner's Pi it overflowed 14,697 times: Caddy saw
"connection reset by peer" and answered 502 for bursts of requests (Settings, the history strips). The real queue the kernel uses is checked here."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box
from monitorbox_app import peer, server


class ListenQueue(unittest.TestCase):
    def test_the_web_server_and_the_site_link_server_queue_128_connections(self):
        self.assertGreaterEqual(server.Server.request_queue_size, 128)
        self.assertGreaterEqual(peer._Server.request_queue_size, 128)

    def test_the_running_box_listens_with_that_queue(self):
        box = Box(self, "fake-queue-pw-62")
        self.assertIsInstance(box.app.httpd, server.Server)
        import shutil, subprocess
        if not shutil.which("ss"):
            self.skipTest("ss is not installed here")
        out = subprocess.run(["ss", "-ltnH", f"sport = :{box.port}"], capture_output=True, text=True).stdout.split()
        self.assertEqual(int(out[2]), 128, out)                    # Send-Q of a listening socket is its queue size

if __name__ == "__main__":
    unittest.main()
