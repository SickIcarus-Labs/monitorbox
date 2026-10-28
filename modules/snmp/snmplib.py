"""A small SNMP client in plain Python (standard library only): v2c and v3 (USM) with
authentication MD5/SHA-1/SHA-2 and privacy AES-128, GET / GETNEXT / GETBULK / walk.

Why not a library: the container image carries only Python, and Python has no AES. Instead of adding a
dependency or Net-SNMP to the image, this module carries ~400 lines and is checked against the published
test vectors (RFC 3414 key localization, FIPS-197 / NIST SP 800-38A for AES) in tests/test_snmplib.py.

Errors: SnmpError = could not talk to the device (timeout, wrong login, device refused). Callers treat that
as "cannot be checked", never as "the device is down"."""
import threading, hashlib, hmac, os, socket, struct, time

# ---------------------------------------------------------------- BER ----
INT, OCT, NULL, OID, SEQ = 0x02, 0x04, 0x05, 0x06, 0x30
IPADDR, COUNTER32, GAUGE32, TIMETICKS, OPAQUE, COUNTER64 = 0x40, 0x41, 0x42, 0x43, 0x44, 0x46
NOSUCHOBJECT, NOSUCHINSTANCE, ENDOFMIB = 0x80, 0x81, 0x82
GET, GETNEXT, RESPONSE, GETBULK, REPORT = 0xA0, 0xA1, 0xA2, 0xA5, 0xA8


class SnmpError(Exception):
    pass


class NoSuch:
    """A value the device says does not exist (noSuchObject / noSuchInstance / endOfMibView)."""
    def __init__(self, kind):
        self.kind = kind

    def __repr__(self):
        return f"NoSuch({self.kind})"

    def __bool__(self):
        return False


def _len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag, content):
    return bytes([tag]) + _len(len(content)) + content


def enc_int(v):
    n = max(1, (v.bit_length() + 8) // 8) if v >= 0 else max(1, ((-v - 1).bit_length() + 8) // 8)
    return tlv(INT, v.to_bytes(n, "big", signed=True))


def enc_oid(oid):
    parts = [int(x) for x in oid.strip(".").split(".")]
    out = bytearray([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(chunk))
    return tlv(OID, bytes(out))


def read(data, pos=0):
    """-> (tag, content, next_pos)"""
    if pos + 2 > len(data):
        raise SnmpError("the reply was cut short")
    tag, ln = data[pos], data[pos + 1]
    pos += 2
    if ln & 0x80:
        k = ln & 0x7F
        if k == 0 or k > 4 or pos + k > len(data):
            raise SnmpError("the reply was malformed")
        ln = int.from_bytes(data[pos:pos + k], "big")
        pos += k
    if pos + ln > len(data):
        raise SnmpError("the reply was cut short")
    return tag, data[pos:pos + ln], pos + ln


def read_pos(data, pos):
    """-> (tag, content_start, content_end); like read() but says where the content sits."""
    tag, c, nxt = read(data, pos)
    return tag, nxt - len(c), nxt


def items(content):
    out, pos = [], 0
    while pos < len(content):
        tag, c, pos = read(content, pos)
        out.append((tag, c))
    return out


def dec_oid(b):
    if not b:
        return ""
    parts = [b[0] // 40, b[0] % 40]
    v = 0
    for x in b[1:]:
        v = (v << 7) | (x & 0x7F)
        if not x & 0x80:
            parts.append(v)
            v = 0
    return ".".join(map(str, parts))


def decode_value(tag, c):
    if tag == INT:
        return int.from_bytes(c, "big", signed=True)
    if tag in (COUNTER32, GAUGE32, TIMETICKS, COUNTER64):
        return int.from_bytes(c, "big")
    if tag == OCT or tag == OPAQUE:
        return bytes(c)
    if tag == OID:
        return dec_oid(c)
    if tag == IPADDR:
        return ".".join(str(x) for x in c)
    if tag == NULL:
        return None
    if tag in (NOSUCHOBJECT, NOSUCHINSTANCE, ENDOFMIB):
        return NoSuch({NOSUCHOBJECT: "noSuchObject", NOSUCHINSTANCE: "noSuchInstance", ENDOFMIB: "endOfMibView"}[tag])
    raise SnmpError(f"unknown value type 0x{tag:02x}")


def text(v):
    """A device string as readable text."""
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip("\x00 ")
    return str(v)


def oid_key(oid):
    return tuple(int(x) for x in oid.strip(".").split("."))


def under(oid, base):
    a, b = oid_key(oid), oid_key(base)
    return a[:len(b)] == b and len(a) > len(b)


# ---------------------------------------------------------------- AES-128 (encryption only; CFB needs nothing else) ----
def _make_sbox():
    sbox, p, q = [0] * 256, 1, 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)          # p *= 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ (q << 1 | q >> 7) & 0xFF ^ (q << 2 | q >> 6) & 0xFF ^ (q << 3 | q >> 5) & 0xFF ^ (q << 4 | q >> 4) & 0xFF
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


SBOX = _make_sbox()


def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def expand_key(key):
    if len(key) != 16:
        raise ValueError("AES-128 needs a 16-byte key")
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [SBOX[t[1]] ^ rcon, SBOX[t[2]], SBOX[t[3]], SBOX[t[0]]]
            rcon = _xt(rcon)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(11)]


def aes_encrypt_block(rk, block):
    s = [b ^ k for b, k in zip(block, rk[0])]
    for r in range(1, 11):
        s = [SBOX[b] for b in s]
        s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3], s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]  # ShiftRows
        if r != 10:
            m = []
            for c in range(0, 16, 4):
                a0, a1, a2, a3 = s[c:c + 4]
                m += [_xt(a0) ^ _xt(a1) ^ a1 ^ a2 ^ a3, a0 ^ _xt(a1) ^ _xt(a2) ^ a2 ^ a3,
                      a0 ^ a1 ^ _xt(a2) ^ _xt(a3) ^ a3, _xt(a0) ^ a0 ^ a1 ^ a2 ^ _xt(a3)]
            s = m
        s = [b ^ k for b, k in zip(s, rk[r])]
    return bytes(s)


def cfb128(key, iv, data, decrypt=False):
    """AES-128 in CFB-128 mode (RFC 3826 uses exactly this)."""
    rk, reg, out = expand_key(key), bytes(iv), bytearray()
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        ks = aes_encrypt_block(rk, reg)
        o = bytes(a ^ b for a, b in zip(chunk, ks))
        out += o
        reg = (chunk if decrypt else o) if len(chunk) == 16 else reg
    return bytes(out)


# ---------------------------------------------------------------- DES (RFC 3414 privacy; QNAP and some older devices) ----
_IP = (58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,62,54,46,38,30,22,14,6,64,56,48,40,32,24,16,8,
       57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7)
_FP = (40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,38,6,46,14,54,22,62,30,37,5,45,13,53,21,61,29,
       36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25)
_E = (32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,12,13,12,13,14,15,16,17,16,17,18,19,20,21,20,21,22,23,24,25,24,25,26,27,28,29,28,29,30,31,32,1)
_P = (16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25)
_PC1 = (57,49,41,33,25,17,9,1,58,50,42,34,26,18,10,2,59,51,43,35,27,19,11,3,60,52,44,36,
        63,55,47,39,31,23,15,7,62,54,46,38,30,22,14,6,61,53,45,37,29,21,13,5,28,20,12,4)
_PC2 = (14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,26,8,16,7,27,20,13,2,
        41,52,31,37,47,55,30,40,51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32)
_SHIFTS = (1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1)
_SB = (
 (14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7,0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8,4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0,15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13),
 (15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10,3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5,0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15,13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9),
 (10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8,13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1,13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7,1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12),
 (7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15,13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9,10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4,3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14),
 (2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9,14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6,4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14,11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3),
 (12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11,10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8,9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6,4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13),
 (4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1,13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6,1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2,6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12),
 (13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7,1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2,7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8,2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11))


def _perm(v, table, nbits):
    out = 0
    for t in table:
        out = (out << 1) | ((v >> (nbits - t)) & 1)
    return out


def _des_keys(key8):
    k = _perm(int.from_bytes(key8, "big"), _PC1, 64)
    c, d, ks = k >> 28, k & 0xFFFFFFF, []
    for sh in _SHIFTS:
        c = ((c << sh) | (c >> (28 - sh))) & 0xFFFFFFF
        d = ((d << sh) | (d >> (28 - sh))) & 0xFFFFFFF
        ks.append(_perm((c << 28) | d, _PC2, 56))
    return ks


def des_block(ks, block8, decrypt=False):
    v = _perm(int.from_bytes(block8, "big"), _IP, 64)
    l, r = v >> 32, v & 0xFFFFFFFF
    for k in (reversed(ks) if decrypt else ks):
        x = _perm(r, _E, 32) ^ k
        f = 0
        for i in range(8):
            six = (x >> (42 - 6 * i)) & 63
            f = (f << 4) | _SB[i][(((six & 32) >> 4) | (six & 1)) * 16 + ((six >> 1) & 15)]
        l, r = r, l ^ _perm(f, _P, 32)
    return _perm((r << 32) | l, _FP, 64).to_bytes(8, "big")


def des_cbc(key8, iv8, data, decrypt=False):
    """DES-CBC with zero padding on encrypt (RFC 3414 section 8.1.1.2); the caller trims on decrypt."""
    ks, prev, out = _des_keys(key8), bytes(iv8), bytearray()
    if not decrypt and len(data) % 8:
        data = data + b"\x00" * (8 - len(data) % 8)
    if decrypt and len(data) % 8:
        raise SnmpError("encrypted data is not a whole number of DES blocks")
    for i in range(0, len(data), 8):
        b = data[i:i + 8]
        if decrypt:
            out += bytes(x ^ y for x, y in zip(des_block(ks, b, True), prev))
            prev = b
        else:
            prev = des_block(ks, bytes(x ^ y for x, y in zip(b, prev)))
            out += prev
    return bytes(out)


def priv_encrypt(kind, key16, boots, etime, salt8, data):
    """-> encrypted bytes. AES: RFC 3826 IV = boots|time|salt. DES: IV = pre-IV (key bytes 8..16) XOR salt."""
    if kind == "des":
        return des_cbc(key16[:8], bytes(a ^ b for a, b in zip(key16[8:16], salt8)), data)
    return cfb128(key16[:16], boots.to_bytes(4, "big") + etime.to_bytes(4, "big") + salt8, data)


def priv_decrypt(kind, key16, boots, etime, salt8, data):
    if kind == "des":
        return des_cbc(key16[:8], bytes(a ^ b for a, b in zip(key16[8:16], salt8)), data, decrypt=True)
    return cfb128(key16[:16], boots.to_bytes(4, "big") + etime.to_bytes(4, "big") + salt8, data, decrypt=True)


# ---------------------------------------------------------------- USM keys ----
HASHES = {"md5": (hashlib.md5, 12), "sha": (hashlib.sha1, 12), "sha1": (hashlib.sha1, 12),
          "sha224": (hashlib.sha224, 16), "sha256": (hashlib.sha256, 24),
          "sha384": (hashlib.sha384, 32), "sha512": (hashlib.sha512, 48)}


def localize(password, engine_id, hashname):
    """RFC 3414 A.2: password -> Ku (hash of 1 MiB of the repeated password) -> key localized to this engine."""
    h = HASHES[hashname][0]
    pw = password.encode() if isinstance(password, str) else password
    if not pw:
        raise SnmpError("an empty SNMPv3 password is not allowed")
    ku = h((pw * (1048576 // len(pw) + 1))[:1048576]).digest()
    return h(ku + engine_id + ku).digest()


USM_ERRORS = {
    "1.3.6.1.6.3.15.1.1.1.0": "the device does not support that security level",
    "1.3.6.1.6.3.15.1.1.3.0": "the device does not know that SNMPv3 user name",
    "1.3.6.1.6.3.15.1.1.4.0": "the device did not recognise its own engine id",
    "1.3.6.1.6.3.15.1.1.5.0": "the SNMPv3 authentication password is wrong (or the hash type does not match)",
    "1.3.6.1.6.3.15.1.1.6.0": "the SNMPv3 privacy password is wrong (or the encryption type does not match)",
}
NOT_IN_TIME_WINDOW = "1.3.6.1.6.3.15.1.1.2.0"


# ---------------------------------------------------------------- session ----
class Session:
    """One device. Reuse it; v3 engine discovery and key localization happen once."""
    def __init__(self, host, port=161, version="2c", community="public", user=None,
                 auth=None, auth_password=None, priv=None, priv_password=None, timeout=2.0, retries=1):
        self.host, self.port, self.version = host, int(port), str(version)
        self.community, self.user = community, user or ""
        self.auth, self.auth_password, self.priv, self.priv_password = auth, auth_password, priv, priv_password
        self.privkind = "aes"
        self.timeout, self.retries = float(timeout), int(retries)
        self._req = int.from_bytes(os.urandom(3), "big")
        self._lock = threading.RLock()     # one conversation with the device at a time: checks on the same device share this session
        self._engine = None          # (engine_id, boots, time, monotonic_at_sync)
        self._keys = None
        self._salt = int.from_bytes(os.urandom(8), "big")
        if self.version == "3":
            if auth and auth not in HASHES:
                raise SnmpError(f"unknown authentication type '{auth}' (use md5, sha, sha224, sha256, sha384 or sha512)")
            if priv and priv.lower() not in ("aes", "aes128", "des"):
                raise SnmpError(f"privacy type '{priv}' is not supported (use aes or des)")
            self.privkind = "des" if priv and priv.lower() == "des" else "aes"
            if priv and not auth:
                raise SnmpError("SNMPv3 privacy needs authentication too")
        elif self.version not in ("1", "2c"):
            raise SnmpError(f"unknown SNMP version '{version}' (use 2c or 3)")

    # -- transport
    def _exchange(self, payload, expect_id):
        err = None
        for _ in range(self.retries + 1):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(self.timeout)
            try:
                s.sendto(payload, (self.host, self.port))
                end = time.monotonic() + self.timeout
                while True:
                    s.settimeout(max(0.05, end - time.monotonic()))
                    data, _ = s.recvfrom(65535)
                    try:
                        return self._parse(data, expect_id)
                    except _Stale:
                        continue
            except socket.timeout:
                err = "the device did not answer (no reply from SNMP)"
            except OSError as e:
                raise SnmpError(f"cannot reach the device: {e.strerror or e}")
            finally:
                s.close()
        raise SnmpError(err)

    def _next_id(self):
        self._req = (self._req + 1) & 0x7FFFFFFF
        return self._req or 1

    # -- v2c / v1
    def _pdu(self, kind, rid, varbinds, a=0, b=0):
        vb = b"".join(tlv(SEQ, enc_oid(o) + tlv(NULL, b"")) for o in varbinds)
        return tlv(kind, enc_int(rid) + enc_int(a) + enc_int(b) + tlv(SEQ, vb))

    def _build(self, pdu):
        if self.version == "3":
            return self._build_v3(pdu)
        ver = 0 if self.version == "1" else 1
        return tlv(SEQ, enc_int(ver) + tlv(OCT, self.community.encode()) + pdu)

    # -- v3
    def _ensure_v3(self):
        if self._engine:
            return
        rid = self._next_id()
        probe = self._msg_v3(rid, b"", 0, 0, b"", 0x04, b"", b"",
                             tlv(SEQ, tlv(OCT, b"") + tlv(OCT, b"") + self._pdu(GET, rid, [])))
        eng = self._exchange_discover(probe)
        self._engine = eng
        if self.auth:
            self._keys = (localize(self.auth_password or "", eng[0], self.auth),
                          localize(self.priv_password or "", eng[0], self.auth) if self.priv else None)

    def _exchange_discover(self, probe):
        err = None
        for _ in range(self.retries + 1):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(self.timeout)
            try:
                s.sendto(probe, (self.host, self.port))
                data, _ = s.recvfrom(65535)
                sec = self._sec_params(data)
                if not sec["engine_id"]:
                    raise SnmpError("the device did not identify itself (is SNMPv3 enabled?)")
                return (sec["engine_id"], sec["boots"], sec["time"], time.monotonic())
            except socket.timeout:
                err = "the device did not answer (no reply from SNMP)"
            except OSError as e:
                raise SnmpError(f"cannot reach the device: {e.strerror or e}")
            finally:
                s.close()
        raise SnmpError(err)

    @staticmethod
    def _sec_params(data):
        tag, body, _ = read(data)
        parts = items(body)
        sec = items(read(parts[2][1], 0)[1]) if parts[2][0] == OCT and parts[2][1] else None
        if not sec:
            return {"engine_id": b"", "boots": 0, "time": 0}
        return {"engine_id": sec[0][1], "boots": int.from_bytes(sec[1][1], "big"),
                "time": int.from_bytes(sec[2][1], "big"), "user": sec[3][1], "auth": sec[4][1], "priv": sec[5][1]}

    def _engine_time(self):
        eid, boots, t, at = self._engine
        return eid, boots, t + int(time.monotonic() - at)

    def _msg_v3(self, mid, engine_id, boots, etime, user, flags, auth_params, priv_params, msg_data):
        gd = tlv(SEQ, enc_int(mid) + enc_int(65507) + tlv(OCT, bytes([flags])) + enc_int(3))
        sec = tlv(SEQ, tlv(OCT, engine_id) + enc_int(boots) + enc_int(etime) + tlv(OCT, user) +
                  tlv(OCT, auth_params) + tlv(OCT, priv_params))
        return tlv(SEQ, enc_int(3) + gd + tlv(OCT, sec) + msg_data)

    def _build_v3(self, pdu):
        self._ensure_v3()
        eid, boots, etime = self._engine_time()
        mid = self._next_id()
        user = self.user.encode()
        flags = 0x04 | (0x01 if self.auth else 0) | (0x02 if self.priv else 0)
        scoped = tlv(SEQ, tlv(OCT, eid) + tlv(OCT, b"") + pdu)
        if not self.auth:
            return self._msg_v3(mid, eid, 0, 0, user, flags, b"", b"", scoped)
        maclen = HASHES[self.auth][1]
        priv_params, data = b"", scoped
        if self.priv:
            self._salt = (self._salt + 1) & 0xFFFFFFFFFFFFFFFF
            priv_params = self._salt.to_bytes(8, "big")
            data = tlv(OCT, priv_encrypt(self.privkind, self._keys[1], boots, etime, priv_params, scoped))

        def build(mac):
            return self._msg_v3(mid, eid, boots, etime, user, flags, mac, priv_params, data)
        mac = hmac.new(self._keys[0], build(b"\x00" * maclen), HASHES[self.auth][0]).digest()[:maclen]
        return build(mac)

    # -- parsing
    def _parse(self, data, expect_id):
        tag, body, _ = read(data)
        parts = items(body)
        ver = int.from_bytes(parts[0][1], "big")
        if ver == 3:
            return self._parse_v3(data, parts, expect_id)
        if ver not in (0, 1) or parts[2][0] != RESPONSE:
            raise _Stale()
        return self._pdu_result(parts[2][1], expect_id)

    def _parse_v3(self, raw, parts, expect_id):
        gd = items(parts[1][1])
        flags = gd[2][1][0]
        sec = self._sec_params(raw)
        data_tag, data = parts[3]
        if flags & 0x02 and data_tag == OCT:
            if not (self._keys and self._keys[1]):
                raise _Stale()
            scoped = read(priv_decrypt(self.privkind, self._keys[1], sec["boots"], sec["time"], sec["priv"], data))[1]
        elif data_tag == SEQ:
            scoped = data
        else:
            raise _Stale()
        if flags & 0x01 and self.auth:
            maclen = HASHES[self.auth][1]
            if len(sec["auth"]) != maclen:
                raise SnmpError("the reply was not authenticated as expected")
            lo, hi = _auth_span(raw)
            blank = raw[:lo] + b"\x00" * maclen + raw[hi:]
            want = hmac.new(self._keys[0], blank, HASHES[self.auth][0]).digest()[:maclen]
            if not hmac.compare_digest(want, sec["auth"]):
                raise SnmpError("the SNMPv3 reply failed its authentication check (wrong password?)")
        pdu_tag, pdu = items(scoped)[2]
        if pdu_tag == REPORT:
            rid, _st, _ix, vbs = self._pdu_fields(pdu)
            for o, _v in vbs:
                if o == NOT_IN_TIME_WINDOW:
                    self._engine = (sec["engine_id"], sec["boots"], sec["time"], time.monotonic())
                    raise _Resync()
                if o in USM_ERRORS:
                    raise SnmpError(USM_ERRORS[o])
            raise SnmpError("the device refused the SNMPv3 request")
        if pdu_tag != RESPONSE:
            raise _Stale()
        return self._pdu_result(pdu, expect_id)

    @staticmethod
    def _pdu_fields(pdu):
        f = items(pdu)
        rid = int.from_bytes(f[0][1], "big", signed=True)
        st, ix = int.from_bytes(f[1][1], "big"), int.from_bytes(f[2][1], "big")
        vbs = []
        for _t, vb in items(f[3][1]):
            o, v = items(vb)
            vbs.append((dec_oid(o[1]), decode_value(v[0], v[1])))
        return rid, st, ix, vbs

    def _pdu_result(self, pdu, expect_id):
        rid, st, ix, vbs = self._pdu_fields(pdu)
        if rid != expect_id:
            raise _Stale()
        if st:
            names = {1: "tooBig", 2: "noSuchName", 3: "badValue", 4: "readOnly", 5: "genErr", 16: "authorizationError"}
            raise SnmpError(f"the device returned an SNMP error: {names.get(st, st)}")
        return vbs

    # -- requests
    def _request(self, kind, varbinds, a=0, b=0):
        with self._lock:
            return self._request_locked(kind, varbinds, a, b)

    def _request_locked(self, kind, varbinds, a=0, b=0):
        for attempt in range(3):
            rid = self._next_id()
            try:
                return self._exchange(self._build(self._pdu(kind, rid, varbinds, a, b)), rid)
            except _Resync:
                continue
        raise SnmpError("could not agree the SNMPv3 time window with the device")

    def get(self, oids):
        """{oid: value}; a missing object is a NoSuch value (falsy)."""
        return dict(self._request(GET, list(oids)))

    def getnext(self, oid):
        vbs = self._request(GETNEXT, [oid])
        return vbs[0] if vbs else (oid, NoSuch("endOfMibView"))

    def walk(self, base, max_rows=4000):
        """All (oid, value) under base, using GETBULK (v2c/v3) or GETNEXT (v1)."""
        out, cur = [], base
        while len(out) < max_rows:
            if self.version == "1":
                o, v = self.getnext(cur)
                vbs = [(o, v)]
            else:
                vbs = self._request(GETBULK, [cur], 0, BULK_ROWS)
            done = False
            for o, v in vbs:
                if isinstance(v, NoSuch) or not under(o, base):
                    done = True
                    break
                out.append((o, v))
                cur = o
            if done or not vbs:
                break
        return out

    def column(self, col_oid):
        """{index_suffix: value} for a table column, e.g. column('1.3.6.1.2.1.31.1.1.1.1') -> {'2': b'eth0', ...}"""
        n = len(col_oid.strip(".").split("."))
        return {".".join(o.split(".")[n:]): v for o, v in self.walk(col_oid)}


def _auth_span(raw):
    """Where the authentication parameters sit in a v3 message (so they can be blanked to check the MAC)."""
    _t, p, _e = read_pos(raw, 0)
    _t, _s, p = read_pos(raw, p)            # version
    _t, _s, p = read_pos(raw, p)            # global data
    _t, sec_start, _e = read_pos(raw, p)    # security parameters (an OCTET STRING holding a SEQUENCE)
    _t, q, _e = read_pos(raw, sec_start)
    for _ in range(4):                      # engine id, boots, time, user
        _t, _s, q = read_pos(raw, q)
    _t, lo, hi = read_pos(raw, q)
    return lo, hi


BULK_ROWS = 40              # rows asked for per GETBULK request while walking a table: fewer round trips on a big table


class _Stale(Exception):
    """A reply that is not ours (late duplicate, wrong request id): keep listening."""


class _Resync(Exception):
    """The device told us the time: send the request again."""
