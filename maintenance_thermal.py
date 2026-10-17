"""Pure thermal contracts and bounded timestamped measurements. No I/O."""
from collections.abc import Mapping
from dataclasses import dataclass
import math
import re

ACTIVE = ('H01', 'H05', 'H06', 'H07', 'H08', 'H09', 'H13')
PID = ('H02', 'H03', 'H04')
_NAME = re.compile(r'(?:extruder[0-9]*|heater_bed|heater_generic [A-Za-z][A-Za-z0-9_]{0,47})\Z')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def heater_name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError('unsafe_heater_identifier')
    # Klipper lookup_heater accepts the short name of heater_generic.
    return value.split(' ', 1)[-1]


@dataclass(frozen=True, slots=True)
class ThermalContract:
    device: str
    target: float
    ceiling: float
    duration: float
    min_temp: float
    max_temp: float

    @property
    def off(self):
        return 'SET_HEATER_TEMPERATURE HEATER=%s TARGET=0' % heater_name(self.device)

    @property
    def heat(self):
        return 'SET_HEATER_TEMPERATURE HEATER=%s TARGET=%.1f' % (
            heater_name(self.device), self.target)

    @property
    def script(self):
        # The OFF is in the same finite Klipper script. It does not depend
        # on Petrel continuing to poll or staying alive after dispatch.
        return '%s\nG4 P%d\nM400\n%s' % (self.heat, self.duration * 1000, self.off)


def contract(device, settings, status, feature, profile=None):
    heater_name(device)
    cfg = settings.get(device) if isinstance(settings, Mapping) else None
    live = status.get(device) if isinstance(status, Mapping) else None
    if not isinstance(cfg, Mapping) or not isinstance(live, Mapping):
        raise ValueError('heater_evidence_missing')
    for section, value in settings.items():
        if (isinstance(section, str) and section.lower() in
                ('gcode_macro set_heater_temperature', 'gcode_macro pid_calibrate',
                 'gcode_macro g4', 'gcode_macro m400')):
            raise ValueError('thermal_command_overridden')
    low, high = cfg.get('min_temp'), cfg.get('max_temp')
    if not all(number(v) for v in (low, high)) or low >= high:
        raise ValueError('heater_limits_unknown')
    if not isinstance(cfg.get('heater_pin'), str) or not cfg['heater_pin'].strip():
        raise ValueError('heater_pin_missing')
    if feature not in ACTIVE + PID:
        raise ValueError('unsupported_thermal_feature')
    # No generic chamber/dryer can be assigned a safe temperature from its
    # name. Require an explicit application-specific profile in a later layer.
    if device.startswith('heater_generic ') and profile is None:
        raise ValueError('generic_thermal_profile_required')
    target = ((60. if device == 'heater_bed' else 150.) if feature in PID
              else 45. if device == 'heater_bed' else 60.)
    ceiling = high  # Use Klipper's configured heater limit, not an extra overshoot margin
    duration = 120.
    if profile is not None:
        if (not isinstance(profile, tuple) or len(profile) not in (2, 3)
                or not all(number(v) for v in profile)):
            raise ValueError('invalid_thermal_profile')
        # Accept legacy (target, ceiling, duration) data without using the
        # retired Petrel-specific ceiling. New profiles carry target/duration.
        target, duration = profile[0], profile[-1]
        if not 30 <= duration <= 120:
            raise ValueError('invalid_thermal_profile')
    if not low < target < high:
        raise ValueError('thermal_test_outside_config_limits')
    temp, original, power = (live.get(k) for k in ('temperature', 'target', 'power'))
    if (not all(number(v) for v in (temp, original, power))
            or not low <= temp <= min(45., target - 10) or original != 0 or power != 0):
        raise ValueError('cold_idle_heater_required')
    # Every configured heater must positively report an OFF target and power.
    for name, other in settings.items():
        if isinstance(name, str) and _NAME.fullmatch(name) and isinstance(other, Mapping) and 'heater_pin' in other:
            values = status.get(name)
            if (not isinstance(values, Mapping)
                    or not number(values.get('target')) or values['target'] != 0
                    or not number(values.get('power')) or values['power'] != 0):
                raise ValueError('another_heater_active_or_unknown')
    return ThermalContract(device, target, ceiling, 900. if feature in PID else duration, low, high)


@dataclass(frozen=True, slots=True)
class Sample:
    eventtime: float
    temperature: float
    target: float
    power: float


def sample(reply, device):
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    values = status.get(device) if isinstance(status, Mapping) else None
    if not isinstance(values, Mapping):
        raise ValueError('thermal_sample_missing')
    fields = (result.get('eventtime'), *(values.get(k) for k in ('temperature', 'target', 'power')))
    if (not all(number(v) for v in fields) or fields[0] < 0
            or not 0 <= fields[3] <= 1):
        raise ValueError('thermal_sample_invalid')
    return Sample(*fields)


class ThermalSeries:
    """At most 256 samples; stale/duplicate/gapped series cannot imply PASS."""
    def __init__(self):
        self.samples = []

    def add(self, value):
        if not isinstance(value, Sample):
            raise ValueError('invalid_thermal_sample')
        if not all(number(v) for v in (value.eventtime, value.temperature, value.target, value.power)):
            raise ValueError('invalid_thermal_sample')
        if self.samples:
            gap = value.eventtime - self.samples[-1].eventtime
            if not 0 < gap <= 5:
                raise ValueError('stale_or_gapped_thermal_sample')
        if len(self.samples) >= 256:
            raise ValueError('thermal_sample_capacity')
        self.samples.append(value)

    def metrics(self, target):
        values = self.samples
        if len(values) < 3:
            raise ValueError('insufficient_thermal_samples')
        first, last = values[0], values[-1]
        span = last.eventtime - first.eventtime
        peak = max(v.temperature for v in values)
        reached = next((v for v in values if v.target == target and v.temperature >= target - 1), None)
        # Stability is evaluated only after 20 s settling and a complete
        # >=30 s tail, all at the expected target. Never include cooling.
        tail = [v for v in values if reached is not None
                and v.eventtime >= reached.eventtime + 20 and v.target == target]
        stable = bool(len(tail) >= 16 and tail[-1].eventtime - tail[0].eventtime >= 30)
        heating = [v for v in values if v.target == target]
        cooling = [v for v in values if v.target == 0]
        result = [('samples', len(values)), ('span_s', round(span, 2)),
                  ('rise_c', round(peak - first.temperature, 3))]
        if len(heating) >= 3:
            a, b = heating[0], heating[-1]
            result.append(('heating_c_per_s', round((b.temperature-a.temperature)/(b.eventtime-a.eventtime), 4)))
        if reached:
            result.extend((('time_to_target_s', round(reached.eventtime-first.eventtime, 2)),
                           ('overshoot_c', round(max(0, peak-target), 3))))
        if stable:
            result.append(('stability_peak_to_peak_c', round(
                max(v.temperature for v in tail)-min(v.temperature for v in tail), 3)))
        if len(cooling) >= 16 and cooling[-1].eventtime-cooling[0].eventtime >= 30:
            a, b = cooling[0], cooling[-1]
            result.append(('cooling_c_per_s', round((b.temperature-a.temperature)/(b.eventtime-a.eventtime), 4)))
        return tuple(result)

    def evaluate(self, feature, target):
        metrics = self.metrics(target)
        m = dict(metrics)
        if feature == 'H01':
            passed = m['rise_c'] >= 5
        elif feature == 'H05':
            passed = m.get('heating_c_per_s', 0) > 0
        elif feature == 'H06':
            passed = 'time_to_target_s' in m
        elif feature == 'H07':
            passed = 'overshoot_c' in m and m['overshoot_c'] <= 5
        elif feature == 'H08':
            passed = 'stability_peak_to_peak_c' in m and m['stability_peak_to_peak_c'] <= 2
        elif feature == 'H09':
            passed = m.get('cooling_c_per_s', 0) < 0
        elif feature == 'H13':
            # Normal limited heating response only. Never induce a fault.
            passed = m['rise_c'] >= 5 and m.get('heating_c_per_s', 0) > 0
        else:
            raise ValueError('unsupported_thermal_metric')
        primary = {'H01': 'rise_c', 'H05': 'heating_c_per_s',
                   'H06': 'time_to_target_s', 'H07': 'overshoot_c',
                   'H08': 'stability_peak_to_peak_c', 'H09': 'cooling_c_per_s',
                   'H13': 'rise_c'}[feature]
        metrics = tuple(sorted(metrics, key=lambda pair: pair[0] != primary))
        return passed, metrics


def pid_evidence(config, device):
    """Only fresh Klipper pending parameters, never console text or HTTP OK."""
    if not isinstance(config, Mapping) or config.get('save_config_pending') is not True:
        return ()
    items = config.get('save_config_pending_items')
    values = items.get(device) if isinstance(items, Mapping) else None
    if not isinstance(values, Mapping) or values.get('control') != 'pid':
        return ()
    result = []
    # Klipper ConfigAutoSave.set() preserves option case in
    # save_config_pending_items: pid_Kp / pid_Ki / pid_Kd.
    # Use lowercase *only* for our existing LCD/report evidence labels.
    for key in ('pid_Kp', 'pid_Ki', 'pid_Kd'):
        value = values.get(key)
        if type(value) not in (int, float, str):
            return ()
        try:
            value = float(value)
        except (ValueError, TypeError):
            return ()
        if not math.isfinite(value) or value <= 0:
            return ()
        result.append((key.lower(), value))
    return tuple(result)
