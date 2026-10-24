"""Picking several things from one device puts them under ONE system on the main screen, and an install that already has one system per check is tidied."""
import json, os, secrets, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import test_snmp_e2e as T, snmp_fake as F
from monitorbox_app import monconfig as M


class Grouping(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def start_nas(self):
        community = "fake-comm-" + secrets.token_hex(4)
        agent = F.Agent(community=community); self.addCleanup(agent.close)
        agent.mib = T.rows([(1, "/data", 100), (2, "/scratch", 990)])
        c = self.start()
        self.configure(c, [{"id": "nas", "module": "snmp", "name": "Granite", "host": "127.0.0.1", "port": agent.port, "version": "2c",
                            "community": community, "timeout": 1, "retries": 0}], [])
        found = c.post("/api/detect", {"connection": "nas"})
        items = [{k: x.get(k) for k in ("label", "check", "params", "node", "group", "rule") if x.get(k) is not None} for x in found["suggest"] if x.get("default") is not False]
        return c, found, items

    def test_everything_picked_from_one_device_is_one_system_with_a_name(self):
        c, found, items = self.start_nas()
        self.assertGreaterEqual(len(items), 3)
        out = c.post("/api/watch", {"connection": "nas", "items": items})
        self.assertEqual(out["added"], len(items), out)
        nodes = c.get("/api/config/monitoring")["monitoring"]["nodes"]
        self.assertEqual([(n["name"], len(n["checks"])) for n in nodes], [("Granite", len(items))])

    def test_an_install_with_one_system_per_check_is_folded_into_one_on_the_next_apply(self):
        c, found, items = self.start_nas()
        chk = lambda i, it: {"id": M.check_id(it["label"]), "type": "module", "module": "snmp", "connection": "nas", "check": it["check"], "params": it["params"], "label": it["label"]}
        split = [{"id": f"granite-{i}", "name": "Granite", "group": "Servers", "rule": "primary", "checks": [chk(i, it)]} for i, it in enumerate(items)]
        rev = c.get("/api/config/monitoring")["revision"]
        self.assertIn("revision", c.post("/api/config/monitoring", {"monitoring": {"builtinInternet": False, "nodes": split}, "revision": rev}))
        c.post("/api/watch", {"connection": "nas", "items": items[:1]})
        nodes = c.get("/api/config/monitoring")["monitoring"]["nodes"]
        self.assertEqual([(n["name"], len(n["checks"])) for n in nodes], [("Granite", len(items))])

    def test_the_pick_list_describes_each_item_with_what_the_device_reports(self):
        c, found, items = self.start_nas()
        self.assertTrue(found.get("volumes"), "the live values the list shows beside each tick come with the detect answer")
        self.assertIn("usedPercent", found["volumes"][0])
        self.assertIn("sysName", found)                          # what the device calls itself, to name a server that was added by address

    def test_a_connection_in_use_is_refused_until_its_systems_stop_being_watched(self):
        """What Remove this server does: stop watching each of its systems, then drop the connections."""
        c, found, items = self.start_nas()
        c.post("/api/watch", {"connection": "nas", "items": items})
        cur = c.get("/api/config/connections")
        self.assertEqual(c.post("/api/config/connections", {"revision": cur["revision"], "connections": []})["_status"], 400)
        for n in c.get("/api/config/monitoring")["monitoring"]["nodes"]:
            self.assertIn("removed", c.post("/api/stopwatching", {"id": n["id"]}))
        cur = c.get("/api/config/connections")
        self.assertIn("revision", c.post("/api/config/connections", {"revision": cur["revision"], "connections": []}))
        self.assertEqual(c.get("/api/config/monitoring")["monitoring"]["nodes"], [])


class Display(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    def test_the_box_keeps_display_choices_and_refuses_anything_else(self):
        c = self.start()
        self.assertEqual(c.get("/api/display"), {})
        self.assertEqual(c.post("/api/display", {"view": "detail"}), {"view": "detail"})
        self.assertEqual(c.post("/api/display", {"hist": 86400, "dw": 640}), {"view": "detail", "hist": 86400, "dw": 640})
        for bad in ({"view": "huge"}, {"hist": 5}, {"dw": -1}, {"dw": True}, {"colour": "red"}):
            self.assertEqual(c.post("/api/display", bad)["_status"], 400, bad)
        self.assertEqual(c.get("/api/display"), {"view": "detail", "hist": 86400, "dw": 640})

    def test_the_graph_windows_are_kept_and_nothing_longer_than_the_hour_the_box_remembers_is_accepted(self):
        c = self.start()
        self.assertEqual(c.post("/api/display", {"gwin": 900, "gpanel": 1800}), {"gwin": 900, "gpanel": 1800})
        self.assertEqual(c.post("/api/display", {"gpanel": 3600})["gpanel"], 3600, "an hour is the most")
        for bad in ({"gwin": 7200}, {"gpanel": 86400}, {"gpanel": 3601}, {"gwin": 0}, {"gwin": True}, {"gpanel": "15 min"}):
            self.assertEqual(c.post("/api/display", bad)["_status"], 400, bad)
        self.assertEqual(c.get("/api/display"), {"gwin": 900, "gpanel": 3600})

    def test_the_box_keeps_its_own_time_zone_refuses_bad_names_and_display_saves_do_not_lose_it(self):
        c = self.start()
        import time as _t; old = os.environ.get("TZ")                                  # the box sets the process clock zone: put it back afterwards
        def restore():
            os.environ.pop("TZ", None) if old is None else os.environ.__setitem__("TZ", old); _t.tzset()
        self.addCleanup(restore)
        self.assertEqual(c.get("/api/timezone"), {"timezone": ""})
        self.assertEqual(c.post("/api/timezone", {"timezone": "America/Chicago"}), {"timezone": "America/Chicago"})
        c.post("/api/display", {"view": "detail"})                                     # saving a display choice must not drop the zone
        self.assertEqual(c.get("/api/timezone"), {"timezone": "America/Chicago"})
        self.assertEqual(c.get("/api/display"), {"view": "detail"})                    # and the zone is not a display choice
        self.assertEqual(c.post("/api/timezone", {"timezone": "Europe/Berlin"}), {"timezone": "Europe/Berlin"})   # it can be changed later
        for bad in ("", "Mars/Olympus", "../etc/passwd", None, 5):
            self.assertEqual(c.post("/api/timezone", {"timezone": bad})["_status"], 400, bad)
        self.assertEqual(c.get("/api/timezone"), {"timezone": "Europe/Berlin"})

    def test_the_bar_filter_is_kept_validated_and_survives_display_saves_and_the_zone(self):
        c = self.start()
        self.assertEqual(c.get("/api/barshow"), {"show": ["failed", "degraded", "unknown"]})
        self.assertEqual(c.post("/api/barshow", {"show": ["unknown", "failed"]}), {"show": ["failed", "unknown"]})
        c.post("/api/display", {"view": "detail"})
        self.assertEqual(c.get("/api/barshow"), {"show": ["failed", "unknown"]})
        self.assertEqual(c.post("/api/barshow", {"show": []}), {"show": []})                     # none is allowed
        for bad in ("failed", ["healthy"], [1], None):
            self.assertEqual(c.post("/api/barshow", {"show": bad})["_status"], 400, bad)
        self.assertEqual(c.get("/api/barshow"), {"show": []})

    def test_history_events_are_listed_filtered_and_clearing_empties_them(self):
        import time as _t
        c = self.start(); self.configure(c, [], [])
        now = int(_t.time())
        r = c.get(f"/api/history?events=1&from={now - 3600}&to={now + 5}&states=failed,degraded,unknown")
        self.assertIn("items", r); self.assertIn("names", r)
        self.assertEqual(c.post("/api/history/clear", {}), {"cleared": True})
        self.assertEqual(c.get(f"/api/history?events=1&from={now - 3600}&to={now + 5}")["items"], [])
        self.assertEqual(c.get(f"/api/history?events=1&from={now - 3600}&to={now + 5}&brief=1")["items"], [], "asking for brief blips is accepted")

    def test_history_lists_why_a_check_failed_when_the_monitor_recorded_it(self):
        import time as _t
        c = self.start()
        self.configure(c, [], [{"id": "dead", "name": "Nothing here", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": 9}]}])
        c.post("/api/config/monitoring", {"monitoring": {**c.get("/api/config/monitoring")["monitoring"], "confirm": {"failures": 1, "seconds": 0}}, "revision": c.get("/api/config/monitoring")["revision"]})
        def items():
            now = int(_t.time())
            return [x for x in c.get(f"/api/history?events=1&from={now - 3600}&to={now + 5}&states=failed")["items"] if x["node"] == "dead"]
        T.wait(lambda: items(), 30, what="the failed check in the history")
        why = items()[0].get("why", "")
        self.assertEqual(why, "port 9 refused the connection")         # exactly what the check said at the time


if __name__ == "__main__":
    unittest.main()
