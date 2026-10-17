"""CI-only regression coverage for the passive Maintenance test catalog."""
import dataclasses
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_catalog import CATALOG, candidate_methods, definition_for
from maintenance_discovery import (
    ALWAYS_HIDDEN, AUTOMATIC, USER, EXTERNAL, CALIBRATION,
    INFORMATION, NONE, FEATURE_COUNT, discover,
)


class MaintenanceCatalogTests(unittest.TestCase):
    def test_all_121_ids_are_unique_and_ordered(self):
        expected = tuple(
            f'{group}{n:02d}' for group, count in
            (('F', 13), ('H', 18), ('M', 17), ('P', 22),
             ('R', 8), ('E', 15), ('S', 20), ('O', 8))
            for n in range(1, count + 1))
        self.assertEqual(len(CATALOG), FEATURE_COUNT)
        self.assertEqual(tuple(item.feature_id for item in CATALOG), expected)
        self.assertTrue(all(definition_for(key) is value
                            for key, value in zip(expected, CATALOG)))

    def test_hidden_ids_are_exact_and_fail_closed(self):
        hidden = {entry.feature_id for entry in CATALOG if entry.methods == NONE}
        self.assertEqual(hidden, ALWAYS_HIDDEN)
        self.assertEqual(len(hidden), 8)
        self.assertTrue(all(definition_for(fid).safety_profile == 'hidden'
                            for fid in hidden))
        for key in ('F00', 'F14', 'P23', 'S21', 'Z01', 'F1', '', 'F01x', None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                definition_for(key)

    def test_catalog_is_immutable_and_has_no_registered_adapters(self):
        self.assertTrue(all(not entry.implemented and entry.adapter_id is None
                            for entry in CATALOG))
        self.assertTrue(all(entry.title and entry.evidence_contract
                            for entry in CATALOG))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            CATALOG[0].adapter_id = 'unauthorized'
        with self.assertRaises(dataclasses.FrozenInstanceError):
            CATALOG[0].methods = AUTOMATIC

    def test_scope_and_method_contracts(self):
        self.assertEqual(definition_for('F01').scope, 'device')
        self.assertEqual(definition_for('F01').methods, AUTOMATIC | USER)
        self.assertEqual(definition_for('H01').safety_profile, 'heater')
        self.assertEqual(definition_for('M07').scope, 'device')
        self.assertEqual(definition_for('M07').methods, AUTOMATIC | INFORMATION)
        self.assertEqual(definition_for('M10').methods, NONE)
        self.assertEqual(definition_for('M10').safety_profile, 'hidden')
        self.assertEqual(definition_for('M11').feature_id, 'M11')
        self.assertEqual(candidate_methods('M10', AUTOMATIC | INFORMATION), NONE)
        self.assertEqual(definition_for('M01').scope, 'mixed')
        self.assertEqual(definition_for('R02').scope, 'mixed')
        self.assertEqual(definition_for('R04').methods, CALIBRATION)
        self.assertEqual(definition_for('E02').methods, EXTERNAL)
        self.assertEqual(definition_for('S01').methods, INFORMATION)
        self.assertEqual(definition_for('O03').safety_profile, 'actuator')

    def test_discovery_overlap_is_not_run_permission(self):
        printer = SimpleNamespace(
            ready=True, epoch=42,
            objects=('fan', 'extruder', 'heater_bed', 'tmc2208 stepper_x',
                     'tmc2208 stepper_y', 'toolhead', 'gcode_move'),
            settings={'extruder': {'min_temp': 0, 'max_temp': 290},
                      'heater_bed': {'min_temp': 0, 'max_temp': 120}},
            status={})
        snapshot = discover(printer)
        self.assertEqual(len(snapshot.instances('H01')), 2)
        self.assertEqual(len(snapshot.instances('M07')), 2)
        self.assertEqual(snapshot.method('F01', 'fan'), USER)
        self.assertEqual(candidate_methods('F01', snapshot.method('F01', 'fan')), USER)
        self.assertEqual(candidate_methods('M07', snapshot.method('M07')), AUTOMATIC | INFORMATION)
        self.assertEqual(candidate_methods('S01', snapshot.method('S01')), NONE)
        self.assertTrue(all(not definition_for(fid).implemented
                            for fid in snapshot.available_features()))

    def test_unsupported_and_untrusted_masks_are_rejected(self):
        self.assertEqual(candidate_methods('M17', AUTOMATIC), NONE)
        self.assertEqual(candidate_methods('S01', AUTOMATIC), NONE)
        for mask in (-1, 32, True, '1', None):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                candidate_methods('F01', mask)

    def test_information_only_never_implies_functional_pass(self):
        info = [entry for entry in CATALOG
                if entry.methods == INFORMATION]
        self.assertTrue(info)
        self.assertTrue(all(not entry.implemented for entry in info))


if __name__ == '__main__':
    unittest.main()
