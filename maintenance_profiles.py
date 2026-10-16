"""Explicit opt-in safety profiles for optional Maintenance actuators.

One tiny configuration is read on Klipper READY, never from the UI hot path.
No output is ever approved by its name alone: the operator's allowlist,
the actual queryable objects (where applicable) and safe effective config must agree.
"""
from collections.abc import Mapping
import json
import math
from pathlib import Path
import re

_SAFE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
_LED_TYPES = ('led', 'neopixel', 'dotstar', 'pca9632')
MAX_BYTES = 2048


def default_path():
    return Path.home() / '.config' / 'Petrel' / 'maintenance-test-profiles.json'


def read_profiles(path=None):
    """Invalid or missing opt-in is disabled; never log its contents."""
    target = Path(path) if path is not None else default_path()
    try:
        if not target.is_file() or target.stat().st_size > MAX_BYTES:
            return ()
        raw = json.loads(target.read_text(encoding='utf-8'))
        if (not isinstance(raw, dict) or set(raw) - {
                'version', 'case_light', 'buzzer_output',
                'fan_generic_output', 'led_output'}
                or type(raw.get('version')) is not int or raw['version'] != 1
                or type(raw.get('case_light', False)) is not bool):
            return ()
        buzzer = raw.get('buzzer_output', '')
        if not isinstance(buzzer, str) or (buzzer and not _SAFE.fullmatch(buzzer)):
            return ()
        generic = raw.get('fan_generic_output', '')
        led = raw.get('led_output', '')
        if not isinstance(generic, str) or (generic and not _SAFE.fullmatch(generic)):
            return ()
        if not isinstance(led, str):
            return ()
        if led:
            parts = led.split(' ', 1)
            if len(parts) != 2 or parts[0] not in _LED_TYPES or not _SAFE.fullmatch(parts[1]):
                return ()
        return (bool(raw.get('case_light', False)), buzzer, generic, led)
    except (OSError, ValueError, TypeError, UnicodeError):
        return ()


def approved_integrations(state, profiles):
    """Return positive, specific service keys only; never writable targets."""
    if (not getattr(state, 'ready', False)
            or not isinstance(profiles, tuple) or len(profiles) not in (2, 4)):
        return ()
    allow_case, buzzer = profiles[:2]
    generic, led = profiles[2:] if len(profiles) == 4 else ('', '')
    settings, names = state.settings, set(state.objects)
    if not isinstance(settings, Mapping):
        return ()
    services = []
    if allow_case is True and 'output_pin case_light' in names:
        cfg = settings.get('output_pin case_light', {})
        if isinstance(cfg, Mapping):
            scale = cfg.get('scale', 1)
            if (cfg.get('pwm') in (True, 'True', 'true', '1', 1)
                    and type(scale) in (float, int) and scale == 1):
                services.append('maintenance.safe_pin:output_pin case_light')
    if isinstance(buzzer, str) and _SAFE.fullmatch(buzzer):
        name = 'pwm_cycle_time ' + buzzer
        cfg = settings.get(name, {})
        # Klipper's pwm_cycle_time is a config-only pin and does not
        # implement get_status(): it is absent from printer.objects.list.
        # Admit ONLY an exact opt-in with an explicit safe default-off config;
        # this is NOT proof of its unknown live output value.
        if isinstance(cfg, Mapping):
            scale = cfg.get('scale')
            start = cfg.get('value')
            stop = cfg.get('shutdown_value')
            pin = cfg.get('pin')
            if (isinstance(pin, str) and bool(pin.strip())
                    and type(scale) in (float, int) and math.isfinite(scale)
                    and 0 < scale <= 2
                    and type(start) in (float, int) and start == 0
                    and type(stop) in (float, int) and stop == 0):
                services.extend(('petrel.buzzer',
                                 'maintenance.buzzer_output:' + buzzer))
    if generic and _SAFE.fullmatch(generic):
        name = 'fan_generic ' + generic
        if name in names and isinstance(settings.get(name), Mapping):
            services.append('maintenance.safe_fan:' + name)
    if led and isinstance(led, str):
        parts = led.split(' ', 1)
        if (len(parts) == 2 and parts[0] in _LED_TYPES
                and _SAFE.fullmatch(parts[1]) and led in names
                and isinstance(settings.get(led), Mapping)):
            services.append('maintenance.safe_led:' + led)
    return tuple(services)
