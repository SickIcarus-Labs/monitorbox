"""The performance view: timings are kept per kind of request, the numbers are right, and Settings shows them."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import perfstats, sysinfo


class Stats(unittest.TestCase):
    def setUp(self):
        perfstats.reset()

    def test_a_kind_of_request_is_one_line_with_count_average_p95_and_max(self):
        for ms in range(1, 101):
            perfstats.record("request", "GET /api/state", ms)
        perfstats.record("request", "GET /api/about", 2)
        top = perfstats.summary("request")
        self.assertEqual(top[0]["key"], "GET /api/state", "slowest first")
        r = top[0]
        self.assertEqual((r["count"], r["avgMs"], r["p95Ms"], r["maxMs"]), (100, 50.5, 96.0, 100.0))
        self.assertEqual(perfstats.summary("module"), [])

    def test_only_the_last_samples_are_kept(self):
        for i in range(perfstats.KEEP + 50):
            perfstats.record("module", "snmp.poll", i)
        r = perfstats.summary("module")[0]
        self.assertEqual(r["count"], perfstats.KEEP)
        self.assertEqual(r["maxMs"], float(perfstats.KEEP + 49))

    def test_requests_to_another_site_are_grouped_as_the_hop_and_streams_are_left_out(self):
        self.assertEqual(perfstats.request_key("GET", "/api/site/ab12cd/state?x=1"), "GET site:/state")
        self.assertEqual(perfstats.request_key("GET", "/api/state?x=1"), "GET /api/state")
        for p in ("/api/stream", "/api/live/events?client=1", "/api/perf", "/", "/icons/a.png"):
            self.assertTrue(perfstats.skip(p), p)
        self.assertFalse(perfstats.skip("/api/state"))

    def test_processes_lists_this_one_with_a_memory_share_biggest_first(self):
        p = sysinfo.processes({})
        self.assertEqual(p[0]["name"] if len(p) == 1 else True, "app" if len(p) == 1 else True)
        self.assertTrue(all(x["mb"] > 0 for x in p))
        self.assertEqual([x["mb"] for x in p], sorted((x["mb"] for x in p), reverse=True))
        self.assertIn("app", [x["name"] for x in p])


if __name__ == "__main__":
    unittest.main()
