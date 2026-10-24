"""Wake on LAN end to end (real launcher, App and wol module). A fake machine listens for magic packets and
only comes up (opens a TCP port) when a packet carries ITS MAC, so a wrong or stale MAC cannot pass.
This is #11: replace a server's MACs in the app, press Wake, the machine wakes and is reported reachable."""
import os, shutil, socket, threading, time, unittest

import test_e2e as base

Client, wait = base.Client, base.wait
PASSWORD = "correct horse"
GOOD_MAC, OLD_MAC = "02:11:22:33:44:55", "02:aa:bb:cc:dd:ee"


class FakeMachine:
    """Off until it receives a magic packet for its MAC; then a TCP port opens (it 'booted')."""
    def __init__(self, mac):
        self.mac = bytes.fromhex(mac.replace(":", ""))
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(0.2)
        self.udp_port = self.udp.getsockname()[1]
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        self.tcp_port = probe.getsockname()[1]
        probe.close()
        self.up, self.packets, self.stop = False, [], False
        self.srv = None
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.stop:
            try:
                pkt, _ = self.udp.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                return
            self.packets.append(pkt)
            if pkt == b"\xff" * 6 + self.mac * 16 and not self.up:
                self.srv = socket.socket()
                self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.srv.bind(("127.0.0.1", self.tcp_port))
                self.srv.listen(8)
                self.up = True

    def close(self):
        self.stop = True
        for s in (self.udp, self.srv):
            if s:
                s.close()


class Wake(unittest.TestCase):
    setUp, tearDown = base.E2E.setUp, base.E2E.tearDown
    write_json, read_json = staticmethod(base.E2E.write_json), staticmethod(base.E2E.read_json)
    publish = base.E2E.publish

    def boot(self, with_wol=True):
        if not with_wol:
            shutil.rmtree(os.path.join(self.src, "modules", "wol"))
        self.publish(app="0.8.0", hello="0.3.0")
        base.E2E.start_launcher(self)
        c = Client(self.port)
        wait(lambda: c.get("/api/health")["version"], what="App up")
        self.assertTrue(c.post("/api/setup", {"password": PASSWORD})["ok"])
        self.assertTrue(c.post("/api/login", {"password": PASSWORD})["ok"])
        if with_wol:
            wait(lambda: any(m["id"] == "wol" and m["running"] for m in c.get("/api/state")["modules"]), what="wol module running")
        return c

    def machine(self):
        m = FakeMachine(GOOD_MAC)
        self.addCleanup(m.close)
        return m

    def save(self, c, m, macs, **wake):
        rev = c.get("/api/config/monitoring")["revision"]
        node = {"id": "granite", "name": "Granite", "group": "Servers", "critical": True,
                "checks": [{"type": "tcp", "target": "127.0.0.1", "port": m.tcp_port}],
                "wake": {"macs": macs, "broadcast": "127.0.0.1", "port": m.udp_port, "timeout": 20, "retry": 3, **wake}}
        return c.post("/api/config/monitoring", {"monitoring": {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [node]}, "revision": rev})

    def wake_state(self, c, want, timeout=30):
        def look():
            w = c.get("/api/status")["wakes"].get("granite")
            return w if w and w["state"] == want else None
        return wait(look, timeout=timeout, what=f"wake state {want}")

    def test_replace_the_macs_in_the_app_then_wake(self):
        m = self.machine()
        c = self.boot()
        self.assertIn("revision", self.save(c, m, [OLD_MAC], timeout=5, retry=2))  # the config still has the OLD server's MAC
        wait(lambda: c.get("/api/status")["nodes"]["granite"]["state"] == "failed", what="machine shows down")
        self.assertTrue(c.get("/api/status")["nodes"]["granite"]["canWake"])

        # wake with the stale MAC: packets go out, nothing wakes, the app says so and what to check
        self.assertIn(c.post("/api/wake", {"id": "granite"})["state"], ("sending", "waiting"))
        w = self.wake_state(c, "timeout", timeout=40)
        self.assertIn("MAC addresses", w["detail"])
        self.assertFalse(m.up)
        self.assertTrue(m.packets)
        self.assertTrue(all(p[6:12] == bytes.fromhex(OLD_MAC.replace(":", "")) for p in m.packets))  # it used the configured MAC

        # replace the MAC in the app (the whole point of #11) and press Wake
        self.assertIn("revision", self.save(c, m, [GOOD_MAC]))
        c.post("/api/wake", {"id": "granite"})
        w = self.wake_state(c, "up")
        self.assertIn("is up", w["detail"])
        self.assertTrue(m.up)
        self.assertEqual(c.get("/api/status")["nodes"]["granite"]["state"], "healthy")

    def test_a_system_without_wake_settings_and_bad_settings_are_refused(self):
        m = self.machine()
        c = self.boot()
        rev = c.get("/api/config/monitoring")["revision"]
        c.post("/api/config/monitoring", {"revision": rev, "monitoring": {"confirm": {"failures": 1, "seconds": 0}, "builtinInternet": False, "nodes": [
            {"id": "granite", "name": "Granite", "group": "Servers", "checks": [{"type": "tcp", "target": "127.0.0.1", "port": m.tcp_port}]}]}})
        self.assertEqual(c.post("/api/wake", {"id": "granite"})["_status"], 400)
        self.assertEqual(c.post("/api/wake", {"id": "nope"})["_status"], 400)
        bad = self.save(c, m, ["not-a-mac"])
        self.assertEqual(bad["_status"], 400)
        self.assertIn("not a MAC", " ".join(bad["errors"]))

    def test_without_the_wol_module_it_says_so_plainly(self):
        m = self.machine()
        c = self.boot(with_wol=False)
        self.save(c, m, [GOOD_MAC])
        c.post("/api/wake", {"id": "granite"})
        w = self.wake_state(c, "error")
        self.assertIn("wol module is not running", w["detail"])
        self.assertFalse(m.up)

    def test_pressing_wake_twice_does_not_start_two_wakes(self):
        m = self.machine()
        c = self.boot()
        self.save(c, m, [OLD_MAC], timeout=8, retry=30)
        c.post("/api/wake", {"id": "granite"})
        c.post("/api/wake", {"id": "granite"})
        c.post("/api/wake", {"id": "granite"})
        self.wake_state(c, "timeout", timeout=40)
        self.assertEqual(len(m.packets), 1)     # one send for the whole attempt (retry is longer than the timeout)


if __name__ == "__main__":
    unittest.main()
