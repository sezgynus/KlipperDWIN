"""CI-only bounded Maintenance read executor and evidence contracts."""
from concurrent.futures import Future
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import MaintenanceSnapshot, INFORMATION, _add
from maintenance_planner import build_plan, visible_plan
from maintenance_executor import (
    MaintenanceReadExecutor, read_only_adapters, _read_fields,
)
from maintenance_safety import SafetyContext


class Worker:
    def __init__(self):
        self.tasks = []
        self.waits = []

    def submit(self, work, queue_timeout=None):
        future = Future()
        self.tasks.append((work, future))
        self.waits.append(queue_timeout)
        return future

    def drain(self):
        work, future = self.tasks.pop(0)
        if future.cancelled():
            return
        future.set_running_or_notify_cancel()
        try:
            future.set_result(work())
        except Exception as error:
            future.set_exception(error)


class Client:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def get(self, path):
        self.requests.append(path)
        return self.reply

    def post(self, *args, **kwargs):
        raise AssertionError('Read executor must not POST or issue G-code')


class ReadExecutorTests(unittest.TestCase):
    def setUp(self):
        self.settings = {}
        self.state = SimpleNamespace(
            ready=True, epoch=33, settings=self.settings,
            status={'webhooks': {'state': 'ready'},
                    'print_stats': {'state': 'standby'},
                    'virtual_sdcard': {'is_active': False},
                    'pause_resume': {'is_paused': False}})
        self.snapshot = MaintenanceSnapshot(
            33, global_modes=_add(0, 'S01', INFORMATION),
            config_marker=id(self.settings))
        self.worker = Worker()
        self.client = Client({'result': {
            'system_cpu_usage': {'cpu': .25},
            'system_memory': {'total': 100, 'available': 50}}})
        self.provenance = {'queue_checked': True, 'job_queue': None,
                           'operations_checked': True,
                           'conflicting_operation': False}

    def context(self):
        return SafetyContext(self.state, **self.provenance)

    def executor(self):
        return MaintenanceReadExecutor(
            self.worker, self.client, self.context, lambda: self.snapshot)

    def row(self):
        return next(r for r in visible_plan(build_plan(
            self.snapshot, read_only_adapters())) if r.feature_id == 'S01')

    def test_positive_information_is_never_test_pass(self):
        exe = self.executor()
        accepted, reason = exe.start(self.row())
        self.assertTrue(accepted)
        self.assertEqual(reason, 'scheduled')
        self.assertEqual(exe.poll(), None)
        self.worker.drain()
        result = exe.poll()
        self.assertIsNone(result.status)
        self.assertEqual(result.reason, 'observed_information')
        self.assertEqual(result.source, '/machine/proc_stats')
        self.assertIn(('cpu.cpu', .25), result.evidence)
        self.assertTrue(result.observed_at > 0)
        self.assertEqual(self.client.requests, ['/machine/proc_stats'])
        self.assertFalse(exe.pending)
        self.assertEqual(self.worker.waits, [3.0])
        self.assertIsNone(exe.poll())

    def test_missing_or_untrusted_evidence_inconclusive(self):
        self.client.reply = {'result': {'system_cpu_usage': {'cpu': True},
                                        'system_memory': {'total': float('nan')}}}
        exe = self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.worker.drain()
        result = exe.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertEqual(result.evidence, ())

    def test_cancel_drops_stale_future_and_allows_new_session(self):
        exe = self.executor()
        self.assertTrue(exe.start(self.row())[0])
        cancelled = exe.cancel()
        self.assertEqual(cancelled.status, 'ABORTED')
        self.assertIsNone(exe.cancel())
        self.assertTrue(exe.start(self.row())[0])
        self.worker.drain()  # first Future cancelled: no HTTP request.
        self.worker.drain()
        self.assertIsNone(exe.poll().status)
        self.assertEqual(len(self.client.requests), 1)

    def test_external_print_start_prevents_queued_get(self):
        exe = self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.state.status['print_stats']['state'] = 'printing'
        self.worker.drain()
        self.assertEqual(self.client.requests, [])
        self.assertEqual(exe.poll().status, 'ABORTED')

    def test_epoch_and_config_drift_prevent_stale_publication(self):
        exe = self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.worker.drain()
        self.state.epoch = 34
        self.assertEqual(exe.poll().status, 'ABORTED')
        self.state.epoch = 33
        self.state.settings = {}
        self.assertFalse(exe.start(self.row())[0])

    def test_queue_or_operation_unknown_blocks_submission(self):
        exe = self.executor()
        self.provenance['queue_checked'] = False
        self.assertFalse(exe.start(self.row())[0])
        self.assertFalse(exe.pending)
        self.assertEqual(len(self.worker.tasks), 0)
        self.provenance['queue_checked'] = True
        self.provenance['conflicting_operation'] = True
        self.assertFalse(exe.start(self.row())[0])
        self.assertEqual(self.client.requests, [])

    def test_single_request_only_and_unsupported_adapter_rejected(self):
        exe = self.executor()
        row = self.row()
        self.assertFalse(exe.start(row, timeout=True)[0])
        self.assertTrue(exe.start(row)[0])
        self.assertFalse(exe.start(row)[0])
        self.worker.drain()
        self.assertIsNone(exe.poll().status)
        self.assertFalse(exe.start(row, timeout=31)[0])

    def test_close_never_closes_shared_worker_or_client(self):
        exe = self.executor()
        self.assertTrue(exe.start(self.row())[0])
        exe.close()
        self.assertFalse(exe.pending)
        self.assertFalse(exe.start(self.row())[0])
        self.worker.drain()
        self.assertEqual(self.client.requests, [])

    def test_information_extractors_are_bounded_and_structured(self):
        self.assertEqual(_read_fields('S02', {'result': {'cpu_temp': 45.3}}),
                         (('cpu_temp_c', 45.3),))
        self.assertEqual(_read_fields('S03', {'result': {'throttled_state': {'bits': 0}}}),
                         (('throttled_bits', 0),))
        self.assertEqual(_read_fields('S03', {'result': {'throttled_state': {'bits': True}}}), ())
        self.assertEqual(_read_fields('S08', {'result': {
            'status': {'webhooks': {'state': 'ready'}}}}),
            (('webhooks_state', 'ready'),))
        self.assertEqual(_read_fields('S10', {'result': {
            'job_totals': {'total_jobs': 5, 'total_time': 123}}}),
            (('total_jobs', 5), ('total_time', 123)))
        self.assertEqual(_read_fields('S05', {'result': {
            'network': {'eth0': {'rx_bytes': 50, 'tx_bytes': 20}}}}),
            (('eth0.rx_bytes', 50), ('eth0.tx_bytes', 20)))
        self.assertEqual(_read_fields('S01', {'error': 'unauthorized'}), ())
        self.assertEqual(_read_fields('S02', {'result': {'cpu_temp': True}}), ())


if __name__ == '__main__':
    unittest.main()
