import os

DIRS = ["launcher", "releases/app", "releases/modules", "config", "data/app",
        "data/launcher", "backups", "logs"]


class Layout:
    def __init__(self, root):
        self.root = root
        self.p = lambda *a: os.path.join(root, *a)
        self.current = self.p("current")
        self.previous = self.p("previous")
        self.request = self.p("data", "launcher", "request.json")
        self.state = self.p("data", "launcher", "state.json")
        self.log = self.p("logs", "launcher.log")
        self.config_file = self.p("config", "monitorbox.json")

    def ensure(self):
        """Create the folder tree. Raises with a plain message if /config is not writable."""
        for d in DIRS:
            try:
                os.makedirs(self.p(d), exist_ok=True)
            except OSError as e:
                raise SystemExit(
                    f"Cannot create {self.p(d)}: {e.strerror}. "
                    f"The /config volume must be writable by the container user.")
        probe = self.p("data", "launcher", ".probe")
        try:
            with open(probe, "w") as f:
                f.write("ok")
            os.unlink(probe)
        except OSError as e:
            raise SystemExit(f"/config is not writable: {e.strerror}")
