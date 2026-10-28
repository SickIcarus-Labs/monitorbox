"""30 days of history, kept as state changes only.

One line per change in config/history.jsonl: {"t": epoch seconds, "n": node id, "s": state}. A node that
stays healthy for a month costs one line, so the file stays tiny, and because it lives under config/ every
backup carries it. A small sidecar (history.hb) holds the last time the App was running: if the App was
off for a while, every node reads Unknown for that gap, never Healthy and never Failed.

Availability = (healthy + degraded) / (healthy + degraded + failed). Unknown time is left out of the sum
because "we could not look" says nothing about the thing itself.
"""
import json, os, tempfile, threading, time

DAYS = 30
WHY_MAX = 400              # longest reason kept with a stretch (a port alert that names both ends of a link runs past 250 characters)


def _cut(w):
    return w if len(w) <= WHY_MAX else w[:WHY_MAX - 1].rstrip() + "…"      # says so when it is cut, never ends mid-word as if complete
GAP_SECONDS = 150          # an App that was silent this long left a hole in the record
HEARTBEAT_EVERY = 30
PRUNE_EVERY = 6 * 3600
STATES = ("healthy", "degraded", "failed", "unknown")


def _brief(min_seconds, node, start, end, state):
    """A Down or Degraded stretch that ended (or has run so far) in less than the node's confirmation seconds."""
    if not min_seconds or state not in ("failed", "degraded"):
        return False
    return (end - start) < min_seconds(node)


class History:
    def __init__(self, path, clock=time.time, days=DAYS):
        self.path, self.hb_path, self.clock, self.days = path, path[:-6] + ".hb" if path.endswith(".jsonl") else path + ".hb", clock, days
        self.lock = threading.Lock()
        self.events = []      # (t, node, state) oldest first
        self.why = {}         # (t, node) -> the reason it was not healthy, as the check said it (kept only for stretches that were not healthy)
        self.last = {}        # node -> last recorded state
        self.began = {}       # node -> when its current stretch began (the time of its last recorded change)
        self._hb = 0.0
        self._pruned = 0.0
        self._load()
        self._close_gap()
        self.prune()

    # -- file ------------------------------------------------------------
    def _load(self):
        try:
            with open(self.path) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if e.get("u"):              # a reason that grew while its stretch was going on: only the reason changes
                            self.why[(int(e["t"]), str(e["n"]))] = str(e["w"])[:WHY_MAX]
                            continue
                        self.events.append((int(e["t"]), str(e["n"]), str(e["s"])))
                        if e.get("w"):
                            self.why[(int(e["t"]), str(e["n"]))] = str(e["w"])[:WHY_MAX]
                    except (ValueError, KeyError, TypeError):
                        continue            # a torn last line must not lose the rest
        except OSError:
            return
        self.events.sort(key=lambda e: e[0])
        for t, n, s in self.events:
            self.last[n] = s
            self.began[n] = t

    def _append(self, rows, why=None):
        if not rows:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            for t, n, s in rows:
                rec = {"t": t, "n": n, "s": s}
                w = _cut(str((why or {}).get(n) or ""))
                if w and s != "healthy":
                    rec["w"] = w
                    self.why[(t, n)] = w
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.events.extend(rows)
        for t, n, s in rows:
            self.last[n] = s
            self.began[n] = t

    def _grow(self, ongoing, names):
        """Add the names a stretch that is still going on has not mentioned yet to its reason (kept inside WHY_MAX, with the cut shown)."""
        for n, s in ongoing.items():
            t, cur = self.began.get(n), None
            cur = self.why.get((t, n)) if t is not None else None
            if not cur:
                continue
            missing = [x for x in dict.fromkeys(str(x) for x in (names or {}).get(n) or []) if x and x not in cur]
            if not missing:
                continue
            new = _cut(cur + "; also " + ", ".join(missing))
            if new == cur:
                continue                    # already as long as it can be
            self.why[(t, n)] = new
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a") as f:
                    f.write(json.dumps({"t": t, "n": n, "s": s, "w": new, "u": 1}, separators=(",", ":")) + "\n")
            except OSError:
                pass

    def _close_gap(self):
        try:
            with open(self.hb_path) as f:
                then = int(float(f.read().strip()))
        except (OSError, ValueError):
            return
        now = int(self.clock())
        if now - then > GAP_SECONDS and self.last:
            self._append([(then, n, "unknown") for n, s in sorted(self.last.items()) if s != "unknown"])

    def _beat(self, now):
        if now - self._hb < HEARTBEAT_EVERY:
            return
        self._hb = now
        try:
            os.makedirs(os.path.dirname(self.hb_path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.hb_path), prefix=".tmp-")
            with os.fdopen(fd, "w") as f:
                f.write(str(int(now)))
            os.replace(tmp, self.hb_path)
        except OSError:
            pass

    # -- writing ---------------------------------------------------------
    def record(self, states, why=None, names=None):
        """states: node id -> state. Writes only what changed; 'pending' (no answer yet) is not a state.
        why: node id -> what the check said, kept with a stretch that was not healthy so the History page can say what it was.
        names: node id -> everything the check is naming right now (the ports rising, say). A stretch keeps the reason from when it began, so a name
        that turns up later in the same stretch is added to it ("; also Den, Port 8") instead of going unmentioned."""
        now = int(self.clock())
        with self.lock:
            rows = [(now, n, s) for n, s in sorted(states.items()) if s in STATES and self.last.get(n) != s]
            self._append(rows, why)
            self._grow({n: s for n, s in states.items() if s in STATES and s != "healthy" and n not in {r[1] for r in rows}}, names)
            self._beat(now)
            if now - self._pruned > PRUNE_EVERY:
                self.prune()

    def node_ids(self):
        with self.lock:
            return sorted({n for _t, n, _s in self.events})

    def clear(self):
        """Forget everything recorded. The next pass writes every node's current state as a fresh start."""
        with self.lock:
            self.events, self.last, self.why, self.began = [], {}, {}, {}
            try:
                open(self.path, "w").close()
            except OSError:
                pass

    def prune(self):
        """Drop what is older than the window, but keep the state each node was in when the window starts."""
        now = int(self.clock())
        self._pruned = now
        cut = now - self.days * 86400
        if not any(t < cut for t, _n, _s in self.events):
            return
        keep, carry = [], {}
        for t, n, s in self.events:
            if t >= cut:
                keep.append((t, n, s))
            else:
                carry[n] = s
        new = [(cut, n, s) for n, s in sorted(carry.items())] + keep
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".tmp-")
            with os.fdopen(fd, "w") as f:
                for t, n, s in new:
                    rec = {"t": t, "n": n, "s": s}
                    if (t, n) in self.why:
                        rec["w"] = self.why[(t, n)]
                    f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            self.events = new
        except OSError:
            pass                            # keep the old file; try again next time

    # -- reading ---------------------------------------------------------
    def timeline(self, node, seconds=None):
        """The last `seconds` (default: the whole window; never more than the window) of one node."""
        now = int(self.clock())
        span = min(max(int(seconds or self.days * 86400), 60), self.days * 86400)
        start = now - span
        with self.lock:
            ev = [(t, s) for t, n, s in self.events if n == node]
        segs = []
        for i, (t, s) in enumerate(ev):
            end = ev[i + 1][0] if i + 1 < len(ev) else now
            a, b = max(t, start), min(end, now)
            if b > a:
                if segs and segs[-1][2] == s and segs[-1][1] == a:
                    segs[-1][1] = b
                else:
                    segs.append([a, b, s])
        secs = {s: 0 for s in STATES}
        for a, b, s in segs:
            secs[s] += b - a
        up, down = secs["healthy"] + secs["degraded"], secs["failed"]
        return {"node": node, "days": self.days, "window": span, "now": now, "since": start, "segments": segs, "seconds": secs,
                "availability": round(100.0 * up / (up + down), 2) if up + down else None,
                "outages": sum(1 for a, b, s in segs if s == "failed")}

    def strip(self, nodes, hours=24, buckets=24, show=None, min_seconds=None):
        """One group's last `hours` as `buckets` equal slices, each the worst state any of `nodes` had in that slice
        (failed > degraded > healthy). Unknown shows only when nothing in the slice was known better, and a slice
        before any of them had a record is None. Used for the little 24 h bar on each main-screen card.
        show = the states the bar may display (a display choice, nothing is erased): a hidden Down or Degraded counts as healthy,
        a hidden Unknown counts as no record.
        min_seconds = node id -> seconds: a Down or Degraded stretch shorter than that is a brief blip (the confirmation setting) and counts as healthy."""
        show = {"failed", "degraded", "unknown"} if show is None else set(show)
        now = int(self.clock()); span = hours * 3600; start = now - span; step = span / buckets
        want = set(nodes)
        with self.lock:
            ev = sorted((t, n, s) for t, n, s in self.events if n in want)
        per = {}
        for t, n, s in ev:
            per.setdefault(n, []).append((t, s))
        rank = {"failed": 3, "degraded": 2, "healthy": 1, "unknown": 0}
        out = []
        for i in range(buckets):
            a, b = start + i * step, start + (i + 1) * step
            best = None
            for n, rows in per.items():
                for j, (t, st) in enumerate(rows):
                    end = rows[j + 1][0] if j + 1 < len(rows) else now
                    if st in ("failed", "degraded") and (st not in show or _brief(min_seconds, n, t, end, st)):
                        st = "healthy"
                    elif st == "unknown" and st not in show:
                        continue
                    if t < b and end > a and (best is None or rank[st] > rank[best]):
                        best = st
            out.append(best)
        return {"since": start, "now": now, "hours": hours, "buckets": out}

    def trouble(self, nodes, a, b, limit=300, show=None, newest_first=False, min_seconds=None, brief=False):
        """Every stretch inside [a, b) when one of `nodes` was not healthy (state, from, to), clipped to the window and
        oldest first. Answers 'what was that red slice?' for the card bars. Each item carries "why" (what the check said when the stretch began) when it was recorded.
        A stretch shorter than the node's confirmation seconds is a brief blip: left out, or with brief=True listed and marked "brief": true."""
        want = set(nodes); now = int(self.clock()); b = min(b, now)
        show = {"failed", "degraded", "unknown"} if show is None else set(show)
        with self.lock:
            ev = sorted((t, n, s) for t, n, s in self.events if n in want)
            whys = {k: v for k, v in self.why.items() if k[1] in want}
        per = {}
        for t, n, s in ev:
            per.setdefault(n, []).append((t, s))
        out = []
        for n, rows in per.items():
            for j, (t, st) in enumerate(rows):
                end = rows[j + 1][0] if j + 1 < len(rows) else now
                lo, hi = max(t, a), min(end, b)
                if st != "healthy" and st in show and hi > lo:
                    short = _brief(min_seconds, n, t, end, st)
                    if short and not brief:
                        continue
                    out.append({"node": n, "state": st, "from": lo, "to": hi, **({"brief": True} if short else {}), **({"why": whys[(t, n)]} if (t, n) in whys else {})})
        out.sort(key=lambda r: (r["from"], r["node"]), reverse=newest_first)   # when over the limit, the page keeps the newest
        return {"from": a, "to": b, "items": out[:limit], "more": max(0, len(out) - limit)}
