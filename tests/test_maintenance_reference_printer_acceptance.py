"""Static regression for the sanitized reference-printer acceptance tracker.

Runs only on GitHub Actions: no Klipper connections, filesystem writes
or physical commands. This ledger is NOT a generic runtime hardware allowlist.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
SOURCE = DOCS / 'maintenance-reference-printer-acceptance.json'
EN = DOCS / 'maintenance-reference-printer-acceptance.md'
TR = DOCS / 'maintenance-reference-printer-acceptance_TR.md'
ROW = re.compile(r'^\|\s+\[([x ])\]\s+\|\s+([FHMPRESO]\d{2})\s+\|\s+\x60([^\x60]+)\x60\s+\|')
VALID = {'accepted', 'pending', 'conditional', 'not_applicable'}
ADAPTERS = {'implemented', 'not_implemented'}
ACCEPTED_RESULTS = {'PASSED_USER', 'OBSERVED_USER'}


def ledger():
    return json.loads(SOURCE.read_text(encoding='utf-8'))


def read_rows(path):
    rows = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        found = ROW.match(line)
        if found is None:
            continue
        key = found.group(2), found.group(3)
        if key in rows:
            raise ValueError('duplicate row ' + repr(key))
        rows[key] = found.group(1) == 'x'
    return rows


class ReferenceAcceptanceTests(unittest.TestCase):
    def test_json_contract_and_provenance(self):
        data = ledger()
        self.assertEqual(data['schema_version'], 1)
        self.assertFalse(data['evidence']['exact_live_id_inventory_recorded'])
        p = data['policy']
        self.assertEqual(p['working_branch'], 'feature/maintenance-test-engine')
        self.assertTrue(p['operator_observation_required_for_physical_acceptance'])
        self.assertTrue(p['ci_is_not_physical_acceptance'])
        self.assertTrue(p['acceptance_per_target'])
        self.assertTrue(p['bilingual_docs_must_match'])
        self.assertTrue(p['no_master_merge_without_request'])
        self.assertTrue(data['entries'])
        keys = set()
        for entry in data['entries']:
            key = entry['feature_id'], entry['target']
            with self.subTest(key=key):
                self.assertRegex(entry['feature_id'], r'^[FHMPRESO]\d{2}$')
                self.assertIsInstance(entry['target'], str)
                self.assertTrue(entry['target'])
                self.assertNotIn(key, keys)
                keys.add(key)
                self.assertIn(entry['status'], VALID)
                self.assertIn(entry['adapter'], ADAPTERS)
                self.assertNotEqual(entry['method'], 'I')
                if entry['status'] == 'accepted':
                    evidence = entry['acceptance']
                    self.assertIsInstance(evidence, dict)
                    self.assertEqual(evidence.get('source'),
                                     'user_explicit_physical_observation')
                    self.assertRegex(evidence.get('date', ''),
                                     r'^\d{4}-\d{2}-\d{2}$')
                    self.assertIn(evidence.get('controller_result'), ACCEPTED_RESULTS)
                    self.assertIs(type(evidence.get('restore_verified')), bool)
                    self.assertIsInstance(evidence.get('observation'), str)
                    self.assertGreater(len(evidence['observation'].strip()), 20)
                    self.assertEqual(entry['adapter'], 'implemented')
                else:
                    self.assertIsNone(entry['acceptance'])
                if entry['status'] == 'conditional':
                    self.assertEqual(entry['reference'], 'conditional')
                if entry['status'] == 'not_applicable':
                    self.assertEqual(entry['reference'], 'absent')

    def test_en_tr_tables_are_identical_to_canonical_ledger(self):
        data = ledger()
        expected = {(e['feature_id'], e['target']): e['status'] == 'accepted'
                    for e in data['entries']}
        self.assertEqual(read_rows(EN), expected)
        self.assertEqual(read_rows(TR), expected)
        for path in (EN, TR):
            body = path.read_text(encoding='utf-8')
            self.assertIn('maintenance-reference-printer-acceptance.json', body)
            self.assertIn('54', body)  # historical count; not exact live ID dump
            self.assertIn('F02', body)

    def test_historical_physical_acceptances_are_preserved(self):
        by_target = {(e['feature_id'], e['target']): e for e in ledger()['entries']}
        confirmed = [('F01', 'fan'), ('S18', 'pwm_cycle_time Buzzer'),
                     ('O03', 'output_pin case_light'),
                     ('O04', 'neopixel mmu_leds')]
        for key in confirmed:
            self.assertEqual(by_target[key]['status'], 'accepted')
        for key in confirmed[1::2]:
            self.assertFalse(by_target[key]['acceptance']['restore_verified'])
        self.assertEqual(by_target[('F04', 'fan_generic (not installed)')]
                         ['status'], 'not_applicable')
        # F02 was accepted by the operator on the old 800 ms/stage
        # revision, but the new 2000 ms/stage program is not accepted yet.
        from maintenance_pulse import _FAN_STEP_MS
        old_f02 = by_target[('F02', 'fan')]
        self.assertEqual(old_f02['status'], 'accepted')
        self.assertEqual(old_f02['adapter'], 'implemented')
        self.assertTrue(old_f02['retest_required'])
        self.assertEqual(old_f02['acceptance']['tested_step_duration_ms'], 800)
        self.assertEqual(old_f02['acceptance']['tested_program_duration_ms'], 2400)
        self.assertEqual(old_f02['acceptance']['controller_result'], 'PASSED_USER')
        self.assertTrue(old_f02['acceptance']['restore_verified'])
        self.assertEqual(_FAN_STEP_MS, 2000)
        self.assertNotEqual(old_f02['acceptance']['tested_step_duration_ms'], _FAN_STEP_MS)
        attempt = old_f02['latest_attempt']
        self.assertEqual(attempt['controller_result'], 'INCONCLUSIVE')
        self.assertIsNone(attempt['restore_verified'])
        self.assertFalse(attempt['operator_confirmation_requested'])
        self.assertEqual(attempt['tested_step_duration_ms'], 2000)
        self.assertNotEqual(attempt['tested_signed_head'],
                            old_f02['acceptance']['tested_signed_head'])
        self.assertIn('YENİDEN TEST', TR.read_text(encoding='utf-8'))
        self.assertIn('RETEST REQUIRED', EN.read_text(encoding='utf-8'))
        o04 = by_target[('O04', 'neopixel mmu_leds')]
        self.assertEqual(o04['status'], 'accepted')  # Prior PASS is historical.
        self.assertTrue(o04['retest_required'])
        self.assertEqual(o04['latest_attempt']['controller_result'], 'BLOCKED')
        self.assertEqual(o04['latest_attempt']['controller_reason'],
                         'mmu_led_not_enabled_or_readable')
        self.assertFalse(o04['latest_attempt']['operator_confirmation_requested'])
        self.assertIsNone(o04['latest_attempt']['restore_verified'])



if __name__ == '__main__':
    unittest.main()
