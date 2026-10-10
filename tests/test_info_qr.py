import unittest
from unittest.mock import Mock
from info_qr import PROJECT_URL, draw_project_qr


class InfoQRTests(unittest.TestCase):
    def test_native_qr_stays_inside_menu_at_every_scroll_position(self):
        for y in range(68, 405, 24):
            with self.subTest(y=y):
                lcd = Mock(Color_White=0xFFFF, Color_Bg_Black=0)
                draw_project_qr(lcd, y)
                if y >= 360 or y + 168 <= 92:
                    lcd.draw_qr.assert_not_called()
                    continue
                lcd.draw_qr.assert_called_once_with(64, 104, 3, PROJECT_URL)
                lcd.draw_rectangle.assert_called_once_with(1, 0xFFFF, 52, 92, 219, 259)
                self.assertLessEqual(len(lcd.mock_calls), 3)
                if y != 92:
                    lcd.move_area.assert_called_once_with(
                        1, 3 if y > 92 else 2, abs(y - 92), 0, 52, 92, 219, 359)
                else:
                    lcd.move_area.assert_not_called()
