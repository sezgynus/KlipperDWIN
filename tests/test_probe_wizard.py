from concurrent.futures import Future
import unittest
from unittest.mock import ANY, Mock, patch

import probe_wizard
from test_capabilities import snapshot, printer, display


def data():
    result = snapshot(probe=True)
    result['objects'].append('manual_probe')
    result['status']['manual_probe'] = {'is_active': False}
    result['status']['configfile'] = {'save_config_pending': False, 'save_config_pending_items': {}}
    return result


class ProbeTests(unittest.TestCase):
    def printer(self):
        result = printer(data())
        result.subscription.request.side_effect = lambda *a, **k: Future()
        def center_future(*args, **kwargs):
            future = Future()
            future.cleanup_complete = True
            return future
        result.sendGCode.side_effect = center_future
        return result

    def status(self, result, active, pending=None):
        source = data()
        source['status']['manual_probe']['is_active'] = active
        if hasattr(result.probe_wizard, 'center'):
            source['status']['toolhead']['position'][:2] = result.probe_wizard.center
        if pending is not None:
            source['status']['configfile'] = dict(save_config_pending=bool(pending), save_config_pending_items=pending)
        result.subscription.snapshot.return_value = source
        result.update_variable()

    def started(self):
        result = self.printer()
        future = result.probe_wizard.start()
        future.set_result('ok')
        self.status(result, False)
        result.probe_wizard.update()
        result.probe_wizard.pending[1].set_result('ok')
        self.status(result, True)
        result.probe_wizard.update()
        return result

    def test_start_centers_probe_before_calibration_and_homes_when_needed(self):
        result = self.printer()
        future = result.probe_wizard.start()
        script = result.sendGCode.call_args.args[0]
        self.assertIn('G1 X125.000 Y130.000', script)
        self.assertIn('SAVE_GCODE_STATE', script)
        self.assertIn('RESTORE_GCODE_STATE', result.sendGCode.call_args.kwargs['cleanup'])
        self.assertLess(script.index('G1 Z5.000'), script.index('G1 X'))
        self.assertNotIn('PROBE_CALIBRATE', script)
        future.set_result('ok')
        result.probe_wizard.update()
        self.assertEqual(result.subscription.request.call_count, 0)
        self.status(result, False)
        result.probe_wizard.update()
        result.subscription.request.assert_called_with('printer.gcode.script', {'script':'PROBE_CALIBRATE'}, guard=ANY)
        result.probe_wizard.pending[1].set_result('ok')
        self.status(result, True)
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'active')
        unhomed = self.printer()
        source = data(); source['status']['toolhead']['homed_axes'] = 'xy'
        unhomed.subscription.snapshot.return_value = source; unhomed.update_variable()
        unhomed.probe_wizard.start()
        self.assertEqual(unhomed.subscription.request.call_args.args[1], {'script':'G28'})

    def test_testz_requires_owned_session_and_serializes_steps(self):
        result = self.printer()
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(-.01)
        result = self.started()
        future = result.probe_wizard.testz(-.01)
        self.assertEqual(result.subscription.request.call_args.args[1]['script'], 'TESTZ Z=-0.01')
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(-.1)
        future.set_result('ok')
        result.probe_wizard.update()
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(-10)

    def test_accept_checks_pending_offset_and_save_is_separate(self):
        result = self.started()
        future = result.probe_wizard.accept()
        future.set_result('ok')
        self.status(result, False, {'bltouch': {'z_offset': '2.100'}})
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'accepted')
        self.assertNotIn('SAVE_CONFIG', [call.args[1]['script'] for call in result.subscription.request.call_args_list])
        result.probe_wizard.save()
        self.assertEqual(result.subscription.request.call_args.args[1]['script'], 'SAVE_CONFIG')

    def test_unsuccessful_accept_response_does_not_allow_save(self):
        result = self.started()
        future = result.probe_wizard.accept()
        future.set_result('ok')
        self.status(result, False)
        with patch.object(probe_wizard.time, 'monotonic', return_value=result.probe_wizard.pending[2] + 31):
            result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'error')
        with self.assertRaises(ValueError):
            result.probe_wizard.save()

    def test_abort_does_not_save_and_waits_for_inactive_status(self):
        result = self.started()
        result.probe_wizard.abort().set_result('ok')
        result.probe_wizard.update()
        self.assertIsNotNone(result.probe_wizard.pending)
        self.status(result, False)
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'idle')
        self.assertEqual(result.subscription.request.call_args.args[1]['script'], 'ABORT')

    def test_external_session_existing_changes_and_print_block_start(self):
        for active, pending, state in ((True, {}, 'standby'), (False, {}, 'printing')):
            result = self.printer()
            source = data()
            source['status']['manual_probe']['is_active'] = active
        if hasattr(result.probe_wizard, 'center'):
            source['status']['toolhead']['position'][:2] = result.probe_wizard.center
            source['status']['configfile']['save_config_pending'] = bool(pending)
            source['status']['print_stats']['state'] = state
            result.subscription.snapshot.return_value = source
            result.update_variable()
            with self.assertRaises(ValueError):
                result.probe_wizard.start()
            result.subscription.request.assert_not_called()

    def test_epoch_change_does_not_replay_commands(self):
        result = self.started()
        source = data()
        source['epoch'] = 2
        result.subscription.snapshot.return_value = source
        result.update_variable()
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'interrupted')
        self.assertEqual(result.subscription.request.call_count, 1)
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(.1)

    def test_ui_offers_probe_separately_from_runtime_offset(self):
        result = display(data())
        self.assertNotIn('PROBE', [item[0] for item in result._menus['control']])
        self.assertIn('PROBE', [item[0] for item in result._mesh_menu_entries()])
        result._probe_selection = 0
        result.checkkey = result.ProbeWizardID
        result.Draw_Probe_Wizard()
        result.pd.sendGCode.assert_not_called()

    def test_save_rejects_unrelated_or_changed_pending_configuration(self):
        for pending in ({'bltouch': {'z_offset': '2.1'}, 'extruder': {'pid_kp': '1'}},
                        {'bltouch': {'z_offset': '2.2'}}):
            result = self.started()
            result.probe_wizard.accept().set_result('ok')
            self.status(result, False, {'bltouch': {'z_offset': '2.1'}})
            result.probe_wizard.update()
            self.status(result, False, pending)
            with self.assertRaises(ValueError):
                result.probe_wizard.save()
            self.assertNotIn('SAVE_CONFIG', [call.args[1]['script'] for call in result.subscription.request.call_args_list])


class ProbeRegressionTests(unittest.TestCase):
    printer = ProbeTests.printer
    status = ProbeTests.status
    started = ProbeTests.started
    def test_pending_mesh_does_not_block_start_or_trigger_save(self):
        result = self.printer()
        self.status(result, False, {'bed_mesh default': {'points': 'old'}})
        result.probe_wizard.start()
        self.assertIn('G1 X125.000 Y130.000', result.sendGCode.call_args.args[0])

    def test_long_probe_start_is_not_failed_after_http_timeout(self):
        result = self.printer()
        future = result.probe_wizard.start()
        started = result.probe_wizard.pending[2]
        with patch.object(probe_wizard.time, 'monotonic', return_value=started+45):
            result.probe_wizard.update()
            self.assertEqual(result.probe_wizard.phase, 'starting')
            future.set_result('ok')
            self.status(result, False)
            result.probe_wizard.update()
            result.probe_wizard.pending[1].set_result('ok')
            self.status(result, True)
            result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'active')

    def test_all_small_and_bracket_steps_dispatch_once(self):
        result = self.started()
        for step in (-.005, .005, -.01, .01, -.05, .05, -.1, .1, -1, 1, '--', '-', '+', '++'):
            before = result.subscription.request.call_count
            future = result.probe_wizard.testz(step)
            token = step if isinstance(step, str) else '{:g}'.format(step)
            self.assertEqual(result.subscription.request.call_args.args[1], {'script': 'TESTZ Z='+token})
            self.assertEqual(result.subscription.request.call_count, before+1)
            future.set_result('ok')
            result.probe_wizard.update()

    def test_compact_ui_shows_four_steps_and_live_bounds_without_waiting_text(self):
        view = display(data())
        view.pd = self.started()
        source = data()
        source['status']['manual_probe'] = {'is_active': True, 'z_position': 2.804,
            'z_position_lower': 2.779, 'z_position_upper': 2.829}
        view.pd.subscription.snapshot.return_value = source
        view.pd.update_variable()
        view.checkkey = view.ProbeWizardID
        view._probe_selection = 1
        self.assertEqual([label for label, _ in view._probe_options()],
                         ['--', '-', '+', '++', 'Cancel', 'Accept'])
        view.Draw_Probe_Wizard()
        labels = [c.args[-1] for c in view.lcd.draw_text.call_args_list]
        for text in ('2.779', '2.804', '2.829', '--', '-', '+', '++', 'Cancel', 'Accept'):
            self.assertIn(text, labels)
        view.Clear_Main_Window = Mock()
        view.Draw_Title = Mock()
        view.lcd.reset_mock()
        future = view.pd.probe_wizard.testz('-')
        view.Draw_Probe_Wizard()
        view.Clear_Main_Window.assert_not_called()
        view.lcd.update.assert_not_called()
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        before = view.pd.subscription.request.call_count
        view.HMI_Probe_Wizard()
        self.assertEqual(view.pd.subscription.request.call_count, before)
        future.set_result('ok')
        source['status']['manual_probe']['z_position'] = 2.79
        view.pd.update_variable()
        view.pd.probe_wizard.update()
        view.Draw_Probe_Wizard()
        view.Clear_Main_Window.assert_not_called()
        view.Draw_Title.assert_not_called()
        labels = [c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('2.790', labels)
        self.assertFalse(any('Waiting' in text or 'TESTZ' in text for text in labels))
        view.lcd.reset_mock()
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view.HMI_Probe_Wizard()
        self.assertEqual(view._probe_selection, 2)
        view.Clear_Main_Window.assert_not_called()
        self.assertEqual([c.args[-1] for c in view.lcd.draw_text.call_args_list], ['-', '+'])


class RepeatedProbeStepTests(unittest.TestCase):
    printer = ProbeTests.printer
    status = ProbeTests.status
    started = ProbeTests.started

    def test_live_position_update_before_dispatch_does_not_reject_testz(self):
        result = self.started()
        future = result.probe_wizard.testz('-')
        guard = result.subscription.request.call_args.kwargs['guard']
        source = result.subscription.snapshot()
        source['status']['gcode_move']['position'][2] -= .025
        result.subscription.snapshot.return_value = source
        self.assertTrue(guard())
        source['status']['manual_probe']['is_active'] = False
        self.assertFalse(guard())

    def test_failed_step_keeps_live_session_without_replay(self):
        from moonraker_client import MoonrakerError
        for active in (True, False):
            result = self.started()
            future = result.probe_wizard.testz('-')
            future.set_exception(MoonrakerError('state changed before dispatch'))
            self.status(result, active)
            result.probe_wizard.update()
            self.assertEqual(result.probe_wizard.phase, 'active' if active else 'error')
            self.assertIsNone(result.probe_wizard.pending)
            self.assertEqual(result.subscription.request.call_count, 2)
            if active:
                result.probe_wizard.update()
                self.assertEqual(result.subscription.request.call_count, 2)
                result.probe_wizard.testz('-')
                self.assertEqual(result.subscription.request.call_count, 3)


class ProbeCenterSafetyTests(unittest.TestCase):
    printer = ProbeTests.printer
    status = ProbeTests.status

    def test_center_accounts_for_probe_offsets_and_dispatch_rechecks_position(self):
        result = self.printer()
        source = data()
        source['settings']['bed_mesh'] = {'mesh_min':[10,20], 'mesh_max':[210,220]}
        source['settings']['bltouch'].update(x_offset=-40, y_offset=-10)
        result.subscription.snapshot.return_value = source; result.update_variable()
        future = result.probe_wizard.start()
        self.assertEqual(result.probe_wizard.center, (150,130))
        self.assertIn('G1 X150.000 Y130.000', result.sendGCode.call_args.args[0])
        future.set_result('ok')
        result.probe_wizard.update()
        self.assertEqual(result.subscription.request.call_count, 0)
        source['status']['toolhead']['position'][:2] = (150,130)
        result.update_variable(); result.probe_wizard.update()
        guard = result.subscription.request.call_args.kwargs['guard']
        self.assertTrue(guard())
        source['status']['toolhead']['position'][0] = 250
        self.assertFalse(guard())

    def test_unreachable_center_sends_no_motion(self):
        result = self.printer(); source = data()
        source['settings']['bltouch']['x_offset'] = -1000
        result.subscription.snapshot.return_value = source; result.update_variable()
        with self.assertRaises(ValueError): result.probe_wizard.start()
        result.subscription.request.assert_not_called()

    def test_failed_homing_never_probes_and_ready_printer_can_retry(self):
        from moonraker_client import MoonrakerError
        result = self.printer(); source = data()
        source['status']['toolhead']['homed_axes'] = ''
        result.subscription.snapshot.return_value = source; result.update_variable()
        result.probe_wizard.start().set_exception(MoonrakerError('homing failed'))
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'error')
        self.assertEqual(result.subscription.request.call_count, 1)
        result.probe_wizard.start()
        self.assertEqual(result.subscription.request.call_args.args[1], {'script':'G28'})
        view = display(data()); view.pd = result
        result.probe_wizard.pending = None; result.probe_wizard.phase = 'error'
        self.assertEqual([label for label,_ in view._probe_options()], ['Retry','Back'])

    def test_homing_completion_requires_referenced_axes_before_center_move(self):
        result = self.printer(); source = data()
        source['status']['toolhead']['homed_axes'] = ''
        result.subscription.snapshot.return_value = source; result.update_variable()
        result.probe_wizard.start().set_result('ok')
        result.probe_wizard.update()
        self.assertEqual(result.subscription.request.call_count, 1)
        source['status']['toolhead']['homed_axes'] = 'xyz'
        result.update_variable(); result.probe_wizard.update()
        self.assertEqual(result.subscription.request.call_count, 1)
        self.assertIn('G1 X125.000 Y130.000', result.sendGCode.call_args.args[0])
        self.assertNotIn('PROBE_CALIBRATE', result.sendGCode.call_args.args[0])


class LevelingNavigationTests(unittest.TestCase):
    def test_probe_navigation_and_return_to_leveling(self):
        view = display(data())
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.checkkey = view.BedMeshMenu
        view._mesh_menu_selection = next(i for i,e in enumerate(view._mesh_menu_entries()) if e[0]=='PROBE')
        view.HMI_Bed_Mesh_Menu()
        self.assertEqual(view.checkkey, view.ProbeWizardID)
        view.pd.subscription.request.assert_not_called()
        view._leave_probe()
        self.assertEqual(view.checkkey, view.BedMeshMenu)
        self.assertEqual(view._mesh_menu_entries()[view._mesh_menu_selection][0], 'PROBE')

    def test_probe_only_printer_has_leveling_without_mesh_options(self):
        source = data()
        source['objects'].remove('bed_mesh')
        view = display(source)
        self.assertIn('LEVEL', [entry[0] for entry in view._home_entries()])
        self.assertEqual([entry[0] for entry in view._mesh_menu_entries()], ['BACK','PROBE'])
        absent = display(snapshot())
        self.assertNotIn('LEVEL', [entry[0] for entry in absent._home_entries()])

class ProbeCenterRestoreTests(unittest.TestCase):
    def setup_printer(self, effects):
        import json
        from moonraker_client import MoonrakerClient
        from test_regressions import backend
        result = ProbeTests.printer(self)
        result.sendGCode = backend.PrinterData.sendGCode.__get__(result)
        opener = Mock()
        opener.open.side_effect = effects
        result.client = MoonrakerClient(opener=opener, timeout=.1)
        self.addCleanup(result.client.close)
        return result, opener

    @staticmethod
    def scripts(opener):
        import json
        return [json.loads(call.args[0].data)['script'] for call in opener.open.call_args_list]

    def test_center_motion_failure_restores_modal_state_without_replay(self):
        from moonraker_client import MoonrakerError
        from test_moonraker_client import response
        result, opener = self.setup_printer([response({'result': 'ok'}),
            response({'error': {'message': 'move rejected'}}), response({'result': 'ok'})])
        future = result.probe_wizard.start()
        with self.assertRaises(MoonrakerError):
            future.result(2)
        result.probe_wizard.update()
        scripts = self.scripts(opener)
        self.assertEqual(len(scripts), 3)
        self.assertTrue(scripts[0].startswith('SAVE_GCODE_STATE NAME='))
        self.assertEqual(scripts[2], 'RESTORE_GCODE_STATE NAME=LCD_PROBE_CENTER MOVE=0')
        self.assertEqual(sum('G1 X125.000 Y130.000' in script for script in scripts), 1)
        self.assertFalse(result.jog_recovery_required)

    def test_save_failure_does_not_mutate_or_require_recovery(self):
        from urllib.error import URLError
        from moonraker_client import MoonrakerError
        result, opener = self.setup_printer([URLError('save failed')])
        future = result.probe_wizard.start()
        with self.assertRaises(MoonrakerError):
            future.result(2)
        result.probe_wizard.update()
        self.assertEqual(len(self.scripts(opener)), 1)
        self.assertFalse(result.jog_recovery_required)

    def test_failed_restore_requires_explicit_recovery(self):
        from urllib.error import URLError
        from moonraker_client import MoonrakerError
        from test_moonraker_client import response
        result, opener = self.setup_printer([response({'result': 'ok'}),
            URLError('move failed'), URLError('restore failed'), response({'result': 'ok'})])
        future = result.probe_wizard.start()
        with self.assertRaises(MoonrakerError):
            future.result(2)
        result.probe_wizard.update()
        self.assertTrue(result.jog_recovery_required)
        self.assertIn('Recovery', result.probe_wizard.message)
        self.assertEqual(len(self.scripts(opener)), 3)
        result.restore_jog_state().result(2)
        self.assertFalse(result.jog_recovery_required)
        self.assertEqual(len(self.scripts(opener)), 4)

    def test_epoch_change_never_restores_to_different_connection(self):
        from urllib.error import URLError
        from moonraker_client import MoonrakerError
        from test_moonraker_client import response
        result, opener = self.setup_printer([])
        count = 0
        def respond(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 1:
                return response({'result': 'ok'})
            source = data()
            source['epoch'] = 2
            result.subscription.snapshot.return_value = source
            raise URLError('disconnected')
        opener.open.side_effect = respond
        future = result.probe_wizard.start()
        with self.assertRaises(MoonrakerError):
            future.result(2)
        result.probe_wizard.update()
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(result.jog_recovery_required)

