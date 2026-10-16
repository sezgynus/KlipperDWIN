"""CI-only end-to-end encoder routing and dedicated error panel layout."""
from types import SimpleNamespace
from threading import Lock
from unittest.mock import Mock
import unittest

from klipper_recovery import RecoveryState
from test_capabilities import display, snapshot
from ui_events import InputEvent
from ui_recovery import error_lines


class RecoveryUITests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view.checkkey = view.MaintenanceMenu
        view._closed = False
        view._boot_active = False
        view._uart_online = True
        view._uart_epoch = 7
        view._relay_status = 'on'
        view._display_activity = Mock(return_value=False)
        view.pd.connection_error = 'Klipper not ready'
        view.pd.recovery = SimpleNamespace(
            state=RecoveryState('shutdown', "MCU 'toolhead' shutdown: Timer too close\n" + 'details '*100,
                                ('restart', 'firmware')),
            busy=False, notice='', poll=Mock(), refresh=Mock(), request=Mock())
        view._draw_list_menu = Mock()
        view._input_lock = Lock()
        view._producer_value = 0
        view._last_encoder_time = None
        view._loop = SimpleNamespace(post=Mock(return_value=True))
        view.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 100}
        return view

    def event(self, view, kind, value=0):
        return InputEvent(kind, value, 100, view._uart_epoch)

    def enter(self, view):
        self.assertTrue(view._poll_recovery_ui())
        self.assertEqual(view.checkkey, view.RecoveryScreen)

    def test_error_is_plain_text_and_controls_are_fixed_below_text(self):
        view = self.view()
        self.enter(view)
        view._draw_list_menu.assert_not_called()
        texts = [c.args for c in view.lcd.draw_text.call_args_list]
        self.assertTrue(any("MCU 'toolhead'" in c[-1] for c in texts))
        for label in ('Restart Klipper', 'Firmware Restart', 'Refresh connection'):
            calls = [c for c in texts if c[-1] == label]
            self.assertEqual(len(calls), 1)
            self.assertGreaterEqual(calls[0][-2], view.RECOVERY_BUTTON_TOP)
        view.pd.recovery.request.assert_not_called()

    def test_newlines_are_split_before_panel_conversion_not_question_marks(self):
        lines = error_lines('Shutdown due to webhooks request\r\nOnce corrected,\nFIRMWARE_RESTART\nPrinter is shutdown')
        self.assertEqual(lines[-1], 'Printer is shutdown')
        self.assertIn('FIRMWARE_RESTART', lines)
        self.assertFalse(any('?' in line or '\n' in line or '\r' in line for line in lines))
        self.assertTrue(all(len(line) <= 30 for line in lines))

    def test_remote_producer_click_dispatches_selected_restart_once_without_dialog(self):
        view = self.view()
        self.enter(view)
        # Initial selection is Refresh (safe); one step left is Firmware.
        self.assertTrue(view._remote_input('rotate', 1))
        view._process_input(view._loop.post.call_args.args[0])
        self.assertEqual(view._recovery_selection, 1)
        self.assertTrue(view._remote_input('press', 1))
        view._process_input(view._loop.post.call_args.args[0])
        view.pd.recovery.request.assert_called_once_with('firmware')
        self.assertEqual(view.checkkey, view.RecoveryScreen)

    def test_physical_encoder_and_short_release_reach_restart(self):
        import time
        view = self.view()
        self.enter(view)
        view.encoder_has_data(1)
        view._process_input(view._loop.post.call_args.args[0])
        self.assertEqual(view._recovery_selection, 1)
        view._button_started_at = time.monotonic()-.1
        view._button_can_power_off = False
        view._button_origin = (100, view._uart_epoch)
        view._button_released()
        view._process_input(view._loop.post.call_args.args[0])
        view.pd.recovery.request.assert_called_once_with('firmware')

    def test_text_scroll_moves_text_but_not_action_positions(self):
        view = self.view()
        self.enter(view)
        view._process_input(self.event(view, 'rotate', 3))
        self.assertEqual(view._recovery_selection, -1)
        view.lcd.reset_mock()
        view._process_input(self.event(view, 'rotate', -5))
        self.assertEqual(view._recovery_scroll, 5)
        positions = {c.args[-1]: c.args[-2] for c in view.lcd.draw_text.call_args_list
                     if c.args[-1] in ('Restart Klipper', 'Firmware Restart', 'Refresh connection')}
        self.assertEqual(positions, {'Restart Klipper': 340, 'Firmware Restart': 384,
                                     'Refresh connection': 428})
        view._process_input(self.event(view, 'press'))
        self.assertEqual(view._recovery_selection, 0)
        view.pd.recovery.request.assert_not_called()

    def test_refresh_is_read_only_and_busy_restart_cannot_repeat(self):
        view = self.view()
        self.enter(view)
        view._process_input(self.event(view, 'press'))
        view.pd.recovery.refresh.assert_called_once_with()
        view.pd.recovery.request.assert_not_called()
        view.pd.recovery.busy = True
        view._recovery_selection = 1
        view._process_input(self.event(view, 'press'))
        view.pd.recovery.request.assert_not_called()

    def test_long_release_stale_uart_and_regular_offline_menu_never_restart(self):
        view = self.view()
        self.enter(view)
        view._recovery_selection = 1
        view._process_input(self.event(view, 'button_release', 500))
        view._process_input(InputEvent('button_release', 100, 100, 6))
        view.pd.recovery.request.assert_not_called()
        view.checkkey = view.TemperatureID
        view._loop.post.reset_mock()
        self.assertFalse(view._remote_input('rotate', -1))
        self.assertFalse(view._remote_input('press', 1))
        view._loop.post.assert_not_called()

    def test_stale_feedback_does_not_trap_navigation(self):
        view = self.view()
        self.enter(view)
        view._action_feedback = SimpleNamespace(phase='running')
        self.assertTrue(view._remote_input('rotate', 1))
        view._process_input(view._loop.post.call_args.args[0])
        self.assertEqual(view._recovery_selection, 1)

    def test_unchanged_poll_is_quiet_and_ready_goes_home_without_resuming_test(self):
        view = self.view()
        self.enter(view)
        view.lcd.reset_mock()
        view._poll_recovery_ui()
        view.lcd.draw_text.assert_not_called()
        view.Goto_MainMenu = Mock()
        view.pd.connection_error = None
        self.assertFalse(view._poll_recovery_ui())
        view.Goto_MainMenu.assert_called_once_with()

    def test_cold_shutdown_stops_splash_and_power_off_has_priority(self):
        view = self.view()
        view._boot_active = True
        view._boot_animation_running = True
        view._boot_animation_active_library = 1
        view._boot_animation_x = 100
        self.enter(view)
        self.assertFalse(view._boot_active)
        self.assertFalse(view._boot_animation_running)
        view = self.view()
        view._relay_status = 'off'
        self.assertFalse(view._poll_recovery_ui())
