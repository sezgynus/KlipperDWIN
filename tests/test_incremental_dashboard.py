import unittest
from unittest.mock import patch
from test_capabilities import display, snapshot
from test_regressions import ui
from test_mmu_control import mmu_snapshot


class IncrementalDashboardTests(unittest.TestCase):
    def make(self, data=None):
        v = display(data or snapshot())
        v.lcd.DWIN_WIDTH = 272
        v.lcd.DWIN_HEIGHT = 480
        v.lcd.Line_Color = 0x3A6A
        v.checkkey = v.MainMenu
        return v

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_unchanged_status_sends_no_drawing(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_only_changed_temperature_is_drawn(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.pd.thermalManager['temp_hotend'][0]['celsius'] = 201
        v.Draw_Status_Area(True)
        self.assertEqual(len(v.lcd.method_calls), 1)
        self.assertEqual(v.lcd.draw_integer_text.call_args.args[-3:], (28, 380, 201))

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_sub_display_precision_does_not_redraw(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.pd.thermalManager['temp_hotend'][0]['celsius'] = 200.1
        v.Draw_Status_Area(True)
        self.assertEqual(v.lcd.method_calls, [])

    @patch.object(ui.time, 'monotonic', return_value=4)
    def test_shorter_text_erases_full_font_height(self, clock):
        v = self.make()
        v.Draw_Status_Area(False)
        v.lcd.reset_mock()
        v.pd.live_velocity = 1
        v.Draw_Status_Area(True)
        rect = v.lcd.draw_rectangle.call_args.args
        self.assertEqual(rect[-3], 380)
        self.assertEqual(rect[-1], 399)
        v.lcd.show_icon.assert_not_called()

    def test_unchanged_mmu_sends_no_drawing(self):
        v = self.make(mmu_snapshot())
        v.Draw_MMU_Status()
        v.lcd.reset_mock()
        v.Draw_MMU_Status()
        self.assertEqual(v.lcd.method_calls, [])

    def test_one_percentage_updates_only_its_text_area(self):
        v = self.make(mmu_snapshot())
        mmu = dict(v.pd.mmu)
        mmu['remaining_percent'] = [100, 100, 100, 100]
        with patch.object(v.pd, 'mmu', mmu):
            v.Draw_MMU_Status()
            v.lcd.reset_mock()
            mmu['remaining_percent'][1] = 99
            v.Draw_MMU_Status()
        self.assertEqual(len(v.lcd.method_calls), 2)
        v.lcd.show_icon.assert_not_called()
        self.assertEqual(v.lcd.draw_text.call_args.args[-1], '99%')
        v.lcd.draw_line.assert_not_called()

    def test_same_page_selection_draws_only_two_tiles(self):
        v = self.make()
        v._draw_home_page()
        v.lcd.reset_mock()
        v.select_page.set(1)
        v._draw_home_page(previous=0)
        self.assertEqual(v.lcd.show_icon.call_count, 2)
        self.assertEqual([c.args[-4:] for c in v.lcd.draw_rectangle.call_args_list
                          if c.args[0] == 1], [(17, 130, 126, 229), (145, 130, 254, 229)])

    def test_mmu_is_redrawn_after_leaving_and_returning(self):
        v = self.make(mmu_snapshot())
        v.Goto_MainMenu()
        v.lcd.reset_mock()
        v.Clear_Main_Window()
        v.Draw_MMU_Status()
        self.assertGreaterEqual(v.lcd.show_icon.call_count, 4)
