"""Settings must not hang when one of its reads gets no answer (seen after a restart: first entry stalled for 30 seconds). The read is given up and asked again.
Runs in a browser; skipped where Playwright/Chromium is not installed."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


class SettingsHang(unittest.TestCase):
    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_read_that_never_answers_is_asked_again(self):
        box = Box(self, "fake-hang-pw-58")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            pg.add_init_script("window.APIQ_MS = 1500")
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "fake-hang-pw-58"); pg.keyboard.press("Enter")
            pg.wait_for_selector("button.hb")
            seen, hung = [], []

            def hang_first(route):
                seen.append(1)
                if len(seen) == 1:
                    hung.append(route)
                    return                                    # never answered: the page has to give up and ask again
                route.continue_()
            pg.route("**/api/versions", hang_first)
            got = pg.evaluate("settingsData(true).then(d => ({hasVersions: !!d.v, bad: !d.s}))")
            self.assertTrue(got["hasVersions"] and not got["bad"], got)
            self.assertGreaterEqual(len(seen), 2, "the stuck read was asked again")
            for r in hung:
                r.abort()
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_read_that_never_answers_twice_says_so_and_is_logged_instead_of_loading_forever(self):
        # 2026-10-31: Settings sat on "Loading settings…" while the box saw no stuck request at all
        box = Box(self, "fake-hang-pw-59")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            pg.add_init_script("window.APIQ_MS = 800")
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "fake-hang-pw-59"); pg.keyboard.press("Enter")
            pg.wait_for_selector("button.hb")
            hung, reports = [], []
            pg.route("**/api/versions", lambda r: hung.append(r))       # never answered, both times
            pg.on("request", lambda r: reports.append(r.post_data) if r.url.endswith("/api/browser-report") else None)
            pg.evaluate("location.hash='#/settings'")
            pg.wait_for_selector("text=Settings did not load", timeout=10000)
            self.assertIn("versions: no answer in", pg.inner_text("#m"))
            self.assertTrue(pg.locator("button:has-text('Try again')").count())
            pg.wait_for_timeout(300)
            self.assertTrue(reports and "versions: no answer in" in reports[0], reports)
            pg.unroute("**/api/versions")                                 # the browser already gave up on the stuck ones
            pg.click("button:has-text('Try again')")
            pg.wait_for_selector("text=Settings did not load", state="detached", timeout=10000)
            b.close()


if __name__ == "__main__":
    unittest.main()
