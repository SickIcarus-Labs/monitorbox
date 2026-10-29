"""A settings backup holds settings only: no history. Restoring one keeps the box's own history; a full backup carries and restores it (#100).
Every value is different from every other and each is compared after the round trip."""
import io, json, os, shutil, sys, tarfile, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
from monitorbox_launcher import backup  # noqa: E402


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def get(path):
    with open(path) as f:
        return f.read()


class BackupHistory(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mb-hist-")
        put(f"{self.root}/config/monitorbox.json", '{"setting": "alpha-111"}')
        put(f"{self.root}/config/alerts.json", '{"alert": "bravo-222"}')
        put(f"{self.root}/config/history.jsonl", '{"t": 1001, "n": "node-a", "s": "failed"}\n{"t": 1002, "n": "node-b", "s": "healthy"}\n')
        put(f"{self.root}/data/app/auth.json", '{"hash": "charlie-333"}')
        put(f"{self.root}/data/app/other.json", '{"x": "delta-444"}')
        put(f"{self.root}/releases/modules/m/1/file.py", "echo-555")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def names(self, name):
        with tarfile.open(os.path.join(self.root, "backups", name)) as tf:
            return {m.name for m in tf.getmembers()}

    def restore(self, name):
        arch = os.path.join(self.root, "backups", name)
        man = backup.stage(self.root, arch)
        backup.swap(self.root, man)
        return man

    def test_a_settings_backup_has_no_history_and_a_full_one_has_it(self):
        cfg = backup.create(self.root, "config", "manual")
        full = backup.create(self.root, "full", "manual")
        self.assertNotIn("config/history.jsonl", self.names(cfg))
        self.assertIn("config/monitorbox.json", self.names(cfg))
        self.assertIn("config/alerts.json", self.names(cfg))
        self.assertIn("data/app/auth.json", self.names(cfg))
        self.assertIn("config/history.jsonl", self.names(full))

    def test_restoring_a_settings_backup_brings_back_settings_and_keeps_the_boxs_own_history(self):
        cfg = backup.create(self.root, "config", "manual")
        put(f"{self.root}/config/monitorbox.json", '{"setting": "changed-999"}')
        put(f"{self.root}/config/history.jsonl", '{"t": 2001, "n": "node-c", "s": "degraded"}\n')
        self.restore(cfg)
        self.assertEqual(get(f"{self.root}/config/monitorbox.json"), '{"setting": "alpha-111"}')
        self.assertEqual(get(f"{self.root}/config/alerts.json"), '{"alert": "bravo-222"}')
        self.assertEqual(get(f"{self.root}/config/history.jsonl"), '{"t": 2001, "n": "node-c", "s": "degraded"}\n', "the history from before the restore stays")
        self.assertTrue(backup.undo(self.root))
        self.assertEqual(get(f"{self.root}/config/monitorbox.json"), '{"setting": "changed-999"}')
        self.assertEqual(get(f"{self.root}/config/history.jsonl"), '{"t": 2001, "n": "node-c", "s": "degraded"}\n', "undo gives back the original too")

    def test_restoring_a_full_backup_restores_its_history(self):
        full = backup.create(self.root, "full", "manual")
        put(f"{self.root}/config/history.jsonl", '{"t": 3001, "n": "node-d", "s": "failed"}\n')
        self.restore(full)
        self.assertEqual(get(f"{self.root}/config/history.jsonl"), '{"t": 1001, "n": "node-a", "s": "failed"}\n{"t": 1002, "n": "node-b", "s": "healthy"}\n')

    def test_an_older_settings_backup_that_holds_history_still_restores_it(self):
        full = backup.create(self.root, "full", "manual")
        with tarfile.open(os.path.join(self.root, "backups", full)) as tf:                     # make a settings-kind archive the way versions before this one did
            parts = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
        man = json.loads(parts.pop("manifest.json"))
        parts = {k: v for k, v in parts.items() if k.startswith("config/") or k == "data/app/auth.json"}
        man["kind"] = "config"; man["files"] = {k: v for k, v in man["files"].items() if k in parts}
        old = os.path.join(self.root, "backups", "monitorbox-config-20200101-000000-manual.tgz")
        with tarfile.open(old, "w:gz") as tf:
            for name, data in [("manifest.json", json.dumps(man).encode())] + sorted(parts.items()):
                ti = tarfile.TarInfo(name); ti.size = len(data); tf.addfile(ti, io.BytesIO(data))
        put(f"{self.root}/config/history.jsonl", '{"t": 4001, "n": "node-e", "s": "failed"}\n')
        self.restore(os.path.basename(old))
        self.assertIn('"t": 1001', get(f"{self.root}/config/history.jsonl"), "the old backup's own history is what it had")

    def test_a_restore_onto_a_box_without_history_does_not_invent_one(self):
        cfg = backup.create(self.root, "config", "manual")
        os.unlink(f"{self.root}/config/history.jsonl")
        self.restore(cfg)
        self.assertFalse(os.path.exists(f"{self.root}/config/history.jsonl"))

    def test_the_listing_reads_the_start_of_each_archive_and_skips_a_damaged_one(self):
        a = backup.create(self.root, "config", "manual", now=1_700_000_000)
        b = backup.create(self.root, "full", "manual", now=1_700_000_100)
        put(os.path.join(self.root, "backups", "monitorbox-config-broken.tgz"), "not an archive")
        got = backup.list_backups(self.root)
        self.assertEqual([x["name"] for x in got], [b, a])
        self.assertEqual([x["kind"] for x in got], ["full", "config"])
        self.assertTrue(backup.list_backups.fast)

    def test_the_last_backups_timings_are_kept_for_the_performance_report(self):
        backup.create(self.root, "full", "manual")
        t = backup.LAST_TIMING
        self.assertEqual(t["kind"], "full")
        self.assertGreaterEqual(t["files"], 6)
        for k in ("find", "copy", "archive", "prune", "total", "archiveMb"):
            self.assertIn(k, t)


if __name__ == "__main__":
    unittest.main()
