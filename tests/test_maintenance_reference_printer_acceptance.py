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
ACCEPTED_RESULTS = {'PASSED_USER', 'OBSERVED_USER', 'FAILED_METRIC', 'PASSED', 'OBSERVED'}


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
        self.assertIs(p['manual_subsystem_disable_required_for_test'],False)
        self.assertIs(p['automatic_subsystem_transition_requires_verified_restore'],True)
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
                    if evidence.get('controller_result') == 'OBSERVED':
                        # R04 reports Klipper-native, unsaved recommendations;
                        # do not mislabel this as a controller PASSED metric.
                        self.assertEqual(key, ('R04', 'input_shaper X/Y'))
                        self.assertFalse(evidence.get('saved'))
                        self.assertFalse(evidence.get('restore_verified'))
                    if evidence.get('controller_result') == 'FAILED_METRIC':
                        # Operator accepts correct test execution, never rewrites
                        # the actual thermal performance outcome to PASS.
                        self.assertIn(entry['feature_id'], ('H07','H08'))
                        self.assertEqual(entry['target'], 'extruder')
                        self.assertTrue(evidence.get('procedure_accepted'))
                        self.assertFalse(evidence.get('performance_criterion_passed'))
                        self.assertTrue(evidence.get('restore_verified'))
                    self.assertIs(type(evidence.get('restore_verified')), bool)
                    self.assertIsInstance(evidence.get('observation'), str)
                    self.assertGreater(len(evidence['observation'].strip()), 20)
                    if entry['adapter'] != 'implemented':
                        self.assertIn(key, {
                            ('P05','probe Z-offset'), ('P07','bed_mesh (probe)'),
                            ('P08','bed_mesh (manual)'), ('P11','screws_tilt_adjust')})
                        self.assertEqual(evidence.get('acceptance_surface'),'leveling')
                        self.assertTrue(evidence.get('maintenance_adapter_excluded'))
                        self.assertFalse(evidence.get('restore_verified'))
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

    def test_bilingual_acceptance_tables_have_unbroken_markdown_blocks(self):
        # A blank line between a table header/separator and its rows makes
        # GitHub render the remaining rows as literal Markdown.
        for path in (EN, TR):
            with self.subTest(path=path):
                lines = path.read_text(encoding='utf-8').splitlines()
                for i,line in enumerate(lines):
                    if not line.startswith('|'):
                        continue
                    self.assertTrue(line.endswith('|'),(path,i+1,line))
                    if i+2 < len(lines) and lines[i+1] == '':
                        self.assertFalse(lines[i+2].startswith('|'),
                                         (path,'split table',i+2))
                    if i and lines[i-1].startswith('|'):
                        self.assertEqual(line.count('|'),lines[i-1].count('|'),
                                         (path,'mismatched column count',i+1))

    def test_p01_p03_p04_operator_acceptances_preserve_original_probe_trace(self):
        data=ledger()
        rows={(e['feature_id'],e['target']):e for e in data['entries']}
        trace=data['evidence']['physical_trace_2026_10_17_probe']
        self.assertEqual(trace['session'],'2d899dbe5dcc42e6a5e6a020df941369')
        self.assertEqual(trace['last_seq'],693)
        self.assertEqual(trace['dropped_events'],0)
        self.assertEqual(trace['write_errors'],0)
        for feature in ('P01','P03','P04'):
            row=rows[feature,'probe']
            self.assertEqual(row['status'],'accepted')
            self.assertEqual(row['adapter'],'implemented')
            self.assertEqual(row['acceptance']['source'],
                             'user_explicit_physical_observation')
            self.assertEqual(row['acceptance']['controller_result'],'PASSED')
            self.assertEqual(row['acceptance']['date'],'2026-10-17')
            self.assertEqual(row['acceptance']['restore_verified'],
                             feature=='P01')
        self.assertEqual(rows['P03','probe']['acceptance']
                         ['measurement']['range_mm'],.0175)
        p04=rows['P04','probe']['acceptance']['measurement']
        self.assertEqual(p04['earlier_blocked_z_mm'],2.964)
        self.assertEqual(p04['starting_z_mm'],52.964)
        self.assertTrue(p04['automatic_lift_physically_retested'])
        self.assertEqual(trace['p04_first_attempt']['controller_result'],'BLOCKED')
        self.assertEqual(len(data['entries']),62)
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)

    def test_existing_leveling_acceptances_do_not_create_maintenance_adapters(self):
        data=ledger()
        entries={(e['feature_id'],e['target']):e for e in data['entries']}
        keys=[('P05','probe Z-offset'),('P07','bed_mesh (probe)'),
              ('P08','bed_mesh (manual)'),('P11','screws_tilt_adjust')]
        for key in keys:
            row=entries[key]
            self.assertEqual(row['status'],'accepted')
            self.assertEqual(row['adapter'],'not_implemented')
            proof=row['acceptance']
            self.assertEqual(proof['date'],'2026-10-18')
            self.assertEqual(proof['source'],'user_explicit_physical_observation')
            self.assertEqual(proof['controller_result'],'OBSERVED_USER')
            self.assertEqual(proof['acceptance_surface'],'leveling')
            self.assertTrue(proof['maintenance_adapter_excluded'])
            self.assertFalse(proof['restore_verified'])
            self.assertFalse(proof['new_instrumented_trace_available'])
            for doc in (EN,TR):
                self.assertTrue(read_rows(doc)[key])
        p04=entries['P04','probe']['acceptance']
        self.assertTrue(p04['measurement']['automatic_lift_physically_retested'])
        self.assertEqual(p04['automatic_lift_followup']['date'],'2026-10-18')
        self.assertEqual(p04['automatic_lift_followup']['controller_result'],'OBSERVED_USER')
        self.assertFalse(p04['automatic_lift_followup']['new_instrumented_trace_available'])
        self.assertFalse(p04['followup_trace']['new_automatic_low_z_lift_tested'])
        self.assertFalse(data['evidence']['physical_trace_2026_10_17_resonance']
                         ['p04']['automatic_low_z_lift_exercised'])
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)

    def test_r01_r03_acceptance_has_real_numeric_evidence_without_granting_r02_r04(self):
        d=ledger()
        entries={(e['feature_id'],e['target']):e for e in d['entries']}
        t=d['evidence']['physical_trace_2026_10_17_resonance']
        self.assertEqual(t['session'],'070d7f8524944245bec7259f58e3f6a3')
        self.assertEqual(t['tested_signed_head'],
                         '15476fa89b70012d503ae25baf1f0b0a1b13e981')
        self.assertEqual(t['last_seq'],672)
        self.assertEqual((t['dropped_events'],t['write_errors'],t['rotations']),
                         (0,0,1))
        self.assertEqual(t['p04']['controller_result'],'PASSED')
        self.assertEqual(t['p04']['homing_command'],'G28')
        self.assertFalse(t['p04']['automatic_low_z_lift_exercised'])
        p04=entries['P04','probe']['acceptance']
        self.assertTrue(p04['measurement']['automatic_lift_physically_retested'])
        self.assertFalse(p04['followup_trace']['new_automatic_low_z_lift_tested'])
        for feature,seq in (('R01',387),('R03',535)):
            row=entries[feature,'adxl345']
            self.assertEqual(row['status'],'accepted')
            a=row['acceptance']
            self.assertEqual(a['source'],'user_explicit_physical_observation')
            self.assertEqual(a['controller_result'],'PASSED')
            self.assertFalse(a['restore_verified'])
            self.assertEqual(a['tested_signed_head'],t['tested_signed_head'])
            self.assertEqual(a['trace']['result_seq'],seq)
            for axis in ('axis_x','axis_y','axis_z'):
                self.assertIsInstance(a['measurement'][axis],float)
        # The 17 Oct cancelled runs remain historically ABORTED; later
        # operator-approved physical runs are tracked independently.
        for feature,target in (('R02','resonance_tester X'),
                               ('R02','resonance_tester Y'),
                               ('R04','input_shaper X/Y')):
            self.assertEqual(entries[feature,target]['status'],'accepted')
            self.assertEqual(entries[feature,target]['acceptance']['date'],'2026-10-18')
        self.assertEqual(t['excluded']['r02']['controller_result'],'ABORTED')
        self.assertEqual(t['excluded']['r04']['controller_result'],'ABORTED')


    def test_resonance_r_group_signed_trace_operator_acceptance(self):
        data=ledger()
        by_target={(e['feature_id'],e['target']):e for e in data['entries']}
        trace=data['evidence']['physical_trace_2026_10_18_resonance_group']
        self.assertEqual(trace['session'],'ff80258017ad4c1495e3fd1c64b17e7e')
        self.assertEqual(trace['tested_signed_head'],'ad0615911960e627dcec70722b84cc5c4a8b88c4')
        self.assertEqual(trace['last_seq'],902)
        self.assertEqual((trace['dropped_events'],trace['write_errors'],
                          trace['rotations']),(0,0,0))
        for axis,target,run,dispatch,observe,result in (
                ('X','resonance_tester X',1,121,177,179),
                ('Y','resonance_tester Y',2,260,305,307)):
            row=by_target['R02',target]
            self.assertEqual(row['status'],'accepted')
            self.assertEqual(row['adapter'],'implemented')
            proof=row['acceptance']
            self.assertEqual(proof['source'],'user_explicit_physical_observation')
            self.assertEqual(proof['date'],'2026-10-18')
            self.assertEqual(proof['controller_result'],'PASSED')
            self.assertFalse(proof['restore_verified'])
            self.assertEqual(proof['tested_signed_head'],trace['tested_signed_head'])
            self.assertEqual((proof['trace']['session'],proof['trace']['run'],
                              proof['trace']['dispatch_seq'],proof['trace']['observe_seq'],
                              proof['trace']['result_seq']),
                             (trace['session'],run,dispatch,observe,result))
            self.assertEqual(proof['measurement']['axis'],axis)
            self.assertTrue(proof['measurement']['klipper_psd_recorded'])
            self.assertFalse(proof['measurement']['shaper_recommendation_computed'])
            self.assertFalse(proof['measurement']['save_config_sent'])
            self.assertFalse('peak_hz' in proof['measurement'])
        r04=by_target['R04','input_shaper X/Y']
        self.assertEqual(r04['status'],'accepted')
        proof=r04['acceptance']
        self.assertEqual(proof['controller_result'],'OBSERVED')
        self.assertFalse(proof['restore_verified'])
        self.assertFalse(proof['saved'])
        self.assertEqual(proof['tested_signed_head'],trace['tested_signed_head'])
        self.assertEqual(proof['trace']['session'],trace['session'])
        self.assertEqual(proof['trace']['successful_runs'],[
            {'axis':'X','run':3,'dispatch_seq':355,'result_seq':439},
            {'axis':'Y','run':5,'homing_dispatch_seq':598,
             'dispatch_seq':769,'result_seq':854}])
        self.assertEqual(proof['trace']['earlier_y_blocked'],
                         {'run':4,'result_seq':519,'reason':'existing_pending_config'})
        self.assertEqual(proof['recommendations']['x'],
                         {'shaper':'3hump_ei','frequency_hz':137.6})
        self.assertEqual(proof['recommendations']['y'],
                         {'shaper':'mzv','frequency_hz':42.2})
        self.assertEqual(trace['r04']['earlier_y_blocked']['controller_result'],
                         'BLOCKED')
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)
        for doc in (EN,TR):
            self.assertTrue(read_rows(doc)['R02','resonance_tester X'])
            self.assertTrue(read_rows(doc)['R02','resonance_tester Y'])
            self.assertTrue(read_rows(doc)['R04','input_shaper X/Y'])
            self.assertIn('ff80258017ad4c1495e3fd1c64b17e7e',
                          doc.read_text(encoding='utf-8'))

    def test_mmu_e11_e12_parked_without_fabricating_acceptance(self):
        from maintenance_filament import METHODS
        data=ledger()
        entries={(e['feature_id'],e['target']):e for e in data['entries']}
        parked=data['evidence']['parked_mmu_workflows_2026_10_18']
        self.assertEqual(parked['feature_ids'],['E11','E12'])
        self.assertIs(parked['hardware_discovery_retained'],True)
        self.assertIs(parked['physical_acceptance'],False)
        for key,status in (
                (('E11','Happy Hare MMU gate sensors (4 gates)'),'pending'),
                (('E12','Happy Hare gear and selector'),'conditional')):
            item=entries[key]
            self.assertEqual(item['adapter'],'not_implemented')
            self.assertEqual(item['status'],status)
            self.assertIsNone(item['acceptance'])
            self.assertNotIn(key[0],METHODS)
            self.assertFalse(read_rows(EN)[key])
            self.assertFalse(read_rows(TR)[key])
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)
        for doc in (EN,TR):
            body=doc.read_text(encoding='utf-8')
            self.assertIn('E11',body)
            self.assertIn('E12',body)

    def test_e_group_partial_operator_acceptances_preserve_blocked_tests(self):
        data=ledger()
        by_target={(entry['feature_id'],entry['target']):entry
                   for entry in data['entries']}
        evidence=data['evidence']['physical_trace_2026_10_18_filament_partial']
        self.assertEqual(evidence['session'],'d924a92a9df94f1b99645da43a7b14be')
        self.assertEqual(evidence['tested_signed_head'],'ad0615911960e627dcec70722b84cc5c4a8b88c4')
        self.assertEqual((evidence['session_first_seq'],evidence['session_last_seq'],
                          evidence['manifest_last_seq']),(903,1877,1877))
        self.assertEqual((evidence['dropped_events'],evidence['write_errors'],
                          evidence['rotations']),(0,0,1))
        accepted=[
            ('E01','extruder filament path',9,1131,1133,5.0),
            ('E02','extruder measured length',10,1249,1251,10.0),
            ('E07','extruder + MMU filament path',12,1360,1362,5.0)]
        for feature,target,run,observe,result,length in accepted:
            key=feature,target
            entry=by_target[key]
            self.assertEqual(entry['status'],'accepted')
            self.assertEqual(entry['adapter'],'implemented')
            proof=entry['acceptance']
            self.assertEqual(proof['date'],'2026-10-18')
            self.assertEqual(proof['source'],'user_explicit_physical_observation')
            self.assertEqual(proof['controller_result'],'PASSED_USER')
            self.assertFalse(proof['restore_verified'])
            self.assertEqual(proof['tested_signed_head'],evidence['tested_signed_head'])
            self.assertEqual((proof['trace']['session'],proof['trace']['run'],
                              proof['trace']['observe_seq'],proof['trace']['result_seq']),
                             (evidence['session'],run,observe,result))
            self.assertEqual(proof['measurement']['commanded_mm'],length)
            self.assertTrue(proof['measurement']['modal_restore_verified'])
            self.assertFalse(proof['measurement']['independent_automatic_measurement'])
            self.assertTrue(read_rows(EN)[key])
            self.assertTrue(read_rows(TR)[key])
        measure=by_target['E02','extruder measured length']['acceptance']
        self.assertEqual(measure['trace']['measurement_entry_seq'],1235)
        self.assertEqual(measure['measurement']['operator_entered_measured_mm'],10)
        self.assertEqual(measure['measurement']['computed_error_mm'],0)
        self.assertEqual(evidence['accepted']['E02']['measurement_entry_seq'],1235)
        # These old BLOCKED E03 runs remain historically correct.
        # A later explicit operator report independently accepts E03.
        e03=by_target['E03','filament_switch_sensor mmu_gate_sensor']
        self.assertEqual(e03['status'],'accepted')
        self.assertEqual(e03['acceptance']['controller_result'],'OBSERVED_USER')
        self.assertFalse(e03['acceptance']['new_instrumented_trace_available'])
        self.assertFalse(e03['acceptance']['restore_verified'])
        self.assertTrue(read_rows(EN)['E03','filament_switch_sensor mmu_gate_sensor'])
        self.assertTrue(read_rows(TR)['E03','filament_switch_sensor mmu_gate_sensor'])
        e11=by_target['E11','Happy Hare MMU gate sensors (4 gates)']
        self.assertEqual(e11['status'],'pending')
        self.assertIsNone(e11['acceptance'])
        self.assertFalse(read_rows(EN)['E11','Happy Hare MMU gate sensors (4 gates)'])
        self.assertFalse(read_rows(TR)['E11','Happy Hare MMU gate sensors (4 gates)'])
        e12=by_target['E12','Happy Hare gear and selector']
        self.assertEqual(e12['status'],'conditional')
        self.assertIsNone(e12['acceptance'])
        blocked=evidence['blocked']
        self.assertEqual([(r['feature_id'],r['run'],r['result_seq']) for r in blocked],
                         [('E01',6,971),('E03',7,1015),('E03',8,1040),
                          ('E03',11,1281),('E11',13,1392),('E12',14,1420)])
        self.assertTrue(all(row['reason']=='motion_requires_cold_idle_heaters'
                            for row in blocked if row['feature_id']!='E01'))
        self.assertEqual(sum(entry['status']=='accepted' for entry in data['entries']),55)
        self.assertEqual(sum(entry['status']=='pending' for entry in data['entries']),1)
        for path in (EN,TR):
            self.assertIn('d924a92a9df94f1b99645da43a7b14be',
                          path.read_text(encoding='utf-8'))

    def test_e03_operator_acceptance_preserves_missing_trace_and_prior_blocks(self):
        data=ledger()
        row=next(e for e in data['entries']
                 if e['feature_id']=='E03'
                 and e['target']=='filament_switch_sensor mmu_gate_sensor')
        self.assertEqual(row['status'],'accepted')
        self.assertEqual(row['adapter'],'implemented')
        proof=row['acceptance']
        self.assertEqual(proof['date'],'2026-10-18')
        self.assertEqual(proof['source'],'user_explicit_physical_observation')
        self.assertEqual(proof['controller_result'],'OBSERVED_USER')
        self.assertFalse(proof['controller_result_reported'])
        self.assertFalse(proof['new_instrumented_trace_available'])
        self.assertFalse(proof['restore_verified'])
        self.assertNotIn('tested_signed_head',proof)
        self.assertNotIn('trace',proof)
        followup=data['evidence']['operator_followup_2026_10_18_e03']
        self.assertEqual(followup['feature_id'],'E03')
        self.assertFalse(followup['new_instrumented_trace_available'])
        self.assertEqual(followup['historic_blocked_result_seqs'],
                         [1015,1040,1281])
        old=data['evidence']['physical_trace_2026_10_18_filament_partial']
        self.assertEqual([r['result_seq'] for r in old['blocked']
                          if r['feature_id']=='E03'],[1015,1040,1281])
        self.assertTrue(read_rows(EN)['E03','filament_switch_sensor mmu_gate_sensor'])
        self.assertTrue(read_rows(TR)['E03','filament_switch_sensor mmu_gate_sensor'])
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)

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
                              if e['status'] == 'accepted']),55)
        self.assertEqual(len([e for e in data['entries']
                              if e['status'] == 'pending']),1)

    def test_thermal_group_procedure_acceptance_preserves_performance_failures(self):
        data = ledger()
        group = {'H01','H05','H06','H07','H08','H09','H13'}
        targets = [e for e in data['entries'] if e['feature_id'] in group]
        self.assertEqual(len(targets), 14)
        self.assertEqual({e['target'] for e in targets}, {'extruder','heater_bed'})
        self.assertTrue(all(e['status'] == 'accepted' and
                            e['adapter'] == 'implemented' for e in targets))
        expected = {
            'extruder': (1,792,794,120,153.57),
            'heater_bed': (2,1660,1662,119,153.56)
        }
        failed = []
        for row in targets:
            with self.subTest(feature=row['feature_id'],device=row['target']):
                evidence = row['acceptance']
                self.assertEqual(evidence['date'], '2026-10-17')
                self.assertTrue(evidence['procedure_accepted'])
                self.assertTrue(evidence['restore_verified'])
                self.assertEqual(evidence['grouped_features'], sorted(group,
                                 key=lambda f: ['H01','H05','H06','H07','H08','H09','H13'].index(f)))
                run, observed, result, samples, span = expected[row['target']]
                self.assertEqual(evidence['trace'],
                    {'session':'58240fb38284486dbb6cbdd3d45f6358',
                     'head':'115e392c348292ab5d6bcf57bcde27874c359536',
                     'run':run,'observe_seq':observed,'result_seq':result})
                self.assertEqual(evidence['measurement']['samples'], samples)
                self.assertEqual(evidence['measurement']['span_s'],span)
                if not evidence['performance_criterion_passed']:
                    failed.append((row['feature_id'],row['target']))
                    self.assertEqual(evidence['controller_result'],'FAILED_METRIC')
                else:
                    self.assertEqual(evidence['controller_result'],'PASSED_USER')
        self.assertEqual(sorted(failed),[('H07','extruder'),('H08','extruder')])
        by_key = {(e['feature_id'],e['target']):e for e in targets}
        self.assertEqual(by_key['H07','extruder']['acceptance']['measurement']['value'],7.72)
        self.assertEqual(by_key['H08','extruder']['acceptance']['measurement']['value'],6.69)
        trace = data['evidence']['physical_trace_2026_10_17_thermal_group']
        self.assertEqual(trace['events'],1830)
        self.assertEqual(trace['accepted_procedures_per_target'],14)
        self.assertEqual(trace['heating_cooling_runs'],2)
        self.assertEqual(trace['dropped_events'],0)
        self.assertEqual(trace['write_errors'],0)
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)
        h03 = next(e for e in data['entries'] if e['feature_id']=='H03'
                   and e['target']=='heater_bed')
        self.assertEqual(h03['status'],'accepted')
        self.assertEqual(h03['acceptance']['controller_result'],'PASSED_USER')
        self.assertTrue(h03['acceptance']['restore_verified'])
        paired = next(e for e in data['entries'] if e['feature_id'] == 'H15')
        self.assertEqual(paired['status'], 'conditional')
        self.assertEqual(paired['adapter'], 'not_implemented')
        for path in (EN,TR):
            body=path.read_text(encoding='utf-8')
            self.assertIn('115e392',body)
            self.assertIn('FAILED_METRIC',body)
            self.assertIn('55',body)

    def test_h02_real_pid_calibration_is_accepted_but_h03_remains_blocked(self):
        data = ledger()
        rows = {(e['feature_id'],e['target']): e for e in data['entries']}
        h02, h03 = rows['H02','extruder'], rows['H03','heater_bed']
        self.assertEqual(h02['status'],'accepted')
        self.assertFalse(h02['retest_required'])
        proof = h02['acceptance']
        self.assertEqual(proof['source'],'user_explicit_physical_observation')
        self.assertEqual(proof['controller_result'],'PASSED_USER')
        self.assertTrue(proof['restore_verified'])
        self.assertEqual(proof['tested_signed_head'],
                         '1b6511db3ab45a3f9b3afc30c2c5364f836c356f')
        self.assertEqual(proof['target_c'],150)
        self.assertEqual(proof['metrics'],{
            'pid_kp':14.738,'pid_ki':0.558,'pid_kd':97.273,
            'heated_to_target_band':True})
        self.assertFalse(proof['save_config_executed'])
        self.assertTrue(proof['klipper_save_config_pending'])
        self.assertEqual(proof['trace'],{
            'session':'31cd66be65bd4a3b88968c920adfe340',
            'head':'1b6511db3ab45a3f9b3afc30c2c5364f836c356f',
            'run':1,'confirm_seq':72,'dispatch_seq':81,
            'completion_seq':1352,'observe_seq':1595,'result_seq':1597})
        # This record tests the earlier H02 session, where an H03 attempt
        # was correctly BLOCKED before dispatch. The later H03 physical
        # acceptance is a separate run and must not rewrite that history.
        self.assertEqual(h03['status'],'accepted')
        self.assertEqual(h03['acceptance']['controller_result'],'PASSED_USER')
        trace = data['evidence']['physical_trace_2026_10_17_h02_pid']
        self.assertEqual(trace['events'],1720)
        self.assertEqual((trace['dropped_events'],trace['write_errors'],
                          trace['rotations']),(0,0,1))
        self.assertTrue(trace['h02']['metric_ok'])
        self.assertEqual(trace['h03']['controller_result'],'BLOCKED')
        self.assertEqual(trace['h03']['reason'],
                         'existing_or_unknown_pending_config')
        self.assertFalse(trace['h03']['actuation_dispatched'])
        self.assertFalse(trace['h03']['physical_acceptance'])
        for doc in (EN,TR):
            body=doc.read_text(encoding='utf-8')
            self.assertIn('31cd66be65bd4a3b88968c920adfe340',body)
            self.assertIn('H03',body)
            self.assertIn('18',body)

    def test_h03_real_bed_pid_acceptance_preserves_h02_and_h07_h08_history(self):
        data = ledger()
        rows = {(e['feature_id'],e['target']): e for e in data['entries']}
        h02, h03 = rows['H02','extruder'], rows['H03','heater_bed']
        self.assertEqual(h02['acceptance']['metrics']['pid_kp'], 14.738)
        self.assertEqual(h03['status'], 'accepted')
        proof = h03['acceptance']
        self.assertEqual(proof['source'],'user_explicit_physical_observation')
        self.assertEqual(proof['controller_result'],'PASSED_USER')
        self.assertTrue(proof['restore_verified'])
        self.assertEqual(proof['tested_signed_head'],
            '1b6511db3ab45a3f9b3afc30c2c5364f836c356f')
        self.assertEqual(proof['target_c'],60)
        self.assertEqual(proof['metrics'],{
            'pid_kp':72.339,'pid_ki':1.502,'pid_kd':870.785,
            'heated_to_target_band':True})
        self.assertTrue(proof['klipper_save_config_pending'])
        self.assertFalse(proof['save_config_executed'])
        self.assertEqual(proof['trace'],{
            'session':'8fa2b04372d94b7ca60e6d443fc098a8',
            'head':'1b6511db3ab45a3f9b3afc30c2c5364f836c356f',
            'run':3,'start_seq':1766,'confirm_seq':1783,'dispatch_seq':1792,
            'completion_seq':4118,'observe_seq':4288,'result_seq':4290})
        trace = data['evidence']['physical_trace_2026_10_17_h03_pid']
        self.assertEqual((trace['session_events'],trace['first_seq'],
                          trace['last_seq']),(2671,1721,4391))
        self.assertEqual((trace['dropped_events'],trace['write_errors'],
                          trace['rotations']),(0,0,1))
        self.assertTrue(trace['h03']['metric_ok'])
        self.assertTrue(trace['h03']['restore_verified'])
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        self.assertEqual(sum(e['status']=='pending' for e in data['entries']),1)
        reference_physical={'H01','H02','H03','H05','H06','H07','H08','H09','H13'}
        physical = [entry for entry in data['entries']
                    if entry['feature_id'] in reference_physical]
        self.assertEqual(len(physical),16)
        self.assertTrue(all(entry['status']=='accepted' for entry in physical))
        for feature in ('H07','H08'):
            evidence=rows[feature,'extruder']['acceptance']
            self.assertEqual(evidence['controller_result'],'FAILED_METRIC')
            self.assertFalse(evidence['performance_criterion_passed'])
        for doc in (EN,TR):
            body=doc.read_text(encoding='utf-8')
            self.assertIn('8fa2b04372d94b7ca60e6d443fc098a8',body)
            self.assertIn('16/16',body)
            self.assertIn('55',body)

    def test_m_implementation_never_grants_physical_acceptance(self):
        items=[e for e in ledger()['entries'] if e['feature_id'].startswith('M')
               and e['reference']=='confirmed']
        self.assertEqual(len(items),14)
        for item in items:
            self.assertEqual(item['adapter'],'implemented')
            if item['feature_id'] in ('M01','M03','M04','M05','M06','M12'):
                self.assertEqual(item['status'],'accepted')
            else:
                self.assertEqual(item['status'],'pending')
                self.assertIsNone(item['acceptance'])

    def test_remaining_unaccepted_group_implementation_never_grants_physical_acceptance(self):
        # P01/P03/P04 and R01/R03 gained explicit real-printer approval in later traces.
        implemented = {'O02','O06'}
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
        # The old S15/S16/S17 session's probe measurements alone did not
        # grant acceptance. The operator explicitly approved them later in
        # their own P-group physical trace; do not rewrite that history.
        for item in ledger()['entries']:
            if item['feature_id'] in ('P03','P04'):
                self.assertEqual(item['status'],'accepted')
                self.assertEqual(item['acceptance']['source'],
                                 'user_explicit_physical_observation')
                self.assertEqual(item['acceptance']['trace']['session'],
                                 '2d899dbe5dcc42e6a5e6a020df941369')

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
        self.assertEqual(sum(e['status']=='accepted' for e in data['entries']),55)
        for document in (EN,TR):
            body=document.read_text(encoding='utf-8')
            self.assertIn('M12/Y Diagnostics',body)
            self.assertIn('58/64',body)
            self.assertIn('33/64',body)

    def test_m07_informational_diagnostics_are_not_physical_acceptance(self):
        data=ledger()
        active=data['entries']
        self.assertEqual(len(active),62)
        self.assertEqual(len({item['feature_id'] for item in active}),46)
        self.assertFalse(any(item['feature_id']=='M07' for item in active))
        archive=data['evidence']['m07_informational_diagnostics']
        self.assertEqual(archive['method'],'INFORMATION')
        self.assertEqual(archive['controller_result'],'observed_information')
        self.assertIs(archive['motor_health_verified'],False)
        previous=archive['retired_physical_acceptance_entries']
        self.assertEqual(len(previous),4)
        self.assertTrue(all(item['feature_id']=='M07'
                            and item['status']=='pending'
                            and item['acceptance'] is None for item in previous))
        readings=archive['readings']
        self.assertEqual({item['target'] for item in readings},
            {'tmc2208 stepper_x','tmc2208 stepper_y',
             'tmc2208 stepper_z','tmc2208 extruder'})
        self.assertTrue(all(item['register']=='DRV_STATUS'
                            and item['fault_count']==0 for item in readings))
        self.assertEqual(sum(item['status']=='accepted' for item in active),55)
        for doc in (EN,TR):
            body=doc.read_text(encoding='utf-8')
            self.assertIn('m07_informational_diagnostics',body)
            self.assertNotIn('| [ ] | M07 |',body)
            self.assertIn('M12',body)

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
