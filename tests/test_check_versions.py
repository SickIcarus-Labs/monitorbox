"""tools/check_versions.py: a changed app or module must carry a new version (regression for the 0.81.5 publish failure)."""
import json, os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import check_versions  # noqa: E402


def run(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd, check=True, capture_output=True)


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


class CheckVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        run(self.r, "init", "-q", "-b", "main")
        write(self.r, "app/monitorbox_app/VERSION", "1.0.0\n")
        write(self.r, "app/monitorbox_app/x.py", "a = 1\n")
        write(self.r, "launcher/monitorbox_launcher/VERSION", "1.0.0\n")
        write(self.r, "launcher/monitorbox_launcher/supervisor.py", "a = 1\n")
        write(self.r, "Dockerfile", "FROM scratch\n")
        for m, v in (("snmp", "0.1.0"), ("nut", "0.3.0")):
            write(self.r, f"modules/{m}/manifest.json", json.dumps({"id": m, "version": v}))
            write(self.r, f"modules/{m}/main.py", "a = 1\n")
        run(self.r, "add", "-A"); run(self.r, "commit", "-q", "-m", "base")
        run(self.r, "checkout", "-q", "-b", "work")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self):
        run(self.r, "add", "-A"); run(self.r, "commit", "-q", "-m", "change")

    def test_nothing_changed(self):
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_module_changed_without_bump_fails_and_names_it(self):
        write(self.r, "modules/snmp/main.py", "a = 2\n"); self.commit()
        p = check_versions.check("main", self.r)
        self.assertEqual(len(p), 1)
        self.assertIn("snmp", p[0])

    def test_a_modules_changelog_alone_needs_no_new_version(self):
        write(self.r, "modules/snmp/CHANGELOG.md", "- **0.1.0** What it does.\n"); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_module_changed_with_bump_passes(self):
        write(self.r, "modules/snmp/main.py", "a = 2\n")
        write(self.r, "modules/snmp/manifest.json", json.dumps({"id": "snmp", "version": "0.1.1"})); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_only_the_changed_module_is_blamed(self):
        write(self.r, "modules/nut/main.py", "a = 2\n"); self.commit()
        p = check_versions.check("main", self.r)
        self.assertEqual(len(p), 1)
        self.assertIn("nut", p[0])

    def test_image_changed_without_a_launcher_bump_fails(self):
        write(self.r, "launcher/monitorbox_launcher/supervisor.py", "a = 2\n"); self.commit()
        p = check_versions.check("main", self.r)
        self.assertEqual(len(p), 1); self.assertIn("launcher/monitorbox_launcher/VERSION", p[0])
        run(self.r, "reset", "-q", "--hard", "main")
        write(self.r, "Dockerfile", "FROM scratch\nRUN true\n"); self.commit()
        self.assertEqual(len(check_versions.check("main", self.r)), 1, "the Dockerfile counts as the image")

    def test_image_changed_with_a_launcher_bump_passes(self):
        write(self.r, "launcher/monitorbox_launcher/supervisor.py", "a = 2\n")
        write(self.r, "launcher/monitorbox_launcher/VERSION", "1.0.1\n"); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_app_changed_without_bump_fails(self):
        write(self.r, "app/monitorbox_app/x.py", "a = 2\n"); self.commit()
        p = check_versions.check("main", self.r)
        self.assertEqual(len(p), 1)
        self.assertIn("VERSION", p[0])

    def test_app_changed_with_bump_passes(self):
        write(self.r, "app/monitorbox_app/x.py", "a = 2\n")
        write(self.r, "app/monitorbox_app/VERSION", "1.0.1\n"); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_docs_tools_and_tests_need_no_bump(self):
        write(self.r, "docs/a.md", "x"); write(self.r, "tools/t.py", "x"); write(self.r, "tests/test_a.py", "x")
        write(self.r, "modules/snmp/tests/test_b.py", "x"); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])

    def test_new_module_needs_nothing_to_compare(self):
        write(self.r, "modules/ping/manifest.json", json.dumps({"id": "ping", "version": "0.1.0"}))
        write(self.r, "modules/ping/main.py", "x"); self.commit()
        self.assertEqual(check_versions.check("main", self.r), [])


if __name__ == "__main__":
    unittest.main()
