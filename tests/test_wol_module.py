"""The wol module on its own: the exact bytes it puts on the wire, MAC handling, and #11's point:
replacing a system's MACs changes who gets woken."""
import importlib.util, os, socket, sys, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("wol_main", os.path.join(REPO, "modules", "wol", "main.py"))
wol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wol)


class Listener:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("127.0.0.1", 0))
        self.s.settimeout(2)
        self.port = self.s.getsockname()[1]

    def got(self, n):
        return [self.s.recvfrom(512)[0] for _ in range(n)]

    def close(self):
        self.s.close()


class Wol(unittest.TestCase):
    def setUp(self):
        self.l = Listener()
        self.addCleanup(self.l.close)

    def send(self, macs, **kw):
        return wol.wake({"macs": macs, "broadcast": "127.0.0.1", "port": self.l.port, **kw})

    def test_magic_packet_bytes(self):
        self.assertEqual(self.send(["aa:bb:cc:dd:ee:01"]), {"sent": 1})
        (pkt,) = self.l.got(1)
        self.assertEqual(len(pkt), 102)
        self.assertEqual(pkt[:6], b"\xff" * 6)
        self.assertEqual(pkt[6:], bytes.fromhex("aabbccddee01") * 16)

    def test_every_mac_gets_its_own_packet(self):
        macs = ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02", "aa:bb:cc:dd:ee:03"]
        self.assertEqual(self.send(macs)["sent"], 3)
        self.assertEqual([p[6:12].hex() for p in self.l.got(3)], ["aabbccddee01", "aabbccddee02", "aabbccddee03"])

    def test_replacing_the_macs_changes_who_is_woken(self):
        self.send(["aa:bb:cc:dd:ee:01"])
        old = self.l.got(1)[0]
        self.send(["11:22:33:44:55:66"])        # the new server's card
        new = self.l.got(1)[0]
        self.assertNotEqual(old, new)
        self.assertEqual(new[6:12].hex(), "112233445566")
        self.assertNotIn(bytes.fromhex("aabbccddee01"), new)

    def test_mac_spellings(self):
        for spelling in ("AA:BB:CC:DD:EE:01", "aa-bb-cc-dd-ee-01", "aabb.ccdd.ee01", "aabbccddee01"):
            self.assertEqual(wol.normalize(spelling), "aa:bb:cc:dd:ee:01")

    def test_bad_macs_send_nothing(self):
        for bad in (["aa:bb:cc:dd:ee"], ["zz:bb:cc:dd:ee:01"], ["aa:bb:cc:dd:ee:01", "nope"], [], None, "aa:bb:cc:dd:ee:01"):
            with self.assertRaises(ValueError, msg=bad):
                self.send(bad)
        self.l.s.settimeout(0.3)
        with self.assertRaises(socket.timeout):    # nothing at all went out, not even for the good first MAC
            self.l.s.recvfrom(512)


if __name__ == "__main__":
    unittest.main()
