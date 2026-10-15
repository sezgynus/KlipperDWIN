"""Subscribed values must repaint idle menus without encoder navigation."""
import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot


class MenuLiveValueTests(unittest.TestCase):
    def view(self, data):
        view = display(data)
        view.last_status = view.pd.status
        view.Draw_Status_Area = Mock()
        view._encoder_move_value = 1
        view._action = Mock()
        return view

    def publish(self, view, data):
        view.pd.subscription._publish(data)
        view.EachMomentUpdate()

    def test_confirmed_fan_value_updates_without_navigation(self):
        data = snapshot()
        data['status']['fan']['speed'] = .07
        view = self.view(data)
        view.checkkey = view.TemperatureID
        view.select_temp.set(view.TEMP_CASE_FAN)
        view.Draw_Temperature_Menu()
        view.pd.HMI_ValueStruct.show_mode = -1
        view._open_thermal_editor('FAN', view.TEMP_CASE_FAN)
        view.pd.HMI_ValueStruct.Fan_speed = 8
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.HMI_FanSpeed()
        self.assertEqual(view._list_render['values'][view.TEMP_CASE_FAN], 7)
        view.lcd.reset_mock()
        data['status']['fan']['speed'] = .08
        self.publish(view, data)
        self.assertEqual(view._list_render['values'][view.TEMP_CASE_FAN], 8)
        view.lcd.draw_integer_text.assert_called_once()
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[-1], 8)
        view.lcd.move_area.assert_not_called()
        self.assertEqual(view.select_temp.now, view.TEMP_CASE_FAN)

    def test_heater_targets_follow_subscription_and_only_repaint_changed_rows(self):
        data = snapshot()
        view = self.view(data)
        view.checkkey = view.TemperatureID
        view.Draw_Temperature_Menu()
        view.Draw_Menu_Line = Mock()
        data['status']['extruder']['target'] = 200
        data['status']['heater_bed']['target'] = 65
        self.publish(view, data)
        self.assertEqual(view._list_render['values'][view.TEMP_CASE_TEMP], 200)
        self.assertEqual(view._list_render['values'][view.TEMP_CASE_BED], 65)
        self.assertEqual([c.args[0] for c in view.Draw_Menu_Line.call_args_list], [1, 2])
        view.lcd.reset_mock()
        view.Draw_Menu_Line.reset_mock()
        data['status']['extruder']['temperature'] += 1
        self.publish(view, data)
        view.Draw_Menu_Line.assert_not_called()
        view.lcd.draw_integer_text.assert_not_called()

    def test_scrolled_temperature_menu_keeps_visible_value_coordinates(self):
        data = snapshot()
        view = self.view(data)
        view.checkkey = view.TemperatureID
        view.index_temp = view.MROWS + 1
        view.select_temp.set(view.TEMP_CASE_FAN)
        view.Draw_Temperature_Menu()
        view.lcd.reset_mock()
        data['status']['fan']['speed'] = .4
        self.publish(view, data)
        view.lcd.draw_integer_text.assert_called_once()
        self.assertEqual(view.lcd.draw_integer_text.call_args.args[8:],
                         (view.MBASE(view.TEMP_CASE_FAN - 1), 40))
        self.assertEqual(view._list_render['start'], 1)

    def test_move_menu_tracks_all_axes_after_subscription_echo(self):
        for index in range(4):
            with self.subTest(axis=index):
                data = snapshot()
                view = self.view(data)
                view.checkkey = view.AxisMove
                view.Draw_Move_Menu()
                view.Draw_Menu_Line = Mock()
                data['status']['gcode_move']['position'][index] = 12.3
                self.publish(view, data)
                self.assertEqual(view._list_render['values'][index + 1], 123)
                view.Draw_Menu_Line.assert_called_once()
                self.assertEqual(view.Draw_Menu_Line.call_args.args[0], index + 1)

    def test_live_refresh_does_not_overwrite_active_thermal_drafts(self):
        for key, attr, handler in (('FAN', 'Fan_speed', 'FanSpeed'),
                                   ('TEMP', 'E_Temp', 'ETemp'),
                                   ('BED', 'Bed_Temp', 'BedTemp')):
            with self.subTest(key=key):
                data = snapshot()
                view = self.view(data)
                view.pd.HMI_ValueStruct.show_mode = -1
                view.Draw_Temperature_Menu()
                view._open_thermal_editor(key, getattr(view, 'TEMP_CASE_' + key))
                setattr(view.pd.HMI_ValueStruct, attr, 42)
                view.lcd.reset_mock()
                data['status']['fan']['speed'] = .3
                data['status']['extruder']['target'] = 200
                data['status']['heater_bed']['target'] = 60
                self.publish(view, data)
                self.assertEqual(view.checkkey, getattr(view, handler))
                self.assertEqual(getattr(view.pd.HMI_ValueStruct, attr), 42)
                view.lcd.draw_integer_text.assert_not_called()
