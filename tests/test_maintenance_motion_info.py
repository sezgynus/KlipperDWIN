import unittest
from types import SimpleNamespace
from maintenance_motion_info import read_fields, path_for, tmc2208_faults
from maintenance_executor import read_only_adapters
from maintenance_discovery import INFORMATION

def reply(values):
    return {'result': {'eventtime': 10., 'status': values}}

class MotionInformationTests(unittest.TestCase):
    def test_disabled_driver_is_unknown_empty_mapping_is_reported_clear(self):
        self.assertEqual(read_fields('M07', reply({'tmc2208 stepper_x': {'drv_status': None}}), 'tmc2208 stepper_x'), ())
        self.assertEqual(tmc2208_faults({'drv_status': None}), None)
        self.assertEqual(tmc2208_faults({'drv_status': {}}), ())
        self.assertEqual(tmc2208_faults({'drv_status': {'stst': 1, 'otpw': 1}}), ('otpw',))
        self.assertIsNone(tmc2208_faults({'drv_status': {'ot': 'false'}}))
        self.assertIsNone(tmc2208_faults({'drv_status': {'unknown_schema': 1}}))
        self.assertEqual(tmc2208_faults({'drv_status': {'cs_actual': 10, 'stealth': 1}}), ())

    def test_m07_driver_fault_summary_replaces_retired_m10(self):
        driver='tmc2208 stepper_x'
        def report(status):
            return read_fields('M07',reply({driver:{'drv_status':status}}),driver)
        clear=report({})
        self.assertIn(('fault_count',0),clear)
        self.assertIn(('faults','none reported'),clear)
        warning=report({'otpw':1,'stst':1,'cs_actual':11})
        self.assertIn(('fault_count',1),warning)
        self.assertIn(('faults','otpw'),warning)
        self.assertIn(('otpw',1),warning)
        self.assertEqual(report(None),())
        self.assertEqual(report({'unknown_schema':1}),())
        other='tmc2209 stepper_x'
        self.assertIn(('otpw',1),
            read_fields('M07',reply({other:{'drv_status':{'otpw':1}}}),other))

    def test_reported_current_and_temperature_are_not_invented(self):
        v = reply({'tmc2208 stepper_x': {'run_current': .8, 'hold_current': .4, 'temperature': None}})
        self.assertEqual(read_fields('M08', v, 'tmc2208 stepper_x'), ())
        self.assertIn(('run_current', .8), read_fields('M09', v, 'tmc2208 stepper_x'))
        v['result']['eventtime'] = True
        self.assertEqual(read_fields('M09', v, 'tmc2208 stepper_x'), ())

    def test_global_status_and_commanded_position_are_bounded(self):
        v = reply({'toolhead': {'homed_axes': 'xyz', 'position': [1.,2.,3.,0.], 'max_velocity': 100.},
                   'stepper_enable': {'steppers': {'stepper_x': True, 'stepper_y': False}}})
        self.assertIn(('commanded_x', 1.), read_fields('M14', v))
        self.assertIn(('stepper_x', True), read_fields('M11', v))
        self.assertFalse(any('actual' in k for k, _ in read_fields('M14', v)))

    def test_exact_object_query_and_no_driver_enable_or_register_write(self):
        state = SimpleNamespace(objects=('toolhead', 'tmc2208 stepper_x', 'angle shaft'))
        self.assertIn('tmc2208%20stepper_x=drv_status', path_for('M07', 'tmc2208 stepper_x', state))
        self.assertIn('toolhead=homed_axes', path_for('M14', None, state))
        with self.assertRaises(ValueError):
            path_for('M07', 'tmc2208 missing', state)
        entries = {r.feature_id:r for r in read_only_adapters()}
        for f in ('M07', 'M08', 'M09', 'M11', 'M12', 'M13', 'M14', 'M16'):
            self.assertEqual(entries[f].method, INFORMATION)

    def test_last_home_is_observation_not_new_calibration(self):
        v=reply({'endstop_phase': {'last_home': {'stepper_x': {'phase': 7, 'phases': 64, 'mcu_position': 123}}}})
        self.assertIn(('stepper_x.phase', '7/64'), read_fields('M12', v))
        self.assertEqual(read_fields('M12', reply({'endstop_phase': {'last_home': {}}})), ())

    def test_unverified_information_source_releases_session(self):
        from types import SimpleNamespace
        from maintenance_executor import MaintenanceReadExecutor,read_only_adapters
        from maintenance_discovery import MaintenanceSnapshot,INFORMATION,_add
        from maintenance_planner import build_plan
        from maintenance_safety import SafetyContext,MaintenanceSafetyCoordinator
        from test_maintenance_controller import printer
        backend,_=printer()
        snap=MaintenanceSnapshot(12,global_modes=_add(0,'M16',INFORMATION),
                                  config_marker=id(backend.state.settings))
        context=SafetyContext(backend.state,queue_checked=True,job_queue=None,
                              operations_checked=True,conflicting_operation=False)
        safety=MaintenanceSafetyCoordinator()
        worker=SimpleNamespace(submit=lambda *a,**k: self.fail('must not queue GET'))
        ex=MaintenanceReadExecutor(worker,None,lambda:context,lambda:snap,safety)
        row=next(r for r in build_plan(snap,read_only_adapters()) if r.feature_id=='M16')
        self.assertEqual(ex.start(row),(False,'information_source_unverified'))
        self.assertFalse(ex.pending)
        self.assertIsNone(safety.active)
