"""THE M3 RELEASE GATE: back up -> wipe -> restore -> every credential is still the right one.

MonitorBox 3 once wrote one credential into two servers' entries and nobody noticed. So here every
secret has its OWN value, each one is compared after the round trip, and a fake device only
accepts the credential that belongs to it: a mix-up cannot pass.
"""
import sys, http.server, io, json, os, secrets, shutil, sys, tarfile, tempfile, threading, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]

from monitorbox_launcher import backup  # noqa: E402
from monitorbox_app.auth import Auth  # noqa: E402
from monitorbox_app.store import Paths, write_json  # noqa: E402

# Every device has different fields, like the real integrations will.
SHAPES = {
    "unifi-network": ["username", "password"],
    "unifi-protect": ["username", "password"],
    "snmp": ["community", "authUser", "authKey", "privKey"],
    "nut": ["username", "password"],
    "http": ["token"],
    "scrypted": ["username", "password", "token"],
    "portainer": ["apiKey"],
}


def make_connections():
    """Two or three devices of every kind, every secret different from every other."""
    conns, n = [], 0
    for kind, fields in SHAPES.items():
        for k in range(3):
            n += 1
            c = {"id": f"{kind}-{k}", "type": kind, "host": f"192.0.2.{n}"}
            for f in fields:
                c[f] = f"fake-{kind}-{k}-{f}-{secrets.token_hex(6)}"
            conns.append(c)
    return conns


def leaves(obj, prefix=""):
    if isinstance(obj, dict):
        for k in sorted(obj):
            yield from leaves(obj[k], f"{prefix}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def secret_pairs(conn):
    return {f: v for f, v in conn.items() if f not in ("id", "type", "host")}


class FakeDevices:
    """GET /<device id> with X-Fake-Auth = the device's own secrets, joined; anything else is 401."""
    def __init__(self, conns):
        want = {c["id"]: "|".join(f"{k}={v}" for k, v in sorted(secret_pairs(c).items())) for c in conns}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                ok = want.get(self.path.strip("/")) == self.headers.get("X-Fake-Auth")
                self.send_response(200 if ok else 401)
                self.end_headers()
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def login(self, device_id, conn):
        import urllib.error, urllib.request
        tok = "|".join(f"{k}={v}" for k, v in sorted(secret_pairs(conn).items()))
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/{device_id}", headers={"X-Fake-Auth": tok})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class World:
    """A /config with everything a real box has, built from distinct values."""
    ADMIN = "admin-" + secrets.token_hex(6)

    def __init__(self, root):
        self.root = root
        self.paths = Paths(root)
        self.conns = make_connections()
        self.monitoring = {"builtinInternet": True, "nodes": [
            {"id": "gw", "name": "Gateway", "group": "Network", "critical": True,
             "checks": [{"id": "p", "type": "ping", "host": "192.0.2.250"}]}]}

    def build(self):
        Auth(self.paths).set_password(self.ADMIN)
        write_json(self.paths.config, {"schema": 4, "revision": 3, "monitoring": self.monitoring,
                                       "connections": self.conns,
                                       "update": {"channel": "beta", "auto_check": False, "auto_update": True,
                                                  "app_pin": "0.4.0", "module_pins": {"hello": "0.1.0"}}})
        rdir = os.path.join(root_of(self), "config", "revisions")
        write_json(os.path.join(rdir, "000003.json"), {"revision": 3, "monitoring": self.monitoring})
        for v in ("0.4.0", "0.5.0"):
            os.makedirs(os.path.join(self.root, "releases", "app", v, "monitorbox_app"))
            with open(os.path.join(self.root, "releases", "app", v, "monitorbox_app", "VERSION"), "w") as f:
                f.write(v)
        os.makedirs(os.path.join(self.root, "releases", "modules", "hello", "0.1.0"))
        with open(os.path.join(self.root, "releases", "modules", "hello", "0.1.0", "main.py"), "w") as f:
            f.write("print('hello module')\n")
        os.symlink(os.path.join(self.root, "releases", "app", "0.5.0"), os.path.join(self.root, "current"))
        os.symlink(os.path.join(self.root, "releases", "app", "0.4.0"), os.path.join(self.root, "previous"))
        write_json(self.paths.modules_state, {"hello": {"active": "0.1.0", "failed": []}})
        os.makedirs(os.path.join(self.root, "data", "launcher"), exist_ok=True)
        write_json(os.path.join(self.root, "data", "launcher", "state.json"), {"protocol": 2})
        return self

    def wipe(self):
        """Everything the owner would lose with the volume: config, data, releases, links, backups."""
        for d in ("config", "data", "releases", "backups", "restore"):
            shutil.rmtree(os.path.join(self.root, d), ignore_errors=True)
        for ln in ("current", "previous"):
            if os.path.lexists(os.path.join(self.root, ln)):
                os.unlink(os.path.join(self.root, ln))

    def tree(self, kind):
        """name -> bytes for everything a backup of this kind is supposed to bring back."""
        out = {}
        for t in backup.TARGETS[kind]:
            base = os.path.join(self.root, t)
            walk = [(os.path.dirname(base), [], [os.path.basename(base)])] if os.path.isfile(base) else os.walk(base)
            for d, _x, names in walk:
                for n in names:
                    p = os.path.join(d, n)
                    with open(p, "rb") as f:
                        out[os.path.relpath(p, self.root)] = f.read()
        return out


def read(path):
    with open(path) as f:
        return json.load(f)


def root_of(w):
    return w.root


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-rt-")
        self.root = os.path.join(self.tmp, "config")
        os.makedirs(self.root)
        self.keep = os.path.join(self.tmp, "downloads")  # where the owner keeps the file: NOT in the volume
        os.makedirs(self.keep)
        self.w = World(self.root).build()
        self.dev = FakeDevices(self.w.conns)

    def tearDown(self):
        self.dev.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def back_up_and_wipe(self, kind):
        name = backup.create(self.root, kind, "manual", app_version="0.5.0")
        before = self.w.tree(kind)
        links = {ln: os.readlink(os.path.join(self.root, ln)) for ln in backup.LINKS}
        dl = os.path.join(self.keep, name)
        shutil.copy(os.path.join(self.root, "backups", name), dl)
        self.w.wipe()
        self.assertFalse(os.path.exists(os.path.join(self.root, "config")))
        return dl, before, links

    def restore(self, archive):
        man = backup.stage(self.root, archive)
        backup.swap(self.root, man)
        backup.commit(self.root)

    # ---- the gate ----------------------------------------------------
    def test_every_credential_survives_and_is_the_right_one(self):
        # the test data itself must have no repeated secret (that is the v3 bug)
        vals = [v for c in self.w.conns for v in secret_pairs(c).values()]
        self.assertEqual(len(vals), len(set(vals)), "test setup reused a credential")
        self.assertGreaterEqual(len(vals), 20)
        for kind in ("config", "full"):
            with self.subTest(kind=kind):
                dl, before, _ = self.back_up_and_wipe(kind)
                self.restore(dl)
                got = read(os.path.join(self.root, "config", "monitorbox.json"))
                # 1. each value, one by one, against what we put in
                want = dict(leaves({"connections": self.w.conns}))
                have = dict(leaves({"connections": got["connections"]}))
                self.assertEqual(set(want), set(have))
                for path, v in want.items():
                    self.assertEqual(have[path], v, f"{path} changed in the round trip")
                # 2. every device accepts its own restored credential and refuses the neighbours'
                for c, r in zip(self.w.conns, got["connections"]):
                    self.assertEqual(self.dev.login(c["id"], r), 200, f"{c['id']} rejected its restored credential")
                for i, c in enumerate(self.w.conns):
                    other = got["connections"][(i + 1) % len(self.w.conns)]
                    self.assertEqual(self.dev.login(c["id"], other), 401, "the fake device accepted another device's credential")
                # 3. the admin password still works, and the wrong one still does not
                a = Auth(Paths(self.root))
                self.assertTrue(a.login(World.ADMIN))
                self.assertIsNone(a.login(World.ADMIN + "x"))
                self.assertTrue(backup.password_ok(self.root, World.ADMIN))
                self.assertFalse(backup.password_ok(self.root, "nope-" + secrets.token_hex(4)))
                # 4. every file a backup of this kind covers is byte-identical, nothing extra
                self.assertEqual(self.w.tree(kind), before)
                self.assertFalse(os.path.exists(os.path.join(self.root, "restore")))
                self.w.wipe()
                conns, self.w = self.w.conns, World(self.root)
                self.w.conns = conns  # same devices for the next round: the fake device still knows them
                self.w.build()

    def test_passkeys_and_the_sign_in_settings_survive_and_still_sign_in(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_passkeys as TP
        from monitorbox_app import passkeys as pk, security as sec
        p, site = pk.Passkeys(Paths(self.root)), sec.Security(Paths(self.root))
        devs = []
        for name in ("Distinct phone one", "Distinct tablet two", "Distinct laptop three"):
            d = TP.Device(count=len(devs) * 7 + 3)              # a different counter for each, too
            o = p.register_options(TP.RP)
            p.register_finish(o["handle"], d.create(o["publicKey"]["challenge"]), TP.RP, TP.ORIGIN, name)
            devs.append(d)
        want_security = site.save({"trustedProxies": ["192.0.2.41", "192.0.2.42"], "publicHost": TP.RP, "internetNeedsPasskey": True})
        want_keys = {c["id"]: dict(c) for c in p.data()["credentials"]}
        want_user = p.data()["userId"]
        self.assertEqual(len(want_keys), 3)
        for kind in ("config", "full"):
            with self.subTest(kind=kind):
                dl, before, _ = self.back_up_and_wipe(kind)
                self.restore(dl)
                p2, site2 = pk.Passkeys(Paths(self.root)), sec.Security(Paths(self.root))
                self.assertEqual(site2.cfg(), want_security)
                have = {c["id"]: dict(c) for c in p2.data()["credentials"]}
                self.assertEqual(set(have), set(want_keys))
                for cid, c in want_keys.items():
                    for field, v in c.items():
                        self.assertEqual(have[cid][field], v, f"{field} of a passkey changed in the round trip")
                self.assertEqual(p2.data()["userId"], want_user)
                # each restored passkey still signs in, and a stranger's does not
                for d in devs:
                    o = p2.login_options(TP.RP)
                    self.assertTrue(p2.login_finish(o["handle"], d.get(o["publicKey"]["challenge"]), TP.RP, TP.ORIGIN))
                o = p2.login_options(TP.RP)
                with self.assertRaises(ValueError):
                    p2.login_finish(o["handle"], TP.Device().get(o["publicKey"]["challenge"]), TP.RP, TP.ORIGIN)
                # rebuild for the next round, with what the restored passkeys now hold
                self.w.wipe(); self.w = World(self.root).build()
                p, site = pk.Passkeys(Paths(self.root)), sec.Security(Paths(self.root))
                write_json(os.path.join(self.root, "config", "passkeys.json"), {"userId": want_user, "credentials": list(have.values())})
                site.save(want_security)

    def test_credentials_that_are_genuinely_shared_survive_too(self):
        """Real homelabs reuse logins (two servers with the same SNMP login). Sharing must round-trip exactly:
        shared stays shared, and the distinct ones around them stay distinct."""
        shared = "fake-shared-" + secrets.token_hex(6)
        conns = make_connections() + [
            {"id": "snmp-a3", "type": "snmp", "host": "192.0.2.201", "authUser": "monitor", "authKey": shared, "privKey": shared},
            {"id": "snmp-granite", "type": "snmp", "host": "192.0.2.202", "authUser": "monitor", "authKey": shared, "privKey": shared}]
        self.dev.close()
        self.dev = FakeDevices(conns)
        self.w.conns = conns
        cfg = read(self.w.paths.config)
        cfg["connections"] = conns
        write_json(self.w.paths.config, cfg)
        for kind in ("config", "full"):
            with self.subTest(kind=kind):
                dl, _before, _ = self.back_up_and_wipe(kind)
                self.restore(dl)
                got = read(os.path.join(self.root, "config", "monitorbox.json"))["connections"]
                self.assertEqual(got, conns)
                for c, r in zip(conns, got):
                    self.assertEqual(self.dev.login(c["id"], r), 200)
                a, b = got[-2], got[-1]
                self.assertEqual((a["authKey"], a["privKey"]), (b["authKey"], b["privKey"]))  # still shared
                self.assertEqual(len({c["password"] for c in got if "password" in c}), len([c for c in got if "password" in c]))  # the rest still distinct
                self.w.wipe()
                self.w.build()
                cfg = read(self.w.paths.config)
                cfg["connections"] = conns
                write_json(self.w.paths.config, cfg)

    def test_history_travels_in_a_full_backup_and_not_in_a_settings_backup(self):
        """Changed on purpose (#100, owner's decision): a settings backup holds settings only, so the history is in the full backup alone.
        (It used to say both kinds carried it.) Every event is different, and each one is compared after the round trip."""
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
        from monitorbox_app.history import History
        now = 1_800_000_000
        hpath = os.path.join(self.root, "config", "history.jsonl")
        h = History(hpath, clock=lambda: now)
        states = ["healthy", "failed", "unknown", "degraded"]
        for i in range(12):
            h.clock = (lambda t: (lambda: t))(now - 86400 * 20 + i * 7919)
            h.record({f"node-{i}": states[i % 4], f"other-{i}": states[(i + 1) % 4]})
        later = now - 86400 * 20 + 11 * 7919 + 1     # just after the last record: no gap to explain
        h.clock = lambda: later
        want = {n: h.timeline(n) for n in ("node-3", "other-7", "node-11")}
        with open(hpath) as f:
            want_text = f.read()
        self.assertEqual(len(want_text.splitlines()), 24)
        dl, _b, _l = self.back_up_and_wipe("config")
        self.restore(dl)
        self.assertFalse(os.path.exists(hpath), "a settings backup carries no history")
        self.w.wipe(); self.w.build()
        with open(hpath, "w") as f:
            f.write(want_text)
        dl, _b, _l = self.back_up_and_wipe("full")
        self.restore(dl)
        with open(hpath) as f:
            self.assertEqual(f.read(), want_text)
        back = History(hpath, clock=lambda: later)
        for n, t in want.items():
            self.assertEqual(back.timeline(n), t, n)

    def test_full_backup_brings_back_releases_and_links(self):
        dl, before, links = self.back_up_and_wipe("full")
        self.restore(dl)
        for ln, tgt in links.items():
            self.assertEqual(os.readlink(os.path.join(self.root, ln)), tgt)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "releases", "modules", "hello", "0.1.0", "main.py")))

    def test_full_backup_ignores_a_module_that_is_being_installed(self):
        """A full backup that runs while an update is half-installed once failed (the temp folder's files vanish
        mid-backup). The half-installed folder is left out and the backup is complete without it."""
        tmpdir = os.path.join(self.root, "releases", "modules", ".tmp-half-installed")
        os.makedirs(tmpdir)
        with open(os.path.join(tmpdir, "main.py"), "w") as f: f.write("half")
        name = backup.create(self.root, "full", "manual")
        with tarfile.open(os.path.join(backup.backups_dir(self.root), name)) as tf:
            names = tf.getnames()
        self.assertFalse([n for n in names if ".tmp-" in n], names)
        self.assertIn("releases/modules/hello/0.1.0/main.py", names)

    def test_a_file_rewritten_while_the_backup_runs_still_gives_a_valid_backup(self):
        """The App rewrites data/app/modules.json as modules update. A backup that hashed the live file and read it
        again for the archive once came out with a checksum that did not match (restore refused it as damaged). Since 1.7.8 the copy is hashed as it is
        written (the hook moved from _sha to _copy_sha); the archive still comes from that same copy."""
        target = os.path.join(self.root, "data", "app", "modules.json")
        self.assertTrue(os.path.isfile(target))
        orig = open(target, "rb").read()
        real, n = backup._copy_sha, [0]
        def copy_then_rewrite(src, dst):
            h = real(src, dst)
            if not n[0] and open(dst, "rb").read() == orig:                # modules.json was just copied and hashed: change the live file now
                n[0] = 1
                with open(target, "w") as f: f.write('{"changed": "after it was hashed"}')
            return h
        backup._copy_sha = copy_then_rewrite
        try:
            name = backup.create(self.root, "full", "manual")
        finally:
            backup._copy_sha = real
        self.assertEqual(n[0], 1, "the test did not rewrite anything")
        backup.validate(os.path.join(backup.backups_dir(self.root), name))
        self.assertEqual([x for x in os.listdir(backup.backups_dir(self.root)) if x.startswith(".tmp-")], [], "snapshot left behind")

    def test_config_backup_does_not_touch_releases(self):
        dl, _, _ = self.back_up_and_wipe("config")
        os.makedirs(os.path.join(self.root, "releases", "app", "9.9.9"))
        os.symlink(os.path.join(self.root, "releases", "app", "9.9.9"), os.path.join(self.root, "current"))
        self.restore(dl)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "releases", "app", "9.9.9")))
        self.assertTrue(os.path.islink(os.path.join(self.root, "current")))

    def test_restore_replaces_changed_config_and_removes_new_files(self):
        name = backup.create(self.root, "config")
        write_json(self.w.paths.config, {"schema": 4, "connections": [{"id": "x", "password": "changed-after-backup"}]})
        write_json(os.path.join(self.root, "config", "extra.json"), {"added": "later"})
        self.restore(os.path.join(self.root, "backups", name))
        got = read(self.w.paths.config)
        self.assertEqual(got["connections"], self.w.conns)
        self.assertFalse(os.path.exists(os.path.join(self.root, "config", "extra.json")))

    def test_a_backup_carries_the_site_name_in_its_file_name_and_still_restores(self):
        sites = os.path.join(self.root, "config", "sites.json")
        os.makedirs(os.path.dirname(sites), exist_ok=True)
        write_json(sites, {"name": "Bay Harbor", "listen": False, "managers": [], "sites": []})
        name = backup.create(self.root, "config")
        self.assertRegex(name, r"^monitorbox-bay-harbor-config-\d{8}-\d{6}-manual\.tgz$")
        self.assertEqual(backup.validate(os.path.join(self.root, "backups", name))["site"], "bay-harbor")
        for raw, want in (("Tidewater #2 (NUC)", "tidewater-2-nuc"), ("  ", ""), ("../../etc", "etc"), ("x" * 80, "x" * 30)):
            write_json(sites, {"name": raw})
            n = backup.create(self.root, "config", "manual", now=1_800_000_000 + len(raw))
            self.assertRegex(n, rf"^monitorbox-{want + '-' if want else ''}config-\d{{8}}-\d{{6}}-manual\.tgz$", raw)
            self.assertTrue(backup.NAME_RE.match(n))
        os.unlink(sites)
        self.assertRegex(backup.create(self.root, "config", "manual", now=1_800_000_900), r"^monitorbox-config-", "no site name set: the old shape")
        write_json(sites, {"name": "Bay Harbor"})
        self.restore(os.path.join(self.root, "backups", name))                       # a named backup restores like any other

    def test_the_file_name_time_is_the_boxs_own_time_zone_and_utc_when_none_is_set(self):
        now = 1_800_000_000                                           # 2027-01-15 08:00:00 UTC
        self.assertIn("-20270115-080000-", backup.create(self.root, "config", "manual", now=now))
        disp = os.path.join(self.root, "config", "display.json")
        os.makedirs(os.path.dirname(disp), exist_ok=True)
        write_json(disp, {"timezone": "America/Chicago"})
        n = backup.create(self.root, "config", "manual", now=now)
        self.assertIn("-20270115-020000-", n)
        self.assertEqual(backup.validate(os.path.join(self.root, "backups", n))["created"], "2027-01-15T08:00:00Z", "the manifest stays UTC")
        write_json(disp, {"timezone": "Not/AZone"})
        self.assertIn("-20270115-080000-", backup.create(self.root, "config", "manual", now=now), "a bad zone falls back to UTC")

    def test_restoring_a_backup_from_a_box_with_no_password_removes_the_password(self):
        os.unlink(self.w.paths.auth)
        name = backup.create(self.root, "config")
        Auth(self.w.paths).set_password("set-later-" + secrets.token_hex(4))
        self.restore(os.path.join(self.root, "backups", name))
        self.assertFalse(os.path.exists(self.w.paths.auth))

    # ---- safety ------------------------------------------------------
    def rebuild(self, name, edit):
        """Rewrite an archive with a change, leaving the manifest alone: a tampered or hand-made file."""
        src = os.path.join(self.root, "backups", name)
        dst = os.path.join(self.keep, "bad.tgz")
        with tarfile.open(src) as a, tarfile.open(dst, "w:gz") as b:
            for m in a.getmembers():
                data = a.extractfile(m).read()
                m, data = edit(m, data)
                if m is None:
                    continue
                m.size = len(data)
                b.addfile(m, io.BytesIO(data))
            extra = edit(None, None)
            if extra:
                b.addfile(extra[0], io.BytesIO(extra[1]))
        return dst

    def assert_refused_and_untouched(self, archive, why):
        before = self.w.tree("full")
        with self.assertRaises(backup.BackupError) as cm:
            backup.stage(self.root, archive)
        self.assertTrue(str(cm.exception), why)
        self.assertEqual(self.w.tree("full"), before, "a refused backup changed files")

    def test_tampered_file_is_refused(self):
        name = backup.create(self.root, "config")
        bad = self.rebuild(name, lambda m, d: (m, d.replace(b"fake-", b"evil-")) if m and m.name == "config/monitorbox.json" else (m, d) if m else None)
        self.assert_refused_and_untouched(bad, "checksum")

    def test_path_traversal_and_links_are_refused(self):
        name = backup.create(self.root, "config")
        for label, mk in (("traversal", lambda: tarfile.TarInfo("config/../../escape")),
                          ("absolute", lambda: tarfile.TarInfo("/etc/passwd")),
                          ("outside", lambda: tarfile.TarInfo("data/launcher/state.json")),
                          ("symlink", lambda: _link())):
            with self.subTest(label):
                def edit(m, d, mk=mk):
                    if m is None:
                        ti = mk()
                        return ti, b"x"
                    return m, d
                self.assert_refused_and_untouched(self.rebuild(name, edit), label)

    def test_not_a_backup_and_garbage_are_refused(self):
        junk = os.path.join(self.keep, "junk.tgz")
        with open(junk, "wb") as f:
            f.write(b"this is not a tar file")
        self.assert_refused_and_untouched(junk, "garbage")
        with tarfile.open(junk, "w:gz") as tf:
            ti = tarfile.TarInfo("hello.txt")
            ti.size = 2
            tf.addfile(ti, io.BytesIO(b"hi"))
        self.assert_refused_and_untouched(junk, "no manifest")

    def test_missing_file_is_refused(self):
        name = backup.create(self.root, "config")
        bad = self.rebuild(name, lambda m, d: (None, d) if m and m.name == "config/monitorbox.json" else (m, d) if m else None)
        self.assert_refused_and_untouched(bad, "incomplete")

    def test_undo_puts_everything_back_exactly(self):
        name = backup.create(self.root, "full")
        write_json(self.w.paths.config, {"schema": 4, "connections": [{"id": "keep-me", "password": "current-" + secrets.token_hex(4)}]})
        os.unlink(os.path.join(self.root, "previous"))
        before = self.w.tree("full")
        old_links = {ln: os.path.lexists(os.path.join(self.root, ln)) for ln in backup.LINKS}
        man = backup.stage(self.root, os.path.join(self.root, "backups", name))
        backup.swap(self.root, man)
        self.assertNotEqual(self.w.tree("full"), before)
        self.assertTrue(backup.undo(self.root))
        self.assertTrue(backup.undo(self.root) is False)  # a second run (after a crash) is harmless
        self.assertEqual(self.w.tree("full"), before)
        self.assertEqual({ln: os.path.lexists(os.path.join(self.root, ln)) for ln in backup.LINKS}, old_links)

    def test_undo_when_the_box_had_no_config_at_all(self):
        name = backup.create(self.root, "config")
        archive = os.path.join(self.keep, name)
        shutil.copy(os.path.join(self.root, "backups", name), archive)
        self.w.wipe()
        man = backup.stage(self.root, archive)
        backup.swap(self.root, man)
        self.assertTrue(os.path.exists(self.w.paths.config))
        backup.undo(self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "config")))
        self.assertFalse(os.path.exists(self.w.paths.auth))

    # ---- housekeeping ------------------------------------------------
    def test_listing_and_pruning(self):
        for i in range(20):
            backup.create(self.root, "config", "auto", now=1_700_000_000 + i)
        backup.create(self.root, "config", "manual", now=1_700_000_100)
        names = backup.list_backups(self.root)
        self.assertEqual(len([b for b in names if b["label"] == "auto"]), 14)
        self.assertEqual(len([b for b in names if b["label"] == "manual"]), 1)
        self.assertEqual(names[0]["label"], "manual")  # newest first
        self.assertEqual(oct(os.stat(os.path.join(self.root, "backups", names[0]["name"])).st_mode & 0o777), "0o600")

    def test_names_cannot_escape_the_backup_folder(self):
        for bad in ("../x.tgz", "/etc/passwd", "a/b.tgz", "x.tar", ""):
            with self.assertRaises(backup.BackupError):
                backup.path_of(self.root, bad)


def _link():
    ti = tarfile.TarInfo("config/evil")
    ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/passwd"
    return ti


if __name__ == "__main__":
    unittest.main()
