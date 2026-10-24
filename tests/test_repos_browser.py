"""The Updates page with more than one repository (#265), in a real browser (skipped without Playwright): the Repositories box,
modules grouped under their repo, one repo failing on its own line, the switch-off checkbox, and the add box's confirm and its errors."""
import json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_e2e as E, test_repos as R
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


class ReposUI(E.E2E):
    pass


for _n in dir(E.E2E):
    if _n.startswith("test_"):
        setattr(ReposUI, _n, None)          # only the harness is borrowed, not the other file's tests


class ReposUI(ReposUI):
    def setUp(self):
        super().setUp()
        self.other = os.path.join(self.tmp, "other")
        R.release_repo(self.other, {"hello-world": [("1.0.0", R.SHA["c"])]})

    def add_other(self, url=None):
        """The add box takes only owner/name on GitHub, so the test writes the entry the box would have stored, pointing at a folder."""
        p = os.path.join(self.cfg, "config", "monitorbox.json")
        cfg = self.read_json(p) if os.path.exists(p) else {"schema": 4}
        cfg.setdefault("update", {})["repos"] = [{"id": "owner/other-repo", "name": "owner/other-repo", "url": url or f"file://{self.other}", "enabled": True}]
        self.write_json(p, cfg)

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_page_groups_modules_by_repo_and_handles_a_repo_that_is_down_or_switched_off(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        self.wait_all_modules(c)
        self.add_other()
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "correct horse"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            pg.click("button:has-text('Check now')")
            pg.wait_for_selector("h4:has-text('owner/other-repo')")
            heads = pg.locator("h4").all_inner_texts()
            self.assertIn("default", heads[0])                                          # the default first
            self.assertIn("owner/other-repo", heads[1])
            self.assertTrue(pg.locator("[data-sw=hello-world]").count() == 1)
            self.assertIn("not installed", pg.inner_text("[data-sw=hello-world]"))      # offered, not installed on its own
            self.assertIn("Install 1.0.0", pg.inner_text("[data-sw=hello-world]"))
            # a repo that is down says so on its own line and the page still works
            shutil.rmtree(self.other)
            pg.click("button:has-text('Check now')")
            pg.wait_for_selector("text=Can't reach this repository right now")
            self.assertIn("Can't reach it right now", pg.inner_text("h3:has-text('Repositories') + .box"))
            self.assertEqual(pg.locator("[data-sw=app]").count(), 1)
            # switching it off from the checkbox is kept on the box
            box = pg.locator("h3:has-text('Repositories') + .box")
            box.locator("label:has-text('owner/other-repo') input").click()
            E.wait(lambda: [r["enabled"] for r in c.get("/api/versions")["repos"]] == [True, False], what="repo switched off")
            pg.wait_for_selector("h4:has-text('switched off')")
            # the add box: a confirm first (cancel adds nothing), and a bad name is refused in plain words
            pg.fill("#repoin", "Some-One/Their_Repo"); pg.click("button:has-text('Add repository')")
            self.assertIn("run on this box", pg.inner_text("#ask"))
            pg.click("#ask-no")
            self.assertEqual(len(c.get("/api/versions")["repos"]), 2)
            pg.fill("#repoin", "not a repo"); pg.click("button:has-text('Add repository')"); pg.click("#ask-ok")
            pg.wait_for_selector("#repomsg:has-text('owner/name')")
            self.assertEqual(len(c.get("/api/versions")["repos"]), 2)
            # the default has no Remove button
            self.assertEqual(box.locator("label:has-text('built in')").locator("xpath=..").locator("button:has-text('Remove')").count(), 0)
            # and no tick box at all: it cannot be switched off, so nothing is offered that looks as if it could be
            self.assertEqual(box.locator("label:has-text('built in') input[type=checkbox]").count(), 0)
            self.assertGreater(box.locator("input[type=checkbox]").count(), 0, "the others still have theirs")
            self.assertEqual(errs, [])
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_uninstall_asks_about_a_backup_and_the_module_goes(self):
        self.publish(app="0.1.0", hello="0.1.0")
        self.start_launcher()
        c = self.signed_in()
        self.wait_all_modules(c)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "correct horse"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".card"); pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=hello]")
            pg.click("[data-sw=hello] button:has-text('Uninstall')")
            self.assertIn("Back up first?", pg.inner_text("#ask"))
            for want in ("Uninstall, no backup", "Back up settings first, then uninstall", "Full backup first, then uninstall", "Cancel"):
                self.assertTrue(pg.locator(f"#ask button:has-text('{want}')").count() >= 1, want)
            pg.click("#ask-no")                                                     # cancel: nothing happens
            self.assertIn("hello", [m["id"] for m in c.get("/api/state")["modules"]])
            pg.click("[data-sw=hello] button:has-text('Uninstall')")
            pg.click("#ask button:has-text('Uninstall, no backup')")
            E.wait(lambda: "hello" not in [m["id"] for m in c.get("/api/state")["modules"]], what="hello uninstalled")
            pg.wait_for_selector("[data-sw=hello]:has-text('not installed')")
            self.assertFalse(os.path.exists(os.path.join(self.cfg, "releases", "modules", "hello")))
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
