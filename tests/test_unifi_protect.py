"""UniFi Protect module: camera, recorder and storage checks, the neutral camera list, snapshots, login behaviour, and the guarantee that it only reads."""
import base64, importlib.util, io, json, os, sys, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "unifi-protect")
sys.path.insert(0, MOD)
from protect_fake import Console, JPEG, NOW  # noqa: E402
import protectlib as P  # noqa: E402
import protectchecks as C  # noqa: E402
_spec = importlib.util.spec_from_file_location("protect_main", os.path.join(MOD, "main.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


class ProtectChecks(unittest.TestCase):
    def setUp(self):
        self.c = Console()
        self.addCleanup(self.c.close)
        self.conn = self.c.conn()
        M.CLIENTS.clear()
        P.CACHE_SECONDS = 0
        P.LOGIN_BACKOFF = 60

    def run_check(self, kind, **params):
        return M.run_check(kind, params, self.conn)

    def test_a_healthy_camera_says_what_it_is_doing(self):
        r = self.run_check("camera", name="Driveway")
        self.assertEqual((r["state"], r["detail"]), ("healthy", "G4 Bullet · recording · connected"))
        self.assertEqual(self.run_check("camera", name="driveway")["state"], "healthy")            # case does not matter

    def test_every_camera_condition(self):
        d = self.c.cameras[0]
        d.update(state="DISCONNECTED", isConnected=False, isRecording=False)
        r = self.run_check("camera", name="Driveway")
        self.assertEqual(r["state"], "failed")
        self.assertIn("offline, last seen", r["detail"])
        d.update(state="CONNECTING", isConnected=False)
        self.assertEqual(self.run_check("camera", name="Driveway")["state"], "degraded")
        d.update(state="CONNECTED", isConnected=True, isUpdating=True)
        self.assertEqual(self.run_check("camera", name="Driveway")["detail"], "G4 Bullet · updating its firmware")
        d.update(isUpdating=False, isRecording=False)                                                # should record all the time but does not
        r = self.run_check("camera", name="Driveway")
        self.assertEqual(r["state"], "degraded")
        self.assertIn("not recording", r["detail"])

    def test_a_camera_set_to_record_on_motion_is_fine_while_it_is_idle(self):
        r = self.run_check("camera", name="Backyard")
        self.assertEqual((r["state"], r["detail"]), ("healthy", "G4 Bullet · records on motion · connected"))
        self.c.cameras[2]["recordingSettings"]["mode"] = "never"
        self.assertEqual(self.run_check("camera", name="Backyard")["state"], "healthy")           # recording off is the owner's choice

    def test_an_unknown_camera_is_unknown_and_lists_what_exists(self):
        r = self.run_check("camera", name="Garage")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("Backyard, Driveway, Front Door", r["detail"])
        self.assertEqual(self.run_check("camera")["state"], "unknown")

    def test_roll_up_of_all_cameras(self):
        self.assertEqual(self.run_check("cameras")["detail"], "3 of 3 cameras fine")
        self.c.cameras[1].update(state="DISCONNECTED", isConnected=False)
        r = self.run_check("cameras")
        self.assertEqual((r["state"], r["detail"]), ("failed", "2 of 3 cameras fine · offline: Front Door"))
        self.assertEqual(self.run_check("cameras", names=["Driveway"])["state"], "healthy")        # only those named
        self.c.cameras = []
        self.assertEqual(self.run_check("cameras")["state"], "unknown")

    def test_the_recorder_and_its_storage(self):
        self.assertEqual(self.run_check("nvr")["detail"], "Fake NVR · Protect 5.3.1 · up 5 d")
        r = self.run_check("storage")
        self.assertEqual((r["state"], r["detail"]), ("healthy", "7.3 TB of 8.0 TB used · 2 disks healthy"))   # nearly full is normal: it overwrites old video
        self.c.nvr["systemInfo"]["storage"]["devices"][1]["healthy"] = False
        r = self.run_check("storage")
        self.assertEqual((r["state"], "FAKE-DISK-B" in r["detail"]), ("failed", True))
        self.c.nvr = {}
        self.assertEqual(self.run_check("storage")["state"], "unknown")

    def test_the_neutral_camera_list_and_discovery(self):
        got = M.handle({"method": "cameras", "params": {"connection": self.conn}})["cameras"]
        self.assertEqual([c["name"] for c in got], ["Backyard", "Driveway", "Front Door"])
        self.assertEqual(got[1], {"id": "cam0001abc", "name": "Driveway", "model": "G4 Bullet", "state": "healthy", "detail": "G4 Bullet · recording · connected",
                                  "recording": "always", "lastSeen": NOW - 1000, "motion": False, "source": "unifi-protect", "snapshot": True,
                                  "mac": "AABBCC000001", "host": "192.0.2.71"})
        self.c.cameras[0].update(state="DISCONNECTED", isConnected=False)
        self.assertFalse({c["name"]: c for c in M.handle({"method": "cameras", "params": {"connection": self.conn}})["cameras"]}["Driveway"]["snapshot"])
        d = M.handle({"method": "discover", "params": {"connection": self.conn}})
        self.assertEqual([s["label"] for s in d["suggest"]],
                         ["Protect recorder", "Protect storage", "Camera Backyard", "Camera Driveway", "Camera Front Door"])
        # every camera is its own item (one that is off shows as Down by name); the recorder and its storage share one, with the recorder first ("is it there")
        self.assertTrue(all(s["group"] == "Cameras" and s["rule"] == "primary" for s in d["suggest"]))
        self.assertEqual([s["node"] for s in d["suggest"]], ["UniFi Protect", "UniFi Protect", "Camera Backyard", "Camera Driveway", "Camera Front Door"])

    def test_a_snapshot_comes_back_as_a_picture_and_only_a_picture(self):
        r = M.handle({"method": "snapshot", "params": {"connection": self.conn, "id": "cam0001abc"}})
        self.assertEqual((r["mime"], base64.b64decode(r["data"])), ("image/jpeg", JPEG))
        self.c.snapshot_type, self.c.snapshot_body = "text/html", b"<html>login</html>"
        with self.assertRaises(P.ProtectError):
            M.handle({"method": "snapshot", "params": {"connection": self.conn, "id": "cam0001abc"}})
        for bad in ("../../etc/passwd", "a/b", "", None, "x" * 100):
            with self.assertRaises(P.ProtectError, msg=str(bad)):
                M.handle({"method": "snapshot", "params": {"connection": self.conn, "id": bad}})

    def test_it_only_ever_logs_in_and_reads(self):
        self.run_check("cameras"); self.run_check("nvr"); self.run_check("storage")
        M.handle({"method": "snapshot", "params": {"connection": self.conn, "id": "cam0002abc"}})
        M.handle({"method": "discover", "params": {"connection": self.conn}})
        posts = [r for r in self.c.requests if r[0] == "POST"]
        self.assertEqual(posts, [("POST", "/api/auth/login")])
        gets = {r[1].split("?")[0] for r in self.c.requests if r[0] == "GET"}
        self.assertEqual(gets, {"/proxy/protect/api/bootstrap", "/proxy/protect/api/cameras/cam0002abc/snapshot"})
        self.assertEqual({r[0] for r in self.c.requests}, {"GET", "POST"})                          # never PUT, PATCH or DELETE

    def test_unreachable_wrong_password_and_no_protect_are_unknown_never_failed(self):
        for conn, word in [(self.c.conn(password="not-the-password-0"), "refused"), (dict(self.conn, base_url="http://127.0.0.1:1", timeout=0.5), "cannot reach")]:
            M.CLIENTS.clear()
            r = M.run_check("cameras", {}, conn)
            self.assertEqual(r["state"], "unknown")
            self.assertIn(word, r["detail"])
        self.assertEqual(self.c.logins, 1)
        M.CLIENTS.clear()
        self.c.protect_missing = True
        r = self.run_check("cameras")
        self.assertEqual((r["state"], "no UniFi Protect" in r["detail"]), ("unknown", True))

    def test_a_refused_login_is_not_retried_for_a_minute(self):
        bad = self.c.conn(password="not-the-password-1")
        c = P.Client(bad["base_url"], bad["username"], bad["password"], timeout=1)
        for _ in range(3):
            with self.assertRaises(P.ProtectError):
                c.bootstrap()
        self.assertEqual(self.c.logins, 1)

    def test_an_expired_session_logs_in_again_once(self):
        self.run_check("cameras")
        self.c.expire_next = True
        self.assertEqual(self.run_check("cameras")["state"], "healthy")
        self.assertEqual(self.c.logins, 2)

    def test_serve_turns_errors_into_unknown_for_checks_and_errors_otherwise(self):
        buf = io.StringIO()
        bad = {"base_url": "http://127.0.0.1:1", "username": "u-fake-1", "password": "p-fake-1", "timeout": 0.5}
        with redirect_stdout(buf):
            M.serve({"id": 1, "method": "check", "params": {"check": "cameras", "connection": bad}})
            M.serve({"id": 2, "method": "discover", "params": {"connection": bad}})
            M.serve({"id": 3, "method": "hello"})
        a, b, c = [json.loads(x) for x in buf.getvalue().splitlines()]
        self.assertEqual(a["result"]["state"], "unknown")
        self.assertIn("error", b)
        self.assertEqual(c["result"], {"module": "unifi-protect", "version": M.VERSION})

    def test_a_connection_without_credentials_says_so(self):
        for conn in ({}, {"host": "192.0.2.5"}, {"host": "192.0.2.5", "username": "u-fake-2"}):
            M.CLIENTS.clear()
            r = M.run_check("cameras", {}, conn)
            self.assertEqual(r["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
