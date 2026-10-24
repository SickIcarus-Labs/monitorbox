"""tools/build_release.py --skip: a module published elsewhere is left out of the catalog and the pointer (hello moved to the test repo, #264)."""
import json, os, subprocess, sys, tempfile, unittest

BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "build_release.py")


class Skip(unittest.TestCase):
    def build(self, *extra):
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
        ptr, cat = os.path.join(tmp.name, "dev.json"), os.path.join(tmp.name, "catalog.json")
        with open(ptr, "w") as f:
            json.dump({"schema": 1, "channel": "dev", "app": None, "modules": {}}, f)
        with open(cat, "w") as f:
            json.dump({"schema": 1, "app": [], "modules": {}}, f)
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


if __name__ == "__main__":
    unittest.main()
