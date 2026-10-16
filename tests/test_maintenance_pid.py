from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from test_maintenance_heater import ThermalControllerTests
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, CALIBRATION, _add
from maintenance_thermal import contract, pid_evidence
from moonraker_subscription import MoonrakerSubscription

class PIDControllerTests(ThermalControllerTests):
    def setUp(self):
        super().setUp()
        snap = self.p.maintenance.snapshot
        device = snap.devices[0]
        self.p.maintenance.snapshot = MaintenanceSnapshot(
            snap.epoch, (DeviceCapabilities(device.name, device.family,
                _add(device.modes, 'H02', CALIBRATION)),), config_marker=snap.config_marker)
        self.pending_config = False
        self.proof = {}
        self.timeouts = []

    def get(self, path):
        reply = super().get(path)
        if path.startswith('/printer/objects/query?'):
            reply['result']['status']['configfile'] = {
                'save_config_pending': self.pending_config,
                'save_config_pending_items': self.proof}
        return reply

    def request(self, method, params=None, guard=None, request_timeout=None):
        self.timeouts.append(request_timeout)
        future = super().request(method, params, guard)
        if method == 'printer.gcode.script' and params['script'].startswith('PID_CALIBRATE'):
            self.data['status']['extruder']['target'] = 150.
        return future

    def test_pid_requires_real_pending_parameters_off_and_operator(self):
        self.armed('H02')
        self.c.confirm()
        self.assertEqual(self.timeouts, [900.])
        script = self.requests[0][1]['script']
        self.assertIn('PID_CALIBRATE HEATER=extruder TARGET=150.0', script)
        self.assertNotIn('SAVE_CONFIG', script)
        for t in range(2, 79, 2):
            self.clock = t
            values = self.data['status']['extruder']
            values['temperature'] = min(150., 25+t*5)
            if t >= 30:
                self.pending_config = True
                self.proof = {'extruder': {'control': 'pid',
                    'pid_kp': '20', 'pid_ki': '1', 'pid_kd': '100'}}
                values.update(target=0., power=0.)
                if not self.heat.done():
                    self.heat.set_result('ok')
            self.c.poll()
            if self.worker.jobs:
                self.worker.drain()
                self.c.poll()
            if self.c.phase == 'await_observation':
                break
        self.assertEqual(self.c.phase, 'await_observation')
        result = self.c.observe(True)
        self.assertEqual(result.status, 'PASSED_USER')
        self.assertEqual(dict(result.evidence)['pid_kp'], 20.)
        self.assertTrue(result.restore_verified)

    def test_pid_rejects_existing_pending_config_before_any_command(self):
        self.pending_config = True
        self.c.start('H02', 'extruder')
        self.worker.drain()
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(self.requests, [])

class PIDEvidenceTests(unittest.TestCase):
    def test_parameters_are_not_inferred_from_ack_or_nan(self):
        for config in ({}, {'save_config_pending': True},
                       {'save_config_pending': True, 'save_config_pending_items': {
                           'extruder': {'control': 'pid', 'pid_kp': 'nan', 'pid_ki': '1', 'pid_kd': '1'}}}):
            self.assertEqual(pid_evidence(config, 'extruder'), ())

    def test_timeout_override_is_bounded_and_script_only(self):
        obj = MoonrakerSubscription.__new__(MoonrakerSubscription)
        obj.notify = Mock(return_value='future')
        self.assertEqual(obj.request('printer.gcode.script', {}, request_timeout=900), 'future')
        obj.notify.assert_called_once_with('printer.gcode.script', {}, completion=True,
                                           guard=None, request_timeout=900)
        # Validation happens before socket/queue access.
        for method, timeout in (('printer.gcode.script', 901),
                                ('printer.gcode.script', float('nan')),
                                ('printer.gcode.script', True),
                                ('printer.emergency_stop', 900)):
            with self.assertRaises(ValueError):
                MoonrakerSubscription.notify(obj, method, completion=True, request_timeout=timeout)
