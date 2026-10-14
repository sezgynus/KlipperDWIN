import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot
from test_t5uic1_driver import driver
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer


class IncrementalMenuTests(unittest.TestCase):
    def make(self):
        v = display(snapshot(probe=True))
        v.lcd.DWIN_WIDTH = 272
        v.checkkey = v.Prepare
        return v

    def entries(self, count=12):
        return [('Row %d' % i, 0, None, None) for i in range(count)]

    def test_selection_changes_only_two_cursor_rectangles(self):
        v = self.make()
        v.Draw_Prepare_Menu()
        v.lcd.reset_mock()
        v.select_prepare.set(1)
        v.Draw_Prepare_Menu()
        self.assertEqual(len(v.lcd.method_calls), 2)
        v.lcd.show_icon.assert_not_called()
        v.lcd.draw_text.assert_not_called()
        self.assertTrue(all(0 <= c.args[-4] <= c.args[-2] <= 14
                            for c in v.lcd.draw_rectangle.call_args_list))

    def test_unchanged_menu_draws_nothing(self):
        v = self.make()
        v.Draw_Control_Menu()
        v.lcd.reset_mock()
        v.Draw_Control_Menu()
        self.assertEqual(v.lcd.method_calls, [])

    def test_scroll_moves_pixels_and_draws_only_exposed_row(self):
        v = self.make()
        entries = self.entries()
        v._draw_list_menu('List', entries, 5)
        v.lcd.reset_mock()
        v.Draw_Menu_Line = Mock(wraps=v.Draw_Menu_Line)
        v._draw_list_menu('List', entries, 6)
        v.lcd.move_area.assert_called_once()
        self.assertEqual(v.lcd.move_area.call_args.args[2], 53)
        v.Draw_Menu_Line.assert_called_once_with(5, 0, 'Row 6')
        v.lcd.reset_mock(); v.Draw_Menu_Line.reset_mock()
        v._draw_list_menu('List', entries, 0)
        v.lcd.move_area.assert_called_once()
        v.Draw_Menu_Line.assert_called_once_with(0, 0, 'Row 0')

    def test_changed_value_redraws_only_its_row(self):
        v = self.make()
        entries = self.entries(4)
        v._draw_list_menu('List', entries, 0)
        v.lcd.reset_mock()
        v.Draw_Menu_Line = Mock(wraps=v.Draw_Menu_Line)
        entries[2] = ('Row 2', 0, 'new', lambda row: v._draw_menu_text('new', 200, v.MBASE(row)))
        v._draw_list_menu('List', entries, 0)
        v.Draw_Menu_Line.assert_called_once_with(2, 0, 'Row 2')
        v.lcd.move_area.assert_not_called()

    def test_incremental_scroll_matches_complete_render_pixels(self):
        v = self.make()
        v.lcd = driver()
        model = Framebuffer(PanelAssets())
        v.lcd._packet_observer = model
        v.lcd.show_jpeg(5)
        entries = self.entries()
        v._draw_list_menu('List', entries, 5)
        for selection in (6, 7, 6, 5, 1, 0):
            with self.subTest(selection=selection):
                v._draw_list_menu('List', entries, selection)
                start = v._list_render['start']
                v.lcd.update()
                incremental = model.snapshot()[0].tobytes()
                v._list_render = None
                v._draw_list_menu('List', entries, selection, start)
                v.lcd.update()
                self.assertEqual(incremental, model.snapshot()[0].tobytes())

    def test_all_short_list_menus_keep_icons_on_selection(self):
        for draw_name, selection_name, is_object in (
            ('Draw_Move_Menu', 'select_axis', True),
            ('Draw_Display_Menu', '_display_selection', False),
            ('Draw_Bed_Mesh_Menu', '_mesh_menu_selection', False),
            ('Draw_Screws_Menu', '_screws_selection', False),
            ('Draw_Case_Light_Menu', 'select_light', True)):
            with self.subTest(menu=draw_name):
                v = self.make()
                getattr(v, draw_name)()
                v.lcd.reset_mock()
                if is_object: getattr(v, selection_name).set(1)
                else: setattr(v, selection_name, 1)
                getattr(v, draw_name)()
                v.lcd.show_icon.assert_not_called()
                v.lcd.draw_text.assert_not_called()
