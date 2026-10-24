"""A fake NUT server (upsd) for tests. It records every command it receives, so tests can prove the
module only ever asks (LIST/GET) and never controls (LOGIN, SET, INSTCMD, FSD)."""
import socket, threading


class Upsd:
    def __init__(self, ups=None, stale=(), users=None, clients=None):
        self.users = users              # {user: password}: when set, reading needs a USERNAME/PASSWORD first (else ERR ACCESS-DENIED)
        self.ups = ups or {}            # name -> {"desc": str, "vars": {name: value}}
        self.stale = set(stale)
        self.clients = clients or {}    # UPS name -> [addresses of the machines attached to it]
        self.commands = []
        self.drop = False
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def close(self):
        self.stop = True
        self.sock.close()

    def _loop(self):
        while not self.stop:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def q(s):
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _serve(self, conn):
        with conn:
            conn.settimeout(2)
            try:
                data = conn.recv(4096).decode()
            except OSError:
                return
            who = {}
            for cmd in [c for c in data.split("\n") if c.strip()]:
                self.commands.append(cmd)
                if self.drop:
                    return
                p = cmd.split(" ", 1)
                if p[0] in ("USERNAME", "PASSWORD"):
                    who[p[0]] = p[1].strip().strip('"').replace('\\"', '"').replace("\\\\", "\\") if len(p) > 1 else ""
                    conn.sendall(b"OK\n")
                    continue
                if self.users is not None and self.users.get(who.get("USERNAME")) != who.get("PASSWORD") or (self.users is not None and "USERNAME" not in who):
                    conn.sendall(b"ERR ACCESS-DENIED\n")
                    continue
                conn.sendall(self._answer(cmd).encode())

    def _answer(self, cmd):
        p = cmd.split()
        if p[:2] == ["LIST", "UPS"]:
            body = "".join(f"UPS {n} {self.q(u['desc'])}\n" for n, u in self.ups.items())
            return "BEGIN LIST UPS\n" + body + "END LIST UPS\n"
        if p[:2] == ["LIST", "VAR"] and len(p) == 3:
            if p[2] not in self.ups:
                return "ERR UNKNOWN-UPS\n"
            if p[2] in self.stale:
                return "ERR DATA-STALE\n"
            body = "".join(f"VAR {p[2]} {k} {self.q(v)}\n" for k, v in self.ups[p[2]]["vars"].items())
            return f"BEGIN LIST VAR {p[2]}\n" + body + f"END LIST VAR {p[2]}\n"
        if p[:2] == ["LIST", "CLIENT"] and len(p) == 3:
            if p[2] not in self.ups:
                return "ERR UNKNOWN-UPS\n"
            body = "".join(f"CLIENT {p[2]} {ip}\n" for ip in self.clients.get(p[2], []))
            return f"BEGIN LIST CLIENT {p[2]}\n" + body + f"END LIST CLIENT {p[2]}\n"
        if p[:2] == ["GET", "VAR"] and len(p) == 4:
            if p[2] not in self.ups:
                return "ERR UNKNOWN-UPS\n"
            v = self.ups[p[2]]["vars"].get(p[3])
            return f"VAR {p[2]} {p[3]} {self.q(v)}\n" if v is not None else "ERR VAR-NOT-SUPPORTED\n"
        return "ERR UNKNOWN-COMMAND\n"
