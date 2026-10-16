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
_MAX_LED_CHAIN = 32  # bounded status, script length and restoration footprint
_MAX_LED_SCRIPT = 7200
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
    managed_hh: bool = False


def _unit(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 <= value <= 1)


def _name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError('unsafe_config_identifier')
    return value


def _command(name, value, *, index, transmit, white):
    return ('SET_LED LED=%s RED=%.4f GREEN=%.4f BLUE=%.4f%s '
            'INDEX=%d TRANSMIT=%d SYNC=0') % (
        name, value[0], value[1], value[2],
        (' WHITE=%.4f' % value[3]) if white else '',
        index, int(transmit))


def _led_managed(settings, target):
    """Refuse known independently managed MMU and led_effect chains.

    MMU action=idle does not establish exclusive ownership of MMU LEDs.
    """
    kind, _, name = target.partition(' ')
    reference = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(kind) + r':' +
                           re.escape(name) + r'(?![A-Za-z0-9_])', re.I)
    for section, cfg in settings.items():
        if not isinstance(section, str) or not isinstance(cfg, Mapping):
            continue
        if section.startswith('mmu_leds '):
            fields = ('exit_leds', 'entry_leds', 'status_leds', 'logo_leds')
        elif section.startswith(('led_effect ', '_led_effect ', 'mmu_led_effect ')):
            fields = ('leds',)
        else:
            continue
        for field in fields:
            value = cfg.get(field)
            if isinstance(value, str) and reference.search(value):
                return True
    return False


def _led_stimulus(original):
    # Choose a low-current visible color different from the captured state.
    options = ((0., .35, 0., 0.), (0., 0., .35, 0.), (.35, 0., 0., 0.))
    for option in options:
        if any(abs(a - b) >= .1 for a, b in zip(original, option)):
            return option
    return options[-1]


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
        if _led_managed(settings, target):
            raise ValueError('led_managed_by_another_controller')
        if (not isinstance(colors, (tuple, list))
                or not 1 <= len(colors) <= _MAX_LED_CHAIN):
            raise ValueError('led_chain_length_unknown_or_exceeds_limit')
        count = cfg.get('chain_count', 1)
        if type(count) is not int or count != len(colors):
            raise ValueError('led_chain_count_mismatch')
        has_white = bool(cfg.get('white_pin')) if kind == 'led' else False
        if kind != 'led':
            order = cfg.get('color_order', 'RGB')
            if not isinstance(order, str):
                raise ValueError('led_color_order_unknown')
            orders = [s.strip().upper() for s in order.split(',')]
            if (not orders or len(orders) not in (1, len(colors))
                    or any(not s or set(s) not in
                           (set('RGB'), set('RGBW')) or len(s) not in (3, 4)
                           for s in orders)):
                raise ValueError('led_color_order_unsupported')
            if len({('W' in s) for s in orders}) != 1:
                raise ValueError('mixed_rgb_rgbw_unsupported')
            has_white = 'W' in orders[0]
        originals = []
        for raw in colors:
            if (not isinstance(raw, (tuple, list)) or len(raw) != 4
                    or not all(_unit(v) for v in raw)):
                raise ValueError('led_baseline_invalid')
            rgba = tuple(float(v) for v in raw)
            if rgba[3] and not has_white:
                raise ValueError('led_white_not_supported')
            originals.append(rgba)
        original = tuple(originals)
        stimuli = tuple(_led_stimulus(color) for color in original)
        # Batch changes; only the last indexed command transmits a frame.
        start = '\n'.join(_command(name, value, index=i,
                                  transmit=i == len(stimuli), white=has_white)
                          for i, value in enumerate(stimuli, 1))
        restore = '\n'.join(_command(name, value, index=i,
                                    transmit=i == len(original), white=has_white)
                            for i, value in enumerate(original, 1))
        evidence = original
        object_name = target
        observation = 'Did every LED in the selected chain briefly change?'
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
    if '\r' in script or len(script) > (_MAX_LED_SCRIPT if feature == 'O04' else 300):
        raise ValueError('unsafe_program')
    from urllib.parse import quote
    endpoint = ('' if feature == 'S18'
                else '/printer/objects/query?' + quote(object_name, safe=''))
    return PulseProgram(feature, row.device, endpoint, object_name, evidence,
                        start, restore, script, duration, observation)



def mmu_led_owner(settings, target):
    """Return one Happy Hare owner for a physical chain, never guess ownership.

    The only supported contract is one complete physical chain mapped exactly
    to one MMU unit's exit segment. Other layouts remain fail-closed.
    """
    if not isinstance(settings, Mapping) or not isinstance(target, str):
        return None
    kind, sep, name = target.partition(' ')
    if not sep or kind not in ('neopixel', 'dotstar', 'led', 'pca9632'):
        return None
    # Happy Hare uses "neopixel:mmu_leds (1-4)" syntax for its exit segment.
    reference = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(kind) +
                           ':' + re.escape(name) + r'(?![A-Za-z0-9_])', re.I)
    owners = []
    for section, cfg in settings.items():
        if not isinstance(section, str) or not section.startswith('mmu_leds '):
            continue
        if not isinstance(cfg, Mapping):
            raise ValueError('mmu_led_config_unknown')
        if any(isinstance(cfg.get(field), str) and reference.search(cfg[field])
               for field in ('exit_leds', 'entry_leds', 'status_leds', 'logo_leds')):
            owners.append((section, cfg))
    if not owners:
        return None
    if len(owners) != 1:
        raise ValueError('multiple_mmu_led_owners')
    section, cfg = owners[0]
    unit = _name(section.split(' ', 1)[1])
    matched = re.fullmatch(re.escape(kind) + ':' + re.escape(name) +
                           r' \((1)-([1-9][0-9]?)\)', str(cfg.get('exit_leds', '')))
    if (matched is None or
            any(isinstance(cfg.get(field), str) and reference.search(cfg[field])
                for field in ('entry_leds', 'status_leds', 'logo_leds'))):
        raise ValueError('mmu_led_partial_or_shared_chain')
    return section, unit, int(matched.group(2))


def compile_mmu_led_pulse(row, snapshot, physical, settings, mmu_led, mmu):
    """Use Happy Hare's *own* expiring effect; do not disable its LED manager.

    MMU_SET_LED ... DURATION=1 goes through HH's LED ownership pipeline and
    returns to its current *policy* on HH's reactor timer (even if Petrel
    disconnects). Dynamic effects mean exact original pixel RGB cannot be
    promised or verified; only an operator observation is accepted.
    """
    if not _trusted_target(row, snapshot) or row.feature_id != 'O04':
        raise ValueError('untrusted_mmu_led_target')
    if (row.epoch != snapshot.epoch or row.config_marker != snapshot.config_marker
            or not isinstance(physical, Mapping)
            or not isinstance(settings, Mapping)
            or not isinstance(mmu_led, Mapping) or not isinstance(mmu, Mapping)):
        raise ValueError('mmu_led_evidence_unavailable')
    owner = mmu_led_owner(settings, row.device)
    if owner is None:
        raise ValueError('mmu_led_owner_missing')
    section, unit, count = owner
    cfg = settings.get(row.device)
    colors = physical.get(row.device, {}).get('color_data')
    if (not isinstance(cfg, Mapping) or type(cfg.get('chain_count')) is not int
            or cfg['chain_count'] != count
            or not 1 <= count <= _MAX_LED_CHAIN
            or not isinstance(colors, (list, tuple)) or len(colors) != count
            or any(not isinstance(pixel, (list, tuple)) or len(pixel) != 4
                   or not all(_unit(c) for c in pixel) for pixel in colors)):
        raise ValueError('mmu_led_physical_chain_unverified')
    if (mmu_led.get('enabled') is not True
            or type(mmu_led.get('animation')) is not bool
            or str(mmu.get('action', '')).lower() != 'idle'):
        raise ValueError('mmu_led_not_idle_or_enabled')
    # Refuse standalone effects on the PHYSICAL chain. HH's own generated
    # animations normally act on its virtual segment and are HH-managed.
    kind, _, name = row.device.partition(' ')
    direct = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(kind) + ':' +
                        re.escape(name) + r'(?![A-Za-z0-9_])', re.I)
    for section_name, effect in settings.items():
        if (isinstance(section_name, str)
                and section_name.startswith(('led_effect ', '_led_effect '))
                and isinstance(effect, Mapping)
                and isinstance(effect.get('leds'), str)
                and direct.search(effect['leds'])):
            raise ValueError('independent_led_effect_owner')
    script = ('MMU_SET_LED UNIT=%s EXIT_EFFECT=(0,0.35,0) '
              'DURATION=1 FADETIME=0' % unit)
    from urllib.parse import quote
    return PulseProgram(
        'O04', row.device, '/printer/objects/query?' + quote(section, safe=''),
        section, (True, mmu_led['animation']),
        script, 'Happy Hare timed return to default (not a SET_LED command)',
        script, 1500,
        'Did all MMU exit LEDs briefly change and return to Happy Hare control?',
        managed_hh=True)


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
    if program.managed_hh:
        # This verifies HH's controller policy is still active, NOT an
        # animated LED's exact RGB baseline or the HH timer's completion.
        return (program.feature_id == 'O04'
                and state.get('enabled') is program.original[0]
                and state.get('animation') is program.original[1])
    if program.feature_id == 'O04':
        colors = state.get('color_data')
        return (isinstance(colors, (list, tuple))
                and len(colors) == len(program.original)
                and all(isinstance(rgba, (list, tuple)) and len(rgba) == 4
                        and all(_unit(value) and abs(value - old) <= .015
                                for value, old in zip(rgba, baseline))
                        for rgba, baseline in zip(colors, program.original)))
    return False
