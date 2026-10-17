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
    def test_unhomed_positive_minimum_homing_has_consent_and_final_bounds(self):
        th=self.data['status']['toolhead']
        th.update(homed_axes='',axis_minimum=[1.5,7.,-5.],axis_maximum=[252.,235.,200.])
        self.data['status']['gcode_move']['position']=[0.,0.,0.,0.]
        self.arm('M03',None)
        self.assertEqual(self.commands,[])
        self.assertTrue(self.c.confirm()[0])
        self.assertFalse(self.command.done())  # dispatch guard accepted the same unhomed data
        self.assertEqual(self.commands[0][1]['script'],'G28\nM400')
        th['homed_axes']='xyz'
        self.data['status']['gcode_move']['position']=[117.5,117.5,10.,0.]
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        self.assertEqual(self.c.observe(True).status,'PASSED_USER')

    def prepare_unhomed(self,feature='M05'):
        self.data['status']['toolhead'].update(homed_axes='',axis_minimum=[1.5,7.,-5.])
        self.data['status']['gcode_move']['position']=[0.,0.,0.,0.]
        self.assertTrue(self.c.start(feature,'stepper_x')[0])
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.worker.drain()
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase,'await_confirmation')
        self.assertTrue(self.c.preparing_home)
        self.assertEqual(self.c.feature_id,feature)
        self.assertEqual(self.commands,[])

    def finish_preparatory_home(self):
        self.data['status']['toolhead']['homed_axes']='xyz'
        self.data['status']['gcode_move']['position']=[50.,50.,20.,0.]
        self.verified()
        # Preparation verification queues a fresh original-test preflight.
        self.assertFalse(self.c.preparing_home)
        self.worker.drain()
        self.assertIsNone(self.c.poll())

    def test_unhomed_tests_home_once_after_consent_then_run_original(self):
        for feature in ('M04','M05','M06','M12'):
            with self.subTest(feature=feature):
                self.setUp()
                self.prepare_unhomed(feature)
                self.clock+=10000  # user question has no deadline
                self.assertIsNone(self.c.poll())
                self.c.confirm()
                self.worker.drain()
                self.c.poll()
                self.assertEqual(self.commands[0][1]['script'],'G28\nM400')
                self.assertEqual(len(self.commands),1)
                self.finish_preparatory_home()
                self.assertEqual(self.c.phase,'running')
                self.assertEqual(self.c.feature_id,feature)
                self.assertEqual(len(self.commands),2)
                script=self.commands[1][1]['script']
                if feature=='M12':
                    self.assertEqual(script.count('G28 X'),10)
                    self.assertNotIn('G28'+chr(10),script)
                    self.assertNotIn('G28 Y',script)
                else:
                    self.assertNotIn('G28',script)
                self.assertTrue(self.c._homing_verified)

    def test_cancel_before_home_does_not_send_motion(self):
        self.prepare_unhomed()
        self.assertEqual(self.c.cancel().status,'ABORTED')
        self.assertFalse(self.worker.jobs)
        self.c.poll()
        self.assertEqual(self.commands,[])

    def test_cancel_while_homing_uses_emergency_stop_without_test_dispatch(self):
        self.prepare_unhomed()
        self.c.confirm()
        self.c.cancel()
        result=self.c.poll()
        self.assertEqual(result.status,'INCONCLUSIVE')
        self.assertEqual([m for m,p in self.commands],
                         ['printer.gcode.script','printer.emergency_stop'])

    def test_failed_homing_never_starts_original_test(self):
        self.prepare_unhomed()
        self.c.confirm()
        self.command.set_exception(ValueError('homing_failed'))
        self.c.poll()
        result=self.c.poll()
        self.assertEqual(result.status,'INCONCLUSIVE')
        self.assertEqual(len(self.commands),2)
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')

    def test_print_start_between_home_and_test_denies_original_dispatch(self):
        self.prepare_unhomed()
        self.c.confirm()
        self.data['status']['toolhead']['homed_axes']='xyz'
        self.data['status']['gcode_move']['position']=[50.,50.,20.,0.]
        self.verified()
        self.data['status']['print_stats']['state']='printing'
        self.worker.drain()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(len(self.commands),1)

    def test_already_homed_test_does_not_home_again(self):
        self.arm()
        self.c.confirm()
        self.assertEqual(len(self.commands),1)
        self.assertNotIn('G28',self.commands[0][1]['script'])

    def test_confirmation_at_2_9_seconds_does_not_shutdown_before_first_refresh(self):
        # Reproduce the physical trace: dispatch at 2.9 s, first poll at 3.12 s.
        self.arm()
        self.clock=2.9
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(len(self.commands),1)
        self.clock=3.12
        self.assertIsNone(self.c.poll())
        self.assertEqual(self.c.phase,'running')
        self.assertTrue(self.worker.jobs)
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'running')
        self.assertEqual(len(self.commands),1)
        self.assertEqual(self.c._safety_reason,'allowed')

    def test_completed_fresh_queue_proof_precedes_old_proof_expiration(self):
        self.arm()
        self.c.confirm()
        self.clock=.3
        self.c.poll()
        # Completed HTTP evidence is waiting when UI consumes it at 5.1 s.
        self.clock=4.9
        self.worker.drain()
        self.clock=5.1
        self.c.poll()
        self.assertEqual(self.c.phase,'running')
        self.assertEqual(len(self.commands),1)
        self.assertAlmostEqual(self.c._queue_age_s,.2)

    def test_real_print_conflict_and_missing_queue_proof_still_shutdown(self):
        self.arm()
        self.c.confirm()
        self.data['status']['print_stats']['state']='printing'
        self.clock=.1
        self.c.poll()
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')
        self.assertEqual(self.c._safety_reason,'print_not_idle')
        self.assertIn('print_not_idle',self.c.poll().reason)

    def test_active_stale_queue_still_stops_at_the_read_watchdog_bound(self):
        self.arm()
        self.c.confirm()
        self.clock=5.01
        self.c.poll()
        self.assertEqual(self.commands[-1][0],'printer.emergency_stop')
        self.assertEqual(self.c._safety_reason,'queue_unknown')
        self.assertEqual(self.c.phase,'stopping')

    def test_late_confirm_still_requires_fresh_admission_without_dispatch(self):
        self.arm()
        self.clock=3.01
        self.c.confirm()
        self.assertEqual(self.c.phase,'preflight')
        self.assertEqual(self.commands,[])

    def test_slow_m03_confirmation_keeps_consent_without_three_start_clicks(self):
        self.arm('M03',None)
        self.clock=4.
        self.c.confirm()
        self.assertTrue(self.c.refreshing_consent)
        self.assertEqual(self.commands,[])
        self.assertIn('Your confirmation is kept',self.c.live_text)
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'running')
        self.assertEqual(len(self.commands),1)
        self.assertEqual(self.commands[0][1]['script'],'G28\nM400')
        self.assertEqual(self.c._confirm_attempts,1)

    def test_cancel_during_consent_refresh_never_dispatches(self):
        self.arm()
        self.clock=4.
        self.c.confirm()
        result=self.c.cancel()
        self.assertEqual(result.status,'ABORTED')
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.commands,[])
        self.assertIsNone(self.c._consented_program)

    def test_changed_position_during_consent_refresh_blocks_without_retargeting(self):
        self.arm()
        self.clock=4.
        self.c.confirm()
        self.data['status']['gcode_move']['position'][0]+=1.
        self.worker.drain()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(result.reason,'motion_consent_context_changed')
        self.assertEqual(self.commands,[])

    def test_real_print_conflict_during_refresh_never_dispatches(self):
        self.arm()
        self.clock=4.
        self.c.confirm()
        self.data['status']['print_stats']['state']='printing'
        self.worker.drain()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(self.commands,[])

    def test_refresh_that_expires_before_ui_poll_never_dispatches(self):
        self.arm()
        self.clock=4.
        self.c.confirm()
        self.worker.drain()
        self.clock=8.
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(self.commands,[])

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
    def test_late_confirmation_refreshes_then_dispatches_same_consent_once(self):
        self.arm()
        self.clock=100000.
        self.assertIsNone(self.c.poll())
        self.assertTrue(self.c.confirm()[0])
        self.assertEqual(self.commands,[])
        self.worker.drain()
        self.c.poll()
        self.assertEqual(self.c.phase,'running')
        self.assertEqual(len(self.commands),1)
        self.assertEqual(self.c._confirm_attempts,1)
        self.c.poll()
        self.assertEqual(len(self.commands),1)
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
        self.assertEqual(self.c.phase,'running')
        self.assertEqual(len(self.commands),2)
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
        self.assertEqual(script.count('G28 X'),10)
        self.assertEqual(script.count('G1 X'),10)
        self.assertIn('ENDSTOP_PHASE_CALIBRATE STEPPER=stepper_x',script)
        self.data['status']['configfile']={'save_config_pending':True,
            'save_config_pending_items':{'endstop_phase stepper_x':{'trigger_phase':'7/64'}}}
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        self.assertIn('Trigger phase: 7/64',self.c.observation_details)
        self.assertIn('Homing cycles: 10',self.c.observation_details)
        self.assertIn('Pending config: YES',self.c.observation_details)
        self.assertIn('Saved to file: NO',self.c.observation_details)
        self.assertEqual(len(self.commands),1)  # Review did not send SAVE_CONFIG.
        result=self.c.observe(True)
        self.assertEqual(result.status,'OBSERVED_USER')
        self.assertFalse(result.restore_verified)
        self.assertIn(('homing_cycles',10),result.evidence)
    def test_phase_y_style_offset_finishes_without_shutdown(self):
        # Synthetic physical trace with an endstop-phase offset outside min.
        from dataclasses import replace
        self.data['settings']['stepper_x'].update(
            position_endstop=1.5,rotation_distance=40.,
            full_steps_per_rotation=200)
        self.data['status']['toolhead']['axis_minimum'][0]=1.5
        self.p.state=PrinterState.from_snapshot(self.data)
        self.p.maintenance.snapshot=replace(
            self.p.maintenance.snapshot,config_marker=id(self.p.state.settings))
        self.arm('M12')
        self.c.confirm()
        self.data['status']['configfile']={'save_config_pending':True,
            'save_config_pending_items':{'endstop_phase stepper_x':{
                'trigger_phase':'49/64'}}}
        self.data['status']['gcode_move']['position'][0]=1.325
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        self.assertEqual(self.c.observe(True).status,'OBSERVED_USER')
        self.assertNotIn('printer.emergency_stop',
                         [method for method,_ in self.commands])

    def test_live_dispatch_geometry_rejection_keeps_specific_diagnostic(self):
        self.arm('M04')
        # On-demand preflight was valid; the subscription dispatch snapshot
        # can still be incomplete. Expose that cause without relaxing guard.
        self.data['status']['toolhead'].pop('max_velocity')
        self.c.confirm()
        self.assertTrue(self.c._command.done())
        self.assertEqual(self.c._dispatch_guard_reason,'motion_velocity_unknown')
        self.assertIsNotNone(self.c._command.exception())

    def test_definitive_pre_send_guard_rejection_never_emergency_stops(self):
        from moonraker_client import MoonrakerError
        self.arm('M04')
        def denied(*args,**kwargs):
            future=Future()
            future.dispatch_stage='guard_denied'
            self.c._dispatch_guard_reason='clear_mesh_before_motion_test'
            future.set_exception(MoonrakerError('Printer state changed before command dispatch'))
            return future
        self.p.subscription.request=denied
        self.c.confirm()
        result=self.c.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(result.reason,'clear_mesh_before_motion_test')
        self.assertFalse(self.c._blocked)
        self.assertEqual(self.commands,[])
        self.assertFalse(self.c.pending)

    def test_cleared_mesh_placeholder_allows_buzz_after_http_preflight(self):
        from printer_state import PrinterState
        from dataclasses import replace
        self.data['settings']['bed_mesh']={}
        self.data['status']['bed_mesh']={'profile_name':'','mesh_min':[0,0],
            'mesh_max':[0,0],'mesh_matrix':[[]]}
        self.p.state=PrinterState.from_snapshot(self.data)
        self.p.maintenance.snapshot=replace(self.p.maintenance.snapshot,
            config_marker=id(self.p.state.settings))
        self.arm('M04')
        self.c.confirm()
        self.assertFalse(self.command.done())
        self.verified()
        self.assertEqual(self.c.phase,'await_observation')
        self.assertEqual(self.c.observe(True).status,'PASSED_USER')
        self.assertEqual(len(self.commands),1)

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
        self.assertEqual(self.commands[0][1]['script'].count('G28 X'),10)
        self.assertIn('ENDSTOP_PHASE_CALIBRATE STEPPER=stepper_x',
                      self.commands[0][1]['script'])

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
