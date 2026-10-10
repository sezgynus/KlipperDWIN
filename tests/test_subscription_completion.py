import json
import unittest
from unittest.mock import Mock

from moonraker_subscription import MoonrakerSubscription
from moonraker_client import MoonrakerError

class CompletionTransportTests(unittest.TestCase):
    def make(self):
        client = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(client.close)
        client._state = 'ready'
        client._socket = Mock()
        return client

    def test_rpc_waits_for_matching_response_while_notifications_merge(self):
        client = self.make()
        future = client.request('printer.gcode.script', {'script': 'SCREWS_TILT_CALCULATE'})
        client._drain_outbound()
        message = json.loads(client._socket.send.call_args.args[0])
        self.assertFalse(future.done())
        client._notification({'method': 'notify_status_update', 'params': [{'fan': {'speed': .5}}, 10]})
        self.assertEqual(client.snapshot()['status']['fan']['speed'], .5)
        client._notification({'id': message['id'] + 1, 'result': 'wrong'})
        self.assertFalse(future.done())
        client._notification({'id': message['id'], 'result': 'ok'})
        self.assertEqual(future.result(), 'ok')

    def test_rpc_error_disconnect_and_cancelled_queue(self):
        for case in ('error', 'disconnect', 'cancel'):
            client = self.make()
            future = client.request('printer.gcode.script')
            if case == 'cancel': future.cancel()
            client._drain_outbound()
            if case == 'cancel':
                client._socket.send.assert_not_called()
            elif case == 'disconnect':
                client._fail_outbound('offline')
                with self.assertRaises(MoonrakerError): future.result()
            else:
                message = json.loads(client._socket.send.call_args.args[0])
                client._notification({'id': message['id'], 'error': {'message': 'probe error'}})
                with self.assertRaises(MoonrakerError): future.result()
            self.assertFalse(client._completion_requests)
            self.assertFalse(client._pending_requests)

    def test_queue_guard_rechecks_state_before_any_socket_write(self):
        client = self.make()
        valid = [True]
        future = client.request('printer.gcode.script', {'script': 'MMU_UNLOAD'},
                                guard=lambda: valid[0])
        valid[0] = False
        client._drain_outbound()
        client._socket.send.assert_not_called()
        with self.assertRaises(MoonrakerError):
            future.result()
        self.assertFalse(client._completion_requests)
        self.assertFalse(client._pending_requests)
