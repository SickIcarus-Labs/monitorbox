import hashlib, hmac, os, secrets, threading, time
from . import applog
from .store import read_json, write_json

N, R, P = 2 ** 14, 8, 1
LIFETIME = 90 * 86400   # a sign-in lasts this long after its last use; every device has its own, so they never affect each other
MAX_SIGNED_IN = 50


def _hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)


def _th(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


class Auth:
    def __init__(self, paths):
        self.paths = paths
        self.sessions = {}  # in-memory only: this box's own internal tokens (token -> expiry)
        self.file = paths.p("data", "local", "sessions.json")   # not under data/app, so no backup ever carries live sign-ins to another box
        self.lock = threading.Lock()
        self.saved = read_json(self.file, {}) or {}   # sha256(token) -> {exp, fp}: kept on disk so an update or restart does not sign anyone out

    def _fp(self):
        """Ties every saved sign-in to the current password: change or reset it and they all stop working."""
        rec = read_json(self.paths.auth)
        return rec["hash"][:16] if rec else None

    def _save(self):
        try:
            write_json(self.file, self.saved)
        except OSError:
            pass

    def is_set(self):
        return bool(read_json(self.paths.auth))

    def set_password(self, password):
        if self.is_set():
            raise PermissionError("password already set")
        if len(password) < 8:
            raise ValueError("Use at least 8 characters.")
        salt = os.urandom(16)
        write_json(self.paths.auth, {"salt": salt.hex(), "hash": _hash(password, salt).hex()})

    def login(self, password):
        rec = read_json(self.paths.auth)
        if not rec:
            return None
        ok = hmac.compare_digest(_hash(password, bytes.fromhex(rec["salt"])), bytes.fromhex(rec["hash"]))
        if not ok:
            time.sleep(0.5)
            applog.warning("auth", "A sign-in with the wrong password was refused.")
            return None
        return self.issue()

    def issue(self):
        """A new signed-in device. Reached only after something proved who is asking: the password, or a registered passkey."""
        rec = read_json(self.paths.auth)
        if not rec:
            return None
        tok = secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self.saved = {h: r for h, r in self.saved.items() if r["exp"] > now}
            while len(self.saved) >= MAX_SIGNED_IN:            # keep the newest; an old forgotten browser goes first
                del self.saved[min(self.saved, key=lambda h: self.saved[h]["exp"])]
            self.saved[_th(tok)] = {"exp": now + LIFETIME, "fp": rec["hash"][:16]}
            self._save()
        applog.info("auth", "A device signed in.")
        return tok

    def valid(self, tok):
        tok = tok or ""
        exp = self.sessions.get(tok)
        now = time.time()
        if exp and exp > now:
            return True
        self.sessions.pop(tok, None)
        h = _th(tok)
        with self.lock:
            r = self.saved.get(h)
            if not r:
                return False
            if r["exp"] <= now or r["fp"] != self._fp():
                del self.saved[h]; self._save()
                return False
            if r["exp"] - now < LIFETIME - 86400:              # in use: slide the expiry forward, written at most about once a day
                r["exp"] = now + LIFETIME; self._save()
            return True

    def logout(self, tok):
        self.sessions.pop(tok or "", None)
        with self.lock:
            if self.saved.pop(_th(tok or ""), None):
                self._save()

    def signed_in(self):
        """How many devices are signed in right now (this box's own internal tokens do not count)."""
        now = time.time()
        with self.lock:
            return sum(1 for r in self.saved.values() if r["exp"] > now and r["fp"] == self._fp())

    def sign_out_others(self, keep_tok):
        """Every device except the one asking. For a lost phone: the passkey is removed, and any sign-in it left behind goes too."""
        keep = _th(keep_tok or "")
        with self.lock:
            gone = [h for h in self.saved if h != keep]
            for h in gone:
                del self.saved[h]
            if gone:
                self._save()
        return len(gone)
