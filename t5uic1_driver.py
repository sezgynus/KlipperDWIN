"""Complete UART driver for DWIN T5UIC1 instruction-set displays.

The class in this module is deliberately limited to panel/protocol concerns.
UI layout and rendering policy live above it.  The public methods map directly
onto the T5UIC1 v2.3 instruction set, with a small set of compatibility
renderers used by KlipperDWIN to preserve its current visual output.
"""

import hashlib
import logging
import math
import struct
import time
import unicodedata
from collections import deque
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import Lock

import display_settings
import lcd_atlas
import serial


class T5UIC1ProtocolError(RuntimeError):
    """Raised when a panel response is malformed or does not match a request."""


class T5UIC1TimeoutError(TimeoutError):
    """Raised when an expected T5UIC1 response is not received in time."""


class T5UIC1Display:
    HEADER = b"\xAA"
    TAIL = b"\xCC\x33\xC3\x3C"

    WIDTH = 272
    HEIGHT = 480
    SRAM_SIZE = 32 * 1024
    FLASH_SIZE = 16 * 1024
    # Physical validation on the reference panel shows that address 0x3FFF
    # does not respond to 0x32 reads and causes writes spanning it to receive
    # no acknowledgement. Keep the documented 16 KiB size, but expose only
    # 0x0000..0x3FFE through the runtime Data Flash API.
    FLASH_USABLE_SIZE = FLASH_SIZE - 1
    MEMORY_SRAM = 0x5A
    MEMORY_FLASH = 0xA5
    MAX_DATA_LENGTH = 248
    MEMORY_WRITE_CHUNK = 128
    # Use conservative read transactions on the reference panel. The earlier
    # 0x40-byte failure was observed at 0x3FC0 and therefore crossed the
    # non-responsive 0x3FFF boundary; it does not establish a 0x3F protocol
    # maximum. The T5UIC1 guide documents 0x01..0xF0 for opcode 0x32.
    MEMORY_READ_CHUNK = 0x3F

    # KlipperDWIN owns the beginning of Data Flash for atlas version metadata.
    # Keeping this record away from the panel's non-responsive 0x3FFF address
    # also makes the 64-byte verification read unambiguous.
    ATLAS_METADATA_SIZE = 64
    DISPLAY_SETTINGS_ADDRESS = 0x0100
    DISPLAY_SETTINGS_SIZE = display_settings.RECORD_SIZE
    ATLAS_METADATA_ADDRESS = 0x0000
    ATLAS_METADATA_MAGIC = b"KDWATLS1"
    ATLAS_METADATA_VERSION = 1
    ATLAS_DIGEST_SIZE = 16
    _ATLAS_METADATA_STRUCT = struct.Struct(
        ">8sBB6xBBBBI16sBBBBI16s"
    )

    # Automatic Picture Flash programming is deliberately one-shot per
    # (picture_id, size, digest) for the lifetime of the host process.  This is
    # a wear-safety backstop for UART reconnect loops: a lost acknowledgement
    # or metadata failure must never cause the same image to be programmed
    # every few seconds. Explicit/manual sync_atlases() calls bypass this set.
    _atlas_auto_picture_attempts = set()

    FONT_SIZES = (
        (6, 12), (8, 16), (10, 20), (12, 24), (14, 28),
        (16, 32), (20, 40), (24, 48), (28, 56), (32, 64),
    )

    FONT_6X12 = 0x00
    FONT_8X16 = 0x01
    FONT_10X20 = 0x02
    FONT_12X24 = 0x03
    FONT_14X28 = 0x04
    FONT_16X32 = 0x05
    FONT_20X40 = 0x06
    FONT_24X48 = 0x07
    FONT_28X56 = 0x08
    FONT_32X64 = 0x09
    FONT_NUM_64X120 = 0x0A
    FONT_NUM_44X80 = 0x0B

    # Compatibility names used by the current UI.  These are constants only;
    # production call sites use the new snake_case driver API.
    font6x12 = FONT_6X12
    font8x16 = FONT_8X16
    font10x20 = FONT_10X20
    font12x24 = FONT_12X24
    font14x28 = FONT_14X28
    font16x32 = FONT_16X32
    font20x40 = FONT_20X40
    font24x48 = FONT_24X48
    font28x56 = FONT_28X56
    font32x64 = FONT_32X64

    DWIN_WIDTH = WIDTH
    DWIN_HEIGHT = HEIGHT

    Color_White = 0xFFFF
    Color_Yellow = 0xFF0F
    Color_Bg_Window = 0x31E8
    Color_Bg_Blue = 0x1125
    Color_Bg_Black = 0x0841
    Color_Bg_Red = 0xF00F
    Popup_Text_Color = 0xD6BA
    Line_Color = 0x3A6A
    Rectangle_Color = 0xEE2F
    Percent_Color = 0xFE29
    BarFill_Color = 0x10E4
    Select_Color = 0x33BB

    DWIN_FONT_MENU = FONT_8X16
    DWIN_FONT_STAT = FONT_10X20
    DWIN_FONT_HEAD = FONT_10X20

    _FIXED_RX_PAYLOAD = {
        0x00: 2,  # "OK"
        0x31: 3,  # Flash write: A5 "OK"
        0x33: 2,  # Picture write: "OK"
        0x34: 2,  # Direction change: "OK"
        0xFF: 1,  # CRC error report
    }

    def __init__(self, port, baudrate=115200, handshake_timeout=1.0,
                 handshake_attempts=3, wake_delay=0.750, startup_progress=None):
        if not isinstance(baudrate, int) or baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if not math.isfinite(handshake_timeout) or handshake_timeout <= 0:
            raise ValueError("handshake timeout must be positive")
        if not isinstance(handshake_attempts, int) or handshake_attempts <= 0:
            raise ValueError("handshake attempts must be positive")
        if not math.isfinite(wake_delay) or wake_delay < 0:
            raise ValueError("wake delay must be nonnegative")

        self.serial = serial.Serial(port, baudrate, timeout=0.05, write_timeout=1)
        # Compatibility attribute while the rest of the application migrates.
        self.MYSERIAL1 = self.serial
        self._closed = False
        self._needs_update = True
        self._defer_updates = False
        self._rx = bytearray()
        self._frames = deque()
        self._aux_rx = deque()
        self._crc_errors = 0
        self._transaction_lock = Lock()
        self._virtual_area_pictures = {}
        self._atlas_specs, self._atlas_icons = self._build_atlas_config()
        self._atlas_synced = False
        self._atlas_virtual_areas_loaded = False
        self._atlas_sync_blocked = False

        try:
            time.sleep(wake_delay)
            for _ in range(handshake_attempts):
                if self.handshake(handshake_timeout):
                    break
            else:
                raise T5UIC1TimeoutError("DWIN handshake timed out")
            # Preserve the existing Ender 3 V2 portrait orientation and startup
            # traffic.  Do not wait for the optional 0x34 acknowledgement here.
            self.set_orientation(1, wait_ack=False)
            if startup_progress is not None:
                startup_progress(self, 40)
            # Atlas Picture Flash is synchronized once during connection.
            # Failure is non-fatal to the normal LCD UI and automatic retry is
            # blocked for this connection/process to protect Flash endurance.
            # Virtual areas are still populated lazily by draw_atlas_icon().
            self._startup_sync_atlases()
            if self._atlas_synced:
                self.load_atlases(preserve_boot_splash=True)
                if startup_progress is not None:
                    startup_progress(self, 70)
            self.update()
        except BaseException:
            self.close()
            raise

    def close(self):
        if not getattr(self, "_closed", False):
            self._closed = True
            self.serial.close()

    @staticmethod
    def _u8(value, name="value"):
        if not isinstance(value, int) or not 0 <= value <= 0xFF:
            raise ValueError(f"{name} must be 0..255")
        return value

    @staticmethod
    def _u16(value, name="value"):
        # Preserve the legacy UI contract for calculations that yield exact
        # integer-valued floats (for example 256.0), while rejecting fractional
        # coordinates that cannot be represented by the wire protocol.
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                raise ValueError(f"{name} must be an integer in 0..65535")
            value = int(value)
        if not isinstance(value, int) or not 0 <= value <= 0xFFFF:
            raise ValueError(f"{name} must be 0..65535")
        return value

    @classmethod
    def _word(cls, value, name="value"):
        return cls._u16(value, name).to_bytes(2, "big")

    @classmethod
    def _words(cls, *values):
        return b"".join(cls._word(value) for value in values)

    @staticmethod
    def _ensure_bytes(data, name="data"):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError(f"{name} must be bytes-like")
        return bytes(data)

    def _send(self, command, payload=b""):
        if self._closed:
            raise RuntimeError("LCD is closed")
        command = self._u8(command, "command")
        payload = self._ensure_bytes(payload)
        if len(payload) > self.MAX_DATA_LENGTH:
            raise ValueError("T5UIC1 data field exceeds 248 bytes")
        frame = self.HEADER + bytes((command,)) + payload + self.TAIL
        written = self.serial.write(frame)
        if written != len(frame):
            self.close()
            raise IOError("Incomplete LCD frame write")
        self._needs_update = True
        time.sleep(0.001)
        return frame

    def _read_available(self):
        if self._closed:
            raise RuntimeError("LCD is closed")
        waiting = int(getattr(self.serial, "in_waiting", 0) or 0)
        if waiting:
            self._rx.extend(self.serial.read(min(waiting, 4096)))
            self._parse_rx()

    def _parse_rx(self):
        while True:
            start = self._rx.find(self.HEADER)
            if start < 0:
                # Keep no arbitrary noise. A future frame always starts at AA.
                self._rx.clear()
                return
            if start:
                del self._rx[:start]
            if len(self._rx) < 2:
                return

            command = self._rx[1]
            if command == 0x32:
                # AA 32 TYPE ADDR_H ADDR_L LEN DATA... TAIL
                if len(self._rx) < 6:
                    return
                payload_length = 4 + self._rx[5]
            elif command == 0x3A:
                # AA 3A LEN DATA... TAIL
                if len(self._rx) < 3:
                    return
                payload_length = 1 + self._rx[2]
            else:
                payload_length = self._FIXED_RX_PAYLOAD.get(command)
                if payload_length is None:
                    # Unknown inbound opcode. Drop only the header byte and
                    # resynchronize without treating data bytes as a frame.
                    del self._rx[0]
                    continue

            total = 2 + payload_length + len(self.TAIL)
            if len(self._rx) < total:
                return
            if bytes(self._rx[total - len(self.TAIL):total]) != self.TAIL:
                del self._rx[0]
                continue

            payload = bytes(self._rx[2:2 + payload_length])
            del self._rx[:total]
            if command == 0x3A:
                self._aux_rx.append(payload[1:])
            elif command == 0xFF:
                self._crc_errors += 1
            else:
                self._frames.append((command, payload))

    def _wait_response(self, command, timeout, predicate=None):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        deadline = time.monotonic() + timeout
        while True:
            for _ in range(len(self._frames)):
                frame_command, payload = self._frames.popleft()
                if frame_command == command and (predicate is None or predicate(payload)):
                    return payload
                self._frames.append((frame_command, payload))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise T5UIC1TimeoutError(f"Timed out waiting for opcode 0x{command:02X}")
            self._read_available()
            if not getattr(self.serial, "in_waiting", 0):
                time.sleep(min(0.005, remaining))

    @staticmethod
    def _ok(payload):
        return payload.endswith(b"OK")

    # ------------------------------------------------------------------
    # Configuration and interface instructions
    # ------------------------------------------------------------------

    def handshake(self, timeout=1.0):
        with self._transaction_lock:
            self._send(0x00)
            try:
                payload = self._wait_response(0x00, timeout)
            except T5UIC1TimeoutError:
                return False
            return payload == b"OK"

    def load_display_settings(self):
        """Read the dedicated 0x0100..0x010F Data Flash record."""
        return display_settings.decode(self.read_flash(
            self.DISPLAY_SETTINGS_ADDRESS, self.DISPLAY_SETTINGS_SIZE))

    def save_display_settings(self, brightness, idle_minutes, dim_brightness=10):
        record = display_settings.encode(brightness, idle_minutes, dim_brightness)
        self.write_flash(self.DISPLAY_SETTINGS_ADDRESS, record)
        if self.read_flash(self.DISPLAY_SETTINGS_ADDRESS, len(record)) != record:
            raise OSError('Display settings verification failed')

    def set_backlight(self, brightness):
        self._send(0x30, bytes((self._u8(brightness, "brightness"),)))

    def set_orientation(self, direction, wait_ack=False, timeout=1.0):
        if direction not in (0, 1, 2, 3):
            raise ValueError("direction must be 0..3")
        with self._transaction_lock:
            self._send(0x34, b"\x5A\xA5" + bytes((direction,)))
            if wait_ack:
                payload = self._wait_response(0x34, timeout, self._ok)
                if payload != b"OK":
                    raise T5UIC1ProtocolError("Invalid orientation acknowledgement")

    def set_aux_baud_divisor(self, divisor):
        if not isinstance(divisor, int) or not 1 <= divisor <= 0x03FF:
            raise ValueError("extended UART divisor must be 1..0x03FF")
        self._send(0x38, self._word(divisor))

    def set_aux_baudrate(self, baudrate):
        if not isinstance(baudrate, int) or baudrate < 15300:
            raise ValueError("extended UART baudrate must be at least 15300")
        divisor = round(15667200 / baudrate)
        if not 1 <= divisor <= 0x03FF:
            raise ValueError("extended UART baudrate is outside panel range")
        self.set_aux_baud_divisor(divisor)
        return 15667200 / divisor

    def aux_write(self, data):
        data = self._ensure_bytes(data)
        if not data:
            raise ValueError("extended UART write must not be empty")
        self._send(0x39, data)

    def poll_aux_data(self):
        self._read_available()
        return self._aux_rx.popleft() if self._aux_rx else None

    def poll_crc_error(self):
        self._read_available()
        if not self._crc_errors:
            return False
        self._crc_errors -= 1
        return True

    def update(self):
        if self._closed:
            raise RuntimeError("LCD is closed")
        if self._defer_updates or not self._needs_update:
            return
        self._send(0x3D)
        self._needs_update = False

    # ------------------------------------------------------------------
    # Drawing instructions
    # ------------------------------------------------------------------

    def clear(self, color):
        self._send(0x01, self._word(color, "color"))

    def draw_points(self, color, width, height, points):
        color = self._u16(color, "color")
        if not isinstance(width, int) or not 1 <= width <= 15:
            raise ValueError("point width must be 1..15")
        if not isinstance(height, int) or not 1 <= height <= 15:
            raise ValueError("point height must be 1..15")
        points = tuple(points)
        if not points:
            raise ValueError("at least one point is required")
        payload = self._word(color) + bytes((width, height))
        for point in points:
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError("points must contain (x, y) pairs")
            payload += self._words(point[0], point[1])
        self._send(0x02, payload)

    def draw_point(self, color, width, height, x, y):
        self.draw_points(color, width, height, ((x, y),))

    def draw_polyline(self, color, points):
        color = self._u16(color, "color")
        points = tuple(points)
        if len(points) < 2:
            raise ValueError("a polyline needs at least two points")
        payload = self._word(color)
        for point in points:
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError("points must contain (x, y) pairs")
            payload += self._words(point[0], point[1])
        self._send(0x03, payload)

    def draw_line(self, color, x0, y0, x1, y1):
        self.draw_polyline(color, ((x0, y0), (x1, y1)))

    def draw_rectangle(self, mode, color, x0, y0, x1, y1):
        if mode not in (0, 1, 2):
            raise ValueError("rectangle mode must be 0, 1 or 2")
        payload = bytes((mode,)) + self._word(color, "color") + self._words(x0, y0, x1, y1)
        self._send(0x05, payload)

    def draw_bitmap(self, x, y, width, color1, color0, data):
        if not isinstance(width, int) or not 1 <= width <= 480:
            raise ValueError("bitmap width must be 1..480")
        data = self._ensure_bytes(data)
        row_bytes = (width + 7) // 8
        if not data or len(data) % row_bytes:
            raise ValueError("bitmap data must contain complete left-aligned rows")
        payload = (self._words(x, y) + self._word(width)
                   + self._word(color1, "color1") + self._word(color0, "color0") + data)
        self._send(0x08, payload)

    def move_area(self, mode, direction, distance, color, x0, y0, x1, y1):
        if mode not in (0, 1):
            raise ValueError("move mode must be 0 or 1")
        if direction not in (0, 1, 2, 3):
            raise ValueError("move direction must be 0..3")
        flags = (mode << 7) | direction
        payload = bytes((flags,)) + self._words(distance, color, x0, y0, x1, y1)
        self._send(0x09, payload)

    # Software-only helpers retained because the current UI uses them.
    def draw_circle(self, color, x0, y0, radius):
        if not isinstance(radius, int) or radius < 0:
            raise ValueError("radius must be a nonnegative integer")
        x = radius
        y = 0
        error = 1 - radius
        while x >= y:
            points = (
                (x0 + x, y0 + y), (x0 + y, y0 + x),
                (x0 - y, y0 + x), (x0 - x, y0 + y),
                (x0 - x, y0 - y), (x0 - y, y0 - x),
                (x0 + y, y0 - x), (x0 + x, y0 - y),
            )
            self.draw_points(color, 1, 1, points)
            y += 1
            if error < 0:
                error += 2 * y + 1
            else:
                x -= 1
                error += 2 * (y - x) + 1

    def fill_circle(self, color, x0, y0, radius):
        if not isinstance(radius, int) or radius < 0:
            raise ValueError("radius must be a nonnegative integer")
        for dy in range(-radius, radius + 1):
            dx = int(math.sqrt(radius * radius - dy * dy))
            self.draw_rectangle(1, color, x0 - dx, y0 + dy, x0 + dx, y0 + dy)

    # ------------------------------------------------------------------
    # Text and numeric instructions
    # ------------------------------------------------------------------

    @staticmethod
    def _panel_text(text):
        text = str(text).translate(str.maketrans({
            "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
        }))
        text = unicodedata.normalize("NFKD", text)
        return "".join(
            char if " " <= char <= "~" else "?"
            for char in text if not unicodedata.combining(char)
        )

    def draw_text_bytes(self, width_adjust, show_background, font, color,
                        background, x, y, data):
        if not isinstance(font, int) or not 0 <= font <= 9:
            raise ValueError("font must be 0..9")
        data = self._ensure_bytes(data)
        if not data:
            return
        mode = (bool(width_adjust) << 7) | (bool(show_background) << 6) | font
        payload = (bytes((mode,)) + self._word(color, "color")
                   + self._word(background, "background") + self._words(x, y) + data)
        self._send(0x11, payload)

    def draw_text(self, width_adjust, show_background, font, color,
                  background, x, y, text):
        self._u16(x, "x")
        self._u16(y, "y")
        if not isinstance(font, int) or not 0 <= font <= 9:
            raise ValueError("font must be 0..9")
        font_width = self.FONT_SIZES[font][0]
        visible = min(90, max(0, (self.WIDTH - x) // font_width))
        encoded = self._panel_text(text)[:visible].encode("ascii")
        if encoded and y < self.HEIGHT:
            self.draw_text_bytes(width_adjust, show_background, font, color,
                                 background, x, y, encoded)

    def draw_number(self, value, *, signed=False, show_background=False,
                    zero_fill=False, zero_mode=False, font=FONT_8X16,
                    color=0xFFFF, background=0, integer_digits=1,
                    fractional_digits=0, x=0, y=0, byte_length=4):
        if not isinstance(font, int) or not 0 <= font <= 0x0F:
            raise ValueError("native numeric font selector must be 0x00..0x0F")
        if not isinstance(integer_digits, int) or not 1 <= integer_digits <= 20:
            raise ValueError("integer_digits must be 1..20")
        if not isinstance(fractional_digits, int) or not 0 <= fractional_digits <= 20:
            raise ValueError("fractional_digits must be 0..20")
        if integer_digits + fractional_digits > 20:
            raise ValueError("integer_digits + fractional_digits must not exceed 20")
        if not isinstance(byte_length, int) or not 1 <= byte_length <= 8:
            raise ValueError("byte_length must be 1..8")
        if not isinstance(value, int):
            raise ValueError("native numeric value must be an integer")
        try:
            raw = value.to_bytes(byte_length, "big", signed=bool(signed))
        except OverflowError as error:
            raise ValueError("numeric value does not fit requested byte length") from error
        mode = (bool(show_background) << 7 | bool(signed) << 6
                | bool(zero_fill) << 5 | bool(zero_mode) << 4 | font)
        payload = (bytes((mode,)) + self._word(color, "color")
                   + self._word(background, "background")
                   + bytes((integer_digits, fractional_digits))
                   + self._words(x, y) + raw)
        self._send(0x14, payload)

    def _format_scaled_decimal(self, value, integer_digits, fractional_digits, signed):
        try:
            number = Decimal(value) if isinstance(value, int) else Decimal(str(value))
            if not number.is_finite():
                raise ValueError("numeric value must be finite")
            limit = Decimal(10) ** (integer_digits + fractional_digits)
            if abs(number) < limit:
                number = number.quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if number == 0:
                number = abs(number)
            width = integer_digits + (fractional_digits + 1 if fractional_digits else 0) + int(signed)
            if abs(number) >= limit:
                return "#" * width
            text = format(number.scaleb(-fractional_digits), f".{fractional_digits}f")
            return text.rjust(width) if len(text) <= width else "#" * width
        except InvalidOperation as error:
            raise ValueError("invalid numeric value") from error

    def draw_integer_text(self, show_background, zero_fill, zero_mode, font,
                          color, background, digits, x, y, value):
        if not isinstance(digits, int) or not 1 <= digits <= 19:
            raise ValueError("digits must be 1..19")
        text = self._format_scaled_decimal(value, digits, 0, False)
        self.draw_text(False, show_background, font, color, background, x, y, text)

    def draw_scaled_float_text(self, show_background, zero_fill, zero_mode, font,
                               color, background, integer_digits, fractional_digits,
                               x, y, value):
        if not (isinstance(integer_digits, int) and isinstance(fractional_digits, int)
                and 1 <= integer_digits <= 19 and 0 <= fractional_digits <= 18
                and integer_digits + fractional_digits < 20):
            raise ValueError("invalid numeric digit count")
        font_width = self.FONT_SIZES[font][0] if isinstance(font, int) and 0 <= font <= 9 else 0
        text = self._format_scaled_decimal(value, integer_digits, fractional_digits, True)
        self.draw_text(False, show_background, font, color, background,
                       max(0, x - font_width), y, text)

    def draw_signed_scaled_float_text(self, font, background, integer_digits,
                                      fractional_digits, x, y, value):
        self.draw_scaled_float_text(
            True, True, False, font, self.Color_White, background,
            integer_digits, fractional_digits, x, y, value,
        )

    # ------------------------------------------------------------------
    # Picture, icon, QR and barcode instructions
    # ------------------------------------------------------------------

    @staticmethod
    def _image_mode(index, background, restore, enhanced):
        if not isinstance(index, int) or not 0 <= index <= 0x0F:
            raise ValueError("image library/cache index must be 0..15")
        return (bool(background) << 7 | bool(restore) << 6
                | bool(enhanced) << 5 | index)

    def draw_qr(self, x, y, pixel_size, data):
        if not isinstance(pixel_size, int) or not 1 <= pixel_size <= 15:
            raise ValueError("QR pixel size must be 1..15")
        if isinstance(data, str):
            data = data.encode("utf-8")
        data = self._ensure_bytes(data)
        if not 1 <= len(data) <= 154:
            raise ValueError("QR data must contain 1..154 bytes")
        self._send(0x21, self._words(x, y) + bytes((pixel_size,)) + data)

    def show_jpeg(self, jpeg_id):
        if not isinstance(jpeg_id, int) or not 0 <= jpeg_id <= 15:
            raise ValueError("JPEG ID must be 0..15")
        self._send(0x22, bytes((0, jpeg_id)))
        if not hasattr(self, "_virtual_area_pictures"):
            self._virtual_area_pictures = {}
        self._virtual_area_pictures[0] = jpeg_id

    def show_icon(self, library_id, icon_ids, x, y, *, background=True,
                  restore=False, enhanced=False):
        mode = self._image_mode(library_id, background, restore, enhanced)
        if isinstance(icon_ids, int):
            icon_ids = (icon_ids,)
        icon_ids = tuple(icon_ids)
        if not icon_ids:
            raise ValueError("at least one icon ID is required")
        icons = bytes(self._u8(icon, "icon ID") for icon in icon_ids)
        self._send(0x23, self._words(x, y) + bytes((mode,)) + icons)

    def show_sram_jpeg(self, x, y, address=0, *, background=True, enhanced=False):
        if not isinstance(address, int) or not 0 <= address < self.SRAM_SIZE:
            raise ValueError("SRAM address outside 32KB range")
        mode = (bool(background) << 7) | (bool(enhanced) << 5)
        self._send(0x24, self._words(x, y) + bytes((mode,)) + self._word(address))

    def cache_jpeg(self, jpeg_id, area=1):
        if not isinstance(jpeg_id, int) or not 0 <= jpeg_id <= 15:
            raise ValueError("JPEG ID must be 0..15")
        if area != 1:
            raise ValueError("cache-only JPEG loading supports virtual area 1; use show_jpeg for area 0")
        self._send(0x25, bytes((area, jpeg_id)))
        if not hasattr(self, "_virtual_area_pictures"):
            self._virtual_area_pictures = {}
        self._virtual_area_pictures[area] = jpeg_id

    def copy_cache1(self, x0, y0, x1, y1, x, y):
        self._send(0x26, self._words(x0, y0, x1, y1, x, y))

    def copy_cache(self, cache_id, x0, y0, x1, y1, x, y, *,
                   background=False, restore=False, enhanced=True):
        if cache_id not in (0, 1):
            raise ValueError("virtual display area must be 0 or 1")
        mode = self._image_mode(cache_id, background, restore, enhanced)
        self._send(0x27, bytes((mode,)) + self._words(x0, y0, x1, y1, x, y))

    def configure_animation(self, animation_id, enabled, library_id,
                            first_icon, last_icon, x, y, interval,
                            *, restart_from_first=True):
        if not isinstance(animation_id, int) or not 0 <= animation_id <= 15:
            raise ValueError("animation ID must be 0..15")
        if not isinstance(library_id, int) or not 0 <= library_id <= 15:
            raise ValueError("icon library ID must be 0..15")
        first_icon = self._u8(first_icon, "first icon")
        last_icon = self._u8(last_icon, "last icon")
        interval = self._u8(interval, "interval")
        mode = (bool(enabled) << 7 | bool(restart_from_first) << 6 | animation_id)
        payload = self._words(x, y) + bytes((mode, library_id, first_icon, last_icon, interval))
        self._send(0x28, payload)

    def set_animation_mask(self, state):
        self._send(0x29, self._word(state, "animation mask"))

    def draw_ean13(self, x, y, digits):
        if isinstance(digits, str):
            if len(digits) != 12 or not digits.isdigit():
                raise ValueError("EAN-13 source must contain exactly 12 digits")
            digits = tuple(int(char) for char in digits)
        else:
            digits = tuple(digits)
        if len(digits) != 12 or any(not isinstance(value, int) or not 0 <= value <= 9 for value in digits):
            raise ValueError("EAN-13 source must contain exactly 12 digits in the range 0..9")
        if x % 2 or y % 2:
            raise ValueError("EAN-13 coordinates must be even")
        self._send(0x2A, self._words(x, y) + bytes(digits))

    # ------------------------------------------------------------------
    # SRAM, data Flash and picture Flash instructions
    # ------------------------------------------------------------------

    @classmethod
    def _memory_limit(cls, memory):
        if memory == cls.MEMORY_SRAM:
            return cls.SRAM_SIZE
        if memory == cls.MEMORY_FLASH:
            return cls.FLASH_USABLE_SIZE
        raise ValueError("memory must be MEMORY_SRAM or MEMORY_FLASH")

    def write_memory(self, memory, address, data, *, timeout=1.25):
        limit = self._memory_limit(memory)
        if not isinstance(address, int):
            raise ValueError("memory address must be an integer")
        data = self._ensure_bytes(data)
        if not data:
            raise ValueError("memory write must not be empty")
        if not 0 <= address < limit or address + len(data) > limit:
            raise ValueError("memory write outside selected memory range")

        with self._transaction_lock:
            offset = 0
            while offset < len(data):
                chunk = data[offset:offset + self.MEMORY_WRITE_CHUNK]
                self._send(0x31, bytes((memory,)) + self._word(address + offset) + chunk)
                if memory == self.MEMORY_FLASH:
                    payload = self._wait_response(
                        0x31, timeout,
                        lambda value: value == bytes((self.MEMORY_FLASH,)) + b"OK",
                    )
                    if payload != bytes((self.MEMORY_FLASH,)) + b"OK":
                        raise T5UIC1ProtocolError("Invalid Flash write acknowledgement")
                offset += len(chunk)

    def read_memory(self, memory, address, length, *, timeout=1.0):
        limit = self._memory_limit(memory)
        if not isinstance(address, int) or not isinstance(length, int):
            raise ValueError("memory address and length must be integers")
        if length <= 0 or not 0 <= address < limit or address + length > limit:
            raise ValueError("memory read outside selected memory range")

        result = bytearray()
        with self._transaction_lock:
            offset = 0
            while offset < length:
                size = min(self.MEMORY_READ_CHUNK, length - offset)
                chunk_address = address + offset
                self._send(0x32, bytes((memory,)) + self._word(chunk_address) + bytes((size,)))

                def matches(payload):
                    return (len(payload) == 4 + size
                            and payload[0] == memory
                            and int.from_bytes(payload[1:3], "big") == chunk_address
                            and payload[3] == size)

                payload = self._wait_response(0x32, timeout, matches)
                if not matches(payload):
                    raise T5UIC1ProtocolError("Memory response does not match request")
                result.extend(payload[4:])
                offset += size
        return bytes(result)

    def write_sram(self, address, data):
        self.write_memory(self.MEMORY_SRAM, address, data)

    def read_sram(self, address, length, *, timeout=1.0):
        return self.read_memory(self.MEMORY_SRAM, address, length, timeout=timeout)

    def write_flash(self, address, data, *, timeout=1.25):
        self.write_memory(self.MEMORY_FLASH, address, data, timeout=timeout)

    def read_flash(self, address, length, *, timeout=1.0):
        return self.read_memory(self.MEMORY_FLASH, address, length, timeout=timeout)

    def store_sram_as_picture(self, picture_id, *, timeout=2.5):
        if not isinstance(picture_id, int) or not 0 <= picture_id <= 15:
            raise ValueError("picture ID must be 0..15")
        with self._transaction_lock:
            self._send(0x33, b"\x5A\xA5" + bytes((picture_id,)))
            payload = self._wait_response(0x33, timeout, self._ok)
            if payload != b"OK":
                raise T5UIC1ProtocolError("Invalid picture Flash acknowledgement")


    # ------------------------------------------------------------------
    # Managed KlipperDWIN custom-atlas layer
    # ------------------------------------------------------------------

    @classmethod
    def _build_atlas_config(cls, atlas_files=None, icon_coordinates=None,
                            base_dir=None):
        """Validate and normalize the host-side atlas manifest.

        atlas_files maps virtual-area IDs to (JPEG path, Picture Flash ID).
        icon_coordinates maps icon IDs to (area, x, y, width, height).
        Coordinates are in the portrait virtual-area coordinate space after
        the panel's runtime orientation has been applied.
        """
        if atlas_files is None:
            atlas_files = lcd_atlas.ATLAS_FILES
        if icon_coordinates is None:
            icon_coordinates = lcd_atlas.ICON_COORDINATES
        if not isinstance(atlas_files, dict) or not isinstance(icon_coordinates, dict):
            raise ValueError("atlas files and icon coordinates must be dictionaries")

        root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
        specs = {}
        picture_ids = set()
        for area, definition in atlas_files.items():
            if area not in (0, 1):
                raise ValueError("atlas virtual area must be 0 or 1")
            if not isinstance(definition, (tuple, list)) or len(definition) != 2:
                raise ValueError("atlas definition must be (jpeg_path, picture_id)")
            filename, picture_id = definition
            if not isinstance(filename, (str, Path)) or not str(filename):
                raise ValueError("atlas JPEG path must be non-empty")
            if not isinstance(picture_id, int) or not 0 <= picture_id <= 15:
                raise ValueError("atlas Picture Flash ID must be 0..15")
            if picture_id in picture_ids:
                raise ValueError("atlas Picture Flash IDs must be unique")
            picture_ids.add(picture_id)
            path = Path(filename)
            if not path.is_absolute():
                path = root / path
            specs[area] = (picture_id, path)

        icons = {}
        for icon_id, definition in icon_coordinates.items():
            if not isinstance(icon_id, int) or not 0 <= icon_id <= 0xFFFF:
                raise ValueError("atlas icon ID must be 0..65535")
            if not isinstance(definition, (tuple, list)) or len(definition) != 5:
                raise ValueError(
                    "atlas icon definition must be (area, x, y, width, height)"
                )
            area, x, y, width, height = definition
            if area not in specs:
                raise ValueError("atlas icon references an undefined virtual area")
            values = (x, y, width, height)
            if any(not isinstance(value, int) for value in values):
                raise ValueError("atlas icon coordinates and dimensions must be integers")
            if x < 0 or y < 0 or width <= 0 or height <= 0:
                raise ValueError("atlas icon rectangle must have positive dimensions")
            if x + width > cls.WIDTH or y + height > cls.HEIGHT:
                raise ValueError("atlas icon rectangle exceeds virtual-area bounds")
            icons[icon_id] = (area, x, y, width, height)
        return specs, icons

    def _atlas_runtime_config(self):
        if not hasattr(self, "_atlas_specs") or not hasattr(self, "_atlas_icons"):
            self._atlas_specs, self._atlas_icons = self._build_atlas_config()
        if not hasattr(self, "_virtual_area_pictures"):
            self._virtual_area_pictures = {}
        return self._atlas_specs, self._atlas_icons

    def _active_atlas_areas(self):
        _, icons = self._atlas_runtime_config()
        return tuple(sorted({definition[0] for definition in icons.values()}))

    @classmethod
    def _pack_atlas_metadata(cls, entries):
        values = [cls.ATLAS_METADATA_MAGIC, cls.ATLAS_METADATA_VERSION,
                  len(entries)]
        zero_digest = bytes(cls.ATLAS_DIGEST_SIZE)
        for area in (0, 1):
            if area in entries:
                picture_id, size, digest = entries[area]
                if not isinstance(digest, bytes) or len(digest) != cls.ATLAS_DIGEST_SIZE:
                    raise ValueError("atlas digest must be exactly 16 bytes")
                values.extend((1, area, picture_id, 0, size, digest))
            else:
                values.extend((0, area, 0, 0, 0, zero_digest))
        return cls._ATLAS_METADATA_STRUCT.pack(*values)

    @classmethod
    def _unpack_atlas_metadata(cls, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            return {}
        data = bytes(data)
        if len(data) != cls.ATLAS_METADATA_SIZE:
            return {}
        try:
            values = cls._ATLAS_METADATA_STRUCT.unpack(data)
        except struct.error:
            return {}
        magic, version, count = values[:3]
        if magic != cls.ATLAS_METADATA_MAGIC or version != cls.ATLAS_METADATA_VERSION:
            return {}
        rest = values[3:]
        entries = {}
        for offset in (0, 6):
            enabled, area, picture_id, flags, size, digest = rest[offset:offset + 6]
            if enabled not in (0, 1) or flags != 0:
                return {}
            if not enabled:
                continue
            if area not in (0, 1) or area in entries:
                return {}
            if not 0 <= picture_id <= 15 or not 0 < size <= cls.SRAM_SIZE:
                return {}
            entries[area] = (picture_id, size, digest)
        if count != len(entries):
            return {}
        return entries

    def _atlas_payloads(self, *, allow_missing=False):
        specs, _ = self._atlas_runtime_config()
        payloads = {}
        entries = {}
        for area in self._active_atlas_areas():
            picture_id, path = specs[area]
            try:
                data = path.read_bytes()
            except OSError as error:
                if allow_missing:
                    logging.warning(
                        "Atlas sync deferred: host JPEG missing: %s", path
                    )
                    return None, None
                raise OSError(f"Unable to read atlas JPEG: {path}") from error
            if not 4 <= len(data) <= self.SRAM_SIZE:
                raise ValueError(
                    f"atlas JPEG for area {area} must fit in 32 KiB SRAM"
                )
            if not data.startswith(b"\xFF\xD8") or not data.endswith(b"\xFF\xD9"):
                raise ValueError(f"atlas JPEG for area {area} is not a complete JPEG")
            digest = hashlib.sha256(data).digest()[:self.ATLAS_DIGEST_SIZE]
            payloads[area] = data
            entries[area] = (picture_id, len(data), digest)
        return payloads, entries

    def _commit_atlas_metadata(self, metadata):
        """Write one metadata checkpoint and verify it by readback."""
        logging.info(
            "Atlas metadata: updating Data Flash @ 0x%04X",
            self.ATLAS_METADATA_ADDRESS,
        )
        try:
            self.write_flash(self.ATLAS_METADATA_ADDRESS, metadata)
        except Exception:
            logging.exception("Atlas metadata: Data Flash write failed")
            raise

        try:
            verified = self.read_flash(
                self.ATLAS_METADATA_ADDRESS, self.ATLAS_METADATA_SIZE
            )
        except Exception:
            logging.exception("Atlas metadata: verification read failed")
            raise
        if verified != metadata:
            logging.error("Atlas metadata: verification mismatch")
            raise T5UIC1ProtocolError("Atlas metadata verification failed")

        logging.info("Atlas metadata: Data Flash update verified")
        return verified

    def _startup_sync_atlases(self):
        """Perform the single automatic atlas-sync attempt for this connection.

        Atlas persistence is optional to the base LCD transport. A metadata or
        picture programming error must not turn the normal 5-second UART
        reconnect path into a Flash-write loop.
        """
        try:
            result = self.sync_atlases(allow_missing=True, automatic=True)
        except Exception:
            self._atlas_sync_blocked = True
            logging.exception(
                "Atlas auto-sync failed; automatic retries are blocked to protect Flash endurance"
            )
            return False
        return result

    def sync_atlases(self, *, allow_missing=False, automatic=False):
        """Synchronize changed host atlas JPEGs into reserved Picture Flash.

        The metadata is checkpointed after every successful Picture Flash
        write. This prevents an unrelated later failure from causing already
        committed atlases to be rewritten on the next service start.

        When automatic=True, each exact Picture Flash payload is attempted at
        most once per host-process lifetime. This guards the UART reconnect
        path against rapid repeated Flash programming. Manual/explicit calls
        may bypass that guard deliberately.

        allow_missing is used only by startup to tolerate a repository update
        where the manifest has landed before its binary JPEG assets.
        """
        self._atlas_synced = False
        payloads, desired = self._atlas_payloads(allow_missing=allow_missing)
        if payloads is None:
            return False
        if not desired:
            logging.info("Atlas sync: no active custom icons; nothing to do")
            self._atlas_synced = True
            return False

        specs, _ = self._atlas_runtime_config()
        logging.info("Atlas sync: checking %d active atlas(es)", len(desired))
        for area in sorted(desired):
            picture_id, size, digest = desired[area]
            _, path = specs[area]
            logging.info(
                "Atlas %d: host=%s picture=%d size=%d hash=%s",
                area, path, picture_id, size, digest.hex()[:12],
            )

        logging.info(
            "Atlas sync: reading metadata @ 0x%04X (%d bytes)",
            self.ATLAS_METADATA_ADDRESS, self.ATLAS_METADATA_SIZE,
        )
        try:
            raw_metadata = self.read_flash(
                self.ATLAS_METADATA_ADDRESS, self.ATLAS_METADATA_SIZE
            )
        except Exception:
            logging.exception("Atlas sync: metadata read failed")
            raise

        current = self._unpack_atlas_metadata(raw_metadata)
        if current:
            logging.info(
                "Atlas sync: valid persistent metadata found for %d atlas(es)",
                len(current),
            )
        else:
            logging.info(
                "Atlas sync: no valid persistent metadata; active atlases require upload"
            )

        changed = [
            area for area in sorted(desired)
            if current.get(area) != desired[area]
        ]
        changed_set = set(changed)
        for area in sorted(desired):
            if area in changed_set:
                logging.info("Atlas %d: changed -> upload required", area)
            else:
                logging.info("Atlas %d: unchanged -> skip", area)

        # Keep only metadata that describes atlases still present in the host
        # manifest. Each successful picture write is checkpointed immediately.
        committed = {
            area: entry for area, entry in current.items()
            if area in desired
        }

        for area in changed:
            picture_id, _ = specs[area]
            data = payloads[area]
            _, size, digest = desired[area]
            attempt_key = (picture_id, size, digest)

            logging.info(
                "Atlas %d: uploading %d bytes to SRAM @ 0x0000",
                area, len(data),
            )
            try:
                self.write_sram(0, data)
            except Exception:
                logging.exception("Atlas %d: SRAM upload failed", area)
                raise
            logging.info("Atlas %d: SRAM upload complete", area)

            if automatic:
                if attempt_key in self._atlas_auto_picture_attempts:
                    logging.critical(
                        "Atlas %d: automatic Picture Flash %d rewrite blocked by wear guard",
                        area, picture_id,
                    )
                    raise T5UIC1ProtocolError(
                        "automatic atlas Picture Flash retry blocked by wear guard"
                    )
                # Mark before issuing 0x33. If the ACK is lost after the panel
                # starts programming, a reconnect still cannot rewrite it.
                self._atlas_auto_picture_attempts.add(attempt_key)

            logging.info(
                "Atlas %d: storing SRAM as Picture Flash %d",
                area, picture_id,
            )
            try:
                self.store_sram_as_picture(picture_id)
            except Exception:
                logging.exception(
                    "Atlas %d: Picture Flash %d write failed",
                    area, picture_id,
                )
                raise
            logging.info(
                "Atlas %d: Picture Flash %d write complete",
                area, picture_id,
            )

            committed[area] = desired[area]
            checkpoint = self._pack_atlas_metadata(committed)
            if raw_metadata != checkpoint:
                raw_metadata = self._commit_atlas_metadata(checkpoint)

        # If nothing changed, never rewrite metadata merely to canonicalize
        # reserved/padding bytes. Avoiding unnecessary writes is preferable.
        self._atlas_synced = (all(committed.get(area) == desired[area]
                                  for area in desired))
        if self._atlas_synced:
            self._atlas_sync_blocked = False

        if changed:
            logging.info(
                "Atlas sync complete: updated virtual area(s) %s",
                ",".join(str(area) for area in changed),
            )
        else:
            logging.info("Atlas metadata: unchanged")
            logging.info("Atlas sync complete: no atlas uploads required")
        return bool(changed)

    def _load_atlas_area(self, area):
        specs, _ = self._atlas_runtime_config()
        if area not in specs:
            raise ValueError("atlas virtual area is not configured")
        picture_id, _ = specs[area]
        logging.info(
            "Atlas %d: loading Picture Flash %d into virtual area %d",
            area, picture_id, area,
        )
        if area == 0:
            self.show_jpeg(picture_id)
        else:
            self.cache_jpeg(picture_id)

    def load_atlases(self, *, preserve_boot_splash=False):
        """Restore volatile virtual areas from persistent Picture Flash.

        This is safe on every panel reconnect: it issues only display/cache
        load commands and never programs Picture Flash or Data Flash.
        """
        if not getattr(self, "_atlas_synced", False):
            raise T5UIC1ProtocolError(
                "custom atlases are not synchronized; refusing render-time Flash sync"
            )
        self._virtual_area_pictures.clear()
        active = self._active_atlas_areas()
        if preserve_boot_splash and 0 in active:
            # On this panel 0x25 loads cache 1, not cache 0. Keep a temporary
            # slot-0 splash in cache 1, load atlas 0 with 0x22, then restore
            # the splash pixels without replacing cache 0. No refresh occurs
            # between the atlas display command and the splash copy.
            self.cache_jpeg(0)
            self._load_atlas_area(0)
            self.copy_cache1(0, 0, self.WIDTH - 1, self.HEIGHT - 1, 0, 0)
            self._virtual_area_pictures.pop(1, None)
        for area in active:
            if preserve_boot_splash and area == 0:
                continue
            self._load_atlas_area(area)
        self._atlas_virtual_areas_loaded = True

    def _ensure_atlas_area(self, area):
        specs, _ = self._atlas_runtime_config()
        picture_id, _ = specs[area]
        if (not getattr(self, "_atlas_virtual_areas_loaded", False) or
                self._virtual_area_pictures.get(area) != picture_id):
            self._load_atlas_area(area)
            self._atlas_virtual_areas_loaded = all(
                self._virtual_area_pictures.get(active_area) == specs[active_area][0]
                for active_area in self._active_atlas_areas()
            )

    def draw_atlas_icon(self, icon_id, x, y):
        """Draw one custom icon by ID without exposing atlas layout to the UI."""
        self._u16(x, "x")
        self._u16(y, "y")
        _, icons = self._atlas_runtime_config()
        if icon_id not in icons:
            raise ValueError(f"unknown atlas icon ID: {icon_id}")
        area, source_x, source_y, width, height = icons[icon_id]
        if x + width > self.WIDTH or y + height > self.HEIGHT:
            raise ValueError("atlas icon destination exceeds display bounds")
        if not getattr(self, "_atlas_synced", False):
            raise T5UIC1ProtocolError(
                "custom atlases are not synchronized; refusing render-time Flash sync"
            )
        self._ensure_atlas_area(area)
        self.copy_cache(
            area,
            source_x, source_y,
            source_x + width - 1, source_y + height - 1,
            x, y,
        )


# Transitional class alias.  The application import is migrated separately.
T5UIC1_LCD = T5UIC1Display
