"""The network map's port watch: the tick is off by default, and a port shows rising errors, "known issue" or "learning" only when the watch is on.
Runs the page's own drawing code on made-up readings; skipped where Playwright/Chromium is not installed."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

MAP_JS = """
([on, watch]) => {
  if (!document.querySelector('#mapout')) document.body.insertAdjacentHTML('beforeend', '<div id=mapout></div>');
  const port = {port: '5', name: 'Goliath', server: true, speedMbps: 10000, down: 1000, up_bps: 2000, errors: 4, drops: 9, keys: [], watchKeys: ['sw1|Port 5']};
  if (watch) port.watch = watch;
  drawMap({nodes: [{id: 'sw1', name: 'Core switch', kind: 'switch', model: 'USW', state: 'healthy', stateWord: 'connected', parent: null, link: null, ports: [port]}],
           counts: {devices: 1, wired: 29, wifi: 100, ports: 47}, notes: [], portwatch: {on}});
  return document.querySelector('#mapout').innerHTML;
}
"""


class PortWatchUi(unittest.TestCase):
    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_tick_and_port_notes(self):
        box = Box(self, "fake-portwatch-pw-47")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "fake-portwatch-pw-47"); pg.keyboard.press("Enter")
            pg.wait_for_function("typeof drawMap === 'function'")
            off = pg.evaluate(MAP_JS, [False, None])
            self.assertIn("Watch for rising port errors", off)
            self.assertIn("1 UniFi devices · 47 switch ports in use · 29 Ethernet clients · 100 Wi-Fi clients. Reminder: an uplink between switches counts as 2 ports and 0 clients.", off, "the map footer says what each number counts")
            self.assertNotIn('checked=""', off.split("Watch for rising port errors")[0].rsplit("<input", 1)[1], "off until ticked")
            self.assertNotIn("data-k=", off, "no per-port marks while the watch is off"); self.assertNotIn("rising (about", off); self.assertNotIn("learning what is normal</span>", off)
            rising = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "perHour": {"errors": 1600, "drops": 0, "flaps": 0}, "was": {"errors": 0}, "known": False}])
            self.assertIn("errors rising (about 1,600 an hour)", rising); self.assertIn("</label>", rising.split("rising (about")[1]); self.assertIn("alert", rising.split("rising (about")[1])
            self.assertRegex(rising.split("rising (about")[1], r'<input type="checkbox" checked="" data-k=', "a port alerts by default: its tick is on")
            both = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "perHour": {"errors": 29068}, "split": {"errors": {"rx": 29000, "tx": 68}}, "traffic": {"avgBps": 4100000000, "peakBps": 9200000000}, "was": {}, "known": False}])
            self.assertIn("errors rising (about 29,068 an hour: 29,000 receive, 68 transmit), carrying about", both)
            far = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "perHour": {"errors": 29068}, "split": {"errors": {"rx": 29000, "tx": 68}}, "other": {"label": "Aggregation, Port 3", "state": "figures", "split": {"errors": {"rx": 0, "tx": 0}}}, "was": {}, "known": False}])
            self.assertIn("other end (Aggregation, Port 3): 0 receive, 0 transmit an hour", far)
            none = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "perHour": {"errors": 5}, "split": {"errors": {"rx": 5, "tx": 0}}, "other": {"label": "Aggregation, Port 3", "state": "none", "split": {}}, "was": {}, "known": False}])
            self.assertIn("other end (Aggregation, Port 3): no counters", none)
            known = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "perHour": {"errors": 1600, "drops": 0, "flaps": 0}, "was": {"errors": 0}, "known": True}])
            self.assertNotIn("errors rising (about", known); self.assertIn("not alerting</span>", known); self.assertRegex(known, r'<input type="checkbox" data-k="[^"]*" onchange="pwKnown', "an unticked port does not alert: its tick is off")
            self.assertIn('checked=""', rising.split("Watch for rising port errors")[0].rsplit("<input", 1)[1], "ticked when the box says it is on")
            learning = pg.evaluate(MAP_JS, [True, {"learning": True, "rising": [], "perHour": {"errors": 0, "drops": 0, "flaps": 0}, "was": {}, "known": False}])
            self.assertIn("learning what is normal", learning)
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
