import json
import socket
from collections import deque
from threading import Event
import unittest
from unittest.mock import Mock

from moonraker_client import MoonrakerError
from moonraker_subscription import MoonrakerSubscription


class FakeSocket:
    def __init__(self, snapshot=None):
        self.messages = deque()
        self.sent = []
        self.closed = False
        self.subscribed = Event()
        self.snapshot = snapshot or {'toolhead': {'position': [0, 0, 1, 0]},
                                    'gcode_move': {}, 'print_stats': {'state': 'paused'},
                                    'virtual_sdcard': {'progress': 0.5},
                                    'webhooks': {'state': 'ready'}}

    def send(self, data):
        request = json.loads(data)
        self.sent.append(request)
        if 'id' not in request:
            return
        results = {'server.connection.identify': {'connection_id': 1},
                   'server.info': {'klippy_state': 'ready'},
                   'printer.info': {'software_version': 'test-klipper'},
                   'printer.objects.list': {'objects': list(self.snapshot) + ['configfile']},
                   'printer.objects.query': {'status': {'configfile': {'settings': {}}}, 'eventtime': 9},
                   'printer.objects.subscribe': {'status': self.snapshot, 'eventtime': 10}}
        result = results[request['method']]
        self.messages.append({'jsonrpc': '2.0', 'id': request['id'], 'result': result})
        if request['method'] == 'printer.objects.subscribe':
            self.subscribed.set()

    def recv_data(self, control_frame=True):
        if self.closed:
            return 8, b''
        if self.messages:
            return 1, json.dumps(self.messages.popleft())
        # Short, interruptible fake read; no busy polling.
        self.subscribed.wait(0.001)
        Event().wait(0.005)
        raise socket.timeout()

    def settimeout(self, timeout):
        self.timeout = timeout

    def ping(self):
        pass

    def close(self):
        self.closed = True


class SubscriptionTests(unittest.TestCase):
    def subscription(self, **kwargs):
        client = MoonrakerSubscription('http://localhost:7125', autostart=False, **kwargs)
        self.addCleanup(client.close)
        return client

    def test_url_conversion(self):
        client = MoonrakerSubscription('https://localhost/proxy/', autostart=False)
        self.addCleanup(client.close)
        self.assertEqual(client.url, 'wss://localhost/proxy/websocket')

    def test_partial_delta_preserves_other_fields_and_objects(self):
        client = self.subscription()
        client._merge({'extruder': {'temperature': 200, 'target': 205},
                       'print_stats': {'state': 'printing'}}, 10, replace=True)
        client._merge({'extruder': {'temperature': 201}}, 11)
        status = client.snapshot()['status']
        self.assertEqual(status['extruder'], {'temperature': 201, 'target': 205})
        self.assertEqual(status['print_stats']['state'], 'printing')
        status['extruder']['target'] = 0
        self.assertEqual(client.snapshot()['status']['extruder']['target'], 205)

    def test_old_delta_is_ignored(self):
        client = self.subscription()
        client._merge({'fan': {'speed': 1}}, 20, replace=True)
        client._merge({'fan': {'speed': 0}}, 19)
        self.assertEqual(client.snapshot()['status']['fan']['speed'], 1)

    def test_lifecycle_invalidates_snapshot_and_epoch(self):
        client = self.subscription()
        client._merge({'print_stats': {'state': 'printing'}}, 20, replace=True)
        before = client.snapshot()['epoch']
        with self.assertRaises(MoonrakerError):
            client._notification({'method': 'notify_klippy_shutdown'})
        client._invalidate('shutdown')
        self.assertEqual(client.snapshot()['status'], {})
        self.assertGreater(client.snapshot()['epoch'], before)
        client._merge({'print_stats': {'state': 'standby'}}, 1, replace=True)
        self.assertEqual(client.snapshot()['status']['print_stats']['state'], 'standby')

    def test_bootstrap_identifies_and_subscribes_only_available_objects(self):
        client = self.subscription(api_key='test-key')
        connection = FakeSocket()
        client._socket = connection
        client._bootstrap()
        self.assertEqual(client.snapshot()['state'], 'ready')
        self.assertEqual(client.snapshot()['software_version'], 'test-klipper')
        self.assertEqual(client.snapshot()['status']['print_stats']['state'], 'paused')
        self.assertEqual(connection.sent[0]['params']['api_key'], 'test-key')
        self.assertNotIn('fan', connection.sent[-1]['params']['objects'])
        self.assertEqual([r['id'] for r in connection.sent], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(r['method'] not in ('printer.gcode.script', 'printer.print.start')
                            for r in connection.sent))

    def test_bootstrap_subscribes_dynamic_mmu_exit_led_units(self):
        snapshot_data = {
            'toolhead': {'position': [0, 0, 1, 0]},
            'gcode_move': {},
            'print_stats': {'state': 'paused'},
            'virtual_sdcard': {'progress': 0.5},
            'webhooks': {'state': 'ready'},
            'unit1_mmu_exit_leds': {'color_data': [[0.0, 1.0, 0.0, 0.0]]},
            'stepper_enable': {'steppers': {'mmu_stepper gear': True}},
            'mmu_leds pico': {'enabled': True, 'animation': False},
        }
        client = self.subscription()
        connection = FakeSocket(snapshot_data)
        client._socket = connection
        client._bootstrap()
        subscribed = connection.sent[-1]['params']['objects']
        self.assertIn('unit1_mmu_exit_leds', subscribed)
        self.assertIn('stepper_enable', subscribed)
        self.assertIn('mmu_leds pico', subscribed)
        self.assertNotIn('mmu_leds absent', subscribed)

    def test_no_empty_auth_sent(self):
        client = self.subscription()
        client._socket = FakeSocket()
        client._bootstrap()
        self.assertEqual(client._headers, [])
        self.assertNotIn('api_key', client._socket.sent[0]['params'])

    def test_notification_before_response_is_merged_after_snapshot(self):
        client = self.subscription()
        connection = FakeSocket()
        original_send = connection.send
        def send(data):
            request = json.loads(data)
            if request['method'] == 'printer.objects.subscribe':
                connection.messages.append({'jsonrpc': '2.0', 'method': 'notify_status_update',
                                            'params': [{'virtual_sdcard': {'progress': 0.6}}, 11]})
            original_send(data)
        connection.send = send
        client._socket = connection
        client._bootstrap()
        self.assertEqual(client.snapshot()['status']['virtual_sdcard']['progress'], 0.6)

    def test_rpc_error_and_invalid_notification(self):
        client = self.subscription()
        connection = FakeSocket()
        connection.send = lambda data: connection.messages.append(
            {'jsonrpc': '2.0', 'id': json.loads(data)['id'], 'error': {'code': 401}})
        client._socket = connection
        with self.assertRaises(MoonrakerError):
            client._rpc('server.info')
        with self.assertRaises(MoonrakerError):
            client._notification({'method': 'notify_status_update', 'params': [{}]})

    def test_rpc_timeout(self):
        client = self.subscription(timeout=0.02)
        connection = FakeSocket()
        connection.send = lambda data: None
        client._socket = connection
        with self.assertRaisesRegex(MoonrakerError, 'timed out'):
            client._rpc('server.info')

    def test_observed_command_is_notification_and_does_not_wait_for_response(self):
        client = self.subscription()
        connection = FakeSocket()
        client._socket = connection
        client._state = 'ready'
        future = client.notify('printer.gcode.script', {'script': 'G28'})
        self.assertFalse(future.done())
        client._drain_outbound()
        self.assertIsNone(future.result())
        request = connection.sent[-1]
        self.assertEqual(request['method'], 'printer.gcode.script')
        self.assertEqual(request['params'], {'script': 'G28'})
        self.assertNotIn('id', request)
        self.assertEqual(len(connection.messages), 0)

    def test_filelist_notification_invalidates_revision(self):
        client = self.subscription()
        client._notification({'method': 'notify_filelist_changed', 'params': []})
        self.assertEqual(client.snapshot()['file_revision'], 1)

    def test_reconnect_performs_new_bootstrap_without_commands(self):
        first, second = FakeSocket(), FakeSocket()
        original_send = first.send
        def disconnect_after_subscription(data):
            original_send(data)
            if json.loads(data)['method'] == 'printer.objects.subscribe':
                first.messages.append({'jsonrpc': '2.0', 'method': 'notify_klippy_disconnected'})
        first.send = disconnect_after_subscription
        reconnected = Event()
        calls = []
        def connector(*args):
            calls.append(args)
            if len(calls) == 1:
                return first
            reconnected.set()
            return second
        client = MoonrakerSubscription('http://localhost:7125', connector=connector, retry_delay=0.01)
        self.addCleanup(client.close)
        self.assertTrue(reconnected.wait(2))
        self.assertTrue(second.subscribed.wait(2))
        client.close()
        self.assertFalse(client._thread.is_alive())
        self.assertTrue(first.closed)
        self.assertEqual(len(first.sent), 6)
        self.assertTrue(second.closed)
        self.assertEqual([r['method'] for r in second.sent],
                         ['server.connection.identify', 'server.info', 'printer.info',
                          'printer.objects.list', 'printer.objects.query', 'printer.objects.subscribe'])


class CommandEpochTests(unittest.TestCase):
    def test_changed_epoch_rejects_queued_command_before_network(self):
        from moonraker_client import MoonrakerClient
        opener = Mock()
        client = MoonrakerClient(opener=opener)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(MoonrakerError, 'connection changed'):
            client.post('/printer/gcode/script', {'script': 'G28'}, guard=lambda: False).result(2)
        opener.open.assert_not_called()
