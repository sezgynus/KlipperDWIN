"""Petrel-owned, opt-in, read-only Maintenance information bridge.

No startup or print-loop reads. A request is admitted using the existing
Maintenance snapshot, async Moonraker job queue evidence and live Petrel
operation guards; result collection never blocks the UI/encoder owner.
"""
from concurrent.futures import CancelledError
from time import monotonic

from maintenance_discovery import MaintenanceSnapshot
from maintenance_executor import MaintenanceReadExecutor, ReadResult, read_only_adapters
from maintenance_planner import build_plan, visible_plan
from maintenance_runtime import live_safety_context, read_queue_evidence


class MaintenanceReadController:
    __slots__ = ('_printer', '_worker', '_client', '_executor', '_row',
                 '_queue', '_preflight', '_deadline', '_phase', '_closed')

    def __init__(self, printer, worker, client):
        self._printer = printer
        self._worker = worker
        self._client = client
        self._queue = None
        self._executor = MaintenanceReadExecutor(
            worker, client,
            lambda: live_safety_context(self._printer, self._queue),
            lambda: self._printer.maintenance.snapshot,
            local_reader=lambda feature:self._printer.maintenance_local_read(feature),
            subscription=getattr(self._printer, 'subscription', None))
        self._row = None
        self._preflight = None
        self._deadline = 0.0
        self._phase = None
        self._closed = False

    @property
    def pending(self):
        return self._phase is not None

    def available(self):
        """On-demand discovery/catalog/adapter join; no implicit I/O."""
        snap = self._printer.maintenance.snapshot
        if not isinstance(snap, MaintenanceSnapshot):
            return ()
        return visible_plan(build_plan(snap, read_only_adapters()))

    def start(self, feature_id, timeout=8.0, device=None):
        """Queue preflight; call poll() later for completion and result."""
        if self._closed or self.pending:
            return False, 'read_busy_or_closed'
        if (type(timeout) not in (int, float)
                or not 0 < timeout <= 30):
            return False, 'invalid_timeout'
        import math
        if not math.isfinite(timeout):
            return False, 'invalid_timeout'
        snap = self._printer.maintenance.snapshot
        if not isinstance(snap, MaintenanceSnapshot):
            return False, 'no_discovery_snapshot'
        row = next((r for r in self.available() if r.feature_id == feature_id and r.device == device), None)
        if row is None:
            return False, 'information_adapter_unavailable'
        if (not self._printer.state.ready
                or self._printer.state.epoch != row.epoch
                or id(self._printer.state.settings) != row.config_marker):
            return False, 'stale_discovery_snapshot'
        self._row = row
        self._queue = None
        self._deadline = monotonic() + timeout
        self._phase = 'preflight'
        try:
            self._preflight = self._worker.submit(
                lambda: read_queue_evidence(
                    self._client, row.epoch, row.config_marker),
                queue_timeout=timeout)
        except Exception:
            self._reset()
            return False, 'preflight_worker_rejected'
        return True, 'preflight_queued'

    def _reset(self):
        self._phase = None
        self._preflight = None
        self._row = None
        self._queue = None
        self._deadline = 0.0

    def _terminal(self, status, reason):
        row = self._row
        result = ReadResult(
            row.feature_id, row.device, status, '/server/job_queue/status',
            None, (), reason)
        self._reset()
        return result

    def poll(self):
        """Nonblocking owner-thread state transition; no callback mutation."""
        if not self.pending:
            return None
        if self._phase == 'preflight':
            row = self._row
            snap = self._printer.maintenance.snapshot
            # The subscription can disconnect or enter a new epoch before
            # the UI's PrinterData.state has observed the lifecycle change.
            try:
                reader = getattr(self._printer.subscription, 'lifecycle', None)
                live = (reader() if callable(reader) else
                        self._printer.subscription.snapshot(include_settings=False))
                current = (live.get('state') == 'ready'
                           and live.get('epoch') == row.epoch)
            except Exception:
                current = False
            if (not current
                    or not isinstance(snap, MaintenanceSnapshot)
                    or snap.epoch != row.epoch
                    or snap.config_marker != row.config_marker
                    or not self._printer.state.ready
                    or self._printer.state.epoch != row.epoch):
                self._preflight.cancel()
                return self._terminal('ABORTED', 'stale_or_disconnected')
            if monotonic() >= self._deadline:
                self._preflight.cancel()
                return self._terminal('ERROR', 'preflight_timeout')
            if not self._preflight.done():
                return None
            try:
                evidence = self._preflight.result()
            except CancelledError:
                return self._terminal('ABORTED', 'preflight_cancelled')
            except Exception:
                return self._terminal('ERROR', 'preflight_failed')
            if evidence is None:
                return self._terminal('ABORTED', 'job_queue_unknown')
            self._queue = evidence
            remaining = self._deadline - monotonic()
            if remaining <= 0:
                return self._terminal('ERROR', 'preflight_timeout')
            accepted, reason = self._executor.start(row, timeout=remaining)
            if not accepted:
                return self._terminal('ABORTED', reason)
            self._phase = 'reading'
            self._preflight = None
        result = self._executor.poll()
        if result is not None:
            self._reset()
        return result

    def cancel(self):
        """Forget in-flight results; never claim HTTP request was reversed."""
        if not self.pending:
            return None
        if self._phase == 'preflight':
            self._preflight.cancel()
            return self._terminal('ABORTED', 'user_cancelled')
        result = self._executor.cancel()
        self._reset()
        return result

    def close(self):
        self.cancel()
        self._executor.close()
        self._closed = True
        # Shared worker and HTTP client remain owned by PrinterData.
