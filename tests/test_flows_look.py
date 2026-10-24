"""The flows look on the box: signed in only, nothing to ask without a UniFi login, and the Settings button is there."""
import os, sys, unittest, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_sites as TS  # noqa: E402


class FlowsLook(unittest.TestCase):
    def test_it_needs_a_sign_in_and_without_a_unifi_login_there_is_nothing_to_ask(self):
        box = TS.Box(self, "fake-flows-pw-84")
        self.assertEqual(box.get("/api/lan/flows-look"), {"sources": []})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{box.port}/api/lan/flows-look")
        self.assertEqual(e.exception.code, 401)

    def test_gateway_usage_without_a_unifi_login_is_an_empty_list_and_its_window_is_kept_to_a_minute_and_an_hour(self):
        box = TS.Box(self, "fake-gw-pw-86")
        d = box.app.gateway_usage(600)
        self.assertEqual((d["clients"], d["seconds"], d["total"]), ([], 600, {"down_bps": 0, "up_bps": 0}))
        self.assertEqual(box.app.gateway_usage(1)["seconds"], 60)
        self.assertEqual(box.app.gateway_usage(999999)["seconds"], 3600)

    def test_the_settings_page_has_the_button(self):
        box = TS.Box(self, "fake-flows-pw-85")
        html = urllib.request.urlopen(f"http://127.0.0.1:{box.port}/").read().decode()
        self.assertIn("flowRun()", html)
        self.assertIn("Flows look", html)


if __name__ == "__main__":
    unittest.main()
