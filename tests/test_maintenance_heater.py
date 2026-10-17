"""CI-only state-machine checks; no hardware or emulator."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from test_maintenance_controller import printer, Worker
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, AUTOMATIC, _add
from maintenance_heater import MaintenanceHeaterController, MaintenancePhysicalRouter
from maintenance_thermal import ACTIVE

class ThermalControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0.
        self.p, self.data = printer()
        self.data['settings'] = {'extruder': {
            'heater_pin': 'PA1', 'min_temp': 0., 'max_temp': 280.}}
        self.data['status']['extruder'] = {'temperature': 25., 'target': 0., 'power': 0.}
        self.p.state = PrinterState.from_snapshot(self.data)
        bits = 0
        for f in ACTIVE:
            bits = _add(bits, f, AUTOMATIC)
        self.p.maintenance.snapshot = MaintenanceSnapshot(12, (
            DeviceCapabilities('extruder', 'heater', bits),),
            config_marker=id(self.p.state.settings))
        self.p.subscription.lifecycle = lambda: {'state': self.data['state'], 'epoch': self.data['epoch']}
        self.worker = Worker()
        self.client = SimpleNamespace(get=self.get)
        self.requests = []
        self.heat = Future()
        self.p.subscription.request = self.request
        self.c = MaintenanceHeaterController(self.p, self.worker, self.client)
        self.patches = [patch('maintenance_heater.monotonic', lambda: self.clock),
                        patch('maintenance_runtime.monotonic', lambda: self.clock)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def get(self, path):
        if path == '/server/info':
            return {'result': {'components': []}}
        if path.startswith('/printer/objects/query?'):
            return {'result': {'eventtime': self.clock, 'status': {
                'extruder': dict(self.data['status']['extruder'])}}}
        raise AssertionError(path)

    def request(self, method, params=None, guard=None):
        self.requests.append((method, params))
        if guard is not None and not guard():
            f = Future()
            f.set_exception(ValueError('guard'))
            return f
        if method == 'printer.gcode.script':
            self.data['status']['extruder']['target'] = 60.
            self.data['status']['extruder']['power'] = .5
            return self.heat
        f = Future()
        f.set_result('ok')
        return f

    def armed(self, feature='H01'):
        self.assertTrue(self.c.start(feature, 'extruder')[0])
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase, 'await_confirmation')
        self.assertEqual(self.requests, [])

    def test_complete_measurement_requires_human_observation_and_verified_off(self):
        self.armed()
        self.assertTrue(self.c.confirm()[0])
        self.assertIn('TARGET=0', self.requests[0][1]['script'].splitlines()[-1])
        for t in range(2, 159, 2):
            self.clock = t
            v = self.data['status']['extruder']
            v['temperature'] = min(60., 25+t)
            if t >= 120:
                v.update(target=0., power=0., temperature=60-(t-120)*.2)
                if not self.heat.done():
                    self.heat.set_result('ok')
            self.assertIsNone(self.c.poll())
            if self.worker.jobs:
                self.worker.drain()
                self.assertIsNone(self.c.poll())
            if self.c.phase == 'await_observation':
                break
        self.assertEqual(self.c.phase, 'await_observation')
        self.clock = 10000
        self.assertIsNone(self.c.poll())
        result = self.c.observe(True)
        self.assertEqual(result.status, 'PASSED_USER')
        self.assertTrue(result.restore_verified)
        self.assertGreater(dict(result.evidence)['rise_c'], 5)
        self.assertEqual([item.feature_id for item in result.components],
                         ['H01','H05','H06','H07','H08','H09','H13'])
        self.assertTrue(all(item.status == 'PASSED_USER'
                            and item.restore_verified for item in result.components))
        self.assertEqual([name for name, _ in self.requests],
                         ['printer.gcode.script'])

    def test_combined_thermal_report_does_not_fail_other_metrics_on_overshoot(self):
        self.armed()
        self.assertTrue(self.c.confirm()[0])
        for t in range(2, 159, 2):
            self.clock = t
            v = self.data['status']['extruder']
            v['temperature'] = 70. if t == 64 else min(60., 25+t)
            if t >= 120:
                v.update(target=0., power=0., temperature=60-(t-120)*.2)
                if not self.heat.done():
                    self.heat.set_result('ok')
            self.assertIsNone(self.c.poll())
            if self.worker.jobs:
                self.worker.drain()
                self.assertIsNone(self.c.poll())
            if self.c.phase == 'await_observation':
                break
        self.assertEqual(self.c.phase, 'await_observation')
        result = self.c.observe(True)
        self.assertEqual(result.status, 'FAILED_METRIC')
        parts = {part.feature_id: part for part in result.components}
        self.assertEqual(len(parts), 7)
        self.assertEqual(parts['H07'].status, 'FAILED_METRIC')
        self.assertEqual(dict(parts['H07'].evidence)['overshoot_c'], 10.)
        self.assertEqual(parts['H01'].status, 'PASSED_USER')
        self.assertEqual(parts['H05'].status, 'PASSED_USER')
        self.assertEqual(parts['H09'].status, 'PASSED_USER')
        self.assertEqual([name for name, _ in self.requests],
                         ['printer.gcode.script'])

    def test_unlimited_wait_one_click_refreshes_then_starts_heat(self):
        self.armed()
        self.clock = 10000
        self.assertIsNone(self.c.poll())  # Human time never aborts the test.
        self.assertEqual(self.requests, [])
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.c.phase, 'preflight')
        self.assertTrue(self.c.refreshing_consent)
        self.assertEqual(self.c._series.samples, [])  # Old preflight sample discarded.
        self.assertEqual(self.requests, [])  # Fresh read before any G-code.
        self.assertIsNone(self.c.poll())  # No extra confirmation requested.
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertFalse(self.c.refreshing_consent)
        self.assertEqual(self.c.phase, 'running')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], 'printer.gcode.script')
        self.assertFalse(self.c.confirm()[0])  # Never dispatch twice.

    def test_refresh_rechecks_cold_limits_and_fails_without_heating(self):
        self.armed()
        self.clock = 10000
        self.assertTrue(self.c.confirm()[0])
        self.data['status']['extruder']['temperature'] = 55.
        self.worker.drain()
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'cold_idle_thermal_preflight_required')
        self.assertFalse(self.c.pending)
        self.assertFalse(self.c._blocked)
        self.assertEqual(self.requests, [])

    def test_refresh_rejects_print_start_and_stale_epochs_without_dispatch(self):
        self.armed()
        self.clock = 10000
        self.assertTrue(self.c.confirm()[0])
        self.data['status']['print_stats']['state'] = 'printing'
        self.p.state = PrinterState.from_snapshot(
            self.data, reused_settings=self.p.state.settings)
        self.worker.drain()
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(self.requests, [])
        self.assertFalse(self.c._blocked)
        self.data['status']['print_stats']['state'] = 'standby'
        self.p.state = PrinterState.from_snapshot(
            self.data, reused_settings=self.p.state.settings)
        self.assertTrue(self.c.start('H01','extruder')[0])
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.clock = 20000
        self.data['epoch'] += 1
        self.p.state = PrinterState.from_snapshot(
            self.data, reused_settings=self.p.state.settings)
        self.assertEqual(self.c.confirm(),
                         (False, 'thermal_confirmation_stale_session'))
        self.assertEqual(self.requests, [])

    def test_refresh_cancel_disowns_future_and_does_not_shutdown(self):
        self.armed()
        self.clock = 10000
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.c.phase, 'preflight')
        self.assertEqual(self.c.cancel().status, 'ABORTED')
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.requests, [])
        self.assertFalse(self.c.refreshing_consent)

    def test_refresh_worker_rejection_is_blocked_without_heating(self):
        self.armed()
        self.clock = 10000
        self.worker.submit = Mock(side_effect=RuntimeError('busy'))
        self.assertEqual(self.c.confirm(),
                         (False, 'thermal_refresh_worker_rejected'))
        self.assertFalse(self.c.pending)
        self.assertEqual(self.requests, [])

    def test_expired_refreshed_safety_never_uses_old_consent_to_heat(self):
        self.armed()
        self.clock = 10000
        self.assertTrue(self.c.confirm()[0])
        self.worker.drain()
        self.clock += 15
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'thermal_preflight_stale')
        self.assertEqual(self.requests, [])

    def test_h05_shared_heater_confirmation_refresh_requires_one_click(self):
        self.armed('H05')
        self.clock = 10000
        self.assertTrue(self.c.confirm()[0])
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase, 'running')
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.c.confirm()[0])

    def test_preheat_label_has_no_uninitialized_elapsed_timer(self):
        self.armed()
        self.clock = 599898
        for item in self.c.live_text:
            self.assertNotIn('599898 s', item)
        self.assertIn('samples', self.c.live_text[-1])

    def test_overshoot_is_measured_not_a_petrel_emergency_stop(self):
        # H01 and H07 both use this thermal controller. Crossing the former
        # target+10 cap must not turn an ordinary measurement into shutdown.
        self.armed('H07')
        self.assertTrue(self.c.confirm()[0])
        self.clock = 1.
        self.assertIsNone(self.c.poll())  # queue fresh telemetry work
        self.data['status']['extruder']['temperature'] = 76.
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase, 'running')
        self.assertNotIn('printer.emergency_stop', [r[0] for r in self.requests])
        self.assertEqual(self.c._contract.ceiling, 280.)

    def test_cancel_during_heat_uses_emergency_rpc_never_queued_gcode_off(self):
        self.armed()
        self.c.confirm()
        self.assertIsNone(self.c.cancel())
        self.assertEqual(self.requests[-1][0], 'printer.emergency_stop')
        result = self.c.poll()
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertFalse(result.restore_verified)
        self.assertFalse(self.c.start('H01', 'extruder')[0])

    def test_lost_connection_and_command_error_are_not_retried(self):
        self.armed()
        self.c.confirm()
        self.heat.set_exception(ValueError('ambiguous'))
        self.c.poll()
        self.assertEqual(self.requests[-1][0], 'printer.emergency_stop')
        self.c.poll()
        self.assertEqual(len(self.requests), 2)

    def test_stale_queue_unknown_temperature_and_target_drift_shutdown(self):
        self.armed()
        self.c.confirm()
        self.clock = 6.
        self.c.poll()
        self.assertEqual(self.c.phase, 'stopping')
        self.assertEqual(self.requests[-1][0], 'printer.emergency_stop')

    def test_preflight_cancel_and_missing_inventory_do_not_heat(self):
        self.armed()
        self.assertEqual(self.c.cancel().status, 'ABORTED')
        self.assertEqual(self.requests, [])
        self.assertFalse(self.c.start('H04', 'heater_generic chamber')[0])

    def test_router_prevents_concurrent_domains(self):
        pulse = SimpleNamespace(pending=True)
        router = MaintenancePhysicalRouter(pulse, self.c)
        self.assertFalse(router.start('H01', 'extruder')[0])
        self.assertEqual(self.requests, [])

    def test_backend_planning_does_not_require_controller_or_io(self):
        from printerInterface import PrinterData
        p = PrinterData.__new__(PrinterData)
        p.maintenance = self.p.maintenance
        rows = p.maintenance_guided_plan()
        self.assertEqual(rows, ())
        self.assertEqual(self.requests, [])

    def test_heater_reactivation_during_cooling_forces_shutdown(self):
        self.armed()
        self.c.confirm()
        self.clock = 2.
        self.c._phase = 'verifying'
        self.c._cool_started = 0.
        self.data['status']['extruder'].update(temperature=40., target=60., power=.5)
        self.c.poll()
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase, 'stopping')
        self.assertEqual(self.requests[-1][0], 'printer.emergency_stop')
        self.assertFalse(self.c.poll().restore_verified)

    def test_completed_command_without_off_has_short_bounded_deadline(self):
        self.armed()
        self.c.confirm()
        self.heat.set_result('ok')
        self.c.poll()
        self.assertLessEqual(self.c._deadline, 8.)

    def test_completed_fresh_read_precedes_old_queue_age_check(self):
        self.armed()
        self.c.confirm()
        self.clock = 1.
        self.c.poll()
        self.clock = 4.
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase, 'running')
        self.assertEqual(len(self.requests), 1)

    def test_active_read_latency_is_bounded_without_stale_admission(self):
        self.armed()
        self.c.confirm()
        self.clock = 1.
        self.c.poll()
        self.clock = 4.
        self.c.poll()
        self.assertEqual(self.c.phase, 'running')
        self.clock = 6.
        self.c.poll()
        self.assertEqual(self.c.phase, 'stopping')

    def test_dispatch_guard_rejection_does_not_shutdown_unheated_printer(self):
        self.armed()
        self.data['status']['extruder']['temperature'] = 55.
        self.c.confirm()
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertIn('before_send', result.reason)
        self.assertEqual([r[0] for r in self.requests], ['printer.gcode.script'])
        self.assertFalse(self.c._blocked)

    def test_unexpected_target_still_shutdowns_with_specific_reason(self):
        self.armed()
        self.c.confirm()
        self.clock = 2.
        self.data['status']['extruder']['target'] = 200.
        self.c.poll()
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase, 'stopping')
        self.assertIn('thermal_target_drift', self.c._stop_reason)

    def test_shutdown_reason_logged_before_rpc_even_without_result_screen(self):
        self.armed()
        self.c.confirm()
        original = self.p.subscription.request
        with self.assertLogs('maintenance_heater', level='ERROR') as logs:
            def checked_request(method, params=None, guard=None):
                self.assertTrue(logs.output)
                self.assertIn('feature=H01 heater=extruder', logs.output[0])
                self.assertIn('reason=diagnostic_probe', logs.output[0])
                return original(method, params, guard)
            self.p.subscription.request = checked_request
            self.c._shutdown('diagnostic_probe')
            self.c._shutdown('must_not_repeat')
        self.assertEqual(len(logs.output), 1)
        self.assertEqual([r[0] for r in self.requests].count('printer.emergency_stop'), 1)

    def test_rejected_sample_values_are_available_in_shutdown_log(self):
        self.armed()
        self.c.confirm()
        self.clock = 2.
        self.data['status']['extruder']['target'] = 200.
        self.c.poll()
        self.worker.drain()
        with self.assertLogs('maintenance_heater', level='ERROR') as logs:
            self.c.poll()
        self.assertIn('thermal_target_drift', logs.output[0])
        self.assertIn('target=200.0', logs.output[0])
        self.assertIn('temperature=25.0', logs.output[0])

    def test_logging_failure_cannot_suppress_emergency_stop(self):
        self.armed()
        self.c.confirm()
        with patch('maintenance_heater._LOG.error', side_effect=RuntimeError('logger')):
            self.c._shutdown('diagnostic_probe')
        self.assertEqual(self.requests[-1][0], 'printer.emergency_stop')
