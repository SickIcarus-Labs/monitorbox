"""Restart the App, factory reset: through the real launcher and App."""
import json, os, sys, unittest, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None
Client, wait, PASSWORD = T.Client, T.wait, T.PASSWORD


class RestartReset(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_there_is_no_way_to_restart_one_module_any_more(self):
        c = self.start()                      # removed on purpose (0.80.6): restarting MonitorBox is quick and one button
        self.assertEqual(c.post("/api/modules/restart", {"id": c.get("/api/state")["modules"][0]["id"]}).get("_status"), 404)

    def test_restart_the_app_keeps_settings_and_factory_reset_wipes_them_but_keeps_backups(self):
        c = self.start()
        self.configure(c, [{"id": "snmp-a", "module": "snmp", "host": "127.0.0.1", "version": "2c", "community": "fake-comm-rr"}],
                       [{"id": "box", "name": "Box one", "group": "Servers", "rule": "any", "checks": [{"id": "up", "type": "ping", "target": "127.0.0.1"}]}])
        c.post("/api/backups", {"kind": "config"})
        names = [b["name"] for b in c.get("/api/backups")["backups"]]
        self.assertTrue(names)
        # restart: same password, same settings
        self.assertTrue(c.post("/api/app/restart")["restarting"])
        c = Client(self.port)
        wait(lambda: c.post("/api/login", {"password": PASSWORD}).get("ok"), what="App back, same password")
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Box one")
        # a wrong or missing confirmation changes nothing
        self.assertEqual(c.post("/api/factory-reset", {"confirm": "reset"})["_status"], 400)
        self.assertEqual(c.post("/api/factory-reset", {})["_status"], 400)
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Box one")
        # reset: the setup screen comes back, settings and installed modules are gone, backups stay
        stale = os.path.join(self.cfg, "releases", "modules", "left-over-module-xyz", "9.9.9"); os.makedirs(stale)
        open(os.path.join(stale, "marker.txt"), "w").write("from before the reset")
        self.assertTrue(c.post("/api/factory-reset", {"confirm": "RESET"})["restarting"])
        c = Client(self.port)
        wait(lambda: c.post("/api/setup", {"password": "another fake pw 9"}).get("ok"), what="the setup screen asks for a new password")
        self.assertTrue(c.post("/api/login", {"password": "another fake pw 9"})["ok"])
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"], [])
        self.assertEqual(c.get("/api/config/connections")["connections"], [])
        self.assertIn(names[0], [b["name"] for b in c.get("/api/backups")["backups"]])
        wait(lambda: c.get("/api/state")["modules"], what="modules downloaded again")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "releases", "modules", "left-over-module-xyz")), "the reset removed what was installed; only the channel's modules came back")

    def test_a_restore_keeps_the_password_the_box_has_and_a_factory_reset_file_is_the_way_out_of_a_forgotten_one(self):
        c = self.start()
        self.configure(c, [{"id": "snmp-a", "module": "snmp", "host": "127.0.0.1", "version": "2c", "community": "fake-comm-fb"}],
                       [{"id": "box", "name": "Box two", "group": "Servers", "rule": "any", "checks": [{"id": "up", "type": "ping", "target": "127.0.0.1"}]}])
        c.post("/api/backups", {"kind": "config"})
        name = c.get("/api/backups")["backups"][0]["name"]
        with c.op.open(c.base + "/api/backups/download?name=" + name, timeout=10) as r:
            blob = r.read()

        def raw_post(client, path, data):
            req = urllib.request.Request(client.base + path, data, {"X-MB": "1"})
            try:
                with client.op.open(req, timeout=15) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")

        self.assertEqual(raw_post(Client(self.port), "/api/backups/upload", blob)[0], 401, "nobody can upload without signing in")
        self.assertTrue(c.post("/api/factory-reset", {"confirm": "RESET"})["restarting"])
        new_pw = "another fake pw 9"
        fresh = Client(self.port)
        wait(lambda: fresh.post("/api/setup", {"password": new_pw}).get("ok"), what="a new box asks for a password")
        self.assertTrue(fresh.post("/api/login", {"password": new_pw})["ok"])
        self.assertEqual(raw_post(fresh, "/api/backups/upload", b"not a backup")[0], 400)      # a bad file changes nothing
        code, out = raw_post(fresh, "/api/backups/upload", blob)
        self.assertEqual(code, 200, out)
        self.assertTrue(fresh.post("/api/restore", {"name": out["name"]})["restarting"])
        back = Client(self.port)
        wait(lambda: back.post("/api/login", {"password": new_pw}).get("ok"), timeout=60, what="the password chosen on this box works after the restore")
        def restored():                    # sign in again each time: the first answer may come from the App that is about to restart
            back.post("/api/login", {"password": new_pw})
            return back.get("/api/config/monitoring")["monitoring"]["nodes"]
        wait(restored, timeout=40, what="the settings came back")
        self.assertEqual(back.get("/api/config/monitoring")["monitoring"]["nodes"][0]["name"], "Box two")
        conn = back.get("/api/config/connections")["connections"][0]
        self.assertEqual((conn["id"], conn["host"], conn["community"]), ("snmp-a", "127.0.0.1", "••••••••"))
        self.assertEqual(Client(self.port).post("/api/login", {"password": PASSWORD}).get("_status"), 401, "the backup's old password does not come back")
        # forgotten password: there is no recovery, only starting over. A file in the config folder (needs access to the box itself) does the factory reset.
        with open(os.path.join(self.cfg, "config", "factory-reset"), "w") as f: f.write("")
        self.assertTrue(back.post("/api/app/restart")["restarting"])
        again = Client(self.port)
        third = "third fake pw 4"
        wait(lambda: again.post("/api/setup", {"password": third}).get("ok"), timeout=60, what="a new password can be chosen")
        self.assertTrue(again.post("/api/login", {"password": third})["ok"])
        self.assertEqual(again.get("/api/config/monitoring")["monitoring"]["nodes"], [], "settings are gone, like a factory reset")
        self.assertIn(out["name"], [x["name"] for x in again.get("/api/backups")["backups"]], "backups are kept")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "config", "factory-reset")), "the file is used once")

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_new_box_asks_for_a_password_first_then_start_fresh_or_restore(self):
        c = self.start()
        self.configure(c, [], [{"id": "box", "name": "Box three", "group": "Servers", "rule": "any", "checks": [{"id": "up", "type": "ping", "target": "127.0.0.1"}]}])
        c.post("/api/backups", {"kind": "config"})
        name = c.get("/api/backups")["backups"][0]["name"]
        with c.op.open(c.base + "/api/backups/download?name=" + name, timeout=10) as r:
            blob = r.read()
        keep = os.path.join(self.tmp, "kept-backup.tgz")
        with open(keep, "wb") as f: f.write(blob)
        url = f"http://127.0.0.1:{self.port}/"
        new_pw = "chosen at first launch 5"
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            c.post("/api/factory-reset", {"confirm": "RESET"})
            wait(lambda: not Client(self.port).get("/api/health")["passwordSet"], what="a new box")
            pg.goto(url); pg.wait_for_selector("text=Choose an admin password")
            self.assertEqual(pg.locator("text=Restore a backup").count(), 0, "the choice comes after the password")
            pg.fill("input[type=password]", new_pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("text=How do you want to begin?")          # signed in, no second password screen
            pg.set_input_files("#w-file", keep)
            wait(lambda: Client(self.port).post("/api/login", {"password": new_pw}).get("ok"), timeout=60, what="same password after the restore")
            pg.goto(url); pg.wait_for_selector("text=Box three")   # the restored settings; still signed in, because sign-ins now survive a restart (and the password is unchanged)
            Client(self.port).post("/api/login", {"password": new_pw})
            pg.context.clear_cookies(); pg.goto(url); pg.wait_for_selector("input[type=password]")            # a browser with no sign-in is asked for the password
            pg.fill("input[type=password]", new_pw); pg.keyboard.press("Enter"); pg.wait_for_selector("text=Box three")
            # a second wiped box: Start fresh goes to the guided setup page
            c2 = Client(self.port); c2.post("/api/login", {"password": new_pw})
            c2.post("/api/factory-reset", {"confirm": "RESET"})
            wait(lambda: not Client(self.port).get("/api/health")["passwordSet"], what="a new box again")
            pg.goto(url); pg.wait_for_selector("text=Choose an admin password")
            pg.fill("input[type=password]", new_pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("text=How do you want to begin?"); pg.wait_for_selector("input[name=wch]:checked")
            self.assertEqual(pg.locator("input[name=wch]").count(), 3)                       # stable, beta, dev; the box's current one is ticked
            pg.check("input[name=wch] >> nth=0"); pg.wait_for_selector("#chmsg:has-text('stable')")     # the first is stable
            wait(lambda: Client(self.port).get("/api/health")["channel"] == "stable", what="the chosen channel saved")
            pg.click("text=Start fresh")
            pg.wait_for_selector("text=Save and finish", timeout=20000)
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
