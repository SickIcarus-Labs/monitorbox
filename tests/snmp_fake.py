"""A fake SNMP device for tests: v2c and v3 (USM auth + AES privacy), GET / GETNEXT / GETBULK, a
changeable MIB, and the real error behaviour (unknown engine, unknown user, wrong digest, time window).
The message handling here is written separately from the client's; they share only the byte-level codec
and the crypto primitives that the published test vectors check."""
import hashlib, hmac, os, socket, struct, sys, threading, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "modules", "snmp"))
import snmplib as L  # noqa: E402

ENGINE_ID = bytes.fromhex("80001f8880") + b"fake-engine"


def val(v):
    """python value -> BER. ('gauge',5) ('ticks',9) ('c64',3) ('str',b'x') or int / bytes / str"""
    if isinstance(v, tuple):
        kind, x = v
        if kind == "gauge":
            return L.tlv(L.GAUGE32, x.to_bytes(max(1, (x.bit_length() + 7) // 8), "big"))
        if kind == "ticks":
            return L.tlv(L.TIMETICKS, x.to_bytes(max(1, (x.bit_length() + 7) // 8), "big"))
        if kind == "c32":
            return L.tlv(L.COUNTER32, x.to_bytes(max(1, (x.bit_length() + 7) // 8), "big"))
        if kind == "c64":
            return L.tlv(L.COUNTER64, x.to_bytes(max(1, (x.bit_length() + 7) // 8), "big"))
        if kind == "oid":
            return L.enc_oid(x)
        raise ValueError(kind)
    if isinstance(v, int):
        return L.enc_int(v)
    return L.tlv(L.OCT, v.encode() if isinstance(v, str) else v)


class Agent:
    def __init__(self, mib=None, community="fake-community", users=None, clock_skew=0, boots=7):
        self.mib = dict(mib or {})            # oid string -> python value (see val)
        self.community = community
        self.users = users or {}              # name -> {"auth": "sha", "authpw": str, "priv": bool, "privpw": str}
        self.boots, self.skew, self.born = boots, clock_skew, time.monotonic()
        self.requests = []                     # what it was asked, for tests
        self.drop = False                      # True = silent (device unreachable)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.stop = False
        self._keys = {}
        self.salt = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def close(self):
        self.stop = True
        self.sock.close()

    def now(self):
        return int(time.monotonic() - self.born) + 1000 + self.skew

    # -- MIB access
    def _sorted(self):
        return sorted(self.mib, key=L.oid_key)

    def _get(self, oid):
        return L.tlv(L.NOSUCHINSTANCE, b"") if oid not in self.mib else val(self.mib[oid])

    def _next(self, oid):
        for o in self._sorted():
            if L.oid_key(o) > L.oid_key(oid):
                return o, val(self.mib[o])
        return oid, L.tlv(L.ENDOFMIB, b"")

    def _answer(self, tag, f):
        rid = int.from_bytes(f[0][1], "big", signed=True)
        a, b = int.from_bytes(f[1][1], "big"), int.from_bytes(f[2][1], "big")
        oids = [L.dec_oid(L.items(vb)[0][1]) for _t, vb in L.items(f[3][1])]
        self.requests.append((tag, oids))
        out = []
        if tag == L.GET:
            out = [(o, self._get(o)) for o in oids]
        elif tag == L.GETNEXT:
            out = [self._next(o) for o in oids]
        elif tag == L.GETBULK:
            cur = oids[0]
            for _ in range(min(b, 50)):
                o, v = self._next(cur)
                out.append((o, v))
                if v[0] == L.ENDOFMIB:
                    break
                cur = o
        vbs = b"".join(L.tlv(L.SEQ, L.enc_oid(o) + v) for o, v in out)
        return L.tlv(L.RESPONSE, L.enc_int(rid) + L.enc_int(0) + L.enc_int(0) + L.tlv(L.SEQ, vbs))

    # -- network
    def _loop(self):
        while not self.stop:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            if self.drop:
                continue
            try:
                reply = self._handle(data)
            except Exception:
                reply = None
            if reply:
                self.sock.sendto(reply, addr)

    def _handle(self, data):
        _t, body, _ = L.read(data)
        parts = L.items(body)
        ver = int.from_bytes(parts[0][1], "big")
        if ver in (0, 1):
            if parts[1][1].decode() != self.community:
                return None
            tag, pdu = parts[2]
            return L.tlv(L.SEQ, parts[0] and L.enc_int(ver) + L.tlv(L.OCT, parts[1][1]) + self._answer(tag, L.items(pdu)))
        return self._handle_v3(data, parts)

    def _report(self, mid, oid, auth_user=None):
        sec = L.tlv(L.SEQ, L.tlv(L.OCT, ENGINE_ID) + L.enc_int(self.boots) + L.enc_int(self.now()) +
                    L.tlv(L.OCT, b"") + L.tlv(L.OCT, b"") + L.tlv(L.OCT, b""))
        pdu = L.tlv(L.REPORT, L.enc_int(0) + L.enc_int(0) + L.enc_int(0) +
                    L.tlv(L.SEQ, L.tlv(L.SEQ, L.enc_oid(oid) + L.tlv(L.COUNTER32, b"\x01"))))
        gd = L.tlv(L.SEQ, L.enc_int(mid) + L.enc_int(65507) + L.tlv(L.OCT, b"\x00") + L.enc_int(3))
        return L.tlv(L.SEQ, L.enc_int(3) + gd + L.tlv(L.OCT, sec) + L.tlv(L.SEQ, L.tlv(L.OCT, ENGINE_ID) + L.tlv(L.OCT, b"") + pdu))

    def _handle_v3(self, raw, parts):
        gd = L.items(parts[1][1])
        mid = int.from_bytes(gd[0][1], "big")
        flags = gd[2][1][0]
        sec = L.items(L.read(parts[2][1], 0)[1])
        eid, boots, etime, user, authp, privp = (sec[0][1], int.from_bytes(sec[1][1], "big"), int.from_bytes(sec[2][1], "big"),
                                                 sec[3][1].decode(), sec[4][1], sec[5][1])
        if not eid or not user:
            return self._report(mid, "1.3.6.1.6.3.15.1.1.4.0")
        u = self.users.get(user)
        if u is None:
            return self._report(mid, "1.3.6.1.6.3.15.1.1.3.0")
        want_auth, want_priv = bool(u.get("auth")), bool(u.get("priv"))
        if not want_auth and (flags & 3):
            return self._report(mid, "1.3.6.1.6.3.15.1.1.1.0")
        if bool(flags & 1) != want_auth or bool(flags & 2) != want_priv:
            return self._report(mid, "1.3.6.1.6.3.15.1.1.1.0")
        akey = pkey = None
        if want_auth:
            key = (user, u["auth"], u["authpw"], u.get("privpw"))
            if key not in self._keys:
                self._keys[key] = (L.localize(u["authpw"], ENGINE_ID, u["auth"]),
                                   L.localize(u["privpw"], ENGINE_ID, u["auth"]) if want_priv else None)
            akey, pkey = self._keys[key]
            maclen = L.HASHES[u["auth"]][1]
            lo, hi = L._auth_span(raw)
            blank = raw[:lo] + b"\x00" * maclen + raw[hi:]
            mac = hmac.new(akey, blank, L.HASHES[u["auth"]][0]).digest()[:maclen]
            if not hmac.compare_digest(mac, authp):
                return self._report(mid, "1.3.6.1.6.3.15.1.1.5.0")
            if boots != self.boots or abs(etime - self.now()) > 150:
                return self._auth_report(mid, "1.3.6.1.6.3.15.1.1.2.0", u, akey)
        dt, data = parts[3]
        if not want_auth:
            tag, pdu = L.items(data)[2]
            return self._reply_v3(mid, 0, u, None, None, self._answer(tag, L.items(pdu)))
        if want_priv:
            try:   # a wrong key yields garbage; whatever way the garbage fails to parse, it is a decryption error
                scoped = L.read(L.priv_decrypt("des" if u.get("priv") == "des" else "aes", pkey, boots, etime, privp, data))[1]
                L.items(L.items(scoped)[2][1])
            except Exception:
                return self._report(mid, "1.3.6.1.6.3.15.1.1.6.0")
        else:
            scoped = data
        s_items = L.items(scoped)
        tag, pdu = s_items[2]
        resp = self._answer(tag, L.items(pdu))
        return self._reply_v3(mid, flags & 0x03, u, akey, pkey, resp)

    def _auth_report(self, mid, oid, u, akey):
        """notInTimeWindow: an authenticated report carrying the device's real time."""
        pdu = L.tlv(L.REPORT, L.enc_int(0) + L.enc_int(0) + L.enc_int(0) +
                    L.tlv(L.SEQ, L.tlv(L.SEQ, L.enc_oid(oid) + L.tlv(L.COUNTER32, b"\x01"))))
        return self._reply_v3(mid, 0x01, u, akey, None, pdu, user=True)

    def _reply_v3(self, mid, level, u, akey, pkey, pdu, user=True):
        scoped = L.tlv(L.SEQ, L.tlv(L.OCT, ENGINE_ID) + L.tlv(L.OCT, b"") + pdu)
        etime, privp, data = self.now(), b"", scoped
        if level & 2:
            self.salt += 1
            privp = self.salt.to_bytes(8, "big")
            data = L.tlv(L.OCT, L.priv_encrypt("des" if u.get("priv") == "des" else "aes", pkey, self.boots, etime, privp, scoped))
        maclen = L.HASHES[u["auth"]][1] if u.get("auth") else 0
        uname = next(k for k, v in self.users.items() if v is u).encode()

        def build(mac):
            gd = L.tlv(L.SEQ, L.enc_int(mid) + L.enc_int(65507) + L.tlv(L.OCT, bytes([level])) + L.enc_int(3))
            sec = L.tlv(L.SEQ, L.tlv(L.OCT, ENGINE_ID) + L.enc_int(self.boots) + L.enc_int(etime) + L.tlv(L.OCT, uname) +
                        L.tlv(L.OCT, mac) + L.tlv(L.OCT, privp))
            return L.tlv(L.SEQ, L.enc_int(3) + gd + L.tlv(L.OCT, sec) + data)
        if not u.get("auth"):
            return build(b"")
        return build(hmac.new(akey, build(b"\x00" * maclen), L.HASHES[u["auth"]][0]).digest()[:maclen])
