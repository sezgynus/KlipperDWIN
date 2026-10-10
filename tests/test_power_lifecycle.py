import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from power_lifecycle import PowerMonitor
from moonraker_subscription import MoonrakerSubscription
import test_uart_reconnect as reconnect
from test_regressions import ui


class RelayLifecycleTests(unittest.TestCase):
    def view(self):
        v = reconnect.UARTReconnectTests().display()
        v._power_monitor = Mock()
        v._power_monitor.poll.return_value = 'on'
        v.pd.power_device = 'Printer'
        v._relay_status = 'on'
        v._relay_off_serial = 0
        v._panel_backend_epoch = 1
        v._uart_online = True
        v.checkkey = v.MainMenu
        v.select_page.set(5)
        return v

    def test_external_off_closes_uart_and_resets_second_home_page(self):
        v = self.view()
        old = v.lcd
        v._power_monitor.poll.return_value = 'off'
        v._poll_panel_power()
        self.assertEqual(v.select_page.now, 0)
        self.assertEqual(v.checkkey, v.MainMenu)
        old.close.assert_called_once()
        self.assertFalse(v._uart_online)
        with patch.object(ui, 'T5UIC1Display') as factory:
            self.assertFalse(v._ensure_uart())
        factory.assert_not_called()
        v.pd.sendGCode.assert_not_called()

    def test_on_reconnects_immediately_with_new_driver_and_atlases(self):
        v = self.view()
        v._relay_status = 'off'
        v._next_uart_retry = float('inf')
        v._power_origin = v.Info
        v._power_focus = True
        v._poll_panel_power()
        new = Mock()
        with patch.object(ui, 'T5UIC1Display', return_value=new) as factory:
            self.assertTrue(v._ensure_uart())
        factory.assert_called_once()
        self.assertIs(v.lcd, new)
        self.assertFalse(v._power_focus)
        self.assertIsNone(v._power_origin)
        self.assertEqual(v.select_page.now, 0)

    def test_new_power_session_restores_area_zero_before_first_frame(self):
        import test_mmu_driver as packets
        v = self.view()
        v._relay_status = 'off'
        v._poll_panel_power()
        lcd = packets.lcd()
        lcd.serial.frames.clear()
        lcd._virtual_area_pictures = {}
        lcd._atlas_virtual_areas_loaded = False

        def construct(*args, **kwargs):
            lcd.load_atlases()
            return lcd

        v.HMI_StartFrame = lambda update: lcd.clear(0)
        with patch.object(ui, 'T5UIC1Display', side_effect=construct):
            self.assertTrue(v._ensure_uart())
        opcodes = [frame[1] for frame in lcd.serial.frames]
        self.assertEqual(opcodes[0], 0x25)
        self.assertEqual(lcd._virtual_area_pictures[0], 14)
        self.assertEqual(opcodes[-1], 0x3D)
        self.assertFalse(set(opcodes) & {0x31, 0x32, 0x33})

    def test_brief_off_on_between_ticks_is_detected_by_notification_serial(self):
        v = self.view()
        s = v.pd.subscription.snapshot.return_value
        s['power_off_serial'] = {'printer': 1}
        v._poll_panel_power()
        self.assertFalse(v._uart_online)
        self.assertEqual(v.select_page.now, 0)
        old_epoch = v._uart_epoch
        v._poll_panel_power()
        self.assertEqual(v._uart_epoch, old_epoch)

    def test_backend_recovery_catches_cycle_missed_during_websocket_outage(self):
        v = self.view()
        v.pd.subscription.snapshot.return_value['epoch'] = 4
        v._poll_panel_power()
        self.assertFalse(v._uart_online)
        self.assertEqual(v.select_page.now, 0)
        self.assertEqual(v._panel_backend_epoch, 4)

    def test_unknown_power_is_not_off_and_stable_on_preserves_navigation(self):
        v = self.view()
        for status in ('on', None):
            v._power_monitor.poll.return_value = status
            v._poll_panel_power()
            self.assertTrue(v._uart_online)
            self.assertEqual(v.select_page.now, 5)

    def test_cycle_discards_confirmation_and_queued_input_epoch(self):
        v = self.view()
        v.checkkey = v.MMUMenu
        v._mmu_confirmation = object()
        v._pending_start = object()
        old_epoch = v._uart_epoch
        v._power_monitor.poll.return_value = 'off'
        v._poll_panel_power()
        self.assertEqual(v.checkkey, v.MainMenu)
        self.assertIsNone(v._mmu_confirmation)
        self.assertIsNone(v._pending_start)
        self.assertGreater(v._uart_epoch, old_epoch)

    def test_notification_counters_survive_klipper_invalidation(self):
        s = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(s.close)
        for status in ('off', 'on'):
            s._notification({'method': 'notify_power_changed', 'params': [
                {'device': 'Printer', 'status': status}]})
        s._invalidate('MCU disconnected')
        snapshot = s.snapshot()
        self.assertEqual(snapshot['power_devices']['printer'], 'on')
        self.assertEqual(snapshot['power_off_serial']['printer'], 1)

    def test_poll_does_not_block_or_overlap_reads_and_errors_are_unknown(self):
        client = Mock(timeout=1)
        with patch('power_lifecycle.ReadWorker') as worker:
            monitor = PowerMonitor(client, 'Printer')
        future = Future()
        worker.return_value.submit.return_value = future
        with patch('power_lifecycle.time.monotonic', return_value=0):
            self.assertIsNone(monitor.poll())
            self.assertIsNone(monitor.poll())
        worker.return_value.submit.assert_called_once()
        future.set_result({'result': {'devices': [{'device': 'printer', 'status': 'off'}]}})
        with patch('power_lifecycle.time.monotonic', return_value=.5):
            self.assertEqual(monitor.poll(), 'off')
        failure = Future()
        failure.set_exception(RuntimeError('network down'))
        monitor.future = failure
        with patch('power_lifecycle.time.monotonic', return_value=.5):
            self.assertIsNone(monitor.poll())
        monitor.close()
        worker.return_value.close.assert_called_once()
