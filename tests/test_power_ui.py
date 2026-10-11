import unittest
from unittest.mock import Mock

from test_capabilities import display, snapshot


class PowerUITests(unittest.TestCase):
    def view(self):
        result = display(snapshot())
        result._power_focus = False
        result._power_origin = None
        result._power_confirm_yes = True
        result.pd.power_off_if_on = Mock()
        return result

    def test_counterclockwise_from_first_item_focuses_global_power_icon(self):
        result = self.view()
        result.checkkey = result.Prepare
        result.select_prepare.reset()
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CCW)
        self.assertTrue(result._handle_power_navigation())
        self.assertTrue(result._power_focus)
        result.lcd.show_icon.assert_called_with(7, 107, 244, 5)

    def test_power_press_opens_confirmation_with_yes_selected_by_default(self):
        result = self.view()
        result.checkkey = result.Control
        result._power_focus = True
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        self.assertTrue(result._handle_power_navigation())
        self.assertEqual(result.checkkey, result.PowerConfirm)
        self.assertEqual(result._power_origin, result.Control)
        self.assertTrue(result._power_confirm_yes)
        result.pd.power_off_if_on.assert_not_called()

    def test_confirmation_yes_powers_off_and_no_restores_origin(self):
        result = self.view()
        result.checkkey = result.PowerConfirm
        result._power_origin = result.MainMenu
        result._power_confirm_yes = True
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result._show_message = Mock()
        result._handle_power_navigation()
        result.pd.power_off_if_on.assert_called_once_with()
        result._show_message.assert_called_once_with('Powering off...')

        result = self.view()
        result.checkkey = result.PowerConfirm
        result._power_origin = result.MainMenu
        result._power_confirm_yes = False
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.Goto_MainMenu = Mock()
        result._handle_power_navigation()
        result.pd.power_off_if_on.assert_not_called()
        result.Goto_MainMenu.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
