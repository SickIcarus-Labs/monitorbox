"""What this container is using, read from /proc and cgroup files. Never raises."""
import os, time

STARTED = time.time()


def _pss_mb(pid):
    """A process's fair share of memory: shared pages (the Python runtime every module loads) are split between the processes using them,
    so the processes add up to what the container really uses. Plain RSS counts them once per process and overstates the total by a lot.
    Needs smaps_rollup (Linux 4.14+); None when it cannot be read."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError):
        pass
    return None


def _rss_mb(pid):
    pss = _pss_mb(pid)
    if pss is not None:
        return pss
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError):
        pass
    return None


def _children(pid):
    out = []
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            out = [int(x) for x in f.read().split()]
    except (OSError, ValueError):
        pass
    return out


def _cgroup_mb():
    for path, div in (("/sys/fs/cgroup/memory.current", 1), ("/sys/fs/cgroup/memory/memory.usage_in_bytes", 1)):
        try:
            with open(path) as f:
                return round(int(f.read().strip()) / 1048576, 1)
        except (OSError, ValueError):
            continue
    return None


def _cache_mb():
    """File cache the kernel keeps in the container's count. It is handed back whenever anything else needs the memory, so it is not 'used'."""
    try:
        with open("/sys/fs/cgroup/memory.stat") as f:
            for line in f:
                if line.startswith("file "):
                    return round(int(line.split()[1]) / 1048576, 1)
    except (OSError, ValueError):
        pass
    return 0.0


def _used_mb():
    total = _cgroup_mb()
    return None if total is None else round(max(total - _cache_mb(), 0.0), 1)


def processes(names=None):
    """Every MonitorBox process with its fair share of memory, biggest first: what the owner needs to see where the memory goes.
    `names` maps a module's process id to its module name."""
    names = names or {}
    me = os.getpid()
    out = [{"name": "app", "mb": _rss_mb(me)}, {"name": "launcher", "mb": _rss_mb(os.getppid())}]
    for c in _children(me):
        out.append({"name": names.get(c) or f"module {c}", "mb": _rss_mb(c)})
    return sorted([x for x in out if x["mb"] is not None], key=lambda x: -x["mb"])


def about():
    me = os.getpid()
    launcher = os.getppid()
    modules = {}
    for c in _children(me):
        try:
            with open(f"/proc/{c}/cmdline") as f:
                modules[c] = (_rss_mb(c) or 0.0)
        except OSError:
            pass
    app_mb, launcher_mb = _rss_mb(me), _rss_mb(launcher)
    parts = [x for x in (app_mb, launcher_mb) if x is not None] + list(modules.values())
    return {"appMb": app_mb, "launcherMb": launcher_mb, "moduleProcesses": len(modules),
            "modulesMb": round(sum(modules.values()), 1), "processesTotalMb": round(sum(parts), 1) if parts else None,
            "containerMb": _used_mb(), "cacheMb": _cache_mb(), "uptimeSeconds": int(time.time() - STARTED)}
