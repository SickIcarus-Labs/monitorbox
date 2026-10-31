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
            self.assertIn("1 devices · 47 switch ports in use · 29 Ethernet clients · 100 Wi-Fi clients. Reminder: an uplink between switches counts as 2 ports and 0 clients.", off, "the map footer says what each number counts")
            self.assertNotIn('checked=""', off.split("Watch for rising port errors")[0].rsplit("<input", 1)[1], "off until ticked")
            self.assertNotIn("data-k=", off, "no per-port marks while the watch is off"); self.assertNotIn("rising (about", off); self.assertNotIn("learning what is normal</span>", off)
            rising = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "count": {"errors": 400, "drops": 0, "flaps": 0}, "was": {"errors": 0}, "known": False}])
            self.assertIn("errors rising (400 in the last 15 min)", rising); self.assertIn("</label>", rising.split("rising (")[1]); self.assertIn("alert", rising.split("rising (")[1])
            self.assertRegex(rising.split("rising (")[1], r'<input type="checkbox" checked="" data-k=', "a port alerts by default: its tick is on")
            both = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "count": {"errors": 7267}, "split": {"errors": {"rx": 7250, "tx": 17}}, "traffic": {"avgBps": 4100000000, "peakBps": 9200000000}, "was": {}, "known": False}])
            self.assertIn("errors rising (7,267 in the last 15 min: 7,250 receive, 17 transmit), carrying about", both)
            far = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "count": {"errors": 7267}, "split": {"errors": {"rx": 7250, "tx": 17}}, "other": {"label": "Aggregation, Port 3", "state": "figures", "split": {"errors": {"rx": 0, "tx": 0}}}, "was": {}, "known": False}])
            self.assertIn("other end (Aggregation, Port 3): 0 receive, 0 transmit in the last 15 min", far)
            none = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "count": {"errors": 5}, "split": {"errors": {"rx": 5, "tx": 0}}, "other": {"label": "Aggregation, Port 3", "state": "none", "split": {}}, "was": {}, "known": False}])
            self.assertIn("other end (Aggregation, Port 3): no counters", none)
            known = pg.evaluate(MAP_JS, [True, {"learning": False, "rising": ["errors"], "count": {"errors": 400, "drops": 0, "flaps": 0}, "was": {"errors": 0}, "known": True}])
            self.assertNotIn("errors rising (about", known); self.assertIn("not alerting</span>", known); self.assertRegex(known, r'<input type="checkbox" data-k="[^"]*" onchange="pwKnown', "an unticked port does not alert: its tick is off")
            self.assertIn('checked=""', rising.split("Watch for rising port errors")[0].rsplit("<input", 1)[1], "ticked when the box says it is on")
            learning = pg.evaluate(MAP_JS, [True, {"learning": True, "rising": [], "count": {"errors": 0, "drops": 0, "flaps": 0}, "was": {}, "known": False}])
            self.assertIn("learning what is normal", learning)
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()


class ReadingsAge(unittest.TestCase):
    """"1046 min of readings" reads as hours and days: the page's own formatter, run with node (skipped where node is not installed)."""
    @unittest.skipIf(__import__("shutil").which("node") is None, "node not installed")
    def test_minutes_hours_and_days(self):
        import re, subprocess
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "monitorbox_app", "ui.py"), encoding="utf-8").read()
        fn = re.search(r"function pwSpan\(m\)\{.*?\}\n", src, re.S).group(0)
        out = subprocess.run(["node", "-e", fn + "console.log(JSON.stringify([0,7,59,60,61,1046,1440,1500,4320].map(pwSpan)))"], capture_output=True, text=True, check=True).stdout
        self.assertEqual(__import__("json").loads(out), ["0 min", "7 min", "59 min", "1 h", "1 h 1 min", "17 h 26 min", "1 day", "1 day 1 h", "3 days"])
