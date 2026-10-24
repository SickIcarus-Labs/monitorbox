import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import versions  # noqa: E402


def e(v, ch):
    return {"version": v, "channels": ch}


ENTRIES = [e("0.1.0", ["dev", "beta", "stable"]), e("0.2.0", ["dev", "beta"]), e("0.3.0", ["dev"]), e("0.10.0", ["dev"])]


class VersionTests(unittest.TestCase):
    def test_channel_visibility(self):
        names = lambda ch: [x["version"] for x in versions.offered(ENTRIES, ch)]
        self.assertEqual(names("stable"), ["0.1.0"])
        self.assertEqual(names("beta"), ["0.2.0", "0.1.0"])
        self.assertEqual(names("dev"), ["0.10.0", "0.3.0", "0.2.0", "0.1.0"])  # numeric order, not text

    def test_latest_and_pin(self):
        c = versions.component("0.1.0", "latest", "0.2.0", ENTRIES, "beta", [])
        self.assertEqual((c["target"], c["needsApply"]), ("0.2.0", True))
        c = versions.component("0.2.0", "0.1.0", "0.2.0", ENTRIES, "beta", [])
        self.assertEqual((c["target"], c["needsApply"], c["latest"]), ("0.1.0", True, "0.2.0"))
        c = versions.component("0.1.0", "0.3.0", "0.2.0", ENTRIES, "beta", [])  # 0.3.0 is dev only
        self.assertEqual((c["target"], c["pinMissing"]), (None, True))

    def test_prerelease_sorts_before_release(self):
        self.assertLess(versions.vkey("1.0.0-beta.1"), versions.vkey("1.0.0"))


if __name__ == "__main__":
    unittest.main()


class PageTests(unittest.TestCase):
    def test_page_reloads_itself_when_the_app_version_changes(self):
        # Found on the Pi: after an update the open tab kept running the old page's code.
        from monitorbox_app.ui import PAGE
        self.assertIn("window.__v!==h.version", PAGE)
        self.assertIn("location.reload()", PAGE)


class FreshTests(unittest.TestCase):
    def test_web_urls_bypass_the_five_minute_cache_but_file_urls_are_untouched(self):
        # Found on the Pi: Check now missed a release published two minutes earlier.
        from monitorbox_app import updates
        self.assertRegex(updates.fresh("https://raw.example/x/catalog.json"), r"catalog\.json\?t=\d+$")
        self.assertEqual(updates.fresh("file:///tmp/x/catalog.json"), "file:///tmp/x/catalog.json")


class SysinfoTests(unittest.TestCase):
    def test_reports_numbers_and_never_raises(self):
        from monitorbox_app import sysinfo
        a = sysinfo.about()
        self.assertGreater(a["appMb"], 1)
        self.assertGreater(a["processesTotalMb"], 1)
        self.assertGreaterEqual(a["uptimeSeconds"], 0)
        self.assertIn("containerMb", a)               # None where the cgroup file is not readable

    def test_missing_proc_files_give_none_not_a_crash(self):
        from monitorbox_app import sysinfo
        self.assertIsNone(sysinfo._rss_mb(99999999))
        self.assertEqual(sysinfo._children(99999999), [])


class MemoryShare(unittest.TestCase):
    def test_a_process_is_counted_by_its_fair_share_not_its_whole_footprint(self):
        from monitorbox_app import sysinfo
        me = os.getpid()
        pss, rss = sysinfo._pss_mb(me), None
        with open(f"/proc/{me}/status") as f:
            rss = round(int(next(l for l in f if l.startswith("VmRSS:")).split()[1]) / 1024, 1)
        self.assertIsNotNone(pss); self.assertGreater(pss, 0); self.assertLessEqual(pss, rss + 0.1)
        self.assertEqual(sysinfo._rss_mb(me), pss, "the reported figure is the fair share")
        self.assertIsNone(sysinfo._pss_mb(2 ** 22 + 12345), "a process that is not there gives nothing, and the caller falls back to RSS")
