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

# IDs whose very premise is unmeasurable, unsafe, or a negative capability.
# Their deliberate hidden state is PART of the complete 121-ID contract.
ALWAYS_HIDDEN = frozenset(('M02', 'M17', 'R07', 'R08', 'E10', 'O07', 'O08'))

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


def _stepper_section(name):
    # Standard Klipper stepper sections are effective configuration, not
    # necessarily separately queryable printer.objects.list members.
    return (isinstance(name, str)
            and name[:9] in ('stepper_x', 'stepper_y', 'stepper_z')
            and (len(name) == 9 or name[9:].isdigit()))


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    name: str
    family: str
    modes: int
    axes: int = 0  # Resonance measurement axes: X=1, Y=2, Z=4.

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
            # Aggregated availability: a fan- or heater-only test must
            # appear in the UI even if it has no global feature bit.
            mode = _mode(self.global_modes, feature)
            for item in self.devices:
                mode |= item.method(feature)
            return mode
        for item in self.devices:
            if item.name == device:
                return item.method(feature)
        return NONE

    def available_features(self):
        """Report global AND per-device tests; compute without a retained index."""
        bits = self.global_modes
        for item in self.devices:
            bits |= item.modes
        return tuple(p + str(i).zfill(2)
                     for p, count in _GROUPS for i in range(1, count + 1)
                     if _mode(bits, p + str(i).zfill(2)))

    def axes(self, feature='R02', device=None):
        """Resonance axis subset (X=1, Y=2, Z=4); no measurement implied."""
        _index_for(feature)  # Validate before revealing any axes.
        if feature not in ('R02', 'R03', 'R04'):
            return 0
        bits = 0
        for item in self.devices:
            if item.family == 'accelerometer' and (device is None or device == item.name):
                bits |= item.axes
        return bits

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
    # Stepper sections are authoritative in configfile.settings even if
    # Klipper does not expose them as individual status objects. Consider
    # only supported X/Y/Z names; never promote arbitrary config sections.
    accel_types = ('adxl345', 'lis2dw', 'mpu9250', 'icm20948',
                   'lis3dh', 'bmi160', 'bmi270')
    if isinstance(settings, Mapping):
        # printer.objects.list is ONLY status-capable Klipper objects.
        # ResonanceTester and accelerometer drivers such as ADXL345 do
        # not expose get_status(), so a valid, loaded config section is
        # the authoritative structural evidence for these features.
        names.update(section for section in settings
                     if _stepper_section(section)
                     or (isinstance(section, str) and section.startswith('pwm_cycle_time ')
                         and 'maintenance.audible:' + section in services)
                     or section == 'resonance_tester'
                     or (isinstance(section, str)
                         and section.split(' ', 1)[0] in accel_types))
    results = []
    physical_endstops = False
    accelerometers = {n for n in names if n.split(' ', 1)[0] in accel_types}
    resonance_config = _get(settings, 'resonance_tester', {})
    assigned_axes = {}
    if 'resonance_tester' in names:
        # Mirror Klipper's actual resonance_tester chip selection:
        # a shared accel_chip is X+Y unless accel_chip_x is configured.
        explicit_x = _get(resonance_config, 'accel_chip_x', '')
        chips = (
            (('x', 'accel_chip_x'), ('y', 'accel_chip_y'))
            if explicit_x else (('xy', 'accel_chip'),)
        )
        for axes, key in chips + (('z', 'accel_chip_z'),):
            raw = _get(resonance_config, key, '')
            if isinstance(raw, str) and raw.strip() in accelerometers:
                axis_bits = (1 if 'x' in axes else 0) | (2 if 'y' in axes else 0) | (4 if 'z' in axes else 0)
                name = raw.strip()
                assigned_axes[name] = assigned_axes.get(name, 0) | axis_bits
    has_resonance = bool(assigned_axes)
    load_cell_probe = 'load_cell_probe' in names
    eddy_probe = any(n.startswith('probe_eddy_current ') for n in names)
    probe = ('probe' in names or 'bltouch' in names or
             'smart_effector' in names or eddy_probe)
    switch_probe = probe and not load_cell_probe and not eddy_probe
    has_motion = 'toolhead' in names and 'gcode_move' in names
    has_manual_probe = 'manual_probe' in names
    has_mesh = 'bed_mesh' in names
    heaters = set()
    humidity_sensors = set()
    temperature_sensors = set()

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
            if name == 'fan':
                bits = _add(bits, 'F01', method)
                if steps:
                    bits = _add(bits, 'F02', method)
                    bits = _add(bits, 'F12', method)
            elif name.startswith('fan_generic '):
                bits = _add(bits, 'F04', method)
                if steps:
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
                # The configured temperature_fan exposes temperature via
                # Klipper's status API; the field need not be subscribed or
                # populated at READY. Read it only when the view opens.
                bits = _add(bits, 'F09', INFORMATION)
                if ('maintenance.safe_temperature_fan:' + name) in services:
                    bits = _add(bits, 'F10', method)
            if tach:
                bits = _add(bits, 'F11', AUTOMATIC | INFORMATION)
                if name in ('fan',) or name.startswith('fan_generic '):
                    bits = _add(bits, 'F03', AUTOMATIC)
            if ('maintenance.thermal_ab_fan:' + name) in services and tach:
                bits = _add(bits, 'F13', AUTOMATIC)
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
                temperature_sensors.add(name)
                for f in ('H01', 'H05', 'H06', 'H07', 'H08', 'H09', 'H13'):
                    bits = _add(bits, f, AUTOMATIC)
                bits = _add(bits, 'H11', INFORMATION)
                bits = _add(bits, 'H14', INFORMATION)
                if ('maintenance.heater_baseline:' + name) in services:
                    bits = _add(bits, 'H10', AUTOMATIC | INFORMATION)
                if ('maintenance.heater_wattage:' + name) in services:
                    bits = _add(bits, 'H12', INFORMATION)
                if ('maintenance.thermal_ab_heater:' + name) in services:
                    bits = _add(bits, 'H18', AUTOMATIC)
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
            temperature_sensors.add(name)
            if _is_number(_get(device_status, 'humidity')):
                bits = _add(bits, 'H16', INFORMATION)
                humidity_sensors.add(name)
            if (_is_number(_get(device_status, 'pressure')) or
                    _is_number(_get(device_status, 'gas'))):
                bits = _add(bits, 'H16', INFORMATION)
        elif name.startswith(('tmc2130 ', 'tmc2208 ', 'tmc2209 ', 'tmc2240 ',
                              'tmc2660 ', 'tmc5160 ', 'tmc5161 ')):
            family = 'driver'
            if _is_number(_get(cfg, 'run_current')) or _is_number(_get(device_status, 'run_current')):
                bits = _add(bits, 'M09', INFORMATION)
            # Klipper defines drv_status for recognized TMC objects but
            # returns null while idle/disabled. Do not confuse absence of
            # a READY sample with lack of a diagnostic capability. Only
            # a fresh non-null measurement can pass a runtime test.
            bits = _add(bits, 'M07', AUTOMATIC | INFORMATION)
            bits = _add(bits, 'M10', AUTOMATIC)
            if (_is_number(_get(device_status, 'temperature')) or
                    'maintenance.driver_thermal_monitor:' + name in services):
                bits = _add(bits, 'M08', AUTOMATIC | INFORMATION)
        elif _stepper_section(name):
            family = 'stepper'
            if has_motion:
                # STEPPER_BUZZ may address a named motor, including stepper_z1.
                bits = _add(bits, 'M04', USER)
                if len(name) == 9:
                    # Ordinary coordinated G1 axis motion does not directly
                    # control an individual auxiliary motor such as stepper_z1.
                    bits = _add(bits, 'M05', USER)
                    bits = _add(bits, 'M06', EXTERNAL)
            pin = str(_get(cfg, 'endstop_pin', ''))
            if pin and 'virtual_endstop' not in pin:
                physical_endstops = True
                if name in ('stepper_x', 'stepper_y', 'stepper_z'):
                    bits = _add(bits, 'M01', AUTOMATIC | USER)
                    if 'endstop_phase '+name in settings:
                        bits = _add(bits, 'M12', CALIBRATION | INFORMATION)
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
        elif name in accelerometers:
            family = 'accelerometer'
            bits = _add(bits, 'R01', AUTOMATIC | INFORMATION)
            if name in assigned_axes:
                bits = _add(bits, 'R02', AUTOMATIC)
                bits = _add(bits, 'R03', AUTOMATIC)
                bits = _add(bits, 'R04', CALIBRATION)
        elif name == 'load_cell' or name.startswith('load_cell '):
            family = 'load_cell'
            bits = _add(bits, 'E08', AUTOMATIC | INFORMATION)
            if 'maintenance.loadcell_reference' in services:
                bits = _add(bits, 'E09', CALIBRATION | EXTERNAL)
        elif name.startswith('gcode_button '):
            family = 'button'
            # A press could run a macro; require an explicit safe integration.
            if ('maintenance.safe_button:' + name) in services:
                # gcode_button always exposes 'state', but its press action
                # may run arbitrary macros. Require an explicit safe profile.
                # No status subscription is needed at discovery.
                bits = _add(bits, 'O01', AUTOMATIC | USER)
        elif name.startswith(('led ', 'neopixel ', 'dotstar ', 'pca9632 ',
                              'display_template ')):
            family = 'led'
            if not name.startswith('display_template '):
                bits = _add(bits, 'O04', USER)
        elif name.startswith(('output_pin ', 'servo ', 'manual_stepper ')):
            # Never infer actuator safety from its name or Klipper object type.
            family = 'actuator'
            if ('maintenance.safe_servo:' + name) in services and name.startswith('servo '):
                bits = _add(bits, 'O02', USER)
            elif ('maintenance.visual:' + name) in services and name.startswith('output_pin '):
                bits = _add(bits, 'O03', USER)
            elif ('maintenance.safe_stepper:' + name) in services and name.startswith('manual_stepper '):
                bits = _add(bits, 'M15', USER | EXTERNAL)
        elif name.startswith('pwm_cycle_time '):
            if 'maintenance.audible:' + name in services:
                family = 'actuator'
                bits = _add(bits, 'S18', USER)
        elif name.startswith('canbus_stats '):
            family = 'can'
            bits = _add(bits, 'S07', AUTOMATIC | INFORMATION)
        elif name.startswith(('bme280 ', 'htu21d ', 'sht3x ', 'aht10 ')):
            family = 'sensor'
            bits = _add(bits, 'H14', INFORMATION)
            # These Klipper modules expose additional structured status
            # fields even when Petrel does not subscribe to them at READY.
            # A BME280 driver may attach to a BMP280 (pressure only);
            # never assume its humidity channel exists.
            bits = _add(bits, 'H16', INFORMATION)
            if (name.startswith(('htu21d ', 'sht3x ', 'aht10 ')) or
                    _is_number(_get(device_status, 'humidity'))):
                humidity_sensors.add(name)
            temperature_sensors.add(name)
        if family is not None and bits:
            results.append(DeviceCapabilities(
                name, family, bits,
                assigned_axes.get(name, 0) if family == 'accelerometer' else 0))

    global_bits = 0
    if has_motion:
        global_bits = _add(global_bits, 'M03', CALIBRATION)
        global_bits = _add(global_bits, 'M14', INFORMATION)
    if physical_endstops and 'query_endstops' in names:
        global_bits = _add(global_bits, 'M01', AUTOMATIC | USER)
        # M02 (pressing sensorless virtual endstop) is deliberately hidden.
    if 'stepper_enable' in names:
        global_bits = _add(global_bits, 'M11', INFORMATION)
    if 'endstop_phase' in names:
        global_bits = _add(global_bits, 'M12', INFORMATION | CALIBRATION)
    if 'dual_carriage' in names or 'generic_cartesian' in names:
        global_bits = _add(global_bits, 'M16', INFORMATION)
    if any(n.startswith('angle ') for n in names):
        global_bits = _add(global_bits, 'M13', INFORMATION)
    z_endstop = str(_get(_get(settings, 'stepper_z', {}), 'endstop_pin', ''))
    if has_manual_probe and z_endstop and 'virtual_endstop' not in z_endstop:
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
        # Klipper load_cell_probe includes load_cell status fields such as
        # force_g. An actual force reading need not exist at READY; the
        # diagnostic will validate fresh samples when explicitly started.
        global_bits = _add(global_bits, 'P20', AUTOMATIC | INFORMATION)
    if has_mesh:
        global_bits = _add(global_bits, 'P08', CALIBRATION | USER)
        if probe or load_cell_probe:
            global_bits = _add(global_bits, 'P07', CALIBRATION)
        # The mesh can be generated, loaded or selected after Klipper READY.
        # Snapshot visibility must represent the capability to inspect it,
        # not whether a mesh happened to be active during startup.
        global_bits = _add(global_bits, 'P09', INFORMATION)
        if 'maintenance.mesh_baseline' in services:
            global_bits = _add(global_bits, 'P10', AUTOMATIC | INFORMATION)
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
            global_bits = _add(global_bits, 'H17', CALIBRATION)
    if 'bltouch' in names:
        global_bits = _add(global_bits, 'P19', USER)
    if 'skew_correction' in names and has_motion:
        global_bits = _add(global_bits, 'P21', EXTERNAL | CALIBRATION)
    if has_resonance:
        global_bits = _add(global_bits, 'R02', AUTOMATIC)
        global_bits = _add(global_bits, 'R03', AUTOMATIC)
        global_bits = _add(global_bits, 'R04', CALIBRATION)
        if 'maintenance.resonance_baseline' in services:
            global_bits = _add(global_bits, 'R05', AUTOMATIC | INFORMATION)
        kin = _get(_get(settings, 'printer', {}), 'kinematics', '')
        if kin in ('corexy', 'corexz') and 'maintenance.belt_resonance_profile' in services:
            global_bits = _add(global_bits, 'R06', AUTOMATIC | INFORMATION)
    if 'extruder' in heaters:
        global_bits = _add(global_bits, 'E01', USER)
        global_bits = _add(global_bits, 'E02', EXTERNAL)
        global_bits = _add(global_bits, 'E07', USER)
    if 'mmu' in names and 'mmu_machine' in names:
        mmu = _get(status, 'mmu', {})
        if _get(mmu, 'sensors'):
            global_bits = _add(global_bits, 'E11', AUTOMATIC | USER)
            if 'petrel.mmu_test_adapter' in services:
                global_bits = _add(global_bits, 'E12', AUTOMATIC | USER)
    if 'spoolman' in services and 'maintenance.material_usage' in services:
        global_bits = _add(global_bits, 'E13', INFORMATION)
    if 'maintenance.dryer_profile' in services and any(n.startswith('heater_generic ') for n in heaters):
        global_bits = _add(global_bits, 'E14', CALIBRATION)
    if humidity_sensors and 'maintenance.chamber_humidity_sensor' in services:
        global_bits = _add(global_bits, 'E15', INFORMATION)
    if len(temperature_sensors) > 1 and 'maintenance.sensor_pairs' in services:
        global_bits = _add(global_bits, 'H15', AUTOMATIC | INFORMATION)
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
                             ('update_manager', 'S19'),
                             ('maintenance.report_export', 'S20')):
        if service in services:
            mode = USER if feature == 'S17' else INFORMATION
            global_bits = _add(global_bits, feature, mode)
    if 'maintenance.travel_counter' in services:
        global_bits = _add(global_bits, 'S13', INFORMATION)
    if 'webhooks' in names:
        global_bits = _add(global_bits, 'S08', INFORMATION)
    if 'gcode_store' in services:
        global_bits = _add(global_bits, 'S09', INFORMATION)
    if any(n == 'mcu' or n.startswith('mcu ') for n in names):
        global_bits = _add(global_bits, 'S06', INFORMATION)
    if 'maintenance.ambient_sensor' in services and temperature_sensors:
        # Do not equate every generic temperature probe with an ambient probe.
        global_bits = _add(global_bits, 'O05', INFORMATION)
    if 'maintenance.guided_service' in services:
        global_bits = _add(global_bits, 'O06', USER)
    # Features without positive evidence and ALWAYS_HIDDEN IDs remain NONE.
    return MaintenanceSnapshot(state.epoch, tuple(results), global_bits,
                               id(settings), tuple(sorted(services)))
