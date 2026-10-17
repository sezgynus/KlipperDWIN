from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from test_maintenance_heater import ThermalControllerTests
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, CALIBRATION, _add
from printer_state import PrinterState
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
        self.pid_device, self.pid_target = 'extruder', 150.

    def _select_pid_device(self, device, feature, target):
        self.pid_device, self.pid_target = device, target
        self.data['settings'] = {device: {
            'heater_pin': 'PA1', 'min_temp': 0., 'max_temp': 280.}}
        self.data['status'][device] = {'temperature': 25., 'target': 0., 'power': 0.}
        self.p.state = PrinterState.from_snapshot(self.data)
        services = (('maintenance.thermal_profile:'+device+'|45,120',)
                    if feature == 'H04' else ())
        self.p.maintenance.snapshot = MaintenanceSnapshot(
            self.data['epoch'], (DeviceCapabilities(device, 'heater',
                _add(0, feature, CALIBRATION)),),
            config_marker=id(self.p.state.settings), service_key=services)

    def get(self, path):
        if path.startswith('/printer/objects/query?'):
            statuses = {item.name: dict(self.data['status'][item.name])
                        for item in self.p.maintenance.snapshot.devices
                        if item.family == 'heater'}
            statuses['configfile'] = {
                'save_config_pending': self.pending_config,
                'save_config_pending_items': self.proof}
            return {'result': {'eventtime': self.clock, 'status': statuses}}
        return super().get(path)

    def request(self, method, params=None, guard=None, request_timeout=None):
        self.timeouts.append(request_timeout)
        if method == 'printer.gcode.script' and params['script'].startswith('PID_CALIBRATE'):
            self.requests.append((method, params))
            if guard is not None and not guard():
                future = Future()
                future.set_exception(ValueError('guard'))
                return future
            self.data['status'][self.pid_device]['target'] = self.pid_target
            self.data['status'][self.pid_device]['power'] = .5
            return self.heat
        return super().request(method, params, guard)

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
                    'pid_Kp': '20.000', 'pid_Ki': '1.000', 'pid_Kd': '100.000'}}
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
        self.assertEqual(dict(result.evidence)['pid_ki'], 1.)
        self.assertEqual(dict(result.evidence)['pid_kd'], 100.)
        self.assertTrue(result.restore_verified)

    def test_h03_bed_and_h04_generic_read_real_klipper_pending_names(self):
        for feature, device, target in (
                ('H03', 'heater_bed', 60.),
                ('H04', 'heater_generic dryer', 45.)):
            with self.subTest(feature=feature, device=device):
                # Use a fresh controller on every device, preventing
                # shared state or old pending config from producing proof.
                if feature == 'H04':
                    self.setUp()
                self._select_pid_device(device, feature, target)
                self.assertTrue(self.c.start(feature, device)[0])
                self.worker.drain()
                self.assertIsNone(self.c.poll())
                self.assertEqual(self.c.phase, 'await_confirmation')
                self.assertTrue(self.c.confirm()[0])
                self.assertIn('PID_CALIBRATE HEATER=%s TARGET=%.1f' %
                              (device.split()[-1], target),
                              self.requests[0][1]['script'])
                self.assertNotIn('SAVE_CONFIG', self.requests[0][1]['script'])
                for t in range(2, 79, 2):
                    self.clock = t
                    values = self.data['status'][device]
                    values['temperature'] = min(target, 25+t*5)
                    if t >= 30:
                        self.pending_config = True
                        self.proof = {device: {'control': 'pid',
                            'pid_Kp': '12.500', 'pid_Ki': '0.750',
                            'pid_Kd': '75.125'}}
                        values.update(target=0., power=0.)
                        if not self.heat.done():
                            self.heat.set_result('ok')
                    self.assertIsNone(self.c.poll())
                    if self.worker.jobs:
                        self.worker.drain()
                        self.assertIsNone(self.c.poll())
                    if self.c.phase == 'await_observation':
                        break
                self.assertEqual(self.c.phase, 'await_observation')
                outcome = self.c.observe(True)
                self.assertEqual(outcome.feature_id, feature)
                self.assertEqual(outcome.status, 'PASSED_USER')
                self.assertTrue(outcome.restore_verified)
                self.assertEqual(dict(outcome.evidence)['pid_kp'], 12.5)
                self.assertEqual(dict(outcome.evidence)['pid_ki'], .75)
                self.assertEqual(dict(outcome.evidence)['pid_kd'], 75.125)
                self.assertEqual(len(self.requests), 1)

    def test_pid_autotune_overshoot_does_not_trigger_petrel_shutdown(self):
        self.armed('H02')
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.c._contract.target, 150.)
        self.assertEqual(self.c._contract.ceiling, 280.)
        self.clock = 1.
        self.assertIsNone(self.c.poll())
        self.data['status']['extruder']['temperature'] = 163.24
        self.data['status']['extruder']['power'] = 0.
        self.data['status']['extruder']['target'] = 145.
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase, 'running')
        self.assertEqual([r[0] for r in self.requests], ['printer.gcode.script'])

    def test_pid_rejects_existing_pending_config_before_any_command(self):
        self.pending_config = True
        self.c.start('H02', 'extruder')
        self.worker.drain()
        result = self.c.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'existing_or_unknown_pending_config')
        self.assertEqual(self.requests, [])

class PIDEvidenceTests(unittest.TestCase):
    def test_klipper_mixed_case_pending_items_for_all_pid_targets(self):
        values = {'control': 'pid', 'pid_Kp': '21.500',
                  'pid_Ki': '1.250', 'pid_Kd': '102.875'}
        for device in ('extruder', 'heater_bed', 'heater_generic dryer'):
            with self.subTest(device=device):
                data = {'save_config_pending': True,
                        'save_config_pending_items': {device: values}}
                self.assertEqual(pid_evidence(data, device),
                    (('pid_kp', 21.5), ('pid_ki', 1.25), ('pid_kd', 102.875)))
                self.assertEqual(pid_evidence(data, 'another_device'), ())

    def test_rejects_incomplete_malformed_stale_or_wrong_case_proof(self):
        template = {'control': 'pid', 'pid_Kp': '20.000',
                    'pid_Ki': '1.000', 'pid_Kd': '100.000'}
        for bad in (
                {'save_config_pending': False},
                {'save_config_pending': True},
                {'save_config_pending': 'true'},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': {'control': 'pid', 'pid_kp': '20',
                                 'pid_ki': '1', 'pid_kd': '100'}}},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': dict(template, pid_Kp='nan')}},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': dict(template, pid_Kd='inf')}},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': dict(template, pid_Ki='0')}},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': dict(template, pid_Kp=True)}},
                {'save_config_pending': True, 'save_config_pending_items': {
                    'extruder': dict(template, control='watermark')}}):
            with self.subTest(data=bad):
                self.assertEqual(pid_evidence(bad, 'extruder'), ())

    def test_requires_complete_proof_for_one_exact_heater_section(self):
        data = {'save_config_pending': True,
                'save_config_pending_items': {
                    'heater_bed': {'control': 'pid', 'pid_Kp': '20',
                                   'pid_Ki': '1', 'pid_Kd': '100'},
                    'extruder': {'control': 'pid', 'pid_Kp': '30',
                                 'pid_Ki': '2', 'pid_Kd': '110'}}}
        self.assertEqual(pid_evidence(data, 'heater_bed')[0], ('pid_kp', 20.))
        self.assertEqual(pid_evidence(data, 'extruder')[0], ('pid_kp', 30.))
        self.assertEqual(pid_evidence(data, 'heater_generic dryer'), ())

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
