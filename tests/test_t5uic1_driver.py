import unittest
from collections import deque

from t5uic1_driver import T5UIC1Display, T5UIC1ProtocolError


class Port:
    def __init__(self):
        self.frames = []
        self.chunks = deque()
        self.closed = 0
        self.short = False

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size=1):
        if not self.chunks:
            return b""
        chunk = self.chunks.popleft()
        value, rest = chunk[:size], chunk[size:]
        if rest:
            self.chunks.appendleft(rest)
        return value

    def write(self, data):
        self.frames.append(bytes(data))
        return len(data) - int(self.short)

    def close(self):
        self.closed += 1


def driver():
    result = T5UIC1Display.__new__(T5UIC1Display)
    result.serial = Port()
    result.MYSERIAL1 = result.serial
    result._closed = False
    result._needs_update = True
    result._defer_updates = False
    result._rx = bytearray()
    result._frames = deque()
    result._aux_rx = deque()
    result._crc_errors = 0
    from threading import Lock
    result._transaction_lock = Lock()
    return result


class T5UIC1DriverPackets(unittest.TestCase):
    def frame(self, operation):
        lcd = driver()
        operation(lcd)
        self.assertEqual(len(lcd.serial.frames), 1)
        return lcd.serial.frames[0]

    def test_configuration_and_interface_opcodes(self):
        self.assertEqual(self.frame(lambda d: d.set_backlight(0x80)),
                         bytes.fromhex("AA 30 80 CC 33 C3 3C"))
        self.assertEqual(self.frame(lambda d: d.set_orientation(2)),
                         bytes.fromhex("AA 34 5A A5 02 CC 33 C3 3C"))
        self.assertEqual(self.frame(lambda d: d.set_aux_baud_divisor(0x0330)),
                         bytes.fromhex("AA 38 03 30 CC 33 C3 3C"))
        self.assertEqual(self.frame(lambda d: d.aux_write(b"123")),
                         bytes.fromhex("AA 39 31 32 33 CC 33 C3 3C"))

    def test_drawing_opcodes_01_02_03_05_08_09(self):
        cases = (
            (lambda d: d.clear(0x001F), "AA 01 00 1F CC 33 C3 3C"),
            (lambda d: d.draw_point(0xF800, 4, 4, 8, 8),
             "AA 02 F8 00 04 04 00 08 00 08 CC 33 C3 3C"),
            (lambda d: d.draw_line(0xFFFF, 0x40, 0x40, 0x100, 0x100),
             "AA 03 FF FF 00 40 00 40 01 00 01 00 CC 33 C3 3C"),
            (lambda d: d.draw_rectangle(2, 0x07E0, 0x40, 0x40, 0x100, 0x100),
             "AA 05 02 07 E0 00 40 00 40 01 00 01 00 CC 33 C3 3C"),
            (lambda d: d.draw_bitmap(4, 4, 8, 0x0000, 0xFFFF, b"\x7C"),
             "AA 08 00 04 00 04 00 08 00 00 FF FF 7C CC 33 C3 3C"),
            (lambda d: d.move_area(0, 0, 8, 0xFFFF, 0x40, 0x40, 0x100, 0x100),
             "AA 09 00 00 08 FF FF 00 40 00 40 01 00 01 00 CC 33 C3 3C"),
        )
        for operation, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.frame(operation), bytes.fromhex(expected))

    def test_text_and_native_number_opcodes(self):
        self.assertEqual(
            self.frame(lambda d: d.draw_text(False, True, 1, 0xFFFF, 0, 0x20, 0x80, "DWIN")),
            bytes.fromhex("AA 11 41 FF FF 00 00 00 20 00 80") + b"DWIN" + T5UIC1Display.TAIL,
        )
        frame = self.frame(lambda d: d.draw_number(
            0x499602D2, show_background=True, zero_fill=False, font=5,
            color=0xFFFF, background=0, integer_digits=10, fractional_digits=2,
            x=0, y=0, byte_length=4,
        ))
        self.assertEqual(frame, bytes.fromhex(
            "AA 14 85 FF FF 00 00 0A 02 00 00 00 00 49 96 02 D2 CC 33 C3 3C"))

    def test_picture_qr_animation_and_barcode_opcodes(self):
        cases = (
            (lambda d: d.draw_qr(8, 8, 4, b"http://x"),
             bytes.fromhex("AA 21 00 08 00 08 04") + b"http://x" + T5UIC1Display.TAIL),
            (lambda d: d.show_jpeg(3), bytes.fromhex("AA 22 00 03 CC 33 C3 3C")),
            (lambda d: d.show_icon(9, (1, 2, 3), 16, 16),
             bytes.fromhex("AA 23 00 10 00 10 89 01 02 03 CC 33 C3 3C")),
            (lambda d: d.show_sram_jpeg(16, 16, 0),
             bytes.fromhex("AA 24 00 10 00 10 80 00 00 CC 33 C3 3C")),
            (lambda d: d.cache_jpeg(1), bytes.fromhex("AA 25 01 01 CC 33 C3 3C")),
            (lambda d: d.copy_cache1(0x40, 0x40, 0x100, 0x100, 0x20, 0x20),
             bytes.fromhex("AA 26 00 40 00 40 01 00 01 00 00 20 00 20 CC 33 C3 3C")),
            (lambda d: d.copy_cache(1, 0x40, 0x40, 0x100, 0x100, 0x40, 0x40,
                                    enhanced=False),
             bytes.fromhex("AA 27 01 00 40 00 40 01 00 01 00 00 40 00 40 CC 33 C3 3C")),
            (lambda d: d.configure_animation(0, True, 9, 0, 9, 16, 16, 10,
                                             restart_from_first=False),
             bytes.fromhex("AA 28 00 10 00 10 80 09 00 09 0A CC 33 C3 3C")),
            (lambda d: d.set_animation_mask(5), bytes.fromhex("AA 29 00 05 CC 33 C3 3C")),
            (lambda d: d.draw_ean13(8, 8, "978753998324"),
             bytes.fromhex("AA 2A 00 08 00 08 09 07 08 07 05 03 09 09 08 03 02 04 CC 33 C3 3C")),
        )
        for operation, expected in cases:
            with self.subTest(expected=expected.hex()):
                self.assertEqual(self.frame(operation), expected)

    def test_memory_write_packets_and_bounds(self):
        lcd = driver()
        lcd.write_sram(0x1234, b"abc")
        self.assertEqual(lcd.serial.frames[-1],
                         bytes.fromhex("AA 31 5A 12 34 61 62 63 CC 33 C3 3C"))
        with self.assertRaises(ValueError):
            lcd.write_sram(T5UIC1Display.SRAM_SIZE, b"x")
        with self.assertRaises(ValueError):
            lcd.write_flash(T5UIC1Display.FLASH_USABLE_SIZE, b"x")
        with self.assertRaises(ValueError):
            lcd.write_flash(T5UIC1Display.FLASH_USABLE_SIZE - 1, b"xx")
        with self.assertRaises(ValueError):
            lcd.read_flash(T5UIC1Display.FLASH_USABLE_SIZE, 1)

    def test_memory_read_response_is_length_driven_not_tail_delimited(self):
        lcd = driver()
        data = b"\x11\xCC\x33\xC3\x3C\x22"
        response = (b"\xAA\x32\x5A\x01\x00" + bytes((len(data),))
                    + data + T5UIC1Display.TAIL)
        lcd.serial.chunks.append(response)
        self.assertEqual(lcd.read_sram(0x0100, len(data)), data)
        self.assertEqual(lcd.serial.frames[-1],
                         bytes.fromhex("AA 32 5A 01 00 06 CC 33 C3 3C"))

    def test_memory_read_uses_single_transaction_at_63_byte_limit(self):
        lcd = driver()
        data = bytes(range(63))
        lcd.serial.chunks.append(
            b"\xAA\x32\x5A\x01\x00\x3F" + data + T5UIC1Display.TAIL
        )

        self.assertEqual(lcd.read_sram(0x0100, 63), data)
        self.assertEqual(
            lcd.serial.frames,
            [bytes.fromhex("AA 32 5A 01 00 3F CC 33 C3 3C")],
        )

    def test_memory_read_chunks_64_bytes_as_63_plus_1(self):
        lcd = driver()
        first = bytes(range(63))
        second = b"\xA5"
        lcd.serial.chunks.append(
            b"\xAA\x32\x5A\x01\x00\x3F" + first + T5UIC1Display.TAIL
        )
        lcd.serial.chunks.append(
            b"\xAA\x32\x5A\x01\x3F\x01" + second + T5UIC1Display.TAIL
        )

        self.assertEqual(lcd.read_sram(0x0100, 64), first + second)
        self.assertEqual(
            lcd.serial.frames,
            [
                bytes.fromhex("AA 32 5A 01 00 3F CC 33 C3 3C"),
                bytes.fromhex("AA 32 5A 01 3F 01 CC 33 C3 3C"),
            ],
        )

    def test_flash_write_picture_write_and_orientation_ack_parsing(self):
        lcd = driver()
        lcd.serial.chunks.append(b"\xAA\x31\xA5OK" + T5UIC1Display.TAIL)
        lcd.write_flash(0, b"x")
        self.assertEqual(lcd.serial.frames[-1],
                         bytes.fromhex("AA 31 A5 00 00 78 CC 33 C3 3C"))

        lcd.serial.chunks.append(b"\xAA\x33OK" + T5UIC1Display.TAIL)
        lcd.store_sram_as_picture(4)
        self.assertEqual(lcd.serial.frames[-1],
                         bytes.fromhex("AA 33 5A A5 04 CC 33 C3 3C"))

        lcd.serial.chunks.append(b"\xAA\x34OK" + T5UIC1Display.TAIL)
        lcd.set_orientation(1, wait_ack=True)

    def test_aux_receive_and_crc_report_are_parsed(self):
        lcd = driver()
        lcd.serial.chunks.append(
            b"noise\xAA\x3A\x03abc" + T5UIC1Display.TAIL
            + b"\xAA\xFF\x01" + T5UIC1Display.TAIL
        )
        self.assertEqual(lcd.poll_aux_data(), b"abc")
        self.assertTrue(lcd.poll_crc_error())
        self.assertFalse(lcd.poll_crc_error())

    def test_payload_limits_and_invalid_fields_fail_before_write(self):
        lcd = driver()
        operations = (
            lambda: lcd.draw_rectangle(3, 0, 0, 0, 1, 1),
            lambda: lcd.draw_bitmap(0, 0, 0, 0, 0, b"x"),
            lambda: lcd.draw_qr(0, 0, 0, b"x"),
            lambda: lcd.draw_ean13(1, 0, "978753998324"),
            lambda: lcd.show_icon(16, 1, 0, 0),
            lambda: lcd.copy_cache(2, 0, 0, 1, 1, 0, 0),
            lambda: lcd.aux_write(b"x" * 249),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()
        self.assertFalse(lcd.serial.frames)

    def test_word_fields_accept_integral_float_but_reject_fraction(self):
        lcd = driver()
        lcd.draw_rectangle(1, 0, 16 + 100 * 240 / 100, 93, 256, 113)
        self.assertEqual(lcd.serial.frames[-1][5:7], bytes.fromhex("01 00"))
        with self.assertRaises(ValueError):
            lcd.draw_rectangle(1, 0, 12.5, 0, 20, 20)

    def test_native_number_accepts_special_font_selectors(self):
        lcd = driver()
        lcd.draw_number(42, font=0x0A, integer_digits=2, byte_length=1)
        self.assertEqual(lcd.serial.frames[-1][2] & 0x0F, 0x0A)
        lcd.draw_number(42, font=0x0F, integer_digits=2, byte_length=1)
        self.assertEqual(lcd.serial.frames[-1][2] & 0x0F, 0x0F)
        with self.assertRaises(ValueError):
            lcd.draw_number(42, font=0x10, integer_digits=2, byte_length=1)


if __name__ == "__main__":
    unittest.main()
