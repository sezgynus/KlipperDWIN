import json
from threading import Event
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from moonraker_client import MoonrakerClient, MoonrakerError


def response(body):
    value = Mock()
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    value.read.return_value = json.dumps(body).encode()
    return value


class TransportTests(unittest.TestCase):
    def client(self, opener=None, **kwargs):
        client = MoonrakerClient(opener=opener or Mock(), **kwargs)
        self.addCleanup(client.close)
        return client

    def test_get_timeout_and_optional_auth(self):
        opener = Mock()
        opener.open.return_value = response({'result': {'state': 'ready'}})
        client = self.client(opener, url='http://localhost:7125', timeout=2)
        self.assertEqual(client.get('/printer/info')['result']['state'], 'ready')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://localhost:7125/printer/info')
        self.assertFalse(request.has_header('X-api-key'))
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 2)

    def test_json_byte_limit_ignores_absent_or_incorrect_content_length(self):
        body = json.dumps({'result': 'ç'}).encode('utf-8')
        for header in (None, '1', '999999999'):
            for limit in (len(body), len(body) - 1):
                with self.subTest(header=header, limit=limit):
                    opener = Mock()
                    value = response({})
                    value.headers = {} if header is None else {'Content-Length': header}
                    value.read.side_effect = lambda size: body[:size]
                    opener.open.return_value = value
                    client = self.client(opener, max_json_bytes=limit)
                    if limit == len(body):
                        self.assertEqual(client.get('/server/files/list'), {'result': 'ç'})
                    else:
                        with self.assertRaisesRegex(MoonrakerError, 'exceeds.*byte limit'):
                            client.get('/server/files/list')
                        self.assertFalse(client.connected)
                        self.assertIsNotNone(client.last_error)
                    value.read.assert_called_once_with(limit + 1)
                    value.__exit__.assert_called_once()

    def test_json_limit_requires_positive_integer(self):
        for limit in (True, 0, -1, 1.5, None, '1024'):
            with self.assertRaises(ValueError):
                MoonrakerClient(max_json_bytes=limit)

    def test_oversized_post_discards_queue_without_replay_and_worker_recovers(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        opener = Mock()
        value = response({})
        def read(size):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test synchronization timed out')
            return b'x' * size
        value.read.side_effect = read
        opener.open.side_effect = [value, response({'result': 'ok'})]
        client = self.client(opener, max_json_bytes=32)
        first = client.post('/printer/gcode/script', {'script': 'G28'})
        self.assertTrue(entered.wait(1))
        second = client.post('/printer/gcode/script', {'script': 'G1 Z0'})
        release.set()
        with self.assertRaisesRegex(MoonrakerError, 'exceeds'):
            first.result(2)
        with self.assertRaisesRegex(MoonrakerError, 'preceding command failure'):
            second.result(2)
        self.assertEqual(opener.open.call_count, 1)
        self.assertTrue(client._worker.is_alive())
        self.assertEqual(client.post('/printer/print/resume').result(2), {'result': 'ok'})
        self.assertEqual(opener.open.call_count, 2)

    def test_explicit_auth(self):
        opener = Mock()
        opener.open.return_value = response({'result': 'ok'})
        self.client(opener, api_key='test-key').get('/printer/info')
        self.assertEqual(opener.open.call_args.args[0].get_header('X-api-key'), 'test-key')

    def test_http_error_and_recovery(self):
        opener = Mock()
        opener.open.side_effect = [HTTPError('url', 401, 'Unauthorized', {}, None), response({'result': 'ok'})]
        client = self.client(opener)
        with self.assertRaisesRegex(MoonrakerError, '401'):
            client.get('/printer/info')
        self.assertFalse(client.connected)
        self.assertEqual(client.get('/printer/info'), {'result': 'ok'})
        self.assertTrue(client.connected)
        self.assertIsNone(client.last_error)

    def test_invalid_json_and_error_envelope(self):
        for body in (b'not json', b'[]', b'{"error":{"message":"failed"}}'):
            with self.subTest(body=body):
                opener = Mock()
                value = response({})
                value.read.return_value = body
                opener.open.return_value = value
                with self.assertRaises(MoonrakerError):
                    self.client(opener).get('/printer/info')

    def test_failed_command_is_not_replayed_and_pending_are_discarded(self):
        entered, release = Event(), Event()
        opener = Mock()
        def timeout(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test synchronization timed out')
            raise URLError('timeout')
        opener.open.side_effect = timeout
        client = self.client(opener)
        first = client.post('/printer/gcode/script', {'script': 'G28'})
        self.assertTrue(entered.wait(2))
        second = client.post('/printer/gcode/script', {'script': 'G1 Z0'})
        release.set()
        with self.assertRaises(MoonrakerError):
            first.result(2)
        with self.assertRaisesRegex(MoonrakerError, 'preceding command failure'):
            second.result(2)
        self.assertEqual(opener.open.call_count, 1)

    def test_post_returns_result(self):
        opener = Mock()
        opener.open.return_value = response({'result': 'ok'})
        client = self.client(opener)
        future = client.post('/printer/print/resume')
        self.assertEqual(future.result(2), {'result': 'ok'})
        self.assertEqual(opener.open.call_args.args[0].method, 'POST')

    def test_close_is_idempotent_and_rejects_new_commands(self):
        opener = Mock()
        client = self.client(opener)
        client.close()
        client.close()
        self.assertFalse(client._worker.is_alive())
        with self.assertRaisesRegex(MoonrakerError, 'closed'):
            client.post('/printer/print/start').result()
        opener.open.assert_not_called()

    def test_silent_immediate_rejection_does_not_report_command_error(self):
        opener = Mock()
        client = self.client(opener)
        client.close()

        future = client.post('/server/spoolman/proxy', {}, report_error=False)

        with self.assertRaisesRegex(MoonrakerError, 'closed'):
            future.result()
        self.assertTrue(client.command_results.empty())
        opener.open.assert_not_called()

    def test_invalid_configuration(self):
        for url in ('file:///tmp/socket', 'http://user:key@localhost', 'http://localhost?key=secret'):
            with self.assertRaises(ValueError):
                MoonrakerClient(url=url)
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                MoonrakerClient(timeout=timeout)

    def test_invalid_path_does_not_send(self):
        opener = Mock()
        client = self.client(opener)
        with self.assertRaises(ValueError):
            client.get('printer/info')
        opener.open.assert_not_called()

class BinaryDownloadTests(unittest.TestCase):
    client = TransportTests.client
    def test_thumbnail_binary_limit_auth_and_timeout(self):
        opener=Mock();data=response({'result':'ok'});data.read.return_value=b'png'
        opener.open.return_value=data
        client=self.client(opener,api_key='key',timeout=2)
        self.assertEqual(client.get_bytes('/server/files/gcodes/.thumbs/a.png',max_bytes=3),b'png')
        data.read.assert_called_once_with(4)
        self.assertEqual(opener.open.call_args.args[0].get_header('X-api-key'),'key')
        data.read.return_value=b'oversize'
        with self.assertRaises(MoonrakerError):client.get_bytes('/image',max_bytes=3)
        with self.assertRaises(ValueError):client.get_bytes('//other-host/image')
        client.close()
        with self.assertRaises(MoonrakerError):client.get_bytes('/image')
