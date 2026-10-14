from concurrent.futures import Future
from dataclasses import replace
from threading import Event, Thread
import json
from unittest.mock import Mock, patch
import unittest
from test_capabilities import snapshot, display
from buzzer_control import Player, outputs, ADDRESS, RECORD_SIZE
from test_regressions import ui
from test_t5uic1_driver import driver

# UI fixtures retain the modules loaded inside their mocked GPIO import context.
Settings = ui.BuzzerSettings


def data():
    value = snapshot()
    value['settings'].update({'pwm_cycle_time buzzer': {'scale': 1},
                              'pwm_cycle_time second': {'scale': 100},
                              'output_pin unrelated': {}})
    value['objects'].extend(('pwm_cycle_time Buzzer', 'pwm_cycle_time Second', 'output_pin unrelated'))
    return value


class BuzzerSettingsTests(unittest.TestCase):
    def test_record_round_trip_corruption_and_memory_ranges(self):
        value = Settings('Buzzer', 80, 5, 0)
        raw = value.encode()
        self.assertEqual(len(raw), RECORD_SIZE)
        self.assertEqual(Settings.decode(raw), value)
        broken = bytearray(raw); broken[15] ^= 1
        self.assertIsNone(Settings.decode(broken))
        self.assertIsNone(Settings.decode(bytes(RECORD_SIZE)))
        from icon_library import METADATA_ADDRESS, METADATA_SIZE
        self.assertGreaterEqual(ADDRESS, METADATA_ADDRESS + METADATA_SIZE)
        self.assertEqual(outputs(data()['settings'], data()['objects']), ('Buzzer', 'Second'))
        self.assertEqual(outputs(data()['settings'], ()), ())
        for invalid in (Settings('a\nSET_PIN'), Settings('x' * 97), Settings(volume=101), Settings(click=9)):
            with self.assertRaises(ValueError): invalid.encode()

    def test_flash_saves_exact_record_and_checks_readback(self):
        lcd = driver(); value = Settings('Second', 10, 3, 4)
        lcd.write_flash = Mock(); lcd.read_flash = Mock(return_value=value.encode())
        lcd.save_buzzer_settings(value)
        lcd.write_flash.assert_called_once_with(ADDRESS, value.encode())
        self.assertEqual(lcd.load_buzzer_settings().encode(), value.encode())
        lcd.read_flash.return_value = bytes(RECORD_SIZE)
        with self.assertRaises(OSError): lcd.save_buzzer_settings(value)


class BuzzerMenuTests(unittest.TestCase):
    def test_lowercase_saved_selection_uses_actual_case_in_menu_and_feedback(self):
        view = self.view()
        view._buzzer_values = view._buzzer_saved = Settings('buzzer', 70, 4, 1)
        self.assertEqual(view._buzzer_outputs(), ('Buzzer', 'Second'))
        self.assertEqual(view._buzzer_rows()[0][1], 'Buzzer')
        view._buzzer_player = Mock()
        view._buzzer_feedback('press')
        view._buzzer_player.play.assert_called_once_with(Settings('Buzzer', 70, 4, 1), 'press')
        self.assertTrue(view._buzzer_enabled())

    def test_saved_preferences_load_once_and_survive_uart_reconnect(self):
        from test_uart_reconnect import UARTReconnectTests
        view = UARTReconnectTests().display()
        saved = Settings('Buzzer', 70, 4, 1)
        view.lcd.load_buzzer_settings.return_value = saved
        with patch.object(ui, 'T5UIC1Display', return_value=view.lcd):
            self.assertTrue(view._ensure_uart())
            self.assertEqual(view._buzzer_settings(), saved)
            view._uart_online = False
            self.assertTrue(view._ensure_uart())
        view.lcd.load_buzzer_settings.assert_called_once_with()

    def view(self):
        view = display(data())
        view._display_values = [100, 0, 10]
        view._display_saved = (100, 0, 10)
        view._display_selection = 4
        view._buzzer_values = view._buzzer_saved = Settings()
        view.checkkey = view.DisplayMenu
        view.get_encoder_state = Mock()
        return view

    def step(self, view, event, buzzer=False):
        view.get_encoder_state.return_value = event
        (view.HMI_Buzzer_Menu if buzzer else view.HMI_Display_Menu)()

    def test_selection_saves_returns_and_conditional_rows_stay_in_display(self):
        view = self.view()
        self.assertEqual([r[0] for r in view._buzzer_rows()], ['Buzzer'])
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey, view.BuzzerMenu)
        view._buzzer_selection = 2
        self.step(view, view.ENCODER_DIFF_ENTER, True)
        self.assertEqual(view.checkkey, view.DisplayMenu)
        self.assertEqual(view._display_selection, 4)
        self.assertEqual(view._buzzer_values.output, 'Buzzer')
        view.lcd.save_buzzer_settings.assert_called_once_with(Settings('Buzzer'))
        self.assertEqual([r[0] for r in view._buzzer_rows()], ['Buzzer', 'Volume', 'Click tone', 'Encoder tone'])
        view._buzzer_selection = 1
        self.step(view, view.ENCODER_DIFF_ENTER, True)
        self.assertEqual(view._buzzer_values.output, '')
        self.assertEqual(len(view._buzzer_rows()), 1)

    def test_async_buzzer_save_requires_verified_flash(self):
        from concurrent.futures import Future
        view = self.view()
        view.lcd.SUPPORTS_NONBLOCKING_FLASH = True
        view.lcd.BUZZER_SETTINGS_ADDRESS = ADDRESS
        future = Future()
        view.lcd.begin_flash_write_verified.return_value = future
        chosen = Settings('Buzzer', 70, 4, 1)
        view._save_buzzer(chosen)
        view.lcd.begin_flash_write_verified.assert_called_once_with(
            ADDRESS, chosen.encode())
        self.assertNotEqual(view._buzzer_saved, chosen)
        view._poll_panel_flash()
        self.assertNotEqual(view._buzzer_saved, chosen)
        future.set_result(chosen.encode())
        view._poll_panel_flash()
        self.assertEqual(view._buzzer_saved, chosen)

    def test_scroll_volume_tones_and_only_confirmed_settings_write_flash(self):
        view = self.view(); view._buzzer_values = view._buzzer_saved = Settings('Buzzer')
        view._display_selection = 5
        self.step(view, view.ENCODER_DIFF_ENTER)
        for _ in range(20): self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._buzzer_values.volume, 100)
        view.lcd.save_buzzer_settings.assert_not_called()
        self.step(view, view.ENCODER_DIFF_ENTER)
        view.lcd.save_buzzer_settings.assert_called_once_with(Settings('Buzzer', 100))
        view._display_selection = 6
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._buzzer_values.click, 3)
        self.step(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._buzzer_saved.click, 3)

    def test_no_outputs_and_removed_output_hide_sound_rows(self):
        view = self.view(); view._buzzer_values = Settings('Missing')
        self.assertFalse(view._buzzer_enabled())
        self.assertEqual(len(view._buzzer_rows()), 1)
        view._display_selection = 7
        self.step(view, view.ENCODER_DIFF_CW)
        self.assertEqual(view._display_selection, 4)
        self.assertFalse(view._display_edit)
        view.pd.state = replace(view.pd.state, settings={})
        self.assertEqual(view._buzzer_outputs(), ())
        view.Draw_Buzzer_Menu()

    def test_failed_save_preserves_output_and_can_retry(self):
        view = self.view(); view._buzzer_selection = 2
        view.lcd.save_buzzer_settings.side_effect = OSError('readback failed')
        self.step(view, view.ENCODER_DIFF_ENTER, True)
        self.assertEqual(view._buzzer_values.output, '')
        view.lcd.save_buzzer_settings.side_effect = None
        self.step(view, view.ENCODER_DIFF_ENTER, True)
        self.assertEqual(view._buzzer_values.output, 'Buzzer')

    def test_input_plays_once_per_physical_event_and_never_for_stale_event(self):
        from ui_events import InputEvent
        view = self.view(); view._buzzer_values = Settings('Buzzer')
        view._buzzer_player = Mock()
        view._closed = False; view._uart_epoch = 1; view._uart_online = True
        view._sync_input_state = Mock(return_value=True)
        view._dispatch_input = Mock(); view._display_activity = Mock(return_value=False)
        view._encoder_acceleration_cap = Mock(return_value=1)
        view._process_input(InputEvent('rotate', 7, 1, 1))
        view._buzzer_player.play.assert_called_once_with(Settings('Buzzer'), 'rotate')
        view._buzzer_player.reset_mock()
        view._process_input(InputEvent('press', 1, 999, 1))
        view._buzzer_player.play.assert_not_called()


class SoundWorkerTests(unittest.TestCase):
    def test_tick_stops_while_subscription_receiver_is_blocked(self):
        from moonraker_subscription import MoonrakerSubscription
        source = data()
        client = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(client.close)
        entered, release, off = Event(), Event(), Event()
        commands = []
        connection = Mock()
        def receive(control_frame=True):
            entered.set()
            release.wait(2)
            return 10, b''
        def send(raw):
            command = json.loads(raw)['params']['script']
            commands.append(command)
            if command.endswith('VALUE=0'):
                off.set()
        connection.recv_data.side_effect = receive
        connection.send.side_effect = send
        client._socket = connection
        client._state = 'ready'
        client._settings = source['settings']
        client._objects = source['objects']
        receiver = Thread(target=client._receive)
        receiver.start()
        player = Player(client)
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(player.play(Settings('Buzzer'), 'rotate'))
            self.assertTrue(off.wait(.5), 'Off must not wait for the one-second receive timeout')
            self.assertTrue(receiver.is_alive())
            self.assertEqual(commands, ['SET_PIN PIN=Buzzer VALUE=0.25 CYCLE_TIME=0.00055556',
                                        'SET_PIN PIN=Buzzer VALUE=0'])
            self.assertTrue(client._outbound.empty())
        finally:
            release.set()
            receiver.join(2)
            player.close()

    def subscription(self):
        source = data(); subscription = Mock()
        subscription.snapshot.side_effect = lambda: source
        return subscription, source

    def test_busy_events_drop_without_waiting_and_stop_uses_zero(self):
        subscription, source = self.subscription()
        sent = Event(); off = Event(); commands = []
        def notify(method, params, guard):
            future = Future()
            if not guard(): future.set_exception(ValueError('stale'))
            else:
                commands.append(params['script'])
                (off if params['script'].endswith('VALUE=0') else sent).set()
                future.set_result(None)
            return future
        subscription.notify_immediate.side_effect = notify
        with patch('buzzer_control.PATTERNS', ((), (), ((1000, 10),))):
            player = Player(subscription); self.addCleanup(player.close)
            self.assertTrue(player.play(Settings('buzzer', 100), 'press'))
            self.assertTrue(sent.wait(1))
            for _ in range(100): self.assertFalse(player.play(Settings('Buzzer'), 'rotate'))
            self.assertFalse(off.is_set())
            player.cancel()
            self.assertTrue(off.wait(1))
        self.assertEqual(commands, ['SET_PIN PIN=Buzzer VALUE=0.5 CYCLE_TIME=0.00100000', 'SET_PIN PIN=Buzzer VALUE=0'])

    def test_muted_unknown_and_offline_inputs_do_not_dispatch(self):
        subscription, source = self.subscription()
        player = Player(subscription); self.addCleanup(player.close)
        for value in (Settings(), Settings('Buzzer', 0), Settings('Missing'), Settings('Buzzer', click=0)):
            self.assertFalse(player.play(value, 'press'))
        source['state'] = 'disconnected'
        self.assertFalse(player.play(Settings('Buzzer'), 'press'))
        subscription.notify_immediate.assert_not_called()

    def test_epoch_change_prevents_stop_from_touching_new_session(self):
        subscription, source = self.subscription()
        sent = Event(); commands = []
        def notify(method, params, guard):
            future = Future()
            if guard():
                commands.append(params['script']); sent.set(); future.set_result(None)
            else: future.set_exception(ValueError('stale'))
            return future
        subscription.notify_immediate.side_effect = notify
        with patch('buzzer_control.PATTERNS', ((), (), ((1000, 10),))):
            player = Player(subscription); self.addCleanup(player.close)
            player.play(Settings('Buzzer'), 'press'); self.assertTrue(sent.wait(1))
            source['epoch'] = 2
            player.close()
        self.assertEqual(len(commands), 1)
