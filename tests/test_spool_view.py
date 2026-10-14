import unittest
from unittest.mock import Mock

from spool_view import SpoolView
from lcd_resources import ICON_SPOOL_EMPTY, SPOOL_LEFT_FLANGES, SPOOL_RIGHT_FLANGES
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer


class SpoolViewTests(unittest.TestCase):
    def test_color_and_percentage_belong_to_each_instance(self):
        lcd = Mock()
        a = SpoolView(lcd, 10, 10, color=0xF800, remaining_percent=50)
        b = SpoolView(lcd, 80, 10, color=0x001F, remaining_percent=75)
        a.draw(); b.draw(); lcd.reset_mock()
        a.color = 0x07E0
        self.assertTrue(a.draw())
        lcd.reset_mock()
        self.assertFalse(b.draw())
        self.assertEqual(b.color, 0x001F)
        self.assertEqual(b.remaining_percent, 75)
        self.assertEqual(lcd.method_calls, [])

    def test_percentage_only_update_keeps_icon_and_filament(self):
        lcd = Mock()
        spool = SpoolView(lcd, 10, 10, color=0xF800, remaining_percent=100)
        spool.draw(); lcd.reset_mock()
        spool.remaining_percent = 99
        spool.draw()
        lcd.show_icon.assert_not_called()
        self.assertEqual(lcd.draw_rectangle.call_count, 1)
        self.assertEqual(lcd.draw_rectangle.call_args.args[-3], 30)
        self.assertEqual(lcd.draw_rectangle.call_args.args[-1], 41)
        self.assertEqual(lcd.draw_text.call_args.args[-1], '99%')

    def test_fill_contracts_equally_at_both_ends_and_reveals_gray_hub(self):
        lcd = Mock()
        spool = SpoolView(lcd, 10, 10, color=0xF800)
        for percent, height in ((100, 50), (50, 32), (0, 12)):
            with self.subTest(percent=percent):
                lcd.reset_mock()
                spool.remaining_percent = percent
                spool.draw()
                rect = lcd.draw_rectangle.call_args.args
                self.assertEqual(rect[3] + rect[5], 2 * spool.y + 51)
                self.assertEqual(rect[5] - rect[3] + 1, height)
                self.assertEqual(rect[1], 0x8410 if percent == 0 else 0xF800)

    def test_unknown_percentage_is_not_reported_as_empty(self):
        lcd = Mock()
        spool = SpoolView(lcd, 10, 10, color=0xF800, remaining_percent=None)
        spool.draw()
        self.assertEqual(lcd.draw_text.call_args.args[-1], '--')
        self.assertEqual(lcd.draw_rectangle.call_args.args[1], 0xF800)

    def test_component_never_draws_led_area(self):
        lcd = Mock()
        spool = SpoolView(lcd, 10, 46, remaining_percent=50)
        spool.draw()
        for call in lcd.draw_rectangle.call_args_list:
            self.assertGreaterEqual(call.args[3], 46)
            self.assertLessEqual(call.args[5], 97)
        lcd.draw_line.assert_not_called()

    def test_compact_sizes_fit_every_existing_home_lane(self):
        for count in range(1, 257):
            gap = 5 if count <= 4 else 2 if count <= 8 else 1 if count <= 32 else 0
            slot = max(1, min(60, (256 - gap * (count - 1)) // count))
            width = min(max(8, int(slot * .70)), max(1, slot - 2))
            self.assertEqual(SpoolView(Mock(), 0, 0, width).width, width)
        self.assertEqual(ICON_SPOOL_EMPTY, 124)
        self.assertEqual(set(SPOOL_LEFT_FLANGES), set(range(1, 8)))
        self.assertEqual(set(SPOOL_RIGHT_FLANGES), set(range(1, 8)))

    def test_both_screens_use_shared_instances_and_one_change_does_not_redraw_others(self):
        from test_capabilities import display
        from test_mmu_control import mmu_snapshot
        view = display(mmu_snapshot())
        view.lcd.DWIN_WIDTH = 272
        view.lcd.Line_Color = 0x3A6A
        view.pd.mmu['remaining_percent'] = [100, 100, 100, 0]
        view.Draw_MMU_Status()
        # Other regression modules deliberately reload UI modules for import safety.
        runtime_class = view.Draw_MMU_Status.__func__.__globals__['SpoolView']
        self.assertTrue(all(isinstance(s, runtime_class) for s in view._home_spool_views.values()))
        view.lcd.reset_mock()
        view.pd.mmu['remaining_percent'][1] = 99
        view.Draw_MMU_Status()
        self.assertEqual(len(view.lcd.method_calls), 2)
        view.lcd.show_icon.assert_not_called()

        view.Enter_MMU_Menu()
        self.assertTrue(all(isinstance(s, runtime_class) for s in view._mmu_spool_views.values()))
        view.lcd.reset_mock()
        view.pd.mmu['remaining_percent'][1] = 98
        view._mmu_spools(view.pd.mmu_session.state)
        self.assertEqual(len(view.lcd.method_calls), 2)
        view.lcd.show_icon.assert_not_called()

    def test_home_led_change_never_redraws_spools(self):
        from test_capabilities import display
        from test_mmu_control import mmu_snapshot
        view = display(mmu_snapshot())
        view.lcd.DWIN_WIDTH = 272
        view.lcd.Line_Color = 0x3A6A
        view.pd.mmu['exit_led_rgb'] = [(1, 0, 0)] * 4
        view.Draw_MMU_Status()
        view.lcd.reset_mock()
        view.pd.mmu['exit_led_rgb'][1] = (0, 1, 0)
        view.Draw_MMU_Status()
        self.assertEqual(len(view.lcd.method_calls), 4)
        view.lcd.show_icon.assert_not_called()
        self.assertTrue(all(103 <= c.args[3] <= c.args[5] <= 117
                            for c in view.lcd.draw_rectangle.call_args_list))

    def test_partial_updates_match_fresh_render_pixels_for_all_sizes(self):
        assets = PanelAssets()
        for width in (42, 34, 28, 23, 8, 2, 1):
            with self.subTest(width=width):
                lcd = driver()
                model = Framebuffer(assets)
                lcd._packet_observer = model
                lcd.clear(0)
                spool = SpoolView(lcd, 80, 60, width, remaining_percent=100,
                                  color=0xF800, label_width=max(28, width))
                for percent, color in ((100, 0xF800), (99, 0xF800), (25, 0xF800),
                                       (0, 0xF800), (100, 0x07E0), (5, 0x07E0)):
                    spool.remaining_percent, spool.color = percent, color
                    spool.draw(); lcd.update()
                    incremental = model.snapshot()[0].tobytes()
                    spool.invalidate()
                    spool.draw(); lcd.update()
                    self.assertEqual(incremental, model.snapshot()[0].tobytes())
