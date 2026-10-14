import json
import unittest
from threading import Event
from unittest.mock import Mock, patch

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

class PendingRequestBudgetTests(unittest.TestCase):
    make = CompletionTransportTests.make

    def test_outstanding_budget_bounds_unanswered_requests(self):
        client = self.make()
        first = None
        for _ in range(200):
            future = client.request('printer.objects.query', {'objects': {'toolhead': None}})
            if first is None:
                first = future
            client._drain_outbound()
        self.assertEqual(len(client._pending_requests), client.MAX_PENDING_REQUESTS)
        self.assertEqual(len(client._pending_deadlines), client.MAX_PENDING_REQUESTS)
        self.assertEqual(client._socket.send.call_count, client.MAX_PENDING_REQUESTS)
        self.assertFalse(first.done())
        client._fail_outbound('connection closed')
        with self.assertRaises(MoonrakerError):
            first.result()
        self.assertFalse(client._pending_requests)
        self.assertFalse(client._pending_deadlines)

    def test_ttl_expiry_releases_future_and_ignores_late_response(self):
        client = self.make()
        future = client.request('printer.objects.query')
        client._drain_outbound()
        request_id, deadline = next(iter(client._pending_deadlines.items()))
        with patch('moonraker_subscription.time.monotonic', return_value=deadline + 1):
            client._drain_outbound()
        with self.assertRaisesRegex(MoonrakerError, 'timed out'):
            future.result()
        self.assertFalse(client._pending_requests)
        self.assertFalse(client._pending_deadlines)
        client._notification({'id': request_id, 'result': 'late'})
        self.assertTrue(future.done())

    def test_cancelled_requests_leave_no_deadline(self):
        client = self.make()
        future = client.request('printer.objects.query')
        client._drain_outbound()
        self.assertTrue(future.cancel())
        client._drain_outbound()
        self.assertFalse(client._pending_requests)
        self.assertFalse(client._pending_deadlines)


class OutboundWakeupTests(unittest.TestCase):
    def test_writer_dispatches_on_idle_connection_without_receive_polling(self):
        client = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(client.close)
        client._state = 'ready'
        written = Event()
        client._socket = Mock()
        client._socket.send.side_effect = lambda payload: written.set()
        client._writer_thread.start()
        future = client.request('printer.gcode.script', {'script': 'BED_MESH_CALIBRATE'})
        self.assertTrue(written.wait(.5), 'outbound writer waited for an inbound frame')
        self.assertFalse(future.done())
        self.assertEqual(len(client._pending_requests), 1)

    def test_emergency_request_is_woken_with_idle_receiver(self):
        client = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(client.close)
        client._state = 'ready'
        written = Event()
        client._socket = Mock()
        client._socket.send.side_effect = lambda payload: written.set()
        client._writer_thread.start()
        future = client.request('printer.emergency_stop')
        self.assertTrue(written.wait(.5))
        self.assertFalse(future.done())
