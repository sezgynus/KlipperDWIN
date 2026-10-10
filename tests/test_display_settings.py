import unittest
from unittest.mock import Mock, patch
import display_settings as settings
from test_t5uic1_driver import driver
from test_capabilities import display, snapshot
from test_regressions import ui

class DisplaySettingsTests(unittest.TestCase):
    def test_record_integrity_and_ranges(self):
        for brightness in (0, 1, 50, 100):
            for minutes in (0, 1, 60):
                record = settings.encode(brightness, minutes)
                self.assertEqual(settings.decode(record), (brightness, minutes))
                damaged = bytearray(record); damaged[9] ^= 1
                self.assertIsNone(settings.decode(damaged))
        self.assertIsNone(settings.decode(bytes(16)))
        self.assertIsNone(settings.decode(b''))
        for pair in ((101, 0), (-1, 0), (50, 61), (50, -1)):
            with self.assertRaises(ValueError): settings.encode(*pair)
        self.assertEqual([settings.raw_brightness(x) for x in (0, 50, 100)], [0, 128, 255])

    def test_flash_is_disjoint_and_verified(self):
        lcd = driver(); record = settings.encode(72, 12)
        lcd.write_flash = Mock(); lcd.read_flash = Mock(return_value=record)
        lcd.save_display_settings(72, 12)
        lcd.write_flash.assert_called_once_with(0x100, record)
        self.assertGreaterEqual(lcd.DISPLAY_SETTINGS_ADDRESS,
                                lcd.ATLAS_METADATA_ADDRESS + lcd.ATLAS_METADATA_SIZE)
        self.assertEqual(lcd.load_display_settings(), (72, 12))
        lcd.read_flash.return_value = bytes(16)
        with self.assertRaises(OSError): lcd.save_display_settings(72, 12)

    def view(self):
        view = display(snapshot())
        view._display_values = [50, 0]; view._display_saved = (50, 0)
        view._display_selection = 1; view._display_edit = False
        view.Draw_Display_Menu = Mock(); view.get_encoder_state = Mock()
        return view

    def step(self, view, event):
        view.get_encoder_state.return_value = event
        view.HMI_Display_Menu()

    def test_live_changes_only_save_final_value_on_click(self):
        view = self.view(); self.step(view, view.ENCODER_DIFF_ENTER)
        for _ in range(7): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._display_values, [57, 0])
        self.assertEqual(view.lcd.set_backlight.call_count, 7)
        view.lcd.save_display_settings.assert_not_called()
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.lcd.save_display_settings.assert_called_once_with(57, 0)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.lcd.save_display_settings.call_count, 1)

    def test_timeout_bounds_save_and_failed_save_retry(self):
        view = self.view(); view._display_selection = 2
        self.step(view, view.ENCODER_DIFF_ENTER)
        for _ in range(65): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._display_values[1], 60)
        view.lcd.save_display_settings.assert_not_called()
        view.lcd.save_display_settings.side_effect = OSError()
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertTrue(view._display_edit)
        self.assertEqual(view._display_saved, (50, 0))
        view.lcd.save_display_settings.side_effect = None
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._display_saved, (50, 60))

    def test_idle_dim_and_wake_never_write_flash(self):
        view = self.view(); view._display_values = [50, 1]
        view._display_last_activity = 100
        with patch.object(ui.time, 'monotonic', return_value=159): view._display_idle_tick()
        view.lcd.set_backlight.assert_not_called()
        with patch.object(ui.time, 'monotonic', return_value=160): view._display_idle_tick()
        view.lcd.set_backlight.assert_called_once_with(26)
        self.assertTrue(view._display_activity())
        view.lcd.set_backlight.assert_called_with(128)
        self.assertFalse(view._display_activity())
        view.lcd.save_display_settings.assert_not_called()

    def test_disabled_low_brightness_and_editing_do_not_brighten(self):
        view = self.view(); view._display_last_activity = 0
        with patch.object(ui.time, 'monotonic', return_value=9999):
            view._display_idle_tick()
            view.lcd.set_backlight.assert_not_called()
            view._display_values = [3, 1]; view._display_edit = True
            view._display_idle_tick()
            view.lcd.set_backlight.assert_not_called()
            view._display_edit = False; view._display_idle_tick()
            view.lcd.set_backlight.assert_called_once_with(8)

    def test_brightness_clamps_at_zero_and_one_hundred(self):
        view = self.view(); self.step(view, view.ENCODER_DIFF_ENTER)
        for _ in range(110): self.step(view, view.ENCODER_DIFF_CCW)
        self.assertEqual(view._display_values[0], 0)
        view.lcd.set_backlight.assert_called_with(0)
        for _ in range(110): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._display_values[0], 100)
        view.lcd.set_backlight.assert_called_with(255)
        view.lcd.save_display_settings.assert_not_called()
