import unittest
from concurrent.futures import Future
from unittest.mock import Mock
from test_capabilities import display, snapshot
from ui_events import InputEvent

class CaseLightLiveTests(unittest.TestCase):
    def make(self):
        data = snapshot()
        data['objects'].append('output_pin case_light')
        data['settings']['output_pin case_light'] = {'pwm': True}
        data['status']['output_pin case_light'] = {'value': 0.25}
        view = display(data)
        view.checkkey = view.CaseLightBrightness
        view._case_light_on = True
        view._case_light_brightness = 25
        view._case_light_brightness_target = 25
        view._encoder_move_value = 1
        view.get_encoder_state = Mock()
        view._action = Mock()
        view.pd.set_case_light_brightness = Mock()
        view.Draw_Case_Light_Menu = Mock()
        return view, data

    def step(self, view, event):
        view.get_encoder_state.return_value = event
        view.HMI_Case_Light_Brightness()

    def test_live_set_is_silent_and_retains_latest_pending_value(self):
        view, _ = self.make(); first = Future(); last = Future()
        view.pd.set_case_light_brightness.side_effect = [first, last]
        self.step(view, view.ENCODER_DIFF_CW)
        view.pd.set_case_light_brightness.assert_called_once_with(26)
        for _ in range(9): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._case_light_brightness_target, 35)
        self.assertEqual(view.pd.set_case_light_brightness.call_count, 1)
        first.set_result({}); view._poll_case_light_live()
        view.pd.set_case_light_brightness.assert_called_with(35)
        view._action.assert_not_called()

    def test_pin_response_does_not_replace_edit_draft_and_exit_reads_actual_value(self):
        view, data = self.make()
        data['status']['output_pin case_light']['value'] = 0.8
        view._poll_case_light_state()
        self.assertEqual(view._case_light_brightness_target, 25)
        view.Draw_Case_Light_Menu.assert_not_called()
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._case_light_brightness, 80)
        view.Draw_Case_Light_Menu.assert_called()

    def test_reconnect_discards_unsent_value(self):
        view, _ = self.make(); future = Future()
        view.pd.set_case_light_brightness.return_value = future
        self.step(view, view.ENCODER_DIFF_CW); self.step(view, view.ENCODER_DIFF_CW)
        view._uart_epoch = 1; view._poll_case_light_live()
        self.assertIsNone(view._case_light_live_pending)
        self.assertEqual(view.pd.set_case_light_brightness.call_count, 1)

    def test_coalesced_input_draws_once_without_acceleration(self):
        view, _ = self.make()
        view._closed = False; view._uart_online = True; view._uart_epoch = 0
        view._sync_input_state = Mock(return_value=True)
        view.get_encoder_state = lambda: view._encoder_event
        view.pd.set_case_light_brightness.return_value = Future()
        view._process_input(InputEvent('rotate', -12, 1, 0, -120, 100))
        self.assertEqual(view._case_light_brightness_target, 37)
        view.lcd.draw_integer_text.assert_called_once()
        view.pd.set_case_light_brightness.assert_called_once_with(37)

    def test_backend_set_pin_uses_websocket_and_scale(self):
        view, data = self.make()
        del view.pd.set_case_light_brightness
        view.pd.sendGCodeObserved = Mock()
        view.pd.set_case_light_brightness(37)
        view.pd.sendGCodeObserved.assert_called_once_with('SET_PIN PIN=case_light VALUE=0.370000')
        data['settings']['output_pin case_light']['scale'] = 255
        view.pd.set_case_light_brightness(100)
        view.pd.sendGCodeObserved.assert_called_with('SET_PIN PIN=case_light VALUE=255.000000')
        with self.assertRaises(ValueError): view.pd.set_case_light_brightness(101)

    def test_menu_tracking_stops_on_exit_and_does_not_repeat(self):
        view, _ = self.make()
        view._sync_case_light_tracking(); view._sync_case_light_tracking()
        view.pd.subscription.set_case_light_tracking.assert_called_once_with(True, None)
        view.checkkey = view.Control; view._sync_case_light_tracking()
        view.pd.subscription.set_case_light_tracking.assert_called_with(False, None)
        view.pd.subscription.reset_mock()
        view._poll_case_light_state()
        view.pd.subscription.snapshot.assert_not_called()

    def test_macro_alone_does_not_enable_menu(self):
        data = snapshot(); data['objects'].append('gcode_macro M355')
        view = display(data)
        self.assertNotIn('LIGHT', [e[0] for e in view._menus['control']])

    def test_toggle_restores_last_positive_value_silently(self):
        view, data = self.make(); view.checkkey = view.CaseLight
        view._poll_case_light_state(); view.select_light.set(1)
        view.get_encoder_state.return_value = view.ENCODER_DIFF_ENTER
        view.HMI_Case_Light()
        view.pd.set_case_light_brightness.assert_called_with(0)
        data['status']['output_pin case_light']['value'] = 0
        view._poll_case_light_state(); view.HMI_Case_Light()
        view.pd.set_case_light_brightness.assert_called_with(25)
        view._action.assert_not_called()
