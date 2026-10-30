"""How long things take, kept in memory only: the last few samples of each kind of request and each module call.
Nothing is written to disk and nothing leaves the box; it is read by Settings > Advanced > Performance."""
import threading, time

KEEP = 200
_lock = threading.Lock()
_data = {}                      # (kind, key) -> list of milliseconds, newest last
_since = time.time()


def record(kind, key, ms):
    with _lock:
        v = _data.setdefault((kind, key), [])
        v.append(float(ms))
        if len(v) > KEEP:
            del v[0:len(v) - KEEP]


SLOW_MS = 3000
_slow = []                      # the last few module calls that took longer than SLOW_MS: [time, what, ms]


def slow(what, ms):
    """Remembers a slow module call and which connection it was for, so the performance report can say which device is slow."""
    if ms < SLOW_MS:
        return
    with _lock:
        _slow.append([time.time(), str(what)[:80], float(ms)])
        del _slow[:-10]


def slow_calls():
    now = time.time()
    with _lock:
        return [{"what": w, "ms": round(ms), "agoSec": int(now - t)} for t, w, ms in reversed(_slow)]


def _pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))]


def summary(kind):
    """Slowest first: [{key, count, avgMs, p95Ms, maxMs}]."""
    with _lock:
        items = [(k[1], list(v)) for k, v in _data.items() if k[0] == kind and v]
    out = []
    for key, v in items:
        s = sorted(v)
        out.append({"key": key, "count": len(v), "avgMs": round(sum(v) / len(v), 1), "p95Ms": round(_pct(s, 0.95), 1), "maxMs": round(s[-1], 1)})
    return sorted(out, key=lambda r: -r["avgMs"] * r["count"] ** 0.5)


def request_key(method, path):
    """One line per kind of request: no query, and ids and numbers folded so /api/site/ab12/state counts as the site hop."""
    p = path.split("?", 1)[0]
    if p.startswith("/api/site/"):
        rest = p[len("/api/site/"):].split("/", 1)
        return f"{method} site:/{rest[1] if len(rest) > 1 else ''}"
    return f"{method} {p}"


def skip(path):
    """Streams stay open for minutes; they are not a slow request."""
    return path.startswith(("/api/stream", "/api/live/events", "/api/perf")) or not path.startswith("/api/")


_open = {}                      # token -> (started, what): requests being answered right now. A request that never finishes is never recorded, so this is the only way to see one
_next = [0]
SLOW_REQUEST_MS = 1000


def begin(what):
    with _lock:
        _next[0] += 1
        _open[_next[0]] = (time.monotonic(), str(what)[:80])
        return _next[0]


def end(token):
    """Takes the request off the waiting list; returns how long it took in ms."""
    with _lock:
        t = _open.pop(token, None)
    return (time.monotonic() - t[0]) * 1000 if t else 0.0


def waiting(over_ms=SLOW_REQUEST_MS):
    """Requests that have been waiting longer than `over_ms`, oldest first: [{what, ageSec}]."""
    now = time.monotonic()
    with _lock:
        rows = sorted(((now - t) * 1000, w) for t, w in _open.values())
    return [{"what": w, "ageSec": round(ms / 1000, 1)} for ms, w in reversed(rows) if ms >= over_ms]


def reset():
    with _lock:
        _data.clear()
        _open.clear()
        del _slow[:]


def started():
    return _since
