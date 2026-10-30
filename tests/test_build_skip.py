"""tools/build_release.py --skip: a module published elsewhere is left out of the catalog and the pointer (hello moved to the test repo, #264)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "build_release.py")


class Skip(unittest.TestCase):
    def build(self, *extra, changelog=None, module_log=None, catalog=None):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = os.path.join(tmp.name, "src")
        os.makedirs(os.path.join(root, "app", "monitorbox_app"))
        with open(os.path.join(root, "app", "monitorbox_app", "VERSION"), "w") as f:
            f.write("1.0.0\n")
        os.makedirs(os.path.join(root, "launcher", "monitorbox_launcher"))
        with open(os.path.join(root, "launcher", "monitorbox_launcher", "VERSION"), "w") as f:
            f.write("3.4.5\n")
        for mid in ("kept", "left-out"):
            os.makedirs(os.path.join(root, "modules", mid))
            with open(os.path.join(root, "modules", mid, "manifest.json"), "w") as f:
                json.dump({"id": mid, "version": "0.1.0", "entry": ["python3", "main.py"]}, f)
            with open(os.path.join(root, "modules", mid, "main.py"), "w") as f:
                f.write("pass\n")
        if changelog is not None:
            with open(os.path.join(root, "CHANGELOG.md"), "w") as f:
                f.write(changelog)
        if module_log is not None:
            with open(os.path.join(root, "modules", "kept", "CHANGELOG.md"), "w") as f:
                f.write(module_log)
        ptr, cat = os.path.join(tmp.name, "dev.json"), os.path.join(tmp.name, "catalog.json")
        with open(ptr, "w") as f:
            json.dump({"schema": 1, "channel": "dev", "app": None, "modules": {}}, f)
        with open(cat, "w") as f:
            json.dump(catalog or {"schema": 1, "app": [], "modules": {}}, f)
        r = subprocess.run([sys.executable, BUILD, "--root", root, "--out", os.path.join(tmp.name, "dist"), "--skip-node-packages",
                            "--url-template", "https://example.invalid/{file}", "--pointer", ptr, "--catalog", cat, *extra], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.load(open(ptr)), json.load(open(cat)), json.loads(r.stdout)

    def test_a_skipped_module_is_not_built_or_listed(self):
        ptr, cat, out = self.build("--skip", "left-out")
        self.assertEqual(sorted(ptr["modules"]), ["kept"])
        self.assertEqual(sorted(cat["modules"]), ["kept"])
        self.assertFalse(any("left-out" in a for a in out["assets"]))

    def test_without_skip_everything_is_built(self):
        ptr, cat, out = self.build()
        self.assertEqual(sorted(ptr["modules"]), ["kept", "left-out"])

    def test_the_pointer_carries_the_launcher_version_this_release_was_built_for(self):
        ptr, cat, out = self.build()
        self.assertEqual(ptr["launcher"], {"version": "3.4.5"})

    def test_the_catalog_entry_carries_that_versions_changelog_lines_without_the_ticket_number(self):
        log = ("# Changelog\n\n## Not on stable yet\n\n- **1.0.1** (#12) A later thing.\n- **1.0.0** (#7, #8) First thing, in plain words.\n"
               "- **1.0.0** Second thing with no ticket.\n- **1.0.10** Not this one.\n")
        ptr, cat, out = self.build(changelog=log)
        self.assertEqual(cat["app"][0]["changes"], ["First thing, in plain words.", "Second thing with no ticket."])
        self.assertNotIn("changes", cat["modules"]["kept"][0], "a module with no CHANGELOG.md has no notes (the app's changelog is not its)")

    MODULE_LOG = "# Kept changelog\n\nIntro text that is not a version line.\n\n- **0.1.1** A later thing.\n- **0.1.0** What the module does, in plain words.\n"

    def test_a_modules_own_changelog_goes_into_its_catalog_entry_and_not_into_its_archive(self):
        ptr, cat, out = self.build(module_log=self.MODULE_LOG)
        self.assertEqual(cat["modules"]["kept"][0]["changes"], ["What the module does, in plain words."])
        self.assertNotIn("changes", cat["modules"]["left-out"][0])

    def test_only_the_modules_own_changelog_stays_out_of_the_archive(self):
        """Regression (1.9.4 publish failed): every changelog was left out, including the ones inside a module's node packages, so the Scrypted archive no longer
        matched the published one."""
        import importlib.util, io, tarfile
        spec = importlib.util.spec_from_file_location("br", BUILD); br = importlib.util.module_from_spec(spec); spec.loader.exec_module(br)
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "node_modules", "pkg"))
        for rel in ("CHANGELOG.md", "main.py", os.path.join("node_modules", "pkg", "CHANGELOG.md")):
            with open(os.path.join(d, rel), "w") as f:
                f.write("x\n")
        names = tarfile.open(fileobj=io.BytesIO(br.make_tgz(d)), mode="r:gz").getnames()
        self.assertIn("main.py", names)
        self.assertNotIn("CHANGELOG.md", names, "the module's own notes are not shipped")
        self.assertIn(os.path.join("node_modules", "pkg", "CHANGELOG.md"), names, "a package's own file is")

    def test_notes_added_after_a_version_was_published_reach_it_without_a_new_version(self):
        ptr, cat1, out1 = self.build()
        sha = cat1["modules"]["kept"][0]["sha256"]
        ptr, cat2, out2 = self.build(module_log=self.MODULE_LOG, catalog=cat1)     # same version, same archive, the notes only now exist
        self.assertEqual(cat2["modules"]["kept"][0]["sha256"], sha, "the archive is unchanged: a note never needs a new version")
        self.assertEqual(cat2["modules"]["kept"][0]["changes"], ["What the module does, in plain words."])

    def test_notes_already_published_are_left_as_they_were(self):
        ptr, cat1, out1 = self.build(module_log=self.MODULE_LOG)
        edited = self.MODULE_LOG.replace("What the module does, in plain words.", "Reworded later.")
        ptr, cat2, out2 = self.build(module_log=edited, catalog=cat1)
        self.assertEqual(cat2["modules"]["kept"][0]["changes"], ["What the module does, in plain words."])

    def test_no_changelog_lines_means_no_changes_field(self):
        ptr, cat, out = self.build(changelog="# Changelog\n")
        self.assertNotIn("changes", cat["app"][0])
        ptr, cat, out = self.build()
        self.assertNotIn("changes", cat["app"][0])

    def test_a_highlight_tag_is_taken_off_the_line_and_its_short_sentence_goes_in_highlights(self):
        log = ("# Changelog\n\n- **1.0.0** (#7) [highlight: The short sentence.] The long full sentence, in plain words.\n"
               "- **1.0.0** An unmarked line.\n")
        ptr, cat, out = self.build(changelog=log)
        self.assertEqual(cat["app"][0]["changes"], ["The long full sentence, in plain words.", "An unmarked line."])
        self.assertEqual(cat["app"][0]["highlights"], ["The short sentence."])

    def test_no_highlight_means_no_highlights_field(self):
        ptr, cat, out = self.build(changelog="# Changelog\n\n- **1.0.0** Plain.\n")
        self.assertNotIn("highlights", cat["app"][0])

    def test_highlights_marked_later_reach_an_already_published_entry_and_nothing_else_changes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("br", BUILD)
        br = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(br)
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        with open(os.path.join(root, "CHANGELOG.md"), "w") as f:
            f.write("- **1.0.0** [highlight: Short.] Long.\n- **0.9.0** Old, unmarked.\n")
        old = {"version": "1.0.0", "url": "u", "sha256": "fake-sha-1", "changes": ["Long."]}
        keep = {"version": "0.9.0", "url": "v", "sha256": "fake-sha-2", "changes": ["Old, unmarked."]}
        entries = [old, keep]
        br.backfill_highlights(entries, root)
        self.assertEqual(old, {"version": "1.0.0", "url": "u", "sha256": "fake-sha-1", "changes": ["Long."], "highlights": ["Short."]})
        self.assertEqual(keep, {"version": "0.9.0", "url": "v", "sha256": "fake-sha-2", "changes": ["Old, unmarked."]})


if __name__ == "__main__":
    unittest.main()
