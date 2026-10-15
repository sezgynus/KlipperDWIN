"""Direct-editor cache ownership, popup return and navigation regressions."""
import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot


class EditorCacheAuditTests(unittest.TestCase):
    def event(self, view, event, handler):
        view.get_encoder_state = Mock(return_value=event)
        handler()

    def canvas(self, data=None):
        from tools.render_docs_screenshots import canvas
        view = canvas(data)
        view._live_jog = False
        view._encoder_move_value = 1
        view._action = Mock()
        return view

    def assert_menu_equal(self, view, reference):
        from PIL import ImageChops
        view.lcd.update(); reference.lcd.update()
        a = view.framebuffer.snapshot()[0].crop((0, 31, 272, 349))
        b = reference.framebuffer.snapshot()[0].crop((0, 31, 272, 349))
        self.assertIsNone(ImageChops.difference(a, b).getbbox())

    def test_axis_edits_then_navigation_match_fresh_subscription_values(self):
        for axis, row, handler in (('X', 1, 'HMI_Move_X'), ('Y', 2, 'HMI_Move_Y'),
                                   ('Z', 3, 'HMI_Move_Z'), ('E', 4, 'HMI_Move_E')):
            for popup in (False, True):
                with self.subTest(axis=axis, popup=popup):
                    data = snapshot()
                    data['status']['extruder']['can_extrude'] = True
                    view, reference = self.canvas(data), self.canvas(data)
                    view.checkkey = view.AxisMove
                    view.select_axis.set(row)
                    view.Draw_Move_Menu()
                    self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_AxisMove)
                    self.assertNotIn(row, view._list_render['values'])
                    self.event(view, view.ENCODER_DIFF_CW, getattr(view, handler))
                    if popup:
                        origin = view.checkkey
                        view.lcd.draw_rectangle(1, 0xFFFF, 28, 160, 240, 260)
                        view._power_origin = origin
                        view._restore_power_origin()
                        self.assertNotIn(row, view._list_render['values'])
                    self.event(view, view.ENCODER_DIFF_ENTER, getattr(view, handler))
                    self.event(view, view.ENCODER_DIFF_CW, view.HMI_AxisMove)
                    reference.select_axis.set(view.select_axis.now)
                    reference.Draw_Move_Menu()
                    self.assert_menu_equal(view, reference)

    def test_case_light_unchanged_edit_and_popup_clear_highlight(self):
        for popup in (False, True):
            with self.subTest(popup=popup):
                data = snapshot()
                data['objects'].append('output_pin case_light')
                data['settings']['output_pin case_light'] = {'pwm': True}
                data['status']['output_pin case_light'] = {'value': .25}
                view, reference = self.canvas(data), self.canvas(data)
                for panel in (view, reference):
                    panel.checkkey = panel.CaseLight
                    panel._case_light_on = True
                    panel._case_light_brightness = 25
                    panel.select_light.set(2)
                    panel._poll_case_light_live = Mock()
                    panel.Draw_Case_Light_Menu()
                self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Case_Light)
                self.assertNotIn(2, view._list_render['values'])
                if popup:
                    view.lcd.draw_rectangle(1, 0xFFFF, 28, 160, 240, 260)
                    view._power_origin = view.CaseLightBrightness
                    view._restore_power_origin()
                    self.assertNotIn(2, view._list_render['values'])
                    self.assertEqual(view._case_light_brightness_target, 25)
                self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Case_Light_Brightness)
                self.event(view, view.ENCODER_DIFF_CCW, view.HMI_Case_Light)
                reference.select_light.set(1)
                reference.Draw_Case_Light_Menu()
                self.assert_menu_equal(view, reference)

    def test_scrolled_zoffset_keeps_row_and_invalidates_cached_normal_row(self):
        view = display(snapshot())
        view._encoder_move_value = 1
        view._action = Mock()
        view.index_prepare = view.MROWS + 1
        view.select_prepare.set(view.PREPARE_CASE_ZOFF)
        view.Draw_Prepare_Menu()
        row = view.PREPARE_CASE_ZOFF - 1
        view._open_zoffset(-4, row)
        self.assertNotIn(view.PREPARE_CASE_ZOFF, view._list_render['values'])
        view.dwin_zoffset = 0
        self.event(view, view.ENCODER_DIFF_CW, view.HMI_Zoffset)
        view._power_origin = view.Homeoffset
        view._restore_power_origin()
        self.assertEqual(view._zoffset_edit_row, row)
        self.assertNotIn(view.PREPARE_CASE_ZOFF, view._list_render['values'])
        self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Zoffset)
        view.Draw_Menu_Line = Mock()
        self.event(view, view.ENCODER_DIFF_CW, view.HMI_Prepare)
        self.assertIn(row, [c.args[0] for c in view.Draw_Menu_Line.call_args_list])

    def test_thermal_popup_restores_scrolled_draft_and_dirty_row(self):
        for key, screen, attr in (('FAN', 'FanSpeed', 'Fan_speed'),
                                  ('TEMP', 'ETemp', 'E_Temp'),
                                  ('BED', 'BedTemp', 'Bed_Temp')):
            with self.subTest(key=key):
                view = display(snapshot())
                view.pd.HMI_ValueStruct.show_mode = -1
                logical = getattr(view, 'TEMP_CASE_' + key)
                view.index_temp = view.MROWS + 1
                view.select_temp.set(logical)
                view.Draw_Temperature_Menu()
                view._open_thermal_editor(key, logical)
                setattr(view.pd.HMI_ValueStruct, attr, 42)
                view._power_origin = getattr(view, screen)
                view.lcd.reset_mock()
                view._restore_power_origin()
                self.assertEqual(view._thermal_edit_row, logical - 1)
                args = view.lcd.draw_integer_text.call_args.args
                self.assertEqual(args[8:], (view.MBASE(logical - 1), 42))
                self.assertNotIn(logical, view._list_render['values'])

    def test_preset_popup_restores_draft_on_visible_row(self):
        view = display(snapshot())
        view.pd.HMI_ValueStruct.show_mode = -2
        view._active_preset = 0
        view.index_preset = view.MROWS
        view.select_PLA.set(view.PREHEAT_CASE_BED)
        view._draw_capability_menu('preheat', view.select_PLA, profile=0)
        view._open_thermal_editor('BED', view.PREHEAT_CASE_BED, 0)
        view.pd.HMI_ValueStruct.Bed_Temp = 65
        view._power_origin = view.BedTemp
        view._restore_power_origin()
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[-1], 65)
        self.assertNotIn(view.PREHEAT_CASE_BED, view._list_render['values'])

    def test_hold_overlay_return_restores_cached_menus_pixel_for_pixel(self):
        for screen, draw, selection in (
                ('Control', 'Draw_Control_Menu', None),
                ('TemperatureID', 'Draw_Temperature_Menu', None),
                ('AxisMove', 'Draw_Move_Menu', None),
                ('DisplayMenu', 'Draw_Display_Menu', '_display_selection'),
                ('Info', 'Draw_Info_Menu', None)):
            with self.subTest(screen=screen):
                view, reference = self.canvas(), self.canvas()
                for panel in (view, reference):
                    panel.checkkey = getattr(panel, screen)
                    if selection:
                        setattr(panel, selection, 1)
                    getattr(panel, draw)()
                view.lcd.draw_rectangle(1, 0xFFFF, 28, 160, 240, 260)
                view._power_origin = getattr(view, screen)
                view._restore_power_origin()
                self.assert_menu_equal(view, reference)

    def test_motion_editor_cache_includes_edit_mode_even_without_value_change(self):
        from test_motion import data
        view = display(data())
        view.checkkey = view.Motion
        view.select_motion.set(1)
        view.Draw_Motion_Menu()
        self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Motion)
        self.assertTrue(view._list_render['values'][1][1])
        self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_MotionValue)
        self.assertFalse(view._list_render['values'][1][1])

    def test_display_editor_cache_includes_edit_mode_even_without_value_change(self):
        view = self.canvas()
        view._display_selection = 1
        view._display_edit = False
        view.Draw_Display_Menu()
        self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Display_Menu)
        self.assertTrue(view._list_render['values'][1][1])
        self.event(view, view.ENCODER_DIFF_ENTER, view.HMI_Display_Menu)
        self.assertFalse(view._list_render['values'][1][1])
