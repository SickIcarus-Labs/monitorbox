"""Sign-ins last: each device has its own, they survive a restart, and a password change ends them all."""
import os, sys, tempfile, time, unittest, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app.auth import Auth, LIFETIME
from monitorbox_app.store import Paths

PW, PW2 = "fake-password-one-1", "fake-password-two-2"


class Sessions(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mb-auth-"); self.paths = Paths(self.root)
        self.a = Auth(self.paths); self.a.set_password(PW)

    def test_two_devices_do_not_sign_each_other_out(self):
        phone, ipad = self.a.login(PW), self.a.login(PW)
        self.assertNotEqual(phone, ipad)
        self.a.logout(phone)
        self.assertFalse(self.a.valid(phone)); self.assertTrue(self.a.valid(ipad), "signing out on one leaves the other")

    def test_signins_survive_a_restart_and_the_file_holds_no_raw_token(self):
        tok = self.a.login(PW)
        b = Auth(self.paths)                                     # the app restarted (an update)
        self.assertTrue(b.valid(tok))
        with open(os.path.join(self.root, "data", "local", "sessions.json")) as f:
            raw = f.read()
        self.assertNotIn(tok, raw)
        self.assertEqual(oct(os.stat(os.path.join(self.root, "data", "local", "sessions.json")).st_mode & 0o777), "0o600")
        self.assertFalse(b.valid("not-a-real-token")); self.assertFalse(b.valid(None))

    def test_signing_out_every_other_device_keeps_only_the_one_asking(self):
        phone, ipad, laptop = self.a.login(PW), self.a.login(PW), self.a.login(PW)
        self.assertEqual(self.a.signed_in(), 3)
        self.assertEqual(self.a.sign_out_others(ipad), 2)
        self.assertTrue(self.a.valid(ipad)); self.assertFalse(self.a.valid(phone)); self.assertFalse(self.a.valid(laptop))
        self.assertEqual(self.a.signed_in(), 1)
        self.assertTrue(Auth(self.paths).valid(ipad), "and it holds after a restart")
        self.assertEqual(self.a.sign_out_others(ipad), 0)
        self.assertTrue(self.a.valid(ipad))

    def test_a_signin_made_with_a_passkey_is_the_same_as_one_made_with_the_password(self):
        tok = self.a.issue()
        self.assertTrue(self.a.valid(tok)); self.assertEqual(self.a.signed_in(), 1)
        self.a.logout(tok); self.assertFalse(self.a.valid(tok))
        self.assertIsNone(Auth(Paths(tempfile.mkdtemp())).issue(), "no password set, nothing to sign in to")

    def test_changing_or_resetting_the_password_ends_every_signin(self):
        tok = self.a.login(PW)
        os.remove(self.paths.auth); c = Auth(self.paths); c.set_password(PW2)
        self.assertFalse(c.valid(tok), "a new password means everyone signs in again")
        self.assertTrue(c.valid(c.login(PW2)))

    def test_it_expires_after_the_lifetime_but_use_slides_it_forward(self):
        tok = self.a.login(PW); h = next(iter(self.a.saved))
        self.a.saved[h]["exp"] = time.time() + LIFETIME - 2 * 86400     # two days since it was last used
        self.assertTrue(self.a.valid(tok)); self.assertGreater(self.a.saved[h]["exp"], time.time() + LIFETIME - 60)
        self.a.saved[h]["exp"] = time.time() - 1
        self.assertFalse(self.a.valid(tok)); self.assertEqual(self.a.saved, {})

    def test_a_wrong_password_gets_nothing_and_the_internal_token_is_not_saved(self):
        self.assertIsNone(self.a.login("wrong-wrong-wrong"))
        self.a.sessions["internal"] = time.time() + 60
        self.assertTrue(self.a.valid("internal")); self.assertFalse(os.path.exists(os.path.join(self.root, "data", "local", "sessions.json")))


if __name__ == "__main__":
    unittest.main()
