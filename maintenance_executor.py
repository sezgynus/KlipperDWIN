"""Bounded on-demand Maintenance information reads, not physical self-tests.

Only explicitly supported GET endpoints are used. No new thread, Moonraker
client or socket is created: callers supply the existing bounded read worker.
Informational data NEVER generates a PASSED hardware-test result.
"""
from concurrent.futures import CancelledError
from dataclasses import dataclass
import math
from time import monotonic, time
from collections.abc import Mapping

from maintenance_catalog import definition_for
from maintenance_motion_info import FIELDS as MOTION_FIELDS, path_for as motion_path, read_fields as motion_fields
from maintenance_discovery import INFORMATION, MaintenanceSnapshot
from maintenance_planner import AdapterRegistration, PlannedTest
from maintenance_safety import MaintenanceSafetyCoordinator


# No dynamic path construction from user-controlled feature or device names.
_ENDPOINTS = {
    'S01': '/machine/proc_stats',
    'S02': '/machine/proc_stats',
    'S03': '/machine/proc_stats',
    'S05': '/machine/proc_stats',
    'S08': '/printer/objects/query?webhooks',
    'S10': '/server/history/totals',
}


_THERMAL_FIELDS = {
    'H11': ('power',), 'H14': ('temperature',),
    'H16': ('humidity', 'pressure', 'gas'),
}


def read_only_adapters():
    """Trusted, fixed registrations: INFORMATION items, never hardware PASS."""
    return tuple(AdapterRegistration(
        feature, INFORMATION, 'maintenance.read.' + feature,
        definition_for(feature).evidence_contract,
        definition_for(feature).safety_profile)
        for feature in (*_ENDPOINTS, *_THERMAL_FIELDS, *MOTION_FIELDS))


@dataclass(frozen=True, slots=True)
class ReadResult:
    feature_id: str
    device: str | None
    status: str | None  # None = observed INFORMATION, not a functional PASS.
    source: str
    observed_at: float | None
    evidence: tuple = ()
    reason: str = ''


def _number(value):
    return (type(value) in (float, int) and math.isfinite(value))


def _read_fields(feature, reply, device=None):
    """Extract only a few known scalar fields; never retain API reply maps."""
    if not isinstance(reply, Mapping):
        return ()
    result = reply.get('result')
    if not isinstance(result, Mapping):
        return ()
    if feature in MOTION_FIELDS:
        return motion_fields(feature, reply, device)
    if feature in _THERMAL_FIELDS:
        status = result.get('status')
        values = status.get(device) if isinstance(status, Mapping) else None
        stamp = result.get('eventtime')
        if not isinstance(values, Mapping) or not _number(stamp) or stamp < 0:
            return ()
        fields = tuple((key, values[key]) for key in _THERMAL_FIELDS[feature]
                       if _number(values.get(key)) and
                       (key != 'power' or 0 <= values[key] <= 1))
        return (('klipper_eventtime_s', stamp),) + fields if fields else ()
    if feature in ('S01', 'S02', 'S03', 'S05'):
        source = result
        if feature == 'S01':
            fields = []
            cpu = source.get('system_cpu_usage')
            if isinstance(cpu, Mapping):
                for key in sorted(cpu)[:4]:
                    value = cpu[key]
                    if _number(value):
                        fields.append(('cpu.' + str(key)[:32], value))
            memory = source.get('system_memory')
            if isinstance(memory, Mapping):
                for key in ('total', 'available', 'used'):
                    if _number(memory.get(key)):
                        fields.append(('memory.' + key, memory[key]))
            return tuple(fields[:7])
        if feature == 'S02':
            temp = source.get('cpu_temp')
            return (('cpu_temp_c', temp),) if _number(temp) else ()
        if feature == 'S03':
            flags = source.get('throttled_state')
            if not isinstance(flags, Mapping):
                return ()
            # Bits are Pi undervoltage/throttling history, NOT the 24 V PSU.
            value = flags.get('bits')
            return (('throttled_bits', value),) if type(value) is int and value >= 0 else ()
        net = source.get('network')
        fields = []
        if isinstance(net, Mapping):
            for name in sorted(str(k) for k in net)[:3]:
                entry = net.get(name)
                if isinstance(entry, Mapping):
                    for key in ('rx_bytes', 'tx_bytes'):
                        if type(entry.get(key)) is int and entry[key] >= 0:
                            fields.append((name[:24] + '.' + key, entry[key]))
        return tuple(fields)
    if feature == 'S08':
        status = result.get('status')
        webhooks = status.get('webhooks') if isinstance(status, Mapping) else None
        state = webhooks.get('state') if isinstance(webhooks, Mapping) else None
        return (('webhooks_state', state),) if state in ('ready', 'startup', 'error', 'shutdown') else ()
    if feature == 'S10':
        totals = result.get('job_totals')
        fields = []
        if isinstance(totals, Mapping):
            for key in ('total_jobs', 'total_time', 'total_print_time',
                        'total_filament_used'):
                if _number(totals.get(key)) and totals[key] >= 0:
                    fields.append((key, totals[key]))
        return tuple(fields)
    return ()


class MaintenanceReadExecutor:
    """One active bounded read; poll on the UI owner, no callback side effects."""

    __slots__ = ('_worker', '_client', '_safety', '_context', '_snapshot',
                 '_active', '_future', '_deadline', '_closed')

    def __init__(self, worker, client, context_provider, snapshot_provider,
                 safety=None):
        if not callable(context_provider) or not callable(snapshot_provider):
            raise ValueError('Fresh context and snapshot providers are required')
        self._worker = worker
        self._client = client
        self._context = context_provider
        self._snapshot = snapshot_provider
        self._safety = safety if safety is not None else MaintenanceSafetyCoordinator()
        self._active = None
        self._future = None
        self._deadline = 0.0
        self._closed = False

    @property
    def pending(self):
        return self._active is not None

    def _context_and_snapshot(self):
        return self._snapshot(), self._context()

    def start(self, row, timeout=3.0):
        """Admit one explicit INFORMATION adapter; return (accepted, reason).

        Caller must ensure real queue/operation checks in context_provider.
        Only a bounded GET is ever scheduled; no physical actuation.
        """
        if self._closed or self.pending:
            return False, 'executor_busy_or_closed'
        if not isinstance(row, PlannedTest):
            return False, 'invalid_plan'
        if (row.feature_id not in (*_ENDPOINTS, *_THERMAL_FIELDS, *MOTION_FIELDS)
                or (row.feature_id in _ENDPOINTS and row.device is not None)
                or (row.feature_id in (*_THERMAL_FIELDS, *MOTION_FIELDS) and
                    row not in __import__('maintenance_planner').build_plan(
                        self._snapshot(), read_only_adapters()))
                or row.method != INFORMATION or row.category != 'informational'
                or row.adapter_id != 'maintenance.read.' + row.feature_id):
            return False, 'unsupported_adapter'
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            return False, 'invalid_timeout'
        try:
            snapshot, context = self._context_and_snapshot()
            if (not isinstance(snapshot, MaintenanceSnapshot)
                    or snapshot.epoch != row.epoch
                    or snapshot.config_marker != row.config_marker):
                return False, 'stale_plan'
            decision, session = self._safety.begin(snapshot, context)
        except Exception:
            return False, 'context_unavailable'
        if not decision.allowed:
            return False, decision.reason
        from urllib.parse import quote
        path = (motion_path(row.feature_id, row.device, context.state)
                if row.feature_id in MOTION_FIELDS else
                _ENDPOINTS[row.feature_id] if row.feature_id in _ENDPOINTS
                else '/printer/objects/query?' + quote(row.device, safe='') +
                '=' + ','.join(_THERMAL_FIELDS[row.feature_id]))

        def work():
            # Recheck immediately before GET; a queued job must not run stale.
            try:
                current, fresh = self._context_and_snapshot()
                if not self._safety.guard(session, current, fresh).allowed:
                    return ()
                return _read_fields(row.feature_id, self._client.get(path), row.device)
            except Exception:
                # Never log/persist response payloads, tokens or transport details.
                raise

        try:
            future = self._worker.submit(work, queue_timeout=timeout)
        except Exception:
            self._safety.end(session)
            return False, 'read_worker_rejected'
        self._active = (session, row)
        self._future = future
        self._deadline = monotonic() + timeout
        return True, 'scheduled'

    def _finish(self, status, reason, evidence=(), observed_at=None):
        session, row = self._active
        self._safety.end(session)
        self._active = None
        self._future = None
        self._deadline = 0.0
        return ReadResult(row.feature_id, row.device, status,
                          (_ENDPOINTS.get(row.feature_id) or '/printer/objects/query'), observed_at,
                          tuple(evidence), reason)

    def poll(self):
        """Nonblocking owner-thread collection; None means still pending."""
        if not self.pending:
            return None
        session, row = self._active
        try:
            snapshot, context = self._context_and_snapshot()
            decision = self._safety.guard(session, snapshot, context)
        except Exception:
            decision = None
        if decision is None or not decision.allowed:
            self._future.cancel()
            return self._finish('ABORTED', 'unsafe_or_stale_session')
        if monotonic() > self._deadline:
            self._future.cancel()
            return self._finish('ERROR', 'timeout')
        if not self._future.done():
            return None
        try:
            evidence = self._future.result()
        except CancelledError:
            return self._finish('ABORTED', 'cancelled')
        except Exception:
            return self._finish('ERROR', 'read_failed')
        if not evidence:
            return self._finish('INCONCLUSIVE', 'no_valid_evidence')
        # Presence of information is not a functional PASS.
        return self._finish(None, 'observed_information', evidence, time())

    def cancel(self):
        """Invalidate a read; late Future results are never reattached."""
        if not self.pending:
            return None
        self._future.cancel()
        return self._finish('ABORTED', 'user_cancelled')

    def close(self):
        self.cancel()
        self._closed = True
        # Worker/client belong to Petrel and must NOT be closed here.
