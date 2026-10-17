"""CI-only filament safety, actual measurements and restoration."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import test_maintenance_probe as fixture
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, _add, INFORMATION, USER
from maintenance_filament import MaintenanceFilamentController, METHODS, filament_services
from maintenance_filament_info import read_fields
from maintenance_executor import read_only_adapters


class FilamentWorkflowTests(unittest.TestCase):
    get = fixture.ProbeWorkflowTests.get
    request = fixture.ProbeWorkflowTests.request
    responses = fixture.ProbeWorkflowTests.responses
    dispatch = fixture.ProbeWorkflowTests.dispatch
    complete = fixture.ProbeWorkflowTests.complete

    def setUp(self):
        fixture.ProbeWorkflowTests.setUp(self)
        self.sensor = 'filament_switch_sensor path'
        self.status[self.sensor] = {'enabled':True,'filament_detected':False}
        self.raw['status'].update(copy.deepcopy(self.status))
        self.raw['objects'] = [self.sensor,'toolhead','manual_probe','configfile']
        self.raw['settings'] = {self.sensor:{}}
        self.p.state = PrinterState.from_snapshot(self.raw)
        modes = _add(0,'E03',METHODS['E03'])
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,
            (DeviceCapabilities(self.sensor,'filament',modes),),
            config_marker=id(self.p.state.settings))
        self.owner = MaintenanceFilamentController(self.p,self.worker,self.client)
        p = patch('maintenance_filament.profile',return_value={})
        p.start()
        self.addCleanup(p.stop)

    def arm(self):
        self.assertTrue(self.owner.start('E03',self.sensor)[0])
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.owner.phase,'await_confirmation')

    def step(self,detected):
        self.status[self.sensor]['filament_detected'] = detected
        self.owner.choose(0)
        self.worker.drain()
        self.owner.poll()
        return self.complete()

    def test_sensor_macros_are_disabled_before_operator_fragment_and_restored(self):
        self.arm()
        self.assertEqual(self.commands,[])
        self.dispatch()
        self.assertIn('ENABLE=0',self.commands[-1][1]['script'])
        self.status[self.sensor]['enabled'] = False
        self.complete()
        self.assertEqual(self.owner.phase,'workflow')
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        for detected in (False,True,False):
            self.step(detected)
        self.assertEqual(self.owner.phase,'preflight')
        self.worker.drain()
        self.owner.poll()
        self.assertIn('ENABLE=1',self.commands[-1][1]['script'])
        self.status[self.sensor]['enabled'] = True
        result = self.complete()
        self.assertEqual(result.status,'PASSED')
        self.assertTrue(result.restore_verified)

    def test_sensor_cancel_restores_original_enabled_state(self):
        self.arm()
        self.dispatch()
        self.status[self.sensor]['enabled'] = False
        self.complete()
        self.assertIsNone(self.owner.cancel())
        self.worker.drain()
        self.owner.poll()
        self.status[self.sensor]['enabled'] = True
        result = self.complete()
        self.assertEqual(result.status,'ABORTED')
        self.assertTrue(result.restore_verified)

    def test_rpc_ok_without_disabled_readback_never_passes(self):
        self.arm()
        self.dispatch()
        self.assertIsNone(self.complete())
        self.assertEqual(self.owner.phase,'preflight')
        self.worker.drain()
        self.owner.poll()
        result = self.complete()
        self.assertEqual(result.status,'INCONCLUSIVE')

    def test_extrusion_without_xyz_motion_does_not_require_xyz_homing(self):
        from test_maintenance_motion import state_and_status
        self.owner._row=SimpleNamespace(feature_id='E01',device=None)
        raw,values=state_and_status()
        self.raw['settings']['extruder']={'min_extrude_temp':170.,'max_temp':300.}
        self.p.state=PrinterState.from_snapshot(self.raw)
        values['manual_probe']={'is_active':False}
        values['configfile']={'save_config_pending':False}
        values['toolhead'].update(extruder='extruder',homed_axes='')
        values['extruder']={'temperature':200.,'target':200.,'power':.2,'can_extrude':True}
        self.assertFalse(self.owner.requires_homing)
        self.owner.validate(values,'start')
        self.assertFalse(self.owner.preparing_home)
        self.assertEqual(self.commands,[])

    def test_extrusion_never_starts_with_unknown_active_tool_or_cold_heater(self):
        self.owner._row = SimpleNamespace(feature_id='E01',device=None)
        values = copy.deepcopy(self.status)
        with self.assertRaisesRegex(ValueError,'active_extruder_unknown'):
            self.owner.validate(values,'start')
        values['toolhead']['extruder'] = 'extruder'
        values['extruder'] = {'temperature':20.,'target':0.,'power':0.,'can_extrude':False}
        with self.assertRaisesRegex(ValueError,'preheat_active_extruder_before_test'):
            self.owner.validate(values,'start')

    def test_reference_mass_and_tare_are_required_before_calibration_accept(self):
        self.owner._row = SimpleNamespace(feature_id='E09',device='load_cell sensor')
        for action in ('calibrate','accept'):
            with self.assertRaises(ValueError):
                self.owner.script(action,{})
        self.owner._phase = 'measurement_edit'
        self.assertFalse(self.owner.record_measurement(1)[0])
        self.assertTrue(self.owner.record_measurement(100)[0])

    def test_each_declared_dryer_requires_its_own_limits(self):
        self.owner._row = SimpleNamespace(feature_id='E14',device='heater_generic dryer')
        self.owner._profile = {'dryers':[{'object':'heater_generic dryer','target':60,
                                          'ceiling':70,'duration_s':3600}]}
        with self.assertRaises(ValueError):
            self.owner._dryer()

    def test_sensor_temperature_fields_are_bounded_to_selected_instance(self):
        self.owner._row = SimpleNamespace(feature_id='E03',device=self.sensor)
        fields = self.owner.fields()
        self.assertIn(self.sensor,fields)
        self.assertLess(len(fields),10)

    def test_mmu_workflows_parked_without_manual_disable_or_motion(self):
        from dataclasses import replace
        # The printer may advertise these genuine MMU capabilities. No
        # runnable adapter is registered until an automatic, VERIFIED
        # save-disable-restore protocol is implemented (and E12's checks
        # cover the actual mechanical actions).
        snapshot=self.p.maintenance.snapshot
        modes=_add(_add(0,'E11',USER),'E12',USER)
        self.p.maintenance.snapshot=replace(snapshot,global_modes=modes)
        self.assertNotIn('E11',METHODS)
        self.assertNotIn('E12',METHODS)
        self.assertTrue(self.p.maintenance.snapshot.method('E11'))
        self.assertTrue(self.p.maintenance.snapshot.method('E12'))
        rows=self.owner.available()
        self.assertIn('E03',[row.feature_id for row in rows])
        self.assertNotIn('E11',[row.feature_id for row in rows])
        self.assertNotIn('E12',[row.feature_id for row in rows])
        self.assertEqual(self.owner.start('E11'),
                         (False,'workflow_adapter_unavailable'))
        self.assertEqual(self.owner.start('E12'),
                         (False,'workflow_adapter_unavailable'))
        self.assertEqual(self.worker.jobs,[])
        self.assertEqual(self.commands,[])

    def test_no_mmu_action_cannot_be_reported_as_physical_pass(self):
        self.owner._row = SimpleNamespace(feature_id='E12',device=None)
        self.owner._phase = 'await_observation'
        self.assertEqual(self.owner.observe(True).status,'INCONCLUSIVE')


class FilamentInformationTests(unittest.TestCase):
    def test_usage_and_chamber_are_diagnostics_not_physical_tests(self):
        read = {a.feature_id:a.method for a in read_only_adapters()}
        self.assertEqual(read['E13'],INFORMATION)
        self.assertEqual(read['E15'],INFORMATION)
        self.assertNotIn('E13',METHODS)
        self.assertNotIn('E15',METHODS)
        self.assertNotIn('E10',METHODS)

    def test_humidity_is_real_sensor_evidence_not_filament_moisture(self):
        reply = {'result':{'eventtime':5.,'status':{'temperature_sensor chamber':{'humidity':40.}}}}
        with patch('maintenance_filament_info.profile',return_value={'chamber_sensor':'temperature_sensor chamber'}):
            self.assertEqual(dict(read_fields('E15',reply))['humidity_pct'],40)
            reply['result']['status']['temperature_sensor chamber']['humidity'] = 200
            self.assertEqual(read_fields('E15',reply),())

    def test_usage_requires_linked_valid_records_and_real_spoolman_reply(self):
        data = {'material_history':[{'spool_id':4,'material':'PLA','used_mm':100.,'source':'imported-history'}]}
        with patch('maintenance_filament_info.profile',return_value=data):
            result = dict(read_fields('E13',{'result':{'spool_id':4}}))
            self.assertEqual(result['declared_used_mm'],100)
            self.assertFalse(result['wear_measured'])
            self.assertEqual(read_fields('E13',{'result':{'spool_id':False}}),())

if __name__ == '__main__':
    unittest.main()
