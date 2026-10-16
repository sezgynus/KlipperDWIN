"""CI-only auxiliary safety profiles and explicit physical observations."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_maintenance_probe as fixture
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot,DeviceCapabilities,_add,USER
from maintenance_auxiliary import MaintenanceAuxiliaryController,benign_button,servo_profile,tasks
from maintenance_auxiliary_info import read_fields

SERVO = {'object':'servo test','minimum_angle':30.,'maximum_angle':150.,'angles':[60.,120.]}
TASK = {'id':'inspect_belt','label':'Inspect belt','steps':['Inspect for wear','Confirm fasteners secure']}


class AuxiliaryProfileTests(unittest.TestCase):
    def test_button_profile_cannot_authorize_arbitrary_motion_or_templates(self):
        state = SimpleNamespace(objects=('gcode_button test',),
            settings={'gcode_button test':{'press_gcode':'M117 Test'}})
        self.assertTrue(benign_button(state,'gcode_button test'))
        for script in ('G28','RESPOND TYPE=command MSG=action:shutdown','{ action_call_remote_method("power") }'):
            state.settings['gcode_button test']['press_gcode'] = script
            self.assertFalse(benign_button(state,'gcode_button test'))

    def test_servo_angles_require_declared_range_and_firmware_limits(self):
        state = SimpleNamespace(objects=('servo test',),settings={'servo test':{}})
        self.assertEqual(servo_profile(state,SERVO)[3],(60.,120.))
        bad = dict(SERVO,angles=[0.,180.])
        with self.assertRaises(ValueError):
            servo_profile(state,bad)
        with self.assertRaises(ValueError):
            servo_profile(state,dict(SERVO,object='servo missing'))

    def test_service_tasks_are_finite_and_cannot_hide_control_characters(self):
        self.assertEqual(len(tasks({'tasks':[TASK]})),1)
        self.assertEqual(tasks({'tasks':[dict(TASK,steps=['line\ncommand'])]}),())

    def test_ambient_monitor_returns_actual_value_not_heater_accuracy(self):
        with patch('maintenance_auxiliary_info.profile',return_value={'ambient_sensor':'temperature_sensor room'}):
            reply = {'result':{'eventtime':10.,'status':{'temperature_sensor room':{'temperature':23.5}}}}
            self.assertEqual(dict(read_fields('O05',reply))['ambient_c'],23.5)
            reply['result']['status']['temperature_sensor room']['temperature'] = None
            self.assertEqual(read_fields('O05',reply),())


class AuxiliaryWorkflowTests(unittest.TestCase):
    get = fixture.ProbeWorkflowTests.get
    request = fixture.ProbeWorkflowTests.request
    responses = fixture.ProbeWorkflowTests.responses
    dispatch = fixture.ProbeWorkflowTests.dispatch
    complete = fixture.ProbeWorkflowTests.complete

    def setUp(self):
        fixture.ProbeWorkflowTests.setUp(self)
        self.status.update({'servo test':{'value':.075},'gcode_button test':{'state':'RELEASED'},
                            'stepper_enable':{'steppers':{'stepper_x':False}}})
        self.raw['objects'] = ['servo test','gcode_button test','stepper_enable']
        self.raw['settings'] = {'servo test':{},'gcode_button test':{'press_gcode':'M117 Test'}}
        self.raw['status'].update(copy.deepcopy(self.status))
        self.p.state = PrinterState.from_snapshot(self.raw)
        self.data = {'version':1,'servos':[SERVO],'buttons':['gcode_button test'],'tasks':[TASK]}
        p = patch('maintenance_auxiliary.profile',side_effect=lambda:copy.deepcopy(self.data))
        p.start()
        self.addCleanup(p.stop)
        devices = (DeviceCapabilities('servo test','actuator',_add(0,'O02',USER)),
                   DeviceCapabilities('gcode_button test','button',_add(0,'O01',USER)))
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,devices,
            global_modes=_add(0,'O06',USER),config_marker=id(self.p.state.settings))
        self.owner = MaintenanceAuxiliaryController(self.p,self.worker,self.client)

    def arm(self,feature,device=None):
        self.assertTrue(self.owner.start(feature,device)[0])
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.owner.phase,'await_confirmation')
        self.assertEqual(self.commands,[])

    def local_complete(self):
        self.owner.poll()
        self.worker.drain()
        return self.owner.poll()

    def advance(self):
        self.assertTrue(self.owner.choose(0)[0])
        self.worker.drain()
        self.owner.poll()

    def test_button_released_pressed_released_is_measured_without_gcode(self):
        self.arm('O01','gcode_button test')
        self.dispatch()
        self.local_complete()
        for state in ('PRESSED','RELEASED'):
            self.status['gcode_button test']['state'] = state
            self.advance()
            result = self.local_complete()
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(self.commands,[])

    def test_servo_has_separate_angle_consent_and_pwm_restore_before_observation(self):
        self.arm('O02','servo test')
        self.dispatch()
        self.assertIn('ANGLE=60.000000',self.commands[-1][1]['script'])
        self.status['servo test']['value'] = (.001+60./180.*.001)/.02
        self.complete()
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.assertEqual(len(self.commands),1)
        self.advance()
        self.assertIn('ANGLE=120.000000',self.commands[-1][1]['script'])
        self.status['servo test']['value'] = (.001+120./180.*.001)/.02
        self.complete()
        self.advance()
        self.assertIn('WIDTH=0.001500000',self.commands[-1][1]['script'])
        self.status['servo test']['value'] = .075
        self.complete()
        self.assertEqual(self.owner.phase,'await_observation')
        result = self.owner.observe(True)
        self.assertEqual(result.status,'PASSED_USER')
        self.assertTrue(result.restore_verified)

    def test_servo_zero_pwm_does_not_invent_an_initial_mechanical_position(self):
        self.status['servo test']['value'] = 0.
        self.owner.start('O02','servo test')
        self.worker.drain()
        result = self.owner.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(self.commands,[])

    def test_manual_service_requires_every_step_and_never_reports_sensor_health(self):
        self.arm('O06')
        self.dispatch()
        self.local_complete()
        self.owner.choose(0)
        self.owner.choose(0)
        self.assertEqual(self.owner.phase,'workflow')
        self.owner.choose(0)
        self.assertEqual(self.owner.phase,'await_observation')
        result = self.owner.observe(True)
        self.assertEqual(result.status,'OBSERVED_USER')
        self.assertEqual(dict(result.evidence)['acknowledged_steps'],2)
        self.assertEqual(self.commands,[])

    def test_service_with_enabled_motor_is_blocked_without_commands(self):
        self.status['stepper_enable']['steppers']['stepper_x'] = True
        self.owner.start('O06')
        self.worker.drain()
        self.assertEqual(self.owner.poll().status,'BLOCKED')
        self.assertEqual(self.commands,[])

if __name__ == '__main__':
    unittest.main()
