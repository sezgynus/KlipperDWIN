"""CI regression: Maintenance planner scopes and fail-closed execution gates."""
import dataclasses
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_catalog import definition_for
from maintenance_discovery import (
    AUTOMATIC, CALIBRATION, EXTERNAL, INFORMATION, USER, _add,
    discover, MaintenanceSnapshot, DeviceCapabilities,
)
from maintenance_planner import (
    AdapterRegistration, PlannedTest, build_plan, visible_plan,
)


def installed(feature, method, name=None):
    spec = definition_for(feature)
    return AdapterRegistration(
        feature, method, name or ('verified.' + feature + '.' + str(method)),
        spec.evidence_contract, spec.safety_profile)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.printer = SimpleNamespace(
            ready=True, epoch=24,
            objects=('fan', 'extruder', 'heater_bed',
                     'tmc2208 stepper_x', 'tmc2208 stepper_y',
                     'toolhead', 'gcode_move', 'webhooks'),
            settings={'extruder': {'min_temp': 0, 'max_temp': 290},
                      'heater_bed': {'min_temp': 0, 'max_temp': 120},
                      'tmc2208 stepper_x': {'run_current': .8},
                      'tmc2208 stepper_y': {'run_current': .8}},
            status={})
        self.snapshot = discover(self.printer, ('machine.proc_stats',))

    def test_unknown_and_empty_snapshots(self):
        self.assertEqual(build_plan(None), ())
        self.assertEqual(build_plan(MaintenanceSnapshot(123)), ())
        with self.assertRaises(ValueError):
            build_plan(self.printer)

    def test_multi_device_and_global_are_not_collapsed(self):
        plan = build_plan(self.snapshot)
        heaters = [r for r in plan if r.feature_id == 'H01']
        drivers = [r for r in plan if r.feature_id == 'M07']
        self.assertEqual({r.device for r in heaters}, {'extruder', 'heater_bed'})
        self.assertEqual({r.device for r in drivers},
                         {'tmc2208 stepper_x', 'tmc2208 stepper_y'})
        self.assertEqual(len([r for r in plan if r.feature_id == 'M03']), 1)
        self.assertIsNone(next(r for r in plan if r.feature_id == 'M03').device)
        self.assertTrue(all(r.category == 'blocked' and not r.visible
                            for r in plan))
        self.assertEqual(visible_plan(plan), ())
        self.assertTrue(all(r.epoch == 24 for r in plan))

    def test_only_exact_installed_method_may_become_candidate(self):
        specs = (installed('F01', AUTOMATIC), installed('H01', AUTOMATIC),
                 installed('M07', INFORMATION), installed('S01', INFORMATION),
                 installed('M03', CALIBRATION))
        plan = build_plan(self.snapshot, specs)
        self.assertEqual([r.device for r in plan
                          if r.feature_id == 'H01' and r.visible],
                         ['extruder', 'heater_bed'])
        self.assertFalse(next(r for r in plan if r.feature_id == 'F01').visible)
        self.assertEqual(len([r for r in plan
                              if r.feature_id == 'M07' and r.category == 'informational']), 2)
        self.assertEqual(next(r for r in plan if r.feature_id == 'M03').category,
                         'guided')
        self.assertEqual(next(r for r in plan if r.feature_id == 'S01').category,
                         'informational')
        self.assertFalse(any(r.category == 'runnable' and r.device == 'fan'
                             for r in plan))

    def test_automatic_and_user_methods_keep_exact_evidence(self):
        plan = build_plan(self.snapshot, (installed('F01', USER),))
        fan = next(r for r in plan if r.feature_id == 'F01')
        self.assertEqual(fan.available_methods, USER)
        self.assertEqual(fan.method, USER)
        self.assertEqual(fan.category, 'guided')
        self.assertEqual(fan.evidence_contract,
                         definition_for('F01').evidence_contract)
        self.assertEqual(fan.safety_profile, 'fan')
        self.assertIsNotNone(fan.adapter_id)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fan.category = 'runnable'

    def test_untrusted_adapter_declarations_fail_closed(self):
        for adapter in (
                installed('M17', AUTOMATIC),
                installed('H01', USER),
                installed('S01', AUTOMATIC),
                AdapterRegistration('H01', AUTOMATIC, 'bad', 'fake', 'heater'),
                AdapterRegistration('H01', AUTOMATIC, 'bad', definition_for('H01').evidence_contract, 'read_only'),
                AdapterRegistration('H01', 3, 'bad', definition_for('H01').evidence_contract, 'heater'),
                AdapterRegistration('H01', True, 'bad', definition_for('H01').evidence_contract, 'heater'),
                AdapterRegistration('H01', False, 'bad', definition_for('H01').evidence_contract, 'heater'),
                AdapterRegistration('H01', AUTOMATIC, '', definition_for('H01').evidence_contract, 'heater')):
            with self.subTest(adapter=adapter), self.assertRaises(ValueError):
                build_plan(self.snapshot, (adapter,))
        duplicate = installed('H01', AUTOMATIC)
        with self.assertRaises(ValueError):
            build_plan(self.snapshot, (duplicate, duplicate))

    def test_resonance_mixed_scope_uses_assigned_chip_axes_once(self):
        printer = SimpleNamespace(
            ready=True, epoch=5, objects=('toolhead', 'gcode_move'),
            settings={'adxl345 tool': {},
                      'lis2dw bed': {},
                      'resonance_tester': {
                          'accel_chip_x': 'adxl345 tool',
                          'accel_chip_y': 'lis2dw bed'}},
            status={})
        snap = discover(printer)
        plan = build_plan(snap, (installed('R02', AUTOMATIC),))
        rows = [r for r in plan if r.feature_id == 'R02']
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.device: r.axes for r in rows},
                         {'adxl345 tool': 1, 'lis2dw bed': 2})
        self.assertTrue(all(r.category == 'runnable' for r in rows))
        self.assertTrue(all(r.device is not None for r in rows))
        self.assertEqual({r.epoch for r in rows}, {5})

    def test_malicious_hidden_feature_and_stale_axes_are_not_planned(self):
        hidden_mask = _add(0, 'M17', AUTOMATIC)
        snap = MaintenanceSnapshot(42, global_modes=hidden_mask)
        self.assertEqual(build_plan(snap), ())
        fake = MaintenanceSnapshot(7, (
            DeviceCapabilities('adxl345', 'accelerometer',
                               _add(0, 'R02', AUTOMATIC), axes=0),),
            _add(0, 'R02', AUTOMATIC))
        self.assertEqual(build_plan(fake, (installed('R02', AUTOMATIC),)), ())

    def test_many_devices_no_persistent_sources_or_side_effects(self):
        device_bits = _add(0, 'F01', USER)
        snapshot = MaintenanceSnapshot(
            101,
            tuple(DeviceCapabilities('fan_generic f' + str(i), 'fan', device_bits)
                  for i in range(150)))
        rows = build_plan(snapshot)
        self.assertEqual(len(rows), 150)
        self.assertEqual(len(visible_plan(rows)), 0)
        self.assertTrue(all(row.adapter_id is None for row in rows))
        self.assertTrue(all(row.device.startswith('fan_generic f')
                            for row in rows))


if __name__ == '__main__':
    unittest.main()
