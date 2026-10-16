"""Operator-declared physical roles for generic Klipper actuator tests.

Nothing here infers a buzzer or light from a pin or object name. On READY
we validate exact Klipper objects and safe effective settings; no I/O occurs.
"""
from collections.abc import Mapping
from maintenance_hh_leds import auto_happy_hare_led_services
from maintenance_thermal_profiles import profile_services
from maintenance_resonance import resonance_services
from maintenance_filament import filament_services
from maintenance_auxiliary import auxiliary_services
import json
import math
from pathlib import Path
import re

_SAFE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
_LED_TYPES = ('led', 'neopixel', 'dotstar', 'pca9632')
_KINDS = {'visual': ('output_pin',), 'audible': ('pwm_cycle_time',),
          'fan': ('fan_generic',), 'led': _LED_TYPES}
MAX_BYTES = 2048
MAX_ACTUATORS = 16


def default_path():
    return Path.home() / '.config' / 'Petrel' / 'maintenance-test-profiles.json'


def _parse_object(role, name):
    if not isinstance(role, str) or not isinstance(name, str):
        return None
    parts = name.split(' ')
    if (len(parts) != 2 or parts[0] not in _KINDS.get(role, ())
            or not _SAFE.fullmatch(parts[1])):
        return None
    # Effective pwm_cycle_time config sections are lowercase. Raw Klipper
    # config is checked separately for the case-sensitive SET_PIN mux name.
    if parts[0] == 'pwm_cycle_time':
        return parts[0] + ' ' + parts[1].lower()
    return name


def read_profiles(path=None):
    """Accept only version-2 role mappings. Legacy and invalid files fail closed."""
    target = Path(path) if path is not None else default_path()
    try:
        if not target.is_file() or target.stat().st_size > MAX_BYTES:
            return ()
        raw = json.loads(target.read_text(encoding='utf-8'))
        if (not isinstance(raw, dict) or set(raw) != {'version', 'actuators'}
                or type(raw['version']) is not int or raw['version'] != 2
                or not isinstance(raw['actuators'], list)
                or len(raw['actuators']) > MAX_ACTUATORS):
            return ()
        result, seen = [], set()
        for item in raw['actuators']:
            if not isinstance(item, dict) or set(item) != {'object', 'role'}:
                return ()
            name = _parse_object(item['role'], item['object'])
            if name is None or name.casefold() in seen:
                return ()
            seen.add(name.casefold())
            result.append((item['role'], name))
        return tuple(result)
    except (OSError, ValueError, TypeError, UnicodeError):
        return ()


def approved_integrations(state, profiles):
    """Per-object positive role evidence; no guessed names or writable grants."""
    if (not getattr(state, 'ready', False) or not isinstance(profiles, tuple)
            or len(profiles) > MAX_ACTUATORS):
        return ()
    settings, names = state.settings, set(state.objects)
    if not isinstance(settings, Mapping):
        return ()
    services, seen = [], set()
    for item in profiles:
        if not isinstance(item, tuple) or len(item) != 2:
            return ()
        role, raw_name = item
        name = _parse_object(role, raw_name)
        if name is None or name.casefold() in seen:
            return ()
        seen.add(name.casefold())
        cfg = settings.get(name)
        if not isinstance(cfg, Mapping):
            continue
        if role == 'audible':
            # pwm_cycle_time has no status readback. Only a declared OFF
            # default is allowed; it is not proof the live pin is OFF.
            scale = cfg.get('scale')
            start, stop = cfg.get('value'), cfg.get('shutdown_value')
            if (isinstance(cfg.get('pin'), str) and cfg['pin'].strip()
                    and type(scale) in (int, float) and math.isfinite(scale)
                    and 0 < scale <= 2
                    and type(start) in (int, float) and math.isfinite(start) and start == 0
                    and type(stop) in (int, float) and math.isfinite(stop) and stop == 0):
                services.append('maintenance.audible:' + name)
        elif role == 'visual':
            scale = cfg.get('scale', 1)
            if (name in names and isinstance(cfg.get('pin'), str)
                    and cfg['pin'].strip()
                    and cfg.get('pwm') in (True, 'True', 'true', '1', 1)
                    and type(scale) in (int, float) and scale == 1):
                services.append('maintenance.visual:' + name)
        elif role == 'fan':
            if name in names:
                services.append('maintenance.safe_fan:' + name)
        elif role == 'led':
            if name in names:
                services.append('maintenance.safe_led:' + name)
    # Named Happy Hare objects provide explicit LED semantics: discovery may
    # register them without a local machine-specific role declaration.
    # The physical runner still requires fresh evidence and user consent.
    services.extend(auto_happy_hare_led_services(state))
    services.extend(profile_services(state))
    services.extend(resonance_services(state))
    services.extend(filament_services(state))
    services.extend(auxiliary_services(state))
    return tuple(dict.fromkeys(services))
