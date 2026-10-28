"""Update all sites: the sites are asked first and not waited for, then this box updates. Made-up site names."""
import json, os, sys, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import peer as peermod, sitesupdate


class Resp:
    def __init__(self, doc, status=200):
        self.doc, self.status = doc, status

    def read(self):
        return json.dumps(self.doc).encode()


class Conn:
    def close(self):
        pass


class FakePeer:
    def __init__(self, sites, answers, log, hold=None):
        self.sites, self.answers, self.log, self.hold = sites, answers, log, hold or {}

    def get(self):
        return {"sites": self.sites}

    def open(self, sid, method, path, headers=None, body_src=None, body_len=0, timeout=60):
        self.log.append(("ask", sid, method, path))
        if sid in self.hold:
            self.hold[sid].wait(10)
        a = self.answers[sid]
        if isinstance(a, Exception):
            raise a
        return Conn(), Resp(*a)


def site(i, name, state="linked"):
    return {"id": i, "name": name, "link": {"state": state}}


def wait_done(su, cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        s = su.status()
        if cond(s):
            return s
        time.sleep(0.01)
    raise AssertionError(su.status())


class Updating(unittest.TestCase):
    def go(self, sites, answers, hold=None, local=None):
        log = []
        local = local or (lambda: log.append(("local",)) or {"message": "Installed App 9.9.9.", "restarting": True})
        su = sitesupdate.SitesUpdate(FakePeer(sites, answers, log, hold), local, grace=0.05)
        return su, log

    def test_sites_are_asked_before_this_box_updates_and_only_linked_ones(self):
        su, log = self.go([site("a", "Harbor"), site("b", "Cabin"), site("c", "Boat", "unreachable")],
                          {"a": ({"message": "Installed App 9.9.9.", "restarting": True},), "b": ({"message": "Nothing needed installing."},)})
        su.start()
        s = wait_done(su, lambda s: not s["running"])
        kinds = [(e[0], e[1]) if e[0] == "ask" else ("local",) for e in log]
        self.assertEqual(kinds[-1], ("local",), "this box goes last")
        self.assertEqual(sorted(k[1] for k in kinds if k[0] == "ask"), ["a", "b"], "the site that is not linked is not asked")
        self.assertTrue(all(e[2:] == ("POST", "/peer/api/apply-all") for e in log if e[0] == "ask"))
        self.assertEqual({r["name"]: r["state"] for r in s["sites"]}, {"Harbor": "restarting", "Cabin": "done"})
        self.assertEqual(s["local"]["state"], "restarting")

    def test_a_slow_site_is_not_waited_for(self):
        gate = threading.Event()
        su, log = self.go([site("a", "Harbor")], {"a": ({"message": "ok"},)}, hold={"a": gate})
        su.start()
        s = wait_done(su, lambda s: s["local"]["state"] in ("done", "restarting"))
        self.assertIn(("local",), log, "this box updated while the site was still busy")
        self.assertEqual(s["sites"][0]["state"], "asking")
        self.assertTrue(s["running"], "still running: the site has not answered")
        gate.set()
        wait_done(su, lambda s: not s["running"])
        self.assertEqual(su.status()["sites"][0]["state"], "done")

    def test_a_site_that_cannot_be_reached_is_named_and_does_not_stop_the_rest(self):
        su, log = self.go([site("a", "Harbor"), site("b", "Cabin")],
                          {"a": peermod.PeerError("Harbor did not answer.", "unknown"), "b": ({"message": "Installed hello 0.3.1."},)})
        su.start()
        s = wait_done(su, lambda s: not s["running"])
        got = {r["name"]: (r["state"], r["message"]) for r in s["sites"]}
        self.assertEqual(got["Harbor"], ("failed", "Harbor did not answer."))
        self.assertEqual(got["Cabin"], ("done", "Installed hello 0.3.1."))
        self.assertIn(("local",), log)

    def test_a_site_that_says_no_is_a_failure_with_its_reason(self):
        su, log = self.go([site("a", "Harbor")], {"a": ({"error": "The container image is out of date."}, 400)})
        su.start()
        s = wait_done(su, lambda s: not s["running"])
        self.assertEqual((s["sites"][0]["state"], s["sites"][0]["message"]), ("failed", "The container image is out of date."))

    def test_this_boxs_own_failure_is_said_and_pressing_again_while_running_is_refused(self):
        gate = threading.Event()
        def bad():
            raise RuntimeError("Could not install: App: no space")
        su, log = self.go([site("a", "Harbor")], {"a": ({"message": "ok"},)}, hold={"a": gate}, local=bad)
        su.start()
        wait_done(su, lambda s: s["local"]["state"] == "failed")
        self.assertEqual(su.status()["local"]["message"], "Could not install: App: no space")
        with self.assertRaises(ValueError):
            su.start()
        gate.set()
        wait_done(su, lambda s: not s["running"])

    def test_with_no_sites_it_just_updates_this_box(self):
        su, log = self.go([], {})
        su.start()
        wait_done(su, lambda s: not s["running"])
        self.assertEqual(log, [("local",)])


if __name__ == "__main__":
    unittest.main()
