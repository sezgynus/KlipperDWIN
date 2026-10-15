"""Passive, bounded, API-backed discovery for Maintenance.

This module deliberately does not import PrinterCapabilities, open connections,
issue G-code, or retain references to PrinterState or configuration data.
All modes are potential test methods; execution must independently check
printer idle state, device telemetry, physical safety, and user consent.

Feature IDs correspond to the Maintenance capability condition map. Unknown,
unsupported, or not-yet-implemented tests have mode NONE and stay hidden.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import math


NONE = 0
AUTOMATIC = 1       # Independent sensor/firmware observation
USER = 2            # Meaningful human observation
EXTERNAL = 4        # User measurement with a physical instrument
CALIBRATION = 8     # Supported guided Klipper calibration
INFORMATION = 16    # Telemetry/history; not a functional test

# Exactly five bits per feature. Device and global masks are immutable ints.
_GROUPS = (('F', 13), ('H', 18), ('M', 17), ('P', 22),
           ('R', 8), ('E', 15), ('S', 20), ('O', 8))
_OFFSETS = {}
_index = 0
for _prefix, _count in _GROUPS:
    _OFFSETS[_prefix] = (_index, _count)
    _index += _count
FEATURE_COUNT = _index
_MASK = 31


def _index_for(feature):
    if not isinstance(feature, str) or len(feature) != 3:
        raise ValueError('Invalid Maintenance feature ID')
    group = _OFFSETS.get(feature[0])
    if group is None or not feature[1:].isdigit():
        raise ValueError('Invalid Maintenance feature ID')
    index = int(feature[1:])
    if not 1 <= index <= group[1]:
        raise ValueError('Unknown Maintenance feature ID')
    return group[0] + index - 1


def _add(bits, feature, modes):
    if modes & ~_MASK:
        raise ValueError('Invalid method mask')
    return bits | (modes << (_index_for(feature) * 5))


def _mode(bits, feature):
    return (bits >> (_index_for(feature) * 5)) & _MASK


def _get(mapping, key, default=None):
    try:
        return mapping.get(key, default)
    except (AttributeError, TypeError):
        return default


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _tachometer(config):
    # An absent/null RPM reading is NOT evidence of a tachometer.
    # tachometer_pin is a structural capability; runtime still verifies RPM.
    return bool(_get(config, 'tachometer_pin'))


def _pwm_steps(config):
    lo = _get(config, 'off_below', 0)
    hi = _get(config, 'max_power', 1)
    return (_is_number(lo) and _is_number(hi) and hi > lo and hi > 0)


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    name: str
    family: str
    modes: int

    def method(self, feature):
        return _mode(self.modes, feature)


@dataclass(frozen=True, slots=True)
class MaintenanceSnapshot:
    epoch: int
    devices: tuple = ()
    global_modes: int = 0
    config_marker: int = 0
    service_key: tuple = ()

    def method(self, feature, device=None):
        if device is None:
            return _mode(self.global_modes, feature)
        for item in self.devices:
            if item.name == device:
                return item.method(feature)
        return NONE

    def instances(self, feature):
        """A compact selection of devices offering a requested feature."""
        index = _index_for(feature)
        shift = 5 * index
        return tuple(item for item in self.devices if (item.modes >> shift) & _MASK)


def discover(state, services=()):
    """Derive a compact immutable snapshot from existing API state references.

    `state` provides .ready, .epoch, .objects, .settings and .status.
    `services` is a caller-provided iterable of positively observed Moonraker
    or Petrel API capabilities; it must not be inferred from a service name.
    No input mapping, callback, connection, or temporary builder survives.
    """
    if not state.ready:
        return MaintenanceSnapshot(state.epoch)
    settings, status = state.settings, state.status
    objects = state.objects
    names = set(objects)             # Temporary; never retained.
    services = frozenset(services)   # Explicit API evidence, never guesses.
    results = []
    physical_endstops = False
    accel = any(n.startswith(('adxl345', 'lis2dw', 'mpu9250', 'icm20948',
                              'lis3dh', 'bmi160', 'bmi270', 'adxl345_pico'))
                for n in names)
    has_resonance = 'resonance_tester' in names and accel
    load_cell_probe = 'load_cell_probe' in names
    eddy_probe = any(n.startswith('probe_eddy_current ') for n in names)
    probe = ('probe' in names or 'bltouch' in names or
             'smart_effector' in names or eddy_probe)
    switch_probe = probe and not load_cell_probe and not eddy_probe
    has_motion = 'toolhead' in names and 'gcode_move' in names
    has_manual_probe = 'manual_probe' in names
    has_mesh = 'bed_mesh' in names
    heaters = set()

    # No objects are copied into the snapshot. Names refer to existing strings.
    for name in sorted(names):
        cfg = _get(settings, name, {})
        device_status = _get(status, name, {})
        bits = 0
        family = None
        if name == 'fan' or name.startswith(('fan_generic ', 'heater_fan ',
                                             'controller_fan ', 'temperature_fan ')):
            family = 'fan'
            tach = _tachometer(cfg)
            steps = _pwm_steps(cfg)
            method = AUTOMATIC if tach else USER
            if name == 'fan' and steps:
                bits = _add(bits, 'F01', method)
                bits = _add(bits, 'F02', method)
                bits = _add(bits, 'F12', method)
            elif name.startswith('fan_generic ') and steps:
                bits = _add(bits, 'F04', method)
                bits = _add(bits, 'F05', method)
                bits = _add(bits, 'F12', method)
            elif name.startswith('heater_fan ') and any(
                    heater.strip() in names for heater in
                    str(_get(cfg, 'heater', 'extruder')).split(',')):
                # Natural heater-fan control only; NEVER force this fan off.
                bits = _add(bits, 'F06', method)
                if tach:
                    bits = _add(bits, 'F07', AUTOMATIC)
            elif name.startswith('controller_fan ') and (
                    _get(cfg, 'heater', 'extruder') or _get(cfg, 'stepper')):
                bits = _add(bits, 'F08', method)
            elif name.startswith('temperature_fan '):
                bits = _add(bits, 'F09', INFORMATION)
            if tach:
                bits = _add(bits, 'F11', AUTOMATIC | INFORMATION)
                if name in ('fan',) or name.startswith('fan_generic '):
                    bits = _add(bits, 'F03', AUTOMATIC)
        elif (name == 'heater_bed' or name.startswith('extruder') and
              name[8:].isdigit() or name == 'extruder' or
              name.startswith('heater_generic ')):
            family = 'heater'
            # Other Klipper objects can have misleading names. Require limits.
            min_temp = _get(cfg, 'min_temp')
            max_temp = _get(cfg, 'max_temp')
            if (_is_number(min_temp) and _is_number(max_temp)
                    and min_temp < max_temp):
                heaters.add(name)
                for f in ('H01', 'H05', 'H06', 'H07', 'H08', 'H09', 'H13'):
                    bits = _add(bits, f, AUTOMATIC)
                bits = _add(bits, 'H11', INFORMATION)
                if name == 'heater_bed':
                    bits = _add(bits, 'H03', CALIBRATION)
                elif name.startswith('heater_generic '):
                    bits = _add(bits, 'H04', CALIBRATION)
                else:
                    bits = _add(bits, 'H02', CALIBRATION)
        elif name.startswith(('temperature_sensor ', 'temperature_host ',
                              'temperature_mcu ')):
            family = 'sensor'
            bits = _add(bits, 'H14', INFORMATION)
        elif name.startswith(('tmc2130 ', 'tmc2208 ', 'tmc2209 ', 'tmc2240 ',
                              'tmc2660 ', 'tmc5160 ', 'tmc5161 ')):
            family = 'driver'
            bits = _add(bits, 'M09', INFORMATION)
            # DUMP_TMC is textual G-code, not a structured status API.
            # Do not advertise fault/temperature tests without actual fields.
            if _is_number(_get(device_status, 'temperature')):
                bits = _add(bits, 'M08', AUTOMATIC | INFORMATION)
            if isinstance(_get(device_status, 'drv_status'), Mapping):
                bits = _add(bits, 'M07', AUTOMATIC | INFORMATION)
                bits = _add(bits, 'M10', AUTOMATIC)
        elif name.startswith(('stepper_x', 'stepper_y', 'stepper_z')):
            family = 'stepper'
            if has_motion:
                bits = _add(bits, 'M04', USER)
                bits = _add(bits, 'M05', USER)
                bits = _add(bits, 'M06', EXTERNAL)
            pin = str(_get(cfg, 'endstop_pin', ''))
            if pin and 'virtual_endstop' not in pin:
                physical_endstops = True
        elif name.startswith(('filament_switch_sensor ',
                              'filament_motion_sensor ')):
            family = 'filament'
            if name.startswith('filament_switch_sensor '):
                bits = _add(bits, 'E03', AUTOMATIC | USER)
            else:
                bits = _add(bits, 'E04', AUTOMATIC)
        elif name.startswith(('hall_filament_width_sensor',
                              'tsl1401cl_filament_width_sensor')):
            family = 'filament'
            bits = _add(bits, 'E05', AUTOMATIC | INFORMATION | EXTERNAL)
            bits = _add(bits, 'E06', AUTOMATIC | INFORMATION)
        elif name.startswith(('adxl345', 'lis2dw', 'mpu9250', 'icm20948',
                              'lis3dh', 'bmi160', 'bmi270')):
            family = 'accelerometer'
            bits = _add(bits, 'R01', AUTOMATIC | INFORMATION)
            if has_resonance:
                bits = _add(bits, 'R02', AUTOMATIC)
                bits = _add(bits, 'R03', AUTOMATIC)
                bits = _add(bits, 'R04', CALIBRATION)
        elif name == 'load_cell' or name.startswith('load_cell '):
            family = 'load_cell'
            bits = _add(bits, 'E08', AUTOMATIC | INFORMATION)
            bits = _add(bits, 'E09', CALIBRATION | EXTERNAL)
        elif name.startswith('gcode_button '):
            family = 'button'
            # Firmware buttons may execute macros on press: no generic test.
        elif name.startswith(('led ', 'neopixel ', 'dotstar ', 'pca9632 ',
                              'display_template ')):
            family = 'led'
            if not name.startswith('display_template '):
                bits = _add(bits, 'O04', USER)
        elif name.startswith(('output_pin ', 'servo ', 'manual_stepper ')):
            # Unknown actuators have no safe generic test protocol.
            family = 'actuator'
        elif name.startswith('canbus_stats '):
            family = 'can'
            bits = _add(bits, 'S07', AUTOMATIC | INFORMATION)
        elif name.startswith(('bme280 ', 'htu21d ', 'sht3x ', 'aht10 ')):
            family = 'sensor'
            bits = _add(bits, 'H14', INFORMATION)
            if _is_number(_get(device_status, 'humidity')):
                bits = _add(bits, 'H16', INFORMATION)
        if family is not None and bits:
            results.append(DeviceCapabilities(name, family, bits))

    global_bits = 0
    if has_motion:
        global_bits = _add(global_bits, 'M03', CALIBRATION | USER)
        global_bits = _add(global_bits, 'M14', INFORMATION)
    if physical_endstops and 'query_endstops' in names:
        global_bits = _add(global_bits, 'M01', AUTOMATIC | USER)
        global_bits = _add(global_bits, 'M02', AUTOMATIC | USER)
    if 'stepper_enable' in names:
        global_bits = _add(global_bits, 'M11', INFORMATION)
    if 'endstop_phase' in names:
        global_bits = _add(global_bits, 'M12', INFORMATION | CALIBRATION)
    if 'dual_carriage' in names:
        global_bits = _add(global_bits, 'M16', INFORMATION)
    if (has_manual_probe and 'stepper_z' in names and
            _get(_get(settings, 'stepper_z', {}), 'endstop_pin')):
        global_bits = _add(global_bits, 'P06', CALIBRATION | USER)
    if switch_probe:
        global_bits = _add(global_bits, 'P01', AUTOMATIC)
    if probe:
        for f in ('P03', 'P04'):
            global_bits = _add(global_bits, f, AUTOMATIC)
        if has_manual_probe:
            global_bits = _add(global_bits, 'P05', CALIBRATION)
    if load_cell_probe:
        global_bits = _add(global_bits, 'P02', AUTOMATIC | USER)
        global_bits = _add(global_bits, 'P20', AUTOMATIC | INFORMATION)
    if has_mesh:
        global_bits = _add(global_bits, 'P08', CALIBRATION | USER)
        if probe or load_cell_probe:
            global_bits = _add(global_bits, 'P07', CALIBRATION)
        if _get(_get(status, 'bed_mesh', {}), 'probed_matrix'):
            global_bits = _add(global_bits, 'P09', INFORMATION)
    if 'screws_tilt_adjust' in names and (probe or load_cell_probe):
        global_bits = _add(global_bits, 'P11', CALIBRATION)
    for obj, feature in (('bed_screws', 'P12'), ('z_tilt', 'P13'),
                         ('quad_gantry_level', 'P14'), ('bed_tilt', 'P15'),
                         ('delta_calibrate', 'P16'), ('axis_twist_compensation', 'P17')):
        if obj in names and (obj in ('bed_screws', 'delta_calibrate') or probe or load_cell_probe):
            global_bits = _add(global_bits, feature, CALIBRATION)
    if eddy_probe:
        global_bits = _add(global_bits, 'P18', CALIBRATION)
        if any(n.startswith('temperature_probe ') for n in names):
            global_bits = _add(global_bits, 'P22', CALIBRATION)
    if 'bltouch' in names:
        global_bits = _add(global_bits, 'P19', USER)
    if 'skew_correction' in names and has_motion:
        global_bits = _add(global_bits, 'P21', EXTERNAL | CALIBRATION)
    if has_resonance:
        global_bits = _add(global_bits, 'R02', AUTOMATIC)
        global_bits = _add(global_bits, 'R03', AUTOMATIC)
        global_bits = _add(global_bits, 'R04', CALIBRATION)
    if 'extruder' in heaters:
        global_bits = _add(global_bits, 'E01', USER)
        global_bits = _add(global_bits, 'E02', EXTERNAL)
        global_bits = _add(global_bits, 'E07', USER)
    if 'mmu' in names and 'mmu_machine' in names:
        mmu = _get(status, 'mmu', {})
        if _get(mmu, 'sensors'):
            global_bits = _add(global_bits, 'E11', AUTOMATIC | USER)
    if 'machine.proc_stats' in services:
        global_bits = _add(global_bits, 'S01', INFORMATION)
    if 'machine.cpu_temp' in services:
        global_bits = _add(global_bits, 'S02', INFORMATION)
    for service, feature in (('machine.throttled_state', 'S03'),
                             ('machine.disk', 'S04'), ('machine.network', 'S05'),
                             ('history', 'S10'), ('maintenance.records', 'S11'),
                             ('maintenance.usage_counters', 'S12'),
                             ('petrel.uart_diagnostics', 'S14'),
                             ('petrel.encoder_diagnostics', 'S15'),
                             ('petrel.lcd_diagnostics', 'S16'),
                             ('petrel.backlight', 'S17'),
                             ('petrel.buzzer', 'S18'),
                             ('update_manager', 'S19'),
                             ('maintenance.report_export', 'S20')):
        if service in services:
            mode = USER if feature in ('S17', 'S18') else INFORMATION
            global_bits = _add(global_bits, feature, mode)
    if 'webhooks' in names:
        global_bits = _add(global_bits, 'S08', INFORMATION)
    if 'gcode_store' in services:
        global_bits = _add(global_bits, 'S09', INFORMATION)
    if any(n == 'mcu' or n.startswith('mcu ') for n in names):
        global_bits = _add(global_bits, 'S06', INFORMATION)
    if 'maintenance.ambient_sensor' in services:
        # Do not equate every generic temperature probe with an ambient probe.
        global_bits = _add(global_bits, 'O05', INFORMATION)
    if 'maintenance.guided_service' in services:
        global_bits = _add(global_bits, 'O06', USER)
    # Feature codes not positively proven are encoded as NONE (hidden).
    return MaintenanceSnapshot(state.epoch, tuple(results), global_bits,
                               id(settings), tuple(sorted(services)))