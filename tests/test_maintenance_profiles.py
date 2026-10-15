"""No implicit actuator approvals: on-disk profile is explicit and bounded."""
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
        objects=('output_pin case_light', 'pwm_cycle_time tick',
                 'pwm_cycle_time heater'),
        settings={'output_pin case_light': {'pwm': True, 'scale': 1},
                  'pwm_cycle_time tick': {'value': 0, 'shutdown_value': 0, 'scale': 1},
                  'pwm_cycle_time heater': {'value': 0, 'shutdown_value': 0, 'scale': 1}},
        status={})


class ProfileTests(unittest.TestCase):
    def test_missing_invalid_or_oversize_file_grants_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            self.assertEqual(read_profiles(path), ())
            for value in (
                    '{', '{}', '{"version":1,"case_light":"yes"}',
                    '{"version":1,"case_light":true,"extra":1}',
                    '{"version":1,"buzzer_output":"tick\\nM109"}',
                    '{"version":2,"case_light":true}',
                    '{"version":1,"fan_generic_output":"x;M109"}',
                    '{"version":1,"led_output":"servo mmu"}',
                    'x' * (MAX_BYTES + 1)):
                path.write_text(value, encoding='utf-8')
                self.assertEqual(read_profiles(path), ())

    def test_profile_requires_positive_object_and_known_safe_config(self):
        p = state()
        self.assertEqual(approved_integrations(p, ()), ())
        self.assertEqual(approved_integrations(p, (False, '')), ())
        self.assertEqual(set(approved_integrations(p, (True, 'tick'))),
                         {'maintenance.safe_pin:output_pin case_light',
                          'petrel.buzzer', 'maintenance.buzzer_output:tick'})
        p.settings['output_pin case_light']['pwm'] = False
        self.assertNotIn('maintenance.safe_pin:output_pin case_light',
                         approved_integrations(p, (True, 'tick')))
        p.settings['pwm_cycle_time tick']['shutdown_value'] = 1
        self.assertNotIn('petrel.buzzer', approved_integrations(p, (True, 'tick')))

    def test_user_profile_json_and_device_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text(json.dumps({
                'version': 1, 'case_light': True, 'buzzer_output': 'tick'}),
                encoding='utf-8')
            allow = read_profiles(path)
            self.assertEqual(allow, (True, 'tick', '', ''))
            p = state()
            snap = discover(p, approved_integrations(p, allow))
            self.assertIn(('O03', 'output_pin case_light'),
                          {(r.feature_id, r.device) for r in guided_plan(snap)})
            self.assertIn(('S18', None),
                          {(r.feature_id, r.device) for r in guided_plan(snap)})
            p.objects = ('pwm_cycle_time heater',)
            self.assertEqual(approved_integrations(p, allow), ())

    def test_unlisted_pwm_pin_cannot_be_used_as_buzzer(self):
        p = state()
        services = approved_integrations(p, (True, 'tick'))
        snap = discover(p, services)
        row = next(r for r in guided_plan(snap) if r.feature_id == 'S18')
        status = {'pwm_cycle_time heater': {'value': 0}}
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, p.settings,
                          buzzer_output='heater')


    def test_generic_fan_and_led_need_exact_explicit_names(self):
        p = state()
        p.objects += ('fan_generic aux', 'neopixel board')
        p.settings.update({
            'fan_generic aux': {'pin': 'PA4'},
            'neopixel board': {'pin': 'PA5'}})
        keys = approved_integrations(
            p, (False, '', 'aux', 'neopixel board'))
        self.assertIn('maintenance.safe_fan:fan_generic aux', keys)
        self.assertIn('maintenance.safe_led:neopixel board', keys)
        self.assertNotIn('maintenance.safe_fan:fan_generic unknown', keys)
        p.objects = ('fan_generic aux',)
        self.assertNotIn('maintenance.safe_led:neopixel board',
                         approved_integrations(p, (False, '', 'aux', 'neopixel board')))

    def test_optional_discovery_manager_uses_profile_once_per_epoch(self):
        from maintenance_session import MaintenanceDiscoveryManager
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text('{"version":1,"case_light":true}', encoding='utf-8')
            p = state()
            manager = MaintenanceDiscoveryManager(profile_path=path)
            first = manager.ready(p)
            self.assertIn('maintenance.safe_pin:output_pin case_light',
                          first.service_key)
            path.write_text('{"version":1,"case_light":false}', encoding='utf-8')
            self.assertIs(manager.ready(p), first)
            p.epoch = 3
            newer = manager.ready(p)
            self.assertNotIn('maintenance.safe_pin:output_pin case_light',
                             newer.service_key)


if __name__ == '__main__':
    unittest.main()
