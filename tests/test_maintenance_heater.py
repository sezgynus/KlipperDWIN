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
        self.clock = 4.
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
