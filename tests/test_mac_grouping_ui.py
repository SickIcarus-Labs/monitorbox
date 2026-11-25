"""Front page: an environment's Docker MAC address watch sits in that environment's fold, under its Portainer environment line, not as a loose line
of its own in the Services card. Not counted as a service; a problem with it still opens the fold. Runs the page's own code (Node for the grouping,
Playwright for the drawing; each skipped where it is not installed)."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
from monitorbox_app import ui  # noqa: E402
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


def mac(nid, env, dep, state="healthy", detail="7 bridge networks, 16 MAC addresses, no two the same on one network"):
    return {"id": nid, "name": f"Docker MAC addresses ({env})", "kind": None, "state": state, "detail": detail, "dependsOn": [dep],
            "checks": [{"id": "c", "type": "portainer", "target": "mac", "state": state, "detail": detail, "label": ""}], "service": None}


def envnode(nid, name, state="healthy"):
    return {"id": nid, "name": name, "state": state, "detail": "Agent reachable from Portainer", "dependsOn": [], "service": None,
            "checks": [{"id": "c", "type": "portainer", "target": "environment", "state": state, "detail": "", "label": ""}]}


def svc(nid, title, env, dep, state="healthy"):
    return {"id": nid, "name": f"{title} ({env})", "state": state, "detail": "running", "dependsOn": [dep],
            "service": {"title": title, "env": env, "container": title.lower()},
            "checks": [{"id": "c", "type": "portainer", "target": "container", "state": state, "detail": "", "label": ""}]}


NODES = [envnode("goliath-env", "Broad Leaf - Goliath Portainer"), svc("sonarr", "Sonarr", "Broad Leaf - Goliath", "goliath-env"),
         svc("radarr", "Radarr", "Broad Leaf - Goliath", "goliath-env"), mac("mac-goliath", "Broad Leaf - Goliath", "goliath-env"),
         envnode("apollo-env", "Turnberry - Apollo Portainer"), mac("mac-apollo", "Turnberry - Apollo", "apollo-env"),
         {"id": "loner", "name": "Something else", "state": "healthy", "dependsOn": [], "service": None, "checks": [{"type": "http", "target": "x"}]}]


def grab():
    """The page's own isMacWatch and envGroups, as written (they run on plain data)."""
    a = ui.PAGE.index("\nconst isMacWatch=")
    return ui.PAGE[a:ui.PAGE.index("\nconst MAC_TITLE=", a)]


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class Grouping(unittest.TestCase):
    def test_mac_watches_join_their_environment(self):
        js = grab() + f"\nconst r=envGroups({json.dumps(NODES)});" \
             "console.log(JSON.stringify({groups:r.groups.map(g=>({env:g.env,node:g.node&&g.node.id,svcs:g.svcs.map(s=>s.id),macs:g.macs.map(m=>m.id)})),taken:[...r.taken].sort()}))"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        out = subprocess.run(["node", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        self.assertEqual(out.returncode, 0, out.stderr[:800])
        r = json.loads(out.stdout)
        self.assertEqual(r["groups"], [
            {"env": "Broad Leaf - Goliath", "node": "goliath-env", "svcs": ["sonarr", "radarr"], "macs": ["mac-goliath"]},
            {"env": "Turnberry - Apollo", "node": "apollo-env", "svcs": [], "macs": ["mac-apollo"]}])
        self.assertEqual(r["taken"], sorted(["goliath-env", "sonarr", "radarr", "mac-goliath", "apollo-env", "mac-apollo"]))   # "loner" stays loose


class Drawing(unittest.TestCase):
    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_fold_shows_mac_line_and_a_clash_opens_it(self):
        from test_sites import Box
        box = Box(self, "fake-macgroup-pw-31")
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{box.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", "fake-macgroup-pw-31"); pg.keyboard.press("Enter")
            pg.wait_for_function("typeof envFold === 'function'")
            draw = "(ns) => envGroups(ns).groups.map((g, i) => envFold(g, 0)).join('')"
            ok = pg.evaluate(draw, NODES)
            self.assertIn("2 services · all good", ok, "the MAC watch is not counted as a service")
            self.assertIn("2 checks · all good", ok, "an environment with only its MAC watch still folds")
            bad = [dict(n) for n in NODES]
            bad[3] = mac("mac-goliath", "Broad Leaf - Goliath", "goliath-env", "failed", "MAC 02:42:ac:1d:00:09 on network media is used by a and b.")
            out = pg.evaluate(draw, bad)
            self.assertIn("Docker MAC addresses", out, "a clash opens the fold")
            self.assertIn("02:42:ac:1d:00:09", out)
            self.assertIn("2 of 3 good · 1 need a look", out)
            self.assertEqual(errs, [])
            b.close()


if __name__ == "__main__":
    unittest.main()
