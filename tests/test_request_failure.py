"""#336: a request whose handler raised used to drop the connection with no answer and nothing logged, so a proxy in front answered 502
and the cause was invisible. It now gets a 500 with a plain message, and the log names the request and where it failed."""
import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sites import Box
from monitorbox_app import applog, sysinfo


class RequestFailure(unittest.TestCase):
    def test_a_handler_that_raises_answers_500_and_is_logged(self):
        box = Box(self, "fake-fail-pw-61")
        lines = []
        with mock.patch.object(sysinfo, "about", side_effect=FileNotFoundError("/proc/4242/status")), \
                mock.patch.object(applog, "error", side_effect=lambda src, text: lines.append((src, text))):
            status, body = box.req("GET", "/api/about")
        self.assertEqual(status, 500)
        self.assertIn("FileNotFoundError", body["error"])
        self.assertTrue(lines and lines[0][0] == "app" and "/api/about" in lines[0][1] and "FileNotFoundError" in lines[0][1], lines)
        self.assertEqual(box.req("GET", "/api/health")[0], 200, "the box keeps answering")


if __name__ == "__main__":
    unittest.main()
