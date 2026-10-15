"""CI-only end-to-end Maintenance read controller regressions."""
from concurrent.futures import Future
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot, INFORMATION, _add
from maintenance_controller import MaintenanceReadController


class Worker:
    def __init__(self):
        self.jobs = []
    def submit(self, work, queue_timeout=None):
        future = Future()
        self.jobs.append((work, future))
        return future
    def drain(self):
        work, future = self.jobs.pop(0)
        if future.cancelled():
            return
        if future.set_running_or_notify_cancel():
            try:
                future.set_result(work())
            except Exception as e:
                future.set_exception(e)


class Client:
    def __init__(self):
        self.paths = []
        self.queue = {'queue_state': 'ready', 'queued_jobs': []}
        self.components = ['job_queue']
        self.stat = {'system_cpu_usage': {'cpu': .12},
                     'system_memory': {'total': 1024, 'available': 256}}
    def get(self, path):
        self.paths.append(path)
        if path == '/server/info':
            return {'result': {'components': self.components}}
        if path == '/server/job_queue/status':
            return {'result': self.queue}
        if path == '/machine/proc_stats':
            return {'result': self.stat}
        raise AssertionError('Unlisted Maintenance endpoint: ' + path)
    def post(self, *args, **kwargs):
        raise AssertionError('Read-only Maintenance must not send commands')


def printer():
    data = {'state': 'ready', 'epoch': 12, 'settings': {},
            'status': {'webhooks': {'state': 'ready'},
                       'print_stats': {'state': 'standby'},
                       'virtual_sdcard': {'is_active': False},
                       'pause_resume': {'is_paused': False}}}
    state = PrinterState.from_snapshot(data)
    owner = lambda: SimpleNamespace(pending=None, phase='idle')
    snap = MaintenanceSnapshot(
        12, global_modes=_add(0, 'S01', INFORMATION),
        config_marker=id(state.settings))
    backend = SimpleNamespace(
        state=state, connection_error=None,
        subscription=SimpleNamespace(snapshot=Mock(return_value=data)),
        maintenance=SimpleNamespace(snapshot=snap),
        jog_recovery_required=False, _jog_restore=None, _settings_save=None,
        bed_mesh=owner(), screws_tilt=owner(), probe_wizard=owner(),
        mmu_session=owner())
    return backend, data


class MaintenanceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.backend, self.data = printer()
        self.worker, self.client = Worker(), Client()
        self.bridge = MaintenanceReadController(
            self.backend, self.worker, self.client)

    def test_read_from_discovery_to_async_evidence_and_result(self):
        self.assertEqual([r.feature_id for r in self.bridge.available()], ['S01'])
        self.assertEqual(self.bridge.start('S01'), (True, 'preflight_queued'))
        self.assertTrue(self.bridge.pending)
        self.assertIsNone(self.bridge.poll())
        self.worker.drain()
        self.assertIsNone(self.bridge.poll())
        self.worker.drain()
        result = self.bridge.poll()
        self.assertIsNone(result.status)
        self.assertEqual(result.reason, 'observed_information')
        self.assertEqual(result.evidence[0], ('cpu.cpu', .12))
        self.assertEqual(self.client.paths, [
            '/server/info', '/server/job_queue/status', '/machine/proc_stats'])
        self.assertFalse(self.bridge.pending)

    def test_job_queue_absent_after_positive_component_check(self):
        self.client.components = ['history']
        self.assertTrue(self.bridge.start('S01')[0])
        self.worker.drain()
        self.assertIsNone(self.bridge.poll())
        self.worker.drain()
        self.assertIsNone(self.bridge.poll().status)
        self.assertNotIn('/server/job_queue/status', self.client.paths)

    def test_full_queue_fails_without_information_get(self):
        self.client.queue = {'queue_state': 'ready', 'queued_jobs': [{'id': 10}]}
        self.assertTrue(self.bridge.start('S01')[0])
        self.worker.drain()
        result = self.bridge.poll()
        self.assertEqual(result.status, 'ABORTED')
        self.assertNotIn('/machine/proc_stats', self.client.paths)

    def test_unknown_queue_blocks_without_faking_absence(self):
        self.client.components = None
        self.assertTrue(self.bridge.start('S01')[0])
        self.worker.drain()
        self.assertEqual(self.bridge.poll().reason, 'job_queue_unknown')

    def test_print_transition_blocks_after_preflight(self):
        self.assertTrue(self.bridge.start('S01')[0])
        self.worker.drain()
        self.data['status']['print_stats']['state'] = 'printing'
        self.assertEqual(self.bridge.poll().status, 'ABORTED')
        self.assertNotIn('/machine/proc_stats', self.client.paths)

    def test_disconnect_drops_queued_future(self):
        self.assertTrue(self.bridge.start('S01')[0])
        self.data['epoch'] = 13
        self.assertEqual(self.bridge.poll().status, 'ABORTED')
        self.worker.drain()
        self.assertEqual(self.client.paths, [])

    def test_live_lifecycle_disconnect_invalidates_preflight_before_state_tick(self):
        self.backend.subscription.lifecycle = Mock(
            return_value={'state': 'disconnected', 'epoch': 12})
        self.assertTrue(self.bridge.start('S01')[0])
        self.assertEqual(self.bridge.poll().reason, 'stale_or_disconnected')
        self.worker.drain()
        self.assertEqual(self.client.paths, [])

    def test_cancel_pending_then_new_request_ignores_old_future(self):
        self.assertTrue(self.bridge.start('S01')[0])
        self.assertEqual(self.bridge.cancel().status, 'ABORTED')
        self.assertFalse(self.bridge.pending)
        self.assertTrue(self.bridge.start('S01')[0])
        self.worker.drain()
        self.worker.drain()
        self.assertIsNone(self.bridge.poll())
        self.worker.drain()
        self.assertIsNone(self.bridge.poll().status)
        self.assertEqual(self.client.paths.count('/machine/proc_stats'), 1)

    def test_negative_and_unregistered_features_are_not_schedulable(self):
        self.assertFalse(self.bridge.start('F01')[0])
        self.assertFalse(self.bridge.start('S02')[0])
        self.assertEqual(self.client.paths, [])

    def test_close_rejects_future_work_and_cleans_pending(self):
        self.assertTrue(self.bridge.start('S01')[0])
        self.bridge.close()
        self.worker.drain()
        self.assertFalse(self.bridge.pending)
        self.assertFalse(self.bridge.start('S01')[0])

    def test_petrel_backend_owns_bridge_without_new_threads(self):
        from unittest.mock import patch
        import tempfile
        import printerInterface as backend
        from read_fixture import ImmediateReadWorker
        with patch.object(backend, 'MoonrakerClient'), \
                patch.object(backend, 'MoonrakerSubscription'), \
                patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            actual = backend.PrinterData(
                settings_path=tempfile.mktemp(prefix='petrel-bridge-', suffix='.json'))
        self.assertIs(actual.maintenance_reader._printer, actual)
        self.assertEqual(actual.maintenance_read_plan(), ())
        self.assertFalse(actual.start_maintenance_read('S01')[0])
        actual.close()


if __name__ == '__main__':
    unittest.main()
