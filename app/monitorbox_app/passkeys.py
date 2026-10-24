"""Passkey (WebAuthn) sign-in, standard library only.

Scope on purpose: the ES256 passkey type (ECDSA over P-256 with SHA-256) that iPhones, iPads, Macs, Android and Windows all make, with no
attestation (we do not care which maker built the authenticator, only that the same private key signs in again). Anything else is refused
with a plain message. Every check the WebAuthn standard asks of a relying party is here and tested: the challenge is ours and used once,
the origin and the site name are exactly the owner's public name, the person was present and verified (Face ID, Touch ID, PIN), the
signature is valid for the stored key, and a counter that goes backwards means a cloned key and is refused."""
import base64, hashlib, hmac, json, os, secrets, struct, threading, time
from .store import read_json, write_json

CHALLENGE_TTL = 300
MAX_PASSKEYS = 20

# ---- P-256 ECDSA verification (public data only, so nothing here has to be constant-time) ----
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _on_curve(pt):
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1, p2):                                  # affine points, None is the point at infinity
    if p1 is None: return p2
    if p2 is None: return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2:
        if (y1 + y2) % P == 0: return None
        m = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (m * m - x1 - x2) % P
    return (x3, (m * (x1 - x3) - y1) % P)


def _mul(k, pt):
    r = None
    while k:
        if k & 1: r = _add(r, pt)
        pt = _add(pt, pt); k >>= 1
    return r


def _der_sig(sig):
    """(r, s) from a DER ECDSA signature, or None if it is not exactly that."""
    try:
        if sig[0] != 0x30: return None
        i = 2
        if sig[1] & 0x80:
            n = sig[1] & 0x7F
            if n != 1: return None
            if sig[2] != len(sig) - 3: return None
            i = 3
        elif sig[1] != len(sig) - 2: return None
        out = []
        for _ in range(2):
            if sig[i] != 0x02: return None
            ln = sig[i + 1]; v = sig[i + 2:i + 2 + ln]
            if len(v) != ln or ln == 0 or v[0] & 0x80: return None
            out.append(int.from_bytes(v, "big")); i += 2 + ln
        return tuple(out) if i == len(sig) else None
    except IndexError:
        return None


def verify_es256(x, y, message, der_signature):
    q = (x, y)
    if not _on_curve(q): return False
    rs = _der_sig(der_signature)
    if not rs: return False
    r, s = rs
    if not (1 <= r < N and 1 <= s < N): return False
    e = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, N)
    pt = _add(_mul(e * w % N, G), _mul(r * w % N, q))
    return pt is not None and pt[0] % N == r


# ---- the little CBOR subset a passkey uses ----
def cbor(data, i=0, depth=0):
    """(value, next index). Integers, byte and text strings, arrays, maps, true/false/null. Nothing else exists in a passkey."""
    if depth > 8: raise ValueError("too deep")
    b = data[i]; mt, ai = b >> 5, b & 31; i += 1
    if ai < 24: n = ai
    elif ai in (24, 25, 26, 27):
        ln = 1 << (ai - 24); n = int.from_bytes(data[i:i + ln], "big"); i += ln
    else: raise ValueError("unsupported")
    if mt == 0: return n, i
    if mt == 1: return -1 - n, i
    if mt in (2, 3):
        v = data[i:i + n]
        if len(v) != n: raise ValueError("short")
        return (bytes(v) if mt == 2 else v.decode()), i + n
    if mt == 4:
        out = []
        for _ in range(n):
            v, i = cbor(data, i, depth + 1); out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(n):
            k, i = cbor(data, i, depth + 1); v, i = cbor(data, i, depth + 1); out[k] = v
        return out, i
    if mt == 7 and ai in (20, 21, 22): return {20: False, 21: True, 22: None}[ai], i
    raise ValueError("unsupported")


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s):
    s = str(s)
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _client_data(raw_b64, kind, challenge, origin):
    raw = unb64u(raw_b64)
    cd = json.loads(raw)
    if cd.get("type") != kind: raise ValueError("That was not the right kind of passkey answer.")
    if not hmac.compare_digest(str(cd.get("challenge", "")), challenge): raise ValueError("The passkey answer was for a different request.")
    if cd.get("origin") != origin: raise ValueError("The passkey answer came from a different address than " + origin + ".")
    if cd.get("crossOrigin"): raise ValueError("Passkeys cannot be used from inside another page.")
    return raw


def _auth_data(ad, rp_id, need_attested):
    if len(ad) < 37: raise ValueError("The passkey answer was too short.")
    if not hmac.compare_digest(ad[:32], hashlib.sha256(rp_id.encode()).digest()): raise ValueError("The passkey is for a different site name.")
    flags = ad[32]
    if not flags & 0x01: raise ValueError("No one was present at the device.")
    if not flags & 0x04: raise ValueError("The device did not check who you are (Face ID, Touch ID or a PIN).")
    count = struct.unpack(">I", ad[33:37])[0]
    return flags, count


class Passkeys:
    def __init__(self, paths):
        self.file = paths.p("config", "passkeys.json")        # in config/, so a backup carries the passkeys
        self.lock = threading.Lock()
        self.pending = {}                                       # challenge handle -> (kind, challenge, expiry)

    def data(self):
        d = read_json(self.file, {}) or {}
        d.setdefault("credentials", [])
        return d

    def count(self):
        return len(self.data()["credentials"])

    def listing(self):
        return [{"id": c["id"], "name": c["name"], "created": c["created"], "lastUsed": c.get("lastUsed")} for c in self.data()["credentials"]]

    def _challenge(self, kind):
        now = time.time()
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v[2] > now}
            if len(self.pending) > 200: self.pending.clear()
            handle, ch = secrets.token_urlsafe(16), b64u(os.urandom(32))
            self.pending[handle] = (kind, ch, now + CHALLENGE_TTL)
        return handle, ch

    def _take(self, handle, kind):
        with self.lock:
            v = self.pending.pop(str(handle), None)
        if not v or v[0] != kind or v[2] < time.time(): raise ValueError("That passkey request expired. Try again.")
        return v[1]

    def register_options(self, rp_id):
        d = self.data()
        if len(d["credentials"]) >= MAX_PASSKEYS: raise ValueError(f"At most {MAX_PASSKEYS} passkeys.")
        if not d.get("userId"):
            d["userId"] = b64u(os.urandom(16)); write_json(self.file, d)
        handle, ch = self._challenge("register")
        return {"handle": handle, "publicKey": {
            "challenge": ch, "rp": {"id": rp_id, "name": "MonitorBox"},
            "user": {"id": d["userId"], "name": "owner", "displayName": "MonitorBox owner"},
            "pubKeyCredParams": [{"type": "public-key", "alg": -7}], "timeout": 120000, "attestation": "none",
            "authenticatorSelection": {"residentKey": "required", "requireResidentKey": True, "userVerification": "required"},
            "excludeCredentials": [{"type": "public-key", "id": c["id"]} for c in d["credentials"]]}}

    def register_finish(self, handle, body, rp_id, origin, name):
        ch = self._take(handle, "register")
        try:
            _client_data(body["response"]["clientDataJSON"], "webauthn.create", ch, origin)
            att, _ = cbor(unb64u(body["response"]["attestationObject"]))
            if not isinstance(att, dict): raise ValueError("x")
            ad = att["authData"]
            if not isinstance(ad, bytes): raise ValueError("x")
            flags, count = _auth_data(ad, rp_id, True)
            if not flags & 0x40: raise ValueError("The passkey answer held no new key.")
            i = 37 + 16
            ln = struct.unpack(">H", ad[i:i + 2])[0]; cid = ad[i + 2:i + 2 + ln]; i += 2 + ln
            key, _ = cbor(ad, i)
            if not isinstance(key, dict): raise ValueError("x")
        except (KeyError, TypeError, IndexError, ValueError, AttributeError, struct.error) as e:
            raise ValueError(str(e) if isinstance(e, ValueError) and e.args and len(str(e)) > 20 else "That did not look like a passkey answer.")
        if key.get(1) != 2 or key.get(3) != -7 or key.get(-1) != 1:
            raise ValueError("This passkey uses a type MonitorBox does not support yet. Try another device.")
        x, y = key.get(-2), key.get(-3)
        if not (isinstance(x, bytes) and isinstance(y, bytes) and len(x) == len(y) == 32) or not _on_curve((int.from_bytes(x, "big"), int.from_bytes(y, "big"))):
            raise ValueError("The passkey's key was not valid.")
        if not cid or len(cid) > 1023 or b64u(cid) != str(body.get("id", b64u(cid))):
            raise ValueError("The passkey's id did not match.")
        d = self.data()
        if any(c["id"] == b64u(cid) for c in d["credentials"]): raise ValueError("That passkey is already added.")
        name = str(name or "").strip()[:60] or "Passkey"
        d["credentials"].append({"id": b64u(cid), "x": x.hex(), "y": y.hex(), "signCount": count, "name": name, "created": int(time.time()), "lastUsed": None})
        write_json(self.file, d)
        return name

    def login_options(self, rp_id):
        if not self.count(): raise ValueError("No passkeys have been added.")
        handle, ch = self._challenge("login")
        return {"handle": handle, "publicKey": {"challenge": ch, "rpId": rp_id, "timeout": 120000, "userVerification": "required", "allowCredentials": []}}

    def login_finish(self, handle, body, rp_id, origin):
        """True when the passkey is one of ours and signed this very challenge; ValueError with a plain reason otherwise."""
        ch = self._take(handle, "login")
        try:
            raw_cd = _client_data(body["response"]["clientDataJSON"], "webauthn.get", ch, origin)
            ad = unb64u(body["response"]["authenticatorData"])
            flags, count = _auth_data(ad, rp_id, False)
            sig = unb64u(body["response"]["signature"])
            cid = b64u(unb64u(body["rawId"]))
        except (KeyError, TypeError, IndexError, ValueError, AttributeError, struct.error) as e:
            raise ValueError(str(e) if isinstance(e, ValueError) and len(str(e)) > 20 else "That did not look like a passkey answer.")
        d = self.data()
        c = next((c for c in d["credentials"] if c["id"] == cid), None)
        if not c or not verify_es256(int(c["x"], 16), int(c["y"], 16), ad + hashlib.sha256(raw_cd).digest(), sig):
            raise ValueError("That passkey was not accepted.")
        if (count or c["signCount"]) and count <= c["signCount"]:
            raise ValueError("That passkey looks copied (its counter went backwards), so it was refused.")
        c["signCount"], c["lastUsed"] = count, int(time.time())
        write_json(self.file, d)
        return True

    def remove(self, cid):
        d = self.data()
        n = len(d["credentials"])
        d["credentials"] = [c for c in d["credentials"] if c["id"] != str(cid)]
        if len(d["credentials"]) == n: raise ValueError("No such passkey.")
        write_json(self.file, d)
        return len(d["credentials"])
