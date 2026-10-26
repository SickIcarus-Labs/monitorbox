"""The page's script must parse. A single clash of names (two `const live`) once made the whole page blank; this says so at once, with the line,
where the browser tests would only time out. Skipped where Node is not installed."""
import os, re, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app import ui  # noqa: E402


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class PageScript(unittest.TestCase):
    def test_the_page_script_parses(self):
        scripts = re.findall(r"<script>(.*?)</script>", ui.PAGE, re.S)
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as d:
            for i, js in enumerate(scripts):
                f = os.path.join(d, f"page{i}.js")
                with open(f, "w") as fh:
                    fh.write(js)
                r = subprocess.run(["node", "--check", f], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[:600])


class Wording(unittest.TestCase):
    def test_the_busiest_card_does_not_call_the_network_wired_only(self):
        # the busiest-client card watches wifi devices too, so its quiet message must not say "wired" (found on the first day of 1.0)
        self.assertIn("The network is quiet", ui.PAGE)
        self.assertNotIn("wired LAN is quiet", ui.PAGE)


if __name__ == "__main__":
    unittest.main()
