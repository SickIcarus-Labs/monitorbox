"""Making a backup must not read every older backup from start to end (it took 17 s for a 51 KB settings backup on a Pi with full backups)."""
import os, shutil, sys, tarfile, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "launcher"), os.path.join(REPO, "app")]
os.environ.pop("MB_LAUNCHER_PATH", None)
from monitorbox_app import backups  # noqa: E402


class BackupSpeed(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mb-bk-")
        for n in range(8):
            p = os.path.join(self.root, "config", f"file-{n}.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(f'{{"value": "distinct-{n}-{n * 7919}"}}')
        os.makedirs(os.path.join(self.root, "data", "app"), exist_ok=True)
        with open(os.path.join(self.root, "data", "app", "auth.json"), "w") as f:
            f.write('{"x": 1}')
        backups._cache.update(sig=None, list=None)
        backups._rows.clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_new_backup_opens_only_the_new_archive_and_the_list_is_the_same(self):
        b = backups.lib()
        for i in range(4):
            b.create(self.root, "config", "manual", app_version="9.9.9", now=1_700_000_000 + i * 60)
        reads = []
        real = tarfile.TarFile.next
        tarfile.TarFile.next = lambda self: (reads.append(1), real(self))[1]
        try:
            b.create(self.root, "config", "manual", app_version="9.9.9", now=1_700_000_300)
        finally:
            tarfile.TarFile.next = real
        self.assertLessEqual(len(reads), 12, "each of the five archives is opened at its start only: two header reads each (it was 60 members read before)")
        want = sorted(os.listdir(os.path.join(self.root, "backups")))
        got = b.list_backups(self.root)
        self.assertEqual(sorted(x["name"] for x in got), want)
        self.assertEqual([x["created"] for x in got], sorted((x["created"] for x in got), reverse=True))
        self.assertEqual({x["kind"] for x in got}, {"config"})
        self.assertTrue(all(x["appVersion"] == "9.9.9" and x["size"] > 0 for x in got))

    def test_the_automatic_pruning_still_keeps_only_the_newest(self):
        b = backups.lib()
        for i in range(b.KEEP[("config", "auto")] + 3):
            b.create(self.root, "config", "auto", now=1_700_000_000 + i * 60)
        autos = [x for x in b.list_backups(self.root) if x["label"] == "auto"]
        self.assertEqual(len(autos), b.KEEP[("config", "auto")])

    def test_how_long_the_steps_took_reaches_the_slow_list(self):
        from monitorbox_app import perfstats
        b = backups.lib()
        b.create(self.root, "full", "manual")
        old = perfstats.SLOW_MS
        perfstats.SLOW_MS = 0
        try:
            backups.note_timing()
        finally:
            perfstats.SLOW_MS = old
        self.assertTrue(any(x["what"].startswith("full backup, ") and "copy" in x["what"] and len(x["what"]) <= 80 for x in perfstats.slow_calls()), perfstats.slow_calls())


if __name__ == "__main__":
    unittest.main()
