from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from test_capabilities import display, snapshot
from test_t5uic1_driver import driver as raw_driver


def driver():
    lcd = raw_driver()
    return lcd


class HomingPopupTests(unittest.TestCase):
    def test_home_click_draws_text_and_dispatches_once_before_confirmation(self):
        view = display(snapshot())
        view.lcd = driver()
        view.checkkey = view.Prepare
        view.select_prepare.set(view.PREPARE_CASE_HOME)
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view._menu_navigation = Mock(return_value=False)
        future = Future()
        view.pd.sendGCodeObserved = Mock(return_value=future)
        view.pd.ishomed = Mock(return_value=False)
        view.Draw_Prepare_Menu = Mock()
        view.HMI_Prepare()
        view.pd.sendGCodeObserved.assert_called_once_with('G28')
        self.assertTrue(any(b'Homing XYZ' in frame for frame in view.lcd.serial.frames))
        self.assertEqual(view.lcd.serial.frames[-1][1], 0x3D)
        self.assertEqual(view.checkkey, view.Last_Prepare)
        future.set_result(None)
        self.assertFalse(view._poll_action())
        view.Draw_Prepare_Menu.assert_not_called()
        view.pd.ishomed.return_value = True
        self.assertFalse(view._poll_action())
        self.assertEqual(view.checkkey, view.Prepare)
        view.Draw_Prepare_Menu.assert_called_once()
        view.pd.sendGCodeObserved.assert_called_once_with('G28')

    def test_legacy_popup_text_supports_integral_float_positions(self):
        for parking, text in ((False, b'Homing XYZ'), (True, b'Parking')):
            with self.subTest(parking=parking):
                view = display(snapshot())
                view.lcd = driver()
                view.Popup_Window_Home(parking=parking)
                self.assertTrue(any(text in frame for frame in view.lcd.serial.frames))

class PopupRenderingTests(unittest.TestCase):
    def test_completed_homing_frame_contains_background_icon_and_label(self):
        from dwin_emulator.assets import PanelAssets, rgb565
        from dwin_emulator.framebuffer import Framebuffer
        view = display(snapshot())
        view.lcd = driver()
        assets = PanelAssets()
        assets.icon = Mock(wraps=assets.icon)
        model = Framebuffer(assets)
        view.lcd._packet_observer = model
        view.lcd.show_jpeg(5)
        view.Popup_Window_Home()
        view.lcd.update()
        image, _ = model.snapshot()
        assets.icon.assert_called_with(3, 78)
        self.assertTrue(any(frame[1] == 0x23 and frame[-5] == 78
                            for frame in view.lcd.serial.frames))
        background = rgb565(view.lcd.Color_Bg_Window)
        self.assertEqual(image.getpixel((20, 70)), background)
        self.assertTrue(any(low != high for low, high in image.crop((101, 105, 171, 175)).getextrema()))
        self.assertTrue(any(low != high for low, high in image.crop((96, 230, 176, 246)).getextrema()))

    def test_float_text_position_matches_integer_packet_and_rejects_fractions(self):
        lcd = driver()
        lcd.draw_text(False, True, 1, 0xFFFF, 0, 96, 230, 'Homing XYZ')
        expected = lcd.serial.frames[-1]
        lcd.draw_text(False, True, 1, 0xFFFF, 0, 96.0, 230.0, 'Homing XYZ')
        self.assertEqual(lcd.serial.frames[-1], expected)
        count = len(lcd.serial.frames)
        for x, y in ((96.5, 230), (96, 230.5), (float('nan'), 230), (96, float('inf'))):
            with self.subTest(x=x, y=y):
                with self.assertRaises(ValueError):
                    lcd.draw_text(False, True, 1, 0xFFFF, 0, x, y, 'Homing XYZ')
                self.assertEqual(len(lcd.serial.frames), count)
