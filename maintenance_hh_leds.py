"""Canonical, read-only Happy Hare LED ownership discovery.

No printer-specific hardware assumptions. Only effective Klipper config
proves the segment-to-physical LED mapping. Unknown or overlapping ownership
is deliberately rejected instead of guessing a G-code target.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import re

_TYPES = ('neopixel', 'dotstar', 'led', 'pca9632')
_SEGMENTS = ('exit', 'entry', 'status', 'logo')
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
_SPEC = re.compile(r'^(neopixel|dotstar|led|pca9632):([A-Za-z][A-Za-z0-9_]{0,47})\s+\(([0-9,\s-]+)\)$')
_MAX = 32


@dataclass(frozen=True, slots=True)
class MmuLedOwner:
    section: str
    unit: str
    segments: tuple  # (segment, 1-based physical LED indices), in fixed order


def _indices(spec, total):
    match = _SPEC.fullmatch(spec.strip())
    if match is None:
        raise ValueError('mmu_led_mapping_unsupported')
    raw = match.group(3)
    indexes = []
    for token in raw.split(','):
        token = token.strip()
        if not token:
            raise ValueError('mmu_led_index_invalid')
        if '-' in token:
            parts = token.split('-')
            if len(parts) != 2 or not all(x.strip().isdigit() for x in parts):
                raise ValueError('mmu_led_index_invalid')
            start, stop = (int(n) for n in parts)
            seq = range(start, stop + (1 if start <= stop else -1),
                        1 if start <= stop else -1)
        else:
            if not token.isdigit():
                raise ValueError('mmu_led_index_invalid')
            seq = (int(token),)
        for index in seq:
            if not 1 <= index <= total or index in indexes:
                raise ValueError('mmu_led_index_out_of_bounds_or_duplicate')
            indexes.append(index)
    if not indexes:
        raise ValueError('mmu_led_empty_mapping')
    return match.group(1) + ' ' + match.group(2), tuple(indexes)


def mmu_led_owners(settings, target):
    """Find all MMU units/segments controlling a physical LED chain.

    None means this physical chain is not referenced by Happy Hare. A tuple
    of unique validated MmuLedOwner objects means MMU-owned. Duplicate
    physical indexes or ambiguous segment sharing fail closed.

    A segment may map exactly one physical chain, with arbitrary valid
    indexes. Other physical chains on that segment are not pulsed.
    """
    if not isinstance(settings, Mapping) or not isinstance(target, str):
        return None
    kind, sep, name = target.partition(' ')
    if not sep or kind not in _TYPES or not _NAME.fullmatch(name):
        return None
    cfg = settings.get(target)
    if not isinstance(cfg, Mapping):
        raise ValueError('mmu_led_physical_config_unavailable')
    total = cfg.get('chain_count', 1)
    if type(total) is not int or not 1 <= total <= _MAX:
        raise ValueError('mmu_led_chain_count_invalid')

    # Detect even malformed references to the target, and refuse them.
    needle = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(kind) + ':' +
                        re.escape(name) + r'(?![A-Za-z0-9_])', re.I)
    owners = []
    taken = set()
    for section, unit_cfg in settings.items():
        if not isinstance(section, str) or not section.startswith('mmu_leds '):
            continue
        if not isinstance(unit_cfg, Mapping):
            raise ValueError('mmu_led_config_unknown')
        owned_segments = []
        for segment in _SEGMENTS:
            value = unit_cfg.get(segment + '_leds', '')
            if not isinstance(value, str):
                raise ValueError('mmu_led_segment_config_unknown')
            lines = tuple(line.strip() for line in value.splitlines() if line.strip())
            if not any(needle.search(line) for line in lines):
                continue
            # MMU_SET_LED operates on the entire segment; never modify a
            # second physical chain hidden in the same segment.
            if len(lines) != 1:
                raise ValueError('mmu_led_segment_spans_multiple_chains')
            mapped, indexes = _indices(lines[0], total)
            if mapped != target:
                raise ValueError('mmu_led_target_identity_mismatch')
            if any(index in taken for index in indexes):
                raise ValueError('mmu_led_overlapping_segment_owners')
            taken.update(indexes)
            owned_segments.append((segment, indexes))
        if owned_segments:
            unit = section.split(' ', 1)[1]
            if not _NAME.fullmatch(unit):
                raise ValueError('mmu_led_unsafe_unit_name')
            owners.append(MmuLedOwner(section, unit, tuple(owned_segments)))
    return tuple(owners) if owners else None


def _configured_units(settings):
    """Optional ordered unit names from effective [mmu_machine] settings."""
    cfg = settings.get('mmu_machine')
    if not isinstance(cfg, Mapping):
        return None
    raw = cfg.get('units')
    if raw is None:
        return None
    if isinstance(raw, str):
        names = tuple(part.strip() for part in raw.split(','))
    elif isinstance(raw, (tuple, list)):
        names = tuple(raw)
    else:
        raise ValueError('mmu_machine_units_invalid')
    return _checked_units(names)


def _checked_units(names):
    if (not 1 <= len(names) <= 64
            or any(not isinstance(name, str) or not _NAME.fullmatch(name)
                   for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('mmu_machine_units_invalid_or_duplicate')
    return tuple(names)


def _live_units(status):
    """Happy Hare mmu_machine.get_status: unit_N -> {'name': ...}.

    The numeric keys and num_units are published by Happy Hare itself; never
    infer indexes from the spelling of a unit/LED configuration section.
    """
    if status is None:
        return None
    if not isinstance(status, Mapping):
        raise ValueError('mmu_machine_live_status_invalid')
    count = status.get('num_units')
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError('mmu_machine_live_count_invalid')
    keys = {k for k in status if isinstance(k, str)
            and re.fullmatch(r'unit_[0-9]+', k)}
    expected = {'unit_%d' % i for i in range(count)}
    if keys != expected:
        raise ValueError('mmu_machine_live_unit_indices_inconsistent')
    names = []
    for i in range(count):
        unit = status.get('unit_%d' % i)
        if not isinstance(unit, Mapping):
            raise ValueError('mmu_machine_live_unit_invalid')
        names.append(unit.get('name'))
    return _checked_units(tuple(names))


def mmu_unit_indices(settings, owners, machine_status=None):
    """Resolve numeric indexes from positive HH configuration or live state.

    Effective Klipper configfile.settings may not expose units, even when
    Happy Hare has fully initialized. The live mmu_machine status publishes
    num_units and unit_0/1/... with their names. Either is authoritative,
    but when both are available they must agree. Unknown mapping fails closed.
    """
    if not isinstance(settings, Mapping):
        raise ValueError('mmu_machine_configuration_missing')
    configured = _configured_units(settings)
    live = _live_units(machine_status)
    if configured is not None and live is not None and configured != live:
        raise ValueError('mmu_machine_unit_order_conflict')
    names = live if live is not None else configured
    if names is None:
        raise ValueError('mmu_machine_unit_order_unavailable')
    index = {name: i for i, name in enumerate(names)}
    if any(owner.unit not in index for owner in owners):
        raise ValueError('mmu_led_unit_not_in_machine')
    return tuple(index[owner.unit] for owner in owners)


def auto_happy_hare_led_services(state):
    """Auto-discover *known MMU LED semantics*, never arbitrary output pins.

    Manual user confirmation is still required before any O04 actuation.
    Independent LED chains keep their existing explicit profile opt-in.
    """
    if not getattr(state, 'ready', False):
        return ()
    settings, objects = getattr(state, 'settings', None), getattr(state, 'objects', ())
    if not isinstance(settings, Mapping):
        return ()
    known = set(objects)
    status = getattr(state, 'status', None)
    machine = status.get('mmu_machine') if isinstance(status, Mapping) else None
    result = []
    for name in sorted(known):
        if not isinstance(name, str) or not name.startswith(
                tuple(kind + ' ' for kind in _TYPES)):
            continue
        try:
            owners = mmu_led_owners(settings, name)
            if owners:
                if 'mmu_machine' not in known:
                    continue
                mmu_unit_indices(settings, owners, machine)
        except ValueError:
            continue
        if (owners and all(owner.section in known for owner in owners)):
            result.append('maintenance.safe_led:' + name)
    return tuple(result)
