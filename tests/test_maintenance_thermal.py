import unittest
from maintenance_thermal import contract, sample, Sample, ThermalSeries

class ThermalContractTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'extruder': {'heater_pin': 'PA1', 'min_temp': 0., 'max_temp': 280.}}
        self.status = {'extruder': {'temperature': 25., 'target': 0., 'power': 0.}}

    def test_bounded_program_contains_its_own_off(self):
        c = contract('extruder', self.settings, self.status, 'H01')
        self.assertEqual(c.target, 60.)
        self.assertEqual(c.script.splitlines()[-1], c.off)
        self.assertIn('G4 P120000\nM400\n' + c.off, c.script)
        self.assertNotIn('SAVE_CONFIG', c.script)

    def test_h_group_uses_klipper_configured_limit_not_target_plus_ten(self):
        for feature in ('H01', 'H02', 'H03', 'H04', 'H05',
                        'H06', 'H07', 'H08', 'H09', 'H13'):
            profile = (60., 120.) if feature == 'H04' else None
            settings = dict(self.settings)
            if feature == 'H04':
                settings = {'heater_generic dryer': settings['extruder']}
                status = {'heater_generic dryer': self.status['extruder']}
                device = 'heater_generic dryer'
            else:
                status, device = self.status, 'extruder'
            result = contract(device, settings, status, feature, profile)
            self.assertEqual(result.ceiling, 280.)
            self.assertEqual(result.max_temp, 280.)
            self.assertGreater(result.ceiling, result.target + 10.)
        old_profile = contract('heater_generic dryer',
                               {'heater_generic dryer': self.settings['extruder']},
                               {'heater_generic dryer': self.status['extruder']},
                               'H04', (60., 70., 120.))
        self.assertEqual(old_profile.ceiling, 280.)

    def test_unsafe_or_unknown_states_block(self):
        for key, value in (('target', 50), ('power', .1), ('temperature', 70),
                           ('temperature', float('nan')), ('target', True)):
            status = {'extruder': dict(self.status['extruder'], **{key: value})}
            with self.assertRaises(ValueError):
                contract('extruder', self.settings, status, 'H01')
        with self.assertRaises(ValueError):
            contract('extruder\nM112', self.settings, self.status, 'H01')

    def test_other_heater_cannot_be_unknown_or_on(self):
        self.settings['heater_bed'] = dict(self.settings['extruder'])
        with self.assertRaisesRegex(ValueError, 'another_heater'):
            contract('extruder', self.settings, self.status, 'H01')

    def test_no_generic_temperature_guesses(self):
        self.settings['heater_generic chamber'] = self.settings['extruder']
        self.status['heater_generic chamber'] = self.status['extruder']
        with self.assertRaisesRegex(ValueError, 'profile_required'):
            contract('heater_generic chamber', self.settings, self.status, 'H01')

    def test_sample_requires_authoritative_timestamp_and_numeric_values(self):
        reply = {'result': {'eventtime': 12., 'status': self.status}}
        self.assertEqual(sample(reply, 'extruder').temperature, 25.)
        reply['result']['eventtime'] = True
        with self.assertRaises(ValueError):
            sample(reply, 'extruder')

class ThermalMetricsTests(unittest.TestCase):
    def test_independent_metrics_and_no_stability_before_full_window(self):
        s = ThermalSeries()
        for t in range(0, 121, 2):
            s.add(Sample(t, min(60., 25+t), 60., .5))
        for f in ('H01', 'H05', 'H06', 'H07', 'H08', 'H13'):
            self.assertTrue(s.evaluate(f, 60.)[0], f)
        self.assertFalse(s.evaluate('H09', 60.)[0])
        for t in range(122, 155, 2):
            s.add(Sample(t, 60-(t-120)*.2, 0., 0.))
        self.assertTrue(s.evaluate('H09', 60.)[0])

    def test_duplicate_gap_capacity_and_insufficient_data(self):
        s = ThermalSeries()
        s.add(Sample(1, 25, 60, .5))
        for t in (1, 0, 7):
            with self.assertRaises(ValueError):
                s.add(Sample(t, 26, 60, .5))
        with self.assertRaises(ValueError):
            s.evaluate('H01', 60)
        s = ThermalSeries()
        for t in range(256):
            s.add(Sample(t, 25, 60, .5))
        with self.assertRaises(ValueError):
            s.add(Sample(256, 25, 60, .5))

    def test_overshoot_and_unreached_target_are_separate(self):
        s = ThermalSeries()
        for t, temp in enumerate((25, 60, 70)):
            s.add(Sample(t, temp, 60, .5))
        self.assertTrue(s.evaluate('H06', 60)[0])
        self.assertFalse(s.evaluate('H07', 60)[0])
        self.assertFalse(s.evaluate('H08', 60)[0])

    def test_selected_metric_is_first_for_small_lcd_result(self):
        s = ThermalSeries()
        for t in range(0, 50, 2):
            s.add(Sample(t, 60-t*.2, 0., 0.))
        ok, evidence = s.evaluate('H09', 60.)
        self.assertTrue(ok)
        self.assertEqual(evidence[0][0], 'cooling_c_per_s')
