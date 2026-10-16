"""Remote emulator viewer: all IPv4 interfaces by default, no GPIO or printer writes."""
from html.parser import HTMLParser
from io import BytesIO
import json
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
from dwin_emulator.remote import RemoteDisplayServer, DEFAULT_PORT, DEFAULT_HOST, resolve_bind_host
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
        self.server = RemoteDisplayServer(self.emulator, self.enqueue, port=0, host="127.0.0.1")
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

    def test_buttons_have_accessible_labels_and_use_existing_encoder_protocol(self):
        class Buttons(HTMLParser):
            def __init__(self):
                super().__init__()
                self.items = []

            def handle_starttag(self, tag, attrs):
                if tag == "button":
                    self.items.append(dict(attrs))

        with self.request("/") as response:
            parser = Buttons()
            parser.feed(response.read().decode())
        self.assertEqual(len(parser.items), 3)
        actions = []
        for button in parser.items:
            self.assertEqual(button["type"], "button")
            self.assertTrue(button["aria-label"])
            body = {"kind": button["data-kind"]}
            if body["kind"] == "rotate":
                body["value"] = int(button["data-value"])
            time.sleep(.03)
            with self.request("/input", body) as response:
                self.assertEqual(response.status, 202)
            actions.append(self.enqueue.call_args.args)
        # Positive encoder input is CCW; negative is CW.
        self.assertEqual(actions, [("rotate", 1), ("press", 1), ("rotate", -1)])

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
        self.assertEqual(args.remote_host, DEFAULT_HOST)
        args = parse_args(["--remote", "--remote-port", "9999"])
        self.assertTrue(args.remote)
        self.assertEqual(args.remote_host, "0.0.0.0")
        self.assertEqual(args.remote_port, 9999)
        args = parse_args(["--remote-host", "127.0.0.1"])
        self.assertEqual(args.remote_host, "127.0.0.1")
        with self.assertRaises(SystemExit):
            parse_args(["--remote-port", "65536"])
        with self.assertRaises(SystemExit):
            parse_args(["--remote-host", "192.168.1.42"])


class AllInterfaceBindingTests(unittest.TestCase):
    def test_all_ipv4_interfaces_accept_client_ip_and_hostname(self):
        emulator = FakeEmulator()
        enqueue = Mock(return_value=True)
        server = RemoteDisplayServer(emulator, enqueue, port=0, host="0.0.0.0")
        try:
            self.assertEqual(server.host, "0.0.0.0")
            url = "http://127.0.0.1:%d" % server.port
            for name in ("192.168.1.43", "100.115.12.34", "openeye3dpi", "printer.example"):
                with self.subTest(name=name):
                    address = "%s:%d" % (name, server.port)
                    request = Request(url + "/", headers={"Host": address})
                    with urlopen(request, timeout=3) as result:
                        self.assertEqual(result.status, 200)
                        self.assertIn(b"Petrel Remote Display", result.read())
            address = "192.168.1.43:%d" % server.port
            post = Request(url + "/input", method="POST",
                data=b'{"kind":"press"}',
                headers={"Host":address, "Origin":"http://"+address,
                         "Content-Type":"application/json", "X-Petrel-Remote":"1"})
            with urlopen(post, timeout=3) as result:
                self.assertEqual(result.status, 202)
            enqueue.assert_called_once_with("press", 1)
            for host in ("printer.example", "evil.example:%d" % (server.port + 1),
                         "a/b:%d" % server.port, "a@b:%d" % server.port):
                with self.subTest(host=host), self.assertRaises(HTTPError) as error:
                    urlopen(Request(url + "/", headers={"Host":host}), timeout=3)
                self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url + "/input", method="POST", data=b'{"kind":"press"}',
                    headers={"Host":address, "Origin":"http://other.example:%d" % server.port,
                             "Content-Type":"application/json", "X-Petrel-Remote":"1"}), timeout=3)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.close()


class TailscaleBindingTests(unittest.TestCase):
    def test_direct_tailscale_ip_is_detected_and_validated(self):
        result = Mock(stdout="100.115.12.34\n")
        with patch("dwin_emulator.remote.subprocess.run", return_value=result) as cmd:
            self.assertEqual(resolve_bind_host("tailscale"), "100.115.12.34")
        cmd.assert_called_once_with(
            ["tailscale", "ip", "-4"], capture_output=True, text=True,
            check=True, timeout=3)

    def test_remote_binding_is_restricted_to_tailscale_or_explicit_local(self):
        self.assertEqual(resolve_bind_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(resolve_bind_host("0.0.0.0"), "0.0.0.0")
        for host in ("::", "192.168.1.42", "localhost", "100.99.10.2"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                resolve_bind_host(host)

    def test_tailscale_unavailable_fails_closed_without_wildcard_fallback(self):
        from subprocess import CalledProcessError, TimeoutExpired
        for error in (FileNotFoundError("tailscale missing"),
                      TimeoutExpired("tailscale", 3),
                      CalledProcessError(1, ["tailscale", "ip", "-4"])):
            with self.subTest(error=type(error).__name__), patch(
                    "dwin_emulator.remote.subprocess.run", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "Tailscale IPv4 unavailable"):
                    RemoteDisplayServer(FakeEmulator(), Mock(), port=0, host="tailscale")
        for wrong in ("192.168.1.4", "127.0.0.1", "100.129.2.1", "not-an-ip", ""):
            with self.subTest(wrong=wrong), patch(
                    "dwin_emulator.remote.subprocess.run",
                    return_value=Mock(stdout=wrong)):
                with self.assertRaises(RuntimeError):
                    resolve_bind_host("tailscale")


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
