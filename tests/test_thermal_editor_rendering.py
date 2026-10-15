"""Regression coverage for edits followed by immediate menu navigation."""
import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot


class ThermalEditorRenderingTests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view._encoder_move_value = 1
        view.pd.HMI_ValueStruct.show_mode = -1
        view.pd.setFanSpeed = Mock()
        view.pd.setExtTemp = Mock()
        view.pd.setBedTemp = Mock()
        return view

    def test_scrolled_editors_use_visible_row_on_open_rotate_and_confirm(self):
        for key, handler in (('FAN', 'HMI_FanSpeed'), ('TEMP', 'HMI_ETemp'),
                             ('BED', 'HMI_BedTemp')):
            with self.subTest(key=key):
                view = self.view()
                logical = next(i for i, entry in enumerate(view._menus['temperature'], 1)
                               if entry[0] == key)
                view.index_temp = view.MROWS + 1
                view.select_temp.set(logical)
                view.Draw_Temperature_Menu()
                view.lcd.reset_mock()
                view._open_thermal_editor(key, logical)
                self.assertEqual(view.lcd.draw_integer_text.call_args.args[8],
                                 view.MBASE(logical - 1))
                for event in (view.ENCODER_DIFF_CW, view.ENCODER_DIFF_CCW,
                              view.ENCODER_DIFF_ENTER):
                    view.get_encoder_state = Mock(return_value=event)
                    view.lcd.reset_mock()
                    getattr(view, handler)()
                    draws = view.lcd.draw_integer_text.call_args_list
                    if event != view.ENCODER_DIFF_ENTER or key != 'FAN':
                        self.assertEqual(draws[-1].args[8], view.MBASE(logical - 1))

    def test_confirm_without_status_echo_repaints_only_edited_row(self):
        view = self.view()
        row = view.TEMP_CASE_FAN
        view.select_temp.set(row)
        view.Draw_Temperature_Menu()
        view._open_thermal_editor('FAN', row)
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_CW)
        view.HMI_FanSpeed()
        view.lcd.reset_mock()
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.Draw_Menu_Line = Mock()
        view.HMI_FanSpeed()
        view.pd.setFanSpeed.assert_called_once()
        self.assertEqual([call.args[0] for call in view.Draw_Menu_Line.call_args_list],
                         [row])
        view.lcd.move_area.assert_not_called()
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[4],
                         view.lcd.Color_White)
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[5],
                         view.lcd.Color_Bg_Black)

    def test_unchanged_confirm_clears_edit_highlight(self):
        view = self.view()
        row = view.TEMP_CASE_FAN
        view.select_temp.set(row)
        view.Draw_Temperature_Menu()
        view._open_thermal_editor('FAN', row)
        view.lcd.reset_mock()
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_FanSpeed()
        view.lcd.draw_integer_text.assert_called_once()
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[5],
                         view.lcd.Color_Bg_Black)

    def test_scrolled_fan_edit_then_navigation_matches_clean_render(self):
        from tools.render_docs_screenshots import canvas
        from PIL import ImageChops
        view, reference = canvas(), canvas()
        for panel in (view, reference):
            panel.pd.HMI_ValueStruct.show_mode = -1
            panel.pd.setFanSpeed = Mock()
            panel._encoder_move_value = 1
            panel.index_temp = panel.MROWS + 1
            panel.select_temp.set(panel.TEMP_CASE_FAN)
            panel.pd.thermalManager['fan_speed'][0] = 7
            panel.Draw_Temperature_Menu()
        for value in (8, 7, 21, 7):
            logical = view.TEMP_CASE_FAN
            view._open_thermal_editor('FAN', logical)
            view.pd.HMI_ValueStruct.Fan_speed = value - 1
            view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_CW)
            view.HMI_FanSpeed()
            view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
            view.HMI_FanSpeed()
            for start, selected in ((0, logical), (1, logical+1), (0, logical)):
                for panel in (view, reference):
                    panel.index_temp = panel.MROWS + start
                    panel.select_temp.set(selected)
                reference._list_render = None
                view.Draw_Temperature_Menu(); view.lcd.update()
                reference.Draw_Temperature_Menu(); reference.lcd.update()
                actual = view.framebuffer.snapshot()[0].crop((0, 31, 272, 349))
                expected = reference.framebuffer.snapshot()[0].crop((0, 31, 272, 349))
                self.assertIsNone(ImageChops.difference(actual, expected).getbbox(),
                                  (value, start))
