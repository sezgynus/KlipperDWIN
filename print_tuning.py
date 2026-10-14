"""Capability-derived print settings and explicit, validated command routing."""
from dataclasses import dataclass
from collections.abc import Mapping
import math

JOB_PINS = (
    ('Turn_OFF_Heaters_After_Job', 'Heaters off'),
    ('Disable_Motors_After_Job', 'Motors off'),
    ('Power_OFF_Printer_After_Job', 'Printer power off'),
)
JOB_OBJECTS = tuple('output_pin ' + name for name, _ in JOB_PINS)

@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str
    value: float
    minimum: float
    maximum: float
    step: float = 1
    decimals: int = 0
    unit: str = ''
    toggle: bool = False


def settings(printer):
    state = printer.state
    if not state.ready:
        return ()
    data, caps = state.status, printer.capabilities
    result = []
    def add(key, label, group, value, low, high, step=1, decimals=0, unit='', toggle=False):
        try:
            value = float(value)
            if not math.isfinite(value):
                return
        except (ValueError, TypeError):
            return
        result.append(Setting(key, label, group, value, low, max(high, value), step, decimals, unit, toggle))
    gcm = data.get('gcode_move', {})
    add('speed', 'Speed', 'PRINT', gcm.get('speed_factor', 1)*100, 1, 999, unit='%')
    if caps.active_hotend:
        add('flow', 'Flow', 'PRINT', gcm.get('extrude_factor', 1)*100, 1, 999, unit='%')
    if caps.fan:
        add('fan', 'Fan', 'PRINT', data.get('fan', {}).get('speed', 0)*100, 0, 100, unit='%')
    if caps.active_hotend:
        add('nozzle@'+caps.active_hotend.name, 'Nozzle', 'PRINT', data[caps.active_hotend.name]['target'], 0, caps.active_hotend.maximum, unit='C')
    if caps.bed:
        add('bed', 'Bed', 'PRINT', data['heater_bed']['target'], 0, caps.bed.maximum, unit='C')
    if printer.HAS_ZOFFSET_ITEM:
        add('z', 'Z offset', 'PRINT', printer.BABY_Z_VAR, printer.Z_PROBE_OFFSET_RANGE_MIN, printer.Z_PROBE_OFFSET_RANGE_MAX, .01, 2, 'mm')
    toolhead = data.get('toolhead', {})
    if 'square_corner_velocity' in toolhead:
        add('scv', 'SCV', 'MOTION', toolhead['square_corner_velocity'], 0, 100, .1, 1, 'mm/s')
    if 'minimum_cruise_ratio' in toolhead:
        add('cruise', 'Min cruise ratio', 'MOTION', toolhead['minimum_cruise_ratio']*100, 0, 99, 1, 0, '%')
    if caps.active_hotend:
        hotend = caps.active_hotend.name
        raw = data.get(hotend, {})
        if 'pressure_advance' in raw:
            add('pa@'+hotend, 'Pressure advance', 'EXTRUSION', raw['pressure_advance'], 0, 1, .001, 3)
        if 'smooth_time' in raw:
            add('smooth@'+hotend, 'PA smooth time', 'EXTRUSION', raw['smooth_time'], .001, .2, .001, 3, 's')
    if 'firmware_retraction' in state.objects and 'firmware_retraction' in state.settings:
        raw = data.get('firmware_retraction', {})
        for field, label, step, decimals, unit, low, high in (
            ('retract_length', 'Retract length', .1, 1, 'mm', 0, 20),
            ('retract_speed', 'Retract speed', 1, 0, 'mm/s', 1, 100),
            ('unretract_extra_length', 'Unretract extra', .1, 1, 'mm', 0, 20),
            ('unretract_speed', 'Unretract speed', 1, 0, 'mm/s', 1, 100)):
            if field in raw:
                add(field, label, 'EXTRUSION', raw[field], low, high, step, decimals, unit)
    for name, label in JOB_PINS:
        obj = 'output_pin '+name
        config = state.settings.get(obj)
        raw = data.get(obj, {})
        if obj in state.objects and isinstance(config, Mapping) and not config.get('pwm', False) and raw.get('value') in (0, 1):
            add('pin@'+name, label, 'AFTER JOB', raw['value'], 0, 1, toggle=True)
    return tuple(result)


def set_value(printer, key, value, report_error=True):
    setting = next((s for s in settings(printer) if s.key == key), None)
    if setting is None or printer.connection_error:
        raise ValueError('Print setting is unavailable')
    value = float(value)
    if not math.isfinite(value) or not setting.minimum <= value <= setting.maximum:
        raise ValueError('Print setting is outside its range')
    kwargs = {} if report_error else {'report_error': False}
    send = lambda script: printer.sendGCode(script, **kwargs)
    if key == 'speed': return printer.set_feedrate(value, **kwargs)
    if key == 'flow': return send('M221 S{:g}'.format(value))
    if key == 'fan': return printer.setFanSpeed(value, **kwargs)
    if key.startswith('nozzle@'):
        return printer.setExtTemp(value, **kwargs)
    if key == 'bed': return printer.setBedTemp(value, **kwargs)
    if key == 'z': return printer.setZOffset(value, **kwargs)
    if key in ('scv', 'cruise'):
        return printer.set_motion_limit('square_corner_velocity' if key == 'scv' else 'minimum_cruise_ratio', value if key == 'scv' else value/100, **kwargs)
    if key.startswith(('pa@', 'smooth@')):
        argument = 'ADVANCE' if key.startswith('pa@') else 'SMOOTH_TIME'
        return send('SET_PRESSURE_ADVANCE EXTRUDER={} {}={:g}'.format(key.split('@')[1], argument, value))
    if key in ('retract_length', 'retract_speed', 'unretract_extra_length', 'unretract_speed'):
        return send('SET_RETRACTION {}={:g}'.format(key.upper(), value))
    if key.startswith('pin@'):
        if value not in (0, 1): raise ValueError('Digital output must be zero or one')
        return send('SET_PIN PIN={} VALUE={}'.format(key.split('@')[1], int(value)))
    raise ValueError('Unknown print setting')


def layers(printer):
    info = printer.state.status.get('print_stats', {}).get('info', {})
    if not isinstance(info, Mapping):
        return None
    current, total = info.get('current_layer'), info.get('total_layer')
    if (isinstance(current, int) and not isinstance(current, bool) and isinstance(total, int)
            and not isinstance(total, bool) and total > 0 and 0 <= current <= total):
        return current, total
    return None
