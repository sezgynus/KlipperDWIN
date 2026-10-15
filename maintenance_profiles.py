"""Explicit opt-in safety profiles for optional Maintenance actuators.

One tiny configuration is read on Klipper READY, never from the UI hot path.
No output is ever approved by its name alone: the operator's allowlist,
the actual Klipper object list and safe effective config must all agree.
"""
from collections.abc import Mapping
import json
import math
from pathlib import Path
import re

_SAFE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
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
                'version', 'case_light', 'buzzer_output'}
                or type(raw.get('version')) is not int or raw['version'] != 1
                or type(raw.get('case_light', False)) is not bool):
            return ()
        buzzer = raw.get('buzzer_output', '')
        if not isinstance(buzzer, str) or (buzzer and not _SAFE.fullmatch(buzzer)):
            return ()
        return (bool(raw.get('case_light', False)), buzzer)
    except (OSError, ValueError, TypeError, UnicodeError):
        return ()


def approved_integrations(state, profiles):
    """Return positive, specific service keys only; never writable targets."""
    if (not getattr(state, 'ready', False)
            or not isinstance(profiles, tuple) or len(profiles) != 2):
        return ()
    allow_case, buzzer = profiles
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
        if name in names and isinstance(cfg, Mapping):
            scale = cfg.get('scale', 1)
            start = cfg.get('value', 0)
            stop = cfg.get('shutdown_value', 0)
            if (type(scale) in (float, int) and math.isfinite(scale)
                    and 0 < scale <= 2 and start == 0 and stop == 0):
                services.extend(('petrel.buzzer',
                                 'maintenance.buzzer_output:' + buzzer))
    return tuple(services)
