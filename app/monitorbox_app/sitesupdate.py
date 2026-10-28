""""Update all sites": one button on the main box that tells every linked site to install what is waiting, then installs here.

The sites are asked first and are not waited for: each is sent the same request the Updates page of that site sends ("install every update waiting"),
and this box does not hold back for the answer, because a site installing the App restarts and may take a while to be back. Only this box's own
update waits until each request has been on its way for a moment, because installing the App here restarts this box. The sites decide for
themselves what is waiting (an item pinned to a version stays there), exactly as if the button had been pressed on them. Nothing here
runs unless a person pressed the button; a site's own automatic update setting is not touched."""
import io
import json
import threading
import time

from . import peer as peermod

GRACE = 3.0          # seconds a request is given to reach its site before this box goes on to update itself


class SitesUpdate:
    def __init__(self, peer, local_apply_all, clock=time.time, grace=GRACE):
        self.peer, self.local, self.clock, self.grace = peer, local_apply_all, clock, grace
        self.lock = threading.Lock()
        self.state = None

    def _running(self):
        return bool(self.state) and (self.state["local"]["state"] in ("waiting", "working") or any(r["state"] == "asking" for r in self.state["sites"]))

    def status(self):
        with self.lock:
            if not self.state:
                return {"running": False, "sites": [], "local": None}
            return {**json.loads(json.dumps(self.state)), "running": self._running()}

    def start(self):
        """Ask every linked site, then update this box. Returns at once with the starting state; progress is read with status()."""
        sites = [s for s in self.peer.get()["sites"] if (s.get("link") or {}).get("state") == "linked"]
        with self.lock:
            if self._running():
                raise ValueError("Sites are already being updated.")
            self.state = {"at": int(self.clock()), "sites": [{"id": s["id"], "name": s.get("name") or "A site", "state": "asking", "message": ""} for s in sites], "local": {"state": "waiting", "message": ""}}
        threading.Thread(target=self._run, args=(sites,), daemon=True).start()
        return self.status()

    def _set(self, which, **kw):
        with self.lock:
            if which == "local":
                self.state["local"].update(kw)
            else:
                next(r for r in self.state["sites"] if r["id"] == which).update(kw)

    def _ask(self, site, sent):
        sid = site["id"]
        try:
            threading.Timer(self.grace, sent.set).start()                  # the request is on its way after a moment, answered or not
            body = b"{}"
            conn, resp = self.peer.open(sid, "POST", "/peer/api/apply-all", {"X-MB": "1", "Content-Type": "application/json"}, io.BytesIO(body), len(body), timeout=300)
            try:
                doc = json.loads(resp.read() or b"{}")
            finally:
                conn.close()
            if resp.status >= 400:
                self._set(sid, state="failed", message=str((doc or {}).get("error") or "That site would not install the updates."))
            elif (doc or {}).get("restarting"):
                self._set(sid, state="restarting", message=str(doc.get("message") or ""))
            else:
                self._set(sid, state="done", message=str(doc.get("message") or ""))
        except peermod.PeerError as e:
            # the link dropping after the request went out is what a site restarting looks like; one that never answered at all is a failure
            self._set(sid, state="failed", message=str(e)) if e.kind == "refused" or not sent.is_set() else self._set(sid, state="restarting", message="The site stopped answering, which is what happens while it restarts.")
        except Exception as e:
            self._set(sid, state="failed", message=str(e)[:200])
        finally:
            sent.set()

    def _run(self, sites):
        sents = []
        for s in sites:
            ev = threading.Event()
            sents.append(ev)
            threading.Thread(target=self._ask, args=(s, ev), daemon=True).start()
        for ev in sents:
            ev.wait(self.grace + 30)
        self._set("local", state="working")
        try:
            r = self.local() or {}
            self._set("local", state="restarting" if r.get("restarting") else "done", message=str(r.get("message") or ""))
        except Exception as e:
            self._set("local", state="failed", message=str(e)[:200])
