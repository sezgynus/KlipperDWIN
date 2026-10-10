import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch
from software_update import SoftwareUpdate


class UpdateTests(unittest.TestCase):
    def make(self, name='KlipperDWIN'):
        snapshot = {'state': 'ready', 'epoch': 1, 'status': {'print_stats': {'state': 'standby'}}}
        printer = SimpleNamespace(subscription=Mock(), client=SimpleNamespace(url='http://localhost:7125', headers={}), _read_worker=Mock())
        printer.subscription.snapshot.return_value = snapshot
        worker = printer._read_worker
        def submit(work):
            f = Future()
            try: f.set_result(work())
            except Exception as error: f.set_exception(error)
            return f
        worker.submit.side_effect = submit
        updater = SoftwareUpdate(printer)
        client = Mock()
        item = {'is_valid': True, 'is_dirty': False, 'current_hash': 'old', 'remote_hash': 'new'}
        client.get.return_value = {'result': {'version_info': {name: item}}}
        client.request.return_value = {'result': {'version_info': {name: item}}}
        return updater, client, item, snapshot

    @patch('software_update.MoonrakerClient')
    def test_checks_and_updates_only_discovered_klipperdwin_name(self, factory):
        updater, client, _, _ = self.make('klipperdwin')
        factory.return_value = client
        updater.start(); updater.poll()
        self.assertEqual(updater.label, 'Update')
        client.request.assert_called_once_with('POST', '/machine/update/refresh', {'name': 'klipperdwin'})
        updater.start(); updater.poll()
        self.assertEqual(updater.phase, 'restarting')
        self.assertEqual(client.request.call_args.args, ('POST', '/machine/update/client', {'name': 'klipperdwin'}))

    @patch('software_update.MoonrakerClient')
    def test_current_invalid_missing_and_printing_never_install(self, factory):
        for mode in ('current', 'invalid', 'missing', 'printing', 'paused'):
            updater, client, item, snapshot = self.make()
            factory.return_value = client
            if mode == 'current': item['remote_hash'] = 'old'
            if mode == 'invalid': item['is_valid'] = False
            if mode == 'missing': client.get.return_value = {'result': {'version_info': {}}}
            if mode in ('printing', 'paused'): snapshot['status']['print_stats']['state'] = mode
            updater.start(); updater.poll()
            self.assertNotEqual(updater.phase, 'available')
            self.assertFalse(any(call.args[1] == '/machine/update/client' for call in client.request.call_args_list))

    @patch('software_update.MoonrakerClient')
    def test_pending_clicks_and_failed_upgrade_are_not_retried(self, factory):
        updater, client, _, _ = self.make()
        factory.return_value = client
        pending = Future()
        updater.printer._read_worker.submit.return_value = pending
        updater.printer._read_worker.submit.side_effect = None
        updater.start(); updater.start()
        self.assertEqual(updater.printer._read_worker.submit.call_count, 1)
        pending.set_exception(RuntimeError('failed'))
        updater.poll()
        self.assertEqual(updater.phase, 'error')
        self.assertEqual(updater.label, 'Check for updates')

    @patch('software_update.MoonrakerClient')
    def test_upgrade_failure_requires_fresh_check(self, factory):
        updater, client, _, _ = self.make()
        factory.return_value = client
        updater.start(); updater.poll()
        client.request.side_effect = RuntimeError('timeout')
        updater.start(); updater.poll()
        self.assertEqual(updater.phase, 'error')
        self.assertEqual(updater.message, 'Update unconfirmed; check Mainsail')
        self.assertEqual(updater.label, 'Check for updates')

    @patch('software_update.MoonrakerClient')
    def test_dirty_repo_and_changed_epoch_block_upgrade(self, factory):
        updater, client, item, snapshot = self.make()
        factory.return_value = client
        updater.start(); updater.poll()
        item['is_dirty'] = True
        client.request.reset_mock()
        updater.start(); updater.poll()
        client.request.assert_not_called()
        updater.phase = 'available'
        captured = []
        updater.printer._read_worker.submit.side_effect = lambda work: captured.append(work) or Future()
        updater.start()
        snapshot['epoch'] = 2
        with self.assertRaisesRegex(ValueError, 'state changed'):
            captured[0]()
        client.request.assert_not_called()
