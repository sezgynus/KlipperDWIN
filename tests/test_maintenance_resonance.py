"""CI-only resonance sensor routing, PSD evidence and safety regressions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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
