"""Install the App named by the channel pointer, start it, roll back if unhealthy,
and serve a recovery page whenever the App is not running."""
import json, os, signal, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import artifacts, backup
from .layout import Layout

PROTOCOL = 3  # 2: understands {"action":"install",...} requests; 3: also {"action":"restore","backup":name} and shares backup.py
RESTART_EXIT = 75  # App exits with this to ask for a restart (after an update request)


class Launcher:
    def __init__(self, root, releases_url, channel="dev", port=8080,
                 health_timeout=30, app_cmd=None):
        self.L = Layout(root)
        self.releases_url = releases_url.rstrip("/")
        self.channel = channel
        self.port = port
        self.health_timeout = health_timeout
        self.app_cmd = app_cmd or [sys.executable, "-m", "monitorbox_app"]
        self.status = "starting"
        self.detail = ""
        self.proc = None
        self.stop = False
        self.restore_asked = False

    # -- small helpers ---------------------------------------------------
    def log(self, msg):
        line = time.strftime("%Y-%m-%dT%H:%M:%S ") + msg
        print(line, flush=True)
        try:
            with open(self.L.log, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def set_status(self, status, detail=""):
        self.status, self.detail = status, detail
        self.log(f"{status}: {detail}" if detail else status)

    def configured_channel(self):
        try:
            with open(self.L.config_file) as f:
                return json.load(f)["update"]["channel"]
        except Exception:
            return self.channel

    def read_request(self):
        try:
            with open(self.L.request) as f:
                req = json.load(f)
            os.unlink(self.L.request)
            return req
        except Exception:
            return None

    # -- state the App reads (what failed, what happened last) ------------
    def read_state(self):
        try:
            with open(self.L.state) as f:
                return json.load(f)
        except Exception:
            return {}

    def write_state(self, **changes):
        st = self.read_state()
        st.update(changes)
        tmp = self.L.state + ".new"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, self.L.state)

    def mark_failed(self, version):
        failed = self.read_state().get("failed", [])
        if version not in failed:
            failed.append(version)
        self.write_state(failed=failed[-20:])

    # -- install / select ------------------------------------------------
    def app_dir(self, version):
        return self.L.p("releases", "app", version)

    def install_and_switch(self, app):
        """Install one specific release ({version,url,sha256}) and make it current."""
        dest = self.app_dir(app["version"])
        artifacts.install_archive(app["url"], app["sha256"], dest)
        cur = artifacts.link_target(self.L.current)
        if cur != os.path.realpath(dest):
            if cur:
                artifacts.switch_link(self.L.previous, cur)
            artifacts.switch_link(self.L.current, dest)
            self.log(f"current -> {app['version']}")
        return app["version"]

    def first_install(self):
        """Nothing installed yet: take the channel's latest."""
        ptr = artifacts.fetch_json(f"{self.releases_url}/channels/{self.configured_channel()}.json")
        if not ptr.get("app"):
            return False
        self.install_and_switch(ptr["app"])
        return True

    def fall_back(self):
        """The App we just switched to would not start: go back to the one before it."""
        prev = artifacts.link_target(self.L.previous)
        cur = artifacts.link_target(self.L.current)
        if not prev or prev == cur:
            return None
        if cur:
            self.mark_failed(os.path.basename(cur))
        artifacts.switch_link(self.L.current, prev)
        self.log(f"fell back to {os.path.basename(prev)}")
        return (os.path.basename(cur) if cur else None, os.path.basename(prev))

    # -- restore ---------------------------------------------------------
    def do_restore(self, name):
        """Stage, check, swap. The App is not running. Returns True if the new files are in place and
        still need proving (run() starts the App and commits or undoes)."""
        try:
            archive = backup.path_of(self.L.root, name)
            man = backup.stage(self.L.root, archive)
        except backup.BackupError as e:
            self.log(f"restore refused: {e}")
            self.write_state(last={"restore": name, "result": f"failed: {e}"})
            return False
        try:
            if os.path.exists(self.L.config_file):  # a safety copy of what we are about to replace
                backup.create(self.L.root, "config", "pre-restore")
        except Exception as e:
            self.log(f"could not make the safety backup: {e}")
        try:
            backup.swap(self.L.root, man)
        except Exception as e:
            self.log(f"restore failed while swapping, putting things back: {e}")
            backup.undo(self.L.root)
            self.write_state(last={"restore": name, "result": f"failed: {e}"})
            return False
        if not os.path.isdir(self.L.current):  # no App to test it with (fresh volume): nothing to go back to either
            backup.commit(self.L.root)
            self.write_state(last={"restore": name, "result": "ok"})
            self.log(f"restored {name}")
            return True
        self.write_state(restoring=name)
        self.log(f"restored {name}; checking the App starts with it")
        return True

    def finish_restore(self, ok):
        name = self.read_state().get("restoring")
        if not name:
            return
        if ok:
            backup.commit(self.L.root)
            self.write_state(restoring=None, last={"restore": name, "result": "ok"})
            self.log(f"restore of {name} confirmed")
        else:
            backup.undo(self.L.root)
            self.write_state(restoring=None, last={"restore": name, "result": "failed: the App would not start with that backup, so your previous files were put back"})
            self.log(f"restore of {name} undone: App did not start")

    # -- run the App -----------------------------------------------------
    def start_app(self):
        env = dict(os.environ, MB_CONFIG=self.L.root, MB_PORT=str(self.port),
                   MB_RELEASES_URL=self.releases_url, MB_CHANNEL=self.configured_channel(),
                   PYTHONPATH=self.L.current, PYTHONDONTWRITEBYTECODE="1",
                   MB_LAUNCHER_PATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logf = open(self.L.p("logs", "app.log"), "a")
        self.proc = subprocess.Popen(self.app_cmd, cwd=self.L.current, env=env,
                                     stdout=logf, stderr=subprocess.STDOUT)

    def healthy(self):
        deadline = time.time() + self.health_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.3)
        return False

    def stop_app(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # -- recovery page ---------------------------------------------------
    PAGE = """<!doctype html><meta name=viewport content='width=device-width'><title>MonitorBox recovery</title>
<body style='font-family:system-ui;background:#161507;color:#eee;max-width:42em;margin:2em auto;padding:0 1em'>
<h1>MonitorBox is not running</h1>
<p><b id=st></b> <span id=dt></span></p>
<h2>Restore from a backup</h2>
<p id=last></p>
<p id=pw style='display:none'>Admin password: <input id=pwv type=password autocomplete=current-password></p>
<div id=list></div>
<p>Or upload a backup file from your device: <input id=up type=file accept=.tgz,.gz></p>
<p id=msg style='color:#ffd166'></p>
<h2>Recent log</h2><pre id=log style='white-space:pre-wrap'></pre>
<script>
const $=i=>document.getElementById(i), H={'X-MB':'1'};
const say=t=>$('msg').textContent=t;
const pwd=()=>$('pwv').value;
async function load(){
  const r=await (await fetch('/recover/info')).json();
  $('st').textContent=r.status; $('dt').textContent=r.detail; $('log').textContent=r.log;
  $('pw').style.display=r.passwordRequired?'block':'none';
  $('last').textContent=r.last&&r.last.restore!==undefined?('Last restore: '+(r.last.restore||'')+' - '+r.last.result):'';
  $('list').innerHTML='';
  if(!r.backups.length) $('list').textContent='No backups are stored on this box. Upload one below.';
  for(const b of r.backups){
    const d=document.createElement('div'); d.style.margin='.4em 0';
    const t=document.createElement('span'); t.textContent=b.created.replace('T',' ').replace('Z',' UTC')+' - '+b.kind+' ('+(b.name.includes('-uploaded-')?'uploaded':b.label)+') '+(b.appVersion?'App '+b.appVersion+' ':'')+Math.ceil(b.size/1024)+' KB ';
    const x=document.createElement('button'); x.textContent='Restore';
    x.onclick=()=>restore(b.name);
    d.append(t,x); $('list').append(d);
  }
}
async function restore(name){
  if(!confirm('Replace the current settings with this backup?')) return;
  const r=await fetch('/recover/restore',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify({name,password:pwd()})});
  const j=await r.json(); say(r.ok?'Restoring... this page will reload when MonitorBox is back.':(j.error||'Failed'));
  if(r.ok) setTimeout(()=>location.reload(),6000);
}
$('up').onchange=async e=>{
  const f=e.target.files[0]; if(!f) return;
  say('Uploading...');
  const r=await fetch('/recover/upload',{method:'POST',headers:{...H,'X-Password':pwd()},body:f});
  const j=await r.json(); say(r.ok?'Uploaded. Press Restore on it in the list above.':(j.error||'Failed')); load();
};
load(); setInterval(load,5000);
</script>"""

    def serve_recovery(self, until):
        """Serve the recovery page until until() is true, a restore was asked for, or we are told to stop."""
        launcher = self
        done = lambda: until() or launcher.restore_asked or launcher.stop

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def reply(self, code, obj=None, body=None, ctype="application/json"):
                body = body if body is not None else json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/health":
                    return self.reply(503, {"ok": False, "launcher": launcher.status})
                if self.path == "/recover/info":
                    tail = ""
                    try:
                        with open(launcher.L.log) as f:
                            tail = "".join(f.readlines()[-30:])
                    except OSError:
                        pass
                    return self.reply(200, {
                        "status": launcher.status, "detail": launcher.detail, "log": tail,
                        "passwordRequired": not backup.password_ok(launcher.L.root, ""),
                        "backups": backup.list_backups(launcher.L.root),
                        "last": launcher.read_state().get("last")})
                self.reply(503, body=launcher.PAGE.encode(), ctype="text/html; charset=utf-8")

            def allowed(self, password):
                if self.headers.get("X-MB") != "1":
                    self.reply(403, {"error": "forbidden"})
                    return False
                if not backup.password_ok(launcher.L.root, password):
                    time.sleep(0.5)
                    self.reply(403, {"error": "Wrong admin password."})
                    return False
                return True

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                if self.path == "/recover/restore":
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError:
                        return self.reply(400, {"error": "bad json"})
                    if not self.allowed(body.get("password", "")):
                        return
                    try:
                        backup.path_of(launcher.L.root, str(body.get("name", "")))
                    except backup.BackupError as e:
                        return self.reply(400, {"error": str(e)})
                    with open(launcher.L.request, "w") as f:
                        json.dump({"action": "restore", "backup": body["name"]}, f)
                    launcher.restore_asked = True
                    return self.reply(200, {"ok": True})
                if self.path == "/recover/upload":
                    if not self.allowed(self.headers.get("X-Password", "")):
                        return
                    if n <= 0 or n > backup.MAX_BYTES:
                        return self.reply(400, {"error": "That file is empty or too large."})
                    os.makedirs(backup.backups_dir(launcher.L.root), exist_ok=True)
                    tmp = os.path.join(backup.backups_dir(launcher.L.root), f".tmp-upload-{os.getpid()}")
                    try:
                        with open(tmp, "wb") as f:
                            left = n
                            while left:
                                chunk = self.rfile.read(min(left, 1 << 20))
                                if not chunk:
                                    break
                                f.write(chunk)
                                left -= len(chunk)
                        backup.validate(tmp)
                        final = os.path.join(backup.backups_dir(launcher.L.root),
                                             time.strftime("monitorbox-uploaded-%Y%m%d-%H%M%S.tgz"))
                        os.replace(tmp, final)
                        return self.reply(200, {"ok": True, "name": os.path.basename(final)})
                    except backup.BackupError as e:
                        return self.reply(400, {"error": str(e)})
                    finally:
                        if os.path.exists(tmp):
                            os.unlink(tmp)
                self.reply(404, {"error": "not found"})

        try:
            srv = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError:
            while not done():
                time.sleep(0.5)
            return
        srv.timeout = 0.5
        while not done():
            srv.handle_request()
        srv.server_close()

    # -- main loop -------------------------------------------------------
    def run(self):
        self.L.ensure()
        self.write_state(protocol=PROTOCOL)
        if backup.pending(self.L.root):  # we died in the middle of a restore: go back to what worked
            self.log("found an unfinished restore; undoing it")
            backup.undo(self.L.root)
            self.write_state(restoring=None, last={"restore": None, "result": "failed: interrupted, previous files put back"})

        def on_term(*_):
            self.stop = True
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()  # so a docker stop ends the App too
        signal.signal(signal.SIGTERM, on_term)
        failures = 0
        while not self.stop:
            req = self.read_request()
            try:
                act = (req or {}).get("action")
                if act == "restore":
                    self.restore_asked = False
                    self.do_restore(str(req.get("backup", "")))
                elif act == "install":
                    self.install_and_switch(req["app"])
                    self.write_state(trying=req["app"]["version"])
                elif act == "update":  # Apps before 0.3.0 ask this way: take the channel's latest
                    self.first_install()
                    self.write_state(trying=os.path.basename(artifacts.link_target(self.L.current) or ""))
                elif act == "rollback":  # ...and this way: go back one
                    prev = artifacts.link_target(self.L.previous)
                    cur = artifacts.link_target(self.L.current)
                    if prev and prev != cur:
                        artifacts.switch_link(self.L.previous, cur)
                        artifacts.switch_link(self.L.current, prev)
                elif not os.path.isdir(self.L.current):
                    self.first_install()
            except Exception as e:  # network/hash problem: keep what we have
                self.log(f"install failed: {e}")
                if req:
                    self.write_state(last={"version": (req.get("app") or {}).get("version"), "result": f"failed: {e}"})
            if not os.path.isdir(self.L.current):
                self.set_status("waiting", "No App release is published on this channel yet (or it could not be reached). Retrying.")
                t0 = time.time()
                self.serve_recovery(lambda: time.time() - t0 > 30)
                continue
            self.set_status("starting", "App")
            self.start_app()
            restoring = bool(self.read_state().get("restoring"))
            if self.healthy():
                self.finish_restore(True)
                failures = 0
                trying = self.read_state().get("trying")
                if trying:
                    self.write_state(trying=None, last={"version": trying, "result": "ok"})
                self.set_status("running")
                code = self.proc.wait()
                self.set_status("stopped", f"App exited with code {code}")
                continue
            self.stop_app()
            if restoring:
                self.finish_restore(False)
                continue
            failures += 1
            moved = self.fall_back()
            if moved:
                self.write_state(trying=None, last={"version": moved[0], "result": f"failed to start; running {moved[1]}"})
                self.set_status("rollback", f"{moved[0]} did not start; running {moved[1]} again.")
                continue
            self.set_status("failed", "App will not start and there is no previous version.")
            t0 = time.time()
            self.serve_recovery(lambda: time.time() - t0 > min(60, 5 * failures))
        self.stop_app()
