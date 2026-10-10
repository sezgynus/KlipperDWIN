from concurrent.futures import Future
import unittest
from unittest.mock import ANY, patch

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
        result.sendGCode.side_effect = lambda *a, **k: Future()
        return result

    def status(self, result, active, pending=None):
        source = data()
        source['status']['manual_probe']['is_active'] = active
        if pending is not None:
            source['status']['configfile'] = dict(save_config_pending=bool(pending), save_config_pending_items=pending)
        result.subscription.snapshot.return_value = source
        result.update_variable()

    def started(self):
        result = self.printer()
        future = result.probe_wizard.start()
        future.set_result('ok')
        self.status(result, True)
        result.probe_wizard.update()
        return result

    def test_start_requires_homing_and_never_auto_homes_or_moves_z_zero(self):
        result = self.printer()
        future = result.probe_wizard.start()
        result.sendGCode.assert_called_once_with('PROBE_CALIBRATE', dispatch_guard=ANY)
        self.assertEqual(result.probe_wizard.phase, 'starting')
        future.set_result('ok')
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'starting')
        self.status(result, True)
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'active')
        blocked = self.printer()
        source = data()
        source['status']['toolhead']['homed_axes'] = 'xy'
        blocked.subscription.snapshot.return_value = source
        blocked.update_variable()
        with self.assertRaises(ValueError):
            blocked.probe_wizard.start()
        blocked.sendGCode.assert_not_called()

    def test_testz_requires_owned_session_and_serializes_steps(self):
        result = self.printer()
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(-.01)
        result = self.started()
        future = result.probe_wizard.testz(-.01)
        self.assertEqual(result.sendGCode.call_args.args[0], 'TESTZ Z=-0.01')
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
        self.assertNotIn('SAVE_CONFIG', [call.args[0] for call in result.sendGCode.call_args_list])
        result.probe_wizard.save()
        self.assertEqual(result.sendGCode.call_args.args[0], 'SAVE_CONFIG')

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
        self.assertEqual(result.sendGCode.call_args.args[0], 'ABORT')

    def test_external_session_existing_changes_and_print_block_start(self):
        for active, pending, state in ((True, {}, 'standby'), (False, {'extruder': {'pid_kp': '1'}}, 'standby'), (False, {}, 'printing')):
            result = self.printer()
            source = data()
            source['status']['manual_probe']['is_active'] = active
            source['status']['configfile']['save_config_pending'] = bool(pending)
            source['status']['print_stats']['state'] = state
            result.subscription.snapshot.return_value = source
            result.update_variable()
            with self.assertRaises(ValueError):
                result.probe_wizard.start()
            result.sendGCode.assert_not_called()

    def test_epoch_change_does_not_replay_commands(self):
        result = self.started()
        source = data()
        source['epoch'] = 2
        result.subscription.snapshot.return_value = source
        result.update_variable()
        result.probe_wizard.update()
        self.assertEqual(result.probe_wizard.phase, 'interrupted')
        result.sendGCode.assert_called_once()
        with self.assertRaises(ValueError):
            result.probe_wizard.testz(.1)

    def test_ui_offers_probe_separately_from_runtime_offset(self):
        result = display(data())
        self.assertIn('PROBE', [item[0] for item in result._menus['control']])
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
            self.assertNotIn('SAVE_CONFIG', [call.args[0] for call in result.sendGCode.call_args_list])
