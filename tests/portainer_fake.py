"""A fake Portainer server for tests. It records every request (method, path, API key) so tests can prove the module
only ever sends GETs with the token, and it can stand in for the apps behind published ports."""
import json, socket, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

TOKEN = "fake-ptr-token-1"


def container(name, state="running", status="Up 3 hours", image=None, stack=None, ports=(), labels=None):
    lab = dict(labels or {})
    if stack:
        lab["com.docker.compose.project"] = stack
    return {"Id": "id-" + name, "Names": ["/" + name], "Image": image or f"example/{name}:latest", "State": state, "Status": status,
            "Labels": lab, "Ports": [{"IP": "0.0.0.0", "PrivatePort": p, "PublicPort": p, "Type": "tcp"} for p in ports]}


def environment(env_id, name, type_=2, status=1, url=None):
    return {"Id": env_id, "Name": name, "Type": type_, "Status": status, "URL": url if url is not None else f"tcp://127.0.0.1:{9000 + env_id}", "GroupId": 1}


class Site:
    """A throwaway HTTP server standing in for an app: always answers with `code`."""
    def __init__(self, code=200):
        outer = self
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(outer.code); self.end_headers(); self.wfile.write(b"hello")
            def log_message(self, *a): pass
        self.code = code
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class Silent:
    """A TCP port that accepts and closes, like a database: open, but not HTTP."""
    def __init__(self):
        self.s = socket.socket(); self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(("127.0.0.1", 0)); self.s.listen(8); self.s.settimeout(0.2)
        self.port = self.s.getsockname()[1]; self.stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self.stop:
            try:
                c, _ = self.s.accept(); c.close()
            except (socket.timeout, OSError):
                continue

    def close(self):
        self.stop = True; self.s.close()


class Portainer:
    def __init__(self, envs=None, containers=None, token=TOKEN):
        outer = self
        self.envs, self.containers, self.token = envs or [], containers or {}, token
        self.requests, self.down = [], False      # down: answer 503 to everything
        class H(BaseHTTPRequestHandler):
            def _do(self):
                u = urlparse(self.path)
                outer.requests.append((self.command, u.path, self.headers.get("X-API-Key")))
                if self.command != "GET":
                    return self._send(405, {"message": "read-only fake"})
                if outer.down:
                    return self._send(503, {"message": "down"})
                if u.path in ("/api/system/status", "/api/status"):
                    return self._send(200, {"Version": "2.21.0", "InstanceID": "fake"})
                if self.headers.get("X-API-Key") != outer.token:
                    return self._send(401, {"message": "Invalid JWT token"})
                if u.path == "/api/endpoints":
                    return self._send(200, outer.envs)
                parts = u.path.strip("/").split("/")
                if len(parts) == 6 and parts[:2] == ["api", "endpoints"] and parts[3:] == ["docker", "containers", "json"]:
                    env = next((e for e in outer.envs if str(e["Id"]) == parts[2]), None)
                    if not env:
                        return self._send(404, {"message": "not found"})
                    return self._send(200, outer.containers.get(env["Id"], []))
                return self._send(404, {"message": "not found"})
            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _do
            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
                self.end_headers(); self.wfile.write(b)
            def log_message(self, *a): pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()
