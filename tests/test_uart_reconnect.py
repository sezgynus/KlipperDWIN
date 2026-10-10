import unittest
from unittest.mock import Mock, patch

from test_capabilities import snapshot, display
from test_regressions import ui
from ui_events import InputEvent


class UARTReconnectTests(unittest.TestCase):
    def display(self):
        result = display(snapshot())
        result._closed = False
        result._settings = ('/dev/fake',)
        result._uart_epoch = 0
        result._uart_online = False
        result._next_uart_retry = 0
        result._next_uart_probe = 0
        result._uart_probe_failures = 0
        result.HMI_Init = Mock()
        result.HMI_StartFrame = Mock()
        result._show_message = Mock()
        result._encoder_event = result.ENCODER_DIFF_NO
        return result

    def test_missing_panel_retries_on_tick_and_redraws_without_commands(self):
        result = self.display()
        result.lcd = None
        port = Mock()
        with patch.object(ui, 'T5UIC1Display', side_effect=[TimeoutError('no panel'), port]) as factory:
            with patch.object(ui.time, 'monotonic', return_value=0):
                self.assertFalse(result._ensure_uart())
            with patch.object(ui.time, 'monotonic', return_value=4):
                result._ui_tick()
                self.assertEqual(factory.call_count, 1)
            with patch.object(ui.time, 'monotonic', return_value=5):
                result._ui_tick()
        self.assertTrue(result._uart_online)
        self.assertIs(result.lcd, port)
        result.HMI_Init.assert_called_once()
        result.HMI_StartFrame.assert_called_once_with(False)
        result.pd.sendGCode.assert_not_called()

    def test_serial_write_failure_closes_and_schedules_reconnect(self):
        result = self.display()
        result._uart_online = True
        old = result.lcd
        old._closed = True
        result.EachMomentUpdate = Mock(side_effect=OSError('write failed'))
        with patch.object(ui.time, 'monotonic', return_value=10):
            result._ui_tick()
        old.close.assert_called_once()
        self.assertFalse(result._uart_online)
        self.assertIsNone(result.lcd)
        self.assertEqual(result._next_uart_retry, 15)

    def test_liveness_probe_requires_two_failures_before_reconnect(self):
        result = self.display()
        result._uart_online = True
        result.lcd.handshake.return_value = False
        result.EachMomentUpdate = Mock()

        with patch.object(ui.time, 'monotonic', return_value=10):
            result._ui_tick()
        self.assertTrue(result._uart_online)
        self.assertEqual(result._uart_probe_failures, 1)

        with patch.object(ui.time, 'monotonic', return_value=12):
            result._ui_tick()
        self.assertFalse(result._uart_online)
        self.assertIsNone(result.lcd)
        self.assertEqual(result._next_uart_retry, 17)

    def test_successful_liveness_probe_resets_failure_count(self):
        result = self.display()
        result._uart_online = True
        result._uart_probe_failures = 1
        result.lcd.handshake.return_value = True
        result.EachMomentUpdate = Mock()

        with patch.object(ui.time, 'monotonic', return_value=10):
            result._ui_tick()

        self.assertTrue(result._uart_online)
        self.assertEqual(result._uart_probe_failures, 0)
        self.assertEqual(result._next_uart_probe, 12)

    def test_liveness_probe_is_rate_limited(self):
        result = self.display()
        result._uart_online = True
        result._next_uart_probe = 12
        result.EachMomentUpdate = Mock()

        with patch.object(ui.time, 'monotonic', return_value=10):
            result._ui_tick()

        result.lcd.handshake.assert_not_called()

    def test_old_uart_epoch_and_offline_input_are_discarded(self):
        result = self.display()
        result._dispatch_input = Mock()
        result._uart_online = True
        result._uart_epoch = 2
        result._process_input(InputEvent('press', 1, 1, 1))
        result._dispatch_input.assert_not_called()
        result._process_input(InputEvent('press', 1, 1, 2))
        result._dispatch_input.assert_called_once()
        result._dispatch_input.reset_mock()
        result._uart_online = False
        result._process_input(InputEvent('press', 1, 1, 2))
        result._dispatch_input.assert_not_called()

    def test_input_uart_failure_does_not_flush_closed_driver(self):
        result = self.display()
        result._uart_online = True
        old = result.lcd
        old._closed = False
        result._sync_input_state = Mock(return_value=True)

        def fail_during_draw():
            old._closed = True
            raise OSError('write failed')

        result._dispatch_input = Mock(side_effect=fail_during_draw)
        result._process_input(InputEvent('press', 1, 1, result._uart_epoch))

        self.assertFalse(result._uart_online)
        self.assertIsNone(result.lcd)
        old.close.assert_called_once()
        old.update.assert_not_called()

    def test_closed_display_does_not_reopen_port(self):
        result = self.display()
        result._closed = True
        with patch.object(ui, 'T5UIC1Display') as factory:
            self.assertFalse(result._ensure_uart())
        factory.assert_not_called()

    def test_unrelated_render_error_is_not_treated_as_uart_failure(self):
        result = self.display()
        result._uart_online = True
        result.lcd._closed = False
        result.EachMomentUpdate = Mock(side_effect=OSError('unrelated'))
        with self.assertRaises(OSError):
            result._ui_tick()
        self.assertTrue(result._uart_online)

    def test_current_screen_is_flushed_immediately_after_reconnect(self):
        from test_t5uic1_driver import driver
        result = self.display()
        lcd = driver()
        lcd.load_display_settings = Mock(return_value=(100, 0))
        lcd._needs_update = False
        result.HMI_Init = Mock()
        result.HMI_StartFrame = lambda update: lcd.clear(0)
        with patch.object(ui, 'T5UIC1Display', return_value=lcd):
            self.assertTrue(result._ensure_uart())
        result.HMI_Init.assert_called_once_with()
        self.assertEqual([frame[1] for frame in lcd.serial.frames], [0x30, 1, 0x3D])
        self.assertFalse(lcd._needs_update)


if __name__ == '__main__':
    unittest.main()
