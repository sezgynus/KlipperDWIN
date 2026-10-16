"""Device-specific thermal information: never physical PASS."""
import unittest
from maintenance_executor import _read_fields, read_only_adapters
from maintenance_discovery import INFORMATION

class ThermalReadTests(unittest.TestCase):
    def test_target_and_eventtime_are_required(self):
        reply = {'result': {'eventtime': 10., 'status': {
            'temperature_sensor room': {'temperature': 24.5},
            'extruder': {'power': .25}}}}
        self.assertEqual(_read_fields('H14', reply, 'temperature_sensor room'),
                         (('klipper_eventtime_s', 10.), ('temperature', 24.5)))
        self.assertEqual(_read_fields('H11', reply, 'extruder')[-1], ('power', .25))
        self.assertEqual(_read_fields('H14', reply, 'missing'), ())
        del reply['result']['eventtime']
        self.assertEqual(_read_fields('H11', reply, 'extruder'), ())

    def test_malformed_and_nonfinite_values_are_not_evidence(self):
        for value in (True, float('nan'), float('inf'), -1, 1.1):
            reply = {'result': {'eventtime': 1., 'status': {'extruder': {'power': value}}}}
            self.assertEqual(_read_fields('H11', reply, 'extruder'), ())

    def test_environment_is_bounded_and_no_temperature_is_invented(self):
        reply = {'result': {'eventtime': 1., 'status': {'sensor': {
            'humidity': 40., 'pressure': 1010., 'secret': 'private'}}}}
        self.assertEqual(len(_read_fields('H16', reply, 'sensor')), 3)
        self.assertEqual(_read_fields('H14', reply, 'sensor'), ())

    def test_registrations_are_information_only(self):
        entries = {r.feature_id: r for r in read_only_adapters()}
        for feature in ('H11', 'H14', 'H16'):
            self.assertEqual(entries[feature].method, INFORMATION)

    def test_ui_keeps_device_optional_for_legacy_global_rows(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / 'ui_maintenance.py').read_text()
        self.assertIn("getattr(item, 'device', None)", source)
        self.assertIn("getattr(row, 'device', None)", source)
