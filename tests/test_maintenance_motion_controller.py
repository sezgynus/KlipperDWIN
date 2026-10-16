from concurrent.futures import Future
from copy import deepcopy
from unittest.mock import patch
import unittest
from test_maintenance_controller import printer, Worker
from test_maintenance_motion import state_and_status
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot,DeviceCapabilities,USER,EXTERNAL,CALIBRATION,_add
from maintenance_motion_controller import MaintenanceMotionController

class MotionControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock=0.
        self.p,self.data=printer()
        raw,status=state_and_status()
        raw.settings['endstop_phase stepper_x']={}
        status['endstop_phase']={'last_home':{'stepper_x':{'phase':4,'phases':64}}}
        status['configfile']={'save_config_pending':False}
        self.data['settings']=raw.settings
        self.data['status'].update(status)
        self.p.state=PrinterState.from_snapshot(self.data)
        self.p.subscription.lifecycle=lambda:{'state':self.data['state'],'epoch':self.data['epoch']}
        bits=0
        for f,m in (('M04',USER),('M05',USER),('M06',EXTERNAL),('M12',CALIBRATION)):
            bits=_add(bits,f,m)
        self.p.maintenance.snapshot=MaintenanceSnapshot(12,(
            DeviceCapabilities('stepper_x','stepper',bits),),
            _add(0,'M03',CALIBRATION),id(self.p.state.settings))
        self.worker=Worker()
        self.p.subscription.request=self.request
        self.commands=[]
        self.client=type('Client',(),{'get':lambda _,path:self.get(path)})()
        self.c=MaintenanceMotionController(self.p,self.worker,self.client)
        for name in ('maintenance_motion_controller.monotonic','maintenance_runtime.monotonic'):
            p=patch(name,lambda:self.clock)
            p.start()
            self.addCleanup(p.stop)
    def get(self,path):
        if path=='/server/info':
            return {'result':{'components':[]}}
        if path.startswith('/printer/objects/query?'):
            return {'result':{'eventtime':self.clock,'status':deepcopy(self.data['status'])}}
        raise AssertionError(path)
    def request(self,method,params=None,guard=None,request_timeout=None):
        f=Future()
        self.commands.append((method,params))
        if guard is not None and not guard():
            f.set_exception(ValueError('guard'))
            return f
        if method=='printer.emergency_stop':
            f.set_result('ok')
        else:
            self.command=f
        return f
    def arm(self,feature='M05',device='stepper_x'):
        self.assertTrue(self.c.start(feature,device)[0])
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase,'await_confirmation')
        self.assertEqual(self.commands,[])
    def verified(self):
        self.command.set_result('ok')
        for i in range(2):
            self.clock+=.5
            self.assertIsNone(self.c.poll())
            self.worker.drain()
            self.assertIsNone(self.c.poll())
    def test_roundtrip_needs_user_observation_and_two_position_mode_reads(self):
        self.arm()
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.commands[0][0],'printer.gcode.script')
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        self.clock=100000.
        self.assertIsNone(self.c.poll())
        result=self.c.observe(True)
        self.assertEqual(result.status,'PASSED_USER')
        self.assertTrue(result.restore_verified)
    def test_late_confirmation_only_refreshes_readonly_preflight(self):
        self.arm()
        self.clock=100000.
        self.assertIsNone(self.c.poll())
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.commands,[])
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'await_confirmation')
    def test_external_measurement_and_return_have_separate_consent(self):
        self.arm('M06')
        self.c.confirm()
        self.data['status']['gcode_move']['position'][0]=60.
        self.verified()
        self.assertEqual(self.c.phase,'await_measurement')
        self.clock=100000.
        self.assertIsNone(self.c.poll())
        self.c.begin_measurement()
        self.c.record_measurement(9.9)
        self.assertEqual(len(self.commands),1)
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'await_confirmation')
        self.assertTrue(self.c.returning)
        # Waiting again at the RETURN question refreshes the same outbound
        # evidence; it must not mistake a prepared return for a sent return.
        self.clock+=10000.
        self.c.confirm()
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'await_confirmation')
        self.c.confirm()
        self.data['status']['gcode_move']['position'][0]=50.
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        result=self.c.observe(True)
        self.assertEqual(result.status,'PASSED_USER')
        self.assertIn(('measured_mm',9.9),result.evidence)
    def test_measured_return_blocks_if_operator_moved_machine(self):
        self.arm('M06')
        self.c.confirm()
        self.data['status']['gcode_move']['position'][0]=60.
        self.verified()
        self.c.begin_measurement()
        self.data['status']['gcode_move']['position'][0]=61.
        self.c.record_measurement(10.)
        self.worker.drain()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertIn('manual_recovery',result.reason)
        self.assertEqual(len(self.commands),1)
    def test_active_cancel_uses_emergency_rpc_not_automatic_reversal(self):
        self.arm()
        self.c.confirm()
        self.c.cancel()
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')
        result=self.c.poll()
        self.assertFalse(result.restore_verified)
        self.assertFalse(self.c.start('M05','stepper_x')[0])
        self.assertEqual(len(self.commands),2)
    def test_phase_requires_pending_exact_result_without_save_or_new_homing(self):
        self.arm('M12')
        self.c.confirm()
        script=self.commands[0][1]['script']
        self.assertEqual(script,'ENDSTOP_PHASE_CALIBRATE STEPPER=stepper_x')
        self.data['status']['configfile']={'save_config_pending':True,
            'save_config_pending_items':{'endstop_phase stepper_x':{'trigger_phase':'7/64'}}}
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        result=self.c.observe(True)
        self.assertEqual(result.status,'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
    def test_command_failure_is_not_retried(self):
        self.arm()
        self.c.confirm()
        self.command.set_exception(ValueError('ambiguous'))
        self.c.poll()
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')
        self.c.poll()
        self.assertEqual(len(self.commands),2)

    def test_phase_dispatch_does_not_require_global_last_home_subscription(self):
        self.arm('M12')
        del self.data['status']['endstop_phase']
        self.assertTrue(self.c.confirm()[0])
        self.assertFalse(self.command.done())
        self.assertEqual(self.commands[0][1]['script'],
                         'ENDSTOP_PHASE_CALIBRATE STEPPER=stepper_x')

    def test_motion_snapshot_epoch_change_never_retargets_old_command(self):
        self.arm()
        self.c.confirm()
        self.data['epoch']=13
        self.c.poll()
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')
        # The shutdown guard rejects the new epoch: no claim of restored state.
        result=self.c.poll()
        self.assertFalse(result.restore_verified)
        self.assertIn('SHUTDOWN_UNCONFIRMED',result.reason)

    def test_owned_other_motion_is_blocked_while_maintenance_reserves_printer(self):
        from types import SimpleNamespace
        from operation_guards import motion_dispatch_guard
        self.p.maintenance_pulse=SimpleNamespace(pending=True)
        with self.assertRaises(ValueError):
            motion_dispatch_guard(self.p,owner='jog',position=True)

    def test_geometry_block_reason_is_specific_and_no_rpc_is_sent(self):
        self.data['status']['gcode_move']['position'][2]=1.
        self.c.start('M05','stepper_x')
        self.worker.drain()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(result.reason,'move_away_from_axis_limits')
        self.assertEqual(self.commands,[])
