from read_fixture import ImmediateReadWorker
from dataclasses import FrozenInstanceError
import importlib.util
from pathlib import Path
import sys
import types
from queue import Queue
from threading import Event, Lock, Thread, get_ident
import unittest
from unittest.mock import Mock, patch

from printer_state import PrinterState
from ui_events import InputEvent, UIEventLoop
from test_regressions import ui, backend


class EventLoopTests(unittest.TestCase):
    def test_shorter_interval_from_input_does_not_wait_for_previous_slow_tick(self):
        ticks=Event()
        loop=UIEventLoop(Mock(),lambda event:loop.set_interval(.02),ticks.set,Mock(),interval=2.0)
        self.addCleanup(loop.close)
        loop.start();loop.post(InputEvent('press',1,0))
        self.assertTrue(ticks.wait(.5))

    def test_all_producers_and_ticks_have_one_owner(self):
        owners = []
        events = []
        ticks = Event()
        complete = Event()
        lock = Lock()

        def event(value):
            with lock:
                owners.append(get_ident())
                events.append(value)
                if len(events) == 80:
                    complete.set()

        def tick():
            owners.append(get_ident())
            ticks.set()

        loop = UIEventLoop(lambda: owners.append(get_ident()), event, tick,
                           lambda: owners.append(get_ident()), interval=0.01)
        self.addCleanup(loop.close)
        loop.start()
        producers = [Thread(target=lambda offset=n: [loop.post((offset, i)) for i in range(20)])
                     for n in range(4)]
        for producer in producers:
            producer.start()
        for producer in producers:
            producer.join()
        self.assertTrue(complete.wait(2))
        self.assertTrue(ticks.wait(2))
        loop.close()
        self.assertEqual(len(set(owners)), 1)
        self.assertNotEqual(owners[0], get_ident())
        for producer in range(4):
            self.assertEqual([index for owner, index in events if owner == producer], list(range(20)))

    def test_adjacent_rotation_events_are_coalesced_without_losing_raw_or_accelerated_steps(self):
        seen = []
        loop = UIEventLoop(Mock(), seen.append, Mock(), Mock())
        loop.post(InputEvent('rotate', 2, 1, 0, 20))
        loop.post(InputEvent('rotate', 3, 1, 0, 300))
        queued = loop._queue.get_nowait()
        self.assertEqual(queued, InputEvent('rotate', 5, 1, 0, 320))
        loop._queue.task_done()

    def test_coalesced_rotation_keeps_latest_measured_rate(self):
        seen = []
        loop = UIEventLoop(Mock(), seen.append, Mock(), Mock())
        loop.post(InputEvent('rotate', 2, 1, 0, 20, 12.0))
        loop.post(InputEvent('rotate', 3, 1, 0, 60, 30.0))
        queued = loop._queue.get_nowait()
        self.assertEqual(queued.value, 5)
        self.assertEqual(queued.accelerated_value, 80)
        self.assertEqual(queued.rate, 30.0)
        loop._queue.task_done()

    def test_full_queue_is_nonblocking_and_closed_queue_rejects_input(self):
        loop = UIEventLoop(Mock(), Mock(), Mock(), Mock(), capacity=1)
        self.assertTrue(loop.post(InputEvent('press', 1, 0)))
        self.assertFalse(loop.post(InputEvent('press', 1, 0)))
        loop.close()
        self.assertFalse(loop.post(InputEvent('press', 1, 0)))

    def test_cleanup_waits_for_active_handler_and_runs_once(self):
        entered, release, closing, cleaned = Event(), Event(), Event(), Event()
        cleanup = Mock(side_effect=cleaned.set)
        def handler(event):
            entered.set()
            release.wait(2)
        loop = UIEventLoop(Mock(), handler, Mock(), cleanup)
        self.addCleanup(loop.close)
        loop.start()
        loop.post(InputEvent('press', 1, 0))
        self.assertTrue(entered.wait(2))
        def close():
            closing.set()
            loop.close()
        closer = Thread(target=close)
        closer.start()
        self.assertTrue(closing.wait(2))
        self.assertFalse(cleaned.is_set())
        release.set()
        closer.join(2)
        self.assertFalse(closer.is_alive())
        loop.close()
        cleanup.assert_called_once()

    def test_startup_failure_closes_partial_resources(self):
        cleanup = Mock()
        loop = UIEventLoop(Mock(side_effect=ValueError('startup')), Mock(), Mock(), cleanup)
        with self.assertRaisesRegex(ValueError, 'startup'):
            loop.start()
        cleanup.assert_called_once()
        self.assertFalse(loop._thread.is_alive())

    def test_handler_exception_does_not_kill_owner(self):
        finished = Event()
        def handler(value):
            if value == 1:
                raise ValueError('known failure')
            finished.set()
        loop = UIEventLoop(Mock(), handler, Mock(), Mock())
        self.addCleanup(loop.close)
        loop.start()
        with self.assertLogs(level='ERROR'):
            loop.post(1)
            loop.post(2)
            self.assertTrue(finished.wait(2))


class ImmutableStateTests(unittest.TestCase):
    def test_nested_status_cannot_be_mutated(self):
        snapshot = {'state': 'ready', 'status': {'toolhead': {'position': [1, 2, 3, 4]}},
                    'objects': ['toolhead'], 'epoch': 2}
        state = PrinterState.from_snapshot(snapshot)
        snapshot['status']['toolhead']['position'][0] = 100
        self.assertEqual(state.status['toolhead']['position'][0], 1)
        with self.assertRaises(TypeError):
            state.status['toolhead']['position'][0] = 100
        with self.assertRaises(TypeError):
            state.status['toolhead']['position'] = ()
        with self.assertRaises(FrozenInstanceError):
            state.epoch = 3


class InputRoutingTests(unittest.TestCase):
    def display(self):
        display = ui.DWIN_LCD.__new__(ui.DWIN_LCD)
        display._closed = False
        display._input_lock = Lock()
        display._producer_value = 0
        display._last_press = float('-inf')
        display.power_on_hold_ms = 2000
        display._encoder_event = display.ENCODER_DIFF_NO
        display._loop = Mock()
        display.pd = Mock(connection_error=None)
        display.pd.state = PrinterState.from_snapshot({'state': 'ready', 'epoch': 1})
        display._configure_menus = Mock(return_value=False)
        display.pd.subscription.snapshot.return_value = {'state': 'ready', 'epoch': 1}
        display._dispatch_input = Mock()
        return display

    def test_gpio_callbacks_only_enqueue(self):
        display = self.display()
        display.encoder_has_data(-3)
        display._button_pressed()
        self.assertEqual(display._loop.post.call_args_list[0].args[0], InputEvent('rotate', -3, 1, 0, -3))
        self.assertEqual(display._loop.post.call_args_list[1].args[0], InputEvent('press', 1, 1))
        display._dispatch_input.assert_not_called()

    def test_configured_hold_routes_power_even_when_printer_and_uart_are_offline(self):
        display = self.display()
        display._uart_online = False
        display.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 2}
        display._button_held()
        event = display._loop.post.call_args.args[0]
        self.assertEqual(event.kind, 'power_on')
        display._process_input(event)
        display.pd.power_on_if_off.assert_called_once_with()
        display._dispatch_input.assert_not_called()

    def test_zero_hold_time_requests_power_on_immediately_on_press(self):
        display = self.display()
        display.power_on_hold_ms = 0
        display._uart_online = False
        display.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 2}
        display._button_pressed()
        events = [call.args[0] for call in display._loop.post.call_args_list]
        self.assertEqual(events[0].kind, 'power_on')
        display._process_input(events[0])
        display.pd.power_on_if_off.assert_called_once_with()

    def test_zero_hold_time_ignores_gpio_held_callback(self):
        display = self.display()
        display.power_on_hold_ms = 0
        display._button_held()
        display._loop.post.assert_not_called()

    def test_each_rotation_step_is_preserved(self):
        display = self.display()
        seen = []
        display._dispatch_input.side_effect = lambda: seen.append(display.get_encoder_state())
        display._process_input(InputEvent('rotate', -3, 1))
        display._process_input(InputEvent('press', 1, 1))
        self.assertEqual(seen, [display.ENCODER_DIFF_CW] * 3 + [display.ENCODER_DIFF_ENTER])
        self.assertEqual(display.get_encoder_state(), display.ENCODER_DIFF_NO)

    def test_numeric_editor_consumes_accelerated_batch_once(self):
        display = self.display()
        display.checkkey = display.Move_X
        seen = []
        display._dispatch_input.side_effect = lambda: seen.append(
            (display.get_encoder_state(), display._encoder_move_value))
        display._process_input(InputEvent('rotate', -4, 1, 0, -100))
        self.assertEqual(seen, [(display.ENCODER_DIFF_CW, 100)])

    def test_numeric_editor_caps_acceleration_by_field(self):
        display = self.display()
        for screen, expected in (
            (display.Move_X, 250),
            (display.MotionValue, 100),
            (display.ETemp, 10),
            (display.FanSpeed, 5),
            (display.Homeoffset, 10),
            (display.MainMenu, 1),
        ):
            with self.subTest(screen=screen):
                display.checkkey = screen
                seen = []
                display._dispatch_input.side_effect = lambda: seen.append(display._encoder_move_value)
                display._process_input(InputEvent('rotate', -1, 1, 0, -250))
                self.assertEqual(seen[-1], expected)

    def test_old_epoch_and_offline_events_are_discarded(self):
        display = self.display()
        display._process_input(InputEvent('press', 1, 0))
        display.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 1}
        display._process_input(InputEvent('press', 1, 1))
        display._dispatch_input.assert_not_called()

    def test_press_debounce_uses_capture_time(self):
        display = self.display()
        with patch.object(ui.time, 'monotonic', side_effect=[10, 10.1, 10.4]):
            display._button_pressed()
            display._button_pressed()
            display._button_pressed()
        self.assertEqual(display._loop.post.call_count, 2)

    def test_rotation_rate_uses_continuous_acceleration_curve(self):
        display = self.display()
        with patch.object(ui.time, 'monotonic',
                          side_effect=[1.0, 1.2, 1.3, 1.35, 1.375, 1.39674]):
            display.encoder_has_data(1)   # first step: 1x
            display.encoder_has_data(2)   # 5 steps/s: 1x
            display.encoder_has_data(3)   # 10 steps/s: 1x
            display.encoder_has_data(4)   # 20 steps/s: proportional
            display.encoder_has_data(5)   # 40 steps/s: proportional
            display.encoder_has_data(6)   # about 46 steps/s: 250x
        events = [call.args[0] for call in display._loop.post.call_args_list]
        multipliers = [abs(event.accelerated_value) for event in events]
        self.assertEqual(multipliers[:3], [1, 1, 1])
        self.assertGreater(multipliers[3], 1)
        self.assertLess(multipliers[3], multipliers[4])
        self.assertLess(multipliers[4], 250)
        self.assertEqual(multipliers[5], 250)

    def test_rotation_never_samples_held_button(self):
        display = self.display()
        display.button = Mock(is_pressed=True)
        seen = []
        display._dispatch_input.side_effect = lambda: seen.append(display.get_encoder_state())
        display._process_input(InputEvent('rotate', 1, 1))
        self.assertEqual(seen, [display.ENCODER_DIFF_CCW])

    def test_disconnect_mid_rotation_batch_discards_remaining_steps(self):
        display = self.display()
        def disconnect():
            display.pd.subscription.snapshot.return_value = {'state': 'disconnected', 'epoch': 2}
        display._dispatch_input.side_effect = disconnect
        display._process_input(InputEvent('rotate', 3, 1))
        display._dispatch_input.assert_called_once()


class EncoderTests(unittest.TestCase):
    def test_cumulative_steps_preserve_count_and_direction_without_reset(self):
        native = Mock(steps=0)
        gpio = types.ModuleType('gpiozero')
        gpio.Device = types.SimpleNamespace(pin_factory=object())
        gpio.RotaryEncoder = Mock(return_value=native)
        pins = types.ModuleType('gpiozero.pins.lgpio')
        pins.LGPIOFactory = Mock()
        spec = importlib.util.spec_from_file_location('test_encoder_driver',
            Path(__file__).resolve().parents[1] / 'encoder.py')
        driver = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'gpiozero': gpio, 'gpiozero.pins.lgpio': pins}):
            spec.loader.exec_module(driver)
        values = []
        encoder = driver.Encoder(21, 19, values.append)
        native.steps = 3
        encoder._rotated()
        encoder._rotated()  # Duplicate notification must not create an input.
        native.steps = 1
        encoder._rotated()
        self.assertEqual(values, [3, 1])
        self.assertEqual(encoder.direction, 'L')
        self.assertEqual(encoder.getValue(), 1)
        self.assertEqual(native.steps, 1)
        encoder.close()
        native.close.assert_called_once()


class DisplayIntegrationTests(unittest.TestCase):
    def test_real_menu_packets_and_cleanup_use_ui_owner(self):
        writes = []
        closed = []
        prepared = Event()
        base = ui.T5UIC1Display

        class FakeLCD(base):
            def __init__(self, port, **kwargs):
                self.serial = Mock()
                self.MYSERIAL1 = self.serial
                self.serial.write.side_effect = lambda data: (writes.append((get_ident(), bytes(data))), len(data))[1]
                self.serial.close.side_effect = lambda: closed.append(get_ident())
                self._closed = False
                self._needs_update = True
                self._defer_updates = False
                self._atlas_synced = True
                self._atlas_sync_blocked = False
                self._virtual_area_pictures = {0: 14}

        encoder = Mock()
        encoder.getValue.return_value = 0
        button = Mock()
        release_callback = button.when_released
        snapshot = {
            'state': 'ready', 'error': None, 'epoch': 1, 'revision': 1, 'file_revision': 0,
            'status': {
                'toolhead': {'position': [0, 0, 0, 0], 'axis_minimum': [0, 0, 0, 0], 'axis_maximum': [220, 220, 250, 0],
                             'homed_axes': 'xyz'},
                'gcode_move': {'homing_origin': [0, 0, 0, 0],
                               'absolute_coordinates': True, 'absolute_extrude': True},
                'print_stats': {'state': 'standby', 'filename': ''},
                'virtual_sdcard': {'is_active': False, 'progress': 0},
            },
        }
        original = ui.DWIN_LCD.Draw_Prepare_Menu
        def prepare(display):
            original(display)
            prepared.set()

        command_client = Mock()
        telemetry_client = Mock()
        command_client.command_results = Queue()
        with patch.object(backend, 'MoonrakerClient',
                          side_effect=[command_client, telemetry_client]), \
                patch.object(backend, 'MoonrakerSubscription') as subscription, patch.object(backend, 'ReadWorker', ImmediateReadWorker), \
                patch.object(ui, 'Encoder', return_value=encoder), \
                patch.object(ui, 'Button', return_value=button), \
                patch.object(ui, 'T5UIC1Display', FakeLCD), \
                patch.object(ui.DWIN_LCD, 'HMI_ShowBoot'), \
                patch.object(ui.DWIN_LCD, 'Draw_Prepare_Menu', prepare):
            subscription.return_value.snapshot.return_value = snapshot
            display = ui.DWIN_LCD('fake-port', (21, 19), 13, '')
            try:
                self.assertIs(button.when_released, release_callback)
                encoder.callback(-1)  # Main menu -> Prepare, preserving old direction.
                button.when_pressed()
                self.assertTrue(prepared.wait(2))
                self.assertEqual(display.checkkey, display.Prepare)
            finally:
                display.lcdExit()
            display.lcdExit()
            owners = {owner for owner, _ in writes}
            self.assertTrue(writes)
            self.assertEqual(len(owners), 1)
            self.assertNotIn(get_ident(), owners)
            self.assertEqual(closed, list(owners))
            encoder.close.assert_called_once()
            button.close.assert_called_once()
            subscription.return_value.close.assert_called_once()
            command_client.close.assert_called_once()
            telemetry_client.close.assert_called_once()

    def test_selection_state_is_not_shared(self):
        first, second = ui.select_t(), ui.select_t()
        first.set(3)
        self.assertEqual(second.now, 0)
