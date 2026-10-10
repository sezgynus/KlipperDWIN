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
        view.pd.sendGCodeObserved = Mock()
        view.Draw_Case_Light_Menu = Mock()
        return view

    def step(self, view, event):
        view.get_encoder_state.return_value = event
        view.HMI_Case_Light_Brightness()

    def test_live_set_is_silent_and_query_waits_for_final_command(self):
        view = self.make(); first = Future(); last = Future()
        view.pd.sendGCodeObserved.side_effect = [first, last]
        self.step(view, view.ENCODER_DIFF_CW)
        view.pd.sendGCodeObserved.assert_called_once_with('M355 P66')
        for _ in range(9): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._case_light_brightness_target, 35)
        self.assertEqual(view.pd.sendGCodeObserved.call_count, 1)
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.pd.query_case_light.assert_not_called()
        first.set_result({}); view._poll_case_light_live()
        view.pd.sendGCodeObserved.assert_called_with('M355 P89')
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
        view.pd.sendGCodeObserved.return_value = future
        self.step(view, view.ENCODER_DIFF_CW)
        self.step(view, view.ENCODER_DIFF_CW)
        view._uart_epoch = 1
        view._poll_case_light_live()
        self.assertIsNone(view._case_light_live_pending)
        self.assertEqual(view.pd.sendGCodeObserved.call_count, 1)

    def test_external_state_is_polled_only_outside_editor(self):
        view = self.make(); view._poll_case_light_live()
        view.pd.query_case_light.assert_not_called()
        view.checkkey = view.CaseLight; view._poll_case_light_live()
        view.pd.query_case_light.assert_called_once_with(report_error=False)

    def test_coalesced_input_draws_once_and_preserves_one_percent_per_detent(self):
        from ui_events import InputEvent
        view = self.make()
        view._closed = False; view._uart_online = True; view._uart_epoch = 0
        view._sync_input_state = Mock(return_value=True)
        view.get_encoder_state = lambda: view._encoder_event
        view.pd.sendGCodeObserved = Mock(return_value=Future())
        view._process_input(InputEvent('rotate', -12, 1, 0, -120, 100))
        self.assertEqual(view._case_light_brightness_target, 37)
        view.lcd.draw_integer_text.assert_called_once()
        view.pd.sendGCodeObserved.assert_called_once_with('M355 P94')
        view._process_input(InputEvent('rotate', 7, 1, 0, 70, 100))
        self.assertEqual(view._case_light_brightness_target, 30)
        self.assertEqual(view.lcd.draw_integer_text.call_count, 2)

    def test_quiet_query_uses_same_websocket_as_brightness(self):
        view = self.make()
        view.pd.clear_gcode_responses = Mock()
        view.pd.sendGCodeObserved = Mock()
        # Query the real backend method rather than the UI fixture mock.
        from printerInterface import PrinterData
        PrinterData.query_case_light(view.pd, report_error=False)
        view.pd.clear_gcode_responses.assert_called_once()
        view.pd.sendGCodeObserved.assert_called_once_with('M355')
        view.pd.sendGCode.assert_not_called()
