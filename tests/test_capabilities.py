from read_fixture import ImmediateReadWorker
import copy
from concurrent.futures import Future
import tempfile
import unittest
from unittest.mock import Mock, patch

from printer_capabilities import PrinterCapabilities
from printer_state import PrinterState
from test_regressions import backend, ui


def snapshot(hotend=True, bed=True, fan=True, probe=False, multiple=False):
    status = {
        'toolhead': {'position': [0, 0, 0, 0], 'axis_minimum': [-10, -20, -2, 0],
                     'axis_maximum': [250, 260, 350, 0], 'homed_axes': 'xyz', 'max_velocity': 150},
        'gcode_move': {'homing_origin': [0, 0, 0, 0], 'absolute_coordinates': True,
                       'absolute_extrude': True, 'position': [0, 0, 0, 0]},
        'print_stats': {'state': 'standby'},
        'virtual_sdcard': {'is_active': False, 'progress': 0},
        'motion_report': {'live_position': [12.3, 45.6, 7.8, 0],
                          'live_velocity': 83.5, 'live_extruder_velocity': 4.0},
    }
    settings = {'printer': {'kinematics': 'cartesian'}}
    objects = list(status) + ['configfile']
    if hotend:
        settings['extruder'] = {'min_temp': 5, 'max_temp': 305, 'min_extrude_temp': 155,
                                'max_extrude_only_distance': 35, 'filament_diameter': 1.75}
        status['extruder'] = {'temperature': 200, 'target': 205, 'can_extrude': True}
        status['toolhead']['extruder'] = 'extruder'
        objects.append('extruder')
    if multiple:
        settings['extruder1'] = {'min_temp': 0, 'max_temp': 280, 'min_extrude_temp': 120,
                                 'max_extrude_only_distance': 15}
        status['extruder1'] = {'temperature': 190, 'target': 195, 'can_extrude': True}
        status['toolhead']['extruder'] = 'extruder1'
        objects.append('extruder1')
    if bed:
        settings['heater_bed'] = {'min_temp': 5, 'max_temp': 115}
        status['heater_bed'] = {'temperature': 55, 'target': 60}
        objects.append('heater_bed')
    if fan:
        status['fan'] = {'speed': 0.5}
        objects.append('fan')
    if probe:
        objects += ['probe', 'bed_mesh']
        settings['bltouch'] = {'z_offset': 2.3}
    return {'state': 'ready', 'error': None, 'epoch': 1, 'revision': 1,
            'file_revision': 0, 'objects': objects, 'status': status, 'settings': settings}


def printer(data):
    with patch.object(backend, 'MoonrakerClient'), patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
        result = backend.PrinterData(settings_path=tempfile.mktemp(prefix='dwin-test-', suffix='.json'))
    result.check_command_results = Mock()
    result.subscription.snapshot.return_value = data
    result.sendGCode = Mock()
    result.update_variable()
    return result


def display(data):
    result = ui.DWIN_LCD.__new__(ui.DWIN_LCD)
    result.pd = printer(data)
    result.lcd = Mock()
    for name in result.SELECTIONS:
        setattr(result, name, ui.select_t())
    result.index_prepare = result.index_tune = result.MROWS
    result._configure_menus()
    return result


class CapabilityTests(unittest.TestCase):
    def test_effective_limits_and_negative_axis_minimum(self):
        caps = PrinterCapabilities.from_state(PrinterState.from_snapshot(snapshot(probe=True)))
        self.assertEqual(caps.active_hotend.maximum, 305)
        self.assertEqual(caps.active_hotend.min_extrude_temp, 155)
        self.assertEqual(caps.active_hotend.max_extrude_distance, 35)
        self.assertEqual(caps.bed.maximum, 115)
        self.assertEqual(caps.axis_minimum, (-10, -20, -2))
        self.assertEqual(caps.build_size, (260, 280, 352))
        self.assertTrue(caps.fan and caps.probe and caps.bed_mesh)

    def test_missing_devices_are_not_invented(self):
        caps = PrinterCapabilities.from_state(PrinterState.from_snapshot(snapshot(False, False, False)))
        self.assertIsNone(caps.active_hotend)
        self.assertIsNone(caps.bed)
        self.assertFalse(caps.has_heaters or caps.fan or caps.probe)

    def test_heater_fan_is_not_a_part_cooling_fan(self):
        data = snapshot(fan=False)
        data['objects'].append('heater_fan hotend_fan')
        self.assertFalse(PrinterCapabilities.from_state(PrinterState.from_snapshot(data)).fan)

    def test_multiple_hotends_use_active_tool_limits(self):
        data = snapshot(multiple=True)
        result = printer(data)
        self.assertIsNone(result.connection_error)
        self.assertEqual(result.HOTENDS, 2)
        self.assertEqual(result.MAX_E_TEMP, 280)
        self.assertEqual(result.EXTRUDE_MAXLENGTH, 15)
        self.assertEqual(result.thermalManager['temp_hotend'][0]['target'], 195)
        result.setExtTemp(210)
        result.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=210')

    def test_status_temperature_columns_leave_room_for_targets(self):
        result = display(snapshot())
        result.lcd.DWIN_WIDTH = 272
        result.lcd.DWIN_HEIGHT = 480
        result.lcd.reset_mock()
        with patch.object(ui.time, 'monotonic', return_value=0):
            result.Draw_Status_Area(True)
        calls = result.lcd.draw_integer_text.call_args_list
        coordinates = [(call.args[7], call.args[8]) for call in calls]
        self.assertIn((26, 382), coordinates)
        self.assertIn((66, 382), coordinates)
        self.assertIn((26, 416), coordinates)
        self.assertIn((66, 416), coordinates)
        self.assertLess(66 + 3 * result.STAT_CHR_W, 116)

    def test_printer_data_initializes_mmu_before_first_status_update(self):
        with patch.object(backend, 'MoonrakerClient'), \
                patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            result = backend.PrinterData(
                settings_path=tempfile.mktemp(prefix='dwin-test-', suffix='.json'))
        self.assertIsNone(result.mmu)

    def test_spoolman_uses_isolated_transport(self):
        command_client = Mock()
        telemetry_client = Mock()
        with patch.object(backend, 'MoonrakerClient',
                          side_effect=[command_client, telemetry_client]), \
                patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            result = backend.PrinterData(
                settings_path=tempfile.mktemp(prefix='dwin-test-', suffix='.json'))
        result._poll_spoolman_percentages((123,))
        telemetry_client.post.assert_called_once_with(
            '/server/spoolman/proxy',
            {'request_method': 'GET', 'path': '/v1/spool/123'},
            report_error=False)
        command_client.post.assert_not_called()

    def test_failed_spoolman_refresh_clears_stale_percentage(self):
        result = printer(snapshot())
        future = Future()
        future.set_result({'result': {'remaining_weight': None}})
        result._spoolman_percentages[123] = 57
        result._spoolman_futures[123] = future

        changed = result._poll_spoolman_percentages((123,))

        self.assertTrue(changed)
        self.assertNotIn(123, result._spoolman_percentages)

    def test_spoolman_remaining_percentage_uses_initial_weight(self):
        self.assertEqual(
            backend.PrinterData._spool_remaining_percent(
                {'remaining_weight': 580, 'initial_weight': 1000, 'used_weight': 420}),
            58)

    def test_spoolman_remaining_percentage_falls_back_to_used_weight(self):
        self.assertEqual(
            backend.PrinterData._spool_remaining_percent(
                {'remaining_weight': 400, 'used_weight': 600}),
            40)
        self.assertIsNone(
            backend.PrinterData._spool_remaining_percent(
                {'remaining_weight': None, 'used_weight': 0}))

    def test_invalid_mmu_does_not_take_core_printer_offline(self):
        data = snapshot()
        data['objects'].append('mmu')
        data['status']['mmu'] = {
            'num_gates': 4, 'gate': 0,
            'gate_status': [1, 1, 1, 1],
            'gate_color_rgb': [[1.0, 0.0, 0.0]],
        }
        result = printer(data)
        self.assertIsNone(result.connection_error)
        self.assertIsNone(result.mmu)
        self.assertEqual(result.status, 'standby')
        self.assertEqual(result.thermalManager['temp_hotend'][0]['target'], 205)

    def test_happy_hare_mmu_state_is_normalized(self):
        data = snapshot()
        data['objects'].append('mmu')
        data['status']['mmu'] = {
            'num_gates': 4, 'gate': 2, 'unit': 0, 'gate_status': [1, 1, 1, 0],
            'gate_color_rgb': [[0.0, 0.4, 1.0], [1.0, 0.1, 0.0],
                               [0.0, 1.0, 0.2], [1.0, 0.8, 0.0]],
            'gate_spool_id': [-1, -1, -1, -1],
            'filament': 'Loaded',
        }
        data['objects'].append('mmu_machine')
        data['status']['mmu_machine'] = {
            'unit_0': {'name': 'mmu', 'display_name': 'OpenEYE MMU'}
        }
        data['objects'].append('unit0_mmu_exit_leds')
        data['status']['unit0_mmu_exit_leds'] = {
            'color_data': [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                           [0.0, 0.0, 1.0, 0.0], [1.0, 0.5, 0.0, 0.0]]
        }
        result = printer(data)
        self.assertEqual(result.mmu['num_gates'], 4)
        self.assertEqual(result.mmu['gate'], 2)
        self.assertEqual(result.mmu['gate_color_rgb'][2], (0.0, 1.0, 0.2))
        self.assertEqual(result.mmu['name'], 'OpenEYE MMU')
        self.assertEqual(result.mmu['exit_led_rgb'][2], (0.0, 0.0, 1.0))

    def test_happy_hare_mmu_name_uses_selected_unit_metadata(self):
        data = snapshot()
        data['objects'] += ['mmu', 'mmu_machine']
        data['status']['mmu'] = {
            'num_gates': 4, 'gate': 2, 'unit_selected': 1,
            'gate_status': [1, 1, 1, 1],
            'gate_color_rgb': [[0.0, 0.0, 0.0]] * 4,
        }
        data['status']['mmu_machine'] = {
            'unit_0': {'name': 'first', 'display_name': 'First MMU'},
            'unit_1': {'name': 'second', 'display_name': 'OpenEYE MMU'},
        }
        result = printer(data)
        self.assertEqual(result.mmu['name'], 'OpenEYE MMU')

    def test_selected_mmu_unit_uses_matching_exit_led_object(self):
        data = snapshot()
        data['objects'] += ['mmu', 'mmu_machine', 'unit0_mmu_exit_leds',
                            'unit1_mmu_exit_leds']
        data['status']['mmu'] = {
            'num_gates': 2, 'gate': 1, 'unit_selected': 1,
            'gate_status': [1, 1],
            'gate_color_rgb': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        }
        data['status']['mmu_machine'] = {
            'unit_1': {'name': 'second', 'display_name': 'Second MMU'},
        }
        data['status']['unit0_mmu_exit_leds'] = {
            'color_data': [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
        }
        data['status']['unit1_mmu_exit_leds'] = {
            'color_data': [[0.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        }

        result = printer(data)

        self.assertEqual(result.mmu['name'], 'Second MMU')
        self.assertEqual(result.mmu['exit_led_rgb'],
                         ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))

    def test_home_uses_mmu_visual_when_available(self):
        data = snapshot()
        data['objects'].append('mmu')
        data['status']['mmu'] = {
            'num_gates': 4, 'gate': 1, 'gate_status': [1, 1, 1, 1],
            'gate_color_rgb': [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0],
                               [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
        }
        result = display(data)
        result.Clear_Main_Window = Mock()
        result.ICON_Print = result.ICON_Prepare = result.ICON_Control = Mock()
        result.ICON_StartInfo = Mock()
        result.Draw_MMU_Status = Mock()
        result.Goto_MainMenu()
        result.Draw_MMU_Status.assert_called_once()
        self.assertFalse(any(call.args[1] == result.ICON_LOGO
                             for call in result.lcd.show_icon.call_args_list))

    def test_home_keeps_logo_without_mmu(self):
        result = display(snapshot())
        result.Clear_Main_Window = Mock()
        result.ICON_Print = result.ICON_Prepare = result.ICON_Control = Mock()
        result.ICON_StartInfo = Mock()
        result.Goto_MainMenu()
        self.assertTrue(any(call.args[1] == result.ICON_LOGO
                            for call in result.lcd.show_icon.call_args_list))

    def test_mmu_visual_marks_active_gate_and_uses_gate_colors(self):
        result = display(snapshot())
        result.pd.mmu = {
            'num_gates': 4, 'gate': 2, 'gate_status': (1, 1, 1, 0),
            'gate_color_rgb': ((0.0, 0.4, 1.0), (1.0, 0.1, 0.0),
                               (0.0, 1.0, 0.2), (1.0, 0.8, 0.0)),
            'remaining_percent': (3, 40, 70, 58),
            'exit_led_rgb': ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                             (0.0, 0.0, 1.0), (1.0, 0.5, 0.0)),
            'filament': 'Loaded',
        }
        result.lcd.DWIN_WIDTH = 272
        result.lcd.DWIN_HEIGHT = 480
        result.lcd.Color_White = 0xffff
        result.lcd.Color_Bg_Black = 0x0841
        result.lcd.Select_Color = 0x33bb
        result.lcd.font6x12 = 0
        result.Draw_MMU_Status()
        rectangles = result.lcd.draw_rectangle.call_args_list
        self.assertTrue(any(call.args[0] == 1 and call.args[1] == result._rgb565((0.0, 0.0, 1.0))
                            for call in rectangles))
        for led_rgb in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                        (0.0, 0.0, 1.0), (1.0, 0.5, 0.0)):
            self.assertTrue(any(call.args[0] == 1 and call.args[1] == result._rgb565(led_rgb)
                                for call in rectangles))
        fills = [call.args[1] for call in rectangles if call.args[0] == 1]
        self.assertIn(result._rgb565((0.0, 1.0, 0.2)), fills)
        self.assertIn(0x8410, fills)
        self.assertIn(0x9B46, fills)
        self.assertTrue(any(call.args[0] == 0 and call.args[1] == 0xD58A
                            for call in rectangles))
        wood_fills = [call.args for call in rectangles
                      if call.args[0] == 1 and call.args[1] == 0x9B46]
        self.assertTrue(all(args[5] - args[3] == 51 for args in wood_fills))
        self.assertGreater(result.lcd.draw_line.call_count, 0)
        result.lcd.fill_circle.assert_not_called()
        result.lcd.draw_circle.assert_not_called()

    def test_mmu_lane_led_hue_is_normalized_for_lcd_visibility(self):
        result = display(snapshot())
        result.lcd.DWIN_WIDTH = 272
        result.lcd.DWIN_HEIGHT = 480
        result.lcd.Color_White = 0xffff
        result.lcd.Color_Bg_Black = 0x0841
        result.lcd.Select_Color = 0x33bb
        result.lcd.font6x12 = 0
        result.pd.mmu = {
            'num_gates': 1, 'gate': 0, 'gate_status': (1,),
            'gate_color_rgb': ((1.0, 0.0, 0.0),),
            'remaining_percent': (50,), 'exit_led_rgb': ((0.1, 0.0, 0.0),),
            'name': 'MMU', 'filament': 'Loaded',
        }
        result.lcd.draw_rectangle.reset_mock()
        result.Draw_MMU_Status()
        fills = [call.args[1] for call in result.lcd.draw_rectangle.call_args_list
                 if call.args[0] == 1]
        self.assertIn(result._rgb565((1.0, 0.0, 0.0)), fills)
        self.assertNotIn(result._rgb565((0.1, 0.0, 0.0)), fills)

    def test_mmu_lane_number_uses_contrasting_text_color(self):
        result = display(snapshot())
        result.lcd.DWIN_WIDTH = 272
        result.lcd.DWIN_HEIGHT = 480
        result.lcd.Color_White = 0xffff
        result.lcd.Color_Bg_Black = 0x0841
        result.lcd.Select_Color = 0x33bb
        result.lcd.font6x12 = 0
        result.pd.mmu = {
            'num_gates': 2, 'gate': 0, 'gate_status': (1, 1),
            'gate_color_rgb': ((1.0, 1.0, 1.0),) * 2,
            'remaining_percent': (50, 50),
            'exit_led_rgb': ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            'name': 'MMU', 'filament': 'Loaded',
        }
        result.lcd.draw_text.reset_mock()
        result.Draw_MMU_Status()
        labels = [call.args for call in result.lcd.draw_text.call_args_list
                  if call.args[-1] in ('1', '2')]
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0][3], 0x0000)
        self.assertEqual(labels[1][3], result.lcd.Color_White)

    def test_high_gate_count_mmu_lane_indicators_do_not_overlap(self):
        result = display(snapshot())
        count = 12
        result.pd.mmu = {
            'num_gates': count, 'gate': 0,
            'gate_status': (1,) * count,
            'gate_color_rgb': ((0.2, 0.4, 0.8),) * count,
            'remaining_percent': (50,) * count,
            'exit_led_rgb': ((0.0, 1.0, 0.0),) * count,
            'name': 'MMU', 'filament': 'Loaded',
        }
        result.lcd.DWIN_WIDTH = 272
        result.lcd.DWIN_HEIGHT = 480
        result.lcd.Color_White = 0xffff
        result.lcd.Color_Bg_Black = 0x0841
        result.lcd.Line_Color = 0x3a6a
        result.lcd.font6x12 = 0

        result.Draw_MMU_Status()

        indicators = [
            call for call in result.lcd.draw_rectangle.call_args_list
            if call.args[0] == 1 and call.args[3] == 103 and call.args[5] == 117
        ]
        self.assertEqual(len(indicators), count)
        intervals = [(call.args[2], call.args[4]) for call in indicators]
        for previous, current in zip(intervals, intervals[1:]):
            self.assertLess(previous[1], current[0])

    def test_mmu_visual_is_not_redrawn_for_unrelated_status_updates(self):
        result = display(snapshot())
        result.pd.mmu = {
            'num_gates': 4, 'gate': 1, 'gate_status': (1, 1, 1, 1),
            'gate_color_rgb': ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                               (1.0, 1.0, 1.0), (1.0, 0.0, 0.0)),
            'filament': 'Loaded',
        }
        result._drawn_mmu_state = result.pd.mmu
        result.checkkey = result.MainMenu
        result.Draw_MMU_Status = Mock()
        result.Draw_Status_Area = Mock()
        result.pd.update_variable = Mock(return_value=True)
        result.pd.connection_error = None
        result._configure_menus = Mock(return_value=False)
        result._poll_action = Mock(return_value=False)
        result.pd.probe_wizard.update = Mock()
        result._poll_print_start = Mock(return_value=False)
        result.last_status = result.pd.status
        result.lcd.update = Mock()
        result.EachMomentUpdate()
        result.Draw_MMU_Status.assert_not_called()

    def test_live_dashboard_telemetry_uses_motion_report(self):
        data = snapshot()
        data['status']['gcode_move']['speed_factor'] = 1.25
        data['status']['gcode_move']['extrude_factor'] = 0.95
        result = printer(data)
        self.assertEqual(result.feedrate_percentage, 125)
        self.assertEqual(result.flow_percentage, 95)
        self.assertEqual(result.live_position, (12.3, 45.6, 7.8))
        self.assertEqual(result.live_velocity, 83.5)
        self.assertEqual(result.live_extruder_velocity, 4.0)
        self.assertAlmostEqual(result.volumetric_flow,
                               4.0 * 3.141592653589793 * (1.75 / 2.0) ** 2)
        self.assertEqual(result.dashboard_fan_pwm, 128)

    def test_dashboard_falls_back_when_motion_report_is_missing(self):
        data = snapshot()
        del data['status']['motion_report']
        data['objects'].remove('motion_report')
        result = printer(data)
        self.assertEqual(result.live_position, (0.0, 0.0, 0.0))
        self.assertEqual(result.live_velocity, 0.0)
        self.assertEqual(result.volumetric_flow, 0.0)

    def test_zero_target_allowed_and_configured_limits_enforced(self):
        result = printer(snapshot())
        result.setExtTemp(0)
        result.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0')
        result.sendGCode.reset_mock()
        for target in (1, 306, float('nan')):
            with self.assertRaises(ValueError):
                result.setExtTemp(target)
        with self.assertRaises(ValueError):
            result.setBedTemp(116)
        result.sendGCode.assert_not_called()

    def test_missing_limits_block_state_and_commands(self):
        data = snapshot()
        del data['settings']['extruder']['max_temp']
        result = printer(data)
        self.assertIsNotNone(result.connection_error)
        self.assertFalse(result.HAS_HOTEND)
        with self.assertRaises(ValueError):
            result.setExtTemp(200)
        result.sendGCode.assert_not_called()

    def test_invalid_preset_is_validated_before_any_heating(self):
        result = printer(snapshot())
        with self.assertRaises(ValueError):
            result.preHeat(60, 400)
        result.sendGCode.assert_not_called()

    def test_bed_only_preheat_never_addresses_absent_hotend(self):
        result = printer(snapshot(hotend=False))
        result.preHeat(60, 200)
        result.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=60')

    def test_new_connection_replaces_hardware_capabilities(self):
        result = printer(snapshot())
        result.subscription.snapshot.return_value = snapshot(False, False, False)
        self.assertTrue(result.update_variable())
        self.assertFalse(result.HAS_HOTEND or result.HAS_HEATED_BED or result.HAS_FAN)
        self.assertEqual(result.thermalManager['temp_hotend'][0]['target'], 0)


class CapabilityMenuTests(unittest.TestCase):
    def test_rows_are_unique_and_compact_for_device_combinations(self):
        for hotend in (False, True):
            for bed in (False, True):
                for fan in (False, True):
                    with self.subTest(hotend=hotend, bed=bed, fan=fan):
                        result = display(snapshot(hotend, bed, fan))
                        for name in ('temperature', 'tune', 'preheat'):
                            keys = [entry[0] for entry in result._menus[name]]
                            self.assertEqual(len(keys), len(set(keys)))
                            self.assertEqual('TEMP' in keys, hotend)
                            self.assertEqual('BED' in keys, bed)
                            self.assertEqual('FAN' in keys, fan and name != 'preheat')
                        if bed and fan:
                            self.assertNotEqual(result.TEMP_CASE_BED, result.TEMP_CASE_FAN)

    def test_scroll_draws_only_visible_rows(self):
        result = display(snapshot())
        result.index_prepare = result.PREPARE_CASE_TOTAL
        result.select_prepare.set(result.PREPARE_CASE_TOTAL)
        result.Draw_Menu_Line = Mock()
        result.Draw_Prepare_Menu()
        rows = [call.args[0] for call in result.Draw_Menu_Line.call_args_list]
        self.assertEqual(rows, list(range(6)))

    def test_temperature_scroll_uses_temperature_offset(self):
        result = display(snapshot())
        result.pd.material_preset = [
            type('Preset', (), {'name': 'Preset %d' % i, 'hotend_temp': 200, 'bed_temp': 60})()
            for i in range(6)
        ]
        result.pd.preset_revision += 1
        result._configure_menus()
        result.index_temp = result.TEMP_CASE_TOTAL
        result.select_temp.set(result.TEMP_CASE_TOTAL)
        result.Draw_Menu_Line = Mock()
        result.Draw_Temperature_Menu()
        rows = [call.args[0] for call in result.Draw_Menu_Line.call_args_list]
        self.assertEqual(rows, list(range(6)))

    def test_preset_refresh_resets_temperature_selection(self):
        result = display(snapshot())
        result.checkkey = result.PLAPreheat
        result.pd.preset_revision += 1
        result.select_temp.set(2)
        result._configure_menus()
        self.assertEqual(result.checkkey, result.TemperatureID)
        self.assertEqual(result.select_temp.now, 0)

    def test_probe_detection_does_not_start_old_calibration_flow(self):
        result = display(snapshot(probe=True))
        result.select_prepare.set(result.PREPARE_CASE_ZOFF)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.pd.probe_calibrate = Mock()
        result.HMI_Prepare()
        result.pd.probe_calibrate.assert_not_called()
        self.assertEqual(result.checkkey, result.Homeoffset)

    def test_info_screen_renders_live_stack_and_network_details(self):
        result = display(snapshot())
        result.pd.refresh_system_info = Mock(return_value=False)
        result.pd.system_info = {
            'klipperdwin': 'v0.4.0-2-g1234abcd', 'moonraker': 'v0.9.3-1-gabcd',
            'mainsail': 'v2.14.0', 'network': 'Online', 'ip': '192.168.1.50',
            'host_cpu': 37.2, 'host_temp': 48.5,
            'mcus': ({'name': 'mcu', 'load': 1.2, 'temperature': 42.5, 'version': 'v1'},
                     {'name': 'mmu', 'load': 0.4, 'temperature': None, 'version': 'v2'}),
        }
        result.pd.SHORT_BUILD_VERSION = 'v0.13.0-123'
        result.pd.MACHINE_SIZE = '220x220x250'
        items = result._info_items()
        self.assertIn(('row', 'Size', '220x220x250'), items)
        self.assertIn(('row', 'CPU', '37%'), items)
        self.assertIn(('section', 'MCU: mcu', None), items)
        self.assertIn(('row', 'Load', '1.2%'), items)
        self.assertIn(('row', 'Temp', '42.5 C'), items)
        self.assertIn(('section', 'MCU: mmu', None), items)
        self.assertIn(('row', 'Temp', 'N/A'), items)
        result.Draw_Info_Menu()
        self.assertGreater(len(items), 11)

    def test_info_encoder_scrolls_and_enter_returns(self):
        result = display(snapshot())
        result.pd.system_info['mcus'] = tuple(
            {'name': 'mcu%d' % i, 'load': i, 'temperature': None, 'version': ''}
            for i in range(4))
        result.Draw_Info_Menu = Mock()
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CW)
        result.HMI_Info()
        self.assertEqual(result._info_scroll, 1)
        result.Draw_Info_Menu.assert_called_once_with()

    def test_case_light_uses_dedicated_light_icon_alias(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        entry = next(item for item in result._menus['control'] if item[0] == 'LIGHT')
        self.assertEqual(entry[2], result.ICON_CaseLight)
        self.assertEqual(result.ICON_CaseLight, result.ICON_Motion)

    def test_case_light_is_hidden_without_m355_macro(self):
        result = display(snapshot())
        keys = [entry[0] for entry in result._menus['control']]
        self.assertNotIn('LIGHT', keys)
        self.assertEqual(result.CONTROL_CASE_LIGHT, -1)

    def test_case_light_is_visible_with_m355_macro(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        keys = [entry[0] for entry in result._menus['control']]
        self.assertIn('LIGHT', keys)
        self.assertLess(keys.index('MOVE'), keys.index('LIGHT'))
        self.assertLess(keys.index('LIGHT'), keys.index('INFO'))

    def test_case_light_opens_submenu_and_queries_initial_state(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        keys = [entry[0] for entry in result._menus['control']]
        self.assertIn('LIGHT', keys)
        self.assertLess(keys.index('MOVE'), keys.index('LIGHT'))
        self.assertLess(keys.index('LIGHT'), keys.index('INFO'))
        result.pd.query_case_light = Mock()
        result.Draw_Case_Light_Menu = Mock()
        result.select_control.set(result.CONTROL_CASE_LIGHT)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Control()
        self.assertEqual(result.checkkey, result.CaseLight)
        result.pd.query_case_light.assert_called_once_with()

    def test_case_light_query_parses_on_and_brightness(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        result.checkkey = result.CaseLight
        result._case_light_query_pending = True
        result.pd.pop_gcode_response = Mock(side_effect=['info Light is ON, Brightness=255'])
        result.Draw_Case_Light_Menu = Mock()
        self.assertTrue(result._poll_case_light_query())
        self.assertTrue(result._case_light_on)
        self.assertEqual(result._case_light_brightness, 100)
        self.assertFalse(result._case_light_query_pending)

    def test_case_light_toggle_waits_for_success_and_fresh_query(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        result._case_light_on = True
        result.Draw_Case_Light_Menu = Mock()
        result._restore_action_screen = Mock()
        result.HMI_AudioFeedback = Mock()
        result.pd.query_case_light = Mock()
        future = Future()
        future.set_result({'result': 'ok'})
        result.pd.sendGCode = Mock(return_value=future)

        result.select_light.set(1)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Case_Light()

        result.pd.sendGCode.assert_called_once_with('M355 S0')
        self.assertTrue(result._case_light_on)
        self.assertFalse(result._poll_action())
        result.pd.query_case_light.assert_called_once_with()
        self.assertTrue(result._case_light_on)

    def test_case_light_brightness_waits_for_success_and_fresh_query(self):
        result = display(snapshot())
        result._case_light_brightness = 25
        result._case_light_brightness_target = 50
        result.checkkey = result.CaseLightBrightness
        result._restore_action_screen = Mock()
        result.HMI_AudioFeedback = Mock()
        result.pd.query_case_light = Mock()
        future = Future()
        future.set_result({'result': 'ok'})
        result.pd.sendGCode = Mock(return_value=future)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)

        result.HMI_Case_Light_Brightness()

        result.pd.sendGCode.assert_called_once_with('M355 P128')
        self.assertEqual(result._case_light_brightness, 25)
        self.assertFalse(result._poll_action())
        result.pd.query_case_light.assert_called_once_with()
        self.assertEqual(result._case_light_brightness, 25)
    def test_case_light_brightness_response_converts_raw_to_percent(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        result.checkkey = result.CaseLight
        result._case_light_query_pending = True
        result.pd.pop_gcode_response = Mock(side_effect=[
            'info Light is OFF, Brightness=128'])
        result.Draw_Case_Light_Menu = Mock()
        result._poll_case_light_query()
        self.assertEqual(result._case_light_brightness, 50)

    def test_case_light_brightness_editor_clamps_percent_range(self):
        data = snapshot()
        data['objects'].append('gcode_macro M355')
        result = display(data)
        result._case_light_brightness_target = 100
        result._encoder_move_value = 10
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CW)
        result.HMI_Case_Light_Brightness()
        self.assertEqual(result._case_light_brightness_target, 100)

        result._case_light_brightness_target = 0
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CCW)
        result.HMI_Case_Light_Brightness()
        self.assertEqual(result._case_light_brightness_target, 0)

    def test_fan_edit_uses_percentage_scale(self):
        result = display(snapshot())
        result.pd.HMI_ValueStruct.show_mode = -1
        result.pd.HMI_ValueStruct.Fan_speed = 50
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_FanSpeed()
        result.pd.sendGCode.assert_called_once_with('M106 S127.5')
