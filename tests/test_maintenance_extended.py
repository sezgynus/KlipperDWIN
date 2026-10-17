"""Extended API-backed capability matrix and fail-closed contracts."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import (discover, AUTOMATIC, CALIBRATION,
                                   EXTERNAL, INFORMATION, NONE, USER)


class State:
    ready = True
    epoch = 12

    def __init__(self, objects=(), settings=None, status=None):
        self.objects = objects
        self.settings = settings or {}
        self.status = status or {}


def device(name, cfg=None, status=None, others=()):
    return discover(State((name,) + tuple(others), {name: cfg or {}},
                          {name: status or {}}))


class ExtendedTests(unittest.TestCase):
    def test_config_only_accelerometer_and_resonance_are_discovered(self):
        # Klipper objects/list filters objects lacking get_status; an
        # attached ADXL345 and ResonanceTester may exist only in the
        # effective configfile.settings received at Klipper READY.
        state = State(
            ('toolhead', 'gcode_move', 'output_pin adxl_power'),
            {'adxl345': {'cs_pin': 'rpi:None'},
             'resonance_tester': {'accel_chip': 'adxl345',
                                  'probe_points': [[100., 100., 20.]]}})
        caps = discover(state)
        self.assertEqual(caps.method('R01', 'adxl345'), AUTOMATIC | INFORMATION)
        self.assertEqual(caps.method('R02', 'adxl345'), AUTOMATIC)
        self.assertEqual(caps.method('R03'), AUTOMATIC)
        self.assertEqual(caps.method('R04'), CALIBRATION)
        self.assertEqual(caps.axes('R02'), 3)
        self.assertIn('R02', caps.available_features())
        self.assertEqual(len(caps.instances('R01')), 1)

        # A power pin name alone is NOT accelerometer evidence.
        power_only = discover(State(('output_pin adxl_power',)))
        self.assertEqual(power_only.method('R01'), NONE)
        self.assertEqual(power_only.method('R02'), NONE)
        no_tester = discover(State((), {'adxl345': {'cs_pin': 'rpi:None'}}))
        self.assertEqual(no_tester.method('R01', 'adxl345'),
                         AUTOMATIC | INFORMATION)
        self.assertEqual(no_tester.method('R02'), NONE)
        mismatched_chip = discover(State(
            (), {'adxl345': {}, 'resonance_tester': {'accel_chip': 'lis2dw'}}))
        self.assertEqual(mismatched_chip.method('R01'), AUTOMATIC | INFORMATION)
        self.assertEqual(mismatched_chip.method('R02'), NONE)

    def test_config_only_named_accelerometers_keep_axis_assignment(self):
        state = State((), {
            'adxl345 toolhead': {'cs_pin': 'rpi:None'},
            'lis2dw bed': {'cs_pin': 'rpi:None'},
            'resonance_tester': {'accel_chip_x': 'adxl345 toolhead',
                                 'accel_chip_y': 'lis2dw bed'}})
        caps = discover(state)
        self.assertEqual(caps.axes('R02', 'adxl345 toolhead'), 1)
        self.assertEqual(caps.axes('R02', 'lis2dw bed'), 2)
        self.assertEqual(caps.axes('R02'), 3)
        self.assertEqual(len(caps.instances('R01')), 2)

    def test_resonance_requires_sensor_assignment_and_correct_chip(self):
        s = State(('adxl345', 'lis2dw extra', 'resonance_tester'),
                  {'resonance_tester': {'accel_chip_x': 'lis2dw extra'}})
        result = discover(s)
        self.assertEqual(result.method('R02'), AUTOMATIC)
        self.assertEqual(result.method('R02', 'lis2dw extra'), AUTOMATIC)
        self.assertEqual(result.method('R02', 'adxl345'), NONE)
        self.assertEqual(discover(State(s.objects)).method('R02'), NONE)
        self.assertEqual(discover(State(s.objects, {'resonance_tester': {'accel_chip': 'unknown'}})).method('R02'), NONE)
        self.assertEqual(result.method('R07'), NONE)
        self.assertEqual(result.method('R08'), NONE)

    def test_resonance_chips_are_scoped_to_assigned_axes(self):
        s = State(('adxl345', 'lis2dw z', 'resonance_tester'),
                  {'resonance_tester': {'accel_chip': 'adxl345',
                                        'accel_chip_z': 'lis2dw z'}})
        result = discover(s)
        self.assertEqual(result.axes('R02'), 7)
        self.assertEqual(result.axes('R02', 'adxl345'), 3)
        self.assertEqual(result.axes('R04', 'lis2dw z'), 4)
        self.assertEqual(result.axes('P01'), 0)
        self.assertEqual(result.axes('R02', 'not-a-chip'), 0)
        separate = discover(State(s.objects, {'resonance_tester': {
            'accel_chip_x': 'adxl345', 'accel_chip_y': 'lis2dw z'}}))
        self.assertEqual(separate.axes('R02', 'adxl345'), 1)
        self.assertEqual(separate.axes('R02', 'lis2dw z'), 2)
        self.assertEqual(discover(State(s.objects)).axes('R02'), 0)

    def test_belt_and_resonance_trends_need_verified_profiles(self):
        objects = ('adxl345', 'resonance_tester')
        settings = {'resonance_tester': {'accel_chip': 'adxl345'}, 'printer': {'kinematics': 'corexy'}}
        bare = discover(State(objects, settings))
        self.assertEqual(bare.method('R05'), NONE)
        self.assertEqual(bare.method('R06'), NONE)
        tagged = discover(State(objects, settings), ('maintenance.resonance_baseline',
                                                   'maintenance.belt_resonance_profile'))
        self.assertEqual(tagged.method('R05'), AUTOMATIC | INFORMATION)
        self.assertEqual(tagged.method('R06'), AUTOMATIC | INFORMATION)
        cartesian = discover(State(objects, {'resonance_tester': settings['resonance_tester']}),
                             ('maintenance.belt_resonance_profile',))
        self.assertEqual(cartesian.method('R06'), NONE)

    def test_configured_steppers_exist_without_klipper_object_status(self):
        # Real Klipper exposes these configured sections through
        # configfile.settings without necessarily advertising matching
        # printer.objects.list entries. The previous implementation missed
        # axis motor, endstop and Z-endstop calibration capabilities.
        objects = ('toolhead', 'gcode_move', 'query_endstops', 'manual_probe')
        settings = {
            'stepper_x': {'step_pin': 'PA0', 'endstop_pin': '^PA1'},
            'stepper_y': {'step_pin': 'PA2', 'endstop_pin': '^PA3'},
            'stepper_z': {'step_pin': 'PA4', 'endstop_pin': '^PA5'},
            'stepper_z1': {'step_pin': 'PB1'},
            'stepper_xy_unsupported': {'step_pin': 'PB2'},
        }
        caps = discover(State(objects, settings))
        for name in ('stepper_x', 'stepper_y', 'stepper_z'):
            self.assertEqual(caps.method('M04', name), USER)
            self.assertEqual(caps.method('M05', name), USER)
            self.assertEqual(caps.method('M06', name), EXTERNAL)
        self.assertEqual(caps.method('M01'), AUTOMATIC | USER)
        self.assertEqual(caps.method('P06'), CALIBRATION | USER)
        self.assertEqual(caps.method('M04', 'stepper_z1'), USER)
        self.assertEqual(caps.method('M05', 'stepper_z1'), NONE)
        self.assertEqual(caps.method('M04', 'stepper_xy_unsupported'), NONE)
        self.assertIn('M04', caps.available_features())

        settings['stepper_z']['endstop_pin'] = 'probe:z_virtual_endstop'
        virtual = discover(State(objects, settings))
        self.assertEqual(virtual.method('P06'), NONE)
        self.assertEqual(virtual.method('M01'), AUTOMATIC | USER)
        settings['stepper_x']['endstop_pin'] = 'tmc2209_stepper_x:virtual_endstop'
        settings['stepper_y']['endstop_pin'] = 'tmc2209_stepper_y:virtual_endstop'
        virtual = discover(State(objects, settings))
        self.assertEqual(virtual.method('M01'), NONE)

    def test_virtual_endstops_are_never_hand_pressed(self):
        c = discover(State(('stepper_x', 'query_endstops', 'toolhead', 'gcode_move'),
                           {'stepper_x': {'endstop_pin': 'tmc2209_stepper_x:virtual_endstop'}}))
        self.assertEqual(c.method('M01'), NONE)
        self.assertEqual(c.method('M02'), NONE)
        physical = discover(State(('stepper_x', 'query_endstops'),
                                  {'stepper_x': {'endstop_pin': '^PA5'}}))
        self.assertEqual(physical.method('M01'), AUTOMATIC | USER)
        self.assertEqual(physical.method('M02'), NONE)

    def test_tmc_status_capability_not_hidden_when_driver_is_disabled(self):
        a = device('tmc2208 stepper_x')
        self.assertEqual(a.method('M07', 'tmc2208 stepper_x'), AUTOMATIC | INFORMATION)
        self.assertEqual(a.method('M10', 'tmc2208 stepper_x'), NONE)
        self.assertEqual(a.method('M08', 'tmc2208 stepper_x'), NONE)
        self.assertEqual(a.method('M09', 'tmc2208 stepper_x'), NONE)
        b = device('tmc2209 stepper_x', {'run_current': .65},
                   {'temperature': None, 'drv_status': None})
        self.assertEqual(b.method('M09', 'tmc2209 stepper_x'), INFORMATION)
        self.assertEqual(b.method('M08', 'tmc2209 stepper_x'), NONE)
        self.assertEqual(b.method('M07', 'tmc2209 stepper_x'), AUTOMATIC | INFORMATION)
        self.assertEqual(b.method('M10', 'tmc2209 stepper_x'), NONE)
        self.assertEqual(device('tmc9999 stepper_x').method('M07', 'tmc9999 stepper_x'), NONE)

    def test_temperature_history_only_after_baseline(self):
        name = 'heater_bed'
        cfg = {'min_temp': 0, 'max_temp': 120}
        bare = device(name, cfg)
        self.assertEqual(bare.method('H03', name), CALIBRATION)
        for f in ('H10', 'H12', 'H18'):
            self.assertEqual(bare.method(f, name), NONE)
        evidence = ('maintenance.heater_baseline:heater_bed',
                    'maintenance.heater_wattage:heater_bed',
                    'maintenance.thermal_ab_heater:heater_bed')
        tagged = discover(State((name,), {name: cfg}), evidence)
        self.assertEqual(tagged.method('H10', name), AUTOMATIC | INFORMATION)
        self.assertEqual(tagged.method('H12', name), INFORMATION)
        self.assertEqual(tagged.method('H18', name), AUTOMATIC)

    def test_environmental_driver_capabilities_without_live_subscription(self):
        sensors = State(('bme280 chamber', 'sht3x chamber',
                         'htu21d cabinet', 'aht10 feeder'))
        result = discover(sensors)
        for name in sensors.objects:
            self.assertEqual(result.method('H14', name), INFORMATION)
            self.assertEqual(result.method('H16', name), INFORMATION)
        self.assertEqual(result.method('E15'), NONE)
        mapped = discover(sensors, ('maintenance.chamber_humidity_sensor',))
        self.assertEqual(mapped.method('E15'), INFORMATION)

        # A BME280 driver can also manage a pressure-only BMP280; the
        # humidity-dependent chamber feature must not be assumed.
        bmp = discover(State(('bme280 pressure_only',)),
                       ('maintenance.chamber_humidity_sensor',))
        self.assertEqual(bmp.method('H16', 'bme280 pressure_only'), INFORMATION)
        self.assertEqual(bmp.method('E15'), NONE)

    def test_humidity_not_automatically_chamber_identity(self):
        s = State(('temperature_sensor chamber',),
                  status={'temperature_sensor chamber': {'temperature': 34, 'humidity': 48}})
        a = discover(s)
        self.assertEqual(a.method('H16', 'temperature_sensor chamber'), INFORMATION)
        self.assertEqual(a.method('E15'), NONE)
        b = discover(s, ('maintenance.chamber_humidity_sensor',))
        self.assertEqual(b.method('E15'), INFORMATION)

    def test_manual_actuator_requires_explicit_positive_safety_record(self):
        s = State(('servo cutter', 'output_pin laser', 'manual_stepper load',
                   'gcode_button emergency'))
        a = discover(s)
        for f, name in [('O02', 'servo cutter'), ('O03', 'output_pin laser'),
                        ('M15', 'manual_stepper load'), ('O01', 'gcode_button emergency')]:
            self.assertEqual(a.method(f, name), NONE)
        b = discover(State(s.objects),
                     ('maintenance.safe_servo:servo cutter',
                      'maintenance.visual:output_pin laser',
                      'maintenance.safe_stepper:manual_stepper load',
                      'maintenance.safe_button:gcode_button emergency'))
        self.assertEqual(b.method('O02', 'servo cutter'), USER)
        self.assertEqual(b.method('O03', 'output_pin laser'), USER)
        self.assertEqual(b.method('M15', 'manual_stepper load'), USER | EXTERNAL)
        self.assertEqual(b.method('O01', 'gcode_button emergency'), AUTOMATIC | USER)

    def test_load_cell_capability_does_not_depend_on_startup_force(self):
        a = discover(State(('load_cell_probe',)))
        self.assertEqual(a.method('P02'), AUTOMATIC | USER)
        self.assertEqual(a.method('P20'), AUTOMATIC | INFORMATION)
        b = discover(State(('load_cell_probe',), status={'load_cell_probe': {'force_g': 1.25}}))
        self.assertEqual(b.method('P20'), AUTOMATIC | INFORMATION)
        self.assertEqual(discover(State(('probe',))).method('P20'), NONE)

    def test_mesh_capability_does_not_depend_on_active_mesh_at_startup(self):
        a = discover(State(('bed_mesh',), status={'bed_mesh': {'probed_matrix': [[]], 'profiles': {}}}))
        self.assertEqual(a.method('P09'), INFORMATION)
        self.assertEqual(a.method('P10'), NONE)
        self.assertEqual(discover(State(('bed_mesh',))).method('P09'), INFORMATION)
        self.assertEqual(discover(State(())).method('P09'), NONE)
        b = discover(State(('bed_mesh',)), ('maintenance.mesh_baseline',))
        self.assertEqual(b.method('P10'), AUTOMATIC | INFORMATION)

    def test_temperature_fan_information_without_subscribed_status(self):
        a = discover(State(('temperature_fan chamber',)))
        self.assertEqual(a.method('F09', 'temperature_fan chamber'), INFORMATION)
        self.assertEqual(discover(State(())).method('F09', 'temperature_fan chamber'), NONE)

    def test_mmupath_and_filament_dryer_do_not_follow_generic_names(self):
        s = State(('mmu', 'mmu_machine', 'heater_generic dryer', 'extruder'),
                  {'heater_generic dryer': {'min_temp': 0, 'max_temp': 110},
                   'extruder': {'min_temp': 0, 'max_temp': 280}},
                  {'mmu': {'sensors': {'gate': True}}})
        a = discover(s)
        self.assertEqual(a.method('E11'), AUTOMATIC | USER)
        self.assertEqual(a.method('E12'), NONE)
        self.assertEqual(a.method('E14'), NONE)
        b = discover(s, ('petrel.mmu_test_adapter', 'maintenance.dryer_profile'))
        self.assertEqual(b.method('E12'), AUTOMATIC | USER)
        self.assertEqual(b.method('E14'), CALIBRATION)

    def test_exact_counter_requires_counter_service(self):
        s = State(('toolhead', 'gcode_move'), status={'motion_report': {'live_position': [1, 2, 3]}})
        self.assertEqual(discover(s).method('S13'), NONE)
        self.assertEqual(discover(s, ('maintenance.travel_counter',)).method('S13'), INFORMATION)

    def test_always_hidden_unverifiable_features(self):
        s = State(('resonance_tester', 'adxl345', 'extruder', 'mmu', 'mmu_machine'))
        a = discover(s, ('maintenance.travel_counter', 'maintenance.dryer_profile'))
        for code in ('M02', 'M17', 'R07', 'R08', 'E10', 'O07', 'O08'):
            self.assertEqual(a.method(code), NONE)


if __name__ == '__main__':
    unittest.main()
