"""Maintenance UI is opt-in: confirmations, cancellation and observations."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from test_capabilities import display, snapshot


class MaintenanceUIFlows(unittest.TestCase):
    def setup_view(self):
        d = display(snapshot())
        d.checkkey = d.MaintenanceMenu
        d._maintenance_page = 'root'
        d._maintenance_selection = 0
        d.get_encoder_state = Mock()
        d.Draw_Maintenance_Menu()
        d.pd.client.get.reset_mock()
        return d

    def event(self, d, event):
        d.get_encoder_state.return_value = event
        d.HMI_Maintenance_Menu()

    def test_entry_has_no_io_or_actuation(self):
        d = self.setup_view()
        self.assertEqual(d._maintenance_rows()[0], 'Maintenance')
        self.assertEqual(d._maintenance_page, 'root')
        d.pd.client.get.assert_not_called()
        self.assertFalse(d.pd.maintenance_pulse.pending)

    def test_test_menu_only_dispatches_after_explicit_second_choice(self):
        d = self.setup_view()
        row = SimpleNamespace(feature_id='F01', device='fan')
        d.pd.maintenance_guided_plan = Mock(return_value=(row,))
        d.pd.start_maintenance_physical = Mock(return_value=(True, 'queued'))
        d.pd.confirm_maintenance_physical = Mock(return_value=(True, 'queued'))
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.assertEqual(d._maintenance_page, 'tests')
        self.assertEqual(d.pd.start_maintenance_physical.call_count, 0)
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        d.pd.start_maintenance_physical.assert_called_once_with('F01', 'fan')
        self.assertEqual(d._maintenance_page, 'pulse')
        d.pd.maintenance_pulse.phase = 'await_confirmation'
        d.Draw_Maintenance_Menu()
        self.assertEqual(d._maintenance_selection, 0)
        d.pd.confirm_maintenance_physical.assert_not_called()
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        d.pd.confirm_maintenance_physical.assert_called_once_with()

    def test_confirm_default_is_cancel_and_result_not_auto_pass(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'await_confirmation'
        d.pd.cancel_maintenance_physical = Mock(return_value=SimpleNamespace(
            status='ABORTED', reason='cancelled'))
        self.event(d, d.ENCODER_DIFF_ENTER)
        d.pd.cancel_maintenance_physical.assert_called_once_with()
        self.assertEqual(d._maintenance_page, 'result')
        self.assertEqual(d._maintenance_result.status, 'ABORTED')

    def test_user_reports_yes_no_only_after_restore(self):
        for choice, expected in ((0, False), (1, True)):
            with self.subTest(choice=choice):
                d = self.setup_view()
                d._maintenance_page = 'pulse'
                d.pd.maintenance_pulse.phase = 'await_observation'
                d._maintenance_selection = choice
                d.pd.observe_maintenance_physical = Mock(
                    return_value=SimpleNamespace(
                        status='PASSED_USER' if choice else 'FAILED_USER',
                        reason='explicit_user_observation'))
                self.event(d, d.ENCODER_DIFF_ENTER)
                d.pd.observe_maintenance_physical.assert_called_once_with(expected)
                self.assertEqual(d._maintenance_page, 'result')

    def test_navigation_and_diagnostics_are_passive_until_selection(self):
        d = self.setup_view()
        d.pd.maintenance_read_plan = Mock(return_value=(
            SimpleNamespace(feature_id='S01'),))
        d.pd.start_maintenance_read = Mock(return_value=(True, 'queued'))
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.assertEqual(d._maintenance_page, 'diagnostics')
        d.pd.start_maintenance_read.assert_not_called()
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        d.pd.start_maintenance_read.assert_called_once_with('S01')
        self.assertEqual(d._maintenance_page, 'reading')

    def test_background_poll_updates_only_selected_maintenance_view(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'running'
        d.pd.poll_maintenance_physical = Mock(return_value=None)
        d._poll_maintenance_ui()
        d.pd.poll_maintenance_physical.assert_called_once_with()
        d.pd.maintenance_pulse.phase = 'await_observation'
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_selection, 0)
        d.pd.poll_maintenance_physical = Mock(return_value=SimpleNamespace(
            status='INCONCLUSIVE', reason='restore_not_verified'))
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page, 'result')
        self.assertEqual(d._maintenance_result.status, 'INCONCLUSIVE')


if __name__ == '__main__':
    unittest.main()
