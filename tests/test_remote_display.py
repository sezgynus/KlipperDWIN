"""Remote emulator viewer: localhost-only, no GPIO and no printer writes."""
from io import BytesIO
import json
import time
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
from dwin_emulator.remote import RemoteDisplayServer, DEFAULT_PORT
from run import parse_args


class FakeEmulator:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return Image.new("RGB", (272, 480), "teal"), self.calls


class RemoteDisplayTests(unittest.TestCase):
    def setUp(self):
        self.emulator = FakeEmulator()
        self.enqueue = Mock(return_value=True)
        self.server = RemoteDisplayServer(self.emulator, self.enqueue, port=0)
        self.base = "http://127.0.0.1:%d" % self.server.port

    def tearDown(self):
        self.server.close()

    def request(self, path, body=None, headers=None):
        if body is None:
            req = Request(self.base + path, headers=headers or {})
        else:
            req = Request(self.base + path, method="POST",
                          data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json",
                                   "X-Petrel-Remote": "1", **(headers or {})})
        return urlopen(req, timeout=3)

    def test_page_serves_local_controls_without_generating_frame(self):
        with self.request("/") as response:
            source = response.read().decode()
            self.assertIn("mouse wheel", source.lower())
            self.assertIn('event.button !== 1', source)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.emulator.calls, 0)
        self.enqueue.assert_not_called()

    def test_image_on_demand_is_native_panel_and_in_memory(self):
        with self.request("/frame.jpg?t=1") as response:
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            image = Image.open(BytesIO(response.read()))
            self.assertEqual(image.size, (272, 480))
        self.assertEqual(self.emulator.calls, 1)
        self.enqueue.assert_not_called()

    def test_rotations_and_middle_click_enter_existing_input_queue(self):
        with self.request("/input", {"kind": "rotate", "value": -2}) as response:
            self.assertEqual(response.status, 202)
        self.enqueue.assert_called_with("rotate", -2)
        time.sleep(.03)
        with self.request("/input", {"kind": "press"}) as response:
            self.assertEqual(response.status, 202)
        self.enqueue.assert_called_with("press", 1)

    def test_input_rejects_unknown_actions_unbounded_or_boolean_steps(self):
        for value in ({"kind": "power_on"}, {"kind": "rotate", "value": 7},
                      {"kind": "rotate", "value": True},
                      {"kind": "press", "value": 1},
                      {"kind": "rotate", "value": 0}):
            with self.subTest(value=value), self.assertRaises(HTTPError) as err:
                self.request("/input", value)
            self.assertEqual(err.exception.code, 400)
        self.enqueue.assert_not_called()

    def test_origin_host_and_cross_site_post_protection(self):
        with self.assertRaises(HTTPError) as err:
            self.request("/", headers={"Host": "evil.example"})
        self.assertEqual(err.exception.code, 403)
        with self.assertRaises(HTTPError) as err:
            self.request("/input", {"kind": "press"},
                         headers={"Origin": "https://evil.example"})
        self.assertEqual(err.exception.code, 403)
        with self.assertRaises(HTTPError) as err:
            self.request("/input", {"kind": "press"},
                         headers={"X-Petrel-Remote": ""})
        self.assertEqual(err.exception.code, 415)
        self.enqueue.assert_not_called()

    def test_backpressure_and_disconnected_ui_never_report_accepted(self):
        with self.request("/input", {"kind": "press"}) as response:
            self.assertEqual(response.status, 202)
        with self.assertRaises(HTTPError) as err:
            self.request("/input", {"kind": "press"})
        self.assertEqual(err.exception.code, 429)
        time.sleep(.03)
        self.enqueue.return_value = False
        with self.assertRaises(HTTPError) as err:
            self.request("/input", {"kind": "press"})
        self.assertEqual(err.exception.code, 409)

    def test_shutdown_idempotent_and_optional_flag_defaults_off(self):
        self.server.close()
        self.server.close()
        args = parse_args([])
        self.assertFalse(args.remote)
        self.assertEqual(args.remote_port, DEFAULT_PORT)
        args = parse_args(["--remote", "--remote-port", "9999"])
        self.assertTrue(args.remote)
        self.assertEqual(args.remote_port, 9999)
        with self.assertRaises(SystemExit):
            parse_args(["--remote-port", "65536"])


class RemoteUIRoutingTests(unittest.TestCase):
    def test_remote_input_uses_normal_epoch_guarded_event_queue(self):
        from test_regressions import ui as app_ui
        PetrelDisplay = app_ui.PetrelDisplay
        display = PetrelDisplay.__new__(PetrelDisplay)
        display._closed = False
        display._uart_online = True
        display._uart_epoch = 9
        display._action_feedback = None
        display._loop = Mock()
        display._loop.post.return_value = True
        display.pd = Mock()
        display.pd.subscription.snapshot.return_value = {"state": "ready", "epoch": 12}
        self.assertTrue(display._remote_input("rotate", -1))
        sent = display._loop.post.call_args.args[0]
        self.assertEqual((sent.kind, sent.value, sent.epoch, sent.ui_epoch),
                         ("rotate", -1, 12, 9))
        self.assertTrue(display._remote_input("press", 1))
        self.assertEqual(display._loop.post.call_args.args[0].kind, "press")
        display._uart_online = False
        self.assertFalse(display._remote_input("press", 1))


if __name__ == "__main__":
    unittest.main()
