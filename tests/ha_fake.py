"""A stand-in for Home Assistant: the sign-in page redirect, /auth/token (code and refresh), /auth/revoke, GET /api/services and
POST /api/services/notify/<device>. Fake credentials only. Records everything it was asked so tests can compare."""
import http.server, json, threading, urllib.parse


class FakeHA:
    def __init__(self, devices=("mobile_app_phone_one", "mobile_app_tablet_two")):
        self.devices = set(devices)
        self.code, self.refresh, self.ttl = "fake-code-111", "fake-refresh-222", 1800
        self.access_ok, self.n = set(), 0
        self.long_lived = "fake-long-lived-333"
        self.sent, self.revoked, self.token_calls, self.authorize_calls = [], [], [], []
        self.deny, self.reject_refresh, self.down = False, False, False
        me = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def reply(self, code, obj=None, headers=None):
                raw = json.dumps(obj if obj is not None else {}).encode()
                self.send_response(code)
                for k, v in (headers or {}).items(): self.send_header(k, v)
                self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
                self.end_headers(); self.wfile.write(raw)

            def authed(self):
                tok = (self.headers.get("Authorization") or "")[7:]
                return tok == me.long_lived or tok in me.access_ok

            def do_GET(self):
                u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
                if me.down: return self.reply(500)
                if u.path == "/auth/authorize":
                    me.authorize_calls.append({k: v[0] for k, v in q.items()})
                    back = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"error": "access_denied", "state": q["state"][0]} if me.deny else {"code": me.code, "state": q["state"][0]})
                    return self.reply(302, headers={"Location": back})
                if u.path == "/api/services":
                    if not self.authed(): return self.reply(401, {"message": "Unauthorized"})
                    return self.reply(200, [{"domain": "notify", "services": {**{d: {} for d in sorted(me.devices)}, "notify": {}, "send_message": {}}},
                                            {"domain": "light", "services": {"turn_on": {}}}])
                self.reply(404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n)
                if me.down: return self.reply(500)
                if self.path == "/auth/token":
                    f = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                    me.token_calls.append(f)
                    if f.get("grant_type") == "authorization_code" and f.get("code") == me.code:
                        return self.reply(200, {"access_token": me.new_access(), "expires_in": me.ttl, "refresh_token": me.refresh, "token_type": "Bearer"})
                    if f.get("grant_type") == "refresh_token" and f.get("refresh_token") == me.refresh and not me.reject_refresh and f.get("refresh_token") not in me.revoked:
                        return self.reply(200, {"access_token": me.new_access(), "expires_in": me.ttl, "token_type": "Bearer"})
                    return self.reply(400, {"error": "invalid_grant"})
                if self.path == "/auth/revoke":
                    me.revoked.append(urllib.parse.parse_qs(raw.decode()).get("token", [""])[0]); return self.reply(200)
                if self.path.startswith("/api/services/notify/"):
                    if not self.authed(): return self.reply(401, {"message": "Unauthorized"})
                    name = self.path.rsplit("/", 1)[1]
                    if name not in me.devices: return self.reply(400, {"message": f"Service notify/{name} not found."})
                    me.sent.append((name, json.loads(raw or b"{}"))); return self.reply(200, [])
                self.reply(404)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def new_access(self):
        self.n += 1
        t = f"fake-access-{self.n}"
        self.access_ok.add(t)
        return t

    def expire_access(self):
        self.access_ok.clear()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()
