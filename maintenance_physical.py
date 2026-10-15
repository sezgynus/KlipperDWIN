"""On-demand, consented Maintenance pulse runner using existing Petrel transports.

One bounded G-code script contains the output's original-state restore.
A transport failure may be ambiguous: NEVER report user PASS without fresh
readback confirming the restored value. No timers/threads/polling at startup.
"""
from collections.abc import Mapping
from concurrent.futures import CancelledError
from dataclasses import dataclass
import math
import re
from time import monotonic
from urllib.parse import quote

from maintenance_guided import guided_plan, GuidedConsentGate
from maintenance_pulse import compile_pulse, restored
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import MaintenanceSafetyCoordinator

_OUTPUT = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')


@dataclass(frozen=True, slots=True)
class PhysicalResult:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False


def _object_name(row, buzzer):
    if row.feature_id == 'S18':
        if not isinstance(buzzer, str) or not _OUTPUT.fullmatch(buzzer):
            raise ValueError('invalid_buzzer_output')
        return 'pwm_cycle_time ' + buzzer
    return row.device


def _read_target(client, name):
    """Small exact-object GET; never store the entire Moonraker reply."""
    if not isinstance(name, str) or not name or len(name) > 96:
        return None
    reply = client.get('/printer/objects/query?' + quote(name, safe=''))
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    return status if isinstance(status, Mapping) else None


class MaintenancePulseController:
    """Explicit interactive state machine; no automatic test entry or PASS."""

    __slots__ = ('_printer', '_client', '_worker', '_gate', '_safety',
                 '_row', '_program', '_evidence', '_future', '_phase',
                 '_deadline', '_token', '_buzzer', '_cancelled', '_closed',
                 '_blocked')

    def __init__(self, printer, worker, client):
        self._printer = printer
        self._worker = worker
        self._client = client
        self._gate = GuidedConsentGate()
        self._safety = MaintenanceSafetyCoordinator()
        self._row = None
        self._program = None
        self._evidence = None
        self._future = None
        self._phase = None
        self._deadline = 0.0
        self._token = None
        self._buzzer = None
        self._cancelled = False
        self._closed = False
        self._blocked = False

    @property
    def phase(self):
        return self._phase

    @property
    def pending(self):
        return self._phase is not None

    @property
    def observation_prompt(self):
        return (self._program.observation if self._program is not None
                and self._phase == 'await_observation' else None)

    def available(self):
        return guided_plan(self._printer.maintenance.snapshot)

    def _snapshot(self):
        return self._printer.maintenance.snapshot

    def _context(self):
        return live_safety_context(self._printer, self._evidence)

    def _current(self):
        row, snap = self._row, self._snapshot()
        return (row is not None and row in guided_plan(snap)
                and self._printer.state.ready
                and row.epoch == self._printer.state.epoch
                and id(self._printer.state.settings) == row.config_marker)

    def _release(self):
        self._gate.cancel()
        self._safety.clear()
        self._row = self._program = self._evidence = self._future = None
        self._phase = None
        self._deadline = 0.0
        self._token = self._buzzer = None
        self._cancelled = False

    def _finish(self, status, reason, verified=False):
        row = self._row
        result = PhysicalResult(row.feature_id, row.device, status, reason, verified)
        self._release()
        return result

    def start(self, feature_id, device=None, *, buzzer_output=None, timeout=12.0):
        """Preflight only; no physical output until a later confirm() action."""
        if self._closed or self.pending or self._blocked:
            return False, 'busy_closed_or_restore_unconfirmed'
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 3 <= timeout <= 30:
            return False, 'invalid_timeout'
        reader = getattr(self._printer, 'maintenance_reader', None)
        if reader is not None and reader.pending:
            return False, 'information_read_active'
        row = next((r for r in self.available()
                    if r.feature_id == feature_id and r.device == device), None)
        if row is None:
            return False, 'test_not_discovered_or_allowed'
        try:
            target = _object_name(row, buzzer_output)
        except ValueError:
            return False, 'invalid_hardware_identifier'
        self._row, self._buzzer = row, buzzer_output
        self._phase = 'preflight'
        self._deadline = monotonic() + timeout

        def preflight():
            # Both GETs run in the existing bounded Maintenance read worker.
            evidence = read_queue_evidence(self._client, row.epoch, row.config_marker)
            if evidence is None:
                return None
            snap = self._snapshot()
            if (not self._current() or
                    not self._safety_check(snap, evidence)):
                return None
            state = _read_target(self._client, target)
            if state is None:
                return None
            program = compile_pulse(row, snap, state,
                                    self._printer.state.settings,
                                    buzzer_output=buzzer_output)
            return evidence, program

        try:
            self._future = self._worker.submit(preflight, queue_timeout=timeout)
        except Exception:
            self._release()
            return False, 'worker_unavailable'
        return True, 'preflight_queued'

    def _safety_check(self, snap, evidence):
        from maintenance_safety import precheck
        return precheck(snap, live_safety_context(self._printer, evidence)).allowed

    def poll(self):
        """Nonblocking progress. Only explicit caller polling advances a test."""
        if not self.pending:
            return None
        now = monotonic()
        if self._phase == 'preflight':
            if not self._current():
                self._future.cancel()
                return self._finish('ABORTED', 'state_changed')
            if now >= self._deadline:
                self._future.cancel()
                return self._finish('ABORTED', 'preflight_timeout')
            if not self._future.done():
                return None
            try:
                found = self._future.result()
            except (Exception):
                return self._finish('BLOCKED', 'preflight_failed')
            if found is None:
                return self._finish('BLOCKED', 'preflight_not_verified')
            evidence, program = found
            self._evidence, self._program = evidence, program
            snapshot = self._snapshot()
            token, reason = self._gate.arm(
                self._row, snapshot, self._context(), timeout=3.0)
            if token is None:
                return self._finish('BLOCKED', reason)
            self._token = token
            self._phase = 'await_confirmation'
            self._deadline = min(now + 3, evidence.observed_at + 3)
            self._future = None
            return None
        if self._phase == 'await_confirmation':
            if now >= self._deadline or not self._current() or not self._safety_check(self._snapshot(), self._evidence):
                return self._finish('ABORTED', 'confirmation_expired_or_unsafe')
            return None
        if self._phase == 'running':
            if now >= self._deadline and not self._future.done():
                # A timed-out POST may still execute. Lock this runner until
                # a new controller is created; never repeat ambiguous writes.
                self._blocked = True
                return self._finish('INCONCLUSIVE', 'command_may_still_be_running')
            if not self._future.done():
                return None
            try:
                self._future.result()
            except Exception:
                self._blocked = True
                return self._finish('INCONCLUSIVE', 'script_failed_or_restore_unknown')
            self._phase = 'verifying'
            self._deadline = now + 6
            name = self._program.object_name
            try:
                self._future = self._worker.submit(
                    lambda: _read_target(self._client, name), queue_timeout=5)
            except Exception:
                return self._finish('INCONCLUSIVE', 'verification_unavailable')
            return None
        if self._phase == 'verifying':
            if now >= self._deadline:
                self._future.cancel()
                return self._finish('INCONCLUSIVE', 'restore_readback_timeout')
            if not self._future.done():
                return None
            try:
                values = self._future.result()
            except Exception:
                return self._finish('INCONCLUSIVE', 'restore_readback_failed')
            if (not self._current() or
                    not restored(self._program, values)):
                return self._finish('INCONCLUSIVE', 'restore_not_verified')
            if self._cancelled:
                return self._finish('ABORTED', 'user_cancelled_after_restore', True)
            self._phase = 'await_observation'
            self._deadline = now + 30
            self._future = None
            return None
        if self._phase == 'await_observation' and now >= self._deadline:
            return self._finish('INCONCLUSIVE', 'observation_timeout', True)
        return None

    def confirm(self):
        """A second, deliberate user action starts the guarded G-code script."""
        if self._phase != 'await_confirmation':
            return False, 'not_awaiting_confirmation'
        if (monotonic() >= self._deadline or not self._current()):
            self._release()
            return False, 'expired_or_changed'
        snap, context = self._snapshot(), self._context()
        result, reason = self._gate.approve(self._token, snap, context)
        if result is None:
            self._release()
            return False, reason
        decision, session = self._safety.begin(snap, context)
        if not decision.allowed:
            self._release()
            return False, decision.reason
        program = self._program

        def guard():
            return (self._current() and
                    self._safety.guard(session, self._snapshot(), self._context()).allowed)

        try:
            self._future = self._printer.postREST(
                '/printer/gcode/script', json={'script': program.script},
                report_error=False, dispatch_guard=guard)
        except Exception:
            self._release()
            return False, 'command_queue_rejected'
        self._phase = 'running'
        self._deadline = monotonic() + 9
        return True, 'bounded_pulse_queued'

    def observe(self, seen):
        """Human observation is separate from a command or reported PWM."""
        if self._phase != 'await_observation' or type(seen) is not bool:
            return None
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
                            'explicit_user_observation', True)

    def cancel(self):
        if not self.pending:
            return None
        if self._phase in ('running', 'verifying'):
            # Never cancel a potentially already executing restoration script.
            self._cancelled = True
            return None
        return self._finish('ABORTED', 'cancelled_before_dispatch')

    def close(self):
        self.cancel()
        self._closed = True
        # Shared client/worker are owned by PrinterData.
