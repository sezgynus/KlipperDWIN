"""Capabilities and limits derived from Klipper's effective configuration."""
from dataclasses import dataclass
import math
import re


def number(settings, key):
    value = float(settings[key])
    if not math.isfinite(value):
        raise ValueError('Invalid configured limit: ' + key)
    return value


@dataclass(frozen=True)
class HeaterLimits:
    name: str
    minimum: float
    maximum: float
    min_extrude_temp: float = 0
    max_extrude_distance: float = 0

    @classmethod
    def from_settings(cls, name, settings, extruder=False):
        minimum, maximum = number(settings, 'min_temp'), number(settings, 'max_temp')
        if minimum >= maximum:
            raise ValueError('Invalid heater temperature range')
        mintemp = number(settings, 'min_extrude_temp') if extruder else 0
        distance = number(settings, 'max_extrude_only_distance') if extruder else 0
        if extruder and (not minimum <= mintemp <= maximum or distance < 0):
            raise ValueError('Invalid extrusion limits')
        return cls(name, minimum, maximum, mintemp, distance)

    def validate_target(self, target):
        target = float(target)
        # Klipper treats zero as off, even when min_temp is positive.
        if not math.isfinite(target) or (target != 0 and not self.minimum <= target <= self.maximum):
            raise ValueError('Temperature target outside configured range')
        return target


@dataclass(frozen=True)
class PrinterCapabilities:
    hotends: tuple = ()
    active_hotend: HeaterLimits = None
    bed: HeaterLimits = None
    fan: bool = False
    probe: bool = False
    bed_mesh: bool = False
    axis_minimum: tuple = (0, 0, 0)
    axis_maximum: tuple = (0, 0, 0)

    screws_tilt_adjust: bool = False
    case_light: bool = False

    @classmethod
    def from_state(cls, state):
        if not state.ready:
            return cls()
        objects = set(state.objects)
        settings = state.settings
        names = sorted((name for name in objects if re.fullmatch(r'extruder\d*', name)),
                       key=lambda name: int(name[8:] or 0))
        hotends = tuple(HeaterLimits.from_settings(name, settings[name], True) for name in names)
        active_name = state.status['toolhead'].get('extruder')
        if active_name is None and len(hotends) == 1:
            active_name = hotends[0].name
        active = next((heater for heater in hotends if heater.name == active_name), None)
        if hotends and active is None:
            raise ValueError('Active extruder is not identified')
        bed = HeaterLimits.from_settings('heater_bed', settings['heater_bed']) if 'heater_bed' in objects else None
        toolhead = state.status['toolhead']
        minimum = tuple(float(value) for value in toolhead['axis_minimum'][:3])
        maximum = tuple(float(value) for value in toolhead['axis_maximum'][:3])
        if len(minimum) != 3 or len(maximum) != 3 or any(
                not math.isfinite(low) or not math.isfinite(high) or low > high
                for low, high in zip(minimum, maximum)):
            raise ValueError('Invalid axis range')
        return cls(hotends, active, bed, 'fan' in objects,
                   'probe' in objects or 'bltouch' in objects,
                   'bed_mesh' in objects, minimum, maximum,
                   'screws_tilt_adjust' in objects and 'screws_tilt_adjust' in settings,
                   'output_pin case_light' in objects)

    @property
    def has_heaters(self):
        return bool(self.hotends or self.bed)

    @property
    def build_size(self):
        return tuple(high - low for low, high in zip(self.axis_minimum, self.axis_maximum))
