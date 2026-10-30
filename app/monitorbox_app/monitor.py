"""Runs the checks and keeps the latest results. One scheduler, a small worker pool.

- every check has an interval (ping/tcp/dns 5 s, http 30 s unless set); a failing one is re-checked every 3 s
- a failure is confirmed by a quick second look (hold-down) before it is shown; a success shows at once
- grace period: a check (or its system, or the site default) can say "Down only after N failures in a row lasting S seconds"; until then
  a healthy thing stays healthy with a heads-up line, so alerts and the screen do not see it. Warnings (Degraded) are held the same way. Default
  2 failures and 60 seconds. History is NOT held back: it records what each check actually answered (`raw`), and the bars and History page
  hide stretches shorter than the grace seconds when drawn, so the setting only ever changes what is shown.
- "unknown" (could not be checked here) shows at once and is never turned into "failed"
- check_now() runs checks immediately and shows the answer without hold-down
- snapshot() = engine.evaluate(...) on the latest results; wait_for_change() lets the web layer push
"""
import json, os, threading, time
from concurrent.futures import ThreadPoolExecutor

from . import applog, engine, probes
from .store import write_json

SLOW_PING_MS = 200.0
DEFAULT_INTERVAL = {"ping": 5.0, "tcp": 5.0, "dns": 5.0, "http": 30.0, "module": 15.0}
RECHECK_AFTER = 2.0     # a first failure is confirmed by a second look this soon
FAILING_INTERVAL = 3.0  # something that is down is watched closely, so recovery shows quickly
CONFIRM_FAILURES = 2
STARTING_RECHECK = 1.0  # a check whose module is still coming up is asked again this soon
STALE_FOR = 120         # seconds after the App starts that readings saved before the restart may be shown while the fresh ones come in
CACHE_EVERY = 20        # seconds between saves of the latest readings
CACHE_MAX_AGE = 600     # saved readings older than this are not shown (a long outage is not "just a restart")


STARTUP_QUIET = 90     # seconds after the App starts when 'could not be checked' is not written to history: modules are still logging in
DEFAULT_CONFIRM = (2, 60)   # the site-wide grace unless the owner sets one: 2 failures in a row, lasting 60 seconds (proved on the owner's boxes, 0.65.1)


def _confirm_pair(c):
    n, s = c.get("failures", DEFAULT_CONFIRM[0]), c.get("seconds", DEFAULT_CONFIRM[1])
    return (n if isinstance(n, int) and n >= 1 else DEFAULT_CONFIRM[0]), (s if isinstance(s, (int, float)) and s >= 0 else DEFAULT_CONFIRM[1])


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Monitor:
    def __init__(self, runner=probes.run, clock=time.time, workers=8, inline=False, history=None, cache_path=None):
        self.runner, self.clock, self.inline, self.history = runner, clock, inline, history
        self.cache_path = cache_path       # where the latest readings are kept so a restart can open with them
        self._saved, self._saved_at, self._stale = -1, 0.0, False
        self._recorded = -1
        self.pool = None if inline else ThreadPoolExecutor(max_workers=workers, thread_name_prefix="probe")
        self.nodes = []
        self.power_follow = {}             # {Portainer environment node id: id of the system it runs on} (App.power_scan): the environment has the power of its machine
        self.power_guess = {}              # {system id: [UPS ids]} the box guessed from the UPS servers' client lists (App.power_scan); an owner's own poweredBy wins
        self.confirm = DEFAULT_CONFIRM   # the site-wide grace: (failures in a row, seconds)
        self.raw = {}           # what each check actually answered, whatever the grace period shows: this is what history records
        self.started = clock()
        self.tasks = {}     # "node/check" -> {"check","due","busy","fails"}
        self.results = {}   # "node/check" -> published result
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.version = 0
        self.config_error = None
        self.stopped = False
        self.thread = None

    # -- configuration ---------------------------------------------------
    def configure(self, nodes, config_error=None, confirm=None):
        with self.lock:
            self.nodes = nodes
            self.confirm = _confirm_pair(confirm or {})
            self.config_error = config_error
            keep, unchanged = {}, set()
            now = self.clock()
            for n in nodes:
                for c in n.get("checks", []):
                    key = f"{n['id']}/{c['id']}"
                    old = self.tasks.get(key)
                    if old and old["check"] == c:
                        old["node_confirm"] = (n.get("confirmFailures"), n.get("confirmSeconds"))
                        keep[key] = old
                        unchanged.add(key)
                    else:
                        keep[key] = {"check": c, "due": now, "busy": False, "fails": 0, "node_confirm": (n.get("confirmFailures"), n.get("confirmSeconds"))}
            self.tasks = keep
            self.results = {k: v for k, v in self.results.items() if k in unchanged}  # a changed check starts fresh
            self.raw = {k: v for k, v in self.raw.items() if k in unchanged}
            self._bump()

    def _bump(self):
        self.version += 1
        self.cv.notify_all()

    # -- running ---------------------------------------------------------
    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name="monitor")
        self.thread.start()

    def stop(self):
        self.stopped = True
        with self.lock:
            self.cv.notify_all()
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def _loop(self):
        while not self.stopped:
            self.run_due()
            self.record_history()
            self.expire_stale()
            self.save_cache()
            time.sleep(0.5)

    # -- the last readings, kept across a restart ---------------------------
    def save_cache(self, force=False):
        """Keeps the latest readings on disk (at most every 20 seconds, only when something changed) so a restart can open with them. Not in the first
        two minutes after a start: until then what is held is mostly the old file's, and it must not be replaced by a half-empty one."""
        if not self.cache_path:
            return
        with self.lock:
            now = self.clock()
            if not force and (self.version == self._saved or now - self._saved_at < CACHE_EVERY or now - self.started < STALE_FOR):
                return
            out = {"saved": now, "results": {k: v for k, v in self.results.items() if not v.get("stale")}}
            self._saved, self._saved_at = self.version, now
        try:
            write_json(self.cache_path, out, mode=0o600)
        except Exception:
            pass                        # a cache that cannot be written is only a slower start next time

    def restore(self):
        """Call after configure(), before the checks run: the readings saved before the restart are shown, marked as old, until each check's own answer replaces them.
        Only healthy or down ones (an unknown tells nothing), only for checks that still exist, only if saved recently."""
        if not self.cache_path:
            return 0
        try:
            with open(self.cache_path) as f:
                data = json.load(f)
        except Exception:
            return 0
        if not isinstance(data, dict) or not isinstance(data.get("results"), dict) or self.clock() - float(data.get("saved") or 0) > CACHE_MAX_AGE:
            return 0
        n = 0
        with self.lock:
            for k, v in data["results"].items():
                if k in self.tasks and k not in self.results and isinstance(v, dict) and v.get("ok") in (True, False) and isinstance(v.get("at"), str) and isinstance(v.get("since"), str):
                    self.results[k] = {"ok": v["ok"], "detail": str(v.get("detail") or ""), "ms": v.get("ms"), "at": v["at"], "since": v["since"],
                                       "warn": bool(v.get("warn")), "notice": bool(v.get("notice")), "stale": True}
                    n += 1
            if n:
                self._stale = True
                self._bump()
        return n

    def expire_stale(self):
        """Readings from before the restart are shown for two minutes at most: after that a check that has not answered is simply not known."""
        if not self._stale or self.clock() - self.started < STALE_FOR:
            return
        with self.lock:
            gone = [k for k, v in self.results.items() if v.get("stale")]
            for k in gone:
                del self.results[k]
            self._stale = False
            if gone:
                self._bump()

    def record_history(self):
        """Write state changes to the 30-day history (cheap: only when something changed, plus a heartbeat)."""
        if not self.history:
            return
        try:
            with self.lock:
                snap = engine.evaluate(self._eval_nodes(), dict(self.raw), _iso(self.clock())) if self.nodes else {"nodes": {}}      # the truth, not what the grace period shows
                self._recorded = self.version
            states = {i: n["state"] for i, n in snap["nodes"].items()}
            if self.clock() - self.started < STARTUP_QUIET:
                states = {i: s for i, s in states.items() if s != "unknown"}       # a restart is not something that happened to the systems
            names = {}
            for key, v in list(self.raw.items()):             # everything a check is naming (all the ports rising), so a stretch can name those that join it later
                if v.get("names"):
                    names.setdefault(key.rsplit("/", 1)[0], []).extend(v["names"])
            self.history.record(states, {i: n.get("detail") for i, n in snap["nodes"].items()}, names)        # with what each said, so History can say why
        except Exception:
            pass                        # history must never stop the monitor

    def run_due(self):
        now = self.clock()
        with self.lock:
            due = [k for k, t in self.tasks.items() if not t["busy"] and t["due"] <= now]
            for k in due:
                self.tasks[k]["busy"] = True
        for k in due:
            if self.inline:
                self._execute(k, False)
            else:
                self.pool.submit(self._execute, k, False)

    def _execute(self, key, manual):
        with self.lock:
            task = self.tasks.get(key)
            if not task:
                return
            check = task["check"]
        try:
            r = self.runner(check)
            if len(r) > 3 and r[3].get("starting"):         # its module is still coming up: no answer yet, so nothing is recorded and the screen keeps saying "checking"
                with self.lock:
                    t = self.tasks.get(key)
                    if t is not None and t["check"] == check:
                        t["busy"] = False
                        t["due"] = self.clock() + STARTING_RECHECK
                return
            ok, detail, ms = r[:3]
            warn = bool(len(r) > 3 and r[3].get("warn"))
            notice = bool(len(r) > 3 and r[3].get("notice"))
            names = [str(x) for x in (r[3].get("names") or [])][:200] if len(r) > 3 and isinstance(r[3].get("names"), list) else None
            if check["type"] == "ping" and ok is True and ms is not None:     # a slow link: three slow answers in a row, not one blip
                with self.lock:
                    t = self.tasks.get(key)
                    if t is not None:
                        t["slow"] = t.get("slow", 0) + 1 if ms >= check.get("slow_ms", SLOW_PING_MS) else 0
                        if t["slow"] >= 3:
                            notice, detail = True, f"{detail} · slow ({ms:.0f} ms)"
        except Exception as e:  # a probe must never kill the scheduler
            ok, detail, ms, warn, notice, names = None, f"check crashed: {e}", None, False, False, None
        now = self.clock()
        with self.lock:
            task = self.tasks.get(key)
            if not task or task["check"] != check:
                return
            task["busy"] = False
            prev = self.results.get(key)
            self._set_raw(key, ok, detail, ms, warn, notice, now, names)
            interval = check.get("interval", DEFAULT_INTERVAL.get(check["type"], 30.0))
            if ok is False and not manual and (prev is None or prev["ok"] is True) and task["fails"] + 1 < CONFIRM_FAILURES:
                task["fails"] += 1                      # not shown yet: look again soon
                task["due"] = now + RECHECK_AFTER
                return
            task["fails"] = 0 if ok is not False else task["fails"] + 1
            bad = ok is False or (ok is True and warn)  # a warning is held the same way as a failure
            if bad:                                     # the grace period (2 in a row and 60 seconds unless changed)
                task["streak"] = task.get("streak", 0) + 1
                task.setdefault("streak_since", now)
                need_n, need_s = self._grace(task)
                if task["streak"] < need_n or now - task["streak_since"] < need_s:
                    task["due"] = now + min(interval, FAILING_INTERVAL)
                    if prev is None:
                        return                          # nothing shown yet: stay "checking"
                    if prev["ok"] is not True or prev.get("warn"):
                        if prev.get("stale"):           # the saved reading from before the restart is confirmed: now it is a fresh one
                            self.results[key] = {**{k: v for k, v in prev.items() if k != "stale"}, "detail": detail, "at": _iso(now)}
                            self._bump()
                        return                          # already not healthy: keep showing what was observed
                    ok, warn, notice, detail = True, False, True, f"{'failed' if ok is False else 'warning'} just now, confirming ({task['streak']} of {need_n} in a row, {int(now - task['streak_since'])} s of {int(need_s)} s): {detail}"
            else:
                task["streak"] = 0
                task.pop("streak_since", None)
            task["due"] = now + (min(interval, FAILING_INTERVAL) if ok is False else interval)
            changed = prev is None or prev["ok"] != ok or bool(prev.get("warn")) != warn or bool(prev.get("notice")) != notice
            since = _iso(now) if changed else prev["since"]
            new = {"ok": ok, "detail": detail, "ms": ms, "at": _iso(now), "since": since, "warn": warn, "notice": notice}
            self.results[key] = new
            if prev is not None and (prev["ok"] != ok or bool(prev.get("warn")) != warn):
                self._log_change(key, check, prev, ok, warn, detail)
            if changed or (prev and (prev["detail"] != detail or prev.get("stale"))):
                self._bump()

    @staticmethod
    def _word(ok, warn):
        return "unknown" if ok is None else "failed" if ok is False else "warning" if warn else "healthy"

    def _log_change(self, key, check, prev, ok, warn, detail):
        """One line when a check really changes state (not a notice, not a first reading). Called with the lock held."""
        node = next((n for n in self.nodes if key.startswith(f"{n['id']}/")), None)
        label = " / ".join(x for x in ((node or {}).get("name"), check.get("name") or check.get("label") or check.get("id")) if x) or key
        was, now = self._word(prev["ok"], prev.get("warn")), self._word(ok, warn)
        applog.log("info" if now == "healthy" else "warning", "checks", f"{label}: {was} to {now}. {str(detail)[:300]}")

    def _set_raw(self, key, ok, detail, ms, warn, notice, now, names=None):
        prev = self.raw.get(key)
        changed = prev is None or prev["ok"] != ok or bool(prev.get("warn")) != warn or bool(prev.get("notice")) != notice
        self.raw[key] = {"ok": ok, "detail": detail, "ms": ms, "at": _iso(now), "since": _iso(now) if changed else prev["since"], "warn": warn, "notice": notice, **({"names": names} if names else {})}

    def grace_seconds(self, node_id):
        """How long a failure or warning must last before the screen shows it: the system's own value, else the site's."""
        for n in self.nodes:
            if n.get("id") == node_id and n.get("confirmSeconds") is not None:
                return n["confirmSeconds"]
        return self.confirm[1]

    def _grace(self, task):
        n, sec = task.get("node_confirm") or (None, None)
        return (n if n is not None else self.confirm[0]), (sec if sec is not None else self.confirm[1])

    def check_now(self, node_id=None, wait=False):
        """Check everything (or one node) right away, without hold-down."""
        with self.lock:
            keys = [k for k in self.tasks if node_id is None or k.split("/")[0] == node_id]
            for k in keys:
                self.tasks[k]["busy"] = True
        for k in keys:
            if self.inline or wait:
                self._execute(k, True)
            else:
                self.pool.submit(self._execute, k, True)
        return len(keys)

    # -- reading ---------------------------------------------------------
    def _eval_nodes(self):
        """The nodes with the power links the box has guessed filled in where the owner has not said (an owner's answer, even an empty list, always wins),
        and a Portainer environment taking the power of the machine it runs on."""
        g, f = self.power_guess, self.power_follow
        nodes = [dict(n, poweredBy=g[n["id"]]) if g and "poweredBy" not in n and n.get("id") in g else n for n in self.nodes]
        if f:
            by = {n["id"]: n for n in nodes}
            nodes = [dict(n, poweredBy=by[f[n["id"]]]["poweredBy"]) if n.get("id") in f and by.get(f[n["id"]], {}).get("poweredBy") else n for n in nodes]
        return nodes

    def snapshot(self, fresh=False):
        """The screen's view. Readings saved before a restart carry "(last reading before the restart)" until the fresh one arrives; fresh=True leaves them out (alerts never act on them)."""
        with self.lock:
            res = {k: v for k, v in self.results.items() if not (fresh and v.get("stale"))}
            res = {k: (dict(v, detail=(f"{v['detail']} " if v.get("detail") else "") + "(last reading before the restart)") if v.get("stale") else v) for k, v in res.items()}
            snap = engine.evaluate(self._eval_nodes(), res, _iso(self.clock()))
            snap["version"] = self.version
            snap["configError"] = self.config_error
            return snap

    def wait_for_change(self, seen_version, timeout=15.0):
        with self.cv:
            if self.version == seen_version and not self.stopped:
                self.cv.wait(timeout)
            return self.version
