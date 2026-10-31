"""Module install/update and the JSON-lines subprocess runner.

Protocol (one JSON object per line):
  App -> module : {"id": 1, "method": "hello", "params": {...}}
  module -> App : {"id": 1, "result": {...}}  or  {"id": 1, "error": "message"}
A module may also send unasked lines {"event": "...", "session": "<id>", "message": {...}} (live video setup messages); they go to whoever
listened for that session id (ModuleProcess.listen), and are dropped if nobody did.
"""
import json, os, re, select, shutil, subprocess, sys, threading, time
from . import perfstats, applog

from .store import read_json, write_json

ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
ALWAYS = ("wol",)                          # installed on a new box: nothing can detect that someone wants Wake-on-LAN, so it is assumed. Every other module is installed when its need shows up.
def always():
    """The modules a new box installs at once. MB_ALWAYS_MODULES (for the end-to-end tests, which want every module on a new box) is "*" for all, or a comma list."""
    v = os.environ.get("MB_ALWAYS_MODULES")
    return None if v == "*" else (tuple(x for x in v.split(",") if x) if v is not None else ALWAYS)


DEV_ONLY = ("hello",)                      # sample modules: only the dev channel offers them, and a box on beta or stable has none installed
RETIRED = {"unifi": "unifi-network"}      # renamed modules: the old one is no longer started


def current(ids):
    """Drop renamed-away modules from a list of ids. The release pointer keeps naming old versions of a module that was renamed."""
    return [i for i in ids if i not in RETIRED]


MODULE_CHECK_WAIT = 20   # seconds a module check may take: a busy UniFi console can take 10 s or more to answer one request (the modules wait 15 s)


class ModuleProcess:
    def __init__(self, mid, version, directory, entry):
        self.id, self.version = mid, version
        self.proc = subprocess.Popen(
            [sys.executable if e == "python3" else e for e in entry], cwd=directory,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}, text=True)
        self.lock = threading.Lock()      # guards writes to stdin and the table of waiting calls
        self.n = 0
        self.waiting = {}                 # id -> [event, message]
        self.dead = False
        self.listeners = {}               # session id -> callback(msg) for unasked event lines
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        """One reader hands each answer to whoever asked, so calls can overlap (a slow device
        must not hold up the others)."""
        try:
            for line in self.proc.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "event" in msg:
                    with self.lock:
                        cb = self.listeners.get(msg.get("session"))
                    if cb:
                        try: cb(msg)
                        except Exception: pass
                    continue
                with self.lock:
                    w = self.waiting.get(msg.get("id"))
                if w:
                    w[1] = msg
                    w[0].set()
        finally:
            with self.lock:
                self.dead = True
                for w in self.waiting.values():
                    w[0].set()
                gone = list(self.listeners.items())
            for sid, cb in gone:                                  # a live view cannot outlive its module
                try: cb({"event": "live", "session": sid, "message": {"type": "closed", "reason": "the module stopped"}})
                except Exception: pass

    def alive(self):
        return self.proc.poll() is None and not self.dead

    def listen(self, session, cb):
        with self.lock:
            self.listeners[session] = cb

    def unlisten(self, session):
        with self.lock:
            self.listeners.pop(session, None)

    def call(self, method, params=None, timeout=5):
        w = [threading.Event(), None]
        with self.lock:
            if not self.alive():
                raise RuntimeError("module is not running")
            self.n += 1
            i = self.n
            self.waiting[i] = w
            try:
                self.proc.stdin.write(json.dumps({"id": i, "method": method, "params": params or {}}) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                self.waiting.pop(i, None)
                raise RuntimeError("module is not running")
        try:
            if not w[0].wait(timeout):
                raise TimeoutError(f"{self.id} did not answer {method}")
        finally:
            with self.lock:
                self.waiting.pop(i, None)
        msg = w[1]
        if msg is None:
            raise RuntimeError("module exited")
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg.get("result")

    def stop(self):
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


HELLO_WAIT = 20          # seconds a starting module has to say hello: several coming up together on a small computer can be slow
START_AT_ONCE = 4        # modules started at the same time (all eight at once can starve each other on a small CPU)
STARTUP_HOLD = 90        # seconds after the app starts during which a module that is still coming up is waited for, not reported


class Modules:
    on_need = None                    # (module id) -> installs it; set by the App
    def __init__(self, paths, installer):
        self.paths = paths
        self.install_archive = installer  # (url, sha256, dest) -> dest
        self.running = {}
        self.lock = threading.Lock()
        self.retry_after = float(os.environ.get("MB_MODULE_RETRY_SECONDS", "10"))
        self.last_try = {}
        self.cards = {}                   # (module id, version) -> its describe answer, kept once known
        self.wanted = lambda: None        # () -> set of module ids some connection uses, or None for "all"
        self.starting = set()             # modules the app is bringing up right now: a check for one of them waits instead of reporting "not running"
        self.boot = time.monotonic()
        self.install_tried = {}           # module id -> when an install for a need was last tried
        self.timeouts = {}                # module id -> calls in a row that got no answer (logged once at 5, and when it answers again)
        self.last_err = {}                # module id -> the last reason it would not start, so the log says each reason once

    def state(self):
        return read_json(self.paths.modules_state, {})

    def _save(self, st):
        write_json(self.paths.modules_state, st, mode=0o644)

    def dir(self, mid, version):
        return os.path.join(self.paths.module_releases, mid, version)

    def _start(self, mid, version):
        d = self.dir(mid, version)
        man = read_json(os.path.join(d, "manifest.json"))
        if not man or man.get("id") != mid or man.get("version") != version:
            raise ValueError(f"{mid} {version}: manifest does not match")
        p = ModuleProcess(mid, version, d, man["entry"])
        p.call("hello", timeout=HELLO_WAIT)  # must answer before we call it healthy
        old = self.running.get(mid)
        self.running[mid] = p
        if old:
            old.stop()
        self.__dict__.setdefault("timeouts", {}).pop(mid, None)
        self.__dict__.setdefault("last_err", {}).pop(mid, None)
        pid = getattr(getattr(p, "proc", None), "pid", None)
        oldpid = getattr(getattr(old, "proc", None), "pid", None) if old else None
        why = threading.current_thread().name           # who asked for this start: the start-up pool, a check that found it dead, an update
        applog.info("modules", f"{mid} {version} started" + (f" (replacing {old.version})" if old and getattr(old, 'version', None) not in (None, version) else "")
                    + f" (pid {pid}" + (f", stopped pid {oldpid}" if oldpid else "") + f", by {why}).")

    def _to_start(self, st):
        want = self.wanted()
        return {mid: rec["active"] for mid, rec in st.items() if mid not in RETIRED and rec.get("active") and (want is None or mid in want)}      # the rest start the first time something asks for them

    def mark_starting(self):
        """Called before the checks begin: which modules are about to be started, so a check that runs first waits for its module instead of saying it is not running."""
        self.boot = time.monotonic()
        self.starting = set(self._to_start(self.state()))

    def start_all(self):
        with self.lock:
            st = self.state()
            if any(mid in st for mid in RETIRED):          # a renamed module's old record would show up as a stray card and be offered updates
                for mid in RETIRED:
                    st.pop(mid, None)
                self._save(st)
            todo = self._to_start(st)
            self.starting |= set(todo)

            def one(mid, version):
                try:
                    p = self.running.get(mid)
                    if p is not None and p.alive() and getattr(p, "version", version) == version:
                        return                                  # already up (started on demand): starting it again would stop it (#334)
                    self._start(mid, version)
                except Exception as e:
                    applog.error("modules", f"{mid} {version} did not start: {e}")
                    # shown as not running in the UI
                finally:
                    self.starting.discard(mid)
            # a few at a time: the wait is a fraction of all of them added up, without eight programs starving each other on a small computer
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=START_AT_ONCE, thread_name_prefix="modstart") as pool:
                list(pool.map(lambda kv: one(*kv), todo.items()))
            self.starting.clear()

    def apply_one(self, mid, entry):
        """Install and start one specific release. The old one keeps running if the new one will not start.
        Returns 'updated', 'unchanged' or 'failed: why'."""
        if not ID_RE.match(mid):
            return "failed: bad module id"
        if mid in RETIRED:
            return f"failed: {mid} was renamed to {RETIRED[mid]}"
        with self.lock:
            st = self.state()
            rec = st.get(mid, {})
            if rec.get("active") == entry["version"]:
                return "unchanged"
            try:
                self.install_archive(entry["url"], entry["sha256"], self.dir(mid, entry["version"]))
            except Exception as e:
                applog.error("modules", f"{mid} {entry['version']} could not be installed: {e}")
                return f"failed: {e}"
            try:
                self._start(mid, entry["version"])
            except Exception as e:
                applog.error("modules", f"{mid} {entry['version']} installed but would not start: {e}" + (f" ({rec.get('active')} keeps running)" if rec.get("active") else ""))
                failed = rec.get("failed", [])
                if entry["version"] not in failed:
                    failed.append(entry["version"])
                st[mid] = {**rec, "active": rec.get("active"), "failed": failed}
                if not rec.get("active"):
                    st.pop(mid)
                self._save(st)
                return f"failed: {e}"
            st[mid] = {"active": entry["version"], "failed": rec.get("failed", []), "sha256": entry["sha256"]}   # the build that runs: a repo that offers the same bytes can take over
            self._save(st)
            applog.info("modules", f"{mid} updated" + (f" from {rec['active']}" if rec.get("active") else "") + f" to {entry['version']}.")
            return "updated"

    def uninstall(self, mid):
        """Stop a module and delete it: its process, its record and its files. (Its settings, the connections that use it, are the App's to remove.)"""
        with self.lock:
            p = self.running.pop(mid, None)
            if p:
                p.stop()
            st = self.state()
            if mid not in st:
                raise ValueError(f"{mid} is not installed.")
            st.pop(mid)
            self._save(st)
            shutil.rmtree(os.path.join(self.paths.module_releases, mid), ignore_errors=True)
            for k in [k for k in self.cards if k[0] == mid]:
                del self.cards[k]
            self.last_try.pop(mid, None)

    def _await_start(self, mid):
        """A module the start-up batch is bringing up is waited for, never started a second time (#334: the LAN sampler or the
        graphs asked first, started their own copy, and the batch then replaced it, so its checks blinked Unknown)."""
        while mid in self.starting and time.monotonic() - self.boot < STARTUP_HOLD:
            p = self.running.get(mid)
            if p is not None and p.alive():
                return p
            time.sleep(0.1)
        return self.running.get(mid)

    def _revive(self, mid):
        """A module that died (a crash in its device library, say) is started again, at most every few seconds."""
        if mid in self.starting and time.monotonic() - self.boot < STARTUP_HOLD:
            return self._await_start(mid)
        if time.monotonic() - self.last_try.get(mid, -1e9) < self.retry_after or not self.lock.acquire(blocking=False):
            return self.running.get(mid)
        try:
            self.last_try[mid] = time.monotonic()
            rec = self.state().get(mid, {})
            if rec.get("active"):
                if self.running.get(mid) is not None and mid not in self.__dict__.setdefault("last_err", {}):
                    applog.warning("modules", f"{mid} stopped unexpectedly; starting it again.")
                try:
                    self._start(mid, rec["active"])
                except Exception as e:
                    if self.__dict__.setdefault("last_err", {}).get(mid) != str(e):
                        self.last_err[mid] = str(e)
                        applog.error("modules", f"{mid} {rec['active']} would not start again: {e}")
            return self.running.get(mid)
        finally:
            self.lock.release()

    def pids(self):
        """{process id: module name} of the modules running now."""
        out = {}
        for mid, p in list(self.running.items()):
            pid = getattr(getattr(p, "proc", None), "pid", None)
            if pid:
                out[pid] = mid
        return out

    def call(self, mid, method, params, timeout=10):
        """Ask a running module to do something. Raises RuntimeError with a plain message if it cannot.
        A module that is not installed yet is installed first (see `on_need`): a device that needs it is the need."""
        self._ensure(mid)
        p = self.running.get(mid)
        if not p or not p.alive():
            p = self._revive(mid)
        if not p or not p.alive():
            raise RuntimeError(f"the {mid} module is not running (install it under Settings, Versions)")
        t0 = time.monotonic()
        try:
            r = p.call(method, params, timeout=timeout)
            if self.__dict__.setdefault("timeouts", {}).pop(mid, 0) >= 5:
                applog.info("modules", f"{mid} is answering again.")
            return r
        except TimeoutError:
            tm = self.__dict__.setdefault("timeouts", {})
            n = tm[mid] = tm.get(mid, 0) + 1
            if n == 5:
                applog.error("modules", f"{mid} has not answered {n} calls in a row (last: {method}).")
            raise
        finally:
            ms = (time.monotonic() - t0) * 1000
            c = (params or {}).get("connection") if isinstance(params, dict) else None
            who = f" for {c.get('name') or c.get('id')}" if isinstance(c, dict) and (c.get("name") or c.get("id")) else ""      # the device's name only: never its address or credentials
            applog.debug("modules", f"call {mid}.{method}{who} took {ms:.0f} ms")
            perfstats.record("module", f"{mid}.{method}", ms)
            if ms >= perfstats.SLOW_MS:
                perfstats.slow(f"{mid}.{method}{who}", ms)

    def _ensure(self, mid):
        """Install a module that something now needs (a connection to a device of its kind). `on_need` is set by the App; it says
        why it will not, and tries a failed install again only after a while."""
        if not hasattr(self, "install_tried"):
            self.install_tried = {}
        if self.on_need and mid not in self.state() and mid not in RETIRED and time.monotonic() - self.install_tried.get(mid, -1e9) > 60:
            self.install_tried[mid] = time.monotonic()
            try:
                self.on_need(mid)
            except Exception:
                pass

    def listen(self, mid, session, cb):
        self._ensure(mid)
        p = self.running.get(mid)
        if not p or not p.alive():
            p = self._revive(mid)
        if not p or not p.alive():
            raise RuntimeError(f"the {mid} module is not running (install it under Settings, Versions)")
        p.listen(session, cb)

    def unlisten(self, mid, session):
        p = self.running.get(mid)
        if p:
            p.unlisten(session)

    def check(self, spec, conn):
        """Run one module check. Returns (ok, detail, ms, extra) like a probe.
        A module that cannot be reached, times out, or errors makes the check UNKNOWN, never failed:
        only the module itself can say a device is down, because it is the one that talked to it."""
        mid = spec["module"]
        p = self.running.get(mid)
        if (not p or not p.alive()) and mid in self.starting and time.monotonic() - self.boot < STARTUP_HOLD:
            return None, f"the {mid} module is starting", None, {"starting": True}          # not an answer yet: the monitor asks again in a moment
        if not p or not p.alive():
            p = self._revive(mid)
        if not p or not p.alive():
            return None, f"the {mid} module is not running", None, {}
        t0 = time.monotonic()
        try:
            res = p.call("check", {"check": spec.get("check"), "params": spec.get("params", {}),
                                   "connection": conn}, timeout=spec.get("timeout", MODULE_CHECK_WAIT) + 2)
        except Exception as e:
            return None, f"the {mid} module did not answer: {e}", None, {}
        ms = round((time.monotonic() - t0) * 1000, 1)
        state = (res or {}).get("state")
        detail = str((res or {}).get("detail", ""))
        ms = res.get("ms", ms) if isinstance(res, dict) else ms
        if state == "healthy":
            return True, detail, ms, ({"notice": True} if (res or {}).get("notice") else {})     # fine, but worth a line (a busy CPU)
        if state == "degraded":
            return True, detail, ms, {"warn": True}
        if state == "failed":
            return False, detail, ms, {}
        return None, detail or f"the {mid} module could not check this", ms, {}

    def describe(self):
        """Each active module's card. A card never changes for a version, so it is asked for once and kept; a module busy with a long check answers late, and asking
        them one after another made the Settings page wait 5 seconds for every busy module. The ones not yet known are asked together, for at most 2 seconds."""
        res = []
        st = self.state()
        todo = []
        for mid, rec in sorted((m, r) for m, r in st.items() if r.get("active")):
            p = self.running.get(mid)
            if p and p.alive() and (mid, rec["active"]) not in self.cards:
                todo.append((mid, rec["active"], p))
        got = {}

        def ask(item):
            mid, ver, p = item
            try:
                self.cards[(mid, ver)] = p.call("describe", timeout=2)
            except Exception as e:
                got[mid] = str(e)
        threads = [threading.Thread(target=ask, args=(t,), daemon=True) for t in todo]
        for t in threads:
            t.start()
        for t in threads:
            t.join(2.5)
        for mid, rec in sorted((m, r) for m, r in st.items() if r.get("active")):
            p = self.running.get(mid)
            card, err = None, None
            if p and p.alive():
                card = self.cards.get((mid, rec["active"]))
                err = None if card else got.get(mid, "did not answer yet")
            elif mid not in self.last_try and mid not in self.running:
                err = "idle until something uses it"       # lazy start: costs no memory until then
            else:
                err = "not running"
            res.append({"id": mid, "version": rec["active"], "pid": p.proc.pid if p and p.alive() else None,
                        "running": bool(p and p.alive()), "card": card, "error": err})
        return res

    def stop_all(self):
        for p in self.running.values():
            p.stop()
