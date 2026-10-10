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

    @patch('software_update.MoonrakerClient')
    def test_dirty_recovery_requires_confirmation_and_scopes_soft_request(self, factory):
        updater, client, item, _ = self.make('klipperdwin')
        factory.return_value = client
        item['is_dirty'] = True
        updater.start(); updater.poll()
        self.assertEqual(updater.phase, 'dirty')
        self.assertEqual(updater.label, 'Soft recovery')
        client.request.reset_mock()
        updater.start()
        self.assertEqual(updater.label, 'Confirm recovery')
        client.request.assert_not_called()
        def request(method, path, params):
            self.assertEqual(params.get('name'), 'klipperdwin')
            if path == '/machine/update/recover':
                self.assertIs(params['hard'], False)
                item['is_dirty'] = False
                return {'result': 'ok'}
            return {'result': {'version_info': {'klipperdwin': item}}}
        client.request.side_effect = request
        updater.start(); updater.poll()
        self.assertEqual(updater.phase, 'available')
        self.assertEqual([call.args[1] for call in client.request.call_args_list],
                         ['/machine/update/recover', '/machine/update/refresh'])

    @patch('software_update.MoonrakerClient')
    def test_cancel_confirmation_and_state_change_never_recover(self, factory):
        updater, client, item, state = self.make()
        factory.return_value = client
        item['is_dirty'] = True
        updater.start(); updater.poll(); updater.start()
        updater.cancel_confirmation()
        self.assertEqual(updater.phase, 'dirty')
        updater.start()
        state['epoch'] = 2
        client.request.reset_mock()
        updater.start()
        self.assertEqual(updater.phase, 'error')
        client.request.assert_not_called()

    @patch('software_update.MoonrakerClient')
    def test_recovery_rechecks_dirty_state_and_rejects_other_updater(self, factory):
        for mode in ('clean', 'missing', 'wrong_name', 'printing', 'paused'):
            updater, client, item, state = self.make()
            factory.return_value = client
            item['is_dirty'] = True
            updater.start(); updater.poll(); updater.start()
            if mode == 'clean': item['is_dirty'] = False
            if mode == 'missing': client.get.return_value = {'result': {'version_info': {}}}
            if mode == 'wrong_name': updater.name = 'moonraker'
            if mode in ('printing', 'paused'): state['status']['print_stats']['state'] = mode
            client.request.reset_mock()
            updater.start(); updater.poll()
            client.request.assert_not_called()

    @patch('software_update.MoonrakerClient')
    def test_recovery_timeout_never_automatically_retries(self, factory):
        updater, client, item, _ = self.make()
        factory.return_value = client
        item['is_dirty'] = True
        updater.start(); updater.poll(); updater.start()
        client.request.side_effect = TimeoutError('timeout')
        client.request.reset_mock()
        updater.start(); updater.poll(); updater.poll()
        self.assertEqual(updater.phase, 'error')
        self.assertEqual(updater.message, 'Recovery unconfirmed; check Mainsail')
        client.request.assert_called_once_with('POST', '/machine/update/recover',
                                               {'name': 'KlipperDWIN', 'hard': False})

    @patch('software_update.MoonrakerClient')
    def test_invalid_clean_repo_offers_and_performs_confirmed_soft_recovery(self, factory):
        updater, client, item, _ = self.make()
        factory.return_value = client
        item['is_valid'] = False
        self.assertFalse(item['is_dirty'])
        updater.start(); updater.poll()
        self.assertEqual(updater.label, 'Soft recovery')
        updater.start()
        self.assertEqual(updater.label, 'Confirm recovery')
        client.request.reset_mock()
        def request(method, path, params):
            if path == '/machine/update/recover':
                self.assertEqual(params, {'name': 'KlipperDWIN', 'hard': False})
                item['is_valid'] = True
                return {'result': 'ok'}
            return {'result': {'version_info': {'KlipperDWIN': item}}}
        client.request.side_effect = request
        updater.start(); updater.poll()
        self.assertEqual(updater.phase, 'available')
        client.request.assert_any_call('POST', '/machine/update/recover',
                                       {'name': 'KlipperDWIN', 'hard': False})
