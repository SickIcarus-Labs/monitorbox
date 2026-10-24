"""Backup and restore against the real launcher and App (no network): restore with the App up,
restore with the App DOWN after the volume was wiped, a wrong password on the recovery page,
a bad upload, and a restore that would leave the App unable to start (it must undo itself)."""
import json, os, shutil, subprocess, sys, time, unittest, urllib.error, urllib.request

import test_e2e as base
from test_backup_roundtrip import FakeDevices, make_connections, secret_pairs

REPO = base.REPO
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
from monitorbox_launcher import backup  # noqa: E402
from monitorbox_app.auth import Auth  # noqa: E402
from monitorbox_app.store import Paths, write_json  # noqa: E402

Client, wait = base.Client, base.wait
PASSWORD = "correct horse"


def node(name):
    return {"builtinInternet": True, "nodes": [
        {"id": "gw", "name": name, "group": "Network", "critical": True,
         "checks": [{"type": "ping", "target": "192.0.2.250"}]}]}


class BackupE2E(unittest.TestCase):
    setUp, tearDown = base.E2E.setUp, base.E2E.tearDown
    write_json, read_json = staticmethod(base.E2E.write_json), staticmethod(base.E2E.read_json)
    publish, start_launcher, health_version = base.E2E.publish, base.E2E.start_launcher, base.E2E.health_version
    wait_all_modules = base.E2E.wait_all_modules

    def sign_in(self, c):
        wait(lambda: c.get("/api/health")["version"], what="App up")
        if not c.get("/api/health")["passwordSet"]:
            self.assertTrue(c.post("/api/setup", {"password": PASSWORD})["ok"])
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])

    def raw(self, c, path, data=None, headers=None):
        req = urllib.request.Request(c.base + path, data, {"X-MB": "1", **(headers or {})})
        try:
            with c.op.open(req, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def stop_launcher(self):
        self.proc.terminate()
        self.proc.wait(20)
        self.proc = None

    def restore_result(self, name):
        """The launcher's own record of how the restore went (the App restarts, so wait on the file)."""
        def look():
            last = self.read_json(os.path.join(self.cfg, "data", "launcher", "state.json")).get("last") or {}
            return last if last.get("restore") == name else None
        return wait(look, timeout=60, what="restore result")

    def config(self):
        try:
            return self.read_json(os.path.join(self.cfg, "config", "monitorbox.json"))
        except FileNotFoundError:
            return {}

    def add_connections(self, conns):
        cfg = self.config()
        cfg["connections"] = conns
        self.write_json(os.path.join(self.cfg, "config", "monitorbox.json"), cfg)

    # ------------------------------------------------------------------
    def test_restore_with_app_up_then_wipe_and_restore_with_app_down(self):
        conns = make_connections()
        dev = FakeDevices(conns)
        self.addCleanup(dev.close)
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        self.sign_in(c)
        self.assertEqual(c.post("/api/config/monitoring", {"monitoring": node("Gateway one"), "revision": 0})["revision"], 1)
        self.add_connections(conns)

        shown = {"view": "detail", "hist": 604800, "cammode": "live", "dw": 777, "gwin": 900, "gpanel": 1800}       # every display choice gets a different value
        self.assertEqual(c.post("/api/display", shown), shown)
        graphs = [{"id": "gx-1", "title": "Distinct graph title 41", "connection": "conn-one", "interface": "ifc-alpha"},
                  {"id": "gx-2", "title": "Distinct graph title 42", "connection": "conn-two", "interface": "ifc-beta"}]
        self.write_json(os.path.join(self.cfg, "config", "graphs.json"), graphs)
        hook = "http://ha-one.example.invalid:8123/api/webhook/fake-backup-hook-61"
        email_saved = {"host": "smtp.mail-one.example.invalid", "port": 2587, "security": "ssl", "user": "user-one@example.invalid", "password": "fake-backup-mailpw-71",
                       "from": "from-one@example.invalid", "to": ["to-one@example.invalid", "to-two@example.invalid"]}
        al = {"enabled": True, "site": "Distinct site 62", "delaySeconds": 63, "homeAssistant": {"webhook": hook}, "email": {**email_saved, "to": "to-one@example.invalid, to-two@example.invalid"}}
        c.post("/api/alerts", al)
        alf = os.path.join(self.cfg, "config", "alerts.json")
        ha_saved = {"webhook": hook, "url": "http://ha-one.example.invalid:8123", "origin": "http://box-one.example.invalid:8099", "refresh": "fake-backup-refresh-66",
                    "token": "", "devices": ["mobile_app_device_seven", "mobile_app_device_eight"]}
        cfg_a = self.read_json(alf); cfg_a["homeAssistant"] = ha_saved; self.write_json(alf, cfg_a)
        sf = os.path.join(self.cfg, "config", "sites.json")
        sites_saved = {"name": "Distinct box name 71", "listen": {"enabled": False, "port": 8471},
                       "managers": [{"id": "fake-mgr-72", "name": "Distinct manager 73", "key": "74" * 32, "since": 1750000075}],
                       "sites": [{"id": "site-76", "name": "Distinct site 77", "address": "far.example.invalid:8478", "mid": "fake-mid-79", "key": "80" * 32, "since": 1750000081}]}
        self.write_json(sf, sites_saved)
        made = c.post("/api/backups", {"kind": "config"})
        self.assertEqual(made["backups"][0]["kind"], "config")
        c.post("/api/backups", {"kind": "full"})
        listing = c.get("/api/backups")["backups"]
        self.assertEqual({b["kind"] for b in listing}, {"config", "full"})
        full = next(b for b in listing if b["kind"] == "full")["name"]
        conf = next(b for b in listing if b["kind"] == "config")["name"]
        code, full_bytes = self.raw(c, "/api/backups/download?name=" + full)
        self.assertEqual(code, 200)
        self.assertGreater(len(full_bytes), 1000)
        self.assertEqual(self.raw(c, "/api/backups/download?name=../x.tgz")[0], 400)

        # --- restore while the App is up: change things, then bring the old ones back
        self.assertEqual(c.post("/api/config/monitoring", {"monitoring": node("Gateway CHANGED"), "revision": 1})["revision"], 2)
        self.add_connections([{"id": "x", "type": "http", "host": "h", "token": "changed-token"}])
        self.assertEqual(c.post("/api/display", {"view": "summary", "hist": 3600, "cammode": "pics", "dw": 0, "gwin": 60, "gpanel": 300})["view"], "summary")
        self.write_json(os.path.join(self.cfg, "config", "graphs.json"), [])
        c.post("/api/alerts", {"enabled": False, "site": "Changed site 64", "delaySeconds": 5, "homeAssistant": {"webhook": "http://other.example.invalid/api/webhook/fake-changed-hook-65"},
                                "email": {"host": "smtp.changed.example.invalid", "port": 465, "security": "starttls", "user": "user-changed@example.invalid", "password": "fake-changed-mailpw-72",
                                          "from": "from-changed@example.invalid", "to": "to-changed@example.invalid"}})
        cfg_b = self.read_json(alf); cfg_b["homeAssistant"].update({"url": "http://other.example.invalid:8123", "refresh": "fake-changed-refresh-67", "devices": ["mobile_app_device_nine"]}); self.write_json(alf, cfg_b)
        self.write_json(sf, {"name": "Changed 82", "listen": {"enabled": False, "port": 8483}, "managers": [], "sites": []})
        self.assertTrue(c.post("/api/restore", {"name": conf})["restarting"])
        self.assertEqual(self.restore_result(conf), {"restore": conf, "result": "ok"})
        wait(lambda: Client(self.port).get("/api/health")["version"], what="App back after restore")
        c = Client(self.port)
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])
        self.assertEqual(c.get("/api/backups")["last"], {"restore": conf, "result": "ok"})
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Gateway one")
        self.assertEqual(self.config()["connections"], conns)
        self.assertEqual(c.get("/api/display"), shown, "the display choices come back with the backup")
        self.assertEqual(c.get("/api/graphs")["graphs"], graphs, "the graph list comes back with the backup")
        got = c.get("/api/alerts")
        self.assertEqual((got["enabled"], got["site"], got["delaySeconds"], got["homeAssistant"]["webhook"], got["homeAssistant"]["host"]), (True, "Distinct site 62", 63, hook, "ha-one.example.invalid:8123"),
                         "the alert settings come back with the backup")
        self.assertEqual(self.read_json(alf)["homeAssistant"], ha_saved, "the Home Assistant sign-in, address and ticked devices come back too")
        self.assertEqual((got["homeAssistant"]["connected"], got["homeAssistant"]["devices"]), (True, ["mobile_app_device_seven", "mobile_app_device_eight"]))
        self.assertEqual(self.read_json(alf)["email"], email_saved, "the email settings, password included, come back too")
        self.assertEqual(self.read_json(sf), sites_saved, "the sites and their keys come back with the backup")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "restore")))  # the copies from before were dropped
        # the safety copy of what was replaced is kept in backups
        self.assertTrue(any(b["label"] == "pre-restore" for b in c.get("/api/backups")["backups"]))

        # --- wipe the whole volume; the App cannot be installed (nothing published), so it is DOWN
        self.stop_launcher()
        shutil.rmtree(self.cfg)
        ptr = os.path.join(self.rel, "channels", "dev.json")
        p = self.read_json(ptr)
        p["app"] = None
        self.write_json(ptr, p)
        self.start_launcher()
        c = Client(self.port)
        info = wait(lambda: (lambda i: i if i["status"] == "waiting" else None)(c.get("/recover/info")), what="recovery page")
        self.assertFalse(info["passwordRequired"])  # nothing to protect on a wiped box
        self.assertEqual(info["backups"], [])
        with self.assertRaises(urllib.error.HTTPError) as cm:
            c.get("/api/health")
        self.assertEqual(cm.exception.code, 503)
        # a bad file is refused and nothing changes
        self.assertEqual(self.raw(c, "/recover/upload", b"not a backup")[0], 400)
        code, out = self.raw(c, "/recover/upload", full_bytes)
        self.assertEqual(code, 200, out)
        name = json.loads(out)["name"]
        self.assertEqual(self.raw(c, "/recover/restore", json.dumps({"name": name}).encode())[0], 200)
        wait(lambda: Client(self.port).get("/api/health")["version"] == "0.1.0", timeout=60, what="App up from the restored volume")
        c = Client(self.port)
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])  # same dashboard, same password
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Gateway one")
        restored = self.config()["connections"]
        self.assertEqual(restored, conns)
        for a, b in zip(conns, restored):
            self.assertEqual(dev.login(a["id"], b), 200)

    def test_recovery_page_asks_for_the_admin_password(self):
        os.makedirs(os.path.join(self.cfg, "config"))
        paths = Paths(self.cfg)
        Auth(paths).set_password(PASSWORD)
        write_json(paths.config, {"schema": 4, "marker": "from-backup"})
        name = backup.create(self.cfg, "config", "manual")
        write_json(paths.config, {"schema": 4, "marker": "current"})
        ptr = os.path.join(self.rel, "channels", "dev.json")
        self.start_launcher()  # nothing published: the App is down
        c = Client(self.port)
        info = wait(lambda: (lambda i: i if i["status"] == "waiting" else None)(c.get("/recover/info")), what="recovery page")
        self.assertTrue(info["passwordRequired"])
        body = lambda pw: json.dumps({"name": name, "password": pw}).encode()
        self.assertEqual(self.raw(c, "/recover/restore", body("wrong password!"))[0], 403)
        self.assertEqual(self.raw(c, "/recover/upload", b"x", {"X-Password": "wrong password!"})[0], 403)
        self.assertEqual(self.config()["marker"], "current")
        req = urllib.request.Request(c.base + "/recover/restore", body(PASSWORD))  # no X-MB header: refused
        with self.assertRaises(urllib.error.HTTPError):
            c.op.open(req)
        self.assertEqual(self.raw(c, "/recover/restore", body(PASSWORD))[0], 200)
        wait(lambda: self.config()["marker"] == "from-backup", what="restore applied")
        self.assertEqual(c.get("/recover/info")["last"], {"restore": name, "result": "ok"})

    def test_bad_uploads_and_unknown_names_are_refused_with_the_app_up(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        self.sign_in(c)
        before = self.config()
        self.assertEqual(self.raw(c, "/api/backups/upload", b"garbage")[0], 400)
        self.assertEqual(c.post("/api/restore", {"name": "nope.tgz"})["_status"], 400)
        self.assertEqual(c.post("/api/restore", {"name": "../../etc/passwd"})["_status"], 400)
        self.assertEqual(c.post("/api/backups", {"kind": "everything"})["_status"], 400)
        self.assertEqual(c.get("/api/backups")["backups"], [])
        self.assertEqual(self.config(), before)
        # signed out: no backup access at all
        out = Client(self.port)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            out.get("/api/backups")
        self.assertEqual(cm.exception.code, 401)
        self.assertEqual(self.raw(out, "/api/backups/upload", b"x")[0], 401)

    def test_a_restore_the_app_cannot_start_with_is_undone(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        self.sign_in(c)
        self.assertEqual(c.post("/api/config/monitoring", {"monitoring": node("live"), "revision": 0})["revision"], 1)
        self.wait_all_modules(c)        # the installer is still writing temp folders into the volume until every module is in
        # a backup whose App cannot start: copy the volume, break the App in the copy, back that up
        scratch = os.path.join(self.tmp, "scratch")
        shutil.copytree(self.cfg, scratch, symlinks=True, ignore=shutil.ignore_patterns("backups", "logs"))
        for ln in ("current", "previous"):
            lp = os.path.join(scratch, ln)
            if os.path.islink(lp):
                tgt = os.path.relpath(os.path.realpath(lp), os.path.realpath(self.cfg))
                os.unlink(lp)
                os.symlink(os.path.join(scratch, tgt), lp)
        with open(os.path.join(scratch, "releases", "app", "0.1.0", "monitorbox_app", "__main__.py"), "w") as f:
            f.write("import sys; sys.exit(1)\n")
        bad = backup.create(scratch, "full", "manual")
        with open(os.path.join(scratch, "backups", bad), "rb") as f:
            code, out = self.raw(c, "/api/backups/upload", f.read())
        self.assertEqual(code, 200, out)
        name = json.loads(out)["name"]
        # change the live config so we can see it come back
        self.assertEqual(c.post("/api/config/monitoring", {"monitoring": node("live-changed"), "revision": 1})["revision"], 2)
        c.post("/api/restore", {"name": name})
        self.assertTrue(self.restore_result(name)["result"].startswith("failed"))
        c2 = Client(self.port)
        wait(lambda: c2.get("/api/health")["version"] == "0.1.0", timeout=60, what="App healthy again after the undone restore")
        self.assertTrue(c2.post("/api/login", {"password": PASSWORD})["ok"])
        last = c2.get("/api/backups")["last"]
        self.assertEqual(last["restore"], name)
        self.assertTrue(last["result"].startswith("failed"), last)
        self.assertEqual(c2.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "live-changed")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "restore")))

    def test_an_interrupted_restore_is_undone_at_start(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        self.sign_in(c)
        c.post("/api/backups", {"kind": "config"})
        name = c.get("/api/backups")["backups"][0]["name"]
        self.assertEqual(c.post("/api/config/monitoring", {"monitoring": node("before crash"), "revision": 0})["revision"], 1)
        self.stop_launcher()
        # simulate the power going out right after the files were swapped
        man = backup.stage(self.cfg, os.path.join(self.cfg, "backups", name))
        backup.swap(self.cfg, man)
        self.assertEqual(self.config().get("monitoring"), None)
        self.start_launcher()
        c = Client(self.port)
        self.sign_in(c)
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "before crash")


if __name__ == "__main__":
    unittest.main()
