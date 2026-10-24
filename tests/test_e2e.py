"""End to end, no network: blank /config -> install from a channel -> hello runs ->
publish a new version -> apply -> roll back -> a broken release rolls itself back.
The 'releases repo' is a temp directory served through file:// URLs."""
import http.cookiejar, json, os, shutil, socket, subprocess, sys, tempfile, time, unittest
import urllib.error, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, "tools", "build_release.py")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Client:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, path):
        with self.op.open(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, body=None):
        req = urllib.request.Request(self.base + path, json.dumps(body or {}).encode(),
                                     {"Content-Type": "application/json", "X-MB": "1"})
        try:
            with self.op.open(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"_status": e.code, **json.loads(e.read() or b"{}")}


def wait(fn, timeout=40, what="condition"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception as e:
            last = e
        time.sleep(0.3)
    raise AssertionError(f"timed out waiting for {what} ({last})")


class E2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-e2e-")
        self.rel = os.path.join(self.tmp, "releases")
        os.makedirs(os.path.join(self.rel, "channels"))
        for ch in ("dev", "beta", "stable"):
            self.write_json(os.path.join(self.rel, "channels", f"{ch}.json"),
                            {"schema": 1, "channel": ch, "updated": "2026-01-01T00:00:00Z", "app": None, "modules": {}})
        self.write_json(os.path.join(self.rel, "catalog.json"), {"schema": 1, "app": [], "modules": {}})
        self.src = os.path.join(self.tmp, "src")
        shutil.copytree(REPO, self.src, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        self.cfg = os.path.join(self.tmp, "config")
        self.port = free_port()
        self.proc = None

    def tearDown(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def write_json(path, obj):
        with open(path, "w") as f:
            json.dump(obj, f)

    @staticmethod
    def read_json(path):
        with open(path) as f:
            return json.load(f)

    def publish(self, app=None, hello=None, break_app=False, fix_app=False):
        """Change versions in the private copy of the source, then build into the releases dir."""
        if app:
            with open(os.path.join(self.src, "app/monitorbox_app/VERSION"), "w") as f:
                f.write(app)
        if hello:
            p = os.path.join(self.src, "modules/hello/manifest.json")
            m = self.read_json(p)
            m["version"] = hello
            self.write_json(p, m)
        main = os.path.join(self.src, "app/monitorbox_app/__main__.py")
        if break_app:
            with open(main, "w") as f:
                f.write("import sys; sys.exit(1)\n")
        if fix_app:
            shutil.copy(os.path.join(REPO, "app/monitorbox_app/__main__.py"), main)
        out = subprocess.run([sys.executable, BUILD, "--root", self.src, "--out", os.path.join(self.rel, "dist"),
                              "--skip-node-packages", "--url-template", f"file://{self.rel}/dist/{{file}}",
                              "--pointer", os.path.join(self.rel, "channels", "dev.json"),
                              "--catalog", os.path.join(self.rel, "catalog.json")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def promote(self, channel, app_version):
        """What the Promote workflow does: mark the version as reached, point the channel at it."""
        cat = self.read_json(os.path.join(self.rel, "catalog.json"))
        ent = next(e for e in cat["app"] if e["version"] == app_version)
        order = ["dev", "beta", "stable"]
        ent["channels"] = order[: order.index(channel) + 1]
        self.write_json(os.path.join(self.rel, "catalog.json"), cat)
        ptr = {"schema": 1, "channel": channel, "updated": "2026-01-01T00:00:00Z", "modules": {},
               "app": {k: ent[k] for k in ("version", "url", "sha256", "signature")}}
        self.write_json(os.path.join(self.rel, "channels", f"{channel}.json"), ptr)

    def start_launcher(self, **extra):
        env = dict(os.environ, MB_CONFIG=self.cfg, MB_RELEASES_URL=f"file://{self.rel}", MB_CHANNEL="dev",
                   MB_PORT=str(self.port), MB_HEALTH_TIMEOUT="15", MB_CHECK_SECONDS="2",
                   PYTHONPATH=os.path.join(REPO, "launcher"), **extra)
        self.proc = subprocess.Popen([sys.executable, "-m", "monitorbox_launcher"], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def signed_in(self):
        c = Client(self.port)
        wait(lambda: c.get("/api/health")["version"], what="App up")
        if not c.get("/api/health")["passwordSet"]:
            self.assertTrue(c.post("/api/setup", {"password": "correct horse"})["ok"])
        self.assertTrue(c.post("/api/login", {"password": "correct horse"})["ok"])
        return c

    def health_version(self, c):
        return c.get("/api/health")["version"]

    def wait_all_modules(self, c):
        """Every module that ships is installed on first run, one after another. Wait for all of them, or a test
        that copies the volume, or sends a Re-detect straight away, races the installer (this flaked in CI)."""
        ships = {d for d in os.listdir(os.path.join(REPO, "modules")) if os.path.exists(os.path.join(REPO, "modules", d, "manifest.json"))}
        wait(lambda: ships <= {m["id"] for m in c.get("/api/state")["modules"] if m["running"]}, what=f"all modules running ({sorted(ships)})")

    def mod_version(self, c, idle_ok=False):
        mods = c.get("/api/state")["modules"]
        return mods[0]["version"] if mods and (mods[0]["running"] or idle_ok) else None

    def launcher_log(self):
        with open(os.path.join(self.cfg, "logs", "launcher.log")) as f:
            return f.read()

    # ------------------------------------------------------------------
    def test_update_all_installs_the_modules_then_the_app(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        wait(lambda: self.health_version(c) == "0.1.0", what="App 0.1.0")
        self.assertTrue(c.post("/api/setup", {"password": "correct horse"})["ok"])
        self.assertTrue(c.post("/api/login", {"password": "correct horse"})["ok"])
        wait(lambda: self.mod_version(c) == "0.1.0", what="hello module running")
        self.wait_all_modules(c)
        self.assertEqual(c.post("/api/apply-all")["message"], "Nothing needed installing.")          # nothing waiting: says so, changes nothing
        self.publish(app="0.2.0", hello="0.2.0")
        v = c.post("/api/check")
        self.assertTrue(v["app"]["needsApply"] and v["modules"]["hello"]["needsApply"])
        r = c.post("/api/apply-all")
        self.assertTrue(r["restarting"], r)
        self.assertIn("hello 0.2.0", r["message"]); self.assertIn("App 0.2.0", r["message"])
        wait(lambda: self.health_version(c) == "0.2.0", what="App 0.2.0 after update all")
        self.assertTrue(c.post("/api/login", {"password": "correct horse"})["ok"])
        self.assertEqual(self.mod_version(c, idle_ok=True), "0.2.0")                                   # the module went first and stayed (no connection uses it, so it starts only when asked)

    def test_full_cycle(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()  # blank config dir
        c = Client(self.port)
        wait(lambda: self.health_version(c) == "0.1.0", what="App 0.1.0 installed and healthy")
        for d in ("config", "data/app", "releases/app", "backups", "logs"):
            self.assertTrue(os.path.isdir(os.path.join(self.cfg, d)), d)

        self.assertFalse(c.get("/api/health")["passwordSet"])
        self.assertEqual(c.post("/api/setup", {"password": "short"})["_status"], 400)
        self.assertTrue(c.post("/api/setup", {"password": "correct horse"})["ok"])
        self.assertEqual(c.post("/api/setup", {"password": "another one!"})["_status"], 400)  # only once
        with self.assertRaises(urllib.error.HTTPError):
            c.get("/api/state")  # signed out
        self.assertEqual(c.post("/api/login", {"password": "wrong password"})["_status"], 401)
        self.assertTrue(c.post("/api/login", {"password": "correct horse"})["ok"])
        wait(lambda: self.mod_version(c) == "0.1.0", what="hello module running")
        self.assertIn("0.1.0", c.get("/api/state")["modules"][0]["card"]["text"])

        # settings defaults: checking on, installing off
        self.assertEqual(c.post("/api/check")["settings"], {"autoCheck": True, "autoUpdate": False})
        about = c.get("/api/about")
        self.assertGreater(about["appMb"], 1)
        self.assertEqual(about["moduleProcesses"], 8)       # hello, wol, snmp, nut, unifi-network, unifi-protect, scrypted and portainer: every module on the channel is installed on first run

        # a custom-header-less POST (what a cross-site form sends) is refused
        req = urllib.request.Request(c.base + "/api/check", b"{}", {"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            c.op.open(req)
        self.assertEqual(cm.exception.code, 403)

        # a new release appears: offered, not installed (auto-update is off)
        self.publish(app="0.2.0", hello="0.2.0")
        v = c.post("/api/check")
        self.assertEqual([o["version"] for o in v["app"]["options"]], ["0.2.0", "0.1.0"])
        self.assertTrue(v["app"]["needsApply"])
        self.assertEqual(v["app"]["target"], "0.2.0")
        self.assertTrue(v["modules"]["hello"]["needsApply"])
        time.sleep(4)  # longer than the auto-check timer: still not installed
        self.assertEqual(self.health_version(c), "0.1.0")

        self.assertIn("0.2.0", c.post("/api/apply", {"kind": "module", "id": "hello"})["message"])
        self.assertEqual(self.mod_version(c), "0.2.0")
        self.assertTrue(c.post("/api/apply", {"kind": "app"})["restarting"])
        wait(lambda: self.health_version(c) == "0.2.0", what="App 0.2.0 after update")
        self.assertTrue(c.post("/api/login", {"password": "correct horse"})["ok"])  # password survived
        self.assertEqual(c.get("/api/versions")["settings"]["autoUpdate"], False)

        # going back is just picking an older version; the newer one stays on offer
        c.post("/api/check")
        v = c.post("/api/select", {"kind": "app", "pin": "0.1.0"})
        self.assertEqual(v["app"]["target"], "0.1.0")
        self.assertTrue(v["app"]["needsApply"])
        c.post("/api/apply", {"kind": "app"})
        wait(lambda: self.health_version(c) == "0.1.0", what="pinned back to 0.1.0")
        c.post("/api/login", {"password": "correct horse"})
        v = c.post("/api/check")
        self.assertEqual(v["app"]["latest"], "0.2.0")           # regression: still offered after going back
        self.assertFalse(v["app"]["needsApply"])                # pinned, so nothing to do
        v = c.post("/api/select", {"kind": "app", "pin": "latest"})
        self.assertTrue(v["app"]["needsApply"])                 # Latest = 0.2.0 is an update again
        self.assertEqual(v["app"]["target"], "0.2.0")
        # a version that does not exist is not installable
        v = c.post("/api/select", {"kind": "app", "pin": "9.9.9"})
        self.assertTrue(v["app"]["pinMissing"])
        self.assertEqual(c.post("/api/apply", {"kind": "app"})["_status"], 400)
        c.post("/api/select", {"kind": "app", "pin": "latest"})

        # same for a module
        c.post("/api/select", {"kind": "module", "id": "hello", "pin": "0.1.0"})
        c.post("/api/apply", {"kind": "module", "id": "hello"})
        self.assertEqual(self.mod_version(c), "0.1.0")
        c.post("/api/select", {"kind": "module", "id": "hello", "pin": "latest"})

        # install Latest for the App again
        c.post("/api/apply", {"kind": "app"})
        wait(lambda: self.health_version(c) == "0.2.0", what="Latest = 0.2.0")
        c.post("/api/login", {"password": "correct horse"})

        # a broken release falls back by itself and is reported
        self.publish(app="0.3.0", break_app=True)
        c.post("/api/check")
        c.post("/api/apply", {"kind": "app"})
        time.sleep(2)
        wait(lambda: self.health_version(c) == "0.2.0", what="automatic fall back from broken 0.3.0")
        c.post("/api/login", {"password": "correct horse"})
        v = c.post("/api/check")
        self.assertIn("0.3.0", v["app"]["failed"])
        self.assertIn("failed to start", v["last"]["result"])
        self.assertTrue(v["app"]["needsApply"])  # still on offer; a person may try again

        # auto-update on: skips the version that failed, takes the next good one
        c.post("/api/settings", {"autoUpdate": True})
        time.sleep(6)
        self.assertEqual(self.health_version(c), "0.2.0")
        self.assertEqual(self.launcher_log().count("current -> 0.3.0"), 1, "must not retry a failed version")
        self.publish(app="0.3.1", fix_app=True)
        wait(lambda: self.health_version(c) == "0.3.1", timeout=30, what="auto-update to 0.3.1")

    def test_channels_only_offer_what_has_reached_them(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.publish(app="0.2.0", hello="0.1.0")
        self.promote("beta", "0.1.0")
        self.start_launcher()
        c = self.signed_in()
        ids = lambda v: [o["version"] for o in v["app"]["options"]]
        self.assertEqual(ids(c.post("/api/check")), ["0.2.0", "0.1.0"])        # dev sees all
        v = c.post("/api/channel", {"channel": "beta"})
        self.assertEqual(ids(v), ["0.1.0"])                                      # beta sees beta
        self.assertEqual(v["app"]["latest"], "0.1.0")
        v = c.post("/api/channel", {"channel": "stable"})
        self.assertEqual(ids(v), [])                                             # nothing stable yet
        self.assertFalse(v["app"]["needsApply"])
        self.promote("stable", "0.1.0")
        self.assertEqual(ids(c.post("/api/check")), ["0.1.0"])                   # stable sees stable
        c.post("/api/channel", {"channel": "dev"})
        self.assertEqual(ids(c.post("/api/check")), ["0.2.0", "0.1.0"])

    def test_an_image_older_than_the_release_expects_is_reported(self):
        """The real launcher records its image version, the real build puts the expected one in the pointer, the app compares them."""
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        c.post("/api/check")
        with open(os.path.join(REPO, "launcher/monitorbox_launcher/VERSION")) as f:
            real = f.read().strip()
        sp = os.path.join(self.cfg, "data", "launcher", "state.json")
        self.assertEqual(self.read_json(sp)["launcher_version"], real)
        self.assertEqual(c.get("/api/versions")["image"], {"have": real, "wants": real, "outdated": False})
        self.assertEqual(c.get("/api/versions")["imageVersion"], real)
        with open(os.path.join(self.src, "launcher/monitorbox_launcher/VERSION"), "w") as f:
            f.write("99.0.0\n")                      # a later release built for a newer image
        self.publish(app="0.2.0")
        c.post("/api/check")
        self.assertEqual(c.get("/api/versions")["image"], {"have": real, "wants": "99.0.0", "outdated": True})
        st = self.read_json(sp)
        st.pop("launcher_version")                    # an image from before the version was recorded: no notice, no guess
        self.write_json(sp, st)
        self.assertIsNone(c.get("/api/versions")["image"])
        self.assertIsNone(c.get("/api/versions")["imageVersion"])

    def test_old_launcher_is_detected(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        self.publish(app="0.2.0", hello="0.1.0")
        c.post("/api/check")
        sp = os.path.join(self.cfg, "data", "launcher", "state.json")
        st = self.read_json(sp)
        st.pop("protocol")  # what an image from before this change looks like
        self.write_json(sp, st)
        r = c.post("/api/apply", {"kind": "app"})
        self.assertEqual(r["_status"], 400)
        self.assertIn("Re-pull", r["error"])
        self.assertEqual(self.health_version(c), "0.1.0")

    def app_pids(self):
        pids = []
        for d in os.listdir("/proc"):
            try:
                if not d.isdigit():
                    continue
                with open(f"/proc/{d}/cmdline") as f:
                    cmd = f.read()
                if "monitorbox_app" in cmd and os.readlink(f"/proc/{d}/cwd").startswith(self.cfg):
                    pids.append(int(d))
            except OSError:
                pass
        return pids

    def test_apps_before_0_3_0_can_still_update_and_roll_back(self):
        """Regression (found on the Pi): an old App asks the launcher with {"action":"update"}
        and then exits. A new launcher must act on that instead of restarting the same App."""
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = Client(self.port)
        wait(lambda: self.health_version(c) == "0.1.0", what="0.1.0")
        self.publish(app="0.2.0", hello="0.1.0")
        for action, expect in (("update", "0.2.0"), ("rollback", "0.1.0")):
            self.write_json(os.path.join(self.cfg, "data", "launcher", "request.json"), {"action": action})
            for pid in self.app_pids():
                os.kill(pid, 15)  # what an old App does after writing the request: exit
            wait(lambda: self.health_version(c) == expect, what=f"legacy {action} -> {expect}")

    def listener(self, port=0):
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(5)
        return srv

    def events(self, c, until, timeout=25):
        """Read the live stream until a snapshot satisfies `until`; returns that snapshot."""
        resp = c.op.open(c.base + "/api/stream", timeout=timeout)
        end = time.time() + timeout
        try:
            while time.time() < end:
                line = resp.readline().decode()
                if line.startswith("data: "):
                    snap = json.loads(line[6:])
                    if until(snap):
                        return snap
        finally:
            resp.close()
        raise AssertionError("the stream never showed the expected status")

    def test_monitoring_end_to_end_with_live_push(self):
        """Green while a service listens, red within seconds of it going away, green again when it returns;
        pushed over the stream, root cause folded, bad edits refused without changing anything."""
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        srv = self.listener()
        port = srv.getsockname()[1]
        mon = {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [
            {"id": "box", "name": "The box", "group": "Servers", "critical": True,
             "checks": [{"type": "tcp", "target": "127.0.0.1", "port": port, "interval": 2}]},
            {"id": "svc", "name": "A service", "group": "Services", "dependsOn": ["box"],
             "checks": [{"type": "tcp", "target": "127.0.0.1", "port": port, "interval": 2}]}]}
        try:
            cfg = c.get("/api/config/monitoring")
            self.assertEqual(cfg["revision"], 0)
            self.assertEqual(c.post("/api/config/monitoring", {"revision": 0, "monitoring": mon})["revision"], 1)

            # a stale edit and a bad edit are both refused, and nothing changes
            self.assertEqual(c.post("/api/config/monitoring", {"revision": 0, "monitoring": mon})["_status"], 409)
            bad = json.loads(json.dumps(mon))
            bad["nodes"][1]["dependsOn"] = ["ghost"]
            r = c.post("/api/config/monitoring", {"revision": 1, "monitoring": bad})
            self.assertEqual(r["_status"], 400)
            self.assertIn("ghost", " ".join(r["errors"]))
            self.assertEqual(c.get("/api/config/monitoring")["revision"], 1)

            snap = self.events(c, lambda s: s["banner"]["status"] == "green")
            self.assertEqual(snap["banner"]["headline"], "Everything is fine")

            srv.close()                                           # the box "goes down"
            # wait for the critical headline itself: if the service's check lands before the box's, the banner is red for a moment
            # with "Something's down" (an actual down is red), and only then escalates
            snap = self.events(c, lambda s: s["banner"]["headline"] == "Everything is fucked.", timeout=30)
            self.assertEqual(snap["banner"]["status"], "red")
            # the service's own check lands a moment later than the box's; wait for it before judging the fold
            snap = self.events(c, lambda s: s["nodes"]["svc"]["state"] == "failed", timeout=30)
            self.assertEqual([a["id"] for a in snap["attention"]], ["box"])        # one alert, not box + service
            self.assertEqual(snap["nodes"]["svc"]["affectedBy"], ["box"])

            srv = self.listener(port)                             # and comes back
            c.post("/api/check-now", {})
            snap = self.events(c, lambda s: s["banner"]["status"] == "green", timeout=30)
            self.assertEqual(snap["attention"], [])
        finally:
            srv.close()

    def test_demo_scenarios_show_each_screen_without_touching_real_data(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        want = {"green": "Everything is fine", "headsup": "Everything is fine", "yellow": "Something's not right", "down": "Something's down",
                "blue": "Something needs a look", "red": "Everything is fucked."}
        real = c.get("/api/status")
        self.assertIsNone(real["demo"])
        for name, headline in want.items():
            self.assertEqual(c.post("/api/demo", {"scenario": name})["demo"], name)
            snap = c.get("/api/status")
            self.assertEqual((snap["demo"], snap["banner"]["headline"]), (name, headline))
        self.assertEqual(c.post("/api/demo", {"scenario": "purple"})["_status"], 400)
        c.post("/api/demo", {"scenario": None})
        self.assertIsNone(c.get("/api/status")["demo"])
        self.assertEqual(c.get("/api/status")["banner"]["status"], real["banner"]["status"])

    def test_a_broken_monitoring_config_on_disk_does_not_stop_the_app(self):
        self.publish(app="0.1.0", hello="0.1.0")
        os.makedirs(os.path.join(self.cfg, "config"))
        self.write_json(os.path.join(self.cfg, "config", "monitorbox.json"),
                        {"schema": 4, "revision": 3, "monitoring": {"nodes": [{"id": "x"}]}})   # hand-edited nonsense
        self.start_launcher()
        c = self.signed_in()
        snap = c.get("/api/status")
        self.assertIn("name is required", snap["configError"])
        self.assertTrue(c.get("/api/health")["ok"])

    def test_checks_can_be_turned_off(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        c.post("/api/settings", {"autoCheck": False})
        self.assertFalse(c.get("/api/versions")["settings"]["autoCheck"])

    def test_tampered_archive_is_refused(self):
        self.publish(app="0.1.0", hello="0.1.0")
        p = os.path.join(self.rel, "channels", "dev.json")
        ptr = self.read_json(p)
        ptr["app"]["sha256"] = "0" * 64
        self.write_json(p, ptr)
        self.start_launcher()
        time.sleep(3)
        self.assertFalse(os.path.isdir(os.path.join(self.cfg, "releases", "app", "0.1.0")))
        with self.assertRaises(Exception):
            Client(self.port).get("/api/health")  # recovery page answers 503, App never ran

    def test_republishing_a_version_with_new_content_is_refused(self):
        self.publish(app="0.1.0", hello="0.1.0")
        with open(os.path.join(self.src, "modules/hello/main.py"), "a") as f:
            f.write("\n# changed\n")
        out = subprocess.run([sys.executable, BUILD, "--root", self.src, "--out", os.path.join(self.rel, "dist"),
                              "--url-template", "x/{file}", "--pointer", os.path.join(self.rel, "channels", "dev.json"),
                              "--catalog", os.path.join(self.rel, "catalog.json")],
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("bump the version", out.stderr)


if __name__ == "__main__":
    unittest.main()
