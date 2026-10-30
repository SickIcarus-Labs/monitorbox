"""Scrypted module (Node), against a fake Scrypted that stands in for the official client library: camera and server checks, the neutral camera
list, pictures, a refused login or an unreachable Scrypted reading Unknown (never Failed), a limited account that cannot see or photograph cameras
getting a plain reason, and the guarantee that only reads reach Scrypted. Skipped where Node is not installed."""
import base64, json, os, shutil, subprocess, tempfile, threading, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(REPO, "modules", "scrypted")
FAKE = os.path.join(REPO, "tests", "fake_scrypted_client.mjs")
with open(os.path.join(MOD, "manifest.json")) as _f:
    VERSION = json.load(_f)["version"]


def cam(i, name, **kw):
    d = {"id": str(i), "name": name, "type": "Camera", "interfaces": ["Camera", "VideoCamera", "RTCSignalingChannel", "Online"], "online": True,
         "nativeId": f"native{i}", "info": {"model": "G5 Pro"}, "bytes": f"JPEG-{name}"}
    d.update(kw)
    return d


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class ScryptedModule(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(prefix="mb-scr-")
        self.addCleanup(shutil.rmtree, d, True)
        self.world, self.log = os.path.join(d, "world.json"), os.path.join(d, "calls.log")
        open(self.log, "w").close()
        self.w = {"username": "viewer-fake", "password": "pw-fake-9921", "version": "0.147.0",
                  "devices": [cam(1, "Driveway"), cam(2, "Doorbell", type="Doorbell"), cam(3, "Garage"),
                              {"id": "9", "name": "Some Plugin", "type": "API", "interfaces": ["Settings"]}]}
        self.save()
        env = dict(os.environ, MB_SCRYPTED_CLIENT=FAKE, MB_FAKE_SCRYPTED=self.world, MB_FAKE_SCRYPTED_LOG=self.log)
        self.p = subprocess.Popen(["node", "main.mjs"], cwd=MOD, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.stop)
        self.n, self.replies, self.events, self.cv = 0, {}, [], threading.Condition()
        threading.Thread(target=self.reader, daemon=True).start()
        self.conn = {"host": "192.0.2.9", "username": "viewer-fake", "password": "pw-fake-9921", "timeout": 3}

    def stop(self):
        self.p.kill(); self.p.wait()
        self.p.stdin.close(); self.p.stdout.close()

    def save(self):
        with open(self.world, "w") as f:
            json.dump(self.w, f)

    def reader(self):
        for line in self.p.stdout:
            msg = json.loads(line)
            with self.cv:
                if "event" in msg:
                    self.events.append(msg)
                else:
                    self.replies[msg["id"]] = msg
                self.cv.notify_all()

    def call(self, method, params=None):
        self.n += 1
        i = self.n
        self.p.stdin.write(json.dumps({"id": i, "method": method, "params": params or {}}) + "\n"); self.p.stdin.flush()
        with self.cv:
            self.assertTrue(self.cv.wait_for(lambda: i in self.replies, timeout=15), f"no reply to {method}")
            return self.replies.pop(i)

    def check(self, kind, conn=None, **params):
        return self.call("check", {"check": kind, "params": params, "connection": conn or self.conn})["result"]

    def calls(self):
        with open(self.log) as f:
            return f.read().split("\n")

    def test_hello_and_describe_need_no_scrypted(self):
        self.assertEqual(self.call("hello")["result"], {"module": "scrypted", "version": VERSION})
        self.assertEqual(self.call("describe")["result"]["title"], "Scrypted")
        self.assertEqual(self.calls(), [""], "hello must not touch Scrypted")

    def test_server_cameras_and_a_single_camera(self):
        self.assertEqual(self.check("server"), {"state": "healthy", "detail": "Scrypted 0.147.0 · 3 cameras"})
        self.assertEqual(self.check("cameras"), {"state": "healthy", "detail": "3 of 3 cameras online"})
        self.assertEqual(self.check("camera", name="driveway")["detail"], "G5 Pro · online")
        self.w["devices"][2]["online"] = False; self.save()
        r = self.check("cameras")
        self.assertEqual((r["state"], r["detail"]), ("failed", "2 of 3 cameras online · offline: Garage"))
        self.assertEqual(self.check("camera", name="Garage")["state"], "failed")
        self.assertEqual(self.check("cameras", names=["Driveway"])["state"], "healthy")
        self.w["devices"][2]["online"] = None; self.save()                                         # no online flag is not the same as offline
        self.assertEqual(self.check("camera", name="Garage")["state"], "healthy")
        r = self.check("camera", name="Nope")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("Doorbell, Driveway, Garage", r["detail"])

    def test_the_neutral_camera_list_skips_things_that_are_not_cameras_and_honours_exclude(self):
        got = self.call("cameras", {"connection": self.conn})["result"]["cameras"]
        self.assertEqual([c["name"] for c in got], ["Doorbell", "Driveway", "Garage"])
        self.assertEqual(got[1], {"id": "1", "name": "Driveway", "model": "G5 Pro", "state": "healthy", "detail": "G5 Pro · online", "recording": None,
                                  "lastSeen": None, "motion": False, "source": "scrypted", "snapshot": True, "live": True})
        got = self.call("cameras", {"connection": dict(self.conn, exclude="garage, nothing")})["result"]["cameras"]
        self.assertEqual([c["name"] for c in got], ["Doorbell", "Driveway"])

    def test_a_picture_is_a_jpeg_from_the_right_camera_and_only_for_cameras(self):
        r = self.call("snapshot", {"connection": self.conn, "id": "3"})["result"]
        self.assertEqual((r["mime"], base64.b64decode(r["data"])), ("image/jpeg", b"JPEG-Garage"))
        for bad in ("9", "404", ""):
            self.assertIn("error", self.call("snapshot", {"connection": self.conn, "id": bad}), bad)

    def test_a_wrong_password_or_unreachable_scrypted_is_unknown_never_failed(self):
        r = self.check("server", dict(self.conn, password="not-the-password-3"))
        self.assertEqual(r["state"], "unknown")
        self.assertIn("refused the user name or password", r["detail"])
        before = len([c for c in self.calls() if c.startswith("connect")])
        r = self.check("server", dict(self.conn, password="not-the-password-3"))                  # a refused login is not retried for a minute
        self.assertIn("not retrying", r["detail"])
        self.assertEqual(len([c for c in self.calls() if c.startswith("connect")]), before)
        self.w["down"] = True; self.save()
        r = self.check("server", dict(self.conn, host="192.0.2.77"))
        self.assertEqual(r["state"], "unknown")
        self.assertIn("cannot reach Scrypted", r["detail"])
        for conn in ({}, {"host": "192.0.2.9"}):
            self.assertEqual(self.check("server", conn)["state"], "unknown")

    def test_discover_suggests_the_server_and_says_why_a_limited_account_fails(self):
        d = self.call("discover", {"connection": self.conn})["result"]
        self.assertEqual([c["name"] for c in d["cameras"]], ["Doorbell", "Driveway", "Garage"])
        self.assertEqual([s["label"] for s in d["suggest"]], ["Scrypted", "Camera Doorbell", "Camera Driveway", "Camera Garage"])      # no all-cameras summary: each camera is its own item
        self.assertEqual([(s["check"], s["params"], s["batch"]) for s in d["suggest"][1:]],
                         [("camera", {"name": n}, "Cameras") for n in ("Doorbell", "Driveway", "Garage")])
        self.assertTrue(all(s["group"] == "Cameras" and s["rule"] == "primary" and s["node"] == ("Scrypted" if s["check"] == "server" else s["label"]) for s in d["suggest"]))
        for dev in self.w["devices"]:
            dev["hidden"] = True                                                                    # a limited account that is shown nothing
        self.save()
        r = self.call("discover", {"connection": dict(self.conn, host="192.0.2.10")})
        self.assertIn("can see no cameras", r["error"])
        self.assertEqual(self.check("server", dict(self.conn, host="192.0.2.10"))["state"], "degraded")
        for dev in self.w["devices"]:
            dev["hidden"] = False
        self.w["devices"][1]["pictureFails"] = True; self.save()                                    # sees them but cannot photograph
        r = self.call("discover", {"connection": dict(self.conn, host="192.0.2.11")})
        self.assertIn("taking a picture from Doorbell failed", r["error"])

    def test_certificate_checking_follows_each_connection_not_the_one_before(self):
        """A connection that asks for the certificate check is checked even after a connection that does not (#328: one switch for the whole process)."""
        other = dict(self.conn, host="192.0.2.10")
        self.check("server")                                                  # no check asked for: self-signed is normal on Scrypted
        self.check("server", conn=dict(other, verify_tls=True))               # check asked for
        self.check("server", conn=dict(self.conn, host="192.0.2.11"))
        tls = [c.split("tls=")[1] for c in self.calls() if c.startswith("connect")]
        self.assertEqual(tls, ["unchecked", "checked", "unchecked"])

    def test_only_reads_ever_reach_scrypted(self):
        self.check("server"); self.check("cameras"); self.call("cameras", {"connection": self.conn})
        self.call("snapshot", {"connection": self.conn, "id": "1"}); self.call("discover", {"connection": self.conn})
        seen = {c.split(" ")[0] for c in self.calls() if c}
        self.assertEqual(seen, {"connect", "getSystemState", "takePicture", "convert"})
        self.assertFalse([c for c in self.calls() if "FORBIDDEN" in c])

    # ---- live video (WebRTC signaling): the module asks the browser, the browser answers, Scrypted gets the answers
    def wait_event(self, kind, session="live-session-1", timeout=10):
        def find():
            return next((e for e in self.events if e["session"] == session and e["message"].get("type") == kind), None)
        with self.cv:
            self.assertTrue(self.cv.wait_for(find, timeout=timeout), f"no {kind} event; got {[e['message'].get('type') for e in self.events]}")
            return find()["message"]

    def open_live(self, session="live-session-1", cid="1", **kw):
        return self.call("live_open", {"connection": self.conn, "id": cid, "session": session, "options": {"userAgent": "fake-browser"}, **kw})

    def test_a_live_view_asks_the_browser_for_an_offer_and_ends_cleanly(self):
        self.assertEqual(self.open_live()["result"], {"started": True})
        call = self.wait_event("call")
        self.assertEqual((call["method"], call["args"][0], call["trickle"]), ("createLocalDescription", "offer", True))
        self.assertEqual(call["args"][1]["video"], {"direction": "recvonly"})
        self.call("live_input", {"session": "live-session-1", "message": {"type": "candidate", "callId": call["callId"], "candidate": {"candidate": "c1"}}})
        self.call("live_input", {"session": "live-session-1", "message": {"type": "result", "callId": call["callId"], "value": {"type": "offer", "sdp": "v=0 fake offer"}}})
        self.wait_event("ready")
        self.assertEqual(self.call("live_close", {"session": "live-session-1"})["result"], {})
        self.wait_event("closed")
        for _ in range(50):
            if "endSession 1" in self.calls(): break
            import time; time.sleep(0.1)
        log = self.calls()
        self.assertIn("startRTC 1", log); self.assertIn("offer offer 14", log); self.assertIn("endSession 1", log)
        self.assertFalse([c for c in log if "FORBIDDEN" in c])

    def test_a_live_view_says_why_it_cannot_start(self):
        r = self.call("live_open", {"connection": self.conn, "id": "9", "session": "live-session-2", "options": {}})
        self.assertIn("no such camera", r["error"])
        self.w["devices"][0]["interfaces"] = ["Camera", "VideoCamera", "Online"]; self.save()           # the account was not given RTCSignalingChannel
        r = self.open_live(session="live-session-3")
        self.assertIn("RTCSignalingChannel", r["error"]); self.assertNotIn("startRTC 1", self.calls())
        self.w["devices"][0]["interfaces"] = ["Camera", "VideoCamera", "RTCSignalingChannel", "Online"]; self.w["rtcFails"] = True; self.save()
        self.assertEqual(self.open_live(session="live-session-4")["result"], {"started": True})
        self.assertIn("Permission denied", self.wait_event("error", "live-session-4")["error"])
        self.assertEqual(self.call("live_open", {"connection": self.conn, "id": "1", "session": "bad session!", "options": {}})["error"], "bad live session id")
        self.assertEqual(self.call("live_input", {"session": "nope", "message": {}})["result"], {})   # a session that is gone is not an error

    def test_only_so_many_live_views_at_once(self):
        for i in range(10):
            self.assertEqual(self.open_live(session=f"live-sess-{i:02d}")["result"], {"started": True})
        self.assertIn("too many live views", self.open_live(session="live-sess-99")["error"])


if __name__ == "__main__":
    unittest.main()
