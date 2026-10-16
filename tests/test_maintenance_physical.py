"""CI-only guarded actuator pipeline tests using fakes (never a real Pi)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
from unittest.mock import Mock, patch
from time import monotonic
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, _add
from maintenance_physical import MaintenancePulseController
from maintenance_profiles import approved_integrations
from maintenance_discovery import discover
from printer_state import PrinterState


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
        self.raw_config = {}
    def get(self, path):
        self.paths.append(path)
        if path == '/server/info': return {'result': {'components': self.components}}
        if path == '/server/job_queue/status': return {'result': self.queue}
        if path == '/printer/objects/query?configfile':
            return {'result': {'status': {'configfile': {'config': self.raw_config}}}}
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
        self.clock = [monotonic()]
        self.clock_patch = patch('maintenance_physical.monotonic',
                                 side_effect=lambda: self.clock[0])
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)

    def advance(self, seconds):
        self.clock[0] += seconds

    def poll_verify(self):
        # A single verification read must never imply restored physical output.
        self.assertIsNone(self.runner.poll())
        self.worker.next()
        self.assertIsNone(self.runner.poll())

    def verify_ready(self):
        self.advance(1.4)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')

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
        self.assertEqual(self.worker.jobs, [])  # Never GET immediately on POST ack.
        self.verify_ready()
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
        self.runner.poll()
        self.advance(1.4)
        for _ in range(3):
            self.poll_verify()
            self.advance(.35)
        self.advance(6)
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertEqual(result.reason, 'restore_value_mismatch')
        self.assertIsNone(self.runner.observe(True))
        self.assertEqual(len(self.commands), 1)

    def test_running_cancel_waits_for_full_script_then_aborts(self):
        self.prepare()
        self.runner.confirm()
        self.assertIsNone(self.runner.cancel())
        self.assertTrue(self.runner.pending)
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(1.4)
        self.poll_verify()
        self.advance(.35)
        self.assertIsNone(self.runner.poll())
        self.worker.next()
        result = self.runner.poll()
        self.assertEqual(result.status, 'ABORTED')
        self.assertEqual(result.reason, 'user_cancelled_after_restore')
        self.assertTrue(result.restore_verified)

    def test_delayed_restore_recovers_without_second_gcode_dispatch(self):
        self.prepare()
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.client.status['fan']['speed'] = .75
        self.advance(1.4)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        # Moonraker now reports the completed restore; require TWO stable reads.
        self.client.status['fan']['speed'] = .35
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.assertIsNone(self.runner.observe(True))
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertEqual(self.runner.observe(True).status, 'PASSED_USER')
        self.assertEqual(len(self.commands), 1)

    def test_early_baseline_while_script_queued_never_autopasses(self):
        self.client.status['fan']['speed'] = 0
        self.prepare()
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'queued'})
        self.runner.poll()
        # HTTP returned instantly; no read until the full pulse time has passed.
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.worker.jobs, [])
        self.advance(.40)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.worker.jobs, [])
        # A single baseline sample might predate the actuator dispatch.
        self.advance(1.0)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.client.status['fan']['speed'] = .75
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        # Even another baseline match requires two consecutive post-delay reads.
        self.client.status['fan']['speed'] = 0
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertEqual(len(self.commands), 1)

    def test_session_change_during_verify_is_distinct_from_value_mismatch(self):
        self.prepare()
        self.runner.confirm()
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.printer.subscription.snapshot.return_value['state'] = 'disconnected'
        self.printer.state = type(self.printer.state).from_snapshot({
            **self.printer.subscription.snapshot.return_value,
            'settings': {'fan': {'pin': 'PA3'}}})
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertEqual(result.reason, 'state_changed_during_restore_check')
        self.assertEqual(self.worker.jobs, [])
        self.assertEqual(len(self.commands), 1)

    def test_unavailable_get_retries_but_never_produces_false_pass(self):
        self.prepare()
        self.runner.confirm()
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(1.4)
        with patch.object(self.client, 'get', side_effect=OSError('temporary GET outage')):
            for _ in range(3):
                self.poll_verify()
                self.advance(.35)
            self.advance(6)
            result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertEqual(result.reason, 'restore_readback_unavailable')
        self.assertEqual(len(self.commands), 1)

    def configure_config_only_buzzer(self):
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = {'pwm_cycle_time buzzer': {
            'pin': 'PB13', 'value': 0.0, 'shutdown_value': 0.0,
            'scale': 1.0, 'cycle_time': 0.001}}
        raw['objects'] = ('webhooks',)  # Excluded from objects/list by Klipper.
        self.printer.state = PrinterState.from_snapshot(raw)
        self.client.raw_config = {'pwm_cycle_time Buzzer': {'pin': 'PB13'}}
        services = approved_integrations(self.printer.state,
                                         (False, 'buzzer', '', ''))
        self.printer.maintenance.snapshot = discover(self.printer.state, services)
        self.assertIn('S18', self.printer.maintenance.snapshot.available_features())
        self.assertTrue(any(row.feature_id == 'S18' for row in self.runner.available()))

    def test_s18_uses_profile_not_lcd_settings_and_has_no_readback_claim(self):
        self.configure_config_only_buzzer()
        self.assertEqual(self.runner.start('S18'), (True, 'preflight_queued'))
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertFalse(any(path.startswith('/printer/objects/query?')
                             and path != '/printer/objects/query?configfile'
                             for path in self.client.paths))
        self.assertEqual(self.runner.confirm(), (True, 'bounded_pulse_queued'))
        self.assertEqual(len(self.commands), 1)
        self.assertIn('SET_PIN PIN=Buzzer VALUE=0', self.commands[0][1]['script'])
        self.assertNotIn('PIN=buzzer', self.commands[0][1]['script'])
        self.assertTrue(self.commands[0][2]())
        self.commands[0][0].set_result({'result': 'ok'})
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'verifying')
        self.advance(.8)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertFalse(any(path.startswith('/printer/objects/query?')
                             and path != '/printer/objects/query?configfile'
                             for path in self.client.paths))
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
        self.assertIn('no_readback', result.reason)

    def test_s18_missing_or_mismatched_original_name_blocks_without_gcode(self):
        from maintenance_physical import _resolve_buzzer_gcode_name
        self.configure_config_only_buzzer()
        settings = self.printer.state.settings['pwm_cycle_time buzzer']
        self.assertEqual(_resolve_buzzer_gcode_name(
            self.client, 'pwm_cycle_time buzzer', settings), 'Buzzer')
        bad = (
            {},
            {'pwm_cycle_time BUZZER': {'pin': 'PA3'}},
            {'pwm_cycle_time Buzzer': {'pin': 'PB13'},
             'pwm_cycle_time buzzer': {'pin': 'PB13'}},
            {'pwm_cycle_time buzzer\nM112': {'pin': 'PB13'}},
        )
        for raw in bad:
            with self.subTest(raw=raw):
                self.client.raw_config = raw
                self.assertTrue(self.runner.start('S18')[0])
                self.worker.next()
                result = self.runner.poll()
                self.assertEqual(result.status, 'BLOCKED')
                self.assertEqual(result.reason, 'preflight_failed')
                self.assertEqual(self.commands, [])
        self.client.raw_config = {'pwm_cycle_time Buzzer': {'pin': 'PB13'}}
        self.assertTrue(self.runner.start('S18')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertEqual(self.runner.cancel().status, 'ABORTED')

    def test_s18_cannot_start_with_wrong_profile_or_claim_automatic_pass(self):
        self.configure_config_only_buzzer()
        self.assertEqual(self.runner.start('S18', buzzer_output='heater'),
                         (False, 'buzzer_profile_missing_or_mismatch'))
        self.assertEqual(self.commands, [])
        self.assertEqual(self.runner.start('S18'), (True, 'preflight_queued'))
        self.worker.next()
        self.runner.poll()
        self.runner.confirm()
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(.8)
        self.runner.poll()
        result = self.runner.observe(False)
        self.assertEqual(result.status, 'FAILED_USER')
        self.assertFalse(result.restore_verified)
        self.assertEqual(len(self.commands), 1)

    def test_petrel_backend_creates_opt_in_physical_controller(self):
        from test_regressions import backend
        from unittest.mock import patch
        from read_fixture import ImmediateReadWorker
        import tempfile
        with patch.object(backend, 'MoonrakerClient'), \
                patch.object(backend, 'MoonrakerSubscription'), \
                patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            pd = backend.PrinterData(
                settings_path=tempfile.mktemp(prefix='petrel-physical-', suffix='.json'))
        self.assertIs(pd.maintenance_pulse._printer, pd)
        self.assertIs(pd.maintenance_pulse._worker, pd._maintenance_worker)
        self.assertFalse(pd.maintenance_pulse.pending)
        self.assertFalse(pd.start_maintenance_physical('F01', 'fan')[0])
        self.assertIsNone(pd.poll_maintenance_physical())
        pd.close()

    def test_physical_runner_blocks_power_off_and_print_start(self):
        from test_regressions import backend
        pd = backend.PrinterData.__new__(backend.PrinterData)
        pd.maintenance_pulse = SimpleNamespace(pending=True)
        self.assertEqual(pd.power_off_block_reason(),
                         'Maintenance operation is active')
        with self.assertRaisesRegex(ValueError, 'Maintenance'):
            pd.openAndPrintFile('test.gcode')

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
