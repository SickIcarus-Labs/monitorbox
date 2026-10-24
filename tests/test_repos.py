"""Several release repositories (#265): the list, one repo failing without hurting the others, which repo a module belongs to,
taking over a module only when the other repo offers the very same build, and no module from another repo installing unasked.
The repos are temp directories read through file:// addresses; every value below is made up and different from every other."""
import json, os, shutil, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
from monitorbox_app import server, updates  # noqa: E402
from monitorbox_launcher import backup  # noqa: E402

SHA = {k: (k * 64)[:64] for k in "abcdef"}      # distinct fake archive hashes


def put(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def release_repo(path, modules, app=None):
    """modules: {id: [(version, sha), ...]} newest last; every version is on dev and the newest is the dev pointer's."""
    cat = {"schema": 1, "app": [], "modules": {}}
    ptr = {"schema": 1, "channel": "dev", "app": None, "modules": {}}
    for mid, vs in modules.items():
        ents = [{"version": v, "url": f"file://{path}/{mid}-{v}.tgz", "sha256": s, "channels": ["dev"]} for v, s in vs]
        cat["modules"][mid] = ents
        ptr["modules"][mid] = {k: ents[-1][k] for k in ("version", "url", "sha256")}
    put(os.path.join(path, "catalog.json"), cat)
    put(os.path.join(path, "channels", "dev.json"), ptr)
    for ch in ("beta", "stable"):
        put(os.path.join(path, "channels", f"{ch}.json"), {**ptr, "channel": ch, "modules": {}})


class Repos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mb-repos-")
        self.main, self.test = os.path.join(self.tmp, "main"), os.path.join(self.tmp, "test")
        release_repo(self.main, {"alpha": [("0.1.0", SHA["a"])], "bravo": [("0.2.0", SHA["b"])]})
        release_repo(self.test, {"hello-world": [("1.0.0", SHA["c"])]})
        self.app = server.App(os.path.join(self.tmp, "box"), f"file://{self.main}", "dev", 0)
        self.app.reload_monitoring = lambda: None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add_test_repo(self, rid="owner/test-repo"):
        """What the add box stores, pointed at the temp directory (a real add only takes owner/name on GitHub)."""
        cfg = updates.get_update_cfg(self.app.paths, "dev")
        updates.set_update_cfg(self.app.paths, repos=cfg["repos"] + [{"id": rid, "name": rid, "url": f"file://{self.test}", "enabled": True}])
        return rid

    def install(self, mid, version, sha, source=None):
        st = self.app.modules.state()
        st[mid] = {"active": version, "failed": [], **({"sha256": sha} if sha else {})}
        self.app.modules._save(st)
        if source:
            updates.set_update_cfg(self.app.paths, module_sources={**self.app.cfg()["module_sources"], mid: source})

    # -- the list ---------------------------------------------------------
    def test_default_comes_first_and_others_follow_in_the_order_added(self):
        a = self.add_test_repo("owner/one")
        b = self.add_test_repo("owner/two")
        ids = [r["id"] for r in self.app.repos()]
        self.assertEqual(ids, ["default", a, b])
        self.assertTrue(self.app.repos()[0]["default"])

    def test_adding_takes_only_a_public_github_repo(self):
        for bad in ("", "justaname", "a/b/c", "../x", "http://example.invalid/a/b", "a/..", "a/b; rm -rf /", "file:///tmp/x"):
            with self.assertRaises(ValueError, msg=bad):
                updates.parse_repo(bad)
        self.assertEqual(updates.parse_repo("https://github.com/Some-One/Their_Repo.git")[:2], ("some-one/their_repo", "Some-One/Their_Repo"))
        rid = updates.add_repo(self.app.paths, "Some-One/Their_Repo", self.app.releases_url)
        self.assertEqual(rid, "some-one/their_repo")
        with self.assertRaises(ValueError):
            updates.add_repo(self.app.paths, "some-one/their_repo", self.app.releases_url)      # twice

    def test_the_default_cannot_be_removed_and_a_repo_with_modules_cannot_either(self):
        rid = self.add_test_repo()
        with self.assertRaises(ValueError):
            updates.remove_repo(self.app.paths, "default", self.app.releases_url, self.app.installed_from)
        self.install("hello-world", "1.0.0", SHA["c"], source=rid)
        with self.assertRaises(ValueError) as cm:
            updates.remove_repo(self.app.paths, rid, self.app.releases_url, self.app.installed_from)
        self.assertIn("hello-world", str(cm.exception))
        self.install("hello-world", "1.0.0", SHA["c"], source="default")
        updates.remove_repo(self.app.paths, rid, self.app.releases_url, self.app.installed_from)
        self.assertEqual([r["id"] for r in self.app.repos()], ["default"])

    def test_a_repo_can_be_switched_off_and_on_but_the_default_is_locked(self):
        """(v2 of #264: the default can no longer be switched off or removed.)"""
        rid = self.add_test_repo()
        updates.set_repo_enabled(self.app.paths, rid, False, self.app.releases_url)
        self.assertEqual([(r["id"], r["enabled"]) for r in self.app.repos()], [("default", True), (rid, False)])
        updates.set_repo_enabled(self.app.paths, rid, True, self.app.releases_url)
        self.assertTrue(self.app.repos()[1]["enabled"])
        with self.assertRaises(ValueError):
            updates.set_repo_enabled(self.app.paths, "default", False, self.app.releases_url)
        updates.set_update_cfg(self.app.paths, default_enabled=False)             # an old settings file that switched it off: ignored
        self.assertTrue(self.app.repos()[0]["enabled"])

    def test_a_stored_copy_of_the_default_is_not_shown_twice(self):
        d = updates.default_repo("https://raw.githubusercontent.com/SickIcarus-Labs/monitorbox-modules/main")
        cfg = {"repos": [{"id": d["id"], "name": d["name"], "url": d["url"], "enabled": True}]}
        self.assertEqual([r["id"] for r in updates.repo_list(cfg, d["url"])], ["sickicarus-labs/monitorbox-modules"])

    # -- checking ---------------------------------------------------------
    def test_modules_are_listed_under_the_repo_that_offers_them(self):
        rid = self.add_test_repo()
        self.app.refresh()
        mods = self.app.view()["modules"]
        self.assertEqual({m: c["repo"] for m, c in mods.items()}, {"alpha": "default", "bravo": "default", "hello-world": rid})
        self.assertEqual(mods["hello-world"]["latest"], "1.0.0")
        self.assertFalse(mods["hello-world"]["fromDefault"])

    def test_one_repo_failing_is_said_on_its_own_line_and_the_others_still_work(self):
        rid = self.add_test_repo()
        shutil.rmtree(self.test)
        self.app.refresh()
        v = self.app.view()
        by = {r["id"]: r for r in v["repos"]}
        self.assertIn("Could not reach", by[rid]["error"])
        self.assertIsNone(by["default"]["error"])
        self.assertIsNone(v["checkError"])
        self.assertEqual(v["modules"]["alpha"]["latest"], "0.1.0")

    def test_a_failing_repo_keeps_what_was_last_known_and_never_marks_modules_failed(self):
        rid = self.add_test_repo()
        self.app.refresh()
        self.install("hello-world", "1.0.0", SHA["c"], source=rid)
        shutil.rmtree(self.test)
        self.app.refresh()
        c = self.app.view()["modules"]["hello-world"]
        self.assertEqual((c["running"], c["latest"], c["failed"]), ("1.0.0", "1.0.0", []))       # still known; not Failed
        self.assertEqual(c["repo"], rid)                                                         # and not handed to anyone else

    def test_a_switched_off_repo_is_not_asked_and_its_modules_get_no_offers(self):
        rid = self.add_test_repo()
        self.install("hello-world", "1.0.0", SHA["c"], source=rid)
        updates.set_repo_enabled(self.app.paths, rid, False, self.app.releases_url)
        self.app.refresh()
        v = self.app.view()
        self.assertFalse(v["repos"][1]["checked"])
        c = v["modules"]["hello-world"]
        self.assertEqual((c["running"], c["target"], c["needsApply"], c["repoOn"]), ("1.0.0", None, False, False))

    # -- taking over ------------------------------------------------------
    def test_the_same_build_in_another_repo_takes_over_when_the_old_repo_no_longer_offers_it(self):
        """The forklift: hello-world moves from the default repo to the test repo; settings and pins stay."""
        updates.set_update_cfg(self.app.paths, module_pins={"hello-world": "1.0.0"}, update_note="kept")
        self.install("hello-world", "1.0.0", SHA["c"])             # installed from the default (no source yet)
        rid = self.add_test_repo()
        self.app.refresh()
        self.assertEqual(self.app.sources()["hello-world"], rid)
        self.assertEqual(self.app.view()["modules"]["hello-world"]["repo"], rid)
        self.assertEqual(self.app.cfg()["module_pins"], {"hello-world": "1.0.0"})
        self.assertEqual(self.app.installed_from("default"), [])

    def test_a_different_build_is_never_taken_over_on_its_own(self):
        release_repo(self.test, {"alpha": [("0.1.0", SHA["d"])]})           # same id, same version, other bytes
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        rid = self.add_test_repo()
        shutil.rmtree(os.path.join(self.main, "channels")); os.makedirs(os.path.join(self.main, "channels"))
        release_repo(self.main, {"bravo": [("0.2.0", SHA["b"])]})           # the default stops offering alpha altogether
        self.app.refresh()
        self.assertEqual(self.app.sources()["alpha"], "default")
        with self.assertRaises(ValueError):
            self.app.adopt("alpha", rid)

    def test_the_same_repo_under_a_new_name_takes_everything_over_by_itself(self):
        """The rename: the old address still answers (GitHub redirects it), so both catalogs hold exactly the same builds."""
        shutil.rmtree(self.test)
        shutil.copytree(self.main, self.test)
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        self.install("bravo", "0.2.0", SHA["b"], source="default")
        rid = self.add_test_repo()
        self.app.refresh()
        self.assertEqual(self.app.sources(), {"alpha": rid, "bravo": rid})
        self.assertEqual(self.app.installed_from("default"), [])
        for _ in range(3):                         # and it stays there: identical repos must not hand a module back and forth at every check
            self.app.refresh()
            self.assertEqual(self.app.sources(), {"alpha": rid, "bravo": rid})

    def test_a_module_in_the_later_repo_is_not_pulled_back_to_the_earlier_identical_one(self):
        shutil.rmtree(self.test)
        shutil.copytree(self.main, self.test)
        rid = self.add_test_repo()
        self.install("alpha", "0.1.0", SHA["a"], source=rid)
        self.app.refresh()
        self.assertEqual(self.app.sources()["alpha"], rid)

    def test_a_copy_with_other_builds_is_not_taken_for_the_same_repo(self):
        release_repo(self.test, {"alpha": [("0.1.0", SHA["a"])], "extra": [("9.9.9", SHA["f"])]})     # same alpha, but not the same repo
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        self.add_test_repo()
        self.app.refresh()
        self.assertEqual(self.app.sources()["alpha"], "default")

    def test_nothing_moves_while_the_current_repo_still_offers_the_build(self):
        release_repo(self.test, {"alpha": [("0.1.0", SHA["a"])]})           # a mirror with identical bytes (but not all of its builds)
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        rid = self.add_test_repo()
        self.app.refresh()
        self.assertEqual(self.app.sources()["alpha"], "default")
        self.assertEqual(self.app.view()["modules"]["alpha"]["alsoIn"], [rid])           # offered, one tap away
        self.assertIn("is now updated from", self.app.adopt("alpha", rid)["message"])
        self.assertEqual(self.app.sources()["alpha"], rid)

    def test_identical_repos_offer_no_move_button_to_each_other(self):
        shutil.rmtree(self.test)
        shutil.copytree(self.main, self.test)
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        self.add_test_repo()
        self.app.refresh()
        self.app.refresh()
        self.assertEqual(self.app.view()["modules"]["alpha"]["alsoIn"], [])

    def test_an_unreachable_old_repo_does_not_hand_its_modules_over(self):
        release_repo(self.test, {"alpha": [("0.1.0", SHA["a"])]})
        self.install("alpha", "0.1.0", SHA["a"], source="default")
        self.add_test_repo()
        shutil.rmtree(self.main)
        self.app.refresh()
        self.assertEqual(self.app.sources()["alpha"], "default")

    def test_a_module_installed_before_builds_were_recorded_learns_its_build_from_its_repo(self):
        self.install("alpha", "0.1.0", None)
        self.app.refresh()
        self.assertEqual(self.app.modules.state()["alpha"]["sha256"], SHA["a"])
        self.assertEqual(self.app.cfg()["module_sources"]["alpha"], "default")

    # -- nothing installs itself from a stranger ---------------------------
    def test_automatic_updating_and_update_all_do_not_install_a_new_module_from_another_repo(self):
        rid = self.add_test_repo()
        self.app.refresh()
        installed = []
        self.app.apply = lambda kind, mid=None: installed.append(mid)
        updates.set_update_cfg(self.app.paths, auto_update=True, auto_check=True)
        self.app.refresh = lambda: None
        self.app.auto_step()
        self.assertNotIn("hello-world", installed)
        self.assertEqual(sorted(installed), ["alpha", "bravo"])      # the default repo's behave as before
        installed.clear()
        self.app.apply_all()
        self.assertNotIn("hello-world", installed)
        self.install("hello-world", "0.9.0", SHA["e"], source=rid)    # once installed by the owner, it follows its updates
        self.app.apply_all()
        self.assertIn("hello-world", installed)

    # -- backups carry it ---------------------------------------------------
    def test_backup_and_restore_keep_the_repo_list_and_every_modules_source(self):
        root = self.app.paths.root
        repos = [{"id": f"owner/repo-{n}", "name": f"Owner/Repo-{n}", "url": f"https://raw.githubusercontent.com/Owner/Repo-{n}/main", "enabled": n % 2 == 0} for n in range(4)]
        sources = {f"mod-{n}": repos[n]["id"] for n in range(4)}
        updates.set_update_cfg(self.app.paths, repos=repos, module_sources=sources)
        put(os.path.join(root, "data", "app", "auth.json"), {"x": 1})
        name = backup.create(root, "config", "manual", app_version="0.0.1")
        before = updates.get_update_cfg(self.app.paths, "dev")
        updates.set_update_cfg(self.app.paths, repos=[], module_sources={})
        archive = os.path.join(backup.backups_dir(root), name)
        backup.swap(root, backup.stage(root, archive))
        backup.commit(root)
        after = updates.get_update_cfg(self.app.paths, "dev")
        self.assertEqual(after["repos"], before["repos"])
        self.assertEqual(after["module_sources"], sources)
        self.assertEqual([r["enabled"] for r in after["repos"]], [True, False, True, False])


if __name__ == "__main__":
    unittest.main()
