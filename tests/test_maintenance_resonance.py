"""CI-only resonance sensor routing, PSD evidence and safety regressions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, _add
from maintenance_resonance import MaintenanceResonanceController, METHODS, read_spectrum, comparison
import test_maintenance_probe as probe_fixture


class ResonanceSpectrumTests(unittest.TestCase):
    def test_real_psd_peak_and_grid_comparison(self):
        token = 'petrelr_'+'a'*32
        target = Path('/tmp/resonances_x_'+token+'.csv')
        self.addCleanup(lambda:target.unlink(missing_ok=True))
        target.write_text('freq,psd_x,psd_y,psd_z,psd_xyz\n5,1,0,0,1\n6,4,0,0,4\n7,2,0,0,2\n8,1,0,0,1\n')
        result = read_spectrum(str(target),token)
        self.assertEqual(result['peak_hz'],6)
        self.assertEqual(dict(comparison(result,result))['spectral_similarity'],1)
        target.write_text('freq,psd_xyz\n5,nan\n6,1\n7,2\n8,1\n')
        with self.assertRaises(ValueError):
            read_spectrum(str(target),token)

    def test_unrelated_paths_and_incompatible_grids_are_rejected(self):
        with self.assertRaises(ValueError):
            read_spectrum('/etc/passwd','petrelr_'+'a'*32)
        with self.assertRaises(ValueError):
            comparison({'peak_hz':6,'bins':[(5,1),(6,2)]},
                       {'peak_hz':7,'bins':[(6,1),(7,2)]})

    def test_no_data_or_zero_psd_is_not_measurement(self):
        token = 'petrelr_'+'b'*32
        target = Path('/tmp/resonances_x_'+token+'.csv')
        self.addCleanup(lambda:target.unlink(missing_ok=True))
        target.write_text('freq,psd_xyz\n5,0\n6,0\n7,0\n8,0\n')
        with self.assertRaises(ValueError):
            read_spectrum(str(target),token)


class ResonanceWorkflowTests(unittest.TestCase):
    arm = probe_fixture.ProbeWorkflowTests.arm
    dispatch = probe_fixture.ProbeWorkflowTests.dispatch
    complete = probe_fixture.ProbeWorkflowTests.complete
    get = probe_fixture.ProbeWorkflowTests.get
    request = probe_fixture.ProbeWorkflowTests.request
    responses = probe_fixture.ProbeWorkflowTests.responses

    def setUp(self):
        probe_fixture.ProbeWorkflowTests.setUp(self)
        modes = 0
        for feature in ('R01','R02','R03','R04'):
            modes = _add(modes,feature,METHODS[feature])
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,
            (DeviceCapabilities('adxl345','accelerometer',modes,1),),
            config_marker=id(self.p.state.settings))
        self.owner = MaintenanceResonanceController(self.p,self.worker,self.client)
        self.profile_patch = patch('maintenance_resonance.read_profile',return_value={})
        self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)

    prepare_unhomed_motion = probe_fixture.ProbeWorkflowTests.prepare_unhomed_motion
    finish_preparation_home = probe_fixture.ProbeWorkflowTests.finish_preparation_home

    def arm_sensor(self,feature):
        self.assertTrue(self.owner.start(feature,'adxl345')[0])
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.owner.phase,'await_confirmation')

    def analyze(self,lines):
        self.complete(lines)
        self.assertEqual(self.owner.phase,'analysis')
        self.worker.drain()
        return self.owner.poll()

    def test_unhomed_resonance_homes_before_measurement(self):
        self.raw['settings']['resonance_tester']={'probe_points':[[50.,50.,20.]]}
        self.prepare_unhomed_motion()
        self.client.url='http://127.0.0.1:7125'
        self.owner.start('R02','adxl345')
        self.worker.drain()
        self.owner.poll()
        self.worker.drain()
        self.owner.poll()
        self.assertTrue(self.owner.preparing_home)
        self.assertEqual(self.commands,[])
        self.owner.confirm()
        self.assertEqual(self.commands[0][1]['script'],'G28\nM400')
        self.finish_preparation_home()
        self.assertEqual(self.owner.phase,'running')
        self.assertTrue(self.commands[1][1]['script'].startswith('TEST_RESONANCES '))
        self.assertEqual(len(self.commands),2)

    def _running_r02(self):
        from dataclasses import replace
        from printer_state import PrinterState
        self.raw['settings']['resonance_tester']={'probe_points':[[50.,50.,20.]]}
        self.p.state=PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot=replace(self.p.maintenance.snapshot,
                                            config_marker=id(self.p.state.settings))
        self.client.url='http://127.0.0.1:7125'
        self.arm_sensor('R02')
        self.dispatch()
        self.assertIn('TEST_RESONANCES',self.commands[0][1]['script'])
        self.assertEqual(len(self.commands),1)

    def _replace_pending_safety_read(self, work):
        """Replace the task already submitted to the bounded fake worker."""
        current = self.owner._safety_future
        self.assertIsNotNone(current)
        self.assertIs(self.worker.jobs[-1][1], current)
        self.worker.jobs[-1] = (work, current)

    def test_r02_queue_refresh_delay_does_not_trigger_false_emergency_stop(self):
        self._running_r02()
        # Reproduce the real 3.07-second gap during the long command.
        self.clock += 3.07
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertIsNotNone(self.owner._safety_future)
        self.assertFalse(self.owner._safety_future.done())
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])
        # A fresh read still has to satisfy the strict safety contract.
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])

    def test_r02_refresh_completion_race_waits_for_unconsumed_safe_read(self):
        self._running_r02()
        self.clock += 3.07
        # The worker completed just AFTER poll() checked done=False.
        # A second done() check in the guard used to cause false shutdown.
        fresh = self.owner.runtime_evidence()
        future = SimpleNamespace(done=Mock(side_effect=(False,True)),
                                 result=lambda: fresh)
        self.owner._safety_future = future
        self.owner._next_safety = self.clock + 5.
        self.assertIsNone(self.owner.poll())
        future.done.assert_called_once()
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.owner._safety_reason,'allowed')
        self.assertGreater(self.owner._queue_age_s,3.)
        self.assertEqual(self.owner._refresh_reason,'queue_refresh_unconsumed')
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])
        # The already-completed refresh MUST be processed next tick.
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.owner._safety_reason,'allowed')
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])

    def test_r02_safety_trace_explains_a_real_print_guard_failure(self):
        from maintenance_test_trace import owner_snapshot
        self._running_r02()
        self.clock += 3.07
        self.raw['status']['print_stats']['state']='printing'
        self.assertIsNone(self.owner.poll())
        snapshot = owner_snapshot(self.owner)
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual(snapshot['safety_reason'],'print_not_idle')
        self.assertGreater(snapshot['queue_age_s'],3.)
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_r02_transient_moonraker_queue_read_failure_retries_without_shutdown(self):
        self._running_r02()
        self.clock += 3.07
        self.assertIsNone(self.owner.poll())
        self._replace_pending_safety_read(lambda:None)
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.owner._refresh_reason,'queue_read_retry')
        self.assertEqual(self.owner._queue_read_failures,1)
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])
        self.clock += 1.1
        self.assertIsNone(self.owner.poll())
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.owner._queue_read_failures,0)
        self.assertEqual(self.owner._safety_reason,'allowed')
        self.assertEqual([x[0] for x in self.commands],['printer.gcode.script'])

    def test_r02_transient_worker_exception_retries_only_with_live_safe_state(self):
        self._running_r02()
        self.clock += 3.07
        self.assertIsNone(self.owner.poll())
        def failed_read():
            raise RuntimeError('offline')
        self._replace_pending_safety_read(failed_read)
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.owner._refresh_reason,'queue_read_retry')
        self.raw['status']['print_stats']['state']='printing'
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual(self.owner._safety_reason,'print_not_idle')
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_r02_stale_queue_grace_is_bounded_during_pending_refresh(self):
        self._running_r02()
        self.clock += self.owner._RUNTIME_QUEUE_RETRY_MAX_AGE + .1
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual(self.owner._refresh_reason,'queue_refresh_grace_expired')
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_r02_actual_unsafe_queue_read_stops_without_retry(self):
        from maintenance_runtime import QueueEvidence
        self._running_r02()
        self.clock += 3.07
        self.assertIsNone(self.owner.poll())
        self._replace_pending_safety_read(lambda:QueueEvidence(
                self.owner._row.epoch,self.owner._row.config_marker,
                self.clock,True,'ready',False))
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual(self.owner._safety_reason,'queue_pending_or_busy')
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_r02_confirmed_print_start_still_requests_emergency_stop(self):
        self._running_r02()
        self.clock += 3.07
        self.raw['status']['print_stats']['state']='printing'
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual([x[0] for x in self.commands],
                         ['printer.gcode.script','printer.emergency_stop'])
        self.assertEqual(self.owner._stop_reason,'workflow_runtime_safety_unknown')

    def test_r02_stale_queue_without_inflight_refresh_cannot_be_bypassed(self):
        self._running_r02()
        self.clock += 3.07
        self.owner._next_safety = self.clock+5
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'stopping')
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_r02_shows_klipper_psd_without_petrel_peak_as_advice(self):
        token = 'petrelr_'+'c'*32
        target = Path('/tmp/resonances_x_'+token+'.csv')
        self.addCleanup(lambda:target.unlink(missing_ok=True))
        target.write_text('freq,psd_xyz\n5,1\n6,4\n7,2\n8,1\n')
        self._running_r02()
        self.owner._token=token
        self.assertIsNone(self.analyze(('Resonances data written to '+str(target)+' file',)))
        self.assertEqual(self.owner.phase,'workflow')
        self.assertNotIn('peak_hz',dict(self.owner._evidence))
        self.assertEqual(dict(self.owner._spectra[-1])['peak_hz'],6)
        self.assertIn('R04',dict(self.owner._evidence)['next'])
        self.assertTrue(self.owner.choose(0)[0])
        result=self.owner.observe(True)
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(result.feature_id,'R02')
        self.assertNotIn('peak_hz',dict(result.evidence))

    def _r04_pending(self, *, shaper='mzv', frequency=34.6):
        self.status['configfile']['save_config_pending_items']={
            'input_shaper':{'shaper_type_x':shaper,'shaper_freq_x':frequency}}
        self.raw['status']['configfile']=self.status['configfile']

    def test_r04_uses_only_klipper_native_shaper_recommendation(self):
        self.raw['settings']['resonance_tester']={'probe_points':[[50.,50.,20.]]}
        from dataclasses import replace
        from printer_state import PrinterState
        self.p.state=PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot=replace(self.p.maintenance.snapshot,
                                            config_marker=id(self.p.state.settings))
        self.client.url='http://127.0.0.1:7125'
        self.arm_sensor('R04')
        self.dispatch()
        self.assertIn('SHAPER_CALIBRATE AXIS=X',self.commands[0][1]['script'])
        self.assertNotIn('SAVE_CONFIG',self.commands[0][1]['script'])
        self._r04_pending()
        out=self.analyze(('Recommended shaper_type_x = mzv, shaper_freq_x = 34.6 Hz',))
        self.assertEqual(out.feature_id,'R04')
        self.assertEqual(out.status,'OBSERVED')
        self.assertEqual(out.reason,'klipper_shaper_recommendation_not_saved')
        self.assertEqual(dict(out.evidence),{
            'axis':'x','shaper':'mzv','frequency_hz':34.6,'saved':False})
        self.assertEqual(len(self.commands),1)

    def test_r04_never_invents_missing_or_mismatched_klipper_recommendations(self):
        self.raw['settings']['resonance_tester']={'probe_points':[[50.,50.,20.]]}
        from dataclasses import replace
        from printer_state import PrinterState
        self.p.state=PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot=replace(self.p.maintenance.snapshot,
                                            config_marker=id(self.p.state.settings))
        self.client.url='http://127.0.0.1:7125'
        self.arm_sensor('R04')
        self.dispatch()
        self._r04_pending(shaper='ei',frequency=51.)
        result=self.analyze(('Recommended shaper_type_x = mzv, shaper_freq_x = 34.6 Hz',))
        self.assertEqual(result.status,'INCONCLUSIVE')
        self.assertEqual(result.reason,'resonance_numeric_evidence_unavailable')

    def test_real_accelerometer_vector_required(self):
        self.arm_sensor('R01')
        self.dispatch()
        self.assertIn('CHIP=adxl345',self.commands[0][1]['script'])
        result = self.analyze(('accelerometer values (x, y, z): 0.000000, 0.000000, 9806.000000',))
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(dict(result.evidence)['z_mm_s2'],9806)

    def test_rpc_ok_without_sensor_sample_is_inconclusive(self):
        self.arm_sensor('R01')
        self.dispatch()
        self.assertEqual(self.analyze(('ok',)).status,'INCONCLUSIVE')

    def test_only_assigned_sensor_noise_is_accepted(self):
        self.arm_sensor('R03')
        self.dispatch()
        result = self.analyze(('Axes noise for y-axis accelerometer: 1.0 (x), 2.0 (y), 3.0 (z)',))
        self.assertEqual(result.status,'INCONCLUSIVE')

    def test_actual_noise_values_are_retained(self):
        self.arm_sensor('R03')
        self.dispatch()
        result = self.analyze(('Axes noise for x-axis accelerometer: 1.0 (x), 2.0 (y), 3.0 (z)',))
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(dict(result.evidence)['x.z_psd'],3)

    def test_global_or_unassigned_chip_cannot_be_dispatched(self):
        self.assertFalse(self.owner.start('R02')[0])
        self.assertFalse(self.owner.start('R01','adxl345 other')[0])
        self.assertEqual(self.commands,[])

    def test_multi_axis_chip_requires_explicit_axis_selection(self):
        snap = self.p.maintenance.snapshot
        d = snap.devices[0]
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,
            (DeviceCapabilities(d.name,d.family,d.modes,3),),
            config_marker=id(self.p.state.settings))
        self.assertTrue(self.owner.start('R02','adxl345')[0])
        self.assertEqual(self.owner.phase,'workflow')
        self.assertEqual([x[0] for x in self.owner.workflow_choices],['Measure X','Measure Y'])
        self.assertEqual(self.commands,[])
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'workflow')

    def test_global_trend_resolves_each_discovered_sensor_and_axis(self):
        snap = self.p.maintenance.snapshot
        devices = (snap.devices[0],
                   DeviceCapabilities('adxl345 y','accelerometer',snap.devices[0].modes,2))
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,devices,
            global_modes=_add(0,'R05',METHODS['R05']),config_marker=id(self.p.state.settings))
        rows = [r for r in self.owner.available() if r.feature_id=='R05']
        self.assertEqual([(r.device,r.axes) for r in rows],[('adxl345',1),('adxl345 y',2)])
        self.assertFalse(self.owner.start('R05')[0])

    def test_axis_is_bound_before_a_worker_can_execute(self):
        from concurrent.futures import Future
        seen = []
        def immediate(work,**kwargs):
            future = Future()
            future.set_result(work())
            return future
        with patch.object(self.owner,'_prepare',side_effect=lambda action:seen.append(self.owner._axis)), \
                patch.object(self.worker,'submit',side_effect=immediate):
            self.assertTrue(self.owner.start('R02','adxl345')[0])
        self.assertEqual(seen,['x'])

    def test_missing_compatible_baseline_blocks_before_resonance_motion(self):
        self.owner._row = SimpleNamespace(feature_id='R05',device='adxl345')
        self.owner._profile = {'mount_id':'fixed','belt_test':False}
        self.client.url = 'http://127.0.0.1:7125'
        with patch('maintenance_workflow.FirmwareWorkflow.validate'), \
                patch.object(self.owner,'_key',return_value='a'*64), \
                patch('maintenance_resonance.read_baselines',return_value={}):
            with self.assertRaisesRegex(ValueError,'compatible_resonance_baseline_missing'):
                self.owner.validate(self.status,'start')
        self.assertEqual(self.commands,[])

    def test_unsupported_z_is_never_offered(self):
        self.assertTrue(all(not r.axes & 4 for r in self.owner.available()
                            if r.feature_id in ('R02','R03','R04')))

if __name__ == '__main__':
    unittest.main()
