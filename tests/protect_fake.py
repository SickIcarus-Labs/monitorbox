"""A fake UniFi Protect console for tests (plain HTTP on localhost). It records every request, so tests can prove the
module only ever logs in and reads a bootstrap or a snapshot."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NOW = 1_700_000_000_000
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes\xff\xd9"


def cam(cid, name, **kw):
    c = {"id": cid, "name": name, "marketName": "G4 Bullet", "type": "UVC G4 Bullet", "state": "CONNECTED", "isConnected": True,
         "isRecording": True, "isMotionDetected": False, "lastSeen": NOW - 1000, "recordingSettings": {"mode": "always"}}
    c.update(kw)
    return c


class Console:
    def __init__(self, username="viewer-fake", password="pw-fake-4417"):
        self.username, self.password = username, password
        self.cameras = [cam("cam0001abc", "Driveway", mac="AABBCC000001", host="192.0.2.71"),
                        cam("cam0002abc", "Front Door", marketName="G4 Doorbell", mac="AABBCC000002", host="192.0.2.72"),
                        cam("cam0003abc", "Backyard", recordingSettings={"mode": "detections"}, isRecording=False, mac="AABBCC000003", host="192.0.2.73")]
        self.nvr = {"name": "Fake NVR", "version": "5.3.1", "uptime": 5 * 86400000,
                    "storageStats": {"utilization": 91.5, "capacity": 8_000_000_000_000,
                                     "recordingSpace": {"total": 8_000_000_000_000, "used": 7_320_000_000_000, "available": 680_000_000_000}},
                    "systemInfo": {"ustorage": {"disks": [{"slot": 1, "model": "FAKE-IRONWOLF-1", "temperature": 45, "healthy": "good", "state": "normal", "bad_sector": 0, "reason": []},
                                                          {"slot": 2, "model": "FAKE-IRONWOLF-2", "temperature": 41, "healthy": "good", "state": "normal", "bad_sector": 0, "reason": []}]},
                                   "storage": {"devices": [{"model": "FAKE-DISK-A", "healthy": True}, {"model": "FAKE-DISK-B", "healthy": True}]}}}
        self.requests, self.logins, self.expire_next, self.sessions = [], 0, False, set()
        self.snapshot_type, self.snapshot_body, self.protect_missing = "image/jpeg", JPEG, False
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, raw=b"{}", ctype="application/json", cookie=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                if cookie:
                    self.send_header("Set-Cookie", f"TOKEN={cookie}; path=/; httponly")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                me.requests.append(("POST", self.path))
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path != "/api/auth/login":
                    return self.send(404)
                me.logins += 1
                if body.get("username") != me.username or body.get("password") != me.password:
                    return self.send(401)
                tok = f"tok{me.logins}"
                me.sessions.add(tok)
                self.send(200, b"{}", cookie=tok)

            def do_GET(self):
                me.requests.append(("GET", self.path))
                tok = (self.headers.get("Cookie") or "").replace("TOKEN=", "")
                if tok not in me.sessions or me.expire_next:
                    me.expire_next = False
                    me.sessions.discard(tok)
                    return self.send(401)
                if me.protect_missing:
                    return self.send(404)
                if self.path == "/proxy/protect/api/bootstrap":
                    return self.send(200, json.dumps({"nvr": me.nvr, "cameras": me.cameras}).encode())
                if self.path == "/proxy/protect/api/nvr":
                    return self.send(200, json.dumps(me.nvr).encode())
                if self.path.startswith("/proxy/protect/api/cameras/") and "/snapshot" in self.path:
                    return self.send(200, me.snapshot_body, me.snapshot_type)
                self.send(404)

            do_PUT = do_DELETE = do_PATCH = lambda self: self.send(405)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def conn(self, **kw):
        return dict({"base_url": self.url, "username": self.username, "password": self.password, "timeout": 2}, **kw)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
