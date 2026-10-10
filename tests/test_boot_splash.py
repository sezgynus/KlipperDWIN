"""Boot waits preserve the panel-provided splash and never expose partial menus."""
import unittest
from unittest.mock import Mock, patch
import test_uart_reconnect as reconnect
import test_mmu_driver as packets
from test_regressions import ui
from ui_events import InputEvent


class BootSplashTests(unittest.TestCase):
    def view(self):
        v = reconnect.UARTReconnectTests().display()
        v._boot_active = True
        v._boot_progress = -1
        v._panel_backend_epoch = 1
        v.lcd = packets.lcd()
        v._uart_online = True
        v.EachMomentUpdate = Mock()
        return v

    def test_waiting_for_klipper_only_draws_lower_bar_and_stage(self):
        v = self.view()
        v.pd.subscription.snapshot.return_value['state'] = 'disconnected'
        v._ui_tick()
        self.assertTrue(v._boot_active)
        self.assertEqual(v._boot_progress, 70)
        v.HMI_StartFrame.assert_not_called()
        v.EachMomentUpdate.assert_not_called()
        v._show_message.assert_not_called()
        frames = v.lcd.serial.frames
        self.assertTrue(frames)
        self.assertTrue(all(f[1] in (0x00, 0x05, 0x11, 0x3D) for f in frames))
        for frame in frames:
            if frame[1] == 0x05:
                x0,y0,x1,y1 = [int.from_bytes(frame[i:i+2], 'big') for i in (5,7,9,11)]
                self.assertGreaterEqual(x0, 16)
                self.assertLessEqual(x1, 255)
                self.assertGreaterEqual(y0, 290)
                self.assertLessEqual(y1, 339)
            elif frame[1] == 0x11:
                self.assertEqual(int.from_bytes(frame[9:11], 'big'), 322)
                self.assertIn(b'Waiting for printer...', frame)

    def test_unchanged_wait_does_not_repaint_or_fake_completion(self):
        v = self.view()
        v.pd.subscription.snapshot.return_value['state'] = 'disconnected'
        v._poll_boot()
        v.lcd.serial.frames.clear()
        for _ in range(20):
            v._poll_boot()
        self.assertEqual(v._boot_progress, 70)
        self.assertEqual(v.lcd.serial.frames, [])

    def test_stage_text_changes_even_when_progress_has_not_changed(self):
        v = self.view()
        v._draw_boot_progress(80)
        v.lcd.serial.frames.clear()
        v._draw_boot_progress(80, message='Waiting for printer data')
        self.assertEqual(v._boot_progress, 80)
        self.assertTrue(any(b'Waiting for printer data' in f for f in v.lcd.serial.frames))

    def test_failed_prerequisites_identify_the_stage_without_opening_menu(self):
        v = self.view()
        v.lcd._atlas_synced = False
        v._poll_boot()
        self.assertEqual(v._boot_message, 'Display assets unavailable')
        self.assertEqual(v._boot_progress, 40)
        v.lcd._atlas_synced = True
        v.pd.update_variable = Mock()
        v.pd.connection_error = 'invalid data'
        v._poll_boot()
        self.assertEqual(v._boot_message, 'Waiting for printer data')
        self.assertEqual(v._boot_progress, 80)
        v.HMI_StartFrame.assert_not_called()

    def test_ready_data_and_atlas_finish_once_with_one_full_frame(self):
        v = self.view()
        v.HMI_StartFrame.side_effect = lambda update: v.lcd.clear(0)
        v._poll_boot()
        self.assertFalse(v._boot_active)
        self.assertEqual(v._boot_progress, 100)
        v.HMI_StartFrame.assert_called_once_with(False)
        self.assertEqual([f[1] for f in v.lcd.serial.frames][-2:], [0x01, 0x3D])
        v.pd.sendGCode.assert_not_called()

    def test_missing_atlas_or_invalid_printer_data_keeps_splash(self):
        for cause in ('atlas', 'error'):
            v = self.view()
            if cause == 'atlas':
                v.lcd._atlas_synced = False
            else:
                v.pd.update_variable = Mock()
                v.pd.connection_error = 'invalid data'
            v._poll_boot()
            self.assertTrue(v._boot_active)
            v.HMI_StartFrame.assert_not_called()
            v._show_message.assert_not_called()

    def test_input_is_ignored_during_boot_but_power_on_still_works(self):
        v = self.view()
        v._dispatch_input = Mock()
        v.pd.power_on_if_off = Mock()
        v._process_input(InputEvent('press', 1, 1, 0))
        v._process_input(InputEvent('rotate', 2, 1, 0))
        v._dispatch_input.assert_not_called()
        v._process_input(InputEvent('power_on', 1, 0, 0))
        v.pd.power_on_if_off.assert_called_once()

    def test_connect_restores_splash_before_refresh_without_drawing_home(self):
        v = self.view()
        v._uart_online = False
        v.pd.subscription.snapshot.return_value['state'] = 'disconnected'
        lcd = v.lcd
        lcd._virtual_area_pictures = {}
        lcd._atlas_virtual_areas_loaded = False

        def constructor(port, **kwargs):
            kwargs['startup_progress'](lcd, 40)
            lcd.load_atlases(preserve_boot_splash=True)
            kwargs['startup_progress'](lcd, 70)
            return lcd

        with patch.object(ui, 'T5UIC1Display', side_effect=constructor):
            self.assertTrue(v._ensure_uart())
        v.HMI_StartFrame.assert_not_called()
        v._show_message.assert_not_called()
        opcodes = [f[1] for f in lcd.serial.frames]
        self.assertIn(0x22, opcodes)
        self.assertIn(0x26, opcodes)
        self.assertNotIn(0x3D, opcodes[opcodes.index(0x22):opcodes.index(0x26)])
        self.assertNotIn(0x01, opcodes)
        self.assertIn(0x11, opcodes)
        self.assertIn(0x25, opcodes)
        self.assertEqual(lcd._virtual_area_pictures, {0: 14})

    def test_progress_resets_on_power_cycle_and_uart_retry(self):
        v = self.view()
        v._boot_progress = 70
        v._reset_power_ui()
        self.assertEqual(v._boot_progress, -1)
        self.assertTrue(v._boot_active)
        v._draw_boot_progress(40)
        v._uart_failed()
        self.assertEqual(v._boot_progress, -1)

    def test_constructor_loads_area_zero_and_restores_splash_before_refresh(self):
        import test_uart as uart
        from t5uic1_driver import T5UIC1Display
        port = uart.Port([b'\xAA\x00OK' + T5UIC1Display.TAIL])
        v = self.view()

        def synchronized(lcd):
            lcd._atlas_synced = True
            return True

        stages = []

        def progress(lcd, value):
            stages.append(value)
            v._draw_boot_progress(value, lcd)

        with patch.object(uart.serial_module, 'Serial', return_value=port, create=True), \
                patch.object(T5UIC1Display, '_startup_sync_atlases', synchronized):
            lcd = T5UIC1Display('/dev/fake', wake_delay=0, startup_progress=progress)
        self.addCleanup(lcd.close)
        self.assertEqual(stages, [40, 70])
        opcodes = [frame[1] for frame in port.frames]
        self.assertIn(0x25, opcodes)
        self.assertFalse(set(opcodes) & {0x01, 0x27})
        self.assertIn(0x22, opcodes)
        self.assertIn(0x26, opcodes)
        self.assertNotIn(0x3D, opcodes[opcodes.index(0x22):opcodes.index(0x26)])
        self.assertEqual(lcd._virtual_area_pictures, {0: 14})

    def test_initial_on_observation_does_not_restart_completed_boot(self):
        v = self.view()
        v._boot_active = False
        v._power_monitor = Mock()
        v._power_monitor.poll.return_value = 'on'
        v._relay_status = None
        v._relay_off_serial = 0
        v.pd.power_device = 'Printer'
        lcd = v.lcd
        v._poll_panel_power()
        self.assertIs(v.lcd, lcd)
        self.assertFalse(v._boot_active)
        self.assertEqual(v._relay_status, 'on')

    def test_backend_ready_does_not_reopen_panel_while_boot_is_waiting(self):
        v = self.view()
        v._power_monitor = Mock()
        v._power_monitor.poll.return_value = 'on'
        v._relay_status = 'on'
        v._relay_off_serial = 0
        v.pd.power_device = 'Printer'
        v.pd.subscription.snapshot.return_value['epoch'] = 4
        lcd = v.lcd
        v._poll_panel_power()
        self.assertIs(v.lcd, lcd)
        self.assertTrue(v._uart_online)
