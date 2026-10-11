import unittest
from unittest.mock import patch

from test_t5uic1_driver import driver
from test_uart import Driver, Port, serial_module


class PacketTests(unittest.TestCase):
    def test_sram_write_and_jpeg_display_packets(self):
        result = driver()
        result.write_sram(0x1234, b'\xff\xd8\xff')
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 31 5A 12 34 FF D8 FF CC 33 C3 3C'))
        result.show_sram_jpeg(72, 80)
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 24 00 48 00 50 80 00 00 CC 33 C3 3C'))
        result.write_sram(32640, b'x' * 128)
        for address, data in ((-1, b'x'), (32768, b'x'), (32767, b'xx'), (0, b'')):
            with self.assertRaises(ValueError):
                result.write_sram(address, data)
        for x, y, address in ((0, 0, 32768),):
            with self.assertRaises(ValueError):
                result.show_sram_jpeg(x, y, address)
        self.assertEqual(len(result.serial.frames), 3)

    def test_numeric_compatibility_renderer_preserves_current_ui_packets(self):
        result = driver()
        result.draw_scaled_float_text(True, False, False, 1, 0xFFFF, 0, 3, 1, 10, 20, -15.5)
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 11 41 FF FF 00 00 00 02 00 14') + b'  -1.6' + Driver.TAIL)
        result.draw_scaled_float_text(True, False, False, 1, 0xFFFF, 0, 3, 1, 10, 20, 15.5)
        self.assertEqual(result.serial.frames[-1][11:-4], b'   1.6')

    def test_integer_compatibility_renderer_is_padded_text(self):
        result = driver()
        result.draw_integer_text(True, True, False, 1, 0xFFFF, 0, 3, 10, 20, 5)
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 11 41 FF FF 00 00 00 0A 00 14') + b'  5' + Driver.TAIL)

    def test_signed_wrapper_emits_one_complete_field(self):
        result = driver()
        result.draw_signed_scaled_float_text(2, 0, 2, 2, 30, 20, -125)
        self.assertEqual(result.serial.frames[-1][11:-4], b' -1.25')
        self.assertEqual(len(result.serial.frames), 1)

    def test_icon_and_copy_flags_follow_proui_transparency(self):
        result = driver()
        result.show_icon(7, 1, 10, 20)
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 23 00 0A 00 14 87 01 CC 33 C3 3C'))
        result.copy_cache(1, 0, 0, 10, 20, 30, 40)
        self.assertEqual(result.serial.frames[-1], bytes.fromhex(
            'AA 27 21 00 00 00 00 00 0A 00 14 00 1E 00 28 CC 33 C3 3C'))

    def test_startup_wakes_then_handshakes_and_sets_direction_without_jpg(self):
        port = Port([b'\xAA\x00OK' + Driver.TAIL])
        with patch.object(serial_module, 'Serial', return_value=port, create=True), \
                patch.object(Driver.__init__.__globals__['time'], 'sleep') as sleep, \
                patch('icon_library.sync_library') as sync:
            result = Driver('/dev/fake')
        self.assertEqual(sleep.call_args_list[0].args, (0.750,))
        sync.assert_called_once_with(result)
        self.assertEqual(port.frames, [bytes.fromhex(frame) for frame in (
            'AA 00 CC 33 C3 3C',
            'AA 34 5A A5 01 CC 33 C3 3C',
            'AA 3D CC 33 C3 3C')])
        result.close()

    def test_update_only_flushes_pending_draws_and_failed_flush_stays_dirty(self):
        result = driver()
        result.update()
        result.update()
        self.assertEqual(len(result.serial.frames), 1)
        result.clear(0)
        result.draw_line(0xFFFF, 0, 0, 10, 10)
        result.update()
        result.update()
        self.assertEqual([frame[1] for frame in result.serial.frames], [0x3D, 1, 3, 0x3D])
        result.clear(0)
        result.serial.short = True
        with self.assertRaises(IOError):
            result.update()
        self.assertTrue(result._needs_update)

    def test_text_transliterates_turkish_and_bounds_visible_field(self):
        result = driver()
        result.draw_text(False, True, 1, 0xFFFF, 0, 0, 0, 'İşık ölçümü: ğüşçöı😀\n')
        self.assertEqual(result.serial.frames[-1][11:-4], b'Isik olcumu: guscoi??')
        result.draw_text(False, True, 0, 0, 0, 0, 0, 'x' * 10000)
        self.assertEqual(len(result.serial.frames[-1][11:-4]), 45)
        result.draw_text(False, True, 1, 0, 0, 256, 0, 'abcd')
        self.assertEqual(result.serial.frames[-1][11:-4], b'ab')
        count = len(result.serial.frames)
        result.draw_text(False, True, 1, 0, 0, 272, 0, 'abcd')
        self.assertEqual(len(result.serial.frames), count)

    def test_decimal_field_roundtrip_uses_same_position_and_width(self):
        result = driver()
        for value, expected in ((-125, b' -1.25'), (125, b'  1.25'),
                                (0, b'  0.00'), (9999, b' 99.99')):
            result.draw_signed_scaled_float_text(1, 0, 2, 2, 100, 20, value)
            frame = result.serial.frames[-1]
            self.assertEqual(frame[7:11], bytes.fromhex('00 5C 00 14'))
            self.assertEqual(frame[11:-4], expected)
        result.draw_signed_scaled_float_text(1, 0, 2, 2, 100, 20, 9999.5)
        self.assertEqual(result.serial.frames[-1][11:-4], b'######')


if __name__ == '__main__':
    unittest.main()
