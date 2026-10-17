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
        # A lightweight fake supplies mutable phase for UI-navigation tests.
        # The real controller exposes phase as a read-only property.
        d.pd.maintenance_pulse = SimpleNamespace(phase=None, pending=False)
        d.get_encoder_state = Mock()
        d.Draw_Maintenance_Menu()
        d.pd.client.get.reset_mock()
        return d

    def event(self, d, event):
        d.get_encoder_state.return_value = event
        d.HMI_Maintenance_Menu()

    def test_r02_result_does_not_report_petrel_derived_peak_as_shaper(self):
        d=self.setup_view()
        d._maintenance_page='result'
        d._maintenance_result=SimpleNamespace(
            feature_id='R02',status='PASSED',
            reason='klipper_resonance_psd_recorded_no_petrel_rating',
            evidence=(('axis','X'),('data','Klipper PSD recorded'),
                      ('next','Run R04 for Klipper fit')))
        title,rows=d._maintenance_rows()
        labels=[item[0] for item in rows]
        self.assertEqual(title,'Klipper PSD captured')
        self.assertIn('Run R04 for Klipper fit',labels)
        self.assertNotIn('peak_hz',str(labels))
        d.pd.client.get.assert_not_called()

    def test_r04_result_shows_only_native_klipper_recommendation(self):
        d=self.setup_view()
        d._maintenance_page='result'
        d._maintenance_result=SimpleNamespace(
            feature_id='R04',status='OBSERVED',
            reason='klipper_shaper_recommendation_not_saved',
            evidence=(('axis','x'),('shaper','mzv'),
                      ('frequency_hz',34.6),('saved',False)))
        title,rows=d._maintenance_rows()
        self.assertEqual(title,'Klipper recommendation')
        self.assertEqual([r[0] for r in rows],[
            'Back','Axis X','Shaper: mzv','Frequency: 34.6 Hz',
            'Klipper suggested values','Live shaper may change',
            'Not saved to printer.cfg'])
        d.pd.client.get.assert_not_called()

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

    def test_confirmation_label_describes_active_test_not_everything_as_pulse(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'await_confirmation'
        for feature, expected in (
                ('F01', 'Run short pulse'),
                ('F02', 'Run speed steps'),
                ('O03', 'Run short pulse'),
                ('O04', 'Run color sequence'),
                ('S18', 'Run short pulse')):
            with self.subTest(feature=feature):
                d.pd.maintenance_pulse.feature_id = feature
                title, entries = d._maintenance_rows()
                self.assertEqual(title, 'Confirm test')
                self.assertEqual(entries[0][0], 'Cancel')
                self.assertEqual(entries[1][0], expected)
                self.assertLessEqual(len(entries[1][0]), 26)
        # The label must not trigger a second confirmation on its own.
        d.pd.client.get.assert_not_called()

    def test_grouped_thermal_row_and_seven_read_only_results(self):
        d = self.setup_view()
        d._maintenance_page = 'tests'
        plan = (SimpleNamespace(feature_id='H01',device='extruder'),
                SimpleNamespace(feature_id='H03',device='heater_bed'))
        d.pd.maintenance_guided_plan = Mock(return_value=plan)
        title, rows = d._maintenance_rows()
        self.assertEqual(title, 'Self Tests')
        self.assertEqual(rows[1][0], 'Thermal extruder')
        self.assertEqual(rows[2][0], 'H03 heater_bed')
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'await_confirmation'
        d.pd.maintenance_pulse.feature_id = 'H01'
        d.pd.maintenance_pulse.live_text = ('Target 60.0 C',)
        title, rows = d._maintenance_rows()
        self.assertEqual(title, 'Confirm thermal group')
        self.assertEqual(rows[1][0], 'Run 7 thermal checks')
        children = tuple(SimpleNamespace(feature_id=f,status='PASSED_USER',
                             evidence=((metric,1.2),))
            for f, metric in (('H01','rise_c'),('H05','heating_c_per_s'),
                              ('H06','time_to_target_s'),('H07','overshoot_c'),
                              ('H08','stability_peak_to_peak_c'),
                              ('H09','cooling_c_per_s'),('H13','rise_c')))
        d._maintenance_result = SimpleNamespace(
            status='PASSED_USER',reason='thermal_group_seven_independent_results',
            components=children,evidence=())
        d._maintenance_page = 'result'
        title, rows = d._maintenance_rows()
        self.assertEqual(title,'Result')
        self.assertEqual(len([row for row in rows if 'PASSED_USER' in row[0]]),8)
        for f in ('H01','H05','H06','H07','H08','H09','H13'):
            self.assertTrue(any(row[0].startswith(f+' PASSED_USER') for row in rows))

    def test_new_auxiliary_controllers_use_their_own_live_confirmation(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'await_confirmation'
        d.pd.maintenance_pulse.live_text = ('Declared safe operation',)
        for feature in ('O01','O02','O06'):
            d.pd.maintenance_pulse.feature_id = feature
            title,entries = d._maintenance_rows()
            self.assertEqual(title,'Confirm '+feature)
            self.assertEqual(entries[1][0],'Start firmware workflow')
            self.assertIn('Declared safe operation',[row[0] for row in entries])
        d.pd.client.get.assert_not_called()

    def test_s18_ui_uses_backend_profile_instead_of_panel_buzzer(self):
        d = self.setup_view()
        row = SimpleNamespace(feature_id='S18', device='pwm_cycle_time alert')
        d.pd.maintenance_guided_plan = Mock(return_value=(row,))
        d.pd.start_maintenance_physical = Mock(return_value=(True, 'queued'))
        d._buzzer_settings = Mock(side_effect=AssertionError('Must not use DWIN buzzer'))
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.event(d, d.ENCODER_DIFF_CW)
        self.event(d, d.ENCODER_DIFF_ENTER)
        d.pd.start_maintenance_physical.assert_called_once_with('S18', 'pwm_cycle_time alert')
        d._buzzer_settings.assert_not_called()

    def test_thermal_confirmation_refresh_is_one_click_and_clear_ui(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        owner = SimpleNamespace(
            phase='await_confirmation', pending=True, feature_id='H01',
            live_text=('Target 60.0 C',), refreshing_consent=False)
        d.pd.maintenance_pulse = owner
        confirmations = []
        def confirm():
            confirmations.append('operator_click')
            owner.phase = 'preflight'
            owner.refreshing_consent = True
            return True, 'thermal_confirmation_safety_refresh'
        d.pd.confirm_maintenance_physical = Mock(side_effect=confirm)
        d._maintenance_selection = 1
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.assertEqual(confirmations, ['operator_click'])
        self.assertEqual(d._maintenance_page, 'pulse')
        title, entries = d._maintenance_rows()
        self.assertEqual(title, 'Refreshing HEAT safety')
        self.assertEqual(entries[0][0], 'Cancel safety checks')
        self.assertEqual([r[0] for r in entries[1:]], ['Target 60.0 C'])
        d.pd.poll_maintenance_physical = Mock(return_value=None)
        owner.phase = 'running'
        owner.refreshing_consent = False
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page, 'pulse')
        self.assertEqual(confirmations, ['operator_click'])
        self.assertEqual(d._maintenance_rows()[0], 'Thermal test')

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


    def test_f12_stage_selection_immediately_shows_stop_confirmation(self):
        # An F12 choice advances the controller to a new nonterminal phase
        # without an outcome. Redraw must not depend on encoder rotation.
        for selected in (0, 1, 4, 5):
            with self.subTest(selected=selected):
                d = self.setup_view()
                d._maintenance_page = 'pulse'
                d._maintenance_selection = selected
                pulse = d.pd.maintenance_pulse
                pulse.feature_id = 'F12'
                pulse.phase = 'await_observation'
                pulse.pwm_levels = (25, 50, 76, 101, 127)
                def observe(choice):
                    self.assertEqual(choice, selected)
                    pulse.phase = 'f12_await_stop'
                    return None
                d.pd.observe_maintenance_physical = Mock(side_effect=observe)
                d.Draw_Maintenance_Menu = Mock(
                    wraps=d.Draw_Maintenance_Menu)
                d.lcd.update = Mock(wraps=d.lcd.update)
                self.event(d, d.ENCODER_DIFF_ENTER)
                d.pd.observe_maintenance_physical.assert_called_once_with(selected)
                self.assertEqual(d._maintenance_page, 'pulse')
                self.assertEqual(pulse.phase, 'f12_await_stop')
                self.assertEqual(d._maintenance_selection, 0)
                self.assertEqual(d._maintenance_rows()[0], 'Fan fully stopped?')
                d.Draw_Maintenance_Menu.assert_called_once_with()
                d.lcd.update.assert_called_once_with()
                d.pd.client.get.assert_not_called()

    def test_invalid_observation_does_not_trigger_extra_redraw(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d._maintenance_selection = 1
        pulse = d.pd.maintenance_pulse
        pulse.feature_id = 'F12'
        pulse.phase = 'await_observation'
        pulse.pwm_levels = (25, 50, 76, 101, 127)
        d.pd.observe_maintenance_physical = Mock(return_value=None)
        d.Draw_Maintenance_Menu = Mock(wraps=d.Draw_Maintenance_Menu)
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.assertEqual(pulse.phase, 'await_observation')
        self.assertEqual(d._maintenance_selection, 1)
        d.Draw_Maintenance_Menu.assert_not_called()

    def test_diagnostic_result_renders_bounded_observed_values(self):
        d = self.setup_view()
        d._maintenance_page = 'reading'
        d.pd.poll_maintenance_read = Mock(return_value=SimpleNamespace(
            status=None, reason='observed_information',
            evidence=(('cpu_temp_c', 52.5), ('memory.total', 1024))))
        d._poll_maintenance_ui()
        self.assertEqual(d._maintenance_page, 'result')
        title, entries = d._maintenance_rows()
        self.assertEqual(title, 'Result')
        self.assertIn('OBSERVED', [e[0] for e in entries])
        self.assertIn('cpu_temp_c: 52.5', [e[0] for e in entries])
        self.assertIn('memory.total: 1024', [e[0] for e in entries])

    def test_guided_observation_question_is_visible_in_title(self):
        d = self.setup_view()
        d._maintenance_page = 'pulse'
        d.pd.maintenance_pulse.phase = 'await_observation'
        d.pd.maintenance_pulse.observation_prompt = 'Did the part fan rotate?'
        self.assertEqual(d._maintenance_rows()[0], 'Did the part fan rotate?')

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

    def test_self_test_result_back_returns_to_selected_test_instead_of_root(self):
        for mode in ('blocked', 'completed', 'cancelled'):
            with self.subTest(mode=mode):
                d = self.setup_view()
                row = SimpleNamespace(feature_id='F01', device='fan')
                d.pd.maintenance_guided_plan = Mock(return_value=(row,))
                d.pd.start_maintenance_physical = Mock(
                    return_value=((False, 'unsafe') if mode == 'blocked'
                                  else (True, 'preflight_queued')))
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'tests')
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_ENTER)
                if mode == 'completed':
                    d.pd.poll_maintenance_physical = Mock(return_value=SimpleNamespace(
                        status='PASSED_USER', reason='explicit_user_observation'))
                    d._poll_maintenance_ui()
                elif mode == 'cancelled':
                    d.pd.maintenance_pulse.phase = 'await_confirmation'
                    d.pd.cancel_maintenance_physical = Mock(
                        return_value=SimpleNamespace(
                            status='ABORTED', reason='user_cancelled'))
                    self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'result')
                self.assertEqual(d._maintenance_selection, 0)
                self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'tests')
                self.assertEqual(d._maintenance_selection, 1)
                self.assertEqual(d._maintenance_rows()[0], 'Self Tests')
                d.pd.start_maintenance_physical.assert_called_once_with(
                    'F01', 'fan')
                d.pd.client.get.assert_not_called()

    def test_diagnostics_result_back_returns_to_selected_diagnostic(self):
        for mode in ('blocked', 'completed', 'cancelled'):
            with self.subTest(mode=mode):
                d = self.setup_view()
                rows = (SimpleNamespace(feature_id='S01'),
                        SimpleNamespace(feature_id='S02'))
                d.pd.maintenance_read_plan = Mock(return_value=rows)
                d.pd.start_maintenance_read = Mock(
                    return_value=((False, 'read_unavailable')
                                  if mode == 'blocked' else (True, 'queued')))
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'diagnostics')
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_CW)
                self.event(d, d.ENCODER_DIFF_ENTER)
                if mode == 'completed':
                    d.pd.poll_maintenance_read = Mock(return_value=SimpleNamespace(
                        status='OBSERVED', reason='observed_information', evidence=()))
                    d._poll_maintenance_ui()
                elif mode == 'cancelled':
                    d.pd.cancel_maintenance_read = Mock(return_value=SimpleNamespace(
                        status='ABORTED', reason='user_cancelled'))
                    self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'result')
                self.event(d, d.ENCODER_DIFF_ENTER)
                self.assertEqual(d._maintenance_page, 'diagnostics')
                self.assertEqual(d._maintenance_selection, 2)
                self.assertEqual(d._maintenance_rows()[0], 'Diagnostics')
                d.pd.start_maintenance_read.assert_called_once_with('S02')
                d.pd.client.get.assert_not_called()

    def test_result_without_known_origin_falls_back_to_maintenance_root(self):
        d = self.setup_view()
        d._maintenance_page = 'result'
        d._maintenance_result = SimpleNamespace(
            status='BLOCKED', reason='unknown')
        self.event(d, d.ENCODER_DIFF_ENTER)
        self.assertEqual(d._maintenance_page, 'root')
        self.assertEqual(d._maintenance_selection, 0)

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


    def test_motion_confirmation_information_rows_do_not_cancel_or_dispatch(self):
        d=self.setup_view()
        d._maintenance_page='pulse'
        d.pd.maintenance_pulse=SimpleNamespace(
            phase='await_confirmation',pending=True,feature_id='M05',
            live_text=('X +1 mm','Clear travel path'),returning=False)
        d.pd.confirm_maintenance_physical=Mock()
        d.pd.cancel_maintenance_physical=Mock()
        d._maintenance_selection=2
        self.event(d,d.ENCODER_DIFF_ENTER)
        d.pd.confirm_maintenance_physical.assert_not_called()
        d.pd.cancel_maintenance_physical.assert_not_called()
        self.assertEqual(d._maintenance_page,'pulse')

    def test_external_measurement_editor_redraws_and_requires_return_preflight(self):
        d=self.setup_view()
        d._maintenance_page='pulse'
        owner=SimpleNamespace(phase='await_measurement',pending=True,
            feature_id='M06',measurement_value=10.,live_text=(),returning=False)
        owner.begin_measurement=Mock(side_effect=lambda:setattr(owner,'phase','measurement_edit'))
        def adjust(delta):
            owner.measurement_value+=delta
        owner.adjust_measurement=Mock(side_effect=adjust)
        def record(value):
            owner.phase='preflight'
            return True,'return_preflight_queued'
        owner.record_measurement=Mock(side_effect=record)
        d.pd.maintenance_pulse=owner
        d._maintenance_selection=1
        self.event(d,d.ENCODER_DIFF_ENTER)
        self.assertEqual(owner.phase,'measurement_edit')
        self.assertEqual(d._maintenance_rows()[0],'Actual measured mm')
        d._menu_batch_steps=2
        self.event(d,d.ENCODER_DIFF_CW)
        self.assertAlmostEqual(owner.measurement_value,10.02)
        self.event(d,d.ENCODER_DIFF_ENTER)
        owner.record_measurement.assert_called_once_with(owner.measurement_value)
        self.assertEqual(owner.phase,'preflight')
        self.assertEqual(d._maintenance_page,'pulse')


if __name__ == '__main__':
    unittest.main()
