"""Negative safety and documentation/registry boundaries."""
from pathlib import Path
import unittest
from maintenance_thermal import contract
from maintenance_heater import thermal_adapters
from maintenance_executor import read_only_adapters

class ThermalAuditTests(unittest.TestCase):
    def test_command_override_is_not_a_trusted_heater_api(self):
        settings = {'extruder': {'heater_pin': 'PA1', 'min_temp': 0., 'max_temp': 280.},
                    'gcode_macro SET_HEATER_TEMPERATURE': {'rename_existing': 'BASE_HEAT'}}
        with self.assertRaisesRegex(ValueError, 'overridden'):
            contract('extruder', settings,
                {'extruder': {'temperature': 25., 'target': 0., 'power': 0.}}, 'H01')

    def test_conditional_ids_have_no_fictional_registered_adapter(self):
        registered = {r.feature_id for r in (*thermal_adapters(), *read_only_adapters())}
        for feature in ('H10', 'H12', 'H15', 'H17', 'H18'):
            self.assertNotIn(feature, registered)
        self.assertTrue({'H01', 'H02', 'H03', 'H04', 'H05', 'H06', 'H07',
                         'H08', 'H09', 'H11', 'H13', 'H14', 'H16'} <= registered)

    def test_bilingual_scope_covers_every_h_id_without_accepting_hardware(self):
        docs = Path(__file__).resolve().parents[1] / 'docs'
        for name in ('maintenance-thermal.md', 'maintenance-thermal_TR.md'):
            text = (docs / name).read_text()
            for n in range(1, 19):
                self.assertIn('H%02d' % n, text)
        from test_maintenance_reference_printer_acceptance import ledger
        self.assertFalse(any(e['status'] == 'accepted' for e in ledger()['entries']
                             if e['feature_id'].startswith('H')))
