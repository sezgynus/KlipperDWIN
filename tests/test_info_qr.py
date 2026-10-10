import unittest
from unittest.mock import Mock

from info_qr import PROJECT_QR, draw_project_qr


class InfoQRTests(unittest.TestCase):
    def test_all_scroll_positions_clip_rectangles_to_menu_and_preserve_modules(self):
        size = len(PROJECT_QR) * 4
        x = (272 - size) // 2
        for y in range(68, 405, 24):
            with self.subTest(y=y):
                lcd = Mock(DWIN_WIDTH=272, Color_White=0xFFFF)
                draw_project_qr(lcd, y)
                pixels = {}
                for call in lcd.draw_rectangle.call_args_list:
                    mode, color, x1, y1, x2, y2 = call.args
                    self.assertEqual(mode, 1)
                    self.assertTrue(0 <= x1 <= x2 < 272)
                    self.assertTrue(92 <= y1 <= y2 < 360)
                    for py in range(y1, y2 + 1):
                        for px in range(x1, x2 + 1):
                            pixels[px, py] = color
                for py in range(max(92, y), min(360, y + size)):
                    for px in range(x, x + size):
                        expected = 0 if PROJECT_QR[(py-y)//4][(px-x)//4] == '1' else 0xFFFF
                        self.assertEqual(pixels[px, py], expected)
                self.assertEqual(len(pixels), size * max(0, min(360, y + size) - max(92, y)))

    def test_matrix_is_square_and_has_four_module_quiet_zone(self):
        self.assertEqual(len(PROJECT_QR), 37)
        for row in PROJECT_QR:
            self.assertEqual(len(row), 37)
            self.assertTrue(set(row) <= {'0', '1'})
            self.assertEqual(row[:4] + row[-4:], '0' * 8)
        self.assertEqual(PROJECT_QR[:4], ('0' * 37,) * 4)
        self.assertEqual(PROJECT_QR[-4:], ('0' * 37,) * 4)
