"""CI-only offline recovery contracts. No printer/emulator/network."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from klipper_recovery import KlipperRecovery
from read_fixture import ImmediateReadWorker


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.
        self.offline = True
        self.kind = 'shutdown'
        self.connected = True
        self.message = "MCU 'toolhead' shutdown: Timer too close"
        self.system = {'provider': 'systemd_dbus',
                       'available_services': ['klipper-other', 'klipper-2'],
                       'instance_ids': {'klipper': 'klipper-2'}}
        self.client = SimpleNamespace(get=Mock(side_effect=self.get), post=Mock())
        self.recovery = KlipperRecovery(self.client, ImmediateReadWorker(),
                                         lambda: self.offline)
        clock = patch('klipper_recovery.monotonic', lambda: self.clock)
        clock.start()
        self.addCleanup(clock.stop)

    def get(self, path):
        if path == '/server/info':
            return {'result': {'klippy_connected': self.connected,
                               'klippy_state': self.kind, 'components': ['machine']}}
        if path == '/printer/info':
            return {'result': {'state': self.kind, 'state_message': self.message}}
        if path == '/machine/system_info':
            return {'result': {'system_info': self.system}}
        raise AssertionError(path)

    def read(self):
        self.recovery.poll()
        self.recovery.poll()

    def test_shutdown_and_config_error_preserve_reason_without_requiring_ready(self):
        self.read()
        self.assertEqual(self.recovery.state.kind, 'shutdown')
        self.assertIn("MCU 'toolhead'", self.recovery.state.message)
        self.assertEqual(self.recovery.state.actions, ('restart', 'firmware'))
        self.client.post.assert_not_called()
        self.kind = 'error'
        self.message = 'Invalid config option'
        self.recovery.refresh()
        self.read()
        self.assertEqual(self.recovery.state.kind, 'error')
        self.assertEqual(self.recovery.state.message, self.message)

    def test_disconnected_service_uses_exact_detected_instance(self):
        self.connected = False
        self.kind = 'disconnected'
        self.read()
        self.assertEqual(self.recovery.state.actions, ('service',))
        self.assertTrue(self.recovery.request('service'))
        args, kwargs = self.client.post.call_args
        self.assertEqual(args, ('/machine/services/restart', {'service': 'klipper-2'}))
        self.assertTrue(kwargs['guard']())
        self.assertFalse(kwargs['report_error'])

    def test_disconnected_does_not_guess_service_when_evidence_missing(self):
        self.connected = False
        self.system['instance_ids'] = {}
        self.read()
        self.assertEqual(self.recovery.state.actions, ())
        self.assertFalse(self.recovery.request('service'))
        self.client.post.assert_not_called()

    def test_both_restart_endpoints_are_explicit_and_never_use_gcode(self):
        for action, endpoint in (('restart', '/printer/restart'),
                                 ('firmware', '/printer/firmware_restart')):
            with self.subTest(action=action):
                self.recovery._command = None
                self.read()
                self.assertTrue(self.recovery.request(action))
                args, kwargs = self.client.post.call_args
                self.assertEqual(args, (endpoint, {}))
                self.assertTrue(kwargs['guard']())
                self.assertEqual(kwargs['request_timeout'], 10.)

    def test_dispatch_guard_rechecks_live_state_and_rejects_ready_printer(self):
        self.read()
        self.assertTrue(self.recovery.request('firmware'))
        guard = self.client.post.call_args.kwargs['guard']
        self.kind = 'ready'  # Another client recovered it before dispatch.
        self.assertFalse(guard())
        self.offline = False
        self.client.get.reset_mock()
        self.assertFalse(guard())
        self.client.get.assert_not_called()

    def test_unknown_startup_ready_and_unavailable_never_offer_restart(self):
        self.kind = 'startup'
        self.read()
        self.assertEqual(self.recovery.state.actions, ())
        self.kind = 'ready'
        self.recovery.refresh()
        self.read()
        self.assertEqual(self.recovery.state.actions, ())
        self.client.get.side_effect = RuntimeError('network')
        self.recovery.refresh()
        self.read()
        self.assertEqual(self.recovery.state.kind, 'unavailable')
        self.assertEqual(self.recovery.state.actions, ())
        self.assertFalse(self.recovery.request('firmware'))

    def test_no_polling_in_ready_and_no_restart_after_indefinite_user_wait(self):
        self.offline = False
        self.read()
        self.client.get.assert_not_called()
        self.offline = True
        self.read()
        self.clock += 100000
        self.client.post.assert_not_called()
        self.assertTrue(self.recovery.request('restart'))
        self.assertTrue(self.client.post.call_args.kwargs['guard']())

    def test_pending_command_and_ambiguous_failure_are_never_replayed(self):
        future = Future()
        self.client.post.return_value = future
        self.read()
        self.assertTrue(self.recovery.request('firmware'))
        self.assertFalse(self.recovery.request('firmware'))
        future.set_exception(RuntimeError('ambiguous'))
        self.recovery.poll()
        self.assertIn('Restart failed', self.recovery.notice)
        self.clock += 20
        self.read()
        self.client.post.assert_called_once()

    def test_ack_wait_is_bounded_and_ready_discards_old_recovery_session(self):
        future = Future()
        future.set_result({'result': 'ok'})
        self.client.post.return_value = future
        self.read()
        self.recovery.request('restart')
        self.recovery.poll()
        self.assertTrue(self.recovery.busy)
        self.clock += 16
        self.recovery.poll()
        self.assertFalse(self.recovery.busy)
        self.assertIn('Still not ready', self.recovery.notice)
        self.offline = False
        self.recovery.poll()
        self.assertEqual(self.recovery.state.kind, 'checking')
        self.assertEqual(self.recovery.notice, '')

    def test_error_text_is_bounded_and_protocol_errors_fail_closed(self):
        self.message = 'x'*10000
        self.read()
        self.assertEqual(len(self.recovery.state.message), 4096)
        self.client.get.side_effect = lambda _: {'result': {'klippy_connected': 'true'}}
        self.recovery.refresh()
        self.read()
        self.assertEqual(self.recovery.state.kind, 'unavailable')
        self.assertEqual(self.recovery.state.actions, ())

class RestartTransportTests(unittest.TestCase):
    def test_restart_bodies_are_objects_through_real_http_client_and_live_guard(self):
        import io
        import json
        from urllib.parse import urlsplit
        from urllib.error import HTTPError
        from moonraker_client import MoonrakerClient

        class Response(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()

        class MoonrakerEndpoint:
            def __init__(self):
                self.posts = []
            def open(self, request, timeout=None):
                path = urlsplit(request.full_url).path
                if request.get_method() == 'GET':
                    result = ({'klippy_connected': True, 'klippy_state': 'shutdown', 'components': []}
                              if path == '/server/info' else
                              {'state': 'shutdown', 'state_message': 'Shutdown due to webhooks request'})
                else:
                    # Moonraker application.parse_args uses
                    # args.update(json.loads(request.body)): JSON null fails.
                    arguments = {}
                    try:
                        arguments.update(json.loads(request.data))
                    except TypeError:
                        raise HTTPError(request.full_url, 500, 'JSON body must be an object', {}, None)
                    self.posts.append((path, arguments))
                    result = 'ok'
                return Response(json.dumps({'result': result}).encode())

        for action, path in (('restart', '/printer/restart'), ('firmware', '/printer/firmware_restart')):
            with self.subTest(action=action):
                server = MoonrakerEndpoint()
                client = MoonrakerClient(opener=server)
                try:
                    recovery = KlipperRecovery(client, ImmediateReadWorker(), lambda: True)
                    recovery.poll()
                    recovery.poll()
                    self.assertTrue(recovery.request(action))
                    self.assertEqual(recovery._command.result(2), {'result': 'ok'})
                    recovery.poll()
                    self.assertEqual(server.posts, [(path, {})])
                    self.assertIn('Restart requested', recovery.notice)
                finally:
                    client.close()
