"""What the bell says about updates MonitorBox applied by itself (automatic updates only: an update the person starts by hand does not notify).

A note is {"id", "at", "kind": "app"|"module", "name", "from", "to"}. The App restarts to install, so its note is written just before it does and only shown once
the App is really running the new version (an install that failed says nothing). Notes are kept a week, at most ten, and go when the person taps them."""
import os

from . import store

KEEP_SECONDS = 7 * 24 * 3600
KEEP = 10


def _file(paths):
    return paths.p("data", "app", "auto-updates.json")


def _load(paths):
    d = store.read_json(_file(paths), [])
    return [n for n in d if isinstance(n, dict) and n.get("id")] if isinstance(d, list) else []


def add(paths, kind, name, frm, to, now):
    """Remember that an automatic update was applied (or, for the App, is about to be)."""
    notes = [n for n in _load(paths) if n["id"] != f"{kind}:{name}:{to}"]
    notes.append({"id": f"{kind}:{name}:{to}", "at": int(now), "kind": kind, "name": name, "from": frm, "to": to})
    store.write_json(_file(paths), notes[-KEEP:])


def add_problem(paths, source, text, now):
    """The App itself failed at its job (a module that will not start, an alert nobody could be sent, a backup that failed): the bell says so, with a link to the log.
    The same trouble again replaces its own note instead of piling up."""
    import hashlib
    nid = "problem:" + source + ":" + hashlib.sha1(text.encode()).hexdigest()[:10]
    notes = [n for n in _load(paths) if n["id"] != nid]
    notes.append({"id": nid, "at": int(now), "kind": "problem", "name": source, "text": text[:240], "go": f"#/logs?source={source}&level=error"})
    store.write_json(_file(paths), notes[-KEEP:])


def current(paths, app_version, now):
    """The notes to show, newest first. An App note shows only when the App now runs that version; one that never got there is dropped."""
    notes = _load(paths)
    keep = [n for n in notes if now - n.get("at", 0) < KEEP_SECONDS and (n.get("kind") != "app" or n.get("to") == app_version or n.get("from") == app_version)]
    if len(keep) != len(notes):
        store.write_json(_file(paths), keep)
    return [{**n, "text": text(n)} for n in sorted((n for n in keep if n.get("kind") != "app" or n.get("to") == app_version), key=lambda n: -n.get("at", 0))]


def text(n):
    if n.get("kind") == "problem":
        return str(n.get("text") or "Something went wrong.")
    who = "MonitorBox" if n.get("kind") == "app" else str(n.get("name") or "A module")
    return f"{who} updated itself from {n.get('from') or 'an earlier version'} to {n.get('to')}."


def dismiss(paths, ids):
    gone = {str(i) for i in ids or []}
    store.write_json(_file(paths), [n for n in _load(paths) if n["id"] not in gone])
