"""Operator-paced physical endstop checks; no passive driver tests."""
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from maintenance_catalog import definition_for
from maintenance_discovery import USER
from maintenance_planner import AdapterRegistration, build_plan, visible_plan
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import precheck


def switch_adapters():
    return (AdapterRegistration('M01', USER, 'maintenance.motion.M01',
        definition_for('M01').evidence_contract,
        definition_for('M01').safety_profile),)


def switch_plan(snapshot):
    return tuple(r for r in visible_plan(build_plan(snapshot, switch_adapters()))
                 if r.feature_id == 'M01'
                 and r.device in ('stepper_x', 'stepper_y', 'stepper_z'))


@dataclass(frozen=True, slots=True)
class MotionObservation:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False
    evidence: tuple = ()


class MaintenanceSwitchController:
    def __init__(self, printer, worker, client):
        self._printer, self._worker, self._client = printer, worker, client
        self._phase = self._row = self._future = None
        self._closed = False
        self._deadline = 0.
        self._step = 0
        self._last = ''

    @property
    def pending(self):
        return self._phase is not None

    @property
    def phase(self):
        return self._phase

    @property
    def feature_id(self):
        return self._row.feature_id if self._row else None

    @property
    def observation_prompt(self):
        return 'Switch responded correctly?'


    @property
    def live_text(self):
        return (self._last,) if self._last else ()

    @property
    def prompt(self):
        axis = self._row.device[-1].upper()
        return ('Release %s switch' % axis, 'Hold %s switch pressed' % axis,
                'Release %s switch' % axis)[self._step]

    def available(self):
        return switch_plan(self._printer.maintenance.snapshot)

    def _current(self):
        try:
            row = self._row
            raw = self._printer.subscription.lifecycle()
            return (row in self.available() and self._printer.state.ready
                    and raw.get('state') == 'ready' and raw.get('epoch') == row.epoch
                    and self._printer.state.epoch == row.epoch
                    and id(self._printer.state.settings) == row.config_marker)
        except Exception:
            return False

    def _work(self):
        row = self._row
        evidence = read_queue_evidence(self._client, row.epoch, row.config_marker)
        if not self._current() or not precheck(self._printer.maintenance.snapshot,
                live_safety_context(self._printer, evidence)).allowed:
            raise ValueError('motion_read_guard_failed')
        if row.feature_id == 'M01':
            cfg = self._printer.state.settings.get(row.device)
            pin = cfg.get('endstop_pin') if isinstance(cfg, Mapping) else None
            if not isinstance(pin, str) or not pin or 'virtual_endstop' in pin:
                raise ValueError('physical_switch_unverified')
            reply = self._client.get('/printer/query_endstops/status')
            result = reply.get('result') if isinstance(reply, Mapping) else None
            # Klipper returns registered names (stepper_x); some versions
            # expose the documented short axis alias (x). Never prefer a
            # contradictory alias or silently accept an invalid primary value.
            if not isinstance(result, Mapping):
                raise ValueError('endstop_state_unknown')
            keys = (row.device, row.device[-1])
            values = [result[k] for k in keys if k in result]
            if len(values)==2 and values[0]!=values[1]:
                raise ValueError('endstop_state_conflicting')
            value = values[0] if values else None
            if value not in ('open', 'TRIGGERED'):
                raise ValueError('endstop_state_unknown')
            return evidence, value
        raise ValueError('unsupported_switch_feature')

    def _schedule(self):
        self._phase = 'preflight'
        self._deadline = monotonic()+10
        try:
            self._future = self._worker.submit(self._work, queue_timeout=6)
        except Exception:
            self._phase = None
            return False, 'motion_read_worker_rejected'
        return True, 'motion_read_queued'

    def start(self, feature_id, device=None, **kwargs):
        if self._closed or self.pending:
            return False, 'motion_read_busy'
        row = next((r for r in self.available() if r.feature_id == feature_id and r.device == device), None)
        if row is None:
            return False, 'motion_observer_unavailable'
        self._row, self._step, self._last = row, 0, ''
        if feature_id == 'M01':
            # Opening this screen never even queries the switch until the
            # operator explicitly says the released switch is ready.
            self._phase = 'await_confirmation'
            return True, 'release_switch_then_confirm'
        return self._schedule()

    def confirm(self):
        if self.phase not in ('await_confirmation', 'await_press', 'await_release'):
            return False, 'not_waiting_for_switch'
        return self._schedule()

    def _finish(self, status, reason, restored=False, evidence=()):
        result = MotionObservation(self.feature_id, self._row.device, status, reason, restored, evidence)
        self._phase = self._future = None
        return result

    def poll(self):
        if self.phase != 'preflight':
            return None  # Every operator question is unbounded.
        if not self._current() or monotonic() >= self._deadline:
            self._future.cancel()
            return self._finish('INCONCLUSIVE', 'motion_read_stale_or_timeout')
        if not self._future.done():
            return None
        try:
            evidence, value = self._future.result()
            if not precheck(self._printer.maintenance.snapshot,
                    live_safety_context(self._printer, evidence)).allowed:
                raise ValueError('motion_state_changed')
        except Exception:
            return self._finish('INCONCLUSIVE', 'switch_or_driver_read_unavailable')
        self._future = None
        expected = ('open', 'TRIGGERED', 'open')[self._step]
        self._last = 'Read: '+value
        if value != expected:
            self._phase = ('await_confirmation', 'await_press', 'await_release')[self._step]
            return None  # A premature click may be retried explicitly.
        self._step += 1
        if self._step == 3:
            self._phase = 'await_observation'
        else:
            self._phase = ('await_confirmation', 'await_press', 'await_release')[self._step]
        return None

    def observe(self, seen):
        if self.phase != 'await_observation' or type(seen) is not bool:
            return None
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
            'physical_switch_open_triggered_open', True,
            (('transitions', 'open > TRIGGERED > open'),))

    def cancel(self):
        if self._future is not None:
            self._future.cancel()
        if self.pending:
            return self._finish('ABORTED', 'user_cancelled_observation')
        return None

    def close(self):
        self.cancel()
        self._closed = True
