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
import threading, time
from concurrent.futures import ThreadPoolExecutor

from . import engine, probes

SLOW_PING_MS = 200.0
DEFAULT_INTERVAL = {"ping": 5.0, "tcp": 5.0, "dns": 5.0, "http": 30.0, "module": 15.0}
RECHECK_AFTER = 2.0     # a first failure is confirmed by a second look this soon
FAILING_INTERVAL = 3.0  # something that is down is watched closely, so recovery shows quickly
CONFIRM_FAILURES = 2


STARTUP_QUIET = 90     # seconds after the App starts when 'could not be checked' is not written to history: modules are still logging in
DEFAULT_CONFIRM = (2, 60)   # the site-wide grace unless the owner sets one: 2 failures in a row, lasting 60 seconds (proved on the owner's boxes, 0.65.1)


def _confirm_pair(c):
    n, s = c.get("failures", DEFAULT_CONFIRM[0]), c.get("seconds", DEFAULT_CONFIRM[1])
    return (n if isinstance(n, int) and n >= 1 else DEFAULT_CONFIRM[0]), (s if isinstance(s, (int, float)) and s >= 0 else DEFAULT_CONFIRM[1])


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Monitor:
    def __init__(self, runner=probes.run, clock=time.time, workers=8, inline=False, history=None):
        self.runner, self.clock, self.inline, self.history = runner, clock, inline, history
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
            time.sleep(0.5)

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
            self.history.record(states, {i: n.get("detail") for i, n in snap["nodes"].items()})        # with what each said, so History can say why
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
            ok, detail, ms = r[:3]
            warn = bool(len(r) > 3 and r[3].get("warn"))
            notice = bool(len(r) > 3 and r[3].get("notice"))
            if check["type"] == "ping" and ok is True and ms is not None:     # a slow link: three slow answers in a row, not one blip
                with self.lock:
                    t = self.tasks.get(key)
                    if t is not None:
                        t["slow"] = t.get("slow", 0) + 1 if ms >= check.get("slow_ms", SLOW_PING_MS) else 0
                        if t["slow"] >= 3:
                            notice, detail = True, f"{detail} · slow ({ms:.0f} ms)"
        except Exception as e:  # a probe must never kill the scheduler
            ok, detail, ms, warn, notice = None, f"check crashed: {e}", None, False, False
        now = self.clock()
        with self.lock:
            task = self.tasks.get(key)
            if not task or task["check"] != check:
                return
            task["busy"] = False
            prev = self.results.get(key)
            self._set_raw(key, ok, detail, ms, warn, notice, now)
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
            if changed or (prev and (prev["detail"] != detail)):
                self._bump()

    def _set_raw(self, key, ok, detail, ms, warn, notice, now):
        prev = self.raw.get(key)
        changed = prev is None or prev["ok"] != ok or bool(prev.get("warn")) != warn or bool(prev.get("notice")) != notice
        self.raw[key] = {"ok": ok, "detail": detail, "ms": ms, "at": _iso(now), "since": _iso(now) if changed else prev["since"], "warn": warn, "notice": notice}

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

    def snapshot(self):
        with self.lock:
            snap = engine.evaluate(self._eval_nodes(), dict(self.results), _iso(self.clock()))
            snap["version"] = self.version
            snap["configError"] = self.config_error
            return snap

    def wait_for_change(self, seen_version, timeout=15.0):
        with self.cv:
            if self.version == seen_version and not self.stopped:
                self.cv.wait(timeout)
            return self.version
