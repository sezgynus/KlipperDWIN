from read_fixture import ImmediateReadWorker
"""Behavioral regression contracts; no GPIO, serial port or server required."""
import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_application():
    # Only import-time dependencies are replaced. Application methods stay real.
    importlib.import_module('ui_events')
    importlib.import_module('printer_state')
    dependencies = {}
    for name in ('requests', 'requests.exceptions', 'multitimer', 'encoder',
                 'gpiozero', 'gpiozero.pins', 'gpiozero.pins.lgpio', 'serial'):
        dependencies[name] = types.ModuleType(name)
    dependencies['requests.exceptions'].ConnectionError = ConnectionError
    dependencies['encoder'].Encoder = Mock()
    dependencies['gpiozero'].Button = Mock()
    dependencies['gpiozero'].Device = types.SimpleNamespace(pin_factory=None)
    dependencies['gpiozero.pins.lgpio'].LGPIOFactory = Mock()
    with patch.dict(sys.modules, dependencies):
        backend = importlib.import_module('printerInterface')
        ui = importlib.import_module('dwinlcd')
    return backend, ui


backend, ui = load_application()


class RegressionContracts(unittest.TestCase):
    def printer(self):
        printer = backend.PrinterData.__new__(backend.PrinterData)
        printer.sendGCode = Mock()
        printer.postREST = Mock()
        printer.current_position = backend.xyze_t()
        printer.HMI_ValueStruct = backend.HMI_value_t()
        printer.HMI_flag = backend.HMI_Flag_t()
        printer.job_Info = {
            'virtual_sdcard': {'is_active': False, 'progress': 0.42},
            'print_stats': {'state': 'paused', 'print_duration': 120.0},
        }
        return printer

    def display(self, mode):
        display = ui.DWIN_LCD.__new__(ui.DWIN_LCD)
        # Use discovered devices and real menu indices, with isolated I/O.
        from test_capabilities import snapshot, printer
        display.pd = printer(snapshot())
        display.index_tune = display.MROWS
        display._configure_menus()
        display.pd.HMI_ValueStruct.show_mode = mode
        display.pd.HMI_ValueStruct.E_Temp = 205
        display.pd.HMI_ValueStruct.Bed_Temp = 65
        display.lcd = Mock()
        display.get_encoder_state = Mock(return_value=display.ENCODER_DIFF_ENTER)
        return display

    def test_pause_state_is_reported(self):
        self.assertTrue(self.printer().printingIsPaused())

    def test_resume_uses_absolute_endpoint_path(self):
        printer = self.printer()
        from threading import Lock
        printer._jog_lock = Lock()
        printer._jog_restore = None
        printer.resume_job()
        printer.postREST.assert_called_once_with('/printer/print/resume', json=None)

    def test_home_returns_command_future(self):
        printer = self.printer()
        command_future = object()
        printer.sendGCode.return_value = command_future

        self.assertIs(printer.home(homeZ=True), command_future)
        printer.sendGCode.assert_called_once_with('G28 X Y Z')

    def test_paused_progress_is_retained(self):
        self.assertAlmostEqual(self.printer().getPercent(), 42.0)

    def test_paused_duration_is_retained(self):
        self.assertEqual(self.printer().duration(), 120.0)

    def test_temperature_menu_applies_hotend_target(self):
        display = self.display(-1)
        display.HMI_ETemp()
        display.pd.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=205')

    def test_temperature_menu_applies_bed_target(self):
        display = self.display(-1)
        display.HMI_BedTemp()
        display.pd.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=65')

    def test_tune_applies_hotend_target(self):
        display = self.display(0)
        display.HMI_ETemp()
        display.pd.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=205')

    def test_tune_applies_bed_target(self):
        display = self.display(0)
        display.HMI_BedTemp()
        display.pd.sendGCode.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=65')

    def test_job_statistics_follow_print_state(self):
        printer = self.printer()
        for state in ('printing', 'paused', 'complete', 'cancelled', 'error'):
            with self.subTest(state=state):
                printer.job_Info['print_stats']['state'] = state
                self.assertEqual(printer.getPercent(), 42)
                self.assertEqual(printer.duration(), 120)
        printer.job_Info['print_stats']['state'] = 'standby'
        self.assertEqual(printer.getPercent(), 0)
        self.assertEqual(printer.duration(), 0)

    def test_live_hotend_edit_addresses_active_extruder(self):
        from test_capabilities import snapshot, printer
        display = self.display(-1)
        display.pd = printer(snapshot(multiple=True))
        display._configure_menus()
        display.pd.HMI_ValueStruct.show_mode = -1
        display.pd.HMI_ValueStruct.E_Temp = 205
        display.HMI_ETemp()
        display.pd.sendGCode.assert_called_once_with(
            'SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=205')

    def test_preset_edits_do_not_heat_printer(self):
        for profile in (0, 1):
            for method, field, target in (('HMI_ETemp', 'hotend_temp', 205),
                                           ('HMI_BedTemp', 'bed_temp', 65)):
                with self.subTest(profile=profile, method=method):
                    display = self.display(-2)
                    display._active_preset = profile
                    getattr(display, method)()
                    self.assertEqual(getattr(display.pd.material_preset[profile], field), target)
                    display.pd.sendGCode.assert_not_called()

    def test_completion_is_reported_by_print_stats(self):
        from test_capabilities import snapshot, printer
        for state, progress, finished in (('printing', 1, False),
                                           ('complete', .999, True),
                                           ('cancelled', 1, False)):
            with self.subTest(state=state):
                data = snapshot()
                data['status']['print_stats']['state'] = state
                data['status']['virtual_sdcard']['progress'] = progress
                self.assertEqual(printer(data).HMI_flag.print_finish, finished)


class BackendConnectionTests(unittest.TestCase):
    def test_initialization_does_not_open_klipper_socket(self):
        command_client = Mock()
        telemetry_client = Mock()
        with patch.object(backend, 'MoonrakerClient',
                          side_effect=[command_client, telemetry_client]) as transport, \
                patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            printer = backend.PrinterData(URL='http://localhost:7125', timeout=2)
            self.assertEqual(
                transport.call_args_list,
                [unittest.mock.call('http://localhost:7125', '', 2),
                 unittest.mock.call('http://localhost:7125', '', 2, queue_size=16)])
            self.assertIsNone(printer.status)
            printer.close()
            command_client.close.assert_called_once()
            telemetry_client.close.assert_called_once()

    def test_missing_snapshot_preserves_previous_state(self):
        with patch.object(backend, 'MoonrakerClient'), patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            printer = backend.PrinterData()
        printer.check_command_results = Mock()
        printer.subscription.snapshot.return_value = {'state': 'ready', 'status': {}}
        printer.status = 'paused'
        self.assertFalse(printer.update_variable())
        self.assertEqual(printer.status, 'paused')
        self.assertIsNotNone(printer.connection_error)

    def test_offline_command_is_rejected_without_network(self):
        with patch.object(backend, 'MoonrakerClient') as transport, patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker) as subscription:
            printer = backend.PrinterData()
            printer.connection_error = 'Disconnected'
            future = printer.postREST('/printer/print/start', {'filename': 'test.gcode'})
            with self.assertRaises(backend.MoonrakerError):
                future.result()
            transport.return_value.post.assert_not_called()

    def test_ready_snapshot_updates_without_http_polling(self):
        with patch.object(backend, 'MoonrakerClient'), patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            printer = backend.PrinterData()
        printer.check_command_results = Mock()
        printer.getREST = Mock(side_effect=AssertionError('status must not poll HTTP'))
        printer.subscription.snapshot.return_value = {
            'state': 'ready', 'file_revision': 1,
            'objects': ['extruder', 'toolhead', 'gcode_move', 'print_stats', 'virtual_sdcard'],
            'settings': {'extruder': {'min_temp': 0, 'max_temp': 300,
                                     'min_extrude_temp': 170, 'max_extrude_only_distance': 50}},
            'status': {
                'toolhead': {'position': [1, 2, 3, 4], 'axis_minimum': [0, 0, 0, 0], 'axis_maximum': [220, 220, 250, 0],
                             'homed_axes': 'xy'},
                'gcode_move': {'homing_origin': [0, 0, 0.1, 0],
                               'absolute_coordinates': True, 'absolute_extrude': False},
                'print_stats': {'state': 'paused', 'filename': 'test.gcode'},
                'virtual_sdcard': {'is_active': False, 'progress': 0.4},
                'extruder': {'temperature': 200, 'target': 205},
            },
        }
        self.assertTrue(printer.update_variable())
        self.assertEqual(printer.status, 'paused')
        self.assertFalse(printer.absolute_extrude)
        self.assertFalse(printer.current_position.home_z)
        self.assertEqual(printer.thermalManager['temp_hotend'][0]['target'], 205)
        printer.getREST.assert_not_called()

    def test_unhomed_axes_clear_previous_flags(self):
        with patch.object(backend, 'MoonrakerClient'), patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            printer = backend.PrinterData()
        printer.check_command_results = Mock()
        snapshot = {
            'state': 'ready', 'file_revision': 0,
            'status': {
                'toolhead': {'position': [0, 0, 0, 0], 'axis_minimum': [0, 0, 0, 0], 'axis_maximum': [220, 220, 250, 0],
                             'homed_axes': 'xyz'},
                'gcode_move': {'homing_origin': [0, 0, 0, 0],
                               'absolute_coordinates': True, 'absolute_extrude': True},
                'print_stats': {'state': 'standby'},
                'virtual_sdcard': {'is_active': False, 'progress': 0},
            },
        }
        printer.subscription.snapshot.return_value = snapshot
        self.assertTrue(printer.update_variable())
        self.assertTrue(printer.current_position.home_x)
        snapshot['status']['toolhead']['homed_axes'] = ''
        self.assertTrue(printer.update_variable())
        self.assertFalse(printer.current_position.home_x)
        self.assertFalse(printer.current_position.home_y)
        self.assertFalse(printer.current_position.home_z)

    def test_backend_guard_rejects_new_epoch(self):
        with patch.object(backend, 'MoonrakerClient') as transport, patch.object(backend, 'MoonrakerSubscription'), patch.object(backend, 'ReadWorker', ImmediateReadWorker):
            printer = backend.PrinterData()
        printer.subscription.snapshot.return_value = {'state': 'ready', 'epoch': 1}
        printer.state = backend.PrinterState.from_snapshot({'state': 'ready', 'epoch': 1})
        printer.postREST('/printer/print/start', {'filename': 'test.gcode'})
        guard = transport.return_value.post.call_args.kwargs['guard']
        self.assertTrue(guard())
        printer.subscription.snapshot.return_value = {'state': 'ready', 'epoch': 2}
        self.assertFalse(guard())


if __name__ == '__main__':
    unittest.main()
