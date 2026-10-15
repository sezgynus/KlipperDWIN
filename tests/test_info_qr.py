import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot
from info_qr import PROJECT_URL, draw_project_qr
from shared_artwork import PICTURE_ID, QR_BOX


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
                    lcd.copy_cache1.assert_not_called()
                    lcd.ensure_cached_picture.assert_not_called()
                    continue
                lcd.draw_qr.assert_not_called()
                lcd.show_icon.assert_not_called()
                lcd.move_area.assert_not_called()
                lcd.ensure_cached_picture.assert_called_once_with(PICTURE_ID)
                first, last = max(y, 92), min(y+168, 360)
                lcd.copy_cache1.assert_called_once_with(0, first-y, 167, last-y-1, 52, first)

    def test_cached_qr_preserves_repo_data_and_exact_info_dimensions(self):
        import qrcode
        from dwin_emulator.assets import PanelAssets
        from PIL import Image
        image = PanelAssets().picture(PICTURE_ID).transpose(Image.Transpose.ROTATE_270).crop(QR_BOX)
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


class InfoCacheRenderingTests(unittest.TestCase):
    def test_area1_is_loaded_once_and_reloaded_after_another_picture(self):
        from test_t5uic1_driver import driver
        lcd = driver()
        lcd.ensure_cached_picture(1)
        lcd.ensure_cached_picture(1)
        self.assertEqual([p[1] for p in lcd.serial.frames], [0x25])
        lcd.cache_jpeg(0)
        lcd.ensure_cached_picture(1)
        self.assertEqual([p[3] for p in lcd.serial.frames], [1, 0, 1])
        from unittest.mock import patch
        with patch.object(lcd, '_wait_response', return_value=b'OK'):
            lcd.store_sram_as_picture(1)
        lcd.serial.frames.clear()
        lcd.ensure_cached_picture(1)
        self.assertEqual([p[1] for p in lcd.serial.frames], [0x25])
        # A new connection has no decoded cache to reuse.
        other = driver()
        other.ensure_cached_picture(1)
        self.assertEqual(len(other.serial.frames), 1)

    def test_incremental_qr_entrance_only_copies_the_exposed_band(self):
        from tools.render_docs_screenshots import canvas
        v = canvas()
        q = next(i for i, item in enumerate(v._info_items()) if item[0] == 'qr')
        v._info_scroll = q-10
        v.Draw_Info_Menu()
        v.lcd.serial.frames.clear()
        v._info_scroll += 1
        v.Draw_Info_Menu()
        packets = v.lcd.serial.frames
        self.assertFalse(any(p[1] in (0x24, 0x25) for p in packets))
        copies = [p for p in packets if p[1] == 0x26]
        self.assertEqual(len(copies), 1)
        self.assertEqual(v.lcd._words(0, 0, 167, 23, 52, 332), copies[0][2:-4])
        self.assertEqual(sum(p[1] == 0x09 for p in packets), 1)
        self.assertLessEqual(sum(map(len, packets)), 260)

    def test_full_and_incremental_scroll_match_in_both_directions(self):
        from tools.render_docs_screenshots import canvas
        from PIL import ImageChops
        v, reference = canvas(), canvas()
        maximum = len(v._info_items()) + 9 - 11
        for scroll in list(range(maximum+1)) + list(range(maximum-1, -1, -1)) + [maximum, 0]:
            v._info_scroll = reference._info_scroll = scroll
            reference._info_render_scroll = None
            v.Draw_Info_Menu(); v.lcd.update()
            reference.Draw_Info_Menu(); reference.lcd.update()
            a = v.framebuffer.snapshot()[0].crop((0, 90, 256, 356))
            b = reference.framebuffer.snapshot()[0].crop((0, 90, 256, 356))
            self.assertIsNone(ImageChops.difference(a, b).getbbox(), scroll)
