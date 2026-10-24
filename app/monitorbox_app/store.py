"""Paths, atomic JSON files, and the minimal config the App owns in M1."""
import json, os, tempfile


class Paths:
    def __init__(self, root):
        self.root = root
        self.p = lambda *a: os.path.join(root, *a)
        self.config = self.p("config", "monitorbox.json")
        self.auth = self.p("data", "app", "auth.json")
        self.auth_keep = self.p("data", "app", "auth.keep")
        self.reset_flag = self.p("config", "factory-reset")
        self.modules_state = self.p("data", "app", "modules.json")
        self.request = self.p("data", "launcher", "request.json")
        self.module_releases = self.p("releases", "modules")


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj, mode=0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
