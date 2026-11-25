"""Docker MAC address watch (Portainer module, check "mac"): the acceptance tests of the 2026-11-25 Goliath requirement, on mocked Docker answers only.

Nothing here touches a real Docker host. The fixtures are the exact November 25 failure on Goliath's "media" bridge and its clean baseline."""
import hashlib, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MOD = os.path.join(HERE, "..", "modules", "portainer")
sys.path.insert(0, MOD)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
import importlib.util
import portainer_fake as F
import macwatch as W
import portainerchecks as C
from monitorbox_app import alerts, engine, monconfig  # noqa: E402

_spec = importlib.util.spec_from_file_location("portainer_main_macs", os.path.join(MOD, "main.py"))
M = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(M)

MEDIA = "a1" * 32                      # network ids, as Docker gives them (64 hex)
OTHER = "b2" * 32
CANARY = "c3" * 32


def cid(name):
    return hashlib.sha256(name.encode()).hexdigest()


def listed(name, state="running"):
    return {"Id": cid(name), "Names": ["/" + name], "State": state, "Status": "Up 1 hour", "Image": "x", "Labels": {}}


class Env:
    """One fake Docker environment behind a fake Portainer. eps: {network id: (name, [(container, ipv4, mac)])}; cfg: {container: config MAC}."""

    def __init__(self, test, nets, cfg=None, stopped=(), extra=None, envs=None):
        self.test, self.cfg, self.stopped = test, dict(cfg or {}), set(stopped)
        self.set(nets, extra)
        envs = envs or [F.environment(1, "Goliath", type_=1, url="unix:///var/run/docker.sock")]
        self.p = F.Portainer(envs, self.lists, networks=self.nets, inspects=self.ins)
        test.addCleanup(self.p.close)
        self.conn = {"module": "portainer", "base_url": self.p.url, "token": F.TOKEN, "timeout": 3}

    def set(self, nets, extra=None, env_id=1):
        names, nl, ins = {}, [], {}
        for nid, (nname, eps) in nets.items():
            nl.append(F.network(nid, nname, [(cid(c), c, ip, mac) for c, ip, mac in eps]))
            for c, ip, mac in eps:
                names.setdefault(c, {})[nname] = (ip, mac)
        for c in (extra or {}):
            names.setdefault(c, {}).update(extra[c])
        for c, nn in names.items():
            first = next(iter(nn), "bridge")
            ins[cid(c)] = F.inspect(cid(c), c, config_mac=self.cfg.get(c, ""), network_mode=first, running=c not in self.stopped, networks=nn)
        if not hasattr(self, "nets"):
            self.nets, self.ins, self.lists = {}, {}, {}
        self.nets[env_id], self.ins[env_id] = nl, ins
        self.lists[env_id] = [listed(c, "exited" if c in self.stopped else "running") for c in names]
        M.MACS.snaps.clear()                                # a new picture: do not reuse the last 20 seconds' reading

    def check(self, allow=None, env="Goliath"):
        M.CLIENTS.clear()
        return M.run_check("mac", {"env": env, **({"allow": allow} if allow is not None else {})}, self.conn)


# The exact failure of 2026-11-25 on Goliath (section 2 of the requirement)
NOV25 = {MEDIA: ("media", [("spottarr", "172.29.0.6", "02:42:ac:1d:00:09"), ("qbittorrent", "172.29.0.9", "02:42:ac:1d:00:09"),
                           ("sabnzbd", "172.29.0.5", "02:42:ac:1d:00:05"), ("flaresolverr", "172.29.0.10", "02:42:ac:1d:00:05"),
                           ("lidarr", "172.29.0.2", "02:42:ac:1d:00:02"), ("sonarr", "172.29.0.3", "02:42:ac:1d:00:03")])}
# The baseline after the fix (section 9): all unique, one leftover fixed MAC on its own network
BASELINE = {MEDIA: ("media", [(n, f"172.29.0.{i}", f"02:42:ac:1d:00:{i:02x}") for i, n in
                              enumerate(["lidarr", "sonarr", "radarr", "sabnzbd", "spottarr", "bazarr", "prowlarr", "qbittorrent", "flaresolverr"], 2)]),
            CANARY: ("db-canary-agent_default", [("db-canary-agent", "172.29.8.2", "02:42:ac:1d:08:02")])}


class Acceptance(unittest.TestCase):
    def setUp(self):
        M.CLIENTS.clear(); M.MACS.snaps.clear(); M.MACS.settings.clear()

    def test_unique_macs_on_a_bridge_are_healthy(self):
        r = Env(self, {MEDIA: BASELINE[MEDIA]}).check()
        self.assertEqual(r["state"], "healthy", r)
        self.assertIn("9 MAC addresses", r["detail"])

    def test_the_november_25_failure_is_critical_and_names_both_pairs(self):
        r = Env(self, NOV25, cfg={"spottarr": "02:42:ac:1d:00:09", "flaresolverr": "02:42:ac:1d:00:05"}).check()
        self.assertEqual(r["state"], "failed")
        d = r["detail"]
        self.assertIn("02:42:ac:1d:00:09 on network media is used by qbittorrent (172.29.0.9) and spottarr (172.29.0.6)", d)
        self.assertIn("02:42:ac:1d:00:05 on network media is used by flaresolverr (172.29.0.10) and sabnzbd (172.29.0.5)", d)
        self.assertIn("spottarr has 172.29.0.6, Docker would give it 02:42:ac:1d:00:06", d)      # the IP/MAC hint, as supporting detail
        self.assertIn("Recreate the affected containers", d)
        self.assertTrue(r["key"])

    def test_two_containers_sharing_a_mac_is_critical(self):
        r = Env(self, {MEDIA: ("media", [("a", "172.29.0.2", "02:42:ac:1d:00:02"), ("b", "172.29.0.3", "02:42:ac:1d:00:02")])}).check()
        self.assertEqual(r["state"], "failed")

    def test_three_sharing_a_mac_are_one_clash_naming_all_three(self):
        eps = [("a", "172.29.0.2", "02:42:ac:1d:00:02"), ("b", "172.29.0.3", "02:42:ac:1d:00:02"), ("c", "172.29.0.4", "02:42:ac:1d:00:02")]
        r = W.judge({"env": "G", "networks": [{"id": MEDIA, "name": "media"}], "containers": [],
                     "endpoints": [{"network": "media", "network_id": MEDIA, "container_id": n, "endpoint_id": n, "name": n, "ipv4": ip, "ipv6": "", "mac": mac}
                                   for n, ip, mac in eps]})
        self.assertEqual(len(r["clashes"]), 1)
        self.assertEqual([e["name"] for e in r["clashes"][0]["members"]], ["a", "b", "c"])
        self.assertIn("a (172.29.0.2), b (172.29.0.3) and c (172.29.0.4)", r["detail"])

    def test_the_same_mac_on_two_separate_bridges_is_not_a_clash(self):
        r = Env(self, {MEDIA: ("media", [("a", "172.29.0.2", "02:42:ac:1d:00:02")]),
                       OTHER: ("other", [("b", "172.30.0.2", "02:42:ac:1d:00:02")])}).check()
        self.assertEqual(r["state"], "healthy", r)

    def test_the_same_mac_on_two_docker_hosts_is_not_a_clash(self):
        envs = [F.environment(1, "Goliath", type_=1, url="unix:///var/run/docker.sock"), F.environment(2, "Arrrrr3", url="tcp://127.0.0.1:9002")]
        e = Env(self, {MEDIA: ("media", [("a", "172.29.0.2", "02:42:ac:1d:00:02")])}, envs=envs)
        e.set({MEDIA: ("media", [("b", "172.29.0.2", "02:42:ac:1d:00:02")])}, env_id=2)
        self.assertEqual(e.check(env="Goliath")["state"], "healthy")
        self.assertEqual(e.check(env="Arrrrr3")["state"], "healthy")

    def test_a_container_on_two_networks_is_judged_on_each(self):
        e = Env(self, {MEDIA: ("media", [("multi", "172.29.0.2", "02:42:ac:1d:00:02"), ("x", "172.29.0.3", "02:42:ac:1d:00:03")]),
                       OTHER: ("other", [("multi", "172.30.0.2", "02:42:ac:1e:00:02"), ("y", "172.30.0.3", "02:42:ac:1d:00:03")])})
        self.assertEqual(e.check()["state"], "healthy")         # 02:42:ac:1d:00:03 is on both networks, but on different ones
        e.set({MEDIA: ("media", [("multi", "172.29.0.2", "02:42:ac:1d:00:02"), ("x", "172.29.0.3", "02:42:ac:1d:00:03")]),
               OTHER: ("other", [("multi", "172.30.0.2", "02:42:ac:1e:00:02"), ("y", "172.30.0.3", "02:42:ac:1e:00:02")])})
        r = e.check()
        self.assertEqual(r["state"], "failed")
        self.assertIn("on network other is used by multi (172.30.0.2) and y (172.30.0.3)", r["detail"])
        self.assertNotIn("network media", r["detail"])

    def test_an_unexpected_fixed_mac_without_a_clash_is_a_warning(self):
        r = Env(self, BASELINE, cfg={"db-canary-agent": "02:42:ac:1d:08:02"}).check()          # Goliath today (section 9)
        self.assertEqual(r["state"], "degraded", r)
        self.assertIn("db-canary-agent has a fixed MAC 02:42:ac:1d:08:02 in its settings (network db-canary-agent_default, 172.29.8.2)", r["detail"])
        self.assertIn("No clash now", r["detail"])
        self.assertIn("Edit monitoring", r["detail"])

    def test_the_spottarr_warning_shows_the_ip_derived_mac(self):
        nets = {MEDIA: ("media", [("spottarr", "172.29.0.6", "02:42:ac:1d:00:09"), ("lidarr", "172.29.0.2", "02:42:ac:1d:00:02")])}
        r = Env(self, nets, cfg={"spottarr": "02:42:ac:1d:00:09"}).check()
        self.assertEqual(r["state"], "degraded")
        self.assertIn("spottarr has a fixed MAC 02:42:ac:1d:00:09 in its settings (network media, 172.29.0.6, Docker would give it 02:42:ac:1d:00:06)", r["detail"])

    def test_an_allowed_fixed_mac_without_a_clash_is_fine(self):
        e = Env(self, BASELINE, cfg={"db-canary-agent": "02:42:ac:1d:08:02"})
        for allow in (["db-canary-agent"], ["DB-Canary-Agent"], ["db-canary-agent/db-canary-agent_default"]):
            r = e.check(allow=allow)
            self.assertEqual(r["state"], "healthy", allow)
            self.assertIn("fixed MAC allowed for db-canary-agent", r["detail"])
        self.assertEqual(e.check(allow=["db-canary-agent/media"])["state"], "degraded")    # allowed on another network only

    def test_an_allowed_fixed_mac_in_a_clash_is_still_critical(self):
        r = Env(self, NOV25, cfg={"spottarr": "02:42:ac:1d:00:09"}).check(allow=["spottarr", "qbittorrent", "sabnzbd", "flaresolverr"])
        self.assertEqual(r["state"], "failed")

    def test_a_mac_that_does_not_follow_the_ip_is_not_a_fault(self):
        nets = {MEDIA: ("media", [("a", "172.29.0.2", "d6:1f:93:4a:00:11"), ("b", "172.29.0.3", "02:42:ac:1d:00:09")])}     # Docker 28 random, or a driver's own
        self.assertEqual(Env(self, nets).check()["state"], "healthy")

    def test_an_empty_mac_is_ignored(self):
        nets = {MEDIA: ("media", [("a", "172.29.0.2", ""), ("b", "172.29.0.3", ""), ("c", "", "")])}
        r = Env(self, nets).check()
        self.assertEqual(r["state"], "healthy", r)

    def test_upper_and_lower_case_are_the_same_mac(self):
        nets = {MEDIA: ("media", [("a", "172.29.0.2", "02:42:AC:1D:00:09"), ("b", "172.29.0.3", "02:42:ac:1d:00:09")])}
        r = Env(self, nets).check()
        self.assertEqual(r["state"], "failed")
        self.assertIn("02:42:ac:1d:00:09", r["detail"])

    def test_a_stopped_container_listed_on_the_network_counts(self):
        nets = {MEDIA: ("media", [("a", "172.29.0.2", "02:42:ac:1d:00:02"), ("ghost", "", "02:42:ac:1d:00:02")])}
        self.assertEqual(Env(self, nets, stopped=["ghost"]).check()["state"], "failed")

    def test_a_runtime_mac_alone_is_not_a_fixed_mac(self):
        r = Env(self, {MEDIA: BASELINE[MEDIA]}).check()           # every endpoint has a MAC, none asked for one
        self.assertEqual(r["state"], "healthy")

    def test_a_stopped_containers_requested_endpoint_mac_is_a_fixed_mac(self):
        e = Env(self, {MEDIA: BASELINE[MEDIA]}, stopped=["parked"], extra={"parked": {"media": ("", "02:42:ac:1d:00:63")}})
        r = e.check()
        self.assertEqual(r["state"], "degraded")
        self.assertIn("parked has a fixed MAC 02:42:ac:1d:00:63 in its network settings (it is stopped)", r["detail"])

    def test_host_networked_containers_are_left_alone(self):
        e = Env(self, {MEDIA: BASELINE[MEDIA]}, cfg={"hostly": "02:42:ac:11:00:02"}, extra={"hostly": {}})
        e.ins[1][cid("hostly")]["HostConfig"]["NetworkMode"] = "host"
        self.assertEqual(e.check()["state"], "healthy")

    def test_a_recreated_container_with_clean_settings_clears_the_warning(self):
        e = Env(self, BASELINE, cfg={"db-canary-agent": "02:42:ac:1d:08:02"})
        self.assertEqual(e.check()["state"], "degraded")
        e.cfg = {}
        e.set({**BASELINE, CANARY: ("db-canary-agent_default", [("db-canary-agent2", "172.29.8.2", "02:42:ac:1d:08:02")])})   # a new id, no fixed MAC
        self.assertEqual(e.check()["state"], "healthy")
        self.assertFalse(any(k[1] == cid("db-canary-agent") for k in M.MACS.settings))       # the old container's settings were dropped

    def test_settings_are_read_once_per_container(self):
        e = Env(self, BASELINE)
        e.check(); M.MACS.snaps.clear(); e.check()
        reads = [r for r in e.p.requests if r[1].endswith(f"/containers/{cid('sonarr')}/json")]
        self.assertEqual(len(reads), 1)

    def test_portainer_unreachable_is_unknown(self):
        e = Env(self, NOV25)
        e.p.down = True
        r = e.check()
        self.assertEqual(r["state"], "unknown")

    def test_a_half_read_network_is_unknown_never_clean(self):
        e = Env(self, {**BASELINE, OTHER: ("other", [("z", "172.30.0.2", "02:42:ac:1e:00:02")])})
        e.p.broken.add("/docker/networks/" + OTHER)
        r = e.check()
        self.assertEqual(r["state"], "unknown")
        self.assertIn("nothing is judged", r["detail"])

    def test_an_environment_portainer_cannot_reach_is_unknown(self):
        e = Env(self, NOV25, envs=[F.environment(1, "Goliath", type_=1, status=2)])
        self.assertEqual(e.check()["state"], "unknown")

    def test_read_only_and_no_secrets_come_out(self):
        e = Env(self, NOV25, cfg={"spottarr": "02:42:ac:1d:00:09"})
        r = e.check()
        self.assertEqual({m for m, _, _ in e.p.requests}, {"GET"})
        self.assertNotIn("do-not-leak", json.dumps(r))
        self.assertNotIn("do-not-leak", json.dumps({str(k): v for k, v in M.MACS.settings.items()}))     # not even kept in memory

    def test_ids_are_the_stable_names_from_the_requirement(self):
        snap = {"env": "Goliath", "networks": [], "containers": [{"id": "x", "name": "spottarr", "state": "running", "config_mac": "02:42:ac:1d:00:09",
                                                                    "network_mode": "media", "running": True, "endpoints": {}}],
                "endpoints": [{"network": "media", "network_id": MEDIA, "container_id": n, "endpoint_id": n, "name": n, "ipv4": "", "ipv6": "",
                               "mac": "02:42:ac:1d:00:09"} for n in ("spottarr", "qbittorrent")]}
        r = W.judge(snap)
        self.assertEqual(r["ids"], [f"docker-mac-duplicate:Goliath:{MEDIA}:02:42:ac:1d:00:09=qbittorrent,spottarr", "docker-mac-persisted:Goliath:spottarr"])

    def test_discovery_suggests_a_watch_per_docker_environment_every_5_minutes(self):
        envs = [F.environment(1, "Goliath", type_=1, url="unix:///var/run/docker.sock"), F.environment(5, "K8s", type_=5)]
        out = C.discover(envs, lambda i: [], "127.0.0.1", lambda h, p: None)
        macs = [s for s in out["suggest"] if s.get("check") == "mac"]
        self.assertEqual(len(macs), 1)
        self.assertEqual((macs[0]["params"], macs[0]["interval"], macs[0]["default"]), ({"env": "Goliath"}, 300, True))
        self.assertEqual(monconfig.watch_item(macs[0])["interval"], 300)


def node(checks, nid="macs", name="Docker MAC addresses (Goliath)"):
    return {"id": nid, "name": name, "group": "Services", "critical": False, "rule": "primary", "dependsOn": [], "checks": checks}


MAC_CHECK = [{"id": "mac", "type": "module", "module": "portainer", "check": "mac", "params": {"env": "Goliath"}, "connection": "p"}]


def snap(ok, key="", warn=False, detail="x"):
    r = {} if ok == "none" else {"macs/mac": {"ok": ok, "detail": detail, "ms": 1, "at": "t", "since": "t", "warn": warn, **({"key": key} if key else {})}}
    return engine.evaluate([node(MAC_CHECK)], r, "t")


class Lifecycle(unittest.TestCase):
    """Alert life of the watch: once per problem, again when the clash changes, all-clear when it clears, nothing for a failed read, nothing twice after a restart."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sent, self.now = [], 1000.0
        self.a = self.make()

    def make(self):
        a = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                          send=lambda url, ev: self.sent.append(ev), clock=lambda: self.now, hostname=lambda: "Goliath")
        a.set({"enabled": True, "homeAssistant": {"webhook": "http://ha.example.invalid/api/webhook/x"}, "delaySeconds": 60})
        return a

    def go(self, s, secs=0):
        self.now += secs
        ev = self.a.observe(s, self.now)
        self.a.flush(self.now)
        return ev

    def announce(self, s):
        self.go(s); self.go(s, 61)
        self.assertEqual(self.sent[-1]["event"], "problem")

    def test_the_attention_entry_carries_the_key(self):
        self.assertEqual(snap(False, "k1")["attention"][0]["key"], "k1")

    def test_an_unchanged_clash_is_announced_once(self):
        bad = snap(False, "k1")
        self.announce(bad)
        n = len(self.sent)
        for _ in range(20):
            self.go(bad, 300)
        self.assertEqual(len(self.sent), n)

    def test_a_change_in_who_clashes_is_announced_once_it_lasts(self):
        self.announce(snap(False, "k1", detail="a and b"))
        self.assertEqual(self.go(snap(False, "k2", detail="a, b and c"), 5), [])        # not at once: a recreate in progress settles first
        self.assertEqual(self.go(snap(False, "k2", detail="a, b and c"), 30), [])
        ev = self.go(snap(False, "k2", detail="a, b and c"), 31)
        self.assertEqual(len(ev), 1)
        self.assertIn("still down, with a change", ev[0]["title"])
        self.assertIn("a, b and c", ev[0]["message"])
        self.assertEqual(self.go(snap(False, "k2"), 300), [])

    def test_a_change_that_reverts_quickly_says_nothing(self):
        self.announce(snap(False, "k1"))
        self.go(snap(False, "k2"), 5)
        self.go(snap(False, "k1"), 5)
        self.assertEqual(self.go(snap(False, "k1"), 120), [])

    def test_a_new_fixed_mac_is_announced_and_a_clash_on_top_updates(self):
        self.announce(snap(True, "p1", warn=True))
        self.assertEqual(self.sent[-1]["state"], "degraded")
        self.go(snap(False, "d1")); ev = self.go(snap(False, "d1"), 61)
        self.assertEqual([e["state"] for e in ev], ["failed"])

    def test_a_cleared_clash_brings_an_all_clear(self):
        self.announce(snap(False, "k1"))
        self.go(snap(True), 5)
        ev = self.go(snap(True), 31)
        self.assertEqual([e["event"] for e in ev], ["recovered"])

    def test_a_cleared_fixed_mac_brings_an_all_clear(self):
        self.announce(snap(True, "p1", warn=True))
        self.go(snap(True), 5)
        self.assertEqual([e["event"] for e in self.go(snap(True), 31)], ["recovered"])

    def test_a_failed_read_is_never_an_all_clear(self):
        self.announce(snap(False, "k1"))
        for _ in range(10):
            self.assertEqual(self.go(snap(None, detail="could not read every Docker network"), 60), [])
        self.assertEqual(self.go(snap(False, "k1"), 60), [])           # still the same clash: nothing new to say

    def test_a_restart_during_a_clash_does_not_announce_it_again(self):
        self.announce(snap(False, "k1"))
        n = len(self.sent)
        self.a = self.make()                                            # MonitorBox restarted: alert state comes back from disk
        self.go(snap(False), 5)                                         # the reading saved before the restart (no key yet)
        for _ in range(5):
            self.go(snap(False, "k1"), 120)
        self.assertEqual(len(self.sent), n)
        self.go(snap(False, "k9"), 5); self.go(snap(False, "k9"), 61)    # and a real change after the restart is still told
        self.assertEqual(len(self.sent), n + 1)


class Settings(unittest.TestCase):
    """Edit monitoring: how often the watch looks and which fixed MACs are on purpose. Saved in the config, checked first."""

    def setUp(self):
        from monitorbox_app.store import Paths
        self.paths = Paths(tempfile.mkdtemp())
        monconfig.save_connections(self.paths, [{"id": "p", "module": "portainer", "host": "192.0.2.9", "token": "fake-token-9"}], 0)
        monconfig.save_monitoring(self.paths, {"builtinInternet": True, "nodes": [node([{**MAC_CHECK[0], "interval": 300}])]},
                                  monconfig.get_monitoring(self.paths)["revision"])

    def check(self):
        return next(n for n in monconfig.get_monitoring(self.paths)["monitoring"]["nodes"] if n["id"] == "macs")["checks"][0]

    def test_allow_and_interval_are_saved_and_cleared(self):
        monconfig.set_mac_watch(self.paths, "macs", 600, ["db-canary-agent", " ", "DB-CANARY-AGENT", "web/media"])
        c = self.check()
        self.assertEqual((c["interval"], c["params"]["allow"]), (600, ["db-canary-agent", "web/media"]))
        monconfig.set_mac_watch(self.paths, "macs", None, [])
        c = self.check()
        self.assertEqual(c["interval"], 300)
        self.assertNotIn("allow", c["params"])

    def test_bad_values_are_refused(self):
        for interval, allow in ((5, []), (True, []), (300, ["a b"]), (300, "x")):
            with self.assertRaises(monconfig.Invalid):
                monconfig.set_mac_watch(self.paths, "macs", interval, allow)
        with self.assertRaises(monconfig.Invalid):
            monconfig.set_mac_watch(self.paths, "nope", 300, [])


class KeyTravels(unittest.TestCase):
    """The module's name for what is wrong reaches the attention list through the App's own paths (modules.py, monitor.py, engine.py)."""

    def test_module_answer_to_attention_entry(self):
        from monitorbox_app import modules, monitor
        class Proc:
            def alive(self): return True
            def call(self, *a, **k): return {"state": "failed", "detail": "clash", "key": "abc123"}
        mm = modules.Modules.__new__(modules.Modules)
        mm.running, mm.starting, mm.boot = {"portainer": Proc()}, set(), 0
        mm.record_took = lambda *a: None
        out = mm.check({"module": "portainer", "check": "mac", "params": {}}, {})
        self.assertEqual((out[0], out[3]), (False, {"key": "abc123"}))
        t = [1_700_000_000.0]
        m = monitor.Monitor(runner=lambda c: out, clock=lambda: t[0], inline=True)
        m.configure([node(MAC_CHECK)], None, {"failures": 1, "seconds": 0})
        m.run_due(); t[0] += 3; m.run_due()                 # a first failure is looked at twice before it is shown
        snap = m.snapshot()
        self.assertEqual(snap["attention"][0]["key"], "abc123")


if __name__ == "__main__":
    unittest.main()
