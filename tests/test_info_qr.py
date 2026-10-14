import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot
from info_qr import PROJECT_URL, draw_project_qr
from lcd_resources import ICON_LIBRARY_ID, ICON_PROJECT_QR


class InfoQRTests(unittest.TestCase):
    def test_update_button_reuses_backing_until_selection_changes(self):
        view = display(snapshot())
        updater = Mock(phase='current', label='Check for updates', message='')
        view._software_update = updater
        view._draw_info_update_button(300, False)
        view.lcd.reset_mock()
        view._draw_info_update_button(300, False)
        view.lcd.draw_bitmap.assert_not_called()
        view.lcd.show_icon.assert_not_called()
        view.lcd.draw_text.assert_not_called()
        updater.label = 'Update'
        view._draw_info_update_button(300, False)
        view.lcd.draw_rectangle.assert_called_once_with(1, 0x2967, 46, 300, 226, 319)
        view.lcd.reset_mock()
        view._draw_info_update_button(300, True)
        view.lcd.draw_bitmap.assert_not_called()
        self.assertEqual(view.lcd.show_icon.call_count, 1)


    def test_managed_qr_stays_inside_menu_at_every_scroll_position(self):
        for y in range(68, 405, 24):
            with self.subTest(y=y):
                lcd = Mock(Color_White=0xFFFF, Color_Bg_Black=0)
                draw_project_qr(lcd, y)
                if y >= 360 or y + 168 <= 92:
                    lcd.show_icon.assert_not_called()
                    continue
                lcd.draw_qr.assert_not_called()
                lcd.show_icon.assert_called_once_with(ICON_LIBRARY_ID, ICON_PROJECT_QR,
                    52, 92, background=True, enhanced=False)
                lcd.draw_rectangle.assert_not_called()
                self.assertLessEqual(len(lcd.mock_calls), 3)
                if y != 92:
                    lcd.move_area.assert_called_once_with(
                        1, 3 if y > 92 else 2, abs(y - 92), 0, 52, 92, 219, 359)
                else:
                    lcd.move_area.assert_not_called()

    def test_packed_qr_preserves_repo_data_and_exact_info_dimensions(self):
        import qrcode
        from dwin_emulator.assets import PanelAssets
        image = PanelAssets().icon(ICON_LIBRARY_ID, ICON_PROJECT_QR)
        self.assertEqual(image.size, (168, 168))
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=2)
        qr.add_data(PROJECT_URL); qr.make(fit=True)
        matrix = qr.get_matrix(); count = len(matrix)
        for row, values in enumerate(matrix):
            for col, dark in enumerate(values):
                x = (round(col*168/count) + round((col+1)*168/count)-1)//2
                y = (round(row*168/count) + round((row+1)*168/count)-1)//2
                if 56 <= x <= 112 and 53 <= y <= 115:
                    continue  # Intentional logo erasure is protected by ECC H.
                self.assertEqual(max(image.getpixel((x,y))) < 128, dark)
