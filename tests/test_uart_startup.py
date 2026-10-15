import unittest
from unittest.mock import Mock, patch
from uart_startup import PanelProbe
from test_uart import Port, Driver
import test_uart_reconnect as reconnect
from test_regressions import ui


class FastStartupTests(unittest.TestCase):
    def probe(self):
        port = Port()
        with patch('uart_startup.serial.Serial', return_value=port):
            probe = PanelProbe('/dev/fake')
        self.addCleanup(probe.close)
        return probe, port

    def test_fast_handshakes_are_nonblocking_rate_limited_and_back_off(self):
        probe, port = self.probe()
        with patch('uart_startup.time.monotonic', return_value=0):
            probe.accelerate()
            self.assertIsNone(probe.poll())
        with patch('uart_startup.time.monotonic', return_value=.1):
            self.assertIsNone(probe.poll())
        self.assertEqual(len(port.frames), 1)
        with patch('uart_startup.time.monotonic', return_value=.15):
            probe.poll()
        self.assertEqual(len(port.frames), 2)
        with patch('uart_startup.time.monotonic', return_value=11):
            probe.poll()
        self.assertEqual(probe.next_send, 16)

    def test_fragmented_ack_transfers_live_port_without_closing_it(self):
        probe, port = self.probe()
        port.chunks = [b'noise' + probe.RESPONSE[:3], probe.RESPONSE[3:]]
        self.assertIsNone(probe.poll())
        self.assertIs(probe.poll(), port)
        probe.close()
        self.assertEqual(port.closed, 0)
        port.close()

    def test_connected_driver_skips_sleep_and_second_handshake(self):
        port = Port()
        with patch('t5uic1_driver.time.sleep') as sleep, patch('boot_artwork.sync'), patch('shared_artwork.sync'), \
                patch('icon_library.sync_library'):
            lcd = Driver('/dev/fake', connected_serial=port)
        self.addCleanup(lcd.close)
        self.assertNotIn((.750,), [c.args for c in sleep.call_args_list])
        self.assertFalse(any(frame[1] in (0x00, 0x34) for frame in port.frames))

    def view(self, available):
        v = reconnect.UARTReconnectTests().display()
        v._panel_probe = None
        v._uart_fast_until = 0
        v._uart_start_signal = None
        v._power_monitor = Mock(available=available)
        v._power_monitor.poll.return_value = None
        v._relay_status = None
        v._relay_off_serial = 0
        v._panel_backend_epoch = 1
        v.pd.power_device = 'Printer'
        return v

    def test_configured_power_on_triggers_before_backend_ready(self):
        v = self.view(True)
        v._power_monitor.poll.return_value = 'on'
        v.pd.subscription.snapshot.return_value['state'] = 'disconnected'
        v._next_uart_retry = 100
        with patch.object(ui.time, 'monotonic', return_value=2):
            v._poll_panel_power()
        self.assertEqual(v._next_uart_retry, 0)
        self.assertEqual(v._uart_fast_until, 12)

    def test_absent_power_device_uses_backend_ready_once_per_epoch(self):
        v = self.view(False)
        with patch.object(ui.time, 'monotonic', return_value=2):
            v._poll_panel_power()
        self.assertEqual(v._uart_fast_until, 12)
        with patch.object(ui.time, 'monotonic', return_value=3):
            v._poll_panel_power()
        self.assertEqual(v._uart_fast_until, 12)
        v.pd.subscription.snapshot.return_value['epoch'] = 2
        with patch.object(ui.time, 'monotonic', return_value=4):
            v._poll_panel_power()
        self.assertEqual(v._uart_fast_until, 14)

    def test_unknown_or_power_off_does_not_use_backend_fallback(self):
        for available, status in ((None, None), (True, 'off')):
            v = self.view(available)
            v._power_monitor.poll.return_value = status
            v._poll_panel_power()
            self.assertEqual(v._uart_fast_until, 0)

    def test_pending_probe_returns_without_constructing_or_waiting(self):
        v = self.view(True)
        v._panel_probe = Mock()
        v._panel_probe.poll.return_value = None
        v._loop = Mock()
        with patch.object(ui, 'T5UIC1Display') as driver:
            self.assertFalse(v._ensure_uart())
        driver.assert_not_called()
        v._loop.set_interval.assert_called_with(.05)

    def test_power_notification_triggers_when_http_is_unknown(self):
        v = self.view(None)
        v.pd.subscription.snapshot.return_value['power_devices'] = {'printer': 'on'}
        v._panel_probe = Mock()
        v._poll_panel_power()
        v._panel_probe.accelerate.assert_called_once()

    def test_stale_notification_does_not_override_later_http_power_off(self):
        v = self.view(True)
        v.pd.subscription.snapshot.return_value['power_devices'] = {'printer': 'on'}
        v._poll_panel_power()
        v._power_monitor.poll.return_value = 'off'
        v._poll_panel_power()
        self.assertEqual(v._relay_status, 'off')
        self.assertIsNone(v._uart_start_signal)

    def test_known_absent_device_ignores_old_notification(self):
        v = self.view(False)
        v.pd.subscription.snapshot.return_value['power_devices'] = {'printer': 'on'}
        v._poll_panel_power()
        self.assertEqual(v._uart_start_signal, ('backend', 1))
