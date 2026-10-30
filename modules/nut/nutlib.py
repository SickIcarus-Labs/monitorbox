"""A tiny, READ-ONLY client for a NUT server (upsd, TCP 3493). It only ever sends LIST UPS, LIST VAR, LIST CLIENT and
GET VAR. No LOGIN, no SET, no INSTCMD, no FSD: this module watches a UPS, it never controls one.
If the server wants a login to answer, the owner can give a user name and password; they are sent as USERNAME and
PASSWORD ahead of the read, nothing more (never LOGIN, which would attach this client to the UPS)."""
import socket


class NutError(Exception):
    pass


class StaleData(NutError):
    """upsd is up, but its driver has lost contact with the UPS (ERR DATA-STALE)."""


def unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        out, i, body = [], 0, s[1:-1]
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                i += 1
            out.append(body[i])
            i += 1
        return "".join(out)
    return s


def split_args(line):
    """'VAR ups ups.status "OL"' -> ['VAR', 'ups', 'ups.status', 'OL'] (quoted parts may hold spaces)."""
    parts, cur, inq, i = [], "", False, 0
    while i < len(line):
        ch = line[i]
        if inq and ch == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if ch == '"':
            inq = not inq
        elif ch == " " and not inq:
            if cur:
                parts.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    if cur:
        parts.append(cur)
    return parts


class Client:
    def __init__(self, host, port=3493, timeout=3.0, username=None, password=None):
        self.host, self.port, self.timeout = host, int(port), float(timeout)
        self.username, self.password = (username or "").strip() or None, password or ""

    @staticmethod
    def _q(s):
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _talk(self, command, terminator=None):
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.settimeout(self.timeout)
                pre = ""
                if self.username:                                  # asked for a login: sent first, on the same connection
                    pre = f"USERNAME {self._q(self.username)}\nPASSWORD {self._q(self.password)}\n"
                s.sendall(pre.encode() + command.encode() + b"\n")
                buf = b""
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    text = buf.decode("utf-8", "replace")
                    if any(ln.startswith("ERR") for ln in text.splitlines()):
                        break
                    if (terminator and terminator in text) or (not terminator and text.endswith("\n")):
                        break
        except socket.timeout:
            raise NutError(f"the NUT server at {self.host}:{self.port} did not answer in time")
        except OSError as e:
            raise NutError(f"cannot reach the NUT server at {self.host}:{self.port} ({e})")
        lines = buf.decode("utf-8", "replace").splitlines()
        while self.username and lines and lines[0] == "OK":        # the answers to USERNAME and PASSWORD
            lines.pop(0)
        if not lines:
            raise NutError("the NUT server closed the connection without answering")
        if lines[0].startswith("ERR"):
            code = lines[0].split(" ", 1)[1] if " " in lines[0] else "UNKNOWN"
            if code.startswith("DATA-STALE"):
                raise StaleData("the UPS driver has lost contact with the UPS (data stale)")
            if code.startswith("ACCESS-DENIED"):
                raise NutError("the NUT server said ACCESS-DENIED" + (" (check the user name and password)" if self.username
                               else " (the server may only allow certain addresses, or want a user name and password: allow this box on the server, or add a login to this connection)"))
            raise NutError(f"the NUT server said {code}")
        return lines

    def list_ups(self):
        """{name: description}"""
        out = {}
        for ln in self._talk("LIST UPS", "END LIST UPS"):
            p = split_args(ln)
            if p[:1] == ["UPS"] and len(p) >= 2:
                out[p[1]] = p[2] if len(p) > 2 else ""
        return out

    def list_vars(self, ups):
        """{variable: value}"""
        out = {}
        for ln in self._talk(f"LIST VAR {ups}", "END LIST VAR"):
            p = split_args(ln)
            if p[:1] == ["VAR"] and len(p) >= 4:
                out[p[2]] = p[3]
        return out

    def list_clients(self, ups):
        """[address]: the machines that are attached to this UPS (upsmon on each server it powers), as the NUT server lists them."""
        out = []
        for ln in self._talk(f"LIST CLIENT {ups}", f"END LIST CLIENT {ups}"):
            p = split_args(ln)
            if p[:1] == ["CLIENT"] and len(p) >= 3:
                out.append(p[2])
        return out
