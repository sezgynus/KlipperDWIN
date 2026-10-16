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
    if owners:
        # A loaded HH LED object without a proven unit index is not a safe
        # guided output candidate, regardless of its config section name.
        mmu_unit_indices(settings, owners)
        return tuple(owners)
    return None


def mmu_unit_indices(settings, owners):
    """Map Happy Hare unit names to numeric UNIT indexes from effective config.

    [mmu_machine] units is the authoritative ordered list used by Happy
    Hare when constructing MmuUnit(unit_index). Do not infer an index from
    unit0 spelling: installations may use any valid unit name/order and
    older Happy Hare versions parse UNIT as an integer only.
    """
    machine = settings.get('mmu_machine') if isinstance(settings, Mapping) else None
    if not isinstance(machine, Mapping):
        raise ValueError('mmu_machine_unit_order_missing')
    declared = machine.get('units')
    if isinstance(declared, str):
        names = tuple(part.strip() for part in declared.split(','))
    elif isinstance(declared, (tuple, list)):
        names = tuple(declared)
    else:
        raise ValueError('mmu_machine_units_unavailable')
    if not 1 <= len(names) <= 64 or any(
            not isinstance(name, str) or not _NAME.fullmatch(name)
            for name in names):
        raise ValueError('mmu_machine_units_invalid')
    if len(names) != len(set(names)):
        raise ValueError('mmu_machine_duplicate_units')
    indices = {name: index for index, name in enumerate(names)}
    if any(owner.unit not in indices for owner in owners):
        raise ValueError('mmu_led_unit_not_in_machine')
    return tuple(indices[owner.unit] for owner in owners)


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
    result = []
    for name in sorted(known):
        if not isinstance(name, str) or not name.startswith(
                tuple(kind + ' ' for kind in _TYPES)):
            continue
        try:
            owners = mmu_led_owners(settings, name)
        except ValueError:
            continue
        if (owners and all(owner.section in known for owner in owners)):
            result.append('maintenance.safe_led:' + name)
    return tuple(result)
