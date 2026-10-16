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
        if feature in ('F01', 'F02', 'F12'):
            name = 'fan'; family = 'fan'
            settings[name] = {'pin': 'PA3'}
            status[name] = {'speed': .35}
        elif feature == 'F04':
            name = 'fan_generic part_aux'; family = 'fan'
            settings[name] = {'pin': 'PA5'}
            status[name] = {'speed': .18}
        elif feature == 'O03':
            name = 'output_pin enclosure'; family = 'actuator'
            settings[name] = {'pin': 'PB1', 'pwm': True, 'scale': 1}
            status[name] = {'value': .25}
        elif feature == 'S18':
            name = 'pwm_cycle_time alert'; family = 'actuator'
            settings[name] = {'pin': 'PB13', 'scale': 1,
                              'value': 0, 'shutdown_value': 0}
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
    snap = MaintenanceSnapshot(4, tuple(devices), 0,
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

    def test_f02_three_bounded_pwm_steps_and_exact_restore(self):
        snap, settings, status = environment(('F02',))
        settings['fan'].update({'off_below': .05, 'max_power': .90})
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings)
        self.assertEqual(p.feature_id, 'F02')
        self.assertEqual(p.duration_ms, 6000)
        self.assertEqual(p.stimulus.splitlines(),
                         ['M106 S99', 'M106 S164', 'M106 S230'])
        self.assertEqual(p.script.count('G4 P2000'), 3)
        self.assertTrue(p.script.endswith('M106 S89'))
        self.assertIn('low/mid/high', p.observation)
        self.assertTrue(restored(p, status))
        self.assertFalse(restored(p, {'fan': {'speed': .9}}))

    def test_f12_adaptive_five_stage_restoration_and_safety(self):
        snap, settings, status = environment(('F12',))
        settings['fan'].update({'off_below': .05, 'max_power': .95, 'min_power': .0})
        status['fan']['speed'] = 0.0
        p = compile_pulse(guided_plan(snap)[0], snap, status, settings)
        self.assertEqual(p.feature_id, 'F12')
        self.assertEqual(p.pwm_levels, (25, 50, 76, 101, 127))
        self.assertEqual(p.duration_ms, 17500)
        self.assertEqual(p.script.count('G4 P2000'), 5)
        self.assertEqual(p.script.count('M106 S0'), 10)
        self.assertTrue(p.script.endswith('M106 S0\\nM400'))
        self.assertTrue(restored(p, status))
        from maintenance_f12 import F12Bracket
        from maintenance_pulse import f12_round_program
        next_program = f12_round_program(p, F12Bracket(76, 101))
        self.assertEqual(next_program.pwm_levels, (81, 86, 91, 96, 101))
        self.assertEqual(next_program.script.count('G4 P2000'), 5)
        self.assertTrue(next_program.script.endswith('M106 S0\\nM400'))
        status['fan']['speed'] = .35
        with self.assertRaisesRegex(ValueError, 'f12_requires_fan_initially_off'):
            compile_pulse(guided_plan(snap)[0], snap, status, settings)
        status['fan']['speed'] = 0.0

    def test_f02_blocks_unusable_limits_and_invalid_baseline(self):
        snap, settings, status = environment(('F02',))
        row = guided_plan(snap)[0]
        for lo, hi in ((0, .25), (.4, .4), (.8, .3),
                       (None, 1), (0, float('nan')), (0, 2)):
            with self.subTest(lo=lo, hi=hi):
                settings['fan'].update({'off_below': lo, 'max_power': hi})
                with self.assertRaises(ValueError):
                    compile_pulse(row, snap, status, settings)
        settings['fan'].update({'off_below': 0, 'max_power': 1})
        status['fan']['speed'] = None
        with self.assertRaisesRegex(ValueError, 'fan_speed_unavailable'):
            compile_pulse(row, snap, status, settings)

    def test_generic_fan_is_specific_and_templates_are_blocked(self):
        snap, settings, status = environment(('F04',))
        p = compile_pulse(guided_plan(snap)[0], snap, status, settings)
        self.assertIn('FAN=part_aux', p.stimulus)
        self.assertIn('SPEED=0.1800', p.restore)
        status['fan_generic part_aux']['template'] = 'pulse'
        with self.assertRaises(ValueError):
            compile_pulse(guided_plan(snap)[0], snap, status, settings)

    def test_generic_visual_output_requires_role_pwm_and_restores(self):
        snap, settings, status = environment(
            ('O03',), ('maintenance.visual:output_pin enclosure',))
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings, pin_command_name='Enclosure')
        self.assertIn('PIN=Enclosure VALUE=0.7000', p.stimulus)
        self.assertIn('PIN=Enclosure VALUE=0.2500', p.restore)
        self.assertTrue(restored(p, status))
        settings['output_pin enclosure']['scale'] = 2
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings, pin_command_name='Enclosure')
        settings['output_pin enclosure']['scale'] = 1
        status['output_pin enclosure']['value'] = .7
        p = compile_pulse(row, snap, status, settings, pin_command_name='Enclosure')
        self.assertIn('VALUE=0.2000', p.stimulus)
        status['output_pin enclosure']['value'] = None
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings, pin_command_name='Enclosure')
        for bad in (None, 'other', 'Enclosure\nM112'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                compile_pulse(row, snap, {'output_pin enclosure': {'value': .2}},
                              settings, pin_command_name=bad)

    def test_single_led_restore_and_multiled_blocked(self):
        snap, settings, status = environment(('O04',))
        row = guided_plan(snap)[0]
        p = compile_pulse(row, snap, status, settings)
        self.assertIn('SET_LED LED=case', p.script)
        self.assertTrue(restored(p, status))
        status['neopixel case']['color_data'] = [(0., 0., 0., 0.), (0., 0., 0., 0.)]
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings)

    def test_generic_config_only_audible_output_never_fakes_readback(self):
        snap, settings, status = environment(
            ('S18',), ('maintenance.audible:pwm_cycle_time alert',))
        row = next(r for r in guided_plan(snap) if r.feature_id == 'S18')
        p = compile_pulse(row, snap, status, settings, pin_command_name='Alert')
        denied = MaintenanceSnapshot(snap.epoch, snap.devices, snap.global_modes,
                                     snap.config_marker, ())
        with self.assertRaises(ValueError):
            compile_pulse(row, denied, status, settings, pin_command_name='Alert')
        self.assertIn('CYCLE_TIME=0.00062500', p.stimulus)
        self.assertIn('PIN=Alert', p.stimulus)
        self.assertEqual(p.duration_ms, 200)
        self.assertEqual(p.read_path, '')
        self.assertEqual(p.script, 'SET_PIN PIN=Alert VALUE=0\nG4 P50\n'
                         'SET_PIN PIN=Alert VALUE=0.2500 CYCLE_TIME=0.00062500\n'
                         'G4 P150\nSET_PIN PIN=Alert VALUE=0')
        self.assertFalse(restored(p, status))
        self.assertFalse(restored(p, {'pwm_cycle_time alert': {'value': 0}}))
        status['pwm_cycle_time alert'] = {'value': .2}
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings, pin_command_name='Alert')
        status.clear()
        settings['pwm_cycle_time alert']['value'] = .2
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings, pin_command_name='Alert')
        settings['pwm_cycle_time alert']['value'] = 0
        for invalid in (None, 'Other', 'Alert\nM112'):
            with self.subTest(name=invalid), self.assertRaises(ValueError):
                compile_pulse(row, snap, status, settings, pin_command_name=invalid)

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
