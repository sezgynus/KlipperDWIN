"""Probe workflows: CI-only fake worker, firmware and printer evidence."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch
import copy
import unittest

from test_maintenance_controller import printer, Worker
from maintenance_discovery import MaintenanceSnapshot, _add
from maintenance_probe import MaintenanceProbeController, METHODS, LEVELING_ONLY, probe_measurement
from maintenance_workflow import adapters


class ProbeEvidenceTests(unittest.TestCase):
    def test_numeric_accuracy_requires_complete_consistent_firmware_result(self):
        line = 'probe accuracy results: maximum 1.000000, minimum 0.900000, range 0.100000, average 0.950000, median 0.950000, standard deviation 0.020000'
        self.assertEqual(dict(probe_measurement('P03',(line,)))['range_mm'],.1)
        for bad in ('ok',line.replace('0.100000','0.200000'),
                    line.replace('0.950000','nan')):
            self.assertEqual(probe_measurement('P03',(bad,)),())

    def test_single_probe_supports_current_and_previous_upstream_result(self):
        for text in ('probe at 50.000,50.000 is z=0.250000',
                     'Result: at 50.000,50.000 estimate contact at z=0.250000'):
            self.assertEqual(dict(probe_measurement('P04',(text,)))['z_mm'],.25)
        self.assertEqual(probe_measurement('P04',('ok',)),())

    def test_leveling_duplicates_never_registered(self):
        ids = {r.feature_id for r in adapters(METHODS,'probe')}
        self.assertFalse(ids & LEVELING_ONLY)
        self.assertEqual(ids, {'P01','P02','P03','P04','P06','P12','P13','P14',
                               'P15','P16','P17','P18','P19','P20','P21','P22'})


class ProbeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.p,self.raw = printer()
        self.status = {'manual_probe':{'is_active':False},
                       'configfile':{'save_config_pending':False,'save_config_pending_items':{}},
                       'probe':{'last_query':False},
                       'toolhead':{'position':[50.,50.,20.,0.],'homed_axes':'xyz',
                                   'axis_minimum':[0.,0.,0.,0.],
                                   'axis_maximum':[200.,200.,200.,0.]}}
        self.raw['status'].update(copy.deepcopy(self.status))
        self.p.subscription.lifecycle = Mock(return_value={'state':'ready','epoch':12})
        self.p.subscription.responses_since = self.responses
        self.p.subscription.request = self.request
        self.commands, self.lines = [], []
        self.stamp = 100.
        self.worker = Worker()
        self.client = SimpleNamespace(get=self.get)
        self.owner = MaintenanceProbeController(self.p,self.worker,self.client)
        modes = 0
        for f,m in METHODS.items():
            modes = _add(modes,f,m)
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,global_modes=modes,
                                             config_marker=id(self.p.state.settings))
        self.clock = 1000.
        self.patches = [patch(name,side_effect=lambda:self.clock)
                       for name in ('maintenance_workflow.monotonic','maintenance_runtime.monotonic')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def get(self,path):
        if path == '/server/info':
            return {'result':{'components':[]}}
        if path.startswith('/printer/objects/query?'):
            self.stamp += 1
            return {'result':{'status':copy.deepcopy(self.status),'eventtime':self.stamp}}
        raise AssertionError(path)

    def responses(self,cursor):
        return len(self.lines), tuple(self.lines[cursor:]) if cursor is not None else ()

    def request(self,method,params=None,guard=None,**kwargs):
        if guard is not None and not guard():
            raise ValueError('dispatch_denied')
        self.commands.append((method,params))
        self.command = Future()
        if method == 'printer.emergency_stop':
            self.command.set_result('ok')
        return self.command

    def set_probe_hooks(self, activate, deactivate):
        # Simulates Moonraker's real configfile.settings snapshot,
        # not a fixture-specific servo name embedded in Petrel.
        from dataclasses import replace
        from printer_state import PrinterState
        self.raw['settings']['probe'] = {
            'pin':'PB1','activate_gcode':activate,'deactivate_gcode':deactivate}
        self.p.state = PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot = replace(self.p.maintenance.snapshot,
                        config_marker=id(self.p.state.settings))

    def set_p04_low_z(self, z=2.964, z_max=200., *, kinematics='cartesian'):
        from dataclasses import replace
        from printer_state import PrinterState
        self.raw['settings']['printer'] = {'kinematics':kinematics}
        self.p.state = PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot = replace(self.p.maintenance.snapshot,
            config_marker=id(self.p.state.settings))
        self.status['toolhead']['position'][2] = z
        self.status['toolhead']['axis_maximum'][2] = z_max
        self.status['gcode_move'] = {
            'position':[50.,50.,z,0.], 'homing_origin':[0.,0.,0.,0.],
            'speed':50., 'speed_factor':1., 'extrude_factor':1.,
            'absolute_coordinates':True, 'absolute_extrude':True}
        self.raw['status'].update(copy.deepcopy(self.status))

    def finish_p04_z_lift(self, z=10., *, x=None, speed_factor=None):
        self.status['toolhead']['position'][2] = z
        self.status['gcode_move']['position'][2] = z
        if x is not None:
            self.status['toolhead']['position'][0] = x
            self.status['gcode_move']['position'][0] = x
        if speed_factor is not None:
            self.status['gcode_move']['speed_factor'] = speed_factor
        self.raw['status'].update(copy.deepcopy(self.status))
        self.command.set_result('ok')
        self.assertIsNone(self.owner.poll())
        self.worker.drain()
        return self.owner.poll()

    def arm(self,feature='P01'):
        self.assertTrue(self.owner.start(feature)[0])
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'await_confirmation')

    def dispatch(self):
        self.assertTrue(self.owner.confirm()[0])
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'running')

    def complete(self,lines=()):
        self.lines.extend(lines)
        self.command.set_result('ok')
        self.assertIsNone(self.owner.poll())
        self.worker.drain()
        return self.owner.poll()

    def prepare_unhomed_motion(self):
        from dataclasses import replace
        from printer_state import PrinterState
        from test_maintenance_motion import state_and_status
        raw,values=state_and_status()
        self.raw['settings'].update(raw.settings)
        self.p.state=PrinterState.from_snapshot(self.raw)
        self.p.maintenance.snapshot=replace(self.p.maintenance.snapshot,
            config_marker=id(self.p.state.settings))
        for key in ('gcode_move','stepper_enable','extruder','heater_bed'):
            if key in values:
                self.status[key]=copy.deepcopy(values[key])
        self.status['toolhead'].update(values['toolhead'])
        self.status['toolhead']['homed_axes']=''
        self.raw['status'].update(copy.deepcopy(self.status))
        p=patch('maintenance_motion_controller.monotonic',side_effect=lambda:self.clock)
        p.start()
        self.addCleanup(p.stop)

    def finish_preparation_home(self):
        self.status['toolhead']['homed_axes']='xyz'
        self.raw['status'].update(copy.deepcopy(self.status))
        self.command.set_result('ok')
        for _ in range(2):
            self.clock+=.5
            self.owner.poll()
            self.worker.drain()
            self.owner.poll()
        self.assertFalse(self.owner.preparing_home)
        self.worker.drain()
        self.owner.poll()

    def test_unhomed_probe_home_then_test_share_one_consent(self):
        self.prepare_unhomed_motion()
        self.owner.start('P04')
        self.worker.drain()
        self.owner.poll()
        self.worker.drain()
        self.owner.poll()
        self.assertTrue(self.owner.preparing_home)
        self.assertEqual(self.owner.feature_id,'P04')
        self.assertEqual(self.commands,[])
        self.owner.confirm()
        self.assertEqual(self.commands[0][1]['script'],'G28\nM400')
        self.finish_preparation_home()
        self.assertEqual(self.owner.phase,'running')
        self.assertEqual(self.commands[1][1]['script'],'PROBE')
        self.assertEqual(len(self.commands),2)

    def test_p04_low_z_raises_only_z_then_probes_after_fresh_readback(self):
        self.set_p04_low_z()
        self.arm('P04')
        self.assertEqual(self.commands,[])
        self.dispatch()
        script=self.commands[0][1]['script']
        self.assertIn('SAVE_GCODE_STATE NAME=_PETREL_P04_',script)
        self.assertIn('G91\nM220 S100\nG1 Z7.0360 F300\nM400',script)
        self.assertIn('RESTORE_GCODE_STATE NAME=_PETREL_P04_',script)
        self.assertFalse(any(line.strip() == 'PROBE' for line in script.splitlines()))
        self.assertIsNone(self.finish_p04_z_lift())
        self.assertEqual(self.owner.phase,'preflight')
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.commands[1][1]['script'],'PROBE')
        self.assertEqual(self.owner.phase,'running')
        result=self.complete(('Result: at 50.000,50.000 estimate contact at z=-0.025000',))
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(dict(result.evidence)['preparation_z_lift_mm'],7.036)
        self.assertEqual(dict(result.evidence)['z_mm'],-.025)
        self.assertFalse(result.restore_verified)
        self.assertNotIn('G28',str(self.commands))
        self.assertEqual(len(self.commands),2)

    def test_p04_sufficient_z_runs_directly_without_lift(self):
        self.arm('P04')
        self.dispatch()
        self.assertEqual(self.commands[0][1]['script'],'PROBE')
        self.assertEqual(self.complete(
            ('Result: at 50.000,50.000 estimate contact at z=0.125000',)
        ).status,'PASSED')
        self.assertEqual(len(self.commands),1)

    def test_p04_rejects_unverified_lift_and_never_probes(self):
        for kwargs in ({'z':7.}, {'z':10.,'x':51.},
                       {'z':10.,'speed_factor':1.2}):
            with self.subTest(kwargs=kwargs):
                self.set_p04_low_z()
                self.arm('P04')
                self.dispatch()
                result=self.finish_p04_z_lift(**kwargs)
                self.assertEqual(result.status,'INCONCLUSIVE')
                self.assertEqual(result.reason,'probe_z_lift_readback_unverified')
                self.assertEqual(len(self.commands),1)
                self.assertTrue(self.owner._locked)
                # Reset only fake harness for the next independent case.
                self.owner = MaintenanceProbeController(self.p,self.worker,self.client)
                self.commands.clear()
                self.status['toolhead']['position'][0]=50.

    def test_p04_lift_requires_valid_bounded_motion_profile(self):
        for zmax,kinematics in ((5.5,'cartesian'),(200.,'delta')):
            with self.subTest(zmax=zmax, kinematics=kinematics):
                self.set_p04_low_z(z_max=zmax,kinematics=kinematics)
                self.assertTrue(self.owner.start('P04')[0])
                self.worker.drain()
                result=self.owner.poll()
                self.assertEqual(result.status,'BLOCKED')
                self.assertEqual(self.commands,[])

    def test_p04_lift_does_not_start_when_printing_after_consent(self):
        self.set_p04_low_z()
        self.arm('P04')
        self.raw['status']['print_stats']['state']='printing'
        self.assertTrue(self.owner.confirm()[0])
        self.worker.drain()
        self.assertEqual(self.owner.poll().status,'BLOCKED')
        self.assertEqual(self.commands,[])

    def test_unhomed_read_only_probe_does_not_home(self):
        self.status['toolhead']['homed_axes']=''
        self.arm('P01')
        self.assertFalse(self.owner.preparing_home)
        self.assertEqual(self.commands,[])

    def test_entry_and_human_wait_never_dispatch_or_expire(self):
        self.arm()
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.owner.phase,'await_confirmation')
        self.assertEqual(self.commands,[])
        self.dispatch()
        self.assertIsNone(self.complete(('probe: open',)))
        self.assertEqual(self.owner.phase,'workflow')
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.assertEqual(len(self.commands),1)

    def test_probe_release_press_release_requires_three_fresh_readings(self):
        self.arm()
        self.dispatch()
        self.assertIsNone(self.complete(('probe: open',)))
        for state in ('TRIGGERED','open'):
            self.assertTrue(self.owner.choose(0)[0])
            self.worker.drain()
            self.owner.poll()
            result = self.complete(('probe: '+state,))
        self.assertEqual(result.status,'PASSED')
        self.assertEqual(dict(result.evidence)['transitions'],'open > TRIGGERED > open')

    def test_p01_dispatches_exact_configured_gcode_and_restores_after_three_reads(self):
        activate = ('SET_SERVO SERVO=probe_servo ANGLE=35   # deploy\n'
                    'G4 P500\n'
                    'SET_SERVO SERVO=probe_servo WIDTH=0')
        deactivate = ('SET_SERVO SERVO=probe_servo ANGLE=103  # retract\n'
                      'G4 P500\n'
                      'SET_SERVO SERVO=probe_servo WIDTH=0')
        self.set_probe_hooks(activate, deactivate)
        self.arm()
        self.dispatch()
        self.assertEqual(self.commands[0][1]['script'], activate+'\nQUERY_PROBE')
        self.assertIsNone(self.complete(('probe: open',)))
        for state in ('TRIGGERED','open'):
            self.assertTrue(self.owner.choose(0)[0])
            self.worker.drain()
            self.assertIsNone(self.owner.poll())
            self.assertEqual(self.commands[-1][1]['script'],'QUERY_PROBE')
            self.assertIsNone(self.complete(('probe: '+state,)))
        # No PASS until the user's own deactivate_gcode has completed.
        self.assertEqual(self.owner.phase,'preflight')
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.commands[-1][1]['script'],deactivate)
        result = self.complete()
        self.assertEqual(result.status,'PASSED')
        self.assertTrue(result.restore_verified)
        self.assertEqual(dict(result.evidence)['transitions'],
                         'open > TRIGGERED > open')
        self.assertTrue(dict(result.evidence)['deactivate_gcode_completed'])
        self.assertEqual(len(self.commands),4)
        self.assertNotIn('SAVE_CONFIG',str(self.commands))

    def test_p01_multiline_config_keeps_blank_lines_and_comments_verbatim(self):
        # Klipper/Moonraker can preserve leading and empty lines in
        # [probe] activate_gcode and deactivate_gcode settings.
        activate = ('\n'
                    '    # Deploy using the operator-defined servo\n'
                    '    SET_SERVO SERVO=probe_servo ANGLE=35 # deploy\n'
                    '\n'
                    '    G4 P500\n'
                    '    SET_SERVO SERVO=probe_servo WIDTH=0\n')
        deactivate = ('\n'
                      '    # Retract using the same user settings\n'
                      '    SET_SERVO SERVO=probe_servo ANGLE=103 # retract\n'
                      '\n'
                      '    G4 P500\n'
                      '    SET_SERVO SERVO=probe_servo WIDTH=0\n')
        self.set_probe_hooks(activate, deactivate)
        self.arm()
        self.dispatch()
        self.assertEqual(self.commands[0][1]['script'],
                         activate + '\nQUERY_PROBE')
        self.assertIsNone(self.complete(('probe: open',)))
        for state in ('TRIGGERED','open'):
            self.assertTrue(self.owner.choose(0)[0])
            self.worker.drain()
            self.owner.poll()
            self.assertIsNone(self.complete(('probe: '+state,)))
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.commands[-1][1]['script'], deactivate)
        result = self.complete()
        self.assertEqual(result.status, 'PASSED')
        self.assertTrue(result.restore_verified)

    def test_p01_blank_lines_cannot_hide_save_config_command(self):
        self.set_probe_hooks('\n # comment\n\n save_config # not allowed\n',
                             '\nSET_SERVO SERVO=probe_servo WIDTH=0\n')
        self.assertTrue(self.owner.start('P01')[0])
        self.worker.drain()
        result = self.owner.poll()
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'workflow_script_invalid')
        self.assertEqual(self.commands, [])

    def test_p01_cancel_after_activation_runs_deactivate_first(self):
        self.set_probe_hooks('SET_SERVO SERVO=probe_servo ANGLE=35',
                             'SET_SERVO SERVO=probe_servo ANGLE=103')
        self.arm()
        self.dispatch()
        self.complete(('probe: open',))
        self.assertIsNone(self.owner.cancel())
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.commands[-1][1]['script'],
                         'SET_SERVO SERVO=probe_servo ANGLE=103')
        result = self.complete()
        self.assertEqual(result.status,'ABORTED')
        self.assertTrue(result.restore_verified)
        self.assertEqual(result.reason,'probe_deactivated_after_cancel')
        self.assertEqual(len(self.commands),2)

    def test_p01_cancel_during_activation_waits_then_deactivates(self):
        self.set_probe_hooks('SET_SERVO SERVO=probe_servo WIDTH=0',
                             'SET_SERVO SERVO=probe_servo ANGLE=103')
        self.arm()
        self.dispatch()
        self.assertIsNone(self.owner.cancel())
        self.assertEqual(len(self.commands),1)
        self.assertIsNone(self.complete(('probe: open',)))
        self.worker.drain()
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.commands[-1][1]['script'],
                         'SET_SERVO SERVO=probe_servo ANGLE=103')
        result = self.complete()
        self.assertEqual(result.status,'ABORTED')
        self.assertTrue(result.restore_verified)

    def test_p01_wrong_probe_status_waits_and_cancel_restores(self):
        self.set_probe_hooks('SET_SERVO SERVO=probe_servo ANGLE=35',
                             'SET_SERVO SERVO=probe_servo ANGLE=103')
        self.arm()
        self.dispatch()
        self.assertIsNone(self.complete(('probe: TRIGGERED',)))
        self.assertEqual(self.owner._stage,0)
        self.assertEqual(self.owner.phase,'workflow')
        self.owner.cancel()
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.commands[-1][1]['script'],
                         'SET_SERVO SERVO=probe_servo ANGLE=103')
        self.assertEqual(self.complete().status,'ABORTED')

    def test_p01_rejects_half_configured_hooks_or_raw_jinja(self):
        for activate,deactivate,reason in (
                ('SET_SERVO SERVO=p ANGLE=90','',
                 'probe_activate_deactivate_pair_required'),
                ('','SET_SERVO SERVO=p WIDTH=0',
                 'probe_activate_deactivate_pair_required'),
                ('{% if printer.toolhead.homed_axes %}SET_SERVO{% endif %}',
                 'SET_SERVO SERVO=p WIDTH=0',
                 'probe_template_requires_native_execution')):
            with self.subTest(reason=reason, activate=activate):
                self.set_probe_hooks(activate,deactivate)
                self.assertTrue(self.owner.start('P01')[0])
                self.worker.drain()
                result=self.owner.poll()
                self.assertEqual(result.status,'BLOCKED')
                self.assertEqual(result.reason,reason)
                self.assertEqual(self.commands,[])

    def test_worker_pressure_never_reuses_a_completed_command_or_preflight(self):
        self.arm()
        with patch.object(self.worker,'submit',side_effect=RuntimeError('full')):
            self.assertFalse(self.owner.confirm()[0])
        self.assertEqual(self.owner.phase,'await_confirmation')
        self.assertIsNone(self.owner._future)
        self.assertIsNone(self.owner.poll())
        self.assertEqual(self.commands,[])

    def test_plain_rpc_ok_is_never_probe_accuracy_pass(self):
        self.arm('P03')
        self.dispatch()
        result = self.complete()
        self.assertEqual(result.status,'INCONCLUSIVE')

    def test_print_start_after_consent_denies_dispatch(self):
        self.arm()
        self.raw['status']['print_stats']['state'] = 'printing'
        self.assertTrue(self.owner.confirm()[0])
        self.worker.drain()
        result = self.owner.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(self.commands,[])

    def test_active_motion_cancel_uses_emergency_stop_without_replay(self):
        self.arm('P04')
        self.dispatch()
        self.assertIsNone(self.owner.cancel())
        result = self.owner.poll()
        self.assertIn('klipper_shutdown',result.reason)
        self.assertEqual(self.commands[-1],('printer.emergency_stop',None))
        self.assertEqual(len(self.commands),2)

    def test_stale_or_malformed_measurement_is_not_passed(self):
        self.arm('P03')
        self.dispatch()
        self.stamp = -100
        self.assertIsNone(self.complete())
        result = self.owner.poll()
        self.assertEqual(result.status,'INCONCLUSIVE')

    def test_skew_requires_all_three_explicit_external_measurements(self):
        self.arm('P21')
        self.dispatch()
        self.complete()
        self.assertEqual(self.owner.phase,'workflow')
        self.owner.choose(3)
        self.worker.drain()
        self.assertEqual(self.owner.poll().reason,'enter_all_three_external_measurements')
        self.assertEqual(len(self.commands),1)

    def test_owned_manual_z_controls_do_not_automatically_accept_or_save(self):
        self.arm('P06')
        self.dispatch()
        self.status['manual_probe'] = {'is_active':True,'z_position':20.}
        self.complete()
        self.assertEqual(self.owner.phase,'workflow')
        self.assertTrue(self.owner._owned_manual)
        self.assertIn(('Accept this point','accept'),self.owner.workflow_choices)
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.assertEqual(len(self.commands),1)
        self.assertNotIn('SAVE_CONFIG',str(self.commands))

    def test_tap_prompt_without_completion_is_not_evidence(self):
        self.arm('P02')
        self.dispatch()
        result = self.complete(('Tap the load cell 1 times:',))
        self.assertEqual(result.status,'INCONCLUSIVE')


if __name__ == '__main__':
    unittest.main()
