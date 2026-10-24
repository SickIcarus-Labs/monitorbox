"""NUT module: UPS states, discovery, and the guarantee that it never controls the UPS."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "nut"))
from nut_fake import Upsd  # noqa: E402
import nutlib as N  # noqa: E402
import main as M  # noqa: E402


def ups(status="OL", charge=100, load=23, runtime=2460, desc="Eaton 5S"):
    return {"desc": desc, "vars": {"ups.status": status, "battery.charge": str(charge), "ups.load": str(load), "battery.runtime": str(runtime)}}


class Nut(unittest.TestCase):
    def setUp(self):
        self.d = Upsd({"networkups": ups(), "qnapups": ups(desc='QNAP "TS" UPS')})
        self.addCleanup(self.d.close)
        self.conn = {"host": "127.0.0.1", "port": self.d.port, "timeout": 1}

    def check(self, name="networkups", **p):
        return M.check_ups({"ups": name, **p}, self.conn)

    def test_online_and_readable_detail(self):
        r = self.check()
        self.assertEqual(r["state"], "healthy", r)
        self.assertEqual(r["detail"], "online · battery 100% · load 23% · 41 min runtime")

    def test_every_status_that_matters(self):
        cases = [("OL CHRG", 60, 20, 2000, "healthy"), ("OB DISCHRG", 90, 20, 2000, "degraded"), ("OL RB", 100, 20, 2000, "degraded"),
                 ("OL", 100, 85, 2000, "degraded"), ("OL", 40, 20, 2000, "degraded"), ("OL", 100, 20, 120, "degraded"),
                 ("OB LB", 10, 20, 100, "failed"), ("FSD", 10, 20, 100, "failed"), ("OL BYPASS", 100, 20, 2000, "degraded")]
        for status, ch, load, rt, want in cases:
            self.d.ups["networkups"] = ups(status, ch, load, rt)
            self.assertEqual(self.check()["state"], want, (status, ch, load, rt))

    def test_thresholds_can_be_changed(self):
        self.d.ups["networkups"] = ups("OL", 100, 85, 2000)
        self.assertEqual(self.check(load_warn=90)["state"], "healthy")

    def test_unreachable_stale_and_unknown_names_are_unknown_never_failed(self):
        self.d.stale.add("qnapups")
        self.assertEqual(self.check("qnapups")["state"], "unknown")
        r = self.check("nosuch")
        self.assertEqual(r["state"], "unknown")
        self.assertIn("networkups", r["detail"])               # says what does exist
        self.assertEqual(M.check_ups({}, self.conn)["state"], "unknown")   # no ups name given
        with self.assertRaises(N.NutError):                      # main.py turns this into state=unknown
            M.check_ups({"ups": "networkups"}, {"host": "127.0.0.1", "port": 1, "timeout": 0.3})

    def test_discover_lists_the_upses_as_checks_in_a_power_group(self):
        s = M.discover(self.conn)["suggest"]
        self.assertEqual([x["params"]["ups"] for x in s], ["networkups", "qnapups"])
        self.assertTrue(all(x["group"] == "Power" and x["check"] == "ups" for x in s))
        self.assertIn('QNAP "TS" UPS', s[1]["label"])           # quotes survive the protocol

    def test_clients_lists_the_machines_attached_to_a_ups_and_only_asks(self):
        d = Upsd({"networkups": ups()}, clients={"networkups": ["192.0.2.31", "127.0.0.1"]})
        self.addCleanup(d.close)
        conn = {"host": "127.0.0.1", "port": d.port, "timeout": 1}
        self.assertEqual(M.handle({"method": "clients", "params": {"connection": conn, "ups": "networkups"}}), {"clients": ["192.0.2.31", "127.0.0.1"]})
        with self.assertRaises(N.NutError):
            M.handle({"method": "clients", "params": {"connection": conn, "ups": "nosuch"}})
        self.assertEqual(d.commands, ["LIST CLIENT networkups", "LIST CLIENT nosuch"])

    def test_it_only_ever_asks_never_controls(self):
        self.check(); self.check("qnapups"); self.check("nosuch"); M.discover(self.conn)
        self.assertTrue(self.d.commands)
        for c in self.d.commands:
            self.assertRegex(c, r"^(LIST UPS|LIST VAR \S+|LIST CLIENT \S+)$", f"the module sent a command that is not a read: {c}")
        for forbidden in ("LOGIN", "USERNAME", "PASSWORD", "SET ", "INSTCMD", "FSD", "STARTTLS"):
            self.assertFalse(any(forbidden in c for c in self.d.commands), forbidden)   # no login given: none is sent

    def test_a_server_that_wants_a_login_gets_one_and_still_only_reads(self):
        d = Upsd({"networkups": ups()}, users={"fake-user-1": 'fake"pass\\2'})            # quote and backslash survive
        self.addCleanup(d.close)
        base = {"host": "127.0.0.1", "port": d.port, "timeout": 1}
        with self.assertRaises(N.NutError) as e:                                            # no login: the server says no, and we say what to do
            M.check_ups({"ups": "networkups"}, base)
        self.assertIn("ACCESS-DENIED", str(e.exception)); self.assertIn("user name and password", str(e.exception))
        with self.assertRaises(N.NutError) as e:
            M.check_ups({"ups": "networkups"}, {**base, "username": "fake-user-1", "password": "wrong-pass-3"})
        self.assertIn("check the user name and password", str(e.exception))
        r = M.check_ups({"ups": "networkups"}, {**base, "username": "fake-user-1", "password": 'fake"pass\\2'})
        self.assertEqual(r["state"], "healthy"); self.assertIn("online", r["detail"])
        self.assertTrue(M.discover({**base, "username": "fake-user-1", "password": 'fake"pass\\2'})["ups"])
        for c in d.commands:
            self.assertRegex(c, r"^(USERNAME \S+|PASSWORD \S+|LIST UPS|LIST VAR \S+|LIST CLIENT \S+)$", f"not a login or a read: {c}")
        for forbidden in ("LOGIN", "SET ", "INSTCMD", "FSD", "STARTTLS"):
            self.assertFalse(any(forbidden in c for c in d.commands), forbidden)

    def test_protocol_parsing(self):
        self.assertEqual(N.split_args('VAR ups ups.model "A \\"B\\" C"'), ["VAR", "ups", "ups.model", 'A "B" C'])


if __name__ == "__main__":
    unittest.main()
