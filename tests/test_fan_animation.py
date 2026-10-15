import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot


class FanAnimationTests(unittest.TestCase):
    def view(self, speed=50):
        v = display(snapshot())
        v.pd.thermalManager['fan_speed'][0] = speed
        return v

    def test_same_rounded_interval_does_not_send_more_packets(self):
        v = self.view(50)
        v._sync_fan_animation(True)
        v.pd.thermalManager['fan_speed'][0] = 51
        v._sync_fan_animation(True)
        v.lcd.configure_animation.assert_called_once()
        self.assertEqual(v.lcd.configure_animation.call_args.args[-1], 2)

    def test_speed_change_continues_and_stop_only_sends_once(self):
        v = self.view(25)
        v._sync_fan_animation(True)
        v.pd.thermalManager['fan_speed'][0] = 100
        v._sync_fan_animation(True)
        self.assertEqual(v.lcd.configure_animation.call_args.args[-1], 1)
        self.assertFalse(v.lcd.configure_animation.call_args.kwargs['restart_from_first'])
        v.pd.thermalManager['fan_speed'][0] = 0
        v._sync_fan_animation(True)
        v._sync_fan_animation(True)
        self.assertEqual(v.lcd.configure_animation.call_count, 3)
        self.assertFalse(v.lcd.configure_animation.call_args.args[1])

    def test_redraw_and_reconnect_reconfigure_unchanged_speed(self):
        v = self.view()
        v._sync_fan_animation(True)
        v._sync_fan_animation(True, force=True)
        v._uart_epoch = 2
        v._sync_fan_animation(True)
        self.assertEqual(v.lcd.configure_animation.call_count, 3)

    def test_mmu_hides_animation_once(self):
        v = self.view()
        v._sync_fan_animation(True)
        v._sync_fan_animation(False)
        v._sync_fan_animation(False)
        self.assertEqual(v.lcd.configure_animation.call_count, 2)
        self.assertFalse(v.lcd.configure_animation.call_args.args[1])

    def test_all_percentages_are_bounded_and_monotonic(self):
        v = self.view()
        values = []
        for speed in range(1, 101):
            v.pd.thermalManager['fan_speed'][0] = speed
            v._sync_fan_animation(True)
            values.append(v._fan_animation_key[2])
        self.assertEqual(values[0], 100)
        self.assertEqual(values[-1], 1)
        self.assertEqual(values, sorted(values, reverse=True))

    def test_dashboard_fan_shows_percent_with_fixed_width(self):
        v = self.view(100)
        v.lcd.DWIN_WIDTH, v.lcd.DWIN_HEIGHT = 272, 480
        v.Draw_Status_Area(False)
        for speed in (100, 50, 0):
            v.pd.thermalManager['fan_speed'][0] = speed
            v.Draw_Status_Area(True)
            texts = [c.args[-1] for c in v.lcd.draw_text.call_args_list
                     if c.args[-3:-1] == (224, 380)]
            self.assertEqual(texts[-1], '{:3d}%'.format(speed))

    def test_status_text_cleanup_uses_its_own_background_and_font_size(self):
        v = self.view()
        v._status_render = {}
        v._draw_status_field('draw_text', False, True, 1, 65535, 0x18C4, 126, 416, '12.3mm3/s')
        v.lcd.reset_mock()
        v._draw_status_field('draw_text', False, True, 1, 65535, 0x18C4, 126, 416, '100%')
        v.lcd.draw_rectangle.assert_called_once_with(1, 0x18C4, 126, 416, 197, 431)

    def test_animation_frames_match_dashboard_background(self):
        from dwin_emulator.assets import PanelAssets
        from lcd_resources import ICON_LIBRARY_ID, ICON_FAN_FIRST, ICON_FAN_LAST
        from PIL import JpegImagePlugin, Image
        from pathlib import Path
        assets = PanelAssets()
        bg = (24, 24, 33)  # Expanded RGB565 0x18C4.
        for icon in range(ICON_FAN_FIRST, ICON_FAN_LAST + 1):
            with self.subTest(icon=icon):
                image = assets.icon(ICON_LIBRARY_ID, icon)
                self.assertEqual(image.size, (20, 20))
                for corner in ((0, 0), (19, 0), (0, 19), (19, 19)):
                    self.assertTrue(all(abs(a-b) <= 3 for a, b in
                                        zip(image.getpixel(corner), bg)))
                self.assertTrue(all(max(pixel) >= 20
                                    for pixel in image.get_flattened_data()))
                path = Path(__file__).resolve().parents[1] / 'assets/icons' / ('%03d.jpg' % icon)
                with Image.open(path) as jpeg:
                    self.assertEqual(JpegImagePlugin.get_sampling(jpeg), 2)
                    self.assertFalse(jpeg.info.get('progressive'))

    def test_stopped_fan_uses_same_opaque_backing_as_native_animation(self):
        from lcd_resources import ICON_FAN_FIRST
        view = self.view(0)
        view._sync_fan_animation(True)
        view.lcd.show_icon.assert_called_once_with(
            view.ICON, ICON_FAN_FIRST, 200, 380, background=True)
        view.lcd.configure_animation.assert_not_called()

    def test_every_fan_frame_preserves_dashboard_corners(self):
        from tools.render_docs_screenshots import canvas
        from lcd_resources import ICON_FAN_FIRST, ICON_FAN_LAST
        from dwin_emulator.framebuffer import rgb565
        view = canvas()
        view.lcd.draw_rectangle(1, 0x18C4, 0, 360, 271, 479)
        for icon in range(ICON_FAN_FIRST, ICON_FAN_LAST + 1):
            view.lcd.show_icon(view.ICON, icon, 200, 380, background=True)
            view.lcd.update()
            image = view.framebuffer.snapshot()[0]
            for point in ((200, 380), (219, 380), (200, 399), (219, 399)):
                self.assertTrue(all(abs(a-b) <= 8 for a, b in
                                    zip(image.getpixel(point), rgb565(0x18C4))))
