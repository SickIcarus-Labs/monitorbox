"""A fake UniFi controller for tests (plain HTTP on localhost). It records every request, so tests can prove the
module only ever logs in and reads, and it can behave like UniFi OS (/proxy/network/...) or a classic controller."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MACS = {"gw": "f4:e2:c6:00:00:01", "agg": "f4:e2:c6:00:00:02", "sw2": "f4:e2:c6:00:00:03", "garage": "f4:e2:c6:00:00:04"}


def dev(key, name, state=1, uplink=None, **kw):
    d = {"mac": MACS[key], "name": name, "model": "USW-X", "ip": "192.0.2.10", "state": state, "adopted": True,
         "uptime": 90000, "version": "7.0.1", "upgradable": False}
    if uplink:
        d["uplink"] = {"type": "wire", "uplink_mac": MACS[uplink[0]], "speed": uplink[1], "up": True}
    d.update(kw)
    return d


def standard():
    return [dev("gw", "Bay Harbor"), dev("agg", "Aggregation", uplink=("gw", 10000)),
            dev("sw2", "Switch 2", uplink=("agg", 10000)), dev("garage", "Garage", uplink=("sw2", 1000))]


class Controller:
    def __init__(self, username="reader-fake", password="pw-fake-7731", os_style=True, site="default"):
        self.username, self.password, self.os_style, self.site = username, password, os_style, site
        self.devices = standard()
        self.clients = []                                  # None = the login may not read the client list
        self.health = [{"subsystem": "wan", "status": "ok", "wan_ip": "203.0.113.9", "num_adopted": 1, "num_disconnected": 0},
                       {"subsystem": "lan", "status": "ok", "num_adopted": 4, "num_disconnected": 0},
                       {"subsystem": "www", "status": "ok", "latency": 12},
                       {"subsystem": "vpn", "status": "unknown"}]
        self.networks = [{"_id": "n1", "name": "Default", "purpose": "corporate"},
                         {"_id": "t1", "name": "PIA Cali", "purpose": "vpn-client", "vpn_type": "openvpn-client", "enabled": True, "ip_subnet": "10.24.112.134/32"},
                         {"_id": "t2", "name": "Tidewater", "purpose": "vpn-client", "vpn_type": "wireguard-client", "enabled": True, "ip_subnet": "192.168.4.4/32"},
                         {"_id": "t3", "name": "Ferndale", "purpose": "vpn-client", "vpn_type": "wireguard-client", "enabled": False}]
        self.connections = [{"network_id": "t1", "status": "CONNECTED"}, {"network_id": "t2", "status": "connected"}]
        self.flows = None                                        # None: no flows API. Else {"traffic": doc, "search": (status, doc)}
        self.vpn_status = True                                   # False: this controller has no VPN status endpoint
        self.requests, self.logins, self.expire_next = [], 0, False
        self.sessions = set()
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, doc, cookie=None):
                raw = json.dumps(doc).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                if cookie:
                    self.send_header("Set-Cookie", f"TOKEN={cookie}; path=/; samesite=none; secure; httponly")
                    self.send_header("X-Csrf-Token", f"csrf-{cookie}")      # UniFi OS hands one out at login and wants it back on every POST
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def send_text(self, code, text):
                raw = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                me.requests.append(("POST", self.path))
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                login = "/api/auth/login" if me.os_style else "/api/login"
                if self.path == f"/proxy/network/v2/api/site/{me.site}/traffic-flows" and me.flows and me.os_style:
                    if (self.headers.get("Cookie") or "").replace("TOKEN=", "") not in me.sessions:
                        return self.send(401, {})
                    if self.headers.get("X-Csrf-Token") != "csrf-" + (self.headers.get("Cookie") or "").replace("TOKEN=", ""):
                        return self.send(403, {})                            # what the real controller does with a POST that has no token
                    me.posted = getattr(me, "posted", []) + [body]
                    code, doc = me.flows["search"](body)
                    return self.send(code, doc)
                if self.path != login:
                    return self.send(404, {})
                me.logins += 1
                if body.get("username") != me.username or body.get("password") != me.password:
                    return self.send(401, {"code": "AUTHENTICATION_FAILED_INVALID_CREDENTIALS"})
                tok = f"tok{me.logins}"
                me.sessions.add(tok)
                self.send(200, {"meta": {"rc": "ok"}, "data": []}, tok)

            def do_GET(self):
                me.requests.append(("GET", self.path))
                tok = (self.headers.get("Cookie") or "").replace("TOKEN=", "")
                prefix = "/proxy/network" if me.os_style else ""
                if tok not in me.sessions or me.expire_next:
                    me.expire_next = False
                    me.sessions.discard(tok)
                    return self.send(401, {})
                base = f"{prefix}/api/s/{me.site}/"
                if self.path == base + "stat/device":
                    return self.send(200, {"meta": {"rc": "ok"}, "data": me.devices})
                if self.path == base + "stat/sta":
                    if me.clients is None:
                        return self.send(403, {})
                    return self.send(200, {"meta": {"rc": "ok"}, "data": me.clients})
                if self.path == base + "rest/networkconf":
                    return self.send(200, {"meta": {"rc": "ok"}, "data": me.networks})
                if self.path == f"/proxy/network/v2/api/site/{me.site}/vpn/connections" and me.os_style and me.vpn_status:
                    return self.send(200, {"connections": me.connections})
                if me.flows and me.os_style and self.path.startswith(f"/proxy/network/v2/api/site/{me.site}/traffic?"):
                    return self.send(200, me.flows["traffic"])
                if me.flows and me.os_style and self.path.split("?")[0] in me.flows.get("names", {}):
                    code, doc = me.flows["names"][self.path.split("?")[0]]
                    return self.send(code, doc) if not isinstance(doc, str) else self.send_text(code, doc)
                if self.path == base + "stat/health":
                    return self.send(200, {"meta": {"rc": "ok"}, "data": me.health})
                self.send(404, {})

            do_PUT = do_DELETE = do_PATCH = lambda self: self.send(405, {})

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
