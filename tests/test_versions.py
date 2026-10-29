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

    def test_image_notice_only_when_both_versions_are_known_and_the_image_is_older(self):
        self.assertEqual(versions.image("1.0.0", "1.0.1"), {"have": "1.0.0", "wants": "1.0.1", "outdated": True})
        self.assertEqual(versions.image("1.9.0", "1.10.0")["outdated"], True)          # numbers, not text
        self.assertEqual(versions.image("1.0.1", "1.0.1")["outdated"], False)
        self.assertEqual(versions.image("2.0.0", "1.0.1")["outdated"], False)          # a newer image is never a problem
        self.assertIsNone(versions.image(None, "1.0.1"))                               # image from before the version was recorded
        self.assertIsNone(versions.image("1.0.0", None))                               # release that does not say
        self.assertIsNone(versions.image("junk", "1.0.1"))

    def test_prerelease_sorts_before_release(self):
        self.assertLess(versions.vkey("1.0.0-beta.1"), versions.vkey("1.0.0"))
        self.assertGreater(versions.vkey("1.0.0"), versions.vkey("0.83.22"))   # the jump to 1.0 is an upgrade, not a downgrade
        self.assertGreater(versions.vkey("0.84.0"), versions.vkey("0.83.22"))


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


class WhatChanged(unittest.TestCase):
    def ent(self, v, *notes):
        return {"version": v, "channels": ["dev"], **({"changes": list(notes)} if notes else {})}

    def test_an_update_lists_every_version_after_the_running_one_up_to_the_target_newest_first(self):
        es = [self.ent("1.0.0", "old"), self.ent("1.0.1", "a"), self.ent("1.0.2", "b", "c"), self.ent("1.0.10", "d"), self.ent("1.0.11", "too new")]
        got = versions.whats_changed(es, "1.0.0", "1.0.10")
        self.assertEqual([(g["version"], g["changes"]) for g in got], [("1.0.10", ["d"]), ("1.0.2", ["b", "c"]), ("1.0.1", ["a"])], "numeric order, not text order")

    def test_versions_without_notes_are_left_out(self):
        es = [self.ent("1.0.0"), self.ent("1.0.1"), self.ent("1.0.2", "b")]
        self.assertEqual([g["version"] for g in versions.whats_changed(es, "1.0.0", "1.0.2")], ["1.0.2"])

    def test_when_up_to_date_it_shows_the_running_versions_own_notes(self):
        es = [self.ent("1.0.0", "x"), self.ent("1.0.1", "y")]
        self.assertEqual([g["version"] for g in versions.whats_changed(es, "1.0.1", "1.0.1")], ["1.0.1"])
        self.assertEqual(versions.whats_changed(es, "1.0.1", None), versions.whats_changed(es, "1.0.1", "1.0.1"))

    def test_bad_input_gives_nothing_rather_than_an_error(self):
        self.assertEqual(versions.whats_changed([{"version": "x"}], "1.0.0", "1.0.1"), [])
        self.assertEqual(versions.whats_changed([], None, None), [])


class Highlights(unittest.TestCase):
    """The short version of a long update (#320). Made-up notes."""

    def log(self, n, marked):
        return [{"version": f"1.0.{i}", "channels": ["dev"], "changes": [f"full {i}"], **({"highlights": [f"short {i}"]} if i in marked else {})} for i in range(n + 1)]

    def test_a_big_jump_gets_only_the_marked_sentences_newest_first(self):
        got = versions.highlights(self.log(30, {3, 12, 25}), "1.0.0", "1.0.30")
        self.assertEqual(got, [{"version": "1.0.25", "text": "short 25"}, {"version": "1.0.12", "text": "short 12"}, {"version": "1.0.3", "text": "short 3"}])

    def test_a_small_jump_has_no_short_version(self):
        self.assertEqual(versions.highlights(self.log(5, {2}), "1.0.0", "1.0.5"), [])
        self.assertEqual(versions.highlights(self.log(versions.BIG_JUMP, {2}), "1.0.0", f"1.0.{versions.BIG_JUMP}"), [], "exactly the limit is still small")
        self.assertEqual(len(versions.highlights(self.log(versions.BIG_JUMP + 1, {2}), "1.0.0", f"1.0.{versions.BIG_JUMP + 1}")), 1)

    def test_a_big_jump_with_nothing_marked_shows_everything_as_before(self):
        self.assertEqual(versions.highlights(self.log(30, set()), "1.0.0", "1.0.30"), [])

    def test_bad_input_gives_nothing(self):
        self.assertEqual(versions.highlights([{"version": "x"}], "1.0.0", "1.0.30"), [])
        self.assertEqual(versions.highlights([], None, None), [])


class WhatChangedAcrossABigJump(unittest.TestCase):
    """A simulated release log: someone on stable jumps many versions at once (1.4.2 to 1.8.3). Made-up notes."""

    def log(self):
        es = [{"version": "1.4.2", "channels": ["dev", "beta", "stable"]}]      # what they run: published before notes travelled with releases
        for minor in range(5, 9):
            for patch in range(0, 12 if minor < 8 else 4):
                v = f"1.{minor}.{patch}"
                es.append({"version": v, "channels": ["dev"], **({"changes": [f"{v} first thing.", f"{v} second thing."]} if (minor, patch) != (6, 3) else {})})
        return es

    def test_every_version_with_notes_is_listed_newest_first_in_numeric_order(self):
        got = versions.whats_changed(self.log(), "1.4.2", "1.8.3")
        wanted = [e["version"] for e in self.log() if e["version"] != "1.4.2" and e["version"] != "1.6.3"]
        self.assertEqual([g["version"] for g in got], sorted(wanted, key=versions.vkey, reverse=True))
        self.assertEqual(got[0]["version"], "1.8.3")
        self.assertEqual(got[-1]["version"], "1.5.0")
        self.assertNotIn("1.6.3", [g["version"] for g in got], "a version that shipped without notes is simply absent")
        self.assertGreater(len(got), 30, "more than the old cap of 30: a long jump is not cut short")

    def test_only_versions_up_to_the_target_are_listed(self):
        got = versions.whats_changed(self.log(), "1.4.2", "1.6.5")
        self.assertEqual(got[0]["version"], "1.6.5")
        self.assertTrue(all(versions.vkey(g["version"]) <= versions.vkey("1.6.5") for g in got))

    def test_the_numbers_are_numbers_so_1_6_10_is_after_1_6_9(self):
        es = [{"version": "1.6.9", "channels": ["dev"], "changes": ["nine"]}, {"version": "1.6.10", "channels": ["dev"], "changes": ["ten"]}, {"version": "1.6.2", "channels": ["dev"]}]
        self.assertEqual([g["version"] for g in versions.whats_changed(es, "1.6.2", "1.6.10")], ["1.6.10", "1.6.9"])
