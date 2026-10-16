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
        # These splash tests model an in-flight status check, not a reported
        # shutdown/unavailable result (covered by test_recovery_ui).
        from types import SimpleNamespace
        from klipper_recovery import RecoveryState
        v.pd.recovery = SimpleNamespace(state=RecoveryState(), poll=Mock())
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
        self.assertTrue(all(f[1] in (0x00, 0x05, 0x23, 0x11, 0x27, 0x28, 0x3D) for f in frames))
        for frame in frames:
            if frame[1] == 0x05:
                x0,y0,x1,y1 = [int.from_bytes(frame[i:i+2], 'big') for i in (5,7,9,11)]
                self.assertGreaterEqual(x0, 16)
                self.assertLessEqual(x1, 255)
                self.assertGreaterEqual(y0, 290)
                self.assertLessEqual(y1, 339)
            elif frame[1] == 0x08:
                x = int.from_bytes(frame[2:4], 'big')
                y = int.from_bytes(frame[4:6], 'big')
                width = int.from_bytes(frame[6:8], 'big')
                self.assertGreaterEqual(x, 16)
                self.assertLessEqual(x + width - 1, 255)
                self.assertTrue(290 <= y <= 339)
            elif frame[1] == 0x11:
                self.assertEqual(int.from_bytes(frame[9:11], 'big'), 322)
                self.assertIn(b'Waiting for printer...', frame)

    def test_boot_animation_uses_stock_frames_and_stops_before_main_screen(self):
        v = self.view()
        v._draw_boot_progress(70)
        frame = next(f for f in v.lcd.serial.frames if f[1] == 0x28)
        self.assertEqual(frame[6:11], bytes((0xC0, 3, 250, 254, 10)))
        self.assertEqual(int.from_bytes(frame[4:6], 'big'), 320)
        text = next(f for f in v.lcd.serial.frames if f[1] == 0x11)
        self.assertEqual(int.from_bytes(text[7:9], 'big'), int.from_bytes(frame[2:4], 'big')+24)
        v.lcd.serial.frames.clear()
        v._poll_boot()
        animation = [f for f in v.lcd.serial.frames if f[1] == 0x28]
        self.assertFalse(animation[-1][6] & 0x80)
        self.assertFalse(v._boot_active)

    def test_boot_animation_stops_before_erasing_and_restarts_at_centered_position(self):
        v = self.view()
        v._draw_boot_progress(40)
        old_x = v._boot_animation_x
        for message in ('Preparing menus', 'Waiting for printer data'):
            v.lcd.serial.frames.clear()
            v._draw_boot_progress(80, message=message)
            frames = v.lcd.serial.frames
            animations = [(i,f) for i,f in enumerate(frames) if f[1] == 0x28]
            self.assertEqual(len(animations), 2)
            stop_i, stop = animations[0]
            start_i, start = animations[1]
            self.assertFalse(stop[6] & 0x80)
            self.assertEqual(int.from_bytes(stop[2:4], 'big'), old_x)
            clear_i = next(i for i,f in enumerate(frames)
                           if f[1] == 0x27)
            self.assertLess(stop_i, clear_i)
            self.assertLess(clear_i, start_i)
            old_x = (272-(len(message)*8+24))//2
            self.assertEqual(int.from_bytes(start[2:4], 'big'), old_x)
            self.assertTrue(start[6] & 0x80)
        v.lcd.serial.frames.clear()
        v._draw_boot_progress(100)
        animations = [f for f in v.lcd.serial.frames if f[1] == 0x28]
        self.assertEqual(len(animations), 1)
        self.assertFalse(animations[0][6] & 0x80)

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
        v.pd.update_variable = Mock()
        v.pd.connection_error = 'invalid data'
        v._poll_boot()
        self.assertEqual(v._boot_message, 'Waiting for printer data')
        self.assertEqual(v._boot_progress, 80)
        v.HMI_StartFrame.assert_not_called()

    def test_ready_data_finishes_once_with_one_full_frame(self):
        v = self.view()
        v.HMI_StartFrame.side_effect = lambda update: v.lcd.clear(0)
        v._poll_boot()
        self.assertFalse(v._boot_active)
        self.assertEqual(v._boot_progress, 100)
        v.HMI_StartFrame.assert_called_once_with(False)
        self.assertEqual([f[1] for f in v.lcd.serial.frames][-2:], [0x01, 0x3D])
        v.pd.sendGCode.assert_not_called()

    def test_invalid_printer_data_keeps_splash(self):
        v = self.view()
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

        def constructor(port, **kwargs):
            lcd.show_jpeg(0)
            kwargs['startup_progress'](lcd, 40)
            kwargs['startup_progress'](lcd, 70)
            return lcd

        with patch.object(ui, 'T5UIC1Display', side_effect=constructor):
            self.assertTrue(v._ensure_uart())
        v.HMI_StartFrame.assert_not_called()
        v._show_message.assert_not_called()
        opcodes = [f[1] for f in lcd.serial.frames]
        self.assertIn(0x22, opcodes)
        self.assertNotIn(0x26, opcodes)
        self.assertNotIn(0x01, opcodes)
        self.assertIn(0x11, opcodes)
        self.assertNotIn(0x25, opcodes)

    def test_progress_resets_on_power_cycle_and_uart_retry(self):
        v = self.view()
        v._boot_progress = 70
        v._reset_power_ui()
        self.assertEqual(v._boot_progress, -1)
        self.assertTrue(v._boot_active)
        v._draw_boot_progress(40)
        v._uart_failed()
        self.assertEqual(v._boot_progress, -1)

    def test_constructor_shows_splash_directly_without_cache_copy(self):
        import test_uart as uart
        from t5uic1_driver import T5UIC1Display
        port = uart.Port([b'\xAA\x00OK' + T5UIC1Display.TAIL])
        v = self.view()

        def synchronized(lcd):
            return True

        stages = []

        def progress(lcd, value):
            stages.append(value)
            v._draw_boot_progress(value, lcd)

        with patch.object(uart.serial_module, 'Serial', return_value=port, create=True), \
                patch.object(T5UIC1Display, '_startup_sync_icons', synchronized), \
                patch('boot_artwork.sync'), patch('shared_artwork.sync'), \
                patch.object(T5UIC1Display, '_startup_animation_library', return_value=3):
            lcd = T5UIC1Display('/dev/fake', wake_delay=0, startup_progress=progress)
        self.addCleanup(lcd.close)
        self.assertEqual(stages, [40, 70])
        opcodes = [frame[1] for frame in port.frames]
        self.assertNotIn(0x25, opcodes)
        self.assertNotIn(0x01, opcodes)
        self.assertTrue(all(f[2] & 1 == 0 for f in port.frames if f[1] == 0x27))
        self.assertIn(0x22, opcodes)
        self.assertNotIn(0x26, opcodes)

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


class BootFilePreparationTests(unittest.TestCase):
    view = BootSplashTests.view
    def test_boot_prepares_files_before_main_and_does_not_wait_forever(self):
        v = self.view()
        v.pd.prefetch_files = Mock()
        v.pd._files_loading = True
        v.pd._directory_loading = False
        with patch.object(ui.time, 'monotonic', return_value=10):
            v._poll_boot()
        self.assertTrue(v._boot_active)
        v.HMI_StartFrame.assert_not_called()
        v.pd.prefetch_files.assert_called_once()
        with patch.object(ui.time, 'monotonic', return_value=16):
            v._poll_boot()
        self.assertFalse(v._boot_active)
        v.HMI_StartFrame.assert_called_once()
