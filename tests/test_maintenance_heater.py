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

    def test_unlimited_user_wait_refreshes_preflight_without_heat(self):
        self.armed()
        self.clock = 10000
        self.assertIsNone(self.c.poll())
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.c.phase, 'preflight')
        self.assertEqual(self.requests, [])
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase, 'await_confirmation')

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
