"""Calls to one module may overlap: a slow answer must not hold up a fast one."""
import os, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from monitorbox_app.modules import ModuleProcess  # noqa: E402

SRC = '''
import json, sys, threading, time
out = threading.Lock()
def go(r):
    time.sleep(r["params"].get("sleep", 0))
    with out:
        print(json.dumps({"id": r["id"], "result": {"echo": r["params"].get("tag")}}), flush=True)
for line in sys.stdin:
    threading.Thread(target=go, args=(json.loads(line),)).start()
'''


class Concurrency(unittest.TestCase):
    def test_a_slow_call_does_not_block_a_fast_one(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "m.py"), "w").write(SRC)
        p = ModuleProcess("t", "1", d, ["python3", "m.py"])
        self.addCleanup(p.stop)
        got = {}
        slow = threading.Thread(target=lambda: got.update(slow=p.call("x", {"sleep": 1.5, "tag": "slow"}, 5)))
        slow.start()
        time.sleep(0.2)
        t0 = time.time()
        self.assertEqual(p.call("x", {"tag": "fast"}, 5), {"echo": "fast"})
        self.assertLess(time.time() - t0, 1.0)
        slow.join()
        self.assertEqual(got["slow"], {"echo": "slow"})

    def test_timeout_and_exit(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "m.py"), "w").write(SRC)
        p = ModuleProcess("t", "1", d, ["python3", "m.py"])
        self.addCleanup(p.stop)
        with self.assertRaises(TimeoutError):
            p.call("x", {"sleep": 2}, 0.3)
        p.proc.kill()
        p.proc.wait()
        time.sleep(0.3)
        with self.assertRaises(RuntimeError):
            p.call("x", {}, 1)


if __name__ == "__main__":
    unittest.main()
