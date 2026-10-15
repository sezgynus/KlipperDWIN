"""CI-only guarded actuator pipeline tests using fakes (never a real Pi)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, _add
from maintenance_physical import MaintenancePulseController


class Worker:
    def __init__(self): self.jobs = []
    def submit(self, work, queue_timeout=None):
        future = Future(); self.jobs.append((future, work)); return future
    def next(self):
        future, fn = self.jobs.pop(0)
        if future.set_running_or_notify_cancel():
            try: future.set_result(fn())
            except Exception as error: future.set_exception(error)


class Client:
    def __init__(self):
        self.paths = []
        self.status = {'fan': {'speed': .35}}
        self.queue = {'queue_state': 'ready', 'queued_jobs': []}
        self.components = ['job_queue']
    def get(self, path):
        self.paths.append(path)
        if path == '/server/info': return {'result': {'components': self.components}}
        if path == '/server/job_queue/status': return {'result': self.queue}
        if path.startswith('/printer/objects/query?'):
            return {'result': {'status': self.status}}
        raise AssertionError('Unexpected GET')
    def post(self, *a, **k):
        raise AssertionError('must go via guarded printer transport')


def setup():
    settings = {'fan': {'pin': 'PA3'}}
    snapshot = MaintenanceSnapshot(
        4, (DeviceCapabilities('fan', 'fan', _add(0, 'F01', USER)),),
        0, id(settings))
    current = {'state': 'ready', 'epoch': 4, 'settings': settings,
               'status': {'webhooks': {'state': 'ready'},
                          'print_stats': {'state': 'standby'},
                          'virtual_sdcard': {'is_active': False},
                          'pause_resume': {'is_paused': False}}}
    # Real PrinterState is immutable and config ID must match snapshot.
    from printer_state import PrinterState
    state = PrinterState.from_snapshot(current)
    snapshot = MaintenanceSnapshot(snapshot.epoch, snapshot.devices, 0,
                                   id(state.settings))
    owners = {key: SimpleNamespace(pending=None, phase='idle')
              for key in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session')}
    printer = SimpleNamespace(
        state=state, connection_error=None,
        subscription=SimpleNamespace(
            snapshot=Mock(return_value=current),
            lifecycle=Mock(return_value={'state': 'ready', 'epoch': 4})),
        maintenance=SimpleNamespace(snapshot=snapshot),
        maintenance_reader=SimpleNamespace(pending=False),
        jog_recovery_required=False, _jog_restore=None,
        _settings_save=None, **owners)
    # The fake subscription returns this *live* raw status, but config ID
    # is provided by PrinterData.state as in production.
    client, worker = Client(), Worker()
    pending = []
    def send(path, json, dispatch_guard=None, **kwargs):
        assert path == '/printer/gcode/script'
        future = Future()
        pending.append((future, json, dispatch_guard))
        return future
    printer.postREST = send
    return printer, client, worker, pending


class PhysicalControllerTests(unittest.TestCase):
    def setUp(self):
        self.printer, self.client, self.worker, self.commands = setup()
        self.runner = MaintenancePulseController(self.printer, self.worker, self.client)

    def prepare(self):
        self.assertEqual(self.runner.start('F01', 'fan'), (True, 'preflight_queued'))
        self.assertIsNone(self.runner.poll())
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')

    def test_explicit_second_confirmation_and_verified_restore_then_user_result(self):
        self.prepare()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.runner.confirm(), (True, 'bounded_pulse_queued'))
        self.assertEqual(len(self.commands), 1)
        future, payload, guard = self.commands[0]
        self.assertIn('G4 P950', payload['script'])
        self.assertIn('M106 S89', payload['script'])
        self.assertTrue(guard())
        future.set_result({'result': 'ok'})
        self.assertIsNone(self.runner.poll())
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertIn('fan rotate', self.runner.observation_prompt)
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'PASSED_USER')
        self.assertTrue(result.restore_verified)
        self.assertEqual(result.reason, 'explicit_user_observation')
        self.assertFalse(self.runner.pending)

    def test_no_observation_no_hardware_pass(self):
        self.prepare()
        self.assertIsNone(self.runner.observe(True))
        self.assertEqual(self.runner.cancel().status, 'ABORTED')
        self.assertEqual(self.commands, [])

    def test_print_or_queue_activity_deny_before_dispatch(self):
        self.prepare()
        current = self.printer.subscription.snapshot.return_value
        current['status']['print_stats']['state'] = 'printing'
        self.assertFalse(self.runner.confirm()[0])
        self.assertEqual(self.commands, [])
        current['status']['print_stats']['state'] = 'standby'
        self.client.queue['queued_jobs'] = [{'filename': 'private.gcode'}]
        self.assertTrue(self.runner.start('F01', 'fan')[0])
        self.worker.next()
        self.assertEqual(self.runner.poll().status, 'BLOCKED')
        self.assertEqual(self.commands, [])

    def test_dispatch_guard_rechecks_live_status(self):
        self.prepare()
        self.assertTrue(self.runner.confirm()[0])
        self.printer.subscription.snapshot.return_value['status']['print_stats']['state'] = 'printing'
        self.assertFalse(self.commands[0][2]())

    def test_command_or_restore_error_never_claims_pass(self):
        self.prepare()
        self.runner.confirm()
        self.commands[0][0].set_result({'result': 'ok'})
        self.client.status['fan']['speed'] = .75
        self.runner.poll(); self.worker.next()
        self.assertEqual(self.runner.poll().status, 'INCONCLUSIVE')
        self.assertIsNone(self.runner.observe(True))

    def test_running_cancel_waits_for_full_script_then_aborts(self):
        self.prepare()
        self.runner.confirm()
        self.assertIsNone(self.runner.cancel())
        self.assertTrue(self.runner.pending)
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll(); self.worker.next()
        self.assertEqual(self.runner.poll().status, 'ABORTED')

    def test_unregistered_and_busy_read_blocked(self):
        self.assertFalse(self.runner.start('F01', 'wrong')[0])
        self.assertFalse(self.runner.start('S18')[0])
        self.printer.maintenance_reader.pending = True
        self.assertFalse(self.runner.start('F01', 'fan')[0])
        self.assertEqual(self.commands, [])
        self.runner.close()
        self.assertFalse(self.runner.start('F01', 'fan')[0])


if __name__ == '__main__':
    unittest.main()
