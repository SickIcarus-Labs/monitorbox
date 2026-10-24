import os, socket, sys, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import liverelay as L

SDP = ("v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:0\r\na=candidate:1 1 udp 2130706431 192.0.2.5 40000 typ host\r\n"
       "a=candidate:2 1 tcp 1 192.0.2.5 9 typ host tcptype passive\r\na=candidate:3 1 udp 1 203.0.113.4 41000 typ srflx raddr 0.0.0.0 rport 0\r\n"
       "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=mid:1\r\na=end-of-candidates\r\n")


class Sdp(unittest.TestCase):
    def test_candidates_are_read_stripped_and_replaced(self):
        self.assertEqual(L.parse_candidates(SDP), [("192.0.2.5", 40000, "host"), ("203.0.113.4", 41000, "srflx")])    # udp only
        self.assertEqual(L.parse_candidate_attr("candidate:7 1 udp 5 192.0.2.9 1234 typ host"), [("192.0.2.9", 1234, "host")])
        self.assertEqual(L.parse_candidates(L.strip_candidates(SDP)), [])
        self.assertNotIn("end-of-candidates", L.strip_candidates(SDP))
        out = L.with_candidate(SDP, "10.0.0.1", 5000)
        self.assertEqual(L.parse_candidates(out), [("10.0.0.1", 5000, "host")] * 2, "one candidate of ours in each media section")
        self.assertNotIn("192.0.2.5", out); self.assertNotIn("203.0.113.4", out)
        self.assertEqual(out.count("m="), 2); self.assertTrue(out.endswith("\r\n"))
        self.assertEqual(L.with_candidate("v=0\r\n", "10.0.0.1", 5000), "v=0\r\n")          # nothing to put it in

    def test_the_target_is_the_hosts_own_address_when_it_offered_one(self):
        cands = [("172.17.0.2", 5, "host"), ("192.0.2.50", 6, "host"), ("203.0.113.4", 7, "srflx"), ("fe80::1", 8, "host")]
        self.assertEqual(L.pick_target(cands, "192.0.2.50"), ("192.0.2.50", 6))
        self.assertEqual(L.pick_target(cands), ("172.17.0.2", 5))
        self.assertEqual(L.pick_target([("203.0.113.4", 7, "srflx")]), ("203.0.113.4", 7))
        self.assertIsNone(L.pick_target([]))

    def test_stun_is_recognised(self):
        self.assertTrue(L.is_stun(b"\x00\x01\x00\x00" + L.STUN_COOKIE + bytes(12)))
        self.assertFalse(L.is_stun(b"\x80" + bytes(30)))


class Pipes(unittest.TestCase):
    def test_two_pipes_carry_packets_both_ways_in_order_and_close_together(self):
        a_sock, b_sock = socket.socketpair()
        a, b = L.Pipe("127.0.0.1"), L.Pipe("127.0.0.1")
        peer_a, peer_b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for s in (peer_a, peer_b):
            s.bind(("127.0.0.1", 0)); s.settimeout(3); self.addCleanup(s.close)
        b.set_target(peer_b.getsockname())                              # b knows where its peer is; a learns it from the first packet
        threading.Thread(target=a.serve, args=(a_sock, True), daemon=True).start()
        threading.Thread(target=b.serve, args=(b_sock, False), daemon=True).start()
        got = []
        deadline = time.time() + 10
        while time.time() < deadline and len(got) < 1:
            peer_a.sendto(b"first", ("127.0.0.1", a.port))
            try:
                got.append(peer_b.recvfrom(2000))
            except socket.timeout:
                pass
        self.assertEqual(got[0][0], b"first"); self.assertEqual(got[0][1][1], b.port)       # arrives from the far pipe's port
        for i in range(50):
            peer_a.sendto(b"p%02d" % i, ("127.0.0.1", a.port))
        self.assertEqual([peer_b.recvfrom(2000)[0] for _ in range(50)], [b"p%02d" % i for i in range(50)], "in order")
        peer_b.sendto(b"x" * 1400, ("127.0.0.1", b.port))                # a full-size packet back the other way
        self.assertEqual(peer_a.recvfrom(2000)[0], b"x" * 1400)
        b.close()
        deadline = time.time() + 5
        while time.time() < deadline and not a.closed.is_set():
            time.sleep(0.1)
        self.assertTrue(a.closed.is_set(), "closing one end closes the other")

    def test_registry_waits_for_a_view_that_is_still_being_opened(self):
        r = L.Registry()
        self.assertIsNone(r.get("x", 0.3), "nothing is opening: no waiting")
        r.begin()
        threading.Timer(0.2, lambda: r.add("x", L.Pipe("127.0.0.1"), "127.0.0.1", "page")).start()
        t = time.time()
        self.assertIsNotNone(r.get("x", 3)); self.assertLess(time.time() - t, 2)
        r.end()


if __name__ == "__main__":
    unittest.main()
