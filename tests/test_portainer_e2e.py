"""Portainer end to end: real launcher, App and portainer module against a fake Portainer server. Test connection works,
containers and their web checks are picked, a stopped container reads Failed, and a Portainer outage reads Unknown."""
import os, sys, unittest
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T  # noqa: E402
import portainer_fake as F  # noqa: E402


class PortainerE2E(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_connection_pick_states_and_an_outage(self):
        web, login = F.Site(200), F.Site(401)
        self.addCleanup(web.close); self.addCleanup(login.close)
        p = F.Portainer(
            envs=[F.environment(1, "Granite"), F.environment(2, "Anchor3")],
            containers={1: [F.container("watchtower")],
                        2: [F.container("plex", ports=[web.port]),
                            F.container("scrob", stack="scrob", ports=[login.port]),
                            F.container("old", state="exited", status="Exited (0) 2 days ago")]})
        self.addCleanup(p.close)
        conn = {"id": "granite-portainer", "module": "portainer", "name": "Granite", "base_url": p.url, "token": F.TOKEN, "timeout": 2}
        c = self.start()
        self.configure(c, [conn], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": p.port}]}])
        # Test connection uses the form's settings and reports what it found, never the token
        tested = c.post("/api/connections/test", {"connection": {**conn, "id": "new-one"}})
        self.assertTrue(tested["ok"], tested)
        self.assertNotIn(F.TOKEN, str(tested))
        bad = c.post("/api/connections/test", {"connection": {**conn, "id": "new-one", "token": "fake-wrong-9"}})
        self.assertTrue(bad["ok"] is False or bad.get("found") == [], bad)
        # Pick
        found = c.post("/api/detect", {"connection": "granite-portainer"})
        by = {s["label"]: s for s in found["suggest"]}
        self.assertFalse(by["Container old on Anchor3"]["default"])          # stopped: listed but not ticked
        self.assertTrue(by["Container plex on Anchor3"]["default"])
        self.assertIn("Web plex on Anchor3", by)
        keep = [s for s in found["suggest"] if s.get("default") is not False]
        keep.append(by["Container old on Anchor3"])
        items = [{k: s[k] for k in ("label", "check", "params", "node", "group", "type", "url", "expect", "insecure", "service", "requires") if k in s} for s in keep]
        out = c.post("/api/watch", {"connection": "granite-portainer", "items": items})
        self.assertIn("added", out, out)
        n = self.states(c, {"plex-anchor3": "healthy", "scrob-anchor3": "healthy", "old-anchor3": "failed", "anchor3-portainer": "healthy"})
        self.assertEqual(n["plex-anchor3"]["service"]["title"], "Plex")
        self.assertEqual(len(n["plex-anchor3"]["checks"]), 2)                  # the container and its web page
        # the web page breaks while the container stays up: the service is no longer healthy (Degraded: one of its two checks fails)
        web.code = 503
        n = self.states(c, {"plex-anchor3": "degraded"}, timeout=90)       # web checks run every 30 s
        self.assertEqual([k["state"] for k in n["plex-anchor3"]["checks"]], ["healthy", "failed"])
        # Portainer goes away: cannot be checked, not failed
        p.down = True
        web.code = 200
        self.states(c, {"anchor3-portainer": "unknown", "old-anchor3": "unknown"}, timeout=60)
        # read-only, with the token on every request
        self.assertEqual({r[0] for r in p.requests}, {"GET"})
        self.assertTrue(all(r[2] in (F.TOKEN, "fake-wrong-9", None) for r in p.requests))


    def test_a_scrypted_container_in_portainer_shows_up_as_a_discovery_that_can_be_hidden(self):
        web = F.Site(200); self.addCleanup(web.close)
        p = F.Portainer(envs=[F.environment(1, "Anchor3")], containers={1: [F.container("scrypted", ports=[web.port], image="koush/scrypted:latest"), F.container("plex")]})
        self.addCleanup(p.close)
        conn = {"id": "pt", "module": "portainer", "name": "Anchor3", "base_url": p.url, "token": F.TOKEN, "timeout": 2}
        c = self.start()
        self.configure(c, [conn], [{"id": "pi", "name": "Pi", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": p.port}]}])
        got = T.wait(lambda: [x for x in c.get("/api/followups")["suggestions"] if x["kind"] == "scrypted"], what="Portainer's answer")
        self.assertEqual((got[0]["host"], got[0]["how"]), ("127.0.0.1", "setup"))
        self.assertIn("Portainer shows", got[0]["why"])
        if sync_playwright is None:
            c.post("/api/followups/dismiss", {"id": got[0]["id"]})
        else:
            with sync_playwright() as pw:
                b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
                errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
                pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
                pg.wait_for_selector("#hdr .badge")                            # the bell counts the new find
                self.assertEqual("1", pg.inner_text("#hdr .badge").strip())
                pg.click("#bellbtn"); pg.click("#bell .nitem"); pg.wait_for_selector("text=Scrypted on 127.0.0.1")
                pg.click("#fu button:has-text('Not now')")
                pg.wait_for_function("!document.querySelector('#fu .devrow')")
                self.assertEqual(errs, [])
                b.close()
        self.assertEqual([x for x in c.get("/api/followups")["suggestions"] if x["kind"] == "scrypted"], [], "hidden for good")


if __name__ == "__main__":
    unittest.main()
