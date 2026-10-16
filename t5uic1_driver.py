"""Complete UART driver for DWIN T5UIC1 instruction-set displays.

The class in this module is deliberately limited to panel/protocol concerns.
UI layout and rendering policy live above it.  The public methods map directly
onto the T5UIC1 v2.3 instruction set, with a small set of compatibility
renderers used by Petrel to preserve its current visual output.
"""

import logging
import math
import struct
import time
import unicodedata
from collections import deque
from concurrent.futures import Future
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock

import display_settings
import buzzer_control
import serial
from graphite_theme import BACKGROUND_COLOR


class T5UIC1ProtocolError(RuntimeError):
    """Raised when a panel response is malformed or does not match a request."""


class T5UIC1TimeoutError(TimeoutError):
    """Raised when an expected T5UIC1 response is not received in time."""


class _ReceivedFrame(tuple):
    def __new__(cls, command, payload):
        frame = super().__new__(cls, (command, payload))
        frame.received_at = time.monotonic()
        return frame


class _AuxFrame(bytes):
    def __new__(cls, payload):
        frame = super().__new__(cls, payload)
        frame.received_at = time.monotonic()
        return frame


class T5UIC1Display:
    SUPPORTS_NONBLOCKING_LIVENESS = True
    SUPPORTS_NONBLOCKING_FLASH = True
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

    DISPLAY_SETTINGS_ADDRESS = 0x0100
    DISPLAY_SETTINGS_SIZE = display_settings.RECORD_SIZE
    BUZZER_SETTINGS_ADDRESS = buzzer_control.ADDRESS

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

    Color_White = 0xE75E
    Color_Yellow = 0xFF0F
    Color_Bg_Window = 0x2967
    Color_Bg_Blue = 0x2966
    Color_Bg_Black = BACKGROUND_COLOR
    Color_Bg_Red = 0xF00F
    Popup_Text_Color = 0xE75E
    Line_Color = 0x39C8
    Rectangle_Color = 0x063B
    Percent_Color = 0x063B
    BarFill_Color = 0x39C8
    Select_Color = 0x19E9

    DWIN_FONT_MENU = FONT_8X16
    DWIN_FONT_STAT = FONT_10X20
    DWIN_FONT_HEAD = FONT_10X20

    RX_FRAME_AGE = 5.0
    RX_FRAME_LIMIT = 64
    AUX_RX_LIMIT = 64

    _FIXED_RX_PAYLOAD = {
        0x00: 2,  # "OK"
        0x31: 3,  # Flash write: A5 "OK"
        0x33: 2,  # Picture write: "OK"
        0x34: 2,  # Direction change: "OK"
        0xFF: 1,  # CRC error report
    }

    def __init__(self, port, baudrate=115200, handshake_timeout=1.0,
                 handshake_attempts=3, wake_delay=0.750, startup_progress=None,
                 packet_observer=None, connected_serial=None):
        if not isinstance(baudrate, int) or baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if not math.isfinite(handshake_timeout) or handshake_timeout <= 0:
            raise ValueError("handshake timeout must be positive")
        if not isinstance(handshake_attempts, int) or handshake_attempts <= 0:
            raise ValueError("handshake attempts must be positive")
        if not math.isfinite(wake_delay) or wake_delay < 0:
            raise ValueError("wake delay must be nonnegative")

        self.serial = (connected_serial if connected_serial is not None else
                       serial.Serial(port, baudrate, timeout=0.05, write_timeout=1))
        self.serial.timeout = 0.05
        self.serial.write_timeout = 1
        # Compatibility attribute while the rest of the application migrates.
        self.MYSERIAL1 = self.serial
        self._closed = False
        self._needs_update = True
        self._defer_updates = False
        self._rx = bytearray()
        self._frames = deque(maxlen=self.RX_FRAME_LIMIT)
        self._aux_rx = deque(maxlen=self.AUX_RX_LIMIT)
        self._rx_discarded_frames = 0
        self._rx_discarded_aux = 0
        self._crc_errors = 0
        self._diagnostic_counts = {}
        self._backlight_raw = None
        self._transaction_lock = Lock()
        self._packet_observer = packet_observer

        try:
            if packet_observer is not None:
                packet_observer.reset_panel()
            if connected_serial is None:
                time.sleep(wake_delay)
                for _ in range(handshake_attempts):
                    if self.handshake(handshake_timeout):
                        break
                else:
                    raise T5UIC1TimeoutError("DWIN handshake timed out")
            # The panel CFG already selects portrait orientation. Preserve
            # its power-on picture instead of reapplying direction via 0x34.
            from boot_artwork import sync
            sync(self)
            # Present the complete boot frame before packing/checking icons.
            # Existing panel icons can animate throughout an unchanged sync.
            if startup_progress is not None:
                self._boot_animation_library = self._startup_animation_library()
                self.show_jpeg(0)
                startup_progress(self, 40)
                self.update()
            self._startup_sync_icons()
            self._startup_sync_shared_artwork()
            from lcd_resources import ICON_LIBRARY_ID
            self._boot_animation_library = ICON_LIBRARY_ID
            if startup_progress is not None:
                # A changed library stops animation before Flash programming;
                # the next stage restarts it using the newly committed icons.
                startup_progress(self, 70)
            self.update()
        except BaseException:
            self.close()
            raise

    def _startup_animation_library(self):
        """Use a committed resident directory while migrating library 7 to 3."""
        from icon_library import MAGIC, METADATA_ADDRESS
        from lcd_resources import ICON_LIBRARY_ID
        header = self.read_flash(METADATA_ADDRESS, 42)
        if (header[:8] == MAGIC and header[8] in (ICON_LIBRARY_ID, 7)
                and 1 <= header[9] <= 16-header[8] and any(header[10:42])):
            return header[8]
        return None  # First install/incomplete directory: animate after upload.

    def _startup_sync_icons(self):
        from icon_library import sync_library
        sync_library(self)
        self._assets_synced = True

    def _startup_sync_shared_artwork(self):
        from shared_artwork import sync
        sync(self)

    def close(self):
        if not getattr(self, "_closed", False):
            self._closed = True
            self.serial.close()
            if getattr(self, '_flash_job', None) is not None or getattr(self, '_flash_queue', None):
                self._flash_abort(OSError('LCD disconnected during Flash transaction'))
            observer = getattr(self, '_packet_observer', None)
            if observer is not None:
                observer.disconnect_panel()

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
        if command in (0x00, 0x31, 0x32, 0x33, 0x34):
            # A queued reply from an earlier transaction cannot confirm this send.
            self._frames = deque((frame for frame in self._frames if frame[0] != command),
                                 maxlen=self.RX_FRAME_LIMIT)
            self._protected_response_slots().pop(command, None)
        frame = self.HEADER + bytes((command,)) + payload + self.TAIL
        try:
            written = self.serial.write(frame)
        except OSError:
            self.close()
            raise
        if written != len(frame):
            self.close()
            raise IOError("Incomplete LCD frame write")
        counts = getattr(self,'_diagnostic_counts',None)
        if counts is not None:
            counts['tx_frames'] = counts.get('tx_frames',0)+1
            counts['tx_bytes'] = counts.get('tx_bytes',0)+len(frame)
            if command==0x00:
                counts['handshake_requests'] = counts.get('handshake_requests',0)+1
        observer = getattr(self, '_packet_observer', None)
        if observer is not None:
            try:
                observer.feed(frame)
            except Exception:
                # A developer observer must never interrupt the physical LCD.
                logging.exception('LCD packet observer failed')
        self._needs_update = True
        return frame

    def _read_available(self):
        if self._closed:
            raise RuntimeError("LCD is closed")
        try:
            waiting = int(getattr(self.serial, "in_waiting", 0) or 0)
            if waiting:
                data = self.serial.read(min(waiting, 4096))
                self._rx.extend(data)
                counts = getattr(self,'_diagnostic_counts',None)
                if counts is not None:
                    counts['rx_bytes'] = counts.get('rx_bytes',0)+len(data)
                self._parse_rx()
        except OSError:
            self.close()
            raise

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
                if len(self._aux_rx) == self._aux_rx.maxlen:
                    self._rx_discarded_aux += 1
                self._aux_rx.append(_AuxFrame(payload[1:]))
            elif command == 0xFF:
                self._crc_errors += 1
                counts = getattr(self,'_diagnostic_counts',None)
                if counts is not None:
                    counts['crc_notifications'] = counts.get('crc_notifications',0)+1
            else:
                frame = _ReceivedFrame(command, payload)
                expected = getattr(self, '_expected_response', None)
                job = getattr(self, '_flash_job', None)
                awaiting = job.get('awaiting') if job is not None else None
                if awaiting is not None and command == awaiting[0]:
                    expected = awaiting
                if command == 0x00 and getattr(self, '_liveness_deadline', None) is not None:
                    expected = 0x00, None
                if (expected is not None and command == expected[0]
                        and (expected[1] is None or expected[1](payload))):
                    # At most three active RPC kinds, one ACK slot per opcode.
                    slots = self._protected_response_slots()
                    if command not in slots and len(slots) < 3:
                        slots[command] = frame
                else:
                    if len(self._frames) == self._frames.maxlen:
                        self._rx_discarded_frames += 1
                    self._frames.append(frame)

    def _protected_response_slots(self):
        if not hasattr(self, '_response_slots'):
            self._response_slots = {}
        return self._response_slots

    def _take_response(self, command, predicate=None):
        now = time.monotonic()
        slot = self._protected_response_slots().pop(command, None)
        if slot is not None:
            if (now - slot.received_at <= self.RX_FRAME_AGE and slot[0] == command
                    and (predicate is None or predicate(slot[1]))):
                return slot[1]
        matched = None
        for _ in range(len(self._frames)):
            frame = self._frames.popleft()
            if now - getattr(frame, 'received_at', now) > self.RX_FRAME_AGE:
                self._rx_discarded_frames += 1
                continue
            op, payload = frame
            if matched is None and op == command and (predicate is None or predicate(payload)):
                matched = payload
                continue
            self._frames.append(frame)
        return matched

    def rx_discard_counts(self):
        """Dropped oldest unmatched replies and auxiliary frames under RX pressure."""
        return {'responses': self._rx_discarded_frames, 'aux': self._rx_discarded_aux}

    def _wait_response(self, command, timeout, predicate=None):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        deadline = time.monotonic() + timeout
        self._expected_response = command, predicate
        try:
            while True:
                payload = self._take_response(command, predicate)
                if payload is not None:
                    return payload
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    counts = getattr(self,'_diagnostic_counts',None)
                    if counts is not None:
                        counts['response_timeouts'] = counts.get('response_timeouts',0)+1
                    raise T5UIC1TimeoutError(f"Timed out waiting for opcode 0x{command:02X}")
                self._read_available()
                if not getattr(self.serial, "in_waiting", 0):
                    time.sleep(min(0.005, remaining))
        finally:
            self._expected_response = None
            self._protected_response_slots().pop(command, None)

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

    def begin_liveness_probe(self, timeout=0.5):
        """Send one handshake; never wait for its ACK on the UI owner."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if getattr(self, '_liveness_deadline', None) is not None:
            return
        with self._transaction_lock:
            # A response from a prior timed-out probe cannot confirm this one.
            self._frames = deque((frame for frame in self._frames
                                  if frame[0] != 0x00), maxlen=self.RX_FRAME_LIMIT)
            self._protected_response_slots().pop(0x00, None)
            self._expected_response = 0x00, None
            self._send(0x00)
            self._liveness_deadline = time.monotonic() + timeout

    def poll_liveness_probe(self):
        """None: pending/no probe, True: ACK, False: invalid/expired ACK."""
        deadline = getattr(self, '_liveness_deadline', None)
        if deadline is None:
            return None
        with self._transaction_lock:
            self._read_available()
            payload = self._take_response(0x00)
            if payload is not None:
                self._liveness_deadline = None
                self._expected_response = None
                return payload == b"OK"
            if time.monotonic() >= deadline:
                self._liveness_deadline = None
                self._expected_response = None
                self._protected_response_slots().pop(0x00, None)
                return False
        return None

    def load_display_settings(self):
        """Read the dedicated 0x0100..0x010F Data Flash record."""
        return display_settings.decode(self.read_flash(
            self.DISPLAY_SETTINGS_ADDRESS, self.DISPLAY_SETTINGS_SIZE))

    def save_display_settings(self, brightness, idle_minutes, dim_brightness=10):
        record = display_settings.encode(brightness, idle_minutes, dim_brightness)
        self.write_flash(self.DISPLAY_SETTINGS_ADDRESS, record)
        if self.read_flash(self.DISPLAY_SETTINGS_ADDRESS, len(record)) != record:
            raise OSError('Display settings verification failed')

    def load_buzzer_settings(self):
        return buzzer_control.Settings.decode(self.read_flash(
            buzzer_control.ADDRESS, buzzer_control.RECORD_SIZE))

    def save_buzzer_settings(self, settings):
        record = settings.encode()
        self.write_flash(buzzer_control.ADDRESS, record)
        if self.read_flash(buzzer_control.ADDRESS, len(record)) != record:
            raise OSError('Buzzer settings verification failed')

    def diagnostics(self):
        counts = dict(getattr(self,'_diagnostic_counts',{}))
        counts.update(self.rx_discard_counts())
        return counts

    def set_backlight(self, brightness):
        self._send(0x30, bytes((self._u8(brightness, "brightness"),)))
        self._backlight_raw = brightness

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
        now = time.monotonic()
        while self._aux_rx:
            frame = self._aux_rx.popleft()
            if now - getattr(frame, 'received_at', now) <= self.RX_FRAME_AGE:
                return bytes(frame)
            self._rx_discarded_aux += 1
        return None

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
        x = self._u16(x, "x")
        y = self._u16(y, "y")
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
        self._cached_picture1 = jpeg_id

    def ensure_cached_picture(self, jpeg_id):
        """Reuse Area 1 until another picture or connection replaces it."""
        if getattr(self, '_cached_picture1', None) != jpeg_id:
            self.cache_jpeg(jpeg_id)

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

    def _flash_state(self):
        # Lazy initialization also supports isolated driver instances in tests.
        if not hasattr(self, '_flash_queue'):
            self._flash_queue = deque()
            self._flash_job = None
            self._flash_fault = None

    def _flash_submit(self, address, value, verify):
        self._flash_state()
        limit = self.FLASH_USABLE_SIZE
        size = len(value) if verify else value
        if (not isinstance(address, int) or not isinstance(size, int)
                or size <= 0 or not 0 <= address < limit
                or address + size > limit):
            raise ValueError('Flash transaction exceeds usable memory')
        future = Future()
        if self._closed:
            future.set_exception(OSError('LCD disconnected'))
        elif self._flash_fault is not None:
            future.set_exception(self._flash_fault)
        elif len(self._flash_queue) + int(self._flash_job is not None) >= 4:
            future.set_exception(RuntimeError('Flash request queue full'))
        else:
            self._flash_queue.append({
                'address': address, 'length': size,
                'data': value if verify else None, 'future': future,
                'stage': 'write' if verify else 'read', 'offset': 0,
                'buffer': bytearray(), 'awaiting': None, 'deadline': 0.0,
                'chunk_size': 0, 'timeout': 1.25 if verify else 1.0,
            })
        return future

    def begin_flash_read(self, address, length):
        """Schedule a Flash read and return a Future; the UI owner must poll."""
        return self._flash_submit(address, length, False)

    def begin_flash_write_verified(self, address, data):
        """Schedule write, ACK, readback verification without waiting for ACK."""
        raw = self._ensure_bytes(data)
        return self._flash_submit(address, raw, True)

    def flash_busy(self):
        self._flash_state()
        return bool(self._flash_job or self._flash_queue)

    def _flash_abort(self, error):
        self._flash_state()
        self._flash_fault = error
        self._expected_response = None
        for op in (0x31, 0x32):
            self._protected_response_slots().pop(op, None)
        jobs = ([self._flash_job] if self._flash_job is not None else [])
        jobs.extend(self._flash_queue)
        self._flash_job = None
        self._flash_queue.clear()
        for job in jobs:
            future = job['future']
            if not future.done():
                future.set_exception(error)

    def poll_flash_tasks(self):
        """Advance at most one Flash packet/ACK, with no sleep or ACK spin.

        Only the UI thread invokes this method, preserving sole UART ownership.
        Failed/ambiguous transactions invalidate the queue until reconnect.
        """
        self._flash_state()
        if self._flash_fault is not None:
            return False
        if self._flash_job is None:
            if not self._flash_queue:
                return False
            self._flash_job = self._flash_queue.popleft()
        job = self._flash_job
        if job['future'].cancelled():
            self._flash_abort(RuntimeError('Cancelled Flash transaction'))
            return False
        try:
            if job['awaiting'] is not None:
                self._read_available()
                op, predicate = job['awaiting']
                matched = self._take_response(op, predicate)
                if matched is None:
                    if time.monotonic() >= job['deadline']:
                        raise T5UIC1TimeoutError('Flash operation timed out')
                    return True
                job['awaiting'] = None
                self._expected_response = None
                job['offset'] += job['chunk_size']
                if job['stage'] == 'read':
                    job['buffer'].extend(matched[4:])
                if job['offset'] >= job['length']:
                    if job['stage'] == 'write':
                        job['stage'], job['offset'] = 'read', 0
                    else:
                        result = bytes(job['buffer'])
                        if job['data'] is not None and result != job['data']:
                            raise T5UIC1ProtocolError('Flash verification mismatch')
                        job['future'].set_result(result)
                        self._flash_job = None
                return True

            # Send only one packet per UI tick. Never send an unrelated
            # write while waiting for an ACK from a previous chunk.
            remaining = job['length'] - job['offset']
            address = job['address'] + job['offset']
            if job['stage'] == 'write':
                chunk = job['data'][job['offset']:
                                    job['offset'] + self.MEMORY_WRITE_CHUNK]
                op, payload = 0x31, bytes((self.MEMORY_FLASH,)) + self._word(address) + chunk
                predicate = lambda value: value == bytes((self.MEMORY_FLASH,)) + b'OK'
                size = len(chunk)
            else:
                size = min(self.MEMORY_READ_CHUNK, remaining)
                op, payload = (0x32, bytes((self.MEMORY_FLASH,))
                               + self._word(address) + bytes((size,)))
                def predicate(value):
                    return (len(value) == 4 + size and value[0] == self.MEMORY_FLASH
                            and int.from_bytes(value[1:3], 'big') == address
                            and value[3] == size)
            self._frames = deque((frame for frame in self._frames
                                  if frame[0] != op), maxlen=self.RX_FRAME_LIMIT)
            self._protected_response_slots().pop(op, None)
            self._expected_response = op, predicate
            self._send(op, payload)
            job['chunk_size'] = size
            job['awaiting'] = op, predicate
            job['deadline'] = time.monotonic() + job['timeout']
            return True
        except (OSError, RuntimeError, ValueError) as error:
            self._flash_abort(error)
            # I/O errors still reach the main UART reconnect handler.
            if self._closed:
                raise
            return False

    def read_flash(self, address, length, *, timeout=1.0):
        return self.read_memory(self.MEMORY_FLASH, address, length, timeout=timeout)

    def store_sram_as_picture(self, picture_id, *, timeout=2.5):
        if not isinstance(picture_id, int) or not 0 <= picture_id <= 15:
            raise ValueError("picture ID must be 0..15")
        if getattr(self, '_cached_picture1', None) == picture_id:
            self._cached_picture1 = None
        with self._transaction_lock:
            self._send(0x33, b"\x5A\xA5" + bytes((picture_id,)))
            payload = self._wait_response(0x33, timeout, self._ok)
            if payload != b"OK":
                raise T5UIC1ProtocolError("Invalid picture Flash acknowledgement")
