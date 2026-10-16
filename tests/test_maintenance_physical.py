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
        future.request_timeout = kwargs.get('request_timeout')
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
        self.assertIsNone(future.request_timeout)
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

    def test_unanswered_initial_consent_stays_open_and_refreshes_on_click(self):
        # Both evidence freshness and controller deadlines use one virtual
        # clock; advancing a fake UI clock must not leave queue GETs on wall time.
        runtime_clock = patch('maintenance_runtime.monotonic',
                              side_effect=lambda: self.clock[0])
        runtime_clock.start()
        self.addCleanup(runtime_clock.stop)
        self.prepare()
        # Neither the gate's three-second proof freshness nor elapsed time
        # should silently end the menu's human-decision phase.
        self.advance(3600)
        for _ in range(5):
            self.assertIsNone(self.runner.poll())
            self.assertEqual(self.runner.phase, 'await_confirmation')
            self.assertEqual(self.commands, [])
        # Late click refreshes read-only evidence without dispatching.
        self.assertEqual(self.runner.confirm(), (True, 'preflight_queued'))
        self.assertEqual(self.runner.phase, 'preflight')
        self.assertEqual(self.commands, [])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        # Second deliberate click now uses fresh guard and queues a pulse.
        self.assertEqual(self.runner.confirm(), (True, 'bounded_pulse_queued'))
        self.assertEqual(len(self.commands), 1)

    def test_unanswered_restored_fan_observation_never_expires(self):
        self.prepare()
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'ok'})
        self.assertIsNone(self.runner.poll())
        self.verify_ready()
        self.advance(3600)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertTrue(self.runner.pending)
        self.assertEqual(self.runner.observe(True).status, 'PASSED_USER')
        self.assertEqual(len(self.commands), 1)

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
        raw['settings'] = {'pwm_cycle_time alarm': {
            'pin': 'PB13', 'value': 0.0, 'shutdown_value': 0.0,
            'scale': 1.0, 'cycle_time': 0.001}}
        raw['objects'] = ('webhooks',)  # Excluded from objects/list by Klipper.
        self.printer.state = PrinterState.from_snapshot(raw)
        self.client.raw_config = {'pwm_cycle_time Alarm': {'pin': 'PB13'}}
        services = approved_integrations(self.printer.state,
                                         (('audible', 'pwm_cycle_time alarm'),))
        self.printer.maintenance.snapshot = discover(self.printer.state, services)
        self.assertIn('S18', self.printer.maintenance.snapshot.available_features())
        self.assertTrue(any(row.feature_id == 'S18' for row in self.runner.available()))

    def test_s18_uses_profile_not_lcd_settings_and_has_no_readback_claim(self):
        self.configure_config_only_buzzer()
        self.assertEqual(self.runner.start('S18', 'pwm_cycle_time alarm'), (True, 'preflight_queued'))
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertFalse(any(path.startswith('/printer/objects/query?')
                             and path != '/printer/objects/query?configfile'
                             for path in self.client.paths))
        self.assertEqual(self.runner.confirm(), (True, 'bounded_pulse_queued'))
        self.assertEqual(len(self.commands), 1)
        self.assertIn('SET_PIN PIN=Alarm VALUE=0', self.commands[0][1]['script'])
        self.assertNotIn('PIN=alarm', self.commands[0][1]['script'])
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

    def test_s18_user_observation_never_expires_and_does_not_invent_restore(self):
        self.configure_config_only_buzzer()
        self.assertTrue(self.runner.start('S18', 'pwm_cycle_time alarm')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(len(self.commands), 1)
        self.assertTrue(self.commands[0][2]())
        self.commands[0][0].set_result({'result': 'ok'})
        self.assertIsNone(self.runner.poll())
        self.advance(.8)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_observation')
        self.advance(60 * 60)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertTrue(self.runner.pending)
        self.assertEqual(len(self.commands), 1)
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
        self.assertEqual(len(self.commands), 1)

    def test_f12_kick_start_preflight_blocks_before_consent_or_gcode(self):
        from maintenance_discovery import _add, DeviceCapabilities, USER, MaintenanceSnapshot
        old = self.printer.maintenance.snapshot
        self.printer.maintenance.snapshot = MaintenanceSnapshot(
            old.epoch, (DeviceCapabilities('fan', 'fan', _add(0, 'F12', USER)),),
            old.global_modes, old.config_marker, old.service_key)
        self.client.status['fan']['speed'] = 0.0
        self.assertEqual(self.runner.start('F12', 'fan'),
                         (True, 'preflight_queued'))
        self.worker.next()
        result = self.runner.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'f12_kick_start_active')
        self.assertEqual(self.commands, [])
        self.assertFalse(self.runner.pending)

    def test_f12_five_separately_verified_stages_and_next_round(self):
        # Match the queue evidence clock to the controller's simulated clock.
        runtime_clock = patch('maintenance_runtime.monotonic',
                              side_effect=lambda: self.clock[0])
        runtime_clock.start()
        self.addCleanup(runtime_clock.stop)
        from maintenance_discovery import _add, DeviceCapabilities, USER, MaintenanceSnapshot
        old = self.printer.maintenance.snapshot
        self.printer.maintenance.snapshot = MaintenanceSnapshot(
            old.epoch, (DeviceCapabilities('fan', 'fan', _add(0, 'F12', USER)),),
            old.global_modes, old.config_marker, old.service_key)
        # Override the effective immutable Klipper config for this F12 test:
        # only an explicitly disabled kick_start_time permits calibration.
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = {'fan': {'pin': 'PA3', 'kick_start_time': 0.0}}
        self.printer.state = PrinterState.from_snapshot(raw)
        self.printer.maintenance.snapshot = MaintenanceSnapshot(
            old.epoch, self.printer.maintenance.snapshot.devices,
            old.global_modes, id(self.printer.state.settings), old.service_key)
        self.client.status['fan']['speed'] = 0.0
        self.assertEqual(self.runner.start('F12', 'fan'), (True, 'preflight_queued'))
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.runner.pwm_levels, ())
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(self.runner.f12_status[:3], (1, 1, 25))
        self.assertEqual(len(self.commands), 1)
        for i, pwm in enumerate((25, 50, 76, 101, 127)):
            with self.subTest(stage=i + 1):
                self.assertEqual(self.runner.phase, 'running')
                future, payload, guard = self.commands[i]
                self.assertEqual(future.request_timeout, 9.0)
                self.assertTrue(guard())
                self.assertIn('M106 S%d' % pwm, payload['script'])
                self.assertTrue(payload['script'].endswith('M106 S0\nM400'))
                self.assertEqual(payload['script'].count('G4 P2000'), 1)
                future.set_result({'result': 'ok'})
                self.assertIsNone(self.runner.poll())
                self.advance(4.1)
                self.poll_verify()
                self.advance(.35)
                self.poll_verify()
                if i < 4:
                    self.assertEqual(self.runner.phase, 'f12_next_preflight')
                    self.assertEqual(len(self.commands), i + 1)
                    self.worker.next()
                    self.assertIsNone(self.runner.poll())
                    self.assertEqual(len(self.commands), i + 2)
                    self.assertEqual(self.runner.f12_status[:3],
                                     (1, i + 2, (25, 50, 76, 101, 127)[i + 1]))
                else:
                    self.assertEqual(self.runner.phase, 'await_observation')
        self.assertIsNone(self.runner.observe(4))
        self.assertEqual(self.runner.phase, 'f12_await_stop')
        self.assertEqual(len(self.commands), 5)
        self.advance(3600)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'f12_await_stop')
        self.assertEqual(len(self.commands), 5)
        result, why = self.runner.f12_confirm_stopped()
        self.assertTrue(result)
        self.assertEqual(why, 'preflight_queued')
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(self.runner.f12_status[:3], (2, 1, 81))
        self.assertEqual(len(self.commands), 6)
        self.assertIn('M106 S81', self.commands[5][1]['script'])

    def test_f02_user_observed_speed_steps_with_verified_restore(self):
        # Reuse the same bounded consent/dispatch/readback lifecycle as F01.
        from maintenance_discovery import _add, DeviceCapabilities, USER, MaintenanceSnapshot
        old = self.printer.maintenance.snapshot
        self.printer.maintenance.snapshot = MaintenanceSnapshot(
            old.epoch, (DeviceCapabilities('fan', 'fan',
                        _add(0, 'F02', USER)),),
            old.global_modes, old.config_marker, old.service_key)
        self.assertTrue(self.runner.start('F02', 'fan')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertTrue(self.runner.confirm()[0])
        future, payload, guard = self.commands[0]
        self.assertEqual(payload['script'].count('G4 P2000'), 3)
        self.assertEqual(future.request_timeout, 10.0)
        self.assertTrue(guard())
        # Binary float subtraction can yield 13.999999999999993.
        # Keep the 14-second lower bound with nanosecond-only test tolerance.
        self.assertGreaterEqual(self.runner._deadline - self.clock[0] + 1e-9, 14.0)
        future.set_result({'result': 'ok'})
        self.assertIsNone(self.runner.poll())
        self.advance(5.9)
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'verifying')
        self.assertEqual(self.worker.jobs, [])  # No early restore read.
        self.advance(.6)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertIn('low/mid/high', self.runner.observation_prompt)
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'PASSED_USER')
        self.assertTrue(result.restore_verified)

    def test_s18_missing_or_mismatched_original_name_blocks_without_gcode(self):
        from maintenance_physical import _resolve_pin_gcode_name
        self.configure_config_only_buzzer()
        settings = self.printer.state.settings['pwm_cycle_time alarm']
        self.assertEqual(_resolve_pin_gcode_name(
            self.client, 'pwm_cycle_time alarm', settings), 'Alarm')
        bad = (
            {},
            {'pwm_cycle_time ALARM': {'pin': 'PA3'}},
            {'pwm_cycle_time Alarm': {'pin': 'PB13'},
             'pwm_cycle_time alarm': {'pin': 'PB13'}},
            {'pwm_cycle_time alarm\nM112': {'pin': 'PB13'}},
        )
        for raw in bad:
            with self.subTest(raw=raw):
                self.client.raw_config = raw
                self.assertTrue(self.runner.start('S18', 'pwm_cycle_time alarm')[0])
                self.worker.next()
                result = self.runner.poll()
                self.assertEqual(result.status, 'BLOCKED')
                self.assertEqual(result.reason, 'preflight_failed')
                self.assertEqual(self.commands, [])
        self.client.raw_config = {'pwm_cycle_time Alarm': {'pin': 'PB13'}}
        self.assertTrue(self.runner.start('S18', 'pwm_cycle_time alarm')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertEqual(self.runner.cancel().status, 'ABORTED')

    def test_s18_cannot_start_with_wrong_profile_or_claim_automatic_pass(self):
        self.configure_config_only_buzzer()
        self.assertEqual(self.runner.start('S18', 'pwm_cycle_time heater'),
                         (False, 'test_not_discovered_or_allowed'))
        self.assertEqual(self.commands, [])
        self.assertEqual(self.runner.start('S18', 'pwm_cycle_time alarm'), (True, 'preflight_queued'))
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

    def test_generic_visual_output_uses_raw_pin_name_and_verifies_restore(self):
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = {'output_pin enclosure': {
            'pin': 'PC9', 'pwm': True, 'scale': 1}}
        raw['objects'] = ('output_pin enclosure',)
        self.printer.state = PrinterState.from_snapshot(raw)
        self.client.raw_config = {'output_pin Enclosure': {'pin': 'PC9'}}
        self.client.status = {'output_pin enclosure': {'value': .3}}
        services = approved_integrations(
            self.printer.state, (('visual', 'output_pin enclosure'),))
        self.printer.maintenance.snapshot = discover(self.printer.state, services)
        self.assertEqual(self.runner.start('O03', 'output_pin enclosure'),
                         (True, 'preflight_queued'))
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertTrue(self.runner.confirm()[0])
        self.assertIn('SET_PIN PIN=Enclosure VALUE=0.7000',
                      self.commands[0][1]['script'])
        self.assertIn('SET_PIN PIN=Enclosure VALUE=0.3000',
                      self.commands[0][1]['script'])
        self.assertTrue(self.commands[0][2]())
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        # Leave a scheduling margin beyond duration + dispatch floor.
        # Checking exactly at the floating-point deadline is racy.
        self.advance(1.3)
        self.poll_verify()
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        self.assertEqual(self.runner.observe(True).status, 'PASSED_USER')

    def test_visual_output_pin_identity_mismatch_blocks_without_gcode(self):
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = {'output_pin enclosure': {
            'pin': 'PC9', 'pwm': True, 'scale': 1}}
        raw['objects'] = ('output_pin enclosure',)
        self.printer.state = PrinterState.from_snapshot(raw)
        self.client.raw_config = {'output_pin Enclosure': {'pin': 'PC8'}}
        self.client.status = {'output_pin enclosure': {'value': .3}}
        services = approved_integrations(
            self.printer.state, (('visual', 'output_pin enclosure'),))
        self.printer.maintenance.snapshot = discover(self.printer.state, services)
        self.assertTrue(self.runner.start('O03', 'output_pin enclosure')[0])
        self.worker.next()
        self.assertEqual(self.runner.poll().status, 'BLOCKED')
        self.assertEqual(self.commands, [])

    def configure_led_chain(self, *, managed=False):
        from maintenance_discovery import discover
        raw = self.printer.subscription.snapshot.return_value
        lights = [(0.0, 0.0, 0.3, 0.0), (0.1, 0.2, 0.0, 0.0),
                  (0.0, 0.35, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)]
        raw['settings'] = {'neopixel diagnostic': {
            'pin': 'PA7', 'chain_count': 4, 'color_order': ['GRB']}}
        if managed:
            raw['settings']['mmu_leds unit0'] = {
                'exit_leds': 'neopixel:diagnostic (1-4)'}
            raw['settings']['mmu_machine'] = {'units': ['unit0']}
        raw['objects'] = (('neopixel diagnostic', 'mmu_leds unit0',
                           'mmu_machine', 'mmu')
                          if managed else ('neopixel diagnostic',))
        self.printer.state = PrinterState.from_snapshot(raw)
        self.client.status = {'neopixel diagnostic': {'color_data': lights}}
        if managed:
            self.client.status.update({
                'mmu_leds unit0': {'enabled': True, 'animation': True, 'exit': 4},
                'mmu_machine': {
                    'num_units': 1, 'unit_0': {'name': 'unit0'}},
                'mmu': {'action': 'Idle'}})
        roles = approved_integrations(
            self.printer.state, (('led', 'neopixel diagnostic'),))
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        return lights

    def test_multi_led_physical_pipeline_requires_two_consents_and_full_restore(self):
        colors = self.configure_led_chain()
        self.assertEqual(self.runner.start('O04', 'neopixel diagnostic'),
                         (True, 'preflight_queued'))
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(len(self.commands), 1)
        script = self.commands[0][1]['script']
        self.assertIn('INDEX=4 TRANSMIT=1 SYNC=0', script)
        self.assertEqual(script.count('TRANSMIT=1'), 5)
        self.assertEqual(script.count('G4 P650'), 4)
        self.assertTrue(self.commands[0][2]())
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(3.1)
        self.poll_verify()
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        outcome = self.runner.observe(True)
        self.assertEqual(outcome.status, 'PASSED_USER')
        self.assertTrue(outcome.restore_verified)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.client.status['neopixel diagnostic']['color_data'],
                         colors)

    def test_multi_led_incomplete_restore_never_reports_pass(self):
        self.configure_led_chain()
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.runner.poll()
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        # Last LED did not restore, although the other three did.
        self.client.status['neopixel diagnostic']['color_data'][3] = (1., 0., 0., 0.)
        self.advance(3.1)
        for _ in range(3):
            self.poll_verify()
            self.advance(.35)
        self.advance(6)
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertFalse(result.restore_verified)
        self.assertIsNone(self.runner.observe(True))
        self.assertEqual(len(self.commands), 1)

    def test_managed_mmu_chain_uses_its_own_timed_effect_no_raw_led(self):
        self.configure_led_chain(managed=True)
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(len(self.commands), 1)
        script = self.commands[0][1]['script']
        self.assertEqual(len(script.splitlines()), 12)
        expected = [(1., 0., 0.), (0., 0., 1.),
                    (0., 1., 0.), (1., 1., 1.)]
        for phase, rgb in enumerate(expected):
            command, dwell, barrier = script.splitlines()[phase * 3:phase * 3 + 3]
            self.assertEqual(
                command,
                'MMU_SET_LED UNIT=0 EXIT_EFFECT=(%.3f,%.3f,%.3f) '
                'DURATION=0.40 FADETIME=0' % rgb)
            self.assertEqual(dwell, 'G4 P650')
            self.assertEqual(barrier, 'M400')
        self.assertEqual(script.count('M400'), 4)
        self.assertNotIn('SET_LED LED=', script)
        self.assertNotIn('MMU_LED QUIET', script)
        self.assertNotIn('SET_LED LED=', script)
        self.assertEqual(script.count('DURATION=0.40'), 4)
        self.assertAlmostEqual(self.commands[0][0].request_timeout, 6.6)
        self.assertTrue(self.commands[0][2]())
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(3.1)
        self.poll_verify()
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
        self.assertEqual(self.client.status['mmu_leds unit0'],
                         {'enabled': True, 'animation': True, 'exit': 4})

    def test_hh_auto_discovered_live_machine_status_preflight_and_user_consent(self):
        self.configure_led_chain(managed=True)
        raw = self.printer.subscription.snapshot.return_value
        raw['settings']['mmu_machine'] = {}  # effective Klipper settings omit units
        raw['status']['mmu_machine'] = {
            'num_units': 1, 'unit_0': {'name': 'OpenEYE MMU'}}
        self.client.status['mmu_machine']['unit_0']['name'] = 'OpenEYE MMU'
        self.printer.state = PrinterState.from_snapshot(raw)
        roles = approved_integrations(self.printer.state, ())
        self.assertIn('maintenance.safe_led:neopixel diagnostic', roles)
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertEqual(self.runner.phase, 'await_confirmation')
        self.assertEqual(self.commands, [])
        self.assertTrue(self.runner.confirm()[0])
        self.assertEqual(len(self.commands), 1)
        command = self.commands[0][1]['script']
        self.assertIn('MMU_SET_LED UNIT=0 EXIT_EFFECT=', command)
        self.assertEqual(command.count('M400'), 4)
        self.assertNotIn('UNIT=unit0', command)
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(3.1)
        self.poll_verify()
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'await_observation')
        result = self.runner.observe(True)
        self.assertEqual(result.status, 'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
        self.assertIn('mmu_machine', ''.join(self.client.paths))

    def test_hh_machine_order_change_blocks_before_dispatch(self):
        self.configure_led_chain(managed=True)
        raw = self.printer.subscription.snapshot.return_value
        raw['status']['mmu_machine'] = {
            'num_units': 1, 'unit_0': {'name': 'unit0'}}
        self.printer.state = PrinterState.from_snapshot(raw)
        roles = approved_integrations(self.printer.state, ())
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        # Config and live machine list disagree at physical preflight.
        self.client.status['mmu_machine']['unit_0']['name'] = 'other'
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        blocked = self.runner.poll()
        self.assertEqual(blocked.status, 'BLOCKED')
        self.assertEqual(self.commands, [])

    def test_mmu_unresolved_numeric_unit_fails_before_any_command(self):
        self.configure_led_chain(managed=True)
        raw = self.printer.subscription.snapshot.return_value
        raw['settings']['mmu_machine'] = {'units': ['different_unit']}
        self.printer.state = PrinterState.from_snapshot(raw)
        roles = approved_integrations(self.printer.state, (
            ('led', 'neopixel diagnostic'),))
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        outcome = self.runner.poll()
        self.assertEqual(outcome.status, 'BLOCKED')
        self.assertEqual(self.commands, [])

    def test_hh_string_boolean_status_is_validated_and_restored(self):
        # Real Happy Hare can serialize Klipper flags as literal strings.
        # Exercise the complete guarded flow with two controller readbacks:
        # a string-form snapshot followed by an equivalent real bool one.
        for animated in ('True', 'False'):
            with self.subTest(animated=animated):
                # read_queue_evidence timestamps use real monotonic(), while
                # the physical runner clock is synthetic in this CI fixture.
                # Reset the synthetic clock for each independent consent.
                self.clock[0] = monotonic()
                self.configure_led_chain(managed=True)
                control = self.client.status['mmu_leds unit0']
                control['enabled'] = 'True'
                control['animation'] = animated
                self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
                self.worker.next()
                self.assertIsNone(self.runner.poll())
                self.assertEqual(self.runner.phase, 'await_confirmation')
                self.assertEqual(self.commands, [])
                self.assertTrue(self.runner.confirm()[0])
                future, payload, guard = self.commands[-1]
                self.assertTrue(guard())
                self.assertIn('MMU_SET_LED UNIT=0 EXIT_EFFECT=', payload['script'])
                self.assertNotIn('SET_LED LED=', payload['script'])
                future.set_result({'result': 'ok'})
                self.runner.poll()
                self.advance(3.1)
                self.poll_verify()
                self.assertEqual(self.runner.phase, 'verifying')
                control['enabled'] = True
                control['animation'] = animated == 'True'
                self.advance(.35)
                self.poll_verify()
                self.assertEqual(self.runner.phase, 'await_observation')
                result = self.runner.observe(True)
                self.assertEqual(result.status, 'OBSERVED_USER')
                self.assertFalse(result.restore_verified)
                self.commands.clear()  # Isolate the next physical program.

    def test_hh_invalid_string_or_numeric_status_blocks_preflight(self):
        # Values that happen to be truthy are NOT evidence of enabled LEDs.
        for enabled, animated in (
                ('False', 'True'), ('true', 'True'), ('1', 'True'),
                (1, True), (True, 'false'), (True, 'TRUE'),
                (True, 'False '), (True, 'on'), (True, 1),
                (True, None)):
            with self.subTest(enabled=enabled, animated=animated):
                self.configure_led_chain(managed=True)
                control = self.client.status['mmu_leds unit0']
                control['enabled'] = enabled
                control['animation'] = animated
                self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
                self.worker.next()
                result = self.runner.poll()
                self.assertEqual(result.status, 'BLOCKED')
                self.assertEqual(result.reason, 'preflight_failed')
                self.assertEqual(self.commands, [])

    def test_hh_string_status_mismatch_cannot_claim_restore(self):
        self.configure_led_chain(managed=True)
        control = self.client.status['mmu_leds unit0']
        control['enabled'] = 'True'
        control['animation'] = 'True'
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        control['animation'] = 'False'
        self.advance(3.1)
        for _ in range(3):
            self.poll_verify()
            self.advance(.35)
        self.advance(6)
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertFalse(result.restore_verified)
        self.assertIsNone(self.runner.observe(True))

    def test_managed_mmu_chain_inactive_or_busy_rejected_without_dispatch(self):
        for status_change in (
                {'mmu_leds unit0': {
                    'enabled': False, 'animation': True, 'exit': 4}},
                {'mmu': {'action': 'Loading'}},
                {'mmu_leds unit0': {
                    'enabled': True, 'animation': None, 'exit': 4}}):
            with self.subTest(status_change=status_change):
                self.configure_led_chain(managed=True)
                self.client.status.update(status_change)
                self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
                self.worker.next()
                result = self.runner.poll()
                self.assertEqual(result.status, 'BLOCKED')
                self.assertEqual(result.reason, 'preflight_failed')
                self.assertEqual(self.commands, [])

    def test_hh_entry_status_logo_grouped_into_one_timed_native_request(self):
        self.configure_led_chain(managed=True)
        settings = dict(self.printer.state.settings)
        settings['mmu_leds unit0'] = {
            'entry_leds': 'neopixel:diagnostic (1,3)',
            'status_leds': 'neopixel:diagnostic (2)',
            'logo_leds': 'neopixel:diagnostic (4)'}
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = settings
        self.printer.state = PrinterState.from_snapshot(raw)
        roles = approved_integrations(self.printer.state, ())
        self.assertIn('maintenance.safe_led:neopixel diagnostic', roles)
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        self.client.status['mmu_leds unit0'] = {
            'enabled': True, 'animation': False,
            'entry': 2, 'status': 1, 'logo': 1}
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertTrue(self.runner.confirm()[0])
        script = self.commands[0][1]['script']
        self.assertIn('ENTRY_EFFECT=', script)
        self.assertIn('STATUS_EFFECT=', script)
        self.assertIn('LOGO_EFFECT=', script)
        self.assertNotIn('EXIT_EFFECT=', script)
        self.assertEqual(len(script.splitlines()), 12)
        self.assertEqual(script.count('M400'), 4)
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(3.1)
        self.poll_verify()
        self.advance(.35)
        self.poll_verify()
        self.assertEqual(self.runner.observe(True).status, 'OBSERVED_USER')

    def test_hh_two_units_same_chain_needs_both_controls_stable(self):
        self.configure_led_chain(managed=True)
        raw = self.printer.subscription.snapshot.return_value
        raw['settings'] = {
            'neopixel diagnostic': {'pin': 'PA7', 'chain_count': 4,
                                     'color_order': 'GRB'},
            'mmu_leds first': {'exit_leds': 'neopixel:diagnostic (1-2)'},
            'mmu_leds second': {'entry_leds': 'neopixel:diagnostic (3-4)'},
            'mmu_machine': {'units': ['second', 'first']}}
        raw['objects'] = ('neopixel diagnostic', 'mmu_leds first',
                          'mmu_leds second', 'mmu_machine', 'mmu')
        self.printer.state = PrinterState.from_snapshot(raw)
        roles = approved_integrations(self.printer.state, ())
        self.printer.maintenance.snapshot = discover(self.printer.state, roles)
        self.client.status = {
            'neopixel diagnostic': {'color_data': [
                (0., 0., 0., 0.) for _ in range(4)]},
            'mmu_leds first': {'enabled': True, 'animation': True, 'exit': 2},
            'mmu_leds second': {'enabled': True, 'animation': False, 'entry': 2},
            'mmu_machine': {
                'num_units': 2,
                'unit_0': {'name': 'second'},
                'unit_1': {'name': 'first'}},
            'mmu': {'action': 'Idle'}}
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.assertIsNone(self.runner.poll())
        self.assertTrue(self.runner.confirm()[0])
        script = self.commands[0][1]['script']
        self.assertEqual(len(script.splitlines()), 16)
        self.assertEqual(script.count('M400'), 4)
        self.assertIn('UNIT=1 EXIT_EFFECT=', script)
        self.assertIn('UNIT=0 ENTRY_EFFECT=', script)
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.advance(3.1)
        self.poll_verify()
        self.assertEqual(self.runner.phase, 'verifying')
        self.client.status['mmu_leds second']['enabled'] = False
        self.advance(.35)
        self.poll_verify()
        self.advance(6)
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertFalse(result.restore_verified)

    def test_mmu_effect_status_change_never_reports_success(self):
        self.configure_led_chain(managed=True)
        self.assertTrue(self.runner.start('O04', 'neopixel diagnostic')[0])
        self.worker.next()
        self.runner.poll()
        self.assertTrue(self.runner.confirm()[0])
        self.commands[0][0].set_result({'result': 'ok'})
        self.runner.poll()
        self.client.status['mmu_leds unit0']['enabled'] = False
        self.advance(3.1)
        for _ in range(3):
            self.poll_verify()
            self.advance(.35)
        self.advance(6)
        result = self.runner.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertFalse(result.restore_verified)
        self.assertIsNone(self.runner.observe(True))

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
        self.assertFalse(self.runner.start('S18', 'pwm_cycle_time alarm')[0])
        self.printer.maintenance_reader.pending = True
        self.assertFalse(self.runner.start('F01', 'fan')[0])
        self.assertEqual(self.commands, [])
        self.runner.close()
        self.assertFalse(self.runner.start('F01', 'fan')[0])


if __name__ == '__main__':
    unittest.main()
