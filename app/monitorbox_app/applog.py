"""The App's own log: what it did and what it saw, in plain text, kept small.

Use it from anywhere:  applog.info("alerts", "Message to Home Assistant failed: no answer")
                       applog.debug("portwatch", "round 41: ...")      # written only while debug is on (it switches itself off after a day)

Two logs in `logs/`, each cut into files by size so that nothing can fill the card:
  * mb.log (normal): 5 files of 1 MB, nothing older than 14 days.
  * debug.log: 5 files of 10 MB, nothing older than 3 days. Switching debug off deletes nothing: the lines age out like any other.
One line per entry:  <id> <2026-10-30T00:54:12> <LEVEL> <source> <text>.  The id only ever grows (it starts from the clock), so a page can ask for "newer than".
A source that writes too fast is cut off for the rest of that minute and says so once. Passwords, tokens, community strings and the path of any web address are
removed from every line before it is written. Read-only, no network.
"""
import json, os, re, threading, time

LEVELS = ("debug", "info", "warning", "error")
NORMAL = {"name": "mb.log", "files": 5, "size": 1_000_000, "days": 14, "per_minute": 120}
DEBUG = {"name": "debug.log", "files": 5, "size": 10_000_000, "days": 3, "per_minute": 1200}
DEBUG_FOR = 24 * 3600
MAX_TEXT = 2000
RING = 3000                      # entries kept in memory for the page

_SECRET = re.compile(r"(?i)\b(pass(?:word|wd)?|authPassword|privPassword|token|secret|community|api[_-]?key|authorization|cookie|session|credential)s?\b(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_URL = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)(?:[^/\s@]*@)?([^/\s?#]+)(/[^\s]*)?")
_LINE = re.compile(r"^(\d+) (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d) (DEBUG|INFO|WARNING|ERROR) (\S+) ?(.*)$")


def redact(text):
    """What is safe to write down: no secrets, and a web address keeps only where it points (a webhook's path is the secret)."""
    text = str(text).replace("\r", " ").replace("\n", " ")
    text = _URL.sub(lambda m: f"{m.group(1)}{m.group(2)}" + ("/…" if m.group(3) and m.group(3) != "/" else ""), text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} ***", text)
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


class Log:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = folder, clock
        self.lock = threading.Lock()
        self.last_id = int(clock() * 1000)
        self.ring = []                                   # [(id, t, level, source, text)] newest last, normal and debug together
        self.rate = {}                                   # (log name, source) -> [window start, lines, suppressed]
        self.debug_file = os.path.join(folder, "debug-until.json")
        self._until = None
        self._sizes = {}                                 # path -> bytes, so a write is not a stat
        self.started = False
        self.on_error = None                             # called (source, text) for every error line: the bell tells the owner the App itself has trouble
        self._seen_files = False

    # ---- writing
    def _next_id(self):
        if not self._seen_files:
            self._seen_files = True                      # ids carry on from the newest line already on disk, even if the clock went back
            for spec in (NORMAL, DEBUG):
                for path in self._files(spec)[:2]:
                    for r in self._parse(path):
                        self.last_id = max(self.last_id, r[0])
        self.last_id = max(self.last_id + 1, int(self.clock() * 1000))
        return self.last_id

    def debug_until(self):
        if self._until is None:
            try:
                with open(self.debug_file) as f:
                    self._until = float(json.load(f).get("until") or 0)
            except (OSError, ValueError, TypeError, AttributeError):
                self._until = 0.0
        return self._until

    def debug_on(self):
        return self.debug_until() > self.clock()

    def set_debug(self, on):
        until = self.clock() + DEBUG_FOR if on else 0.0
        self._until = until
        try:
            os.makedirs(self.folder, exist_ok=True)
            with open(self.debug_file, "w") as f:
                json.dump({"until": until}, f)
        except OSError:
            pass
        self.write("info", "logs", "Debug logging switched on for 24 hours." if on else "Debug logging switched off.")
        return until

    def write(self, level, source, text):
        level = level if level in LEVELS else "info"
        if level == "debug" and not self.debug_on():
            return
        spec = DEBUG if level == "debug" else NORMAL
        source = re.sub(r"\W+", "-", str(source or "app"))[:24] or "app"
        text = redact(text)
        with self.lock:
            now = self.clock()
            win = self.rate.setdefault((spec["name"], source), [now, 0, 0])
            if now - win[0] >= 60:
                if win[2]:
                    self._emit(spec, "warning", source, f"Suppressed {win[2]} similar lines in the last minute (too many from one source).", now)
                win[0], win[1], win[2] = now, 0, 0
            win[1] += 1
            if win[1] > spec["per_minute"]:
                win[2] += 1
                return
            self._emit(spec, level, source, text, now)
        if level == "error" and self.on_error:
            try:
                self.on_error(source, text)
            except Exception:
                pass

    def _emit(self, spec, level, source, text, now):
        i = self._next_id()
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        line = f"{i} {stamp} {level.upper()} {source} {text}\n"
        self.ring.append((i, now, level, source, text))
        if len(self.ring) > RING:
            del self.ring[:len(self.ring) - RING]
        try:
            os.makedirs(self.folder, exist_ok=True)
            path = os.path.join(self.folder, spec["name"])
            size = self._sizes.get(path)
            if size is None:
                size = os.path.getsize(path) if os.path.exists(path) else 0
            if size + len(line) > spec["size"]:
                self._rotate(spec)
                size = 0
            with open(path, "a") as f:
                f.write(line)
            self._sizes[path] = size + len(line.encode())
        except OSError:
            pass                                          # a log that cannot be written must never stop the App

    def _rotate(self, spec):
        base = os.path.join(self.folder, spec["name"])
        try:
            last = f"{base}.{spec['files'] - 1}"
            if os.path.exists(last):
                os.remove(last)
            for n in range(spec["files"] - 2, 0, -1):
                if os.path.exists(f"{base}.{n}"):
                    os.replace(f"{base}.{n}", f"{base}.{n + 1}")
            os.replace(base, f"{base}.1")
        except OSError:
            pass
        self._sizes.pop(base, None)

    def purge(self):
        """Files with nothing newer than their age limit are removed (a quiet box would otherwise keep a stale file for ever)."""
        for spec in (NORMAL, DEBUG):
            for path in self._files(spec):
                try:
                    if self.clock() - os.path.getmtime(path) > spec["days"] * 86400:
                        os.remove(path)
                        self._sizes.pop(path, None)
                except OSError:
                    pass

    # ---- reading
    def _files(self, spec):
        base = os.path.join(self.folder, spec["name"])
        return [base] + [f"{base}.{n}" for n in range(1, spec["files"])]

    def _parse(self, path):
        out = []
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    m = _LINE.match(line.rstrip("\n"))
                    if m:
                        out.append((int(m.group(1)), m.group(2), m.group(3).lower(), m.group(4), m.group(5)))
        except OSError:
            pass
        return out

    def start(self, version, channel=""):
        """Called once when the App starts: clears what is too old, and says which build wrote what follows."""
        self.purge()
        self.started = True
        self.write("info", "app", f"MonitorBox {version} started" + (f" (channel {channel})" if channel else "") + ".")

    def entries(self, since=0, level="info", source=None, q=None, limit=300, include_debug=True):
        """Newest first. `level` is the lowest shown. Reads the files, not the memory, so a restart does not empty the page."""
        floor = LEVELS.index(level) if level in LEVELS else 1
        seen, rows = set(), []
        with self.lock:
            ring = list(self.ring)
        for r in ring:
            seen.add(r[0])
        pool = [(i, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)), lv, src, tx) for i, t, lv, src, tx in ring]
        specs = (NORMAL, DEBUG) if include_debug else (NORMAL,)
        if since <= 0 or not ring or since < ring[0][0]:
            for spec in specs:
                for path in self._files(spec):
                    for r in self._parse(path):
                        if r[0] not in seen:
                            seen.add(r[0]); pool.append(r)
        needle = (q or "").lower()
        for r in pool:
            if r[0] <= since or LEVELS.index(r[2]) < floor or (source and r[3] != source):
                continue
            if needle and needle not in (r[3] + " " + r[4]).lower():
                continue
            rows.append({"id": r[0], "time": r[1], "level": r[2], "source": r[3], "text": r[4]})
        rows.sort(key=lambda r: -r["id"])
        return rows[:limit]

    def summary(self):
        """(sources, counts) for the page: reads every file, so it is kept for 30 seconds."""
        c = getattr(self, "_summary", None)
        if c is None or self.clock() - c[0] > 30:
            c = self._summary = (self.clock(), self.sources(), self.counts())
        return c[1], c[2]

    def sources(self):
        return sorted({r["source"] for r in self.entries(limit=100000)})

    def counts(self, hours=24):
        """How many warnings and errors in the last hours (the Logs row says '3 errors in the last day')."""
        cut = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.clock() - hours * 3600))
        out = {"warning": 0, "error": 0}
        for r in self.entries(level="warning", limit=100000):
            if r["time"] >= cut:
                out[r["level"]] += 1
        return out

    def download(self):
        """Every kept line of both logs, oldest first, as one text."""
        rows = sorted(self.entries(level="debug", limit=10_000_000), key=lambda r: r["id"])
        return "".join(f"{r['time']} {r['level'].upper():7} {r['source']:12} {r['text']}\n" for r in rows)


_log = None


def setup(folder, version="", channel="", clock=time.time):
    global _log
    _log = Log(folder, clock)
    _log.start(version, channel)
    return _log


def get():
    return _log


def _w(level, source, text):
    if _log is not None:
        try:
            _log.write(level, source, text)
        except Exception:
            pass                                          # logging must never break what it is logging


def log(level, source, text): _w(level, source, text)
def debug(source, text): _w("debug", source, text)
def info(source, text): _w("info", source, text)
def warning(source, text): _w("warning", source, text)
def error(source, text): _w("error", source, text)
def debug_on(): return _log is not None and _log.debug_on()
