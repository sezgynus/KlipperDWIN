"""Offline Maintenance capability rules; no Moonraker, GPIO, or printer needed."""
import gc
import sys
import unittest
import weakref
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_cache import MaintenanceCache
from maintenance_discovery import (
    discover, MaintenanceSnapshot, FEATURE_COUNT, NONE, AUTOMATIC,
    USER, EXTERNAL, CALIBRATION, INFORMATION,
)


class Snapshot:
    def __init__(self, objects=(), settings=None, status=None, ready=True, epoch=7):
        self.objects = objects
        self.settings = settings if settings is not None else {}
        self.status = status if status is not None else {}
        self.ready = ready
        self.epoch = epoch


class DiscoveryTests(unittest.TestCase):
    def test_all_feature_ids_and_fail_closed(self):
        self.assertEqual(FEATURE_COUNT, 121)
        empty = discover(Snapshot())
        self.assertEqual(empty.devices, ())
        for prefix, total in (('F', 13), ('H', 18), ('M', 17), ('P', 22),
                              ('R', 8), ('E', 15), ('S', 20), ('O', 8)):
            for i in range(1, total + 1):
                self.assertEqual(empty.method(f'{prefix}{i:02}'), NONE)
        for name in ('Z01', 'F14', 'F00', 'X', '', 'H99'):
            with self.assertRaises(ValueError):
                empty.method(name)

    def test_device_capabilities_are_visible_in_aggregate_list(self):
        s = Snapshot(objects=('fan', 'extruder', 'heater_bed'),
                     settings={'extruder': {'min_temp': 0, 'max_temp': 290},
                               'heater_bed': {'min_temp': 0, 'max_temp': 125}})
        snap = discover(s)
        self.assertIn('F01', snap.available_features())
        self.assertIn('H01', snap.available_features())
        self.assertIn('H03', snap.available_features())
        self.assertEqual(snap.method('F01'), USER)
        self.assertEqual(snap.method('F01', 'fan'), USER)
        self.assertEqual(snap.method('F01', 'extruder'), NONE)
        self.assertEqual(len(snap.instances('H05')), 2)
        self.assertNotIn('R02', snap.available_features())

    def test_open_loop_and_tach_fan(self):
        s = Snapshot(objects=('fan', 'fan_generic exhaust', 'heater_fan heatsink', 'extruder'),
                     settings={'fan': {'max_power': 1., 'off_below': .12},
                               'fan_generic exhaust': {'max_power': 1., 'tachometer_pin': '^PA1'},
                               'heater_fan heatsink': {'heater': 'extruder'},
                               'extruder': {'min_temp': 0, 'max_temp': 280}})
        caps = discover(s)
        self.assertEqual(caps.method('F01', 'fan'), USER)
        self.assertEqual(caps.method('F02', 'fan'), USER)
        self.assertEqual(caps.method('F03', 'fan'), NONE)
        self.assertEqual(caps.method('F04', 'fan_generic exhaust'), AUTOMATIC)
        self.assertEqual(caps.method('F11', 'fan_generic exhaust'), AUTOMATIC | INFORMATION)
        self.assertEqual(caps.method('F06', 'heater_fan heatsink'), USER)
        self.assertEqual(caps.method('F07', 'heater_fan heatsink'), NONE)
        self.assertEqual(caps.method('R02'), NONE)
        self.assertEqual(len(caps.instances('F11')), 1)

    def test_heaters_multiple_and_no_retained_source(self):
        cfg = {'min_temp': 0., 'max_temp': 280.}
        s = Snapshot(objects=('extruder', 'extruder1', 'heater_bed', 'heater_generic chamber'),
                     settings={'extruder': cfg, 'extruder1': cfg,
                               'heater_bed': {'min_temp': 0., 'max_temp': 125.},
                               'heater_generic chamber': {'min_temp': 0., 'max_temp': 65.}})
        snap = discover(s)
        self.assertEqual(snap.method('H02', 'extruder1'), CALIBRATION)
        self.assertEqual(snap.method('H03', 'heater_bed'), CALIBRATION)
        self.assertEqual(snap.method('H04', 'heater_generic chamber'), CALIBRATION)
        self.assertEqual(len(snap.instances('H05')), 4)
        self.assertEqual(snap.method('H10', 'extruder'), NONE)  # No baseline.
        ref = weakref.ref(s)
        del s
        gc.collect()
        self.assertIsNone(ref(), 'Discovery snapshot retained its input state')
        self.assertEqual(snap.method('H05', 'heater_bed'), AUTOMATIC)

    def test_manual_mesh_probe_and_resonance(self):
        base = discover(Snapshot(objects=('bed_mesh', 'manual_probe', 'query_endstops',
                                          'stepper_x', 'toolhead', 'gcode_move'),
                                 settings={'stepper_x': {'endstop_pin': '^PA5'}}))
        self.assertEqual(base.method('P08'), CALIBRATION | USER)
        self.assertEqual(base.method('P07'), NONE)
        self.assertEqual(base.method('P03'), NONE)
        self.assertEqual(base.method('M01'), AUTOMATIC | USER)
        self.assertEqual(base.method('R02'), NONE)
        sensor = discover(Snapshot(objects=('adxl345', 'resonance_tester', 'probe', 'bed_mesh'),
                                   settings={'resonance_tester': {'accel_chip_x': 'adxl345'}}))
        self.assertEqual(sensor.method('R02'), AUTOMATIC)
        self.assertEqual(sensor.method('R04'), CALIBRATION)
        self.assertEqual(sensor.method('P07'), CALIBRATION)
        self.assertEqual(sensor.method('R07'), NONE)

    def test_dynamic_filament_and_unknown_actuators(self):
        snap = discover(Snapshot(objects=('filament_switch_sensor runout',
                                          'filament_motion_sensor encoder',
                                          'servo cutter', 'output_pin laser',
                                          'gcode_macro SELF_TEST', 'neopixel display')))
        self.assertEqual(snap.method('E03', 'filament_switch_sensor runout'), AUTOMATIC | USER)
        self.assertEqual(snap.method('E04', 'filament_motion_sensor encoder'), AUTOMATIC)
        self.assertEqual(snap.method('O02', 'servo cutter'), NONE)
        self.assertEqual(snap.method('O03', 'output_pin laser'), NONE)
        self.assertEqual(snap.method('O08'), NONE)
        self.assertEqual(snap.method('O04', 'neopixel display'), USER)

    def test_services_are_positive_api_evidence_not_assumptions(self):
        source = Snapshot(objects=('mcu', 'webhooks'))
        snap = discover(source)
        self.assertEqual(snap.method('S06'), INFORMATION)
        self.assertEqual(snap.method('S10'), NONE)
        self.assertEqual(snap.method('S03'), NONE)
        snap = discover(source, services=('history', 'machine.throttled_state'))
        self.assertEqual(snap.method('S10'), INFORMATION)
        self.assertEqual(snap.method('S03'), INFORMATION)
        self.assertEqual(snap.method('S18'), NONE)

    def test_load_cell_eddy_and_controller_fan_special_cases(self):
        load = discover(Snapshot(objects=('probe', 'load_cell_probe')))
        self.assertEqual(load.method('P02'), AUTOMATIC | USER)
        self.assertEqual(load.method('P01'), NONE)
        eddy = discover(Snapshot(objects=('probe', 'probe_eddy_current scanner',
                                          'temperature_probe scanner')))
        self.assertEqual(eddy.method('P18'), CALIBRATION)
        self.assertEqual(eddy.method('P22'), CALIBRATION)
        self.assertEqual(eddy.method('P01'), NONE)
        fan = discover(Snapshot(objects=('controller_fan mcu', 'extruder'),
                                settings={'extruder': {'min_temp': 0, 'max_temp': 280}}))
        self.assertEqual(fan.method('F08', 'controller_fan mcu'), USER)
        self.assertEqual(fan.method('O05'), NONE)
        sensor = discover(Snapshot(objects=('temperature_sensor chamber',)))
        self.assertEqual(sensor.method('O05'), NONE)

    def test_lazy_cache_only_retains_discovery_results(self):
        source = Snapshot(objects=('fan',), settings={'fan': {'max_power': 1.}})
        cache = MaintenanceCache()
        self.assertIsNone(cache.snapshot)
        first = cache.get(source)
        self.assertIs(first, cache.snapshot)
        self.assertIs(first, cache.get(source))
        source.status = {'fan': {'speed': 1.}}
        self.assertIs(first, cache.get(source))
        new = cache.get(source, services=('history',))
        self.assertIsNot(first, new)
        self.assertEqual(new.method('S10'), INFORMATION)
        source.epoch += 1
        self.assertIsNot(new, cache.get(source, services=('history',)))
        source.ready = False
        self.assertIsNone(cache.get(source))
        self.assertIsNone(cache.snapshot)
        source.ready = True
        self.assertIsNotNone(cache.get(source))

    def test_idle_source_and_compact_snapshot(self):
        snap = discover(Snapshot(ready=False, epoch=42), services=('history',))
        self.assertIsInstance(snap, MaintenanceSnapshot)
        self.assertEqual(snap.epoch, 42)
        self.assertEqual(snap.method('S10'), NONE)
        # Even with many configured devices, only tiny packed masks survive.
        objects = tuple('fan_generic f{}'.format(n) for n in range(150))
        source = Snapshot(objects=objects, settings={name: {'max_power': 1.}
                                                     for name in objects})
        snap = discover(source)
        self.assertEqual(len(snap.devices), 150)
        # Count device objects AND their device-name strings. Do not claim
        # sys.getsizeof measures process RSS; the CI benchmark reports that.
        size = (sys.getsizeof(snap) + sys.getsizeof(snap.devices)
                + sys.getsizeof(snap.global_modes)
                + sys.getsizeof(snap.service_key))
        size += sum(sys.getsizeof(item) + sys.getsizeof(item.modes)
                    + sys.getsizeof(item.name) for item in snap.devices)
        self.assertLess(size, 100 * 1024)


if __name__ == '__main__':
    unittest.main()
