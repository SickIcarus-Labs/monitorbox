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


def reset():
    with _lock:
        _data.clear()


def started():
    return _since
