"""Pixel contracts for transparent artwork and selection transitions."""
import unittest
from unittest.mock import Mock, patch
from PIL import ImageChops
from test_capabilities import display, snapshot
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from lcd_resources import ICON_LIBRARY_ID


class VisualRoundingTests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view.lcd = driver()
        view.framebuffer = Framebuffer(PanelAssets())
        view.lcd._packet_observer = view.framebuffer
        view.lcd.clear(0x2125)
        view._power_hold_popup = True
        view._power_blocked = None
        return view

    def capture(self, view):
        view.lcd.update()
        return view.framebuffer.snapshot()[0]

    def test_power_artwork_has_filtered_corners_and_no_opaque_matte(self):
        assets = PanelAssets()
        for index in (146, 149, 150, 151):
            with self.subTest(icon=index):
                image = assets.icon(ICON_LIBRARY_ID, index)
                for corner in ((0, 0), (image.width-1, 0),
                               (0, image.height-1), (image.width-1, image.height-1)):
                    self.assertLessEqual(max(image.getpixel(corner)), 31)

    def test_power_selection_matches_fresh_render_after_round_trip(self):
        with patch('t5uic1_driver.time.sleep'):
            view = self.view()
            view._power_confirm_yes = False
            view._draw_power_confirmation()
            before = self.capture(view)
            view._power_confirm_yes = True
            view._draw_power_confirmation(buttons_only=True)
            fresh = self.view()
            fresh._power_confirm_yes = True
            fresh._draw_power_confirmation()
            self.assertIsNone(ImageChops.difference(
                self.capture(view), self.capture(fresh)).getbbox())
            view._power_confirm_yes = False
            view._draw_power_confirmation(buttons_only=True)
            self.assertIsNone(ImageChops.difference(before, self.capture(view)).getbbox())

    def test_stop_and_mmu_error_round_trips_leave_no_previous_selection(self):
        with patch('t5uic1_driver.time.sleep'):
            for kind in ('stop', 'mmu'):
                with self.subTest(kind=kind):
                    view = self.view()
                    if kind == 'stop':
                        view.pd.HMI_flag.select_flag = False
                        view._focus_stop_draw()
                        before = self.capture(view)
                        view.pd.HMI_flag.select_flag = True
                        view._focus_stop_draw(buttons_only=True)
                        view.pd.HMI_flag.select_flag = False
                        view._focus_stop_draw(buttons_only=True)
                    else:
                        view._focus_error_lines = ['Example MMU error']
                        view._focus_error_scroll = view._focus_error_choice = 0
                        view._focus_error_draw()
                        before = self.capture(view)
                        view._focus_error_choice = 1
                        view._focus_error_draw(buttons_only=True)
                        view._focus_error_choice = 0
                        view._focus_error_draw(buttons_only=True)
                    self.assertIsNone(ImageChops.difference(before, self.capture(view)).getbbox())

    def test_info_selection_round_trip_preserves_the_initial_pixels(self):
        with patch('t5uic1_driver.time.sleep'):
            view = self.view()
            view._software_update = Mock(phase='current', label='Check for updates', message='')
            view._draw_info_update_button(332, False)
            before = self.capture(view)
            view._draw_info_update_button(332, True)
            view._draw_info_update_button(332, False)
            self.assertIsNone(ImageChops.difference(before, self.capture(view)).getbbox())
