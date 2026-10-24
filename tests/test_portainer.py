"""Portainer module: read-only, token only, states from Docker's own words, Unknown when Portainer or an environment cannot be read."""
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MOD = os.path.join(HERE, "..", "modules", "portainer")
sys.path.insert(0, MOD)
import portainer_fake as F
import importlib.util
import portainerlib as P, portainerchecks as C
_spec = importlib.util.spec_from_file_location("portainer_main", os.path.join(MOD, "main.py"))      # not `import main`: every module has one
M = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(M)


def conn(p, **kw):
    return {"module": "portainer", "base_url": p.url, "token": F.TOKEN, "timeout": 3, **kw}


class CheckPath(unittest.TestCase):
    def test_pihole_is_checked_at_its_front_page_and_others_at_the_plain_address(self):
        from importlib import import_module
        C = import_module("portainerchecks")
        mk = lambda n: {"Names": ["/" + n], "Image": "x/" + n + ":latest", "Labels": {}}
        self.assertEqual(C.check_path(mk("pihole")), "admin/")
        self.assertEqual(C.check_path(mk("pi-hole")), "admin/")
        self.assertEqual(C.check_path(mk("plex")), "")


class Base(unittest.TestCase):
    def setUp(self):
        M.CLIENTS.clear()
        self.web, self.login, self.db = F.Site(200), F.Site(401), F.Silent()
        for x in (self.web, self.login, self.db):
            self.addCleanup(x.close)
        envs = [F.environment(1, "Granite", type_=1, url="unix:///var/run/docker.sock"), F.environment(2, "Anchor3", url="tcp://127.0.0.1:9001"),
                F.environment(3, "Tidewater", status=2, url="tcp://10.9.0.5:9001")]
        cs = {1: [F.container("portainer", status="Up 2 days"), F.container("backup-job", state="exited", status="Exited (0) 3 hours ago")],
              2: [F.container("plex", image="lscr.io/linuxserver/plex:latest", ports=[self.web.port]),
                  F.container("scrob", stack="scrob", status="Up 1 hour (healthy)", ports=[self.login.port]),
                  F.container("scrob-db", stack="scrob", status="Up 1 hour", ports=[self.db.port]),
                  F.container("sonarr", status="Up 5 minutes (unhealthy)"),
                  F.container("loopy", state="restarting", status="Restarting (1) 4 seconds ago"),
                  F.container("pausey", state="paused", status="Up 1 hour (Paused)"),
                  F.container("booting", status="Up 3 seconds (health: starting)")]}
        self.p = F.Portainer(envs, cs); self.addCleanup(self.p.close)
        self.conn = conn(self.p)

    def check(self, kind, params):
        return M.run_check(kind, params, self.conn)


class Checks(Base):
    def test_container_states_follow_dockers_own_words(self):
        want = {"plex": "healthy", "scrob": "healthy", "sonarr": "failed", "loopy": "failed", "pausey": "degraded", "booting": "healthy"}
        for name, state in want.items():
            self.assertEqual(self.check("container", {"env": "Anchor3", "name": name})["state"], state, name)
        self.assertIn("unhealthy", self.check("container", {"env": "Anchor3", "name": "sonarr"})["detail"])
        self.assertIn("restarting", self.check("container", {"env": "Anchor3", "name": "loopy"})["detail"])

    def test_a_stopped_container_fails_unless_it_is_meant_to_be_stopped(self):
        self.assertEqual(self.check("container", {"env": "Granite", "name": "backup-job"})["state"], "failed")
        r = self.check("container", {"env": "Granite", "name": "backup-job", "allow_stopped": True})
        self.assertEqual(r["state"], "healthy"); self.assertIn("as expected", r["detail"])

    def test_environment_down_fails_it_but_leaves_its_containers_unknown(self):
        self.assertEqual(self.check("environment", {"name": "Anchor3"})["state"], "healthy")
        r = self.check("environment", {"name": "Tidewater"})
        self.assertEqual(r["state"], "failed"); self.assertIn("10.9.0.5", r["detail"])
        r = self.check("container", {"env": "Tidewater", "name": "anything"})
        self.assertEqual(r["state"], "unknown"); self.assertIn("cannot reach Tidewater", r["detail"])

    def test_a_missing_container_or_environment_is_unknown_not_failed(self):
        self.assertEqual(self.check("container", {"env": "Anchor3", "name": "gone"})["state"], "unknown")
        self.assertEqual(self.check("container", {"env": "Nowhere", "name": "x"})["state"], "unknown")
        self.assertEqual(self.check("environment", {"name": "Nowhere"})["state"], "unknown")

    def test_portainer_unreachable_or_a_wrong_token_is_unknown_not_failed(self):
        self.p.down = True
        M.CLIENTS.clear()
        for e in (P.PortainerError,):
            with self.assertRaises(e):
                M.run_check("environment", {"name": "Anchor3"}, self.conn)
        # through the protocol the same errors become Unknown
        import io, json, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.serve({"id": 1, "method": "check", "params": {"check": "environment", "params": {"name": "Anchor3"}, "connection": self.conn}})
        self.assertEqual(json.loads(out.getvalue())["result"]["state"], "unknown")
        self.p.down = False; M.CLIENTS.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.serve({"id": 2, "method": "check", "params": {"check": "environment", "params": {"name": "Anchor3"}, "connection": {**self.conn, "token": "fake-wrong-token-2"}}})
        r = json.loads(out.getvalue())["result"]
        self.assertEqual(r["state"], "unknown"); self.assertIn("refused the access token", r["detail"])
        self.assertNotIn("fake-wrong-token-2", out.getvalue())          # the token never comes back in a message

    def test_only_get_requests_with_the_token_ever_leave(self):
        self.check("environment", {"name": "Anchor3"}); self.check("container", {"env": "Anchor3", "name": "plex"})
        M.handle({"method": "discover", "params": {"connection": self.conn}})
        self.assertTrue(self.p.requests)
        self.assertEqual({m for m, _p, _k in self.p.requests}, {"GET"})
        self.assertEqual({k for _m, _p, k in self.p.requests}, {F.TOKEN})
        self.assertTrue(all(P.READ_ONLY.match(path) for _m, path, _k in self.p.requests), [r[1] for r in self.p.requests])

    def test_the_client_refuses_any_path_it_is_not_allowed_to_fetch(self):
        c = M.client(self.conn)
        for bad in ("/api/users", "/api/endpoints/1/docker/containers/abc/stop", "/api/endpoints/1/docker/containers/json/../exec", "/api/stacks"):
            with self.assertRaises(P.PortainerError):
                c.get(bad)

    def test_where_portainer_is_follows_its_own_defaults(self):
        self.assertEqual(P.base_of({"host": "192.0.2.13"}), "https://192.0.2.13:9443")
        self.assertEqual(P.base_of({"host": "192.0.2.13", "http": True}), "http://192.0.2.13:9000")
        self.assertEqual(P.base_of({"host": "192.0.2.13", "port": 9444}), "https://192.0.2.13:9444")
        self.assertEqual(P.base_of({"host": "192.0.2.13:8443"}), "https://192.0.2.13:8443")
        self.assertEqual(P.base_of({"base_url": "http://portainer.lan:9000/some/path"}), "http://portainer.lan:9000")

    def test_a_connection_without_a_token_says_what_to_do(self):
        with self.assertRaises(P.PortainerError) as e:
            M.client({"base_url": self.p.url})
        self.assertIn("access token", str(e.exception))


class Discovery(Base):
    def setUp(self):
        super().setUp()
        self.r = M.handle({"method": "discover", "params": {"connection": self.conn}})
        self.by = {s["label"]: s for s in self.r["suggest"]}

    def test_environments_are_listed_with_where_they_are(self):
        envs = {e["name"]: e for e in self.r["environments"]}
        self.assertEqual((envs["Anchor3"]["up"], envs["Anchor3"]["address"]), (True, "127.0.0.1"))
        self.assertEqual((envs["Tidewater"]["up"], envs["Tidewater"]["address"]), (False, "10.9.0.5"))
        self.assertEqual(envs["Granite"]["address"], "127.0.0.1")        # a unix socket means Portainer's own machine

    def test_containers_are_grouped_by_stack_and_running_ones_are_ticked(self):
        c = self.by["Container scrob on Anchor3"]
        self.assertEqual((c["batch"], c["service"]["stack"], c["default"]), ("Anchor3 · scrob", "scrob", True))
        self.assertEqual(self.by["Container plex on Anchor3"]["batch"], "Anchor3 · other containers")
        self.assertFalse(self.by["Container backup-job on Granite"]["default"])     # it has exited: probably a one-shot job
        self.assertNotIn("Container anything on Tidewater", self.by)

    def test_a_down_environment_still_gets_its_own_check_but_no_containers(self):
        self.assertIn("Environment Tidewater", self.by)
        self.assertFalse([s for s in self.r["suggest"] if s["label"].endswith("on Tidewater")])

    def test_web_checks_are_suggested_only_where_something_answers_http(self):
        self.assertEqual(self.by["Web plex on Anchor3"]["url"], f"http://127.0.0.1:{self.web.port}/")
        self.assertNotIn("expect", self.by["Web plex on Anchor3"])
        w = self.by["Web scrob on Anchor3"]                               # a login wall still proves the app is answering
        self.assertEqual(w["url"], f"http://127.0.0.1:{self.login.port}/"); self.assertIn(401, w["expect"]); self.assertIn(200, w["expect"])
        self.assertNotIn("Web scrob-db on Anchor3", self.by)              # a database port is open but is not HTTP
        self.assertEqual(self.by["Container plex on Anchor3"]["service"]["url"], self.by["Web plex on Anchor3"]["url"] + "web")   # same address; the link goes on to Plex's own front page

    def test_icon_names_come_from_the_image_and_titles_are_readable(self):
        self.assertEqual(self.by["Container plex on Anchor3"]["service"]["icon"], "plex")
        self.assertEqual(self.by["Container scrob-db on Anchor3"]["service"]["title"], "Scrob db")
        self.assertEqual(self.by["Container plex on Anchor3"]["node"], "Plex (Anchor3)")

    def test_every_item_says_which_environment_it_belongs_to(self):
        self.assertTrue(all(x.get("env") for x in self.r["suggest"]))
        self.assertEqual(self.by["Container plex on Anchor3"]["env"], "Anchor3")
        self.assertEqual(self.by["Web plex on Anchor3"]["env"], "Anchor3")
        self.assertEqual(self.by["Environment Tidewater"]["env"], "Tidewater")

    def test_every_container_item_needs_its_environment_check(self):
        c = self.by["Container plex on Anchor3"]
        self.assertEqual(c["requires"]["label"], "Environment Anchor3")
        self.assertEqual(self.by["Web plex on Anchor3"]["requires"]["label"], "Environment Anchor3")


class HostNetworkLinks(unittest.TestCase):
    """Apps on the host network publish no ports, so a link comes from the app's usual port, and only when something answers there."""
    def host(self, name, image):
        c = F.container(name, image=image)
        c["HostConfig"] = {"NetworkMode": "host"}
        return c

    def test_candidates(self):
        plex = self.host("plex", "plexinc/pms-docker:latest")
        self.assertEqual(C.web_candidates(plex), [32400])
        self.assertEqual(C.web_candidates(self.host("home-assistant", "ghcr.io/home-assistant/home-assistant:stable")), [8123])
        self.assertEqual(C.web_candidates(self.host("homebridge-homebridge-1", "homebridge/homebridge:latest")), [8581])
        self.assertEqual(C.web_candidates(self.host("mystery", "example/mystery")), [])                # nothing to guess from
        bridged = F.container("plex", image="plexinc/pms-docker")                                    # not on the host network: no guessing
        self.assertEqual(C.web_candidates(bridged), [])
        self.assertEqual(C.web_candidates(dict(self.host("plex", "x/plex"), Ports=[{"PublicPort": 1234, "Type": "tcp"}])), [1234])   # a published port wins

    def test_discover_offers_the_link_only_when_something_answers(self):
        asked = []
        def probe(host, port):
            asked.append((host, port))
            return {"url": f"http://{host}:{port}/"} if port == 32400 else None
        env = F.environment(1, "Anchor3", url="tcp://10.0.0.7:9001")
        r = C.discover([env], lambda i: [self.host("plex", "plexinc/pms-docker"), self.host("homebridge", "homebridge/homebridge")], "10.0.0.7", probe)
        by = {s["label"]: s for s in r["suggest"]}
        self.assertEqual(by["Container plex on Anchor3"]["service"]["url"], "http://10.0.0.7:32400/web")        # the link opens the app's own front page
        self.assertIn("Web plex on Anchor3", by)
        self.assertNotIn("url", by["Container homebridge on Anchor3"]["service"])                       # nothing answered on 8581
        self.assertEqual(sorted(asked, key=lambda x: x[1]), [("10.0.0.7", 8581), ("10.0.0.7", 32400)])

    def test_an_edge_agent_has_no_address_and_is_never_looked_for_on_the_portainer_servers_own(self):
        asked = []
        def probe(host, port):
            asked.append((host, port)); return {"url": f"http://{host}:{port}/"}
        edge = F.environment(2, "Cabin", type_=4, url="")
        r = C.discover([edge], lambda i: [self.host("plex", "plexinc/pms-docker")], "10.0.0.7", probe)
        self.assertEqual(r["environments"], [{"name": "Cabin", "type": "Edge agent", "up": True, "address": "", "edge": True}])
        self.assertEqual(asked, [], "the Portainer server's own address was not borrowed for it")
        self.assertIn("Container plex on Cabin", {s["label"] for s in r["suggest"]}, "its containers are still listed through Portainer")

    def test_links_open_the_apps_own_front_page(self):
        self.assertEqual(C.link_path(self.host("plex", "plexinc/pms-docker")), "web")
        self.assertEqual(C.link_path(self.host("pihole", "pihole/pihole")), "admin/")
        self.assertEqual(C.link_path(self.host("radarr", "linuxserver/radarr")), "")
        def probe(host, port): return {"url": f"http://{host}:{port}/"}
        env = F.environment(1, "Anchor3", url="tcp://10.0.0.7:9001")
        r = C.discover([env], lambda i: [self.host("plex", "plexinc/pms-docker")], "10.0.0.7", probe)
        by = {s["label"]: s for s in r["suggest"]}
        self.assertEqual(by["Container plex on Anchor3"]["service"]["url"], "http://10.0.0.7:32400/web")   # the link
        self.assertEqual(by["Web plex on Anchor3"]["url"], "http://10.0.0.7:32400/")                       # the check stays on the plain address


if __name__ == "__main__":
    unittest.main()
