"""Small allowlisted motion/driver diagnostics; no writes or hardware PASS."""
from collections.abc import Mapping
import math
from urllib.parse import quote

FIELDS = {
    'M07': ('drv_status',), 'M08': ('temperature',),
    'M09': ('run_current', 'hold_current'),
    'M11': ('steppers',), 'M12': ('last_home',),
    'M13': ('temperature',), 'M14': ('homed_axes', 'position', 'max_velocity'),
    'M16': ('carriage_0', 'carriage_1', 'active_carriage'),
}
_GLOBAL = {'M11': 'stepper_enable', 'M12': 'endstop_phase', 'M14': 'toolhead'}
_DRIVER = ('tmc2130', 'tmc2208', 'tmc2209', 'tmc2240', 'tmc2660', 'tmc5160', 'tmc5161')
_FLAGS = ('ot', 'otpw', 's2ga', 's2gb', 's2vsa', 's2vsb', 'ola', 'olb',
          'stst', 't120', 't143', 't150', 't157')


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def path_for(feature, device, state):
    names = getattr(state, 'objects', ())
    if feature in ('M07', 'M08', 'M09'):
        if (not isinstance(device, str) or device not in names
                or device.partition(' ')[0] not in _DRIVER):
            raise ValueError('driver_object_unverified')
        objects = (device,)
    elif feature in _GLOBAL:
        objects = (_GLOBAL[feature],)
    elif feature == 'M13':
        objects = tuple(n for n in names if isinstance(n, str) and n.startswith('angle '))[:4]
    elif feature == 'M16':
        objects = tuple(n for n in ('dual_carriage', 'generic_cartesian') if n in names)[:1]
    else:
        raise ValueError('motion_information_unavailable')
    if not objects or any(n not in names or len(n) > 96 for n in objects):
        raise ValueError('motion_object_unverified')
    # M16 implementations differ: query the one verified object, parse only
    # known scalar mode fields. Never activate a carriage or move a motor.
    return '/printer/objects/query?' + '&'.join(
        quote(n, safe='') + ('=' + ','.join(FIELDS[feature]) if feature != 'M16' else '')
        for n in objects)


def read_fields(feature, reply, device=None):
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    stamp = result.get('eventtime') if isinstance(result, Mapping) else None
    if not isinstance(status, Mapping) or not number(stamp) or stamp < 0:
        return ()
    if feature in ('M07', 'M08', 'M09'):
        v = status.get(device)
        if not isinstance(v, Mapping):
            return ()
        if feature == 'M07':
            fields = v.get('drv_status')
            # Klipper returns null while the driver's monitor is disabled.
            # A valid empty dict means all nonzero-only reported flags clear.
            if not isinstance(fields, Mapping) or len(fields) > 64:
                return ()
            out = [('reported_nonzero_fields', len(fields))]
            if isinstance(device, str) and device.startswith('tmc2208 '):
                faults = tmc2208_faults(v)
                if faults is None:
                    return ()  # Unknown driver schema is not a clean result.
                out.extend((('fault_count', len(faults)),
                            ('faults', ','.join(faults) or 'none reported')))
            out.extend((k, fields[k]) for k in _FLAGS
                       if k in fields and type(fields[k]) in (bool, int) and 0 <= fields[k] <= 1)
        else:
            out = [(k, v[k]) for k in FIELDS[feature] if number(v.get(k))]
            if feature == 'M09':
                out = [(k, x) for k, x in out if x >= 0]
    elif feature == 'M11':
        v = status.get('stepper_enable', {}).get('steppers')
        if not isinstance(v, Mapping):
            return ()
        out = [(str(k)[:32], v[k]) for k in sorted(v)[:16]
               if isinstance(k, str) and type(v[k]) is bool]
    elif feature == 'M12':
        v = status.get('endstop_phase', {}).get('last_home')
        if not isinstance(v, Mapping):
            return ()
        out = []
        for name in ((device,) if device is not None else sorted(v)[:4]):
            if name not in v:
                continue
            entry = v[name]
            if not isinstance(name, str) or not isinstance(entry, Mapping):
                continue
            phase, count = entry.get('phase'), entry.get('phases')
            if type(phase) is int and type(count) is int and 0 <= phase < count <= 4096:
                out.append((name[:24]+'.phase', '%d/%d' % (phase, count)))
    elif feature == 'M14':
        v = status.get('toolhead')
        if not isinstance(v, Mapping):
            return ()
        out = []
        axes = v.get('homed_axes')
        if isinstance(axes, str) and set(axes) <= set('xyz'):
            out.append(('homed_axes', axes or 'none'))
        pos = v.get('position')
        if isinstance(pos, (tuple, list)) and len(pos) >= 3 and all(number(x) for x in pos[:3]):
            out.extend(('commanded_'+a, round(pos[i], 4)) for i, a in enumerate('xyz'))
        if number(v.get('max_velocity')) and v['max_velocity'] > 0:
            out.append(('max_velocity_mm_s', v['max_velocity']))
    elif feature == 'M13':
        out = [(name[:24]+'.temperature', v['temperature'])
               for name, v in status.items()
               if isinstance(name, str) and name.startswith('angle ')
               and isinstance(v, Mapping) and number(v.get('temperature'))][:4]
    elif feature == 'M16':
        out = []
        for name in ('dual_carriage', 'generic_cartesian'):
            v = status.get(name)
            if not isinstance(v, Mapping):
                continue
            for k in FIELDS['M16']:
                value = v.get(k)
                if value in ('PRIMARY', 'INACTIVE', 'COPY', 'MIRROR') or (
                        type(value) is int and 0 <= value <= 1):
                    out.append((k, value))
    else:
        return ()
    return (('klipper_eventtime_s', stamp), *out) if out else ()


def tmc2208_faults(values):
    """Supported exact chip schema; nonzero-only fields from Klipper monitor."""
    if not isinstance(values, Mapping):
        return None
    fields = values.get('drv_status')
    if not isinstance(fields, Mapping) or len(fields) > 64:
        return None
    allowed=set(_FLAGS)|{'cs_actual','stealth'}
    if any(k not in allowed for k in fields):
        return None
    if any(type(v) not in (bool,int) or not 0<=v<=(
            31 if k=='cs_actual' else 1) for k,v in fields.items()):
        return None
    keys = ('ot', 'otpw', 's2ga', 's2gb', 's2vsa', 's2vsb',
            't120', 't143', 't150', 't157')
    if any(k in fields and (type(fields[k]) not in (bool, int) or fields[k] not in (0, 1)) for k in keys):
        return None
    return tuple(k for k in keys if fields.get(k, 0))
