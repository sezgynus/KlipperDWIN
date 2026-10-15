"""CI regressions for exact, restore-bearing physical pulse programs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, _add
from maintenance_guided import guided_plan
from maintenance_pulse import compile_pulse, restored


def environment(features=('F01',), services=()):
    devices = []
    settings = {}
    status = {}
    for feature in features:
        if feature == 'F01':
            name = 'fan'; family = 'fan'
            settings[name] = {'pin': 'PA3'}
            status[name] = {'speed': .35}
        elif feature == 'F04':
            name = 'fan_generic part_aux'; family = 'fan'
            settings[name] = {'pin': 'PA5'}
            status[name] = {'speed': .18}
        elif feature == 'O03':
            name = 'output_pin case_light'; family = 'actuator'
            settings[name] = {'pwm': True, 'scale': 1}
            status[name] = {'value': .25}
        else:
            name = 'neopixel case'; family = 'led'
            settings[name] = {'color_order': 'GRB'}
            status[name] = {'color_data': [(1., .0, .2, .0)]}
        devices.append(DeviceCapabilities(name, family, _add(0, feature, USER)))
    allow = set(services)
    for item in devices:
        if item.family == 'led':
            allow.add('maintenance.safe_led:' + item.name)
        if item.name.startswith('fan_generic '):
            allow.add('maintenance.safe_fan:' + item.name)
    snap = MaintenanceSnapshot(4, tuple(devices), _add(0, 'S18', USER),
                               id(settings), tuple(sorted(allow)))
    return snap, settings, status


class PhysicalPulseTests(unittest.TestCase):
    def test_part_fan_is_bounded_and_restores_baseline(self):
        snap, settings, status = environment()
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings)
        self.assertEqual(p.stimulus, 'M106 S191')
        self.assertEqual(p.restore, 'M106 S89')
        self.assertEqual(p.duration_ms, 950)
        self.assertEqual(p.script, 'M106 S191\nG4 P950\nM106 S89')
        self.assertTrue(restored(p, status))
        self.assertFalse(restored(p, {'fan': {'speed': .75}}))

    def test_generic_fan_is_specific_and_templates_are_blocked(self):
        snap, settings, status = environment(('F04',))
        p = compile_pulse(guided_plan(snap)[0], snap, status, settings)
        self.assertIn('FAN=part_aux', p.stimulus)
        self.assertIn('SPEED=0.1800', p.restore)
        status['fan_generic part_aux']['template'] = 'pulse'
        with self.assertRaises(ValueError):
            compile_pulse(guided_plan(snap)[0], snap, status, settings)

    def test_case_light_requires_explicit_profile_pwm_and_restore(self):
        snap, settings, status = environment(
            ('O03',), ('maintenance.safe_pin:output_pin case_light',))
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings)
        self.assertIn('VALUE=0.2500', p.restore)
        self.assertTrue(restored(p, status))
        settings['output_pin case_light']['scale'] = 2
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings)
        settings['output_pin case_light']['scale'] = 1
        status['output_pin case_light']['value'] = None
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings)

    def test_single_led_restore_and_multiled_blocked(self):
        snap, settings, status = environment(('O04',))
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings)
        self.assertIn('SET_LED LED=case', p.script)
        self.assertTrue(restored(p, status))
        status['neopixel case']['color_data'] = [(0., 0., 0., 0.), (0., 0., 0., 0.)]
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings)

    def test_buzzer_requires_exact_off_status_and_profile(self):
        snap, settings, status = environment(
            (), ('petrel.buzzer', 'maintenance.buzzer_output:tick'))
        settings['pwm_cycle_time tick'] = {'scale': 1, 'shutdown_value': 0}
        status['pwm_cycle_time tick'] = {'value': 0}
        row = next(r for r in guided_plan(snap) if r.feature_id == 'S18')
        p = compile_pulse(row, snap, status, settings, buzzer_output='tick')
        denied = MaintenanceSnapshot(snap.epoch, snap.devices, snap.global_modes,
                                     snap.config_marker, ('petrel.buzzer',))
        with self.assertRaises(ValueError):
            compile_pulse(row, denied, status, settings, buzzer_output='tick')
        self.assertIn('CYCLE_TIME=0.00062500', p.stimulus)
        self.assertEqual(p.duration_ms, 150)
        self.assertTrue(restored(p, status))
        status['pwm_cycle_time tick']['value'] = .2
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings, buzzer_output='tick')

    def test_unknown_programs_cannot_inject_macros_or_modify_heaters(self):
        snap, settings, status = environment(('F04',))
        row = guided_plan(snap)[0]
        for bad in ('hotend fan', 'foo\nM109 S300', 'slash;M106', 'x' * 100):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                compile_pulse(row, snap, {'fan_generic ' + bad: {'speed': .3}}, settings)
        self.assertNotIn('TURN_OFF_HEATERS', compile_pulse(
            row, snap, status, settings).script)

    def test_no_fake_success_for_missing_or_malformed_telemetry(self):
        snap, settings, status = environment()
        row = guided_plan(snap)[0]
        for bad in (None, True, float('nan'), 1.5, -1):
            with self.subTest(bad=bad):
                status['fan']['speed'] = bad
                with self.assertRaises(ValueError):
                    compile_pulse(row, snap, status, settings)
        status['fan']['speed'] = .2
        p = compile_pulse(row, snap, status, settings)
        self.assertFalse(restored(p, {}))
        self.assertFalse(restored(p, {'fan': {'speed': float('nan')}}))


if __name__ == '__main__':
    unittest.main()
