"""Listing backups: remembered until the folder changes, each archive read once (however many ask at once), and read from its start only.
Changed on purpose from the version that counted launcher.list_backups calls: the App now reads the manifests itself, because the launcher's
reader loads a whole archive to find the manifest (about 14 s a request on the Pi, which made the first Settings page take 21 s)."""
import io, json, os, sys, tarfile, tempfile, threading, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app")); sys.path.insert(0, os.path.join(ROOT, "launcher"))
from monitorbox_app import backups  # noqa: E402
from monitorbox_launcher import backup as launcher_backup  # noqa: E402


def make(path, created, kind="config", label="manual", ver="9.9.9", payload=b"x" * 1000):
    man = json.dumps({"kind": kind, "label": label, "created": created, "appVersion": ver}).encode()
    with tarfile.open(path, "w:gz") as tf:
        ti = tarfile.TarInfo("manifest.json"); ti.size = len(man); tf.addfile(ti, io.BytesIO(man))
        ti = tarfile.TarInfo("config/data.bin"); ti.size = len(payload); tf.addfile(ti, io.BytesIO(payload))


class Cache(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dir = os.path.join(self.root, "backups"); os.makedirs(self.dir)
        self.reads = []
        self._lib, backups.lib = backups.lib, lambda: launcher_backup
        self._row, real = backups._row, backups._row
        backups._row = lambda root, name, size: (self.reads.append(name), real(root, name, size))[1]
        backups._cache.update(sig=None, list=None); backups._rows.clear()

    def tearDown(self):
        backups.lib, backups._row = self._lib, self._row

    def put(self, name, created="2026-10-19T00:00:00Z", **kw):
        make(os.path.join(self.dir, name), created, **kw)

    def test_the_folder_is_read_once_until_it_changes_and_only_the_new_archive_is_opened(self):
        self.put("monitorbox-config-1.tgz", "2026-10-19T00:00:00Z")
        first = backups.listing(self.root)
        for _ in range(5):
            self.assertEqual(backups.listing(self.root), first)
        self.assertEqual(self.reads, ["monitorbox-config-1.tgz"], "five more looks cost nothing")
        self.put("monitorbox-config-2.tgz", "2026-10-20T00:00:00Z")
        self.assertEqual([b["name"] for b in backups.listing(self.root)], ["monitorbox-config-2.tgz", "monitorbox-config-1.tgz"], "newest first")
        self.assertEqual(self.reads, ["monitorbox-config-1.tgz", "monitorbox-config-2.tgz"], "a new backup is noticed and only it is opened")
        os.unlink(os.path.join(self.dir, "monitorbox-config-1.tgz"))
        self.assertEqual([b["name"] for b in backups.listing(self.root)], ["monitorbox-config-2.tgz"])
        self.put("monitorbox-config-2.tgz", "2026-10-21T00:00:00Z", payload=b"replaced with more bytes" * 50)
        self.assertEqual(backups.listing(self.root)[0]["created"], "2026-10-21T00:00:00Z", "a file replaced under the same name is read again")

    def test_it_gives_exactly_what_the_launcher_gives(self):
        self.put("monitorbox-config-1.tgz", "2026-10-19T00:00:00Z", label="auto", ver="1.2.3")
        self.put("monitorbox-full-2.tgz", "2026-10-20T00:00:00Z", kind="full", label="manual", ver="4.5.6", payload=b"y" * 5000)
        with open(os.path.join(self.dir, "monitorbox-config-3.tgz"), "wb") as f:
            f.write(b"not an archive")
        self.assertEqual(backups.listing(self.root), launcher_backup.list_backups(self.root), "same fields, same order, damaged file skipped")

    def test_only_the_start_of_each_archive_is_read(self):
        self.put("monitorbox-full-1.tgz", payload=os.urandom(200_000))
        p = os.path.join(self.dir, "monitorbox-full-1.tgz")
        with open(p, "r+b") as f:
            f.truncate(os.path.getsize(p) - 30_000)         # the tail is gone: reading the whole archive to find the manifest fails, reading its start does not
        self.assertEqual(launcher_backup.list_backups(self.root), [], "the launcher's reader needs the whole archive")
        self.assertEqual([b["name"] for b in backups.listing(self.root)], ["monitorbox-full-1.tgz"])

    def test_several_requests_at_once_read_each_archive_once(self):
        for i in range(3):
            self.put(f"monitorbox-config-{i}.tgz", f"2026-10-1{i}T00:00:00Z")
        out = []
        ts = [threading.Thread(target=lambda: out.append(backups.listing(self.root))) for _ in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(out), 6); self.assertTrue(all(o == out[0] for o in out))
        self.assertEqual(sorted(self.reads), [f"monitorbox-config-{i}.tgz" for i in range(3)], "six at once, three archives, three reads")

    def test_a_file_still_being_written_does_not_count_and_the_caller_cannot_change_the_kept_list(self):
        self.put("monitorbox-config-1.tgz"); backups.listing(self.root)
        open(os.path.join(self.dir, ".tmp-123.tgz"), "wb").close(); open(os.path.join(self.dir, "notes.txt"), "w").close()
        got = backups.listing(self.root); self.assertEqual(len(self.reads), 1)
        got[0]["name"] = "changed"
        self.assertEqual(backups.listing(self.root)[0]["name"], "monitorbox-config-1.tgz")

    def test_an_empty_or_missing_folder_is_an_empty_list(self):
        os.rmdir(self.dir)
        self.assertEqual(backups.listing(self.root), [])


if __name__ == "__main__":
    unittest.main()
