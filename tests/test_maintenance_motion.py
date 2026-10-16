from types import SimpleNamespace
import unittest
from maintenance_motion import compile_motion, return_program, verify_motion
TOKEN='_PETREL_M_'+'a'*32

def state_and_status():
    settings={'printer':{'kinematics':'cartesian','max_z_velocity':5.},
              'stepper_x':{'endstop_pin':'^PA1'},'stepper_y':{'endstop_pin':'^PA2'},
              'stepper_z':{'endstop_pin':'probe:z_virtual_endstop'}}
    status={'toolhead':{'homed_axes':'xyz','axis_minimum':[0.,0.,0.],
                       'axis_maximum':[200.,200.,200.],'max_velocity':100.},
            'gcode_move':{'position':[50.,50.,20.,0.],'homing_origin':[0.,0.,0.,0.],
                'speed':50.,'speed_factor':.8,'extrude_factor':1.1,
                'absolute_coordinates':True,'absolute_extrude':False},
            'stepper_enable':{'steppers':{'stepper_x':True,'stepper_y':True,'stepper_z':True}}}
    return SimpleNamespace(settings=settings),status

class MotionContractTests(unittest.TestCase):
    def setUp(self):
        self.state,self.status=state_and_status()
    def row(self,f='M05',d='stepper_x'):
        return SimpleNamespace(feature_id=f,device=d)
    def test_bounded_roundtrip_restores_modes_without_return_move(self):
        p=compile_motion(self.row(),self.state,self.status,TOKEN)
        self.assertIn('G1 X1.0000 F300.000',p.script)
        self.assertIn('G1 X-1.0000 F300.000',p.script)
        self.assertTrue(p.script.endswith('MOVE=0'))
        self.assertEqual(p.script.count('M400'),3)
        self.assertTrue(verify_motion(p,self.status))
        self.status['gcode_move']['speed_factor']=1.
        self.assertFalse(verify_motion(p,self.status))
    def test_measured_move_requires_external_value_and_explicit_return(self):
        p=compile_motion(self.row('M06'),self.state,self.status,TOKEN)
        self.assertEqual(p.expected,(60.,50.,20.))
        self.assertNotIn('G1 X-10',p.script)
        with self.assertRaises(ValueError):
            return_program(p,self.state,self.status,TOKEN)
        self.status['gcode_move']['position'][0]=60.
        back=return_program(p,self.state,self.status,TOKEN)
        self.assertIn('G1 X-10.0000',back.script)
        self.assertEqual(back.expected,(50.,50.,20.))
    def test_unhomed_limits_active_mesh_and_multi_z_fail_closed(self):
        self.status['toolhead']['homed_axes']='xy'
        with self.assertRaises(ValueError):
            compile_motion(self.row(),self.state,self.status,TOKEN)
        self.status['toolhead']['homed_axes']='xyz'
        self.status['gcode_move']['position'][2]=1.
        with self.assertRaises(ValueError):
            compile_motion(self.row(),self.state,self.status,TOKEN)
        self.status['gcode_move']['position'][2]=20.
        self.state.settings['bed_mesh']={}
        self.status['bed_mesh']={'profile_name':'default','mesh_matrix':[[0.]]}
        with self.assertRaises(ValueError):
            compile_motion(self.row(),self.state,self.status,TOKEN)
        del self.state.settings['bed_mesh']
        self.state.settings['stepper_z1']={}
        with self.assertRaises(ValueError):
            compile_motion(self.row('M04','stepper_z'),self.state,self.status,TOKEN)
    def test_no_force_move_macros_or_automatic_home_before_jog(self):
        self.state.settings['gcode_macro G1']={}
        with self.assertRaisesRegex(ValueError,'overridden'):
            compile_motion(self.row(),self.state,self.status,TOKEN)
        del self.state.settings['gcode_macro G1']
        self.status['toolhead']['homed_axes']=''
        home=compile_motion(self.row('M03',None),self.state,self.status,TOKEN)
        self.assertEqual(home.script,'G28\nM400')
        self.assertNotIn('FORCE_MOVE',home.script)
    def test_phase_calibration_requires_actual_history_and_exact_pending_result(self):
        self.state.settings['endstop_phase stepper_x']={}
        self.status['configfile']={'save_config_pending':False}
        self.status['endstop_phase']={'last_home':{'stepper_x':{'phase':4,'phases':64}}}
        p=compile_motion(self.row('M12'),self.state,self.status,TOKEN)
        self.assertEqual(p.script,'ENDSTOP_PHASE_CALIBRATE STEPPER=stepper_x')
        self.assertFalse(verify_motion(p,self.status))
        self.status['configfile']={'save_config_pending':True,'save_config_pending_items':{
            'endstop_phase stepper_x':{'trigger_phase':'7/64'}}}
        self.assertTrue(verify_motion(p,self.status))
        self.assertNotIn('SAVE_CONFIG',p.script)

    def test_small_mesh_bounds_prove_clear_without_fetching_matrix(self):
        self.state.settings['bed_mesh']={}
        self.status['bed_mesh']={'profile_name':'','mesh_min':[0.,0.],'mesh_max':[0.,0.]}
        p=compile_motion(self.row(),self.state,self.status,TOKEN)
        self.assertEqual(p.feature_id,'M05')
        self.status['bed_mesh']['mesh_max']=[200.,200.]
        with self.assertRaises(ValueError):
            compile_motion(self.row(),self.state,self.status,TOKEN)
