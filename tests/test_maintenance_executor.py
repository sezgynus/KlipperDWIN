"""CI-only bounded Maintenance read executor and evidence contracts."""
from concurrent.futures import Future
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, AUTOMATIC, INFORMATION, _add
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


class DriverSubscription:
    def __init__(self):
        self.history=[]
        self.serial=0
        self.calls=[]
        self.done=Future()
        self.guard=None
    def responses_since(self, cursor):
        return self.serial, tuple(self.history[cursor:] if cursor is not None else ())
    def request(self, method, params, guard=None, request_timeout=None):
        self.calls.append((method, params, request_timeout))
        self.guard=guard
        return self.done
    def reply(self, text, done=True):
        self.history.append(text)
        self.serial+=1
        if done:
            self.done.set_result('ok')


class DirectTmcReadTests(unittest.TestCase):
    context = ReadExecutorTests.context
    def setUp(self):
        ReadExecutorTests.setUp(self)
        self.driver='tmc2208 stepper_x'
        self.state.objects=(self.driver,)
        self.snapshot=MaintenanceSnapshot(
            33,
            (DeviceCapabilities(self.driver,'driver',
                _add(0,'M07',AUTOMATIC | INFORMATION)),),
            config_marker=id(self.settings))
        self.subscription=DriverSubscription()

    def executor(self):
        return MaintenanceReadExecutor(self.worker,self.client,
            self.context,lambda:self.snapshot,subscription=self.subscription)

    def row(self):
        return next(r for r in visible_plan(build_plan(
            self.snapshot,read_only_adapters())) if r.feature_id=='M07')

    def test_homing_not_required_and_disabled_driver_has_direct_register(self):
        # Only READY/idle safety matters; no toolhead.homed_axes in context.
        exe=self.executor()
        self.assertEqual(exe.start(self.row()),(True,'scheduled'))
        self.assertFalse(self.worker.tasks)
        self.assertEqual(self.client.requests,[])
        method,params,timeout=self.subscription.calls[0]
        self.assertEqual(method,'printer.gcode.script')
        self.assertEqual(params,{'script':'DUMP_TMC STEPPER=stepper_x REGISTER=DRV_STATUS'})
        self.assertEqual(timeout,3.0)
        self.assertTrue(self.subscription.guard())
        self.assertIsNone(exe.poll())
        self.subscription.reply('DRV_STATUS: c0120000 cs_actual=18 stealth=1 stst=1')
        result=exe.poll()
        self.assertIsNone(result.status)
        self.assertEqual(result.reason,'observed_information')
        self.assertIn(('register_hex','C0120000'),result.evidence)
        self.assertIn(('fault_count',0),result.evidence)
        self.assertIn(('standstill',1),result.evidence)
        self.assertEqual(result.source,'printer.gcode.script:DUMP_TMC')

    def test_stale_console_lines_are_not_reused_as_driver_evidence(self):
        self.subscription.history=['DRV_STATUS: c0120000']
        self.subscription.serial=1
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.subscription.reply('unrelated console reply')
        self.assertIsNone(exe.poll())
        exe._deadline=0
        result=exe.poll()
        self.assertEqual(result.status,'INCONCLUSIVE')
        self.assertEqual(result.reason,'register_output_missing')
        self.assertFalse(any(k=='fault_count' for k,_ in result.evidence))

    def test_uart_read_failure_is_not_reported_as_clean(self):
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.subscription.reply('Unable to read tmc uart stepper_x register DRV_STATUS')
        result=exe.poll()
        self.assertEqual(result.status,'ERROR')
        self.assertEqual(result.reason,'tmc_communication_error')
        self.assertEqual(result.evidence,())

    def test_rpc_failure_and_stale_state_never_emit_fault_free_evidence(self):
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.subscription.done.set_exception(RuntimeError('UART disconnected'))
        self.assertEqual(exe.poll().reason,'tmc_register_read_failed')
        self.subscription=DriverSubscription()
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.state.status['print_stats']['state']='printing'
        self.assertFalse(self.subscription.guard())
        self.assertEqual(exe.poll().status,'ABORTED')

    def test_concurrent_driver_responses_are_ambiguous(self):
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.subscription.reply('DRV_STATUS: c0120000',done=False)
        self.subscription.reply('DRV_STATUS: c0000000',done=True)
        exe._deadline=0
        self.assertEqual(exe.poll().status,'INCONCLUSIVE')

    def test_cancel_disowns_late_register_reply(self):
        exe=self.executor()
        self.assertTrue(exe.start(self.row())[0])
        self.assertEqual(exe.cancel().status,'ABORTED')
        self.subscription.reply('DRV_STATUS: c0120000',done=False)
        self.assertIsNone(exe.poll())



if __name__ == '__main__':
    unittest.main()
