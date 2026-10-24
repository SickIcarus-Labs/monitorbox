"""A box nobody has chosen a channel for follows stable (#118): the launcher, the App and the example compose file all say so."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def text(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


class DefaultChannel(unittest.TestCase):
    def test_launcher_and_app_default_to_stable(self):
        for p in (("launcher", "monitorbox_launcher", "__main__.py"), ("app", "monitorbox_app", "__main__.py")):
            self.assertIn('os.environ.get("MB_CHANNEL", "stable")', text(*p), p)
        self.assertIn('channel="stable"', text("launcher", "monitorbox_launcher", "supervisor.py"))

    def test_the_example_compose_file_leaves_the_channel_to_the_default_and_the_welcome_page(self):
        compose = text("deploy", "docker-compose.yml")
        self.assertNotRegex(compose, r"(?m)^\s*MB_CHANNEL:\s*(dev|beta)\b", "a stranger's compose must not pin a test channel")

    def test_a_chosen_channel_still_wins_over_the_default(self):
        import sys, tempfile, json
        sys.path.insert(0, os.path.join(ROOT, "app"))
        from monitorbox_app import updates
        class P:  # just the one path the config reader needs
            config = os.path.join(tempfile.mkdtemp(), "monitorbox.json")
        self.assertEqual(updates.get_update_cfg(P, "stable")["channel"], "stable")
        with open(P.config, "w") as f:
            json.dump({"update": {"channel": "beta"}}, f)
        self.assertEqual(updates.get_update_cfg(P, "stable")["channel"], "beta")


if __name__ == "__main__":
    unittest.main()
