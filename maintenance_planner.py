"""Pure, bounded test planning over an immutable Maintenance discovery snapshot.

A plan row is a candidate, not permission to execute. In particular a
registered adapter never bypasses the future Safety Coordinator's live checks.
No I/O, G-code, background thread, or UI work is performed here.
"""
from dataclasses import dataclass

from maintenance_catalog import CATALOG, definition_for
from maintenance_discovery import (
    MaintenanceSnapshot, NONE, AUTOMATIC, USER, EXTERNAL,
    CALIBRATION, INFORMATION, _mode,
)


_METHODS = frozenset((AUTOMATIC, USER, EXTERNAL, CALIBRATION, INFORMATION))
_PRIORITY = (AUTOMATIC, CALIBRATION, USER, EXTERNAL, INFORMATION)
_RESONANCE_AXES = frozenset(('R02', 'R03', 'R04'))


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    """Trusted installed adapter descriptor, not derived from a macro name.

    Registration alone is not a live printer safety authorization.
    The corresponding adapter and verifier must actually be implemented
    before this descriptor is used in the production registry.
    """
    feature_id: str
    method: int
    adapter_id: str
    evidence_contract: str
    safety_profile: str


@dataclass(frozen=True, slots=True)
class PlannedTest:
    feature_id: str
    device: str | None
    available_methods: int
    method: int
    adapter_id: str | None
    category: str
    evidence_contract: str
    safety_profile: str
    epoch: int
    config_marker: int
    axes: int = 0

    @property
    def visible(self):
        """Only concrete adapter registrations may produce a UI candidate."""
        return self.category != 'blocked'


def _registered(adapters):
    """Reject malformed or conflicting adapter declarations, failing closed."""
    installed = {}
    for adapter in adapters:
        if not isinstance(adapter, AdapterRegistration):
            raise ValueError('Invalid Maintenance adapter registration')
        spec = definition_for(adapter.feature_id)
        if (type(adapter.method) is not int or adapter.method not in _METHODS
                or not adapter.adapter_id or not isinstance(adapter.adapter_id, str)
                or adapter.safety_profile != spec.safety_profile
                or adapter.evidence_contract != spec.evidence_contract
                or not (spec.methods & adapter.method)):
            raise ValueError('Unverified Maintenance adapter declaration')
        key = (adapter.feature_id, adapter.method)
        if key in installed:
            raise ValueError('Duplicate Maintenance adapter registration')
        installed[key] = adapter
    return installed


def _choose(feature, available, installed):
    for method in _PRIORITY:
        if not available & method:
            continue
        adapter = installed.get((feature, method))
        if adapter is not None:
            return method, adapter
    return NONE, None


def _planned_row(snapshot, spec, device, raw_methods, installed):
    available = raw_methods & spec.methods
    if not available:
        return None
    axes = snapshot.axes(spec.feature_id, device) if spec.feature_id in _RESONANCE_AXES else 0
    if spec.feature_id in _RESONANCE_AXES and not axes:
        return None
    method, adapter = _choose(spec.feature_id, available, installed)
    if method == NONE:
        category = 'blocked'
    elif method == INFORMATION:
        category = 'informational'
    elif method in (USER, EXTERNAL, CALIBRATION):
        category = 'guided'
    else:
        category = 'runnable'
    return PlannedTest(
        spec.feature_id, device, available, method,
        adapter.adapter_id if adapter else None, category,
        spec.evidence_contract, spec.safety_profile,
        snapshot.epoch, snapshot.config_marker, axes)


def build_plan(snapshot, adapters=()):
    """Build immutable per-device and global candidate rows, without I/O.

    'runnable' means an adapter has been explicitly registered and the
    discovered method matches; it is NOT permission to dispatch a command.
    Safety and current printer state still need positive checks at runtime.

    Unregistered candidates are 'blocked' and must never enter active menus.
    Mixed-scope resonance entries resolve to real chip instances and assigned
    axes, never a duplicate global XY test.
    """
    if snapshot is None:
        return ()
    if not isinstance(snapshot, MaintenanceSnapshot):
        raise ValueError('MaintenanceSnapshot required')
    installed = _registered(adapters)
    planned = []
    for spec in CATALOG:
        if spec.methods == NONE:
            continue
        instances = snapshot.instances(spec.feature_id) if spec.scope != 'global' else ()
        if spec.scope in ('device', 'mixed'):
            for instance in instances:
                row = _planned_row(snapshot, spec, instance.name,
                                   instance.method(spec.feature_id), installed)
                if row is not None:
                    planned.append(row)
        if spec.scope in ('global', 'mixed') and not (
                spec.scope == 'mixed' and instances):
            global_mask = _mode(snapshot.global_modes, spec.feature_id)
            row = _planned_row(snapshot, spec, None, global_mask, installed)
            if row is not None:
                planned.append(row)
    return tuple(planned)


def visible_plan(plan):
    """Small list for a future dynamic menu; hides unavailable adapters."""
    return tuple(row for row in plan if row.visible)
