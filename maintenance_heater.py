"""Consented thermal self-tests; shared worker and completion WebSocket RPC.

A finite Klipper script contains OFF. Cancel or uncertain active safety uses
Klipper emergency_stop (shutdown), never queued ordinary G-code behind a dwell.
No autonomous retries, threads, config writes or acceptance updates.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from urllib.parse import quote

from maintenance_catalog import definition_for
from maintenance_discovery import AUTOMATIC, CALIBRATION
from maintenance_planner import AdapterRegistration, build_plan, visible_plan
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import precheck
from maintenance_thermal import ACTIVE, PID, ThermalSeries, contract, sample, pid_evidence, heater_name


def thermal_adapters():
    return tuple(AdapterRegistration(f, CALIBRATION if f in PID else AUTOMATIC, 'maintenance.thermal.'+f,
                 definition_for(f).evidence_contract,
                 definition_for(f).safety_profile) for f in ACTIVE + PID)


def thermal_plan(snapshot):
    return tuple(r for r in visible_plan(build_plan(snapshot, thermal_adapters()))
                 if r.device == 'heater_bed' or
                 (isinstance(r.device, str) and r.device.startswith('extruder')
                  and (r.device == 'extruder' or r.device[8:].isdigit())))


@dataclass(frozen=True, slots=True)
class ThermalResult:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False
    evidence: tuple = ()


class MaintenanceHeaterController:
    def __init__(self, printer, worker, client):
        self._printer, self._worker, self._client = printer, worker, client
        self._row = self._future = self._command = self._contract = None
        self._phase = None
        self._deadline = self._next = self._started = 0.
        self._queue = None
        self._series = ThermalSeries()
        self._off_matches = 0
        self._closed = self._blocked = False
        self._pid_proof = ()
        self._metric_ok = False
        self._metrics = ()

    @property
    def phase(self):
        return self._phase

    @property
    def pending(self):
        return self._phase is not None

    @property
    def feature_id(self):
        return self._row.feature_id if self._row else None

    @property
    def observation_prompt(self):
        return 'PID completed and OFF seen?' if self.feature_id in PID else 'Heating and safe OFF seen?'

    @property
    def live_text(self):
        c = self._contract
        values = self._series.samples
        if c is None:
            return ()
        return ('Target %.1f C' % c.target,
                'Temp %.1f C' % values[-1].temperature if values else 'Reading temperature',
                '%.0f s / %d samples' % (max(0, monotonic()-self._started), len(values)))

    def available(self):
        return thermal_plan(self._printer.maintenance.snapshot)

    def _current(self):
        try:
            row = self._row
            state = self._printer.state
            raw = self._printer.subscription.lifecycle()
            return (row is not None and state.ready and
                    raw.get('state') == 'ready' and raw.get('epoch') == row.epoch
                    and state.epoch == row.epoch and id(state.settings) == row.config_marker
                    and row in self.available())
        except Exception:
            return False

    def _safe(self, evidence):
        return (self._current() and precheck(self._printer.maintenance.snapshot,
                live_safety_context(self._printer, evidence)).allowed)

    def _read(self, initial=False):
        row = self._row
        evidence = read_queue_evidence(self._client, row.epoch, row.config_marker)
        names = [r.name for r in self._printer.maintenance.snapshot.devices if r.family == 'heater']
        if not names or len(names) > 16 or row.device not in names:
            raise ValueError('heater_inventory_unbounded_or_missing')
        path = '/printer/objects/query?' + '&'.join(quote(n, safe='')+'=temperature,target,power' for n in names)
        if row.feature_id in PID:
            path += '&configfile=save_config_pending,save_config_pending_items'
        reply = self._client.get(path)
        point = sample(reply, row.device)
        status = reply['result']['status']
        c = contract(row.device, self._printer.state.settings, status, row.feature_id) if initial else None
        if not initial:
            for name in names:
                if name != row.device:
                    v = status.get(name, {})
                    if v.get('target') != 0 or v.get('power') != 0:
                        raise ValueError('another_heater_active')
        config = status.get('configfile')
        if initial and row.feature_id in PID and (
                not isinstance(config, Mapping) or config.get('save_config_pending') is not False):
            raise ValueError('existing_or_unknown_pending_config')
        return evidence, point, c, pid_evidence(config, row.device) if row.feature_id in PID else ()

    def start(self, feature_id, device=None, **kwargs):
        if self._closed or self._blocked or self.pending:
            return False, 'thermal_busy_or_locked'
        row = next((r for r in self.available() if r.feature_id == feature_id and r.device == device), None)
        if row is None:
            return False, 'thermal_adapter_unavailable'
        self._row, self._phase = row, 'preflight'
        self._series = ThermalSeries()
        self._off_matches = 0
        self._metrics = self._pid_proof = ()
        self._contract = self._command = None
        self._deadline = monotonic()+12
        try:
            self._future = self._worker.submit(lambda: self._read(True), queue_timeout=8)
        except Exception:
            self._phase = None
            return False, 'thermal_worker_rejected'
        return True, 'thermal_preflight_queued'

    def _finish(self, status, reason, restored=False):
        result = ThermalResult(self.feature_id, self._row.device, status, reason,
                               restored, self._metrics)
        self._phase = None
        self._future = None
        self._command = None
        return result

    def _shutdown(self, reason):
        # Independent high priority JSON-RPC, bypasses G-code mutex/dwell.
        # Never repeat a possibly accepted stimulus. Shutdown is a distinct
        # safety action, guarded against reaching a new printer epoch.
        if self._phase != 'stopping':
            self._blocked = True
            self._stop_reason = reason
            self._phase = 'stopping'
            self._deadline = monotonic()+8
            try:
                epoch = self._row.epoch
                self._stop = self._printer.subscription.request(
                    'printer.emergency_stop',
                    guard=lambda: self._printer.subscription.lifecycle().get('epoch') == epoch)
            except Exception:
                self._stop = None
        return None

    def confirm(self):
        if self.phase != 'await_confirmation':
            return False, 'not_awaiting_thermal_confirmation'
        if monotonic() >= self._deadline or not self._safe(self._queue):
            # User waiting is unlimited; expired evidence only requests
            # another read-only preflight and a new deliberate confirmation.
            f, d = self.feature_id, self._row.device
            self._phase = None
            return self.start(f, d)
        c = self._contract
        row = self._row
        def guard():
            if self._phase not in ('await_confirmation', 'running') or not self._safe(self._queue):
                return False
            try:
                # Dispatch-time status must still be cold and every heater OFF.
                state = live_safety_context(self._printer, self._queue).state
                contract(row.device, state.settings, state.status, row.feature_id)
                return True
            except Exception:
                return False
        try:
            script = ('PID_CALIBRATE HEATER=%s TARGET=%.1f\n%s' %
                      (heater_name(c.device), c.target, c.off)
                      if row.feature_id in PID else c.script)
            if row.feature_id in PID:
                self._command = self._printer.subscription.request(
                    'printer.gcode.script', {'script': script}, guard=guard,
                    request_timeout=900.)
            else:
                self._command = self._printer.subscription.request(
                    'printer.gcode.script', {'script': script}, guard=guard)
        except Exception:
            self._shutdown('thermal_dispatch_unknown')
            return True, 'thermal_shutdown_requested'
        self._series = ThermalSeries()
        self._started = monotonic()
        self._phase = 'running'
        self._deadline = self._started+c.duration+12
        self._next = self._started+1
        self._future = None
        return True, 'bounded_thermal_script_queued'

    def poll(self):
        if not self.pending:
            return None
        now = monotonic()
        if self.phase == 'stopping':
            if self._stop is not None and self._stop.done():
                try:
                    self._stop.result()
                    reason = self._stop_reason+'_klipper_shutdown'
                except Exception:
                    reason = self._stop_reason+'_SHUTDOWN_UNCONFIRMED'
                return self._finish('INCONCLUSIVE', reason)
            if now >= self._deadline:
                return self._finish('INCONCLUSIVE', self._stop_reason+'_SHUTDOWN_UNCONFIRMED')
            return None
        if self.phase in ('await_confirmation', 'await_observation'):
            return None
        if self.phase == 'preflight':
            if not self._current() or now >= self._deadline:
                self._future.cancel()
                return self._finish('BLOCKED', 'thermal_preflight_stale')
            if not self._future.done():
                return None
            try:
                evidence, point, c, _ = self._future.result()
                if not self._safe(evidence):
                    raise ValueError('thermal_safety_denied')
                self._series.add(point)
            except Exception:
                return self._finish('BLOCKED', 'cold_idle_thermal_preflight_required')
            self._queue, self._contract = evidence, c
            self._future = None
            self._phase = 'await_confirmation'
            self._deadline = min(now+3, evidence.observed_at+3)
            return None
        if not self._current():
            return self._shutdown('thermal_connection_or_epoch_changed')
        # Local print/operation checks use a fresh subscription every tick.
        if not precheck(self._printer.maintenance.snapshot,
                        live_safety_context(self._printer, self._queue)).allowed:
            return self._shutdown('thermal_operation_conflict')
        if self._command is not None and self._command.done():
            try:
                self._command.result()
            except Exception:
                return self._shutdown('thermal_script_failed_or_ambiguous')
        if now >= self._deadline:
            return self._shutdown('thermal_deadline_or_off_unverified')
        if self._future is None:
            if now < self._next:
                return None
            try:
                self._future = self._worker.submit(self._read, queue_timeout=3)
                self._read_deadline = now+5
            except Exception:
                return self._shutdown('thermal_read_worker_unavailable')
            return None
        if not self._future.done():
            if now >= self._read_deadline:
                return self._shutdown('thermal_read_timeout')
            return None
        try:
            evidence, point, _, proof = self._future.result()
            if not self._safe(evidence):
                raise ValueError('thermal_guard_failed')
            self._series.add(point)
            if self.feature_id in PID:
                # Keep continuity proof without retaining a 15-minute trace.
                self._series.samples[:] = self._series.samples[-2:]
                if proof:
                    self._pid_proof = proof
            c = self._contract
            if not c.min_temp <= point.temperature < c.ceiling:
                raise ValueError('thermal_temperature_limit')
            elapsed = now-self._started
            finished = (self._command.done() if self.feature_id in PID else elapsed >= c.duration)
            if self.phase == 'running' and not finished:
                if point.target not in ((c.target, c.target-5) if self.feature_id in PID else (c.target,)):
                    raise ValueError('thermal_target_drift')
            elif point.target != 0 or point.power != 0:
                self._off_matches = 0
            else:
                self._off_matches += 1
            self._queue = evidence
        except Exception:
            return self._shutdown('thermal_sample_or_safety_invalid')
        self._future = None
        self._next = now+1
        if (self.phase == 'running' and finished
                and self._command.done() and self._off_matches >= 2):
            self._phase = 'verifying'
            self._deadline = now+42
            self._cool_started = point.eventtime
        if self.phase == 'verifying' and point.eventtime-self._cool_started >= 32:
            try:
                if self.feature_id in PID:
                    self._metric_ok, self._metrics = bool(self._pid_proof), self._pid_proof
                else:
                    self._metric_ok, self._metrics = self._series.evaluate(self.feature_id, self._contract.target)
            except ValueError:
                return self._finish('INCONCLUSIVE', 'thermal_measurement_incomplete', True)
            self._phase = 'await_observation'
        return None

    def observe(self, seen):
        if self.phase != 'await_observation' or type(seen) is not bool:
            return None
        return self._finish(
            'PASSED_USER' if seen and self._metric_ok else 'FAILED_USER' if not seen else 'INCONCLUSIVE',
            'thermal_metric_and_user_observation' if self._metric_ok else 'thermal_metric_not_satisfied',
            True)

    def cancel(self):
        if self.phase in ('running', 'verifying', 'stopping'):
            return self._shutdown('user_cancelled_thermal')
        if self.pending:
            if self._future is not None:
                self._future.cancel()
            return self._finish('ABORTED', 'user_cancelled_before_heat')
        return None

    def close(self):
        self.cancel()
        self._closed = True


class MaintenancePhysicalRouter:
    """One UI operation owner for pulse and thermal domains."""
    def __init__(self, pulse, heater):
        self._pulse, self._heater = pulse, heater
        self._active = pulse

    def __getattr__(self, key):
        return getattr(self._active, key)

    @property
    def pending(self):
        return self._pulse.pending or self._heater.pending

    def available(self):
        return self._pulse.available() + self._heater.available()

    def start(self, feature_id, device=None, **kwargs):
        if self.pending:
            return False, 'maintenance_busy'
        self._active = self._heater if feature_id.startswith('H') else self._pulse
        return self._active.start(feature_id, device, **kwargs)

    def close(self):
        self._pulse.close()
        self._heater.close()
