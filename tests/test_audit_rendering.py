import unittest
from test_capabilities import display, snapshot
from test_t5uic1_driver import driver


class AuditRenderingTests(unittest.TestCase):
    def screen(self):
        result = display(snapshot())
        result.lcd = driver()
        return result

    def test_mcu_headings_use_native_library_chip_including_unavailable_heading(self):
        result = self.screen()
        for label in ('MCU: mcu', 'MCU: mmu', 'MCU'):
            with self.subTest(label=label):
                result.lcd.serial.frames.clear()
                result._draw_info_section(label, 140)
                icons = [f for f in result.lcd.serial.frames if f[1] == 0x23]
                self.assertEqual(icons, [bytes.fromhex('AA 23 00 08 00 8A 23 67 CC 33 C3 3C')])
                self.assertFalse(any(f[1] == 0x27 for f in result.lcd.serial.frames))

    def test_machine_host_software_headings_use_native_library_ids(self):
        result = self.screen()
        for label, icon in (('Machine', 104), ('Host', 105), ('Software', 106)):
            with self.subTest(label=label):
                result.lcd.serial.frames.clear()
                result._draw_info_section(label, 140)
                icons = [f for f in result.lcd.serial.frames if f[1] == 0x23]
                self.assertEqual(icons, [bytes.fromhex('AA 23 00 08 00 8A 23') + bytes((icon,)) + result.lcd.TAIL])
                self.assertFalse(any(f[1] == 0x27 for f in result.lcd.serial.frames))

    def test_clock_is_larger_right_aligned_and_deduplicated(self):
        from unittest.mock import patch
        from test_regressions import ui
        result = self.screen()
        result._header_clock_drawn = None
        result.lcd.serial.frames.clear()
        with patch.object(ui.time, 'strftime', return_value='12:34'):
            self.assertTrue(result._draw_header_clock())
            frames = list(result.lcd.serial.frames)
            self.assertFalse(result._draw_header_clock())
        self.assertEqual(result.lcd.serial.frames, frames)
        text = next(f for f in frames if f[1] == 0x11)
        self.assertEqual(text[2] & 15, result.lcd.font8x16)
        self.assertEqual(text[7:11], bytes.fromhex('00 E0 00 06'))

    def test_title_does_not_draw_removed_power_icon(self):
        result = self.screen()
        result.lcd.serial.frames.clear()
        result.Draw_Title('Prepare')
        icons = [f for f in result.lcd.serial.frames if f[1] == 0x23]
        self.assertEqual(icons, [])
        self.assertFalse(any(f[1] == 0x27 for f in result.lcd.serial.frames))

    def test_complete_progress_has_three_digits_before_percent_sign(self):
        result = self.screen()
        result.Draw_Print_ProgressBar(100)
        text = [f for f in result.lcd.MYSERIAL1.frames if f[1] == 0x11]
        self.assertEqual(text[0][11:-4], b'100%')
        self.assertEqual(int.from_bytes(text[0][7:9], 'big'), 120)

    def test_print_time_formats_completed_minutes_and_long_prints(self):
        result = self.screen()
        for seconds, expected in ((0, b'00:00'), (3599, b'00:59'), (3600, b'01:00'),
                                  (359999, b'99:59'), (360000, b'100:00')):
            result.pd.duration = lambda: seconds
            result.Draw_Print_ProgressElapsed()
            self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], expected)

    def test_near_zero_negative_does_not_leave_minus_sign(self):
        result = self.screen()
        result.lcd.draw_signed_scaled_float_text(1, 0, 2, 2, 100, 20, -.1)
        self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], b'  0.00')

    def test_thermal_editor_draw_is_flushed_by_input_owner(self):
        from ui_events import InputEvent
        from unittest.mock import Mock
        result = self.screen()
        result._closed = False
        result._encoder_event = result.ENCODER_DIFF_NO
        result._dispatch_input = lambda: result.lcd.draw_integer_text(True, True, 0, 1, 0xFFFF, 0, 3, 216, 50, 205)
        result._process_input(InputEvent('press', 1, 1))
        self.assertEqual([frame[1] for frame in result.lcd.MYSERIAL1.frames], [0x11, 0x3D])

    def test_info_long_version_and_unicode_fields_have_visible_coordinates(self):
        result = self.screen()
        result.pd.refresh_system_info = lambda: False
        result.pd.system_info = {
            'petrel': 'v' * 100, 'moonraker': 'm' * 100,
            'mainsail': 'Ölçüm' * 20, 'network': 'Online', 'ip': '192.168.100.200',
            'host_cpu': 99.9, 'host_temp': 52.75,
            'mcus': ({'name': 'toolhead-µcu-with-long-name', 'load': 12.34,
                      'temperature': 44.4, 'version': 'v' * 100},),
        }
        result.pd.SHORT_BUILD_VERSION = 'k' * 100
        result.pd.MACHINE_SIZE = '999x999x999'
        for scroll in (0, 5, 9):
            result._info_scroll = scroll
            result.lcd.MYSERIAL1.frames.clear()
            result.Draw_Info_Menu()
            frames = [frame for frame in result.lcd.MYSERIAL1.frames if frame[1] == 0x11]
            values = [frame for frame in frames if int.from_bytes(frame[7:9], 'big') == 128]
            for frame in values:
                self.assertLessEqual(len(frame[11:-4]), 17)
                self.assertLessEqual(128 + len(frame[11:-4]) * result.MENU_CHR_W,
                                     result.lcd.DWIN_WIDTH)
                self.assertLess(int.from_bytes(frame[9:11], 'big'), 360)

    def test_large_printer_values_show_overflow_without_changing_target(self):
        result = self.screen()
        result.pd.feedrate_percentage = 1000
        result.pd.thermalManager['temp_hotend'][0]['target'] = 1200
        result.Draw_Status_Area(False)
        self.assertTrue(any(frame[11:-4] == b'###' for frame in result.lcd.MYSERIAL1.frames if frame[1] == 0x11))
        self.assertEqual(result.pd.feedrate_percentage, 1000)
        self.assertEqual(result.pd.thermalManager['temp_hotend'][0]['target'], 1200)
        result.lcd.draw_signed_scaled_float_text(1, 0, 3, 1, 216, 50, 1234567890)
        self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], b'######')
        result.lcd.draw_signed_scaled_float_text(1, 0, 3, 1, 216, 50, 5)
        self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], b'   0.5')

    def test_negative_integer_sign_transition_clears_entire_field(self):
        result = self.screen()
        for value, expected in ((-5, b' -5'), (5, b'  5'), (-999, b'###')):
            result.lcd.draw_integer_text(True, True, 0, 1, 0xFFFF, 0, 3, 33, 50, value)
            self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], expected)

    def test_motion_value_is_complete_scientific_text_with_fixed_padding(self):
        result = self.screen()
        result.checkkey = result.Motion
        result.pd.motion_settings = lambda: (('max_accel', 'ACCEL', 'Accel', 10, 1234567890123),)
        result.Draw_Motion_Menu()
        frames = [frame for frame in result.lcd.MYSERIAL1.frames if frame[1] == 0x11]
        self.assertEqual(frames[-1][11:-4], b' 1.23e+12')
        self.assertEqual(int.from_bytes(frames[-1][7:9], 'big'), 168)
        self.assertLessEqual(168 + 9 * result.MENU_CHR_W, 240)

    def test_extreme_finite_numbers_render_marker_without_decimal_overflow(self):
        result = self.screen()
        for value in (1e300, -1e300, 10**100):
            result.lcd.draw_integer_text(True, True, 0, 1, 0xFFFF, 0, 3, 33, 50, value)
            self.assertEqual(result.lcd.MYSERIAL1.frames[-1][11:-4], b'###')

    def test_move_menu_and_editor_use_same_command_coordinates(self):
        data = snapshot()
        data['status']['toolhead']['position'] = [91, 92, 93, 94]
        data['status']['gcode_move']['position'] = [-1.5, 12.3, 2.5, -4.5]
        result = self.screen()
        result.pd.subscription.snapshot.return_value = data
        result.pd.update_variable()
        result.Draw_Move_Menu()
        frames = [f for f in result.lcd.MYSERIAL1.frames if f[1] == 0x11]
        rendered = [f[11:-4].strip() for f in frames
                    if int.from_bytes(f[7:9], 'big') == 208
                    and int.from_bytes(f[9:11], 'big') in (102, 155, 208, 261)]
        self.assertEqual(rendered, [b'-1.5', b'12.3', b'2.5', b'-4.5'])
        result.select_axis.set(1)
        result.get_encoder_state = lambda: result.ENCODER_DIFF_ENTER
        result.HMI_AxisMove()
        self.assertEqual(result.pd.HMI_ValueStruct.Move_X_scale, -15)
        frames = [f for f in result.lcd.MYSERIAL1.frames if f[1] == 0x11]
        self.assertEqual(frames[-1][11:-4].strip(), b'-1.5')
        result.pd.sendGCode.assert_not_called()

    def test_move_menu_without_hotend_draws_only_xyz(self):
        result = display(snapshot(hotend=False))
        result.Draw_Move_Menu()
        self.assertEqual(result.lcd.draw_scaled_float_text.call_count, 3)
        result.lcd.draw_signed_scaled_float_text.assert_not_called()


def test_user_visible_labels_do_not_depend_on_frame_copy_assets():
    source = Path(__file__).resolve().parents[1].joinpath('petrel_ui.py').read_text()
    legacy_text_fragments = (
        'Frame_TitleCopy(',
        'copy_cache(1, 226, 179, 256, 189',  # Back
        'copy_cache(1, 69, 61, 102, 71',     # Move
        'copy_cache(1, 1, 451, 31, 463',     # Print
        'copy_cache(1, 33, 451, 82, 466',    # Prepare
        'copy_cache(1, 85, 451, 132, 463',   # Control
        'copy_cache(1, 132, 451, 159, 466',  # Info
        'copy_cache(1, 103, 59, 200, 74',    # Disable steppers
        'copy_cache(1, 202, 61, 271, 71',    # Auto home
    )
    assert not any(fragment in source for fragment in legacy_text_fragments)
