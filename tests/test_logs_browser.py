"""The Logs page: tapping a line opens it visibly, a filter you just picked does not hold back new lines,
new lines wait behind the button only while you are reading. Skipped where Playwright/Chromium is not installed."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


class Logs(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_tap_opens_a_line_a_picked_filter_does_not_hold_lines_back_and_reading_does(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 820, "height": 1000})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#hdr .bar")
            pg.goto(f"http://127.0.0.1:{self.port}/#/logs"); pg.wait_for_selector(".lg-l")
            pg.locator(".lg-l").first.click()
            self.assertEqual(pg.locator(".lg-l.open .lg-d").count(), 1, "an opened line shows its details")
            self.assertIn("entry", pg.inner_text(".lg-l.open .lg-d"))
            pg.locator(".lg-l.open").click()
            self.assertEqual(pg.locator(".lg-l.open").count(), 0, "a second tap closes it")
            pg.select_option("#lg-lvl", "debug")
            self.assertNotEqual(pg.evaluate("document.activeElement.tagName"), "SELECT", "a picked filter must not stay focused: that held new lines back")
            self.assertFalse(pg.evaluate("lgBusy()"))
            # a line left open means the page holds new lines behind the button, and the button brings them
            pg.locator(".lg-l").first.click(); self.assertTrue(pg.evaluate("lgBusy()"))
            pg.evaluate("lgHeld=[{id:Date.now()+1,time:'2026-10-30T03:00:00',level:'info',source:'app',text:'held line'}];lgPill()")
            self.assertFalse(pg.evaluate("document.getElementById('lg-new').hidden"))
            pg.click("#lg-new"); self.assertIn("held line", pg.inner_text("#lg-list"))
            self.assertEqual(errs, []); b.close()
