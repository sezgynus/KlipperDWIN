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

    def test_f12_operator_acceptance_tracks_adaptive_search_without_invented_pwm(self):
        data = ledger()
        by_target = {(entry['feature_id'], entry['target']): entry
                     for entry in data['entries']}
        f12 = by_target[('F12', 'fan')]
        self.assertEqual(f12['status'], 'accepted')
        self.assertEqual(f12['adapter'], 'implemented')
        evidence = f12['acceptance']
        self.assertEqual(evidence['controller_result'], 'PASSED_USER')
        self.assertTrue(evidence['restore_verified'])
        self.assertEqual(evidence['algorithm'], 'adaptive_five_stage_command_bracketing')
        self.assertFalse(evidence['threshold_reported'])
        self.assertNotIn('threshold_m106_s', evidence)
        self.assertIn('iterative', evidence['observation'])
        self.assertIn('kick-start', evidence['observation'])
        # Ensure the new ledger was not accidentally applied to another fan.
        self.assertEqual(by_target[('F04', 'fan_generic (not installed)')]
                         ['status'], 'not_applicable')
        self.assertEqual(len([e for e in data['entries']
                              if e['status'] == 'accepted']), 23)
        self.assertEqual(len([e for e in data['entries']
                              if e['status'] == 'pending']), 37)

    def test_h_implementation_does_not_grant_physical_acceptance(self):
        targets = [e for e in ledger()['entries']
                   if e['feature_id'].startswith('H') and e['reference'] == 'confirmed']
        self.assertEqual(len(targets), 16)
        for item in targets:
            self.assertEqual(item['adapter'], 'implemented')
            self.assertEqual(item['status'], 'pending')
            self.assertIsNone(item['acceptance'])
        paired = next(e for e in ledger()['entries'] if e['feature_id'] == 'H15')
        self.assertEqual(paired['status'], 'conditional')
        self.assertEqual(paired['adapter'], 'not_implemented')

    def test_m_implementation_never_grants_physical_acceptance(self):
        items=[e for e in ledger()['entries'] if e['feature_id'].startswith('M')
               and e['reference']=='confirmed']
        self.assertEqual(len(items),18)
        for item in items:
            self.assertEqual(item['adapter'],'implemented')
            if item['feature_id'] in ('M01','M03','M04','M05','M06','M12'):
                self.assertEqual(item['status'],'accepted')
            else:
                self.assertEqual(item['status'],'pending')
                self.assertIsNone(item['acceptance'])

    def test_remaining_group_implementation_never_grants_physical_acceptance(self):
        implemented = {'P01','P03','P04','R01','R02','R03','R04','E01','E02','E03','E07','E11',
                       'E12','O02','O06'}
        for entry in ledger()['entries']:
            if entry['feature_id'] in implemented:
                self.assertEqual(entry['adapter'],'implemented')
                self.assertNotEqual(entry['status'],'accepted')
                self.assertIsNone(entry['acceptance'])
            if entry['feature_id'] in {'P05','P07','P08','P11'}:
                self.assertEqual(entry['adapter'],'not_implemented')
                self.assertIn('Leveling',entry['note'])

    def test_panel_acceptance_requires_uploaded_explicit_observation_and_restore(self):
        expected = {'S15':(48,2274,2276),'S16':(50,2491,2493),'S17':(53,2762,2764)}
        rows = {e['feature_id']:e for e in ledger()['entries'] if e['feature_id'] in expected}
        for feature,(run,observed,result) in expected.items():
            item = rows[feature]
            self.assertEqual(item['status'],'accepted')
            evidence = item['acceptance']
            self.assertEqual(evidence['controller_result'],'PASSED_USER')
            self.assertTrue(evidence['restore_verified'])
            self.assertEqual(evidence['trace']['session'],'dec3042495ca4ab78b58b947e2b3c73a')
            self.assertEqual((evidence['trace']['run'],evidence['trace']['observe_seq'],
                              evidence['trace']['result_seq']),(run,observed,result))
        # Firmware measurement PASSED alone does not grant physical acceptance.
        for item in ledger()['entries']:
            if item['feature_id'] in ('P03','P04'):
                self.assertEqual(item['status'],'pending')
                self.assertIsNone(item['acceptance'])

    def test_registered_endstop_fix_has_per_axis_operator_acceptance(self):
        rows = {e['target']:e for e in ledger()['entries'] if e['feature_id']=='M01'}
        for target,run,observed,result in (
                ('physical X endstop',1,249,251),('physical Y endstop',2,392,394)):
            item=rows[target]
            self.assertEqual(item['status'],'accepted')
            evidence=item['acceptance']
            self.assertEqual(evidence['controller_result'],'PASSED_USER')
            self.assertTrue(evidence['restore_verified'])
            self.assertEqual(evidence['measurements']['transitions'],'open > TRIGGERED > open')
            trace=evidence['trace']
            self.assertEqual(trace['session'],'2de3566ce59d476cb020ad83dd5360bf')
            self.assertEqual((trace['run'],trace['observe_seq'],trace['result_seq']),
                             (run,observed,result))

    def test_m03_acceptance_requires_explicit_observation_and_final_xyz_readback(self):
        item = next(e for e in ledger()['entries'] if e['feature_id'] == 'M03')
        self.assertEqual(item['target'], 'Cartesian X/Y/Z homing')
        self.assertEqual(item['status'], 'accepted')
        evidence = item['acceptance']
        self.assertEqual(evidence['controller_result'], 'PASSED_USER')
        self.assertTrue(evidence['restore_verified'])
        self.assertEqual(evidence['trace']['session'], 'a4ad65170ed04b649b0a1a58c9c55b53')
        self.assertEqual(evidence['trace']['head'], '4deca8ee79a4b3f4c8cd154869e796f46bb42981')
        self.assertEqual((evidence['trace']['run'], evidence['trace']['observe_seq'],
                          evidence['trace']['result_seq']), (1, 220, 222))
        self.assertEqual(evidence['measurements']['homed_axes'], 'xyz')
        self.assertEqual(evidence['measurements']['position_xyz'], [157.9, 141.5, 10])

    def test_motion_batch_keeps_per_target_operator_evidence_and_limited_outcomes(self):
        expected=[["M04","stepper_x",3,553,555,True],["M04","stepper_y",4,675,677,True],["M04","stepper_z",5,794,796,True],["M05","axis X",7,966,968,True],["M05","axis Y",9,1115,1117,True],["M05","axis Z",12,1308,1310,True],["M06","axis X",13,1498,1500,True],["M06","axis Y",14,1701,1703,True],["M06","axis Z",15,1935,1937,True],["M12","endstop_phase X",16,2019,2021,False],["M10","tmc2208 stepper_x",23,2355,2357,False],["M10","tmc2208 stepper_y",24,2394,2396,False],["M10","tmc2208 stepper_z",25,2452,2454,False]]
        data=ledger()
        rows={(e['feature_id'],e['target']):e for e in data['entries']}
        archived={(e['feature_id'],e['target']):e
                  for e in data['evidence']['retired_m10_entries']['entries']}
        for feature,target,run,observed,result,restored in expected:
            item=archived[(feature,target)] if feature=='M10' else rows[(feature,target)]
            if feature in ('M10','M12'):
                if feature=='M10':
                    self.assertEqual(item['status'],'pending')
                    self.assertIsNone(item['acceptance'])
                else:
                    self.assertEqual(item['status'],'accepted')
                evidence=item['previous_acceptances'][-1]
                self.assertTrue(evidence['invalidated'])
                self.assertIn('without understanding',evidence['invalidation_reason'])
            else:
                self.assertEqual(item['status'],'accepted')
                evidence=item['acceptance']
            self.assertEqual(evidence['restore_verified'],restored)
            self.assertEqual(evidence['controller_result'],
                             'PASSED_USER' if restored else 'OBSERVED_USER')
            trace=evidence['trace']
            self.assertEqual(trace['session'],'3e8f0231f5a84e8eaeae6944aba6951d')
            self.assertEqual((trace['run'],trace['observe_seq'],trace['result_seq']),
                             (run,observed,result))
            if feature=='M06':
                self.assertEqual(evidence['measurements']['operator_entered_mm'],10)
                self.assertIn('not_independent_metrology',
                              evidence['measurements']['measurement_source'])
            if feature=='M10':
                self.assertFalse(evidence['measurements']['motor_health_verified'])
            if feature=='M12':
                self.assertFalse(evidence['measurements']['saved'])
                self.assertFalse(evidence['measurements']['trigger_phase_recorded'])
        for key in (('M10','tmc2208 extruder'),):
            self.assertEqual(archived[key]['status'],'pending')
            self.assertIsNone(archived[key]['acceptance'])
        failed=rows[('M04','stepper_x')]['previous_attempts'][-1]
        self.assertEqual(failed['controller_result'],'FAILED_USER')
        self.assertEqual(failed['trace']['observe_seq'],326)
        self.assertTrue(failed['operator_correction']['accidental_selection'])
        self.assertTrue(failed['operator_correction']['exclude_from_physical_failure'])

    def test_retired_m10_entries_are_archived_not_accepted(self):
        data=ledger()
        self.assertFalse(any(e['feature_id']=='M10' for e in data['entries']))
        retired=data['evidence']['retired_m10_entries']['entries']
        self.assertEqual(len(retired),4)
        self.assertEqual({e['target'] for e in retired},
            {'tmc2208 stepper_x','tmc2208 stepper_y',
             'tmc2208 stepper_z','tmc2208 extruder'})
        self.assertTrue(all(e['status']=='pending' and e['acceptance'] is None
                            for e in retired))
        self.assertTrue(all(e['previous_acceptances'][-1]['invalidated']
                            for e in retired[:3]))

    def test_m12_operator_acceptance_keeps_unsaved_phase_and_history(self):
        rows={(e['feature_id'],e['target']):e for e in ledger()['entries']}
        expected=[
            ('endstop_phase X','2a74f7fe73914463b7798c7551b51c92',
             'c9d3b3326c95734c2e03366608ee9631785714ff',1,1086,1088,'49/64'),
            ('endstop_phase Y','2fd812d7ffdb4c6e8b59275ef181b1b2',
             'e85474ff788d9a17007bbe6e24c2e3f8e0445a98',2,769,771,'33/64')]
        for target,session,head,run,observe_seq,result_seq,phase in expected:
            entry=rows['M12',target]
            self.assertEqual(entry['status'],'accepted')
            self.assertFalse(entry['retest_required'])
            acceptance=entry['acceptance']
            self.assertEqual(acceptance['controller_result'],'OBSERVED_USER')
            self.assertFalse(acceptance['restore_verified'])
            self.assertEqual(acceptance['trace'],dict(session=session,head=head,
                run=run,observe_seq=observe_seq,result_seq=result_seq))
            evidence=acceptance['measurements']
            self.assertEqual(evidence['homing_cycles'],10)
            self.assertEqual(evidence['trigger_phase'],phase)
            self.assertTrue(evidence['pending_config'])
            self.assertFalse(evidence['saved'])
            self.assertFalse(evidence['independent_metrology'])
        self.assertTrue(rows['M12','endstop_phase X']['previous_acceptances'][-1]['invalidated'])
        self.assertFalse(any(feature=='M10' for feature,target in rows))

    def test_m12_y_homed_diagnostic_is_separate_from_existing_calibration_acceptance(self):
        data=ledger()
        rows={(e['feature_id'],e['target']):e for e in data['entries']}
        y=rows['M12','endstop_phase Y']
        self.assertEqual(y['status'],'accepted')
        self.assertEqual(y['acceptance']['measurements']['homing_cycles'],10)
        self.assertEqual(y['acceptance']['measurements']['trigger_phase'],'33/64')
        self.assertFalse(y['acceptance']['measurements']['saved'])
        diagnostic=y['diagnostic_observations']
        self.assertEqual(len(diagnostic),1)
        self.assertEqual(diagnostic[0]['feature_id'],'M12')
        self.assertEqual(diagnostic[0]['target'],'stepper_y')
        self.assertEqual(diagnostic[0]['source'],'user_supplied_lcd_screenshot')
        self.assertEqual(diagnostic[0]['status'],'observed_information')
        self.assertIs(diagnostic[0]['verified'],True)
        self.assertEqual(diagnostic[0]['output']['stepper_y.phase'],'58/64')
        self.assertIn('last_home',diagnostic[0]['scope'])
        self.assertNotIn('diagnostic_observations',rows['M12','endstop_phase X'])
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),23)
        for document in (EN,TR):
            body=document.read_text(encoding='utf-8')
            self.assertIn('M12/Y Diagnostics',body)
            self.assertIn('58/64',body)
            self.assertIn('33/64',body)

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
        from maintenance_pulse import _FAN_STEP_MS
        f02 = by_target[('F02', 'fan')]
        self.assertEqual(f02['status'], 'accepted')
        self.assertFalse(f02['retest_required'])
        self.assertEqual(_FAN_STEP_MS, 2000)
        self.assertEqual(f02['acceptance']['tested_step_duration_ms'], _FAN_STEP_MS)
        self.assertEqual(f02['acceptance']['tested_program_duration_ms'], 6000)
        self.assertEqual(f02['acceptance']['controller_result'], 'OBSERVED_USER')
        self.assertFalse(f02['acceptance']['restore_verified'])
        self.assertFalse(f02['acceptance']['controller_result_reported'])
        self.assertEqual(f02['previous_acceptances'][0]['tested_step_duration_ms'], 800)
        self.assertTrue(f02['previous_acceptances'][0]['restore_verified'])
        self.assertEqual(f02['previous_attempts'][0]['controller_result'], 'INCONCLUSIVE')
        self.assertIsNone(f02['previous_attempts'][0]['restore_verified'])
        o04 = by_target[('O04', 'neopixel mmu_leds')]
        self.assertEqual(o04['status'], 'accepted')
        self.assertFalse(o04['retest_required'])
        self.assertFalse(o04['acceptance']['restore_verified'])
        self.assertFalse(o04['acceptance']['controller_result_reported'])
        for color in ('red', 'green', 'blue', 'white'):
            self.assertIn(color, o04['acceptance']['observation'])
        self.assertEqual(o04['previous_attempts'][0]['controller_result'], 'BLOCKED')
        self.assertEqual(o04['previous_attempts'][1]['controller_result'], 'not_reported')
        self.assertIn('blue stage was not visible',
                      o04['previous_attempts'][1]['observation'])



if __name__ == '__main__':
    unittest.main()
