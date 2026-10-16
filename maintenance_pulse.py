"""Bounded hardware pulse programs for user-observed Maintenance tests.

This is a pure compiler, NEVER a command dispatcher. Unknown, dynamic, or
unverifiable hardware is rejected. Commanded PWM is not measured RPM.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import math
import re

from maintenance_guided import _trusted_target

_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
_TONE = 0.000625  # 1600 Hz; one 150-ms chirp
_PULSE_MS = {'F01': 950, 'F04': 950, 'O03': 850,
             'O04': 750, 'S18': 150}


@dataclass(frozen=True, slots=True)
class PulseProgram:
    feature_id: str
    device: str | None
    read_path: str
    object_name: str
    original: tuple
    stimulus: str
    restore: str
    script: str
    duration_ms: int
    observation: str


def _unit(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 <= value <= 1)


def _name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError('unsafe_config_identifier')
    return value


def _command(name, value):
    return 'SET_LED LED=%s RED=%.4f GREEN=%.4f BLUE=%.4f%s SYNC=0' % (
        name, value[0], value[1], value[2],
        ' WHITE=%.4f' % value[3] if value[3] else '')


def compile_pulse(row, snapshot, status, settings, *, pin_command_name=None):
    """Compile a short, self-restoring script from *fresh* printer status.

    The caller must independently verify live safety and target discovery
    at dispatch time. A status mapping from printer.objects.query is required;
    an omitted/unknown baseline blocks rather than guessing an off state.
    """
    if not _trusted_target(row, snapshot):
        raise ValueError('untrusted_guided_target')
    if (not isinstance(status, Mapping) or not isinstance(settings, Mapping)
            or row.epoch != snapshot.epoch
            or row.config_marker != snapshot.config_marker):
        raise ValueError('invalid_or_stale_evidence')
    feature = row.feature_id
    target = row.device
    cfg = settings.get(target or '', {})
    current = status.get(target or '', {})
    if feature == 'S18':
        if (not isinstance(target, str) or
                not target.startswith('pwm_cycle_time ')
                or 'maintenance.audible:' + target not in snapshot.service_key):
            raise ValueError('audible_target_not_authorized')
        cfg = settings.get(target)
        current = status.get(target)
    if not isinstance(cfg, Mapping) or (feature != 'S18' and not isinstance(current, Mapping)):
        raise ValueError('target_state_or_config_unknown')

    if feature in ('F01', 'F04'):
        original = current.get('speed')
        if not _unit(original):
            raise ValueError('fan_speed_unavailable')
        if feature == 'F01':
            start = 'M106 S191'  # 75% commanded, never inferred tachometer RPM
            restore = 'M106 S%d' % round(original * 255)
            observation = 'Did the part-cooling fan rotate during the pulse?'
        else:
            fan_name = _name(target[len('fan_generic '):])
            if ('template' in current and current['template']):
                raise ValueError('fan_template_active')
            start = 'SET_FAN_SPEED FAN=%s SPEED=0.75' % fan_name
            restore = 'SET_FAN_SPEED FAN=%s SPEED=%.4f' % (fan_name, original)
            observation = 'Did the selected generic fan rotate?'
        evidence = (float(original),)
        object_name = target
    elif feature == 'O03':
        if (not isinstance(target, str) or not target.startswith('output_pin ')
                or 'maintenance.visual:' + target not in snapshot.service_key
                or cfg.get('pwm') not in (True, 'True', 'true', '1', 1)):
            raise ValueError('visual_pwm_unverified')
        scale = cfg.get('scale', 1)
        value = current.get('value')
        if not _unit(value) or type(scale) not in (int, float) or scale != 1:
            raise ValueError('case_light_original_unknown')
        configured = _name(target.split(' ', 1)[1])
        command_name = _name(pin_command_name)
        if command_name.casefold() != configured.casefold():
            raise ValueError('visual_command_name_mismatch')
        # Never choose a stimulus identical to the captured baseline.
        stimulus = .7 if value < .5 else .2
        start = 'SET_PIN PIN=%s VALUE=%.4f' % (command_name, stimulus)
        restore = 'SET_PIN PIN=%s VALUE=%.4f' % (command_name, value)
        evidence = (float(value),)
        object_name = target
        observation = 'Did the selected visual output change and restore?'
    elif feature == 'O04':
        kind, name = target.split(' ', 1)
        if kind not in ('led', 'neopixel', 'dotstar', 'pca9632'):
            raise ValueError('led_type_unsupported')
        name = _name(name)
        colors = current.get('color_data')
        # Multiple LEDs or templates cannot be restored by one safe command.
        if not isinstance(colors, (tuple, list)) or len(colors) != 1:
            raise ValueError('led_baseline_unavailable')
        raw = colors[0]
        if not isinstance(raw, (tuple, list)) or len(raw) != 4 or not all(_unit(v) for v in raw):
            raise ValueError('led_baseline_invalid')
        original = tuple(float(v) for v in raw)
        has_white = (bool(cfg.get('white_pin')) if kind == 'led'
                     else 'W' in str(cfg.get('color_order', 'RGB')).upper())
        if original[3] and not has_white:
            raise ValueError('led_white_not_supported')
        start = _command(name, (.0, .4, .0, .0))
        restore = _command(name, original)
        evidence = original
        object_name = target
        observation = 'Did the single LED briefly become green?'
    elif feature == 'S18':
        # pwm_cycle_time has NO get_status() and no live readback. The only
        # allowed baseline is an explicit OFF config, not invented telemetry.
        # Abort if a runtime value happens to be supplied and reports ON.
        if (cfg.get('value') != 0 or cfg.get('shutdown_value') != 0
                or not isinstance(cfg.get('pin'), str) or not cfg['pin'].strip()):
            raise ValueError('buzzer_default_off_config_required')
        if isinstance(current, Mapping) and 'value' in current and current['value'] != 0:
            raise ValueError('buzzer_reports_active')
        scale = cfg.get('scale')
        if type(scale) not in (int, float) or not math.isfinite(scale) or not 0 < scale <= 2:
            raise ValueError('invalid_buzzer_scale')
        name = _name(target.split(' ', 1)[1])
        command_name = _name(pin_command_name)
        if command_name.casefold() != name.casefold():
            raise ValueError('buzzer_gcode_name_mismatch')
        start = 'SET_PIN PIN=%s VALUE=%.4f CYCLE_TIME=%.8f' % (
            command_name, scale * .25, _TONE)
        restore = 'SET_PIN PIN=%s VALUE=0' % command_name
        evidence = (0.0,)  # Configured OFF, NOT observed live output state.
        object_name = target
        observation = 'Did the selected audible output sound and stop?'
    else:
        raise ValueError('unsupported_feature')

    duration = _PULSE_MS[feature]
    if feature == 'S18':
        # Start with a deterministic OFF command; finish in the same bounded
        # script. This still cannot prove a restoration without a sensor.
        script = '%s\nG4 P50\n%s\nG4 P%d\n%s' % (
            restore, start, duration, restore)
        duration += 50
    else:
        script = '%s\nG4 P%d\n%s' % (start, duration, restore)
    if '\r' in script or len(script) > 300:
        raise ValueError('unsafe_program')
    from urllib.parse import quote
    endpoint = ('' if feature == 'S18'
                else '/printer/objects/query?' + quote(object_name, safe=''))
    return PulseProgram(feature, row.device, endpoint, object_name, evidence,
                        start, restore, script, duration, observation)


def restored(program, status):
    """Return True only when *reported state* matches the captured original."""
    if not isinstance(program, PulseProgram) or not isinstance(status, Mapping):
        return False
    state = status.get(program.object_name)
    if not isinstance(state, Mapping):
        return False
    if program.feature_id in ('F01', 'F04'):
        value = state.get('speed')
        return _unit(value) and abs(value - program.original[0]) <= .015
    if program.feature_id == 'O03':
        value = state.get('value')
        return _unit(value) and abs(value - program.original[0]) <= .015
    if program.feature_id == 'O04':
        colors = state.get('color_data')
        return (isinstance(colors, (list, tuple)) and len(colors) == 1
                and isinstance(colors[0], (list, tuple))
                and len(colors[0]) == 4
                and all(_unit(value) and abs(value - old) <= .015
                        for value, old in zip(colors[0], program.original)))
    return False
