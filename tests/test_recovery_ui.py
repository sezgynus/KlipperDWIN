from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from klipper_recovery import RecoveryState
from test_capabilities import display, snapshot
from ui_events import InputEvent


class RecoveryUITests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view.checkkey = view.MaintenanceMenu
        view._maintenance_page = 'result'
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
        return view

    def event(self, view, kind, value=0):
        return InputEvent(kind, value, 999, view._uart_epoch)

    def test_shutdown_replaces_generic_unavailable_with_reason_and_actions(self):
        view = self.view()
        self.assertTrue(view._poll_recovery_ui())
        self.assertEqual(view.checkkey, view.RecoveryScreen)
        title, rows, _ = view._draw_list_menu.call_args.args
        self.assertEqual(title, 'Klipper shutdown')
        self.assertIn('Firmware Restart', [r[0] for r in rows])
        self.assertTrue(any("MCU 'toolhead'" in r[0] for r in rows))
        self.assertGreater(len(rows), view.TROWS)
        view.pd.recovery.request.assert_not_called()

    def test_offline_encoder_bypasses_normal_ready_gate_but_requires_second_confirmation(self):
        view = self.view()
        view._poll_recovery_ui()
        view._ui_lifecycle = Mock(side_effect=AssertionError('normal READY gate'))
        view._process_input(self.event(view, 'rotate', -2))
        self.assertEqual(view._recovery_selection, 2)
        view._process_input(self.event(view, 'press'))
        self.assertEqual(view._recovery_confirm, 'firmware')
        self.assertEqual(view._recovery_selection, 0)
        view.pd.recovery.request.assert_not_called()
        # Default Cancel, then a deliberate move to Restart and press.
        view._process_input(self.event(view, 'rotate', -1))
        view._process_input(self.event(view, 'press'))
        view.pd.recovery.request.assert_called_once_with('firmware')

    def test_stale_uart_input_and_cancel_never_restart(self):
        view = self.view()
        view._poll_recovery_ui()
        view._recovery_confirm = 'firmware'
        view._process_input(InputEvent('press', 0, 999, 6))
        self.assertEqual(view._recovery_confirm, 'firmware')
        view._process_input(self.event(view, 'press'))
        self.assertIsNone(view._recovery_confirm)
        view.pd.recovery.request.assert_not_called()

    def test_error_scroll_and_selection_do_not_reset_on_unchanged_poll(self):
        view = self.view()
        view._poll_recovery_ui()
        view._recovery_input(self.event(view, 'rotate', -10))
        self.assertEqual(view._recovery_selection, 10)
        view._draw_list_menu.reset_mock()
        view._poll_recovery_ui()
        view._poll_recovery_ui()
        self.assertEqual(view._recovery_selection, 10)
        # First poll after input may refresh signature; steady polling is quiet.
        self.assertLessEqual(view._draw_list_menu.call_count, 1)

    def test_ready_returns_home_without_resuming_interrupted_test(self):
        view = self.view()
        view._poll_recovery_ui()
        view.Goto_MainMenu = Mock()
        view.pd.connection_error = None
        self.assertFalse(view._poll_recovery_ui())
        view.Goto_MainMenu.assert_called_once_with()
        view.pd.recovery.request.assert_not_called()

    def test_boot_with_shutdown_exits_splash_and_exposes_recovery(self):
        view = self.view()
        view._boot_active = True
        view._boot_animation_running = True
        view._boot_animation_active_library = 1
        view._boot_animation_x = 100
        view._poll_recovery_ui()
        self.assertFalse(view._boot_active)
        self.assertFalse(view._boot_animation_running)
        self.assertEqual(view.checkkey, view.RecoveryScreen)

    def test_power_off_has_priority_over_recovery(self):
        view = self.view()
        view._relay_status = 'off'
        self.assertFalse(view._poll_recovery_ui())
        self.assertNotEqual(view.checkkey, view.RecoveryScreen)

    def offline_producer_view(self):
        from threading import Lock
        view = self.view()
        view._poll_recovery_ui()
        view._input_lock = Lock()
        view._producer_value = 0
        view._last_encoder_time = None
        view._loop = SimpleNamespace(post=Mock(return_value=True))
        view.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 100}
        return view

    def test_physical_encoder_producer_reaches_offline_recovery_handler(self):
        view = self.offline_producer_view()
        view.encoder_has_data(-2)
        event = view._loop.post.call_args.args[0]
        self.assertEqual(event.kind, 'rotate')
        self.assertEqual(event.value, -2)
        view._process_input(event)
        self.assertEqual(view._recovery_selection, 2)
        view.pd.recovery.request.assert_not_called()

    def test_remote_rotation_and_click_are_enqueued_while_klipper_offline(self):
        view = self.offline_producer_view()
        self.assertTrue(view._remote_input('rotate', -2))
        view._process_input(view._loop.post.call_args.args[0])
        self.assertTrue(view._remote_input('press', 1))
        view._process_input(view._loop.post.call_args.args[0])
        self.assertEqual(view._recovery_confirm, 'firmware')
        self.assertEqual(view._recovery_selection, 0)
        view.pd.recovery.request.assert_not_called()

    def test_physical_short_release_opens_confirmation_and_can_confirm(self):
        import time
        view = self.offline_producer_view()
        view._recovery_selection = 2
        view._button_started_at = time.monotonic() - .1
        view._button_can_power_off = False
        view._button_origin = (100, view._uart_epoch)
        view._button_released()
        event = view._loop.post.call_args.args[0]
        self.assertEqual(event.kind, 'button_release')
        view._process_input(event)
        self.assertEqual(view._recovery_confirm, 'firmware')
        view.pd.recovery.request.assert_not_called()
        view._recovery_selection = 1
        view._button_started_at = time.monotonic() - .1
        view._button_released()
        view._process_input(view._loop.post.call_args.args[0])
        view.pd.recovery.request.assert_called_once_with('firmware')

    def test_long_release_and_stale_uart_never_select_restart(self):
        view = self.offline_producer_view()
        view._recovery_confirm = 'firmware'
        view._recovery_selection = 1
        view._process_input(InputEvent('button_release', 500, 100, view._uart_epoch))
        view._process_input(InputEvent('button_release', 100, 100, view._uart_epoch-1))
        view.pd.recovery.request.assert_not_called()
        self.assertEqual(view._recovery_confirm, 'firmware')

    def test_normal_offline_menus_still_reject_producer_input(self):
        view = self.offline_producer_view()
        view.checkkey = view.TemperatureID
        self.assertFalse(view._remote_input('rotate', -1))
        self.assertFalse(view._remote_input('press', 1))
        view._loop.post.assert_not_called()

    def test_stale_action_feedback_does_not_trap_recovery_navigation(self):
        view = self.offline_producer_view()
        view._action_feedback = SimpleNamespace(phase='running')
        self.assertTrue(view._remote_input('rotate', -1))
        view._process_input(view._loop.post.call_args.args[0])
        self.assertEqual(view._recovery_selection, 1)
