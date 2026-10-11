import unittest
from unittest.mock import patch

from t5uic1_driver import T5UIC1Display as Driver, T5UIC1TimeoutError

serial_module = Driver.__init__.__globals__['serial']


class Port:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.frames = []
        self.closed = 0
        self.short = False

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size=1):
        if not self.chunks:
            return b''
        chunk = self.chunks.pop(0)
        value, remaining = chunk[:size], chunk[size:]
        if remaining:
            self.chunks.insert(0, remaining)
        return value

    def write(self, frame):
        self.frames.append(bytes(frame))
        return len(frame) - 1 if self.short else len(frame)

    def close(self):
        self.closed += 1


class UARTTests(unittest.TestCase):
    def open(self, port, **kwargs):
        # UART framing tests intentionally isolate the transport constructor
        # from managed icon persistence, covered in test_managed_icon_library.py.
        with patch.object(serial_module, 'Serial', return_value=port, create=True), \
                patch.object(Driver.__init__.__globals__['time'], 'sleep'), \
                patch('icon_library.sync_library'):
            return Driver('/dev/fake', **kwargs)

    def test_first_handshake_frame_and_fragmented_ack_with_noise(self):
        tail = Driver.TAIL
        port = Port([b'noise\xAA', b'\x00', b'O', b'K', tail[:2], tail[2:]])
        result = self.open(port)
        self.assertEqual(port.frames[0], b'\xAA\x00\xCC\x33\xC3\x3C')
        self.assertTrue(all(frame.startswith(Driver.HEADER) and frame.endswith(Driver.TAIL)
                            for frame in port.frames))
        result.close()
        result.close()
        self.assertEqual(port.closed, 1)

    def test_no_screen_has_bounded_retries_and_closes_port(self):
        port = Port()
        with self.assertRaises(T5UIC1TimeoutError):
            self.open(port, handshake_timeout=.005, handshake_attempts=2)
        self.assertEqual(len(port.frames), 2)
        self.assertEqual(port.closed, 1)

    def test_noise_is_discarded_and_partial_frame_is_retained(self):
        result = Driver.__new__(Driver)
        result._rx = bytearray(b'x' * 10000)
        result._frames = __import__('collections').deque()
        result._aux_rx = __import__('collections').deque()
        result._crc_errors = 0
        result._parse_rx()
        self.assertEqual(result._rx, bytearray())
        result._rx.extend(b'\xAA\x00O')
        result._parse_rx()
        self.assertEqual(result._rx, bytearray(b'\xAA\x00O'))

    def test_short_write_is_not_retried_and_constructor_closes(self):
        port = Port()
        port.short = True
        with self.assertRaises(IOError):
            self.open(port)
        self.assertEqual(len(port.frames), 1)
        self.assertEqual(port.closed, 1)

    def test_backlight_validation_does_not_corrupt_next_frame(self):
        port = Port([b'\xAA\x00OK' + Driver.TAIL])
        result = self.open(port)
        with self.assertRaises(ValueError):
            result.set_backlight(256)
        result.set_backlight(0)
        self.assertEqual(port.frames[-1], b'\xAA\x30\x00\xCC\x33\xC3\x3C')
        result.close()
        with self.assertRaises(RuntimeError):
            result.update()

    def test_instance_receive_buffers_are_independent(self):
        first = self.open(Port([b'\xAA\x00OK' + Driver.TAIL]))
        second = self.open(Port([b'\xAA\x00OK' + Driver.TAIL]))
        first._rx.extend(b'abc')
        self.assertEqual(second._rx, bytearray())
        first.close()
        second.close()


if __name__ == '__main__':
    unittest.main()
