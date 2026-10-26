"""A card with many alike items (cameras, switches and access points, VPN tunnels) folds them under one heading per source, and a problem opens the fold by itself.
Runs the page's own drawing code on made-up readings; skipped where Playwright/Chromium is not installed."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

NODES_JS = """
(bad) => {
  const mk = (id, name, mod, check, state) => ({id, name, group: 'Cameras', kind: 'leaf', state, label: state, detail: 'x', checks: [{id: 'c', type: mod, target: check, label: name, state, detail: 'x'}], dependsOn: [], children: []});
  const names = ['Doorbell', 'Driveway', 'Garage', 'Patio'];
  const nodes = {};
  names.forEach(n => { const id = 'p-' + n; nodes[id] = mk(id, 'Camera ' + n, 'unifi-protect', 'camera', n === bad ? 'failed' : 'healthy') });
  names.forEach(n => { const id = 's-' + n; nodes[id] = mk(id, 'Camera ' + n, 'scrypted', 'camera', 'healthy') });
  nodes.prot = mk('prot', 'UniFi Protect', 'unifi-protect', 'nvr', 'healthy');
  snap.nodes = nodes;
  snap.cards = [{name: 'Cameras', state: bad ? 'failed' : 'healthy', label: 'x', big: 'x', line: 'x', nodes: Object.keys(nodes)}];
  openN.clear();
  return detailCard(snap.cards[0], 0);
}
"""


class CardSections(unittest.TestCase):
    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_alike_items_fold_under_one_heading_per_source_and_a_problem_opens_its_fold(self):
        box = Box(self, "fake-sections-pw-31")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "fake-sections-pw-31"); pg.keyboard.press("Enter")
            pg.wait_for_function("typeof detailCard === 'function' && typeof snap !== 'undefined' && snap")
            calm = pg.evaluate(NODES_JS, None)
            self.assertIn("UniFi Protect cameras", calm); self.assertIn("Scrypted cameras", calm)
            self.assertIn('aria-expanded=false', calm)
            self.assertNotIn("Camera Driveway", calm, "all good: the cameras are folded away")
            self.assertIn("UniFi Protect</", calm.replace("UniFi Protect cameras", ""), "the recorder stays on the card, outside the folds")
            trouble = pg.evaluate(NODES_JS, "Patio")
            self.assertIn("Camera Patio", trouble, "a camera that is down opens its own fold")
            self.assertIn("3 of 4 good", trouble)
            # a long name with a middling detail ("Camera Garage" + "G6 Instant · recording · connected") gets two lines like its neighbours, not a cut-off one
            row = lambda name, dt: pg.evaluate("([n, d]) => line('go()', 'healthy', n, d, 1)", [name, dt])
            self.assertIn("rw two", row("Camera Garage", "G6 Instant · recording · connected"))
            self.assertIn("rw two", row("Scrypted", "Scrypted 0.147.0 · 9 cameras"))
            self.assertNotIn("rw two", row("Gateway", "reply from 192.168.77.1"), "short ones stay on one line")
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
