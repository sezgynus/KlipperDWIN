"""On-demand *live* Maintenance safety evidence from existing Petrel state.

No polling, G-code, threads or new Moonraker connections. Queue evidence is
read only when requested by a future test, on the existing bounded read worker.
A queue component is considered absent ONLY after positive /server/info data.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic

from maintenance_safety import SafetyContext
from printer_state import PrinterState


_QUEUE_MAX_AGE = 3.0


@dataclass(frozen=True, slots=True)
class QueueEvidence:
    epoch: int
    config_marker: int
    observed_at: float
    component_present: bool
    queue_state: str | None = None
    is_empty: bool | None = None


def read_queue_evidence(client, epoch, config_marker):
    """Make at most two small read-only GETs; never preserve queued filenames.

    An unavailable endpoint or a malformed answer returns None (unknown),
    not a fabricated 'queue disabled' or empty queue.
    """
    try:
        info = client.get('/server/info')
        result = info.get('result') if isinstance(info, Mapping) else None
        components = result.get('components') if isinstance(result, Mapping) else None
        if (not isinstance(components, (tuple, list))
                or len(components) > 128
                or any(not isinstance(item, str) for item in components)):
            return None
        present = 'job_queue' in components
        del info, result, components
        if not present:
            return QueueEvidence(epoch, config_marker, monotonic(), False)
        payload = client.get('/server/job_queue/status')
        result = payload.get('result') if isinstance(payload, Mapping) else None
        if not isinstance(result, Mapping):
            return None
        queue_state, queued_jobs = result.get('queue_state'), result.get('queued_jobs')
        if (queue_state not in ('ready', 'paused', 'loading', 'starting')
                or not isinstance(queued_jobs, (tuple, list))):
            return None
        # Never preserve the potentially private filenames or job IDs.
        return QueueEvidence(epoch, config_marker, monotonic(), True,
                             queue_state, not bool(queued_jobs))
    except (Exception):
        # Optional Moonraker APIs may be missing or temporarily unavailable.
        return None


def conflicting_petrel_operation(printer):
    """Check existing operation owners, not guessed macro or device names."""
    try:
        if printer.jog_recovery_required or getattr(printer, '_jog_restore', None):
            return True
        if getattr(printer, '_settings_save', None) is not None:
            return True
        for name in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session'):
            owner = getattr(printer, name, None)
            if owner is None:
                return True  # An incomplete owner is not proof of safety.
            if getattr(owner, 'pending', None):
                return True
        probe = printer.probe_wizard
        if getattr(probe, 'phase', None) in ('starting', 'active', 'accepted',
                                           'aborting', 'recovering'):
            return True
        return False
    except Exception:
        return True


def live_safety_context(printer, queue_evidence, now=None, *, queue_max_age=_QUEUE_MAX_AGE):
    """Return fresh SafetyContext; unknown evidence denies admission.

    Query subscription only on-demand (not from update_variable hot path).
    The existing immutable config identity is reused only within one epoch.
    """
    now = monotonic() if now is None else now
    try:
        raw = printer.subscription.snapshot(include_settings=False)
        stored = printer.state
        if (not stored.ready or printer.connection_error
                or not isinstance(raw, Mapping)
                or raw.get('state') != 'ready'
                or raw.get('epoch') != stored.epoch):
            return SafetyContext(None)
        state = PrinterState.from_snapshot(raw, reused_settings=stored.settings)
        no_conflicts = not conflicting_petrel_operation(printer)
        fresh = (isinstance(queue_evidence, QueueEvidence)
                 and queue_evidence.epoch == state.epoch
                 and queue_evidence.config_marker == id(state.settings)
                 and 0 <= now - queue_evidence.observed_at <= queue_max_age)
        if not fresh:
            return SafetyContext(state, operations_checked=True,
                                 conflicting_operation=not no_conflicts)
        queue = None
        if queue_evidence.component_present:
            queue = {'queue_state': queue_evidence.queue_state,
                     'queued_jobs': () if queue_evidence.is_empty is True else (1,)}
        return SafetyContext(state, queue_checked=True, job_queue=queue,
                             operations_checked=True,
                             conflicting_operation=not no_conflicts)
    except Exception:
        return SafetyContext(None)
