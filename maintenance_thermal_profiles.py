"""Explicit generic-heater applications; bounded READY-time profile parsing."""
from collections.abc import Mapping
import json
from pathlib import Path
from maintenance_thermal import number, heater_name

_PREFIX = 'maintenance.thermal_profile:'


def profile_services(state, path=None):
    """No inferred application role, temperature, wattage or fan mapping."""
    target = Path(path) if path is not None else Path.home() / '.config' / 'Petrel' / 'maintenance-thermal-profiles.json'
    try:
        if not state.ready or not target.is_file() or target.stat().st_size > 4096:
            return ()
        data = json.loads(target.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or set(data) != {'version', 'heaters'}
                or type(data['version']) is not int or data['version'] != 1
                or not isinstance(data['heaters'], list) or len(data['heaters']) > 8):
            return ()
        result, seen = [], set()
        for item in data['heaters']:
            if not isinstance(item, dict) or set(item) not in (
                    {'object', 'target', 'duration_s'},
                    {'object', 'target', 'ceiling', 'duration_s'}):
                return ()
            name = item['object']
            heater_name(name)
            if not name.startswith('heater_generic ') or name in seen:
                return ()
            seen.add(name)
            cfg = state.settings.get(name)
            # The optional legacy 'ceiling' field is validated as numeric
            # for compatibility but no longer participates in admission,
            # runtime temperature limits or the discovery snapshot.
            if 'ceiling' in item and not number(item['ceiling']):
                return ()
            values = (item['target'], item['duration_s'])
            if (name not in state.objects or not isinstance(cfg, Mapping)
                    or not all(number(v) for v in values)
                    or not number(cfg.get('min_temp')) or not number(cfg.get('max_temp'))
                    or not cfg['min_temp'] < values[0] < cfg['max_temp']
                    or not 30 <= values[1] <= 120):
                return ()
            result.append(_PREFIX+name+'|'+','.join(format(v, '.6g') for v in values))
        return tuple(result)
    except (OSError, ValueError, TypeError, UnicodeError):
        return ()


def profile_for(snapshot, device):
    if snapshot is None or not isinstance(device, str):
        return None
    prefix = _PREFIX+device+'|'
    entries = [s[len(prefix):] for s in snapshot.service_key if s.startswith(prefix)]
    if len(entries) != 1:
        return None
    try:
        values = tuple(float(v) for v in entries[0].split(','))
        if len(values) not in (2, 3) or not all(number(v) for v in values):
            return None
        # Prior snapshot tokens had a middle ceiling value; ignore it.
        target, duration = values[0], values[-1]
        if not 30 <= duration <= 120:
            return None
        return target, duration
    except (ValueError, TypeError):
        return None
