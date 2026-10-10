import unittest
from concurrent.futures import Future
from unittest.mock import Mock
from test_capabilities import display, snapshot

class CaseLightLiveTests(unittest.TestCase):
    def make(self):
        view = display(snapshot())
        view.checkkey = view.CaseLightBrightness
        view._case_light_brightness = 25
        view._case_light_brightness_target = 25
        view._encoder_move_value = 1
        view.get_encoder_state = Mock()
        view._action = Mock()
        view.pd.query_case_light = Mock()
        view.Draw_Case_Light_Menu = Mock()
        return view

    def step(self, view, event):
        view.get_encoder_state.return_value = event
        view.HMI_Case_Light_Brightness()

    def test_live_set_is_silent_and_query_waits_for_final_command(self):
        view = self.make(); first = Future(); last = Future()
        view.pd.sendGCode.side_effect = [first, last]
        self.step(view, view.ENCODER_DIFF_CW)
        view.pd.sendGCode.assert_called_once_with('M355 P66', report_error=False)
        for _ in range(9): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._case_light_brightness_target, 35)
        self.assertEqual(view.pd.sendGCode.call_count, 1)
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.pd.query_case_light.assert_not_called()
        first.set_result({}); view._poll_case_light_live()
        view.pd.sendGCode.assert_called_with('M355 P89', report_error=False)
        view.pd.query_case_light.assert_not_called()
        last.set_result({}); view._poll_case_light_live()
        view.pd.query_case_light.assert_called_once_with(report_error=False)
        view._action.assert_not_called()

    def test_m355_response_does_not_replace_edit_draft(self):
        view = self.make(); view._case_light_query_pending = True
        view.pd.pop_gcode_response = Mock(return_value='Light is ON, Brightness=255')
        view._poll_case_light_query()
        self.assertEqual(view._case_light_brightness_target, 25)
        view.Draw_Case_Light_Menu.assert_not_called()
        self.step(view, view.ENCODER_DIFF_ENTER)
        view._poll_case_light_query()
        self.assertEqual(view._case_light_brightness, 100)
        view.Draw_Case_Light_Menu.assert_called()

    def test_reconnect_discards_unsent_value(self):
        view = self.make(); future = Future()
        view.pd.sendGCode.return_value = future
        self.step(view, view.ENCODER_DIFF_CW)
        self.step(view, view.ENCODER_DIFF_CW)
        view._uart_epoch = 1
        view._poll_case_light_live()
        self.assertIsNone(view._case_light_live_pending)
        self.assertEqual(view.pd.sendGCode.call_count, 1)

    def test_external_state_is_polled_only_outside_editor(self):
        view = self.make(); view._poll_case_light_live()
        view.pd.query_case_light.assert_not_called()
        view.checkkey = view.CaseLight; view._poll_case_light_live()
        view.pd.query_case_light.assert_called_once_with(report_error=False)
