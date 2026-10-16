"""CI-only regression of role-based Maintenance actuator authorization."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance_profiles import read_profiles, approved_integrations, MAX_BYTES
from maintenance_discovery import discover
from maintenance_guided import guided_plan
from maintenance_pulse import compile_pulse


def state():
    return SimpleNamespace(
        ready=True, epoch=2,
        objects=('output_pin enclosure', 'output_pin tool_lamp',
                 'fan_generic aux', 'neopixel board'),
        settings={
            'output_pin enclosure': {'pin': 'PB1', 'pwm': True, 'scale': 1},
            'output_pin tool_lamp': {'pin': 'PC2', 'pwm': True, 'scale': 1},
            'pwm_cycle_time alert': {'pin': 'PB13', 'value': 0,
                                     'shutdown_value': 0, 'scale': 1},
            'pwm_cycle_time beep2': {'pin': 'PB14', 'value': 0,
                                     'shutdown_value': 0, 'scale': 1},
            'pwm_cycle_time heater': {'pin': 'PA8', 'value': 0,
                                     'shutdown_value': 0, 'scale': 1},
            'fan_generic aux': {'pin': 'PA4'},
            'neopixel board': {'pin': 'PA5'}},
        status={})


PROFILES = (('visual', 'output_pin enclosure'),
            ('visual', 'output_pin tool_lamp'),
            ('audible', 'pwm_cycle_time alert'),
            ('audible', 'pwm_cycle_time beep2'))


class ProfileTests(unittest.TestCase):
    def test_invalid_legacy_conflicting_and_oversize_profiles_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            self.assertEqual(read_profiles(path), ())
            for value in (
                    '{', '{}', '{"version":1,"case_light":true}',
                    '{"version":2,"actuators":"invalid"}',
                    '{"version":2,"actuators":[{"role":"visual","object":"output_pin x\\nM112"}]}',
                    '{"version":2,"actuators":[{"role":"visual","object":"pwm_cycle_time x"}]}',
                    '{"version":2,"actuators":[{"role":"audible","object":"output_pin x"}]}',
                    '{"version":2,"actuators":[{"role":"visual","object":"output_pin x","extra":1}]}',
                    '{"version":2,"actuators":[{"role":"visual","object":"output_pin x"},{"role":"visual","object":"output_pin X"}]}',
                    '{"version":2,"actuators":[{"role":"visual","object":"output_pin x"}],"extra":1}',
                    'x' * (MAX_BYTES + 1)):
                with self.subTest(value=value[:40]):
                    path.write_text(value, encoding='utf-8')
                    self.assertEqual(read_profiles(path), ())

    def test_v2_profile_reads_exact_role_object_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text(json.dumps({'version': 2, 'actuators': [
                {'role': 'visual', 'object': 'output_pin enclosure'},
                {'role': 'audible', 'object': 'pwm_cycle_time ALERT'},
                {'role': 'fan', 'object': 'fan_generic aux'},
                {'role': 'led', 'object': 'neopixel board'}]}), encoding='utf-8')
            self.assertEqual(read_profiles(path), (
                ('visual', 'output_pin enclosure'),
                ('audible', 'pwm_cycle_time alert'),
                ('fan', 'fan_generic aux'),
                ('led', 'neopixel board')))

    def test_multiple_outputs_discover_independently_without_hardcoded_names(self):
        p = state()
        keys = approved_integrations(p, PROFILES)
        self.assertEqual(set(keys), {
            'maintenance.visual:output_pin enclosure',
            'maintenance.visual:output_pin tool_lamp',
            'maintenance.audible:pwm_cycle_time alert',
            'maintenance.audible:pwm_cycle_time beep2'})
        self.assertNotIn('maintenance.audible:pwm_cycle_time heater', keys)
        snap = discover(p, keys)
        actual = {(r.feature_id, r.device) for r in guided_plan(snap)}
        self.assertTrue({('O03', 'output_pin enclosure'),
                         ('O03', 'output_pin tool_lamp'),
                         ('S18', 'pwm_cycle_time alert'),
                         ('S18', 'pwm_cycle_time beep2')} <= actual)
        self.assertNotIn(('S18', None), actual)
        self.assertNotIn(('S18', 'pwm_cycle_time heater'), actual)
        self.assertEqual(snap.method('S18', 'pwm_cycle_time alert'), 2)

    def test_unsafe_or_missing_config_disables_only_matching_role(self):
        p = state()
        p.objects = ('output_pin enclosure',)
        keys = approved_integrations(p, PROFILES)
        self.assertNotIn('maintenance.visual:output_pin tool_lamp', keys)
        self.assertIn('maintenance.audible:pwm_cycle_time alert', keys)
        for field, bad in (('pin', ''), ('value', .1), ('shutdown_value', 1),
                           ('scale', 0)):
            with self.subTest(field=field):
                original = p.settings['pwm_cycle_time alert'][field]
                p.settings['pwm_cycle_time alert'][field] = bad
                self.assertNotIn('maintenance.audible:pwm_cycle_time alert',
                                 approved_integrations(p, PROFILES))
                self.assertIn('maintenance.audible:pwm_cycle_time beep2',
                              approved_integrations(p, PROFILES))
                p.settings['pwm_cycle_time alert'][field] = original
        p.settings['output_pin enclosure']['pwm'] = False
        self.assertNotIn('maintenance.visual:output_pin enclosure',
                         approved_integrations(p, PROFILES))

    def test_other_pin_never_becomes_audible_without_profile(self):
        p = state()
        keys = approved_integrations(p, (('audible', 'pwm_cycle_time alert'),))
        snap = discover(p, keys)
        row = next(r for r in guided_plan(snap) if r.feature_id == 'S18')
        other = discover(p, approved_integrations(
            p, (('audible', 'pwm_cycle_time heater'),)))
        self.assertNotEqual(row.device, next(
            r for r in guided_plan(other) if r.feature_id == 'S18').device)
        with self.assertRaises(ValueError):
            compile_pulse(row, other, {}, p.settings, pin_command_name='Heater')

    def test_fan_and_led_still_require_registered_object(self):
        p = state()
        roles = (('fan', 'fan_generic aux'), ('led', 'neopixel board'))
        keys = approved_integrations(p, roles)
        self.assertIn('maintenance.safe_fan:fan_generic aux', keys)
        self.assertIn('maintenance.safe_led:neopixel board', keys)
        p.objects = ()
        self.assertEqual(approved_integrations(p, roles), ())

    def test_profiles_cached_once_per_ready_epoch(self):
        from maintenance_session import MaintenanceDiscoveryManager
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text(json.dumps({'version': 2, 'actuators': [
                {'role': 'visual', 'object': 'output_pin enclosure'}]}),
                encoding='utf-8')
            p = state()
            manager = MaintenanceDiscoveryManager(profile_path=path)
            first = manager.ready(p)
            self.assertIn('maintenance.visual:output_pin enclosure',
                          first.service_key)
            path.write_text('{"version":2,"actuators":[]}', encoding='utf-8')
            self.assertIs(manager.ready(p), first)
            p.epoch = 3
            newer = manager.ready(p)
            self.assertNotIn('maintenance.visual:output_pin enclosure',
                             newer.service_key)


if __name__ == '__main__':
    unittest.main()
