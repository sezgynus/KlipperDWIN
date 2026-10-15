"""Fail-closed Maintenance session admission and per-dispatch safety checks.

No G-code, HTTP, printer locks, scheduling or actuation occurs here. This
coordinator only manages one local Maintenance reservation; external clients
must be treated as concurrent, not magically blocked by this reservation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock

from maintenance_discovery import MaintenanceSnapshot


_IDLE_PRINT_STATES = frozenset(('standby', 'complete', 'cancelled', 'error'))


@dataclass(frozen=True, slots=True)
class SafetyContext:
    """Fresh evidence provided by the caller, never retained by the session."""
    state: object
    queue_checked: bool = False
    job_queue: object = None
    operations_checked: bool = False
    conflicting_operation: bool = True


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SafetySession:
    token: int
    epoch: int
    config_marker: int


def precheck(snapshot, context):
    """Conservatively inspect a fresh, complete status before any dispatch.

    job_queue=None is permitted only when the caller positively verified that
    no queue component exists. Queue and other Petrel operation checks are
    mandatory, rather than trusting a stale UI-idle hint.
    """
    if not isinstance(snapshot, MaintenanceSnapshot):
        return SafetyDecision(False, 'no_snapshot')
    if not isinstance(context, SafetyContext):
        return SafetyDecision(False, 'no_context')
    state = context.state
    if state is None or getattr(state, 'ready', None) is not True:
        return SafetyDecision(False, 'not_ready')
    if (getattr(state, 'epoch', None) != snapshot.epoch
            or id(getattr(state, 'settings', None)) != snapshot.config_marker):
        return SafetyDecision(False, 'epoch_or_config_changed')
    status = getattr(state, 'status', None)
    if not isinstance(status, Mapping):
        return SafetyDecision(False, 'status_missing')
    webhooks = status.get('webhooks')
    if not isinstance(webhooks, Mapping) or webhooks.get('state') != 'ready':
        return SafetyDecision(False, 'webhooks_not_ready')
    print_stats = status.get('print_stats')
    if (not isinstance(print_stats, Mapping)
            or print_stats.get('state') not in _IDLE_PRINT_STATES):
        return SafetyDecision(False, 'print_not_idle')
    sdcard = status.get('virtual_sdcard')
    if not isinstance(sdcard, Mapping) or sdcard.get('is_active') is not False:
        return SafetyDecision(False, 'sdcard_unknown_or_active')
    paused = status.get('pause_resume')
    if not isinstance(paused, Mapping) or paused.get('is_paused') is not False:
        return SafetyDecision(False, 'pause_unknown_or_active')
    probe = status.get('manual_probe')
    if probe is not None and (
            not isinstance(probe, Mapping) or probe.get('is_active') is not False):
        return SafetyDecision(False, 'manual_probe_active')
    mmu = status.get('mmu')
    if mmu is not None and (
            not isinstance(mmu, Mapping)
            or str(mmu.get('action', '')).lower() != 'idle'):
        return SafetyDecision(False, 'mmu_busy')
    if context.queue_checked is not True:
        return SafetyDecision(False, 'queue_unknown')
    if context.job_queue is not None:
        queue = context.job_queue
        if not isinstance(queue, Mapping):
            return SafetyDecision(False, 'queue_invalid')
        # An auto-starting queued job can race the UI's idle observation.
        if (queue.get('queue_state') not in ('ready', 'paused')
                or not isinstance(queue.get('queued_jobs'), (tuple, list))
                or queue['queued_jobs']):
            return SafetyDecision(False, 'queue_pending_or_busy')
    if context.operations_checked is not True:
        return SafetyDecision(False, 'other_operations_unknown')
    if context.conflicting_operation is not False:
        return SafetyDecision(False, 'conflicting_operation')
    return SafetyDecision(True, 'allowed')


class MaintenanceSafetyCoordinator:
    """Single active local reservation; every step rechecks live evidence."""
    __slots__ = ('_lock', '_generation', '_session')

    def __init__(self):
        self._lock = Lock()
        self._generation = 0
        self._session = None

    @property
    def active(self):
        with self._lock:
            return self._session

    def begin(self, snapshot, context):
        """Start only after positive admission checks; never sends a command."""
        with self._lock:
            if self._session is not None:
                return SafetyDecision(False, 'session_busy'), None
            decision = precheck(snapshot, context)
            if not decision.allowed:
                return decision, None
            self._generation += 1
            session = SafetySession(
                self._generation, snapshot.epoch, snapshot.config_marker)
            self._session = session
            return decision, session

    def guard(self, session, snapshot, context):
        """Call just before EACH potential side-effecting dispatch."""
        with self._lock:
            if (not isinstance(session, SafetySession)
                    or self._session != session):
                return SafetyDecision(False, 'stale_session')
            if (not isinstance(snapshot, MaintenanceSnapshot)
                    or session.epoch != snapshot.epoch
                    or session.config_marker != snapshot.config_marker):
                self._session = None
                return SafetyDecision(False, 'epoch_or_config_changed')
            decision = precheck(snapshot, context)
            if not decision.allowed:
                self._session = None
            return decision

    def end(self, session):
        """Idempotently invalidate one exact session; no restore is claimed."""
        with self._lock:
            if not isinstance(session, SafetySession) or self._session != session:
                return False
            self._session = None
            return True

    def clear(self):
        """Invalidate in-flight callbacks on disconnect/cancel/close."""
        with self._lock:
            self._generation += 1
            self._session = None
