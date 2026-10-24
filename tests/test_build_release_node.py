"""A module with Node packages ships them inside its archive: installed from the lock file at build time, the same every time, and a failed
install stops the publish. A fake npm stands in for the real one (the real registry is not needed to prove the wiring)."""
import hashlib, json, os, stat, subprocess, sys, tarfile, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, "tools", "build_release.py")


class NodePackages(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mb-brn-")
        def w(p, t):
            os.makedirs(os.path.dirname(os.path.join(self.d, p)), exist_ok=True)
            with open(os.path.join(self.d, p), "w") as f:
                f.write(t)
        w("root/app/monitorbox_app/VERSION", "9.9.9\n")
        w("root/modules/demo/manifest.json", json.dumps({"id": "demo", "version": "1.0.0", "entry": ["node", "main.mjs"]}))
        w("root/modules/demo/main.mjs", "console.log('hi')\n")
        w("root/modules/demo/package.json", "{}\n")
        w("root/modules/demo/package-lock.json", "{}\n")
        w("rel/channels/dev.json", json.dumps({"schema": 1, "channel": "dev", "modules": {}}))
        w("rel/catalog.json", "{}\n")
        self.npm = os.path.join(self.d, "fake-npm")
        w("fake-npm", "#!/bin/sh\n[ \"$1\" = ci ] || exit 2\n[ -f package-lock.json ] || exit 3\nmkdir -p node_modules/dep && echo 'export const x = 1' > node_modules/dep/index.js\n")
        os.chmod(self.npm, os.stat(self.npm).st_mode | stat.S_IEXEC)

    def build(self, out, *extra, npm=None):
        env = dict(os.environ, MB_NPM=npm or self.npm)
        return subprocess.run([sys.executable, BUILD, "--root", os.path.join(self.d, "root"), "--out", os.path.join(self.d, out), "--url-template", "file://x/{file}",
                               "--pointer", os.path.join(self.d, "rel/channels/dev.json"), "--catalog", os.path.join(self.d, "rel/catalog.json"), *extra],
                              capture_output=True, text=True, env=env)

    def names(self, out):
        with tarfile.open(os.path.join(self.d, out, "module-demo-1.0.0.tar.gz")) as t:
            return sorted(t.getnames())

    def test_packages_are_installed_into_the_archive_the_same_every_time(self):
        r = self.build("a"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("node_modules/dep/index.js", self.names("a"))
        self.assertIn("package-lock.json", self.names("a"))
        def sha(out):
            with open(os.path.join(self.d, out, "module-demo-1.0.0.tar.gz"), "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        first = sha("a")
        with open(os.path.join(self.d, "rel/catalog.json"), "w") as f:
            f.write("{}\n")
        with open(os.path.join(self.d, "rel/channels/dev.json"), "w") as f:
            json.dump({"schema": 1, "channel": "dev", "modules": {}}, f)
        r = self.build("b"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sha("b"), first, "the same lock file must give the same archive")

    def test_skipping_leaves_them_out_and_a_failed_install_stops_the_build(self):
        r = self.build("c", "--skip-node-packages"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("node_modules/dep/index.js", self.names("c"))
        broken = os.path.join(self.d, "broken-npm")
        with open(broken, "w") as f:
            f.write("#!/bin/sh\necho nope >&2\nexit 1\n")
        os.chmod(broken, 0o755)
        r = self.build("d", npm=broken)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("npm ci failed", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
