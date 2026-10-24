import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import alerts, engine  # noqa: E402

HOOK = "http://ha.example.invalid:8123/api/webhook/fake-hook-id-1"
HOOK2 = "http://ha2.example.invalid:8123/api/webhook/fake-hook-id-2"


def node(i, name, deps=(), expected=False, kind=None, children=()):
    n = {"id": i, "name": name, "group": "Servers", "critical": False, "checks": [{"id": "c", "type": "ping", "target": "x"}],
         "rule": "primary", "dependsOn": list(deps)}
    if expected:
        n["expectedDown"] = True
    return n


def snap(nodes, **res):
    r = {f"{k}/c": {"ok": v, "detail": "no answer" if v is False else "", "ms": 1, "at": "t", "since": "t"} for k, v in res.items()}
    return engine.evaluate(nodes, r, "t")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sent, self.fail = [], None
        self.now = 1000.0
        self.a = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                               send=self.send, clock=lambda: self.now, hostname=lambda: "box-host")
        self.a.set({"enabled": True, "homeAssistant": {"webhook": HOOK}, "delaySeconds": 60})

    def send(self, url, ev):
        if self.fail:
            return self.fail
        self.sent.append((url, ev))
        return None

    def go(self, s, secs=0):
        self.now += secs
        ev = self.a.observe(s, self.now)
        self.a.flush(self.now)
        return ev

    NODES = [node("a", "Anchor3"), node("b", "Granite")]

    def test_a_problem_is_announced_only_after_the_delay(self):
        bad = snap(self.NODES, a=False, b=True)
        self.assertEqual(self.go(bad), [])
        self.assertEqual(self.go(bad, 59), [])
        self.assertEqual(len(self.go(bad, 2)), 1)
        url, ev = self.sent[0]
        self.assertEqual(url, HOOK)
        self.assertEqual((ev["event"], ev["state"], ev["name"], ev["site"]), ("problem", "failed", "Anchor3", "box-host"))
        self.assertEqual(ev["title"], "box-host: Anchor3 is down")
        self.assertEqual(self.go(bad, 600), [])             # once, not every few seconds

    def test_a_blip_that_clears_in_time_sends_nothing(self):
        self.go(snap(self.NODES, a=False, b=True))
        self.go(snap(self.NODES, a=True, b=True), 30)
        self.go(snap(self.NODES, a=True, b=True), 200)
        self.assertEqual(self.sent, [])

    def test_recovery_follows_once_it_stays_healthy(self):
        bad, good = snap(self.NODES, a=False, b=True), snap(self.NODES, a=True, b=True)
        self.go(bad); self.go(bad, 61)
        self.assertEqual(self.go(good, 5), [])
        self.assertEqual(self.go(good, 10), [])
        ev = self.go(good, 30)
        self.assertEqual([e["event"] for e in ev], ["recovered"])
        self.assertEqual(self.sent[-1][1]["title"], "box-host: Anchor3 is back")
        self.assertEqual(self.go(good, 300), [])

    def test_degraded_alerts_and_a_change_to_down_updates(self):
        deg = engine.evaluate([{**self.NODES[0], "checks": [{"id": "c", "type": "ping", "target": "x"}, {"id": "d", "type": "tcp", "target": "x", "port": 1}]}],
                              {"a/c": {"ok": True, "detail": "", "ms": 1, "at": "t", "since": "t"},
                               "a/d": {"ok": False, "detail": "port closed", "ms": 1, "at": "t", "since": "t"}}, "t")
        self.assertEqual(deg["nodes"]["a"]["state"], "degraded")
        self.go(deg); self.go(deg, 61)
        self.assertEqual(self.sent[-1][1]["state"], "degraded")
        down = snap(self.NODES, a=False, b=True)
        self.go(down); self.go(down, 61)
        self.assertEqual([e["state"] for _u, e in self.sent], ["degraded", "failed"])

    def test_unknown_never_alerts_and_does_not_count_as_back(self):
        bad, unk = snap(self.NODES, a=False, b=True), snap(self.NODES, a=None, b=True)
        self.assertEqual(unk["nodes"]["a"]["state"], "unknown")
        self.go(unk); self.go(unk, 500)
        self.assertEqual(self.sent, [])
        self.go(bad); self.go(bad, 61)
        n = len(self.sent)
        self.go(unk, 5); self.go(unk, 500)
        self.assertEqual(len(self.sent), n)                 # could not look: no all-clear
        self.go(snap(self.NODES, a=True, b=True), 5); self.go(snap(self.NODES, a=True, b=True), 40)
        self.assertEqual(self.sent[-1][1]["event"], "recovered")

    def test_expected_down_and_dependents_stay_quiet_and_one_alert_per_root_cause(self):
        nodes = [node("sw", "Switch"), node("srv", "Server", deps=["sw"]), node("nas", "NAS", expected=True)]
        s = snap(nodes, sw=False, srv=False, nas=False)
        self.go(s); self.go(s, 61)
        self.assertEqual([e["name"] for _u, e in self.sent], ["Switch"])
        self.assertIn("Server", self.sent[0][1]["message"])   # what it takes with it

    def test_marking_a_problem_expected_closes_it_silently(self):
        bad = snap(self.NODES, a=False, b=True)
        self.go(bad); self.go(bad, 61)
        n = len(self.sent)
        quiet = snap([{**self.NODES[0], "expectedDown": True}, self.NODES[1]], a=False, b=True)
        self.go(quiet, 5); self.go(quiet, 500)
        self.assertEqual(len(self.sent), n)

    def test_off_means_nothing_and_turning_on_announces_what_is_wrong_then(self):
        self.a.set({"enabled": False})
        bad = snap(self.NODES, a=False, b=True)
        self.go(bad); self.go(bad, 500)
        self.assertEqual(self.sent, [])
        self.a.set({"enabled": True})
        self.go(bad); self.go(bad, 61)
        self.assertEqual(len(self.sent), 1)

    def test_restart_does_not_announce_the_same_problem_twice(self):
        bad = snap(self.NODES, a=False, b=True)
        self.go(bad); self.go(bad, 61)
        again = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                              send=self.send, clock=lambda: self.now)
        self.now += 5
        again.observe(bad, self.now); again.flush(self.now)
        self.now += 500
        again.observe(bad, self.now); again.flush(self.now)
        self.assertEqual(len(self.sent), 1)

    def test_a_failed_delivery_is_kept_and_retried_then_reported(self):
        bad = snap(self.NODES, a=False, b=True)
        self.fail = "nothing is listening at that address and port"
        self.go(bad); self.go(bad, 61)
        self.assertEqual(self.sent, [])
        g = self.a.get()
        self.assertEqual((g["waiting"], g["last"]["ok"]), (1, False))
        self.go(bad, 2)
        self.assertEqual(self.sent, [])                    # backing off
        self.fail = None
        self.go(bad, 10)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.a.get()["waiting"], 0)
        self.assertTrue(self.a.get()["last"]["ok"])

    def test_waiting_messages_survive_a_restart(self):
        bad = snap(self.NODES, a=False, b=True)
        self.fail = "could not connect"
        self.go(bad); self.go(bad, 61)
        again = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                              send=self.send, clock=lambda: self.now)
        self.fail = None
        again.flush(self.now + 60)
        self.assertEqual(len(self.sent), 1)

    def test_gives_up_after_half_an_hour(self):
        bad = snap(self.NODES, a=False, b=True)
        self.fail = "could not connect"
        self.go(bad); self.go(bad, 61)
        for _ in range(8):
            self.go(bad, 300)
        self.assertEqual(self.a.get()["waiting"], 0)


class Settings(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = os.path.join(self.d, "alerts.json")
        self.a = alerts.Alerts(self.cfg, os.path.join(self.d, "state.json"), lambda: None, send=lambda u, e: None, hostname=lambda: "box-host")

    def test_the_owner_can_read_the_address_back_and_it_is_kept_when_not_sent_again(self):
        self.a.set({"homeAssistant": {"webhook": HOOK}, "site": "Bay Harbor"})
        g = self.a.get()
        self.assertEqual({k: g["homeAssistant"][k] for k in ("set", "host", "webhook", "connected")}, {"set": True, "host": "ha.example.invalid:8123", "webhook": HOOK, "connected": False})
        self.a.set({"delaySeconds": 30})
        self.assertTrue(self.a.get()["homeAssistant"]["set"])
        with open(self.cfg) as f:
            self.assertEqual(json.load(f)["homeAssistant"]["webhook"], HOOK)
        self.assertEqual(oct(os.stat(self.cfg).st_mode & 0o777), "0o600")
        self.a.set({"homeAssistant": {"webhook": HOOK2}})
        with open(self.cfg) as f:
            self.assertEqual(json.load(f)["homeAssistant"]["webhook"], HOOK2)
        self.a.set({"homeAssistant": {"webhook": ""}})
        self.assertEqual({k: self.a.get()["homeAssistant"][k] for k in ("set", "host", "webhook")}, {"set": False, "host": "", "webhook": ""})

    def test_a_trailing_space_pasted_with_the_address_is_dropped_even_as_percent_20(self):
        for pasted in (HOOK + " ", "  " + HOOK + "\n", HOOK + "%20", HOOK + "%20%20", HOOK + "%20 "):
            self.a.set({"homeAssistant": {"webhook": pasted}})
            self.assertEqual(self.a.get()["homeAssistant"]["webhook"], HOOK, repr(pasted))
        self.a.set({"homeAssistant": {"webhook": "%20"}})
        self.assertFalse(self.a.get()["homeAssistant"]["set"])

    def test_bad_input_is_refused_with_a_plain_reason(self):
        for body in ({"homeAssistant": {"webhook": "ftp://x/y"}}, {"homeAssistant": {"webhook": "not a url"}},
                     {"delaySeconds": -1}, {"delaySeconds": 99999}, {"delaySeconds": "60"}, {"enabled": True}, "x"):
            with self.assertRaises(alerts.Invalid, msg=str(body)):
                self.a.set(body)

    def test_site_name_defaults_to_the_host_name(self):
        self.assertEqual(self.a.get()["siteDefault"], "box-host")

    def test_test_button_reports_what_happened_without_the_address(self):
        self.assertFalse(self.a.test()["ok"])
        self.a.set({"homeAssistant": {"webhook": HOOK}})
        got = []
        self.a.send = lambda u, e: got.append((u, e)) or None
        r = self.a.test()
        self.assertTrue(r["ok"])
        self.assertEqual((got[0][1]["event"], got[0][1]["title"]), ("test", "box-host: test alert"))
        self.a.send = lambda u, e: "nothing is listening at that address and port"
        r = self.a.test()
        self.assertFalse(r["ok"])
        self.assertNotIn("fake-hook-id-1", r["message"])


class RealSend(unittest.TestCase):
    def test_posts_json_to_a_real_listener_and_explains_failures(self):
        import http.server, threading
        got = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                code = 404 if self.path.endswith("missing") else 200
                self.send_response(code); self.end_headers()

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        self.assertIsNone(alerts.post_json(f"http://127.0.0.1:{port}/api/webhook/fake-id-9", {"title": "t"}))
        self.assertEqual(got[0], ("/api/webhook/fake-id-9", {"title": "t"}))
        self.assertIn("404", alerts.post_json(f"http://127.0.0.1:{port}/missing", {"a": 1}))
        srv.shutdown(); srv.server_close()
        why = alerts.post_json(f"http://127.0.0.1:{port}/api/webhook/fake-id-9", {"a": 1}, timeout=2)
        self.assertIn("nothing is listening", why)
        self.assertNotIn("fake-id-9", why)


def ups_snap(detail, warn=True, others=()):
    """A UPS node (the NUT module's check) plus other nodes, the UPS saying `detail`."""
    ups = {"id": "ups", "name": "Rack UPS", "group": "Power", "critical": True, "checks": [{"id": "c", "type": "ups", "module": "nut", "check": "ups"}], "rule": "primary", "dependsOn": []}
    res = {"ups/c": {"ok": True, "warn": warn, "detail": detail, "ms": 1, "at": "t", "since": "t"}}
    nodes = [ups]
    for i, ok in others:
        nodes.append(node(i, i.upper()))
        res[f"{i}/c"] = {"ok": ok, "detail": "no answer" if ok is False else "", "ms": 1, "at": "t", "since": "t"}
    return engine.evaluate(nodes, res, "t")


class Storms(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sent = []
        self.now = 1000.0
        self.a = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                               send=lambda url, ev: self.sent.append(ev), clock=lambda: self.now, hostname=lambda: "box-host")
        self.a.set({"enabled": True, "homeAssistant": {"webhook": HOOK}, "delaySeconds": 60})
        self.nodes = [node(i, n) for i, n in (("a", "Anchor3"), ("b", "Granite"), ("c", "Switch-Two"), ("d", "Camera-Four"), ("e", "Plex"))]

    def go(self, s, secs=0):
        self.now += secs
        ev = self.a.observe(s, self.now)
        self.a.flush(self.now)
        return ev

    def state(self, **ok):
        return snap(self.nodes, **{k: ok.get(k, True) for k in "abcde"})

    def test_three_problems_within_a_minute_are_one_message_and_one_all_clear(self):
        down = self.state(a=False, b=False, c=False, d=False)
        self.go(down); self.go(down, 20)
        ev = self.go(down, 45)
        self.assertEqual([(e["event"], e["id"], e["count"]) for e in ev], [("problem", "storm", 4)])
        self.assertEqual(ev[0]["title"], "box-host: 4 things went down at once")
        for n in ("Anchor3", "Granite", "Switch-Two", "Camera-Four"):
            self.assertIn(n, ev[0]["message"])
        self.assertEqual(self.go(down, 200), [], "not repeated, and not one by one")
        up = self.state()
        self.assertEqual(self.go(up, 5), [])
        ev = self.go(up, 40)
        self.assertEqual([(e["event"], e["id"]) for e in ev], [("recovered", "storm")], "one all-clear, not four")
        self.assertEqual(ev[0]["title"], "box-host: everything is back")
        self.assertEqual(len(self.sent), 2)

    def test_two_problems_are_still_announced_one_by_one(self):
        down = self.state(a=False, b=False)
        self.go(down)
        ev = self.go(down, 61)
        self.assertEqual(sorted(e["id"] for e in ev), ["a", "b"])

    def test_a_storm_that_mostly_clears_before_the_delay_falls_back_to_the_ordinary_message_for_what_is_left(self):
        self.go(self.state(a=False, b=False, c=False))
        self.go(self.state(a=False), 30)
        self.assertEqual(self.go(self.state(a=False), 31), [])         # the storm dissolves here
        ev = self.go(self.state(a=False), 1)
        self.assertEqual([(e["event"], e["id"]) for e in ev], [("problem", "a")])

    def test_a_late_arrival_joins_quietly_and_one_update_follows_when_the_storm_settles(self):
        self.go(self.state(a=False, b=False, c=False))
        self.assertEqual([e["id"] for e in self.go(self.state(a=False, b=False, c=False), 61)], ["storm"])
        late = self.state(a=False, b=False, c=False, d=False)
        self.assertEqual(self.go(late, 60), [], "no message of its own")
        self.assertEqual(self.go(late, 100), [])
        ev = self.go(late, 201)
        self.assertEqual([(e["event"], e["id"], e["count"]) for e in ev], [("problem", "storm", 4)])
        self.assertIn("Camera-Four", ev[0]["message"])

    def test_a_ups_on_battery_is_announced_at_once_and_is_not_swallowed_by_a_storm(self):
        s = ups_snap("on battery · 100%", others=[("a", False), ("b", False), ("c", False)])
        ev = self.go(s)
        self.assertEqual([(e["id"], e.get("urgent")) for e in ev], [("ups", True)], "no waiting for the delay")
        self.assertEqual(ev[0]["title"], "box-host: Rack UPS is running on battery")
        ev = self.go(s, 61)
        self.assertEqual([e["id"] for e in ev], ["storm"])
        self.assertNotIn("Rack UPS", ev[0]["message"])

    def test_a_ups_that_is_merely_degraded_for_another_reason_waits_like_anything_else(self):
        s = ups_snap("replace battery")
        self.assertEqual(self.go(s), [])
        self.assertEqual([e["id"] for e in self.go(s, 61)], ["ups"])

    def test_the_words_that_make_a_ups_urgent_are_the_nut_modules_own(self):
        import importlib.util
        mod = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "nut")
        sys.path.insert(0, mod)
        try:
            spec = importlib.util.spec_from_file_location("nut_main_for_alerts", os.path.join(mod, "main.py"))
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        finally:
            sys.path.remove(mod)
        for w in alerts.URGENT:
            self.assertIn(w, m.STATUS_WORDS.values())

    def test_a_thing_that_keeps_going_down_is_one_message_then_one_when_it_is_steady(self):
        down, up = self.state(a=False), self.state()
        evs = []
        for _ in range(2):                                                  # two ordinary down/back pairs
            self.go(down); evs += self.go(down, 61); evs += self.go(up, 5); evs += self.go(up, 40)
        self.assertEqual([e["event"] for e in evs], ["problem", "recovered", "problem", "recovered"])
        self.go(down); ev = self.go(down, 61)
        self.assertEqual([(e["event"], e.get("flapping")) for e in ev], [("problem", True)])
        self.assertIn("keeps going down", ev[0]["title"])
        evs = self.go(up, 5) + self.go(up, 40) + self.go(down, 10) + self.go(down, 61) + self.go(up, 5) + self.go(up, 40)
        self.assertEqual(evs, [], "quiet while it flaps")
        ev = self.go(up, 700)
        self.assertEqual([(e["event"], e["id"]) for e in ev], [("recovered", "a")])
        self.assertIn("steady again", ev[0]["title"])

    def test_a_ups_on_battery_is_never_flap_damped(self):
        on, ok = ups_snap("on battery"), ups_snap("online", warn=False)
        titles = []
        for _ in range(5):
            titles += [e["title"] for e in self.go(on)] + [e["title"] for e in self.go(ok, 5)] + [e["title"] for e in self.go(ok, 40)]
        self.assertEqual(titles.count("box-host: Rack UPS is running on battery"), 5)
        self.assertFalse([t for t in titles if "keeps going down" in t])

    def test_a_storm_survives_a_restart_without_being_announced_again(self):
        down = self.state(a=False, b=False, c=False)
        self.go(down); self.go(down, 61)
        again = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                              send=lambda url, ev: self.sent.append(ev), clock=lambda: self.now, hostname=lambda: "box-host")
        self.assertEqual(again.observe(down, self.now + 30), [])
        self.assertEqual([e["event"] for e in again.observe(self.state(), self.now + 100)], [])
        self.assertEqual([e["id"] for e in again.observe(self.state(), self.now + 140)], ["storm"])


def power_snap(ups, a, b=True):
    """The rack UPS (`ups`: 'battery', 'unknown', 'online'), Anchor3 powered by it, and Camera (not on it). a / b: is each up?"""
    u = {"id": "ups", "name": "Rack UPS", "group": "Power", "critical": False, "checks": [{"id": "c", "type": "ups", "module": "nut", "check": "ups"}], "rule": "primary", "dependsOn": []}
    res = {"ups/c": {"battery": {"ok": True, "warn": True, "detail": "on battery, 80%"}, "unknown": {"ok": None, "detail": "cannot reach the NUT server"},
                     "online": {"ok": True, "detail": "online"}}[ups] | {"ms": 1, "at": "t", "since": "t"}}
    nodes = [u, {**node("a", "Anchor3"), "poweredBy": ["ups"]}, node("b", "Camera")]
    for i, ok in (("a", a), ("b", b)):
        res[f"{i}/c"] = {"ok": ok, "detail": "no answer" if ok is False else "", "ms": 1, "at": "t", "since": "t"}
    return engine.evaluate(nodes, res, "t")


class PowerHold(Storms):
    def test_a_system_on_a_ups_that_announced_battery_does_not_alert_when_it_goes_down_even_after_the_ups_goes_quiet(self):
        ev = self.go(power_snap("battery", True))
        self.assertEqual([e["id"] for e in ev], ["ups"])
        self.go(power_snap("battery", False), 120)                                   # it shuts itself down on purpose
        self.go(power_snap("unknown", False, True), 300)                              # and takes the UPS's NUT server with it
        self.assertEqual(self.go(power_snap("unknown", False, True), 300), [], "nothing for Anchor3, though it is down and the UPS reads Unknown")
        self.go(power_snap("unknown", False, False), 1)
        self.assertEqual([e["id"] for e in self.go(power_snap("unknown", False, False), 61)], ["b"], "the camera is not on that UPS: its trouble is its own")

    def test_the_hold_ends_a_grace_after_the_ups_is_healthy_again_so_a_system_that_never_comes_back_does_alert(self):
        self.go(power_snap("battery", True))
        self.go(power_snap("unknown", False), 600)
        self.assertEqual(self.go(power_snap("online", False), 5), [])
        self.assertEqual([e["event"] for e in self.go(power_snap("online", False), 40)], ["recovered"], "the UPS is back")
        self.assertEqual(self.go(power_snap("online", False), 300), [], "still booting: inside the grace")
        self.assertEqual(self.go(power_snap("online", False), 400), [], "the hold ends here; the system's own delay starts now")
        self.assertEqual([e["id"] for e in self.go(power_snap("online", False), 61)], ["a"])

    def test_a_system_that_boots_in_time_never_alerts_and_the_hold_survives_a_restart(self):
        self.go(power_snap("battery", True))
        self.go(power_snap("unknown", False), 300)
        again = alerts.Alerts(os.path.join(self.d, "alerts.json"), os.path.join(self.d, "state.json"), lambda: None,
                              send=lambda url, ev: self.sent.append(ev), clock=lambda: self.now, hostname=lambda: "box-host")
        self.now += 100
        self.assertEqual(again.observe(power_snap("unknown", False), self.now), [])


if __name__ == "__main__":
    unittest.main()
