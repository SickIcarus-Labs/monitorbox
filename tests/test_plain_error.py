"""Device errors in words an owner can act on."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app.server import plain_error


class PlainError(unittest.TestCase):
    def test_a_self_signed_certificate_says_what_to_turn_off(self):
        raw = "cannot reach Portainer at https://192.0.2.13:9443 ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate (_ssl.c:1032))"
        out = plain_error(raw)
        self.assertIn("self-signed", out)
        self.assertIn("Check the certificate", out)
        self.assertNotIn("_ssl.c", out)

    def test_other_errors_keep_their_wording(self):
        self.assertIn("refused the user name", plain_error("HTTP 401 unauthorized"))
        self.assertIn("refused the connection", plain_error("connection refused"))


if __name__ == "__main__":
    unittest.main()
