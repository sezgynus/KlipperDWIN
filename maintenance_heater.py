"""Consented thermal self-tests; shared worker and completion WebSocket RPC.

A finite Klipper script contains OFF. Cancel or uncertain active safety uses
Klipper emergency_stop (shutdown), never queued ordinary G-code behind a dwell.
No autonomous retries, threads, config writes or acceptance updates.
"""
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from urllib.parse import quote

from maintenance_catalog import definition_for
from maintenance_thermal_profiles import profile_for
from maintenance_discovery import AUTOMATIC, CALIBRATION
from maintenance_planner import AdapterRegistration, build_plan, visible_plan
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import precheck
from maintenance_thermal import ACTIVE, PID, ThermalSeries, contract, sample, pid_evidence, heater_name


_LOG = logging.getLogger(__name__)


def thermal_adapters():
    return tuple(AdapterRegistration(f, CALIBRATION if f in PID else AUTOMATIC, 'maintenance.thermal.'+f,
                 definition_for(f).evidence_contract,
                 definition_for(f).safety_profile) for f in ACTIVE + PID)


def thermal_plan(snapshot):
    return tuple(r for r in visible_plan(build_plan(snapshot, thermal_adapters()))
                 if r.device == 'heater_bed' or
                 (isinstance(r.device, str) and r.device.startswith('extruder')
                  and (r.device == 'extruder' or r.device[8:].isdigit())) or
                 (isinstance(r.device, str) and r.device.startswith('heater_generic ')
                  and profile_for(snapshot, r.device) is not None))


@dataclass(frozen=True, slots=True)
class ThermalResult:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False
    evidence: tuple = ()
    components: tuple = ()


# These catalog IDs share one finite H01 heating/cooling observation.
# PID calibration H02/H03/H04 stays independent.
THERMAL_GROUP = ('H01', 'H05', 'H06', 'H07', 'H08', 'H09', 'H13')
THERMAL_PRIMARY = {'H01': 'rise_c', 'H05': 'heating_c_per_s',
                   'H06': 'time_to_target_s', 'H07': 'overshoot_c',
                   'H08': 'stability_peak_to_peak_c',
                   'H09': 'cooling_c_per_s', 'H13': 'rise_c'}


class MaintenanceHeaterController:
    def __init__(self, printer, worker, client):
        self._printer, self._worker, self._client = printer, worker, client
        self._row = self._future = self._command = self._contract = None
        self._phase = None
        self._deadline = self._next = self._started = 0.
        self._queue = None
        self._series = ThermalSeries()
        self._last_read_point = None
        self._off_matches = 0
        self._closed = self._blocked = False
        self._pid_proof = ()
        self._pid_saw_power = self._pid_reached = False
        self._metric_ok = False
        self._metrics = ()
        self._component_metrics = ()
        self._refreshing_consent = False

    @property
    def phase(self):
        return self._phase

    @property
    def pending(self):
        return self._phase is not None

    @property
    def refreshing_consent(self):
        return self._phase == 'preflight' and self._refreshing_consent

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
        if self._phase in ('preflight', 'await_confirmation'):
            return ('Target %.1f C' % c.target,
                    'Checking safety...' if self.refreshing_consent else
                    'Ready for confirmation',
                    '%d samples' % len(values))
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
        c = contract(row.device, self._printer.state.settings, status, row.feature_id,
                     profile_for(self._printer.maintenance.snapshot, row.device)) if initial else None
        if not initial:
            for name in names:
                if name != row.device:
                    v = status.get(name, {})
                    if (type(v.get('target')) not in (int, float) or v.get('target') != 0
                            or type(v.get('power')) not in (int, float) or v.get('power') != 0):
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
        self._metrics = self._pid_proof = self._component_metrics = ()
        self._pid_saw_power = self._pid_reached = False
        self._contract = self._command = None
        self._refreshing_consent = False
        self._started = 0.
        self._ack_seen = False
        self._dispatch_rejected = False
        self._deadline = monotonic()+12
        try:
            self._future = self._worker.submit(lambda: self._read(True), queue_timeout=8)
        except Exception:
            self._phase = None
            return False, 'thermal_worker_rejected'
        return True, 'thermal_preflight_queued'

    def _finish(self, status, reason, restored=False, components=()):
        result = ThermalResult(self.feature_id, self._row.device, status, reason,
                               restored, self._metrics, components)
        _LOG.info('Thermal result feature=%s heater=%s status=%s reason=%s restored=%s',
                  self.feature_id, self._row.device, status, reason, restored)
        self._phase = None
        self._future = None
        self._command = None
        self._refreshing_consent = False
        return result

    def _shutdown(self, reason):
        # Independent high priority JSON-RPC, bypasses G-code mutex/dwell.
        # Never repeat a possibly accepted stimulus. Shutdown is a distinct
        # safety action, guarded against reaching a new printer epoch.
        if self._phase != 'stopping':
            # Log BEFORE the RPC: Klipper shutdown UI can replace Result before
            # the operator sees it. Only bounded diagnostic scalars, no payloads.
            now = monotonic()
            point = self._last_read_point
            previous = self._series.samples[-1] if self._series.samples else None
            try:
                _LOG.error(
                    'Thermal shutdown feature=%s heater=%s reason=%s phase=%s '
                    'elapsed_s=%.3f queue_age_s=%s samples=%d '
                    'sample_eventtime=%s temperature=%s target=%s power=%s '
                    'previous_eventtime=%s command_done=%s',
                    self.feature_id, self._row.device, reason, self._phase,
                    max(0., now-self._started),
                    now-self._queue.observed_at if self._queue is not None else None,
                    len(self._series.samples),
                    getattr(point, 'eventtime', None),
                    getattr(point, 'temperature', None),
                    getattr(point, 'target', None), getattr(point, 'power', None),
                    getattr(previous, 'eventtime', None),
                    self._command.done() if self._command is not None else None)
            except Exception:
                pass  # A diagnostic failure must never prevent emergency stop.
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
            # Retain this exact operator click across one read-only safety
            # refresh. The new preflight must prove cold/idle/queue safety,
            # and the dispatch guard checks again immediately before send.
            # Never reuse the old queue evidence or blindly start heating.
            if not self._current():
                return False, 'thermal_confirmation_stale_session'
            self._refreshing_consent = True
            self._phase = 'preflight'
            self._queue = None
            # The earlier preflight sample can be arbitrarily old while the
            # operator reads the screen. Never splice it into a fresh
            # bounded-gap thermal series (max 5s between samples).
            self._series = ThermalSeries()
            self._deadline = monotonic() + 12
            try:
                self._future = self._worker.submit(
                    lambda: self._read(True), queue_timeout=8)
            except Exception:
                self._refreshing_consent = False
                self._phase = None
                self._future = None
                return False, 'thermal_refresh_worker_rejected'
            return True, 'thermal_confirmation_safety_refresh'
        return self._dispatch_confirmed()

    def _dispatch_confirmed(self):
        # Called only after one explicit user confirmation and fresh positive
        # safety, either immediately or when its read-only refresh completes.
        c = self._contract
        row = self._row
        def guard():
            if self._phase not in ('await_confirmation', 'running') or not self._safe(self._queue):
                self._dispatch_rejected = True
                return False
            try:
                # Dispatch-time status must still be cold and every heater OFF.
                state = live_safety_context(self._printer, self._queue).state
                contract(row.device, state.settings, state.status, row.feature_id,
                         profile_for(self._printer.maintenance.snapshot, row.device))
                return True
            except Exception:
                self._dispatch_rejected = True
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
        _LOG.info('Thermal script queued feature=%s heater=%s target=%s duration_s=%s',
                  self.feature_id, row.device, c.target, c.duration)
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
            if self._refreshing_consent:
                # A successful refreshed preflight consumes the existing
                # consent exactly once; no second 'Run thermal test' screen.
                self._refreshing_consent = False
                self._phase = 'await_confirmation'
                if not self._safe(self._queue):
                    return self._finish('BLOCKED', 'thermal_refreshed_safety_stale')
                self._dispatch_confirmed()
                return None
            self._phase = 'await_confirmation'
            self._deadline = min(now+3, evidence.observed_at+3)
            return None
        if not self._current():
            return self._shutdown('thermal_connection_or_epoch_changed')
        # Consume completed evidence BEFORE judging the previous queue sample.
        # Otherwise a slow HTTP round trip can trigger shutdown despite a fresh
        # successful response already waiting on the worker.
        if self._future is not None and self._future.done():
            try:
                self._queue = self._future.result()[0]
            except Exception:
                return self._shutdown('thermal_read_failed')
        # Admission/dispatch retain the strict 3 s limit. During an active
        # script, allow the same bounded 5 s window as the telemetry watchdog;
        # print/operation/epoch checks still use the live subscription each tick.
        decision = precheck(self._printer.maintenance.snapshot,
                           live_safety_context(self._printer, self._queue,
                                               queue_max_age=5.))
        if not decision.allowed:
            return self._shutdown('thermal_operation_conflict_'+decision.reason)
        if self._command is not None and self._command.done():
            try:
                self._command.result()
                if not self._ack_seen:
                    self._ack_seen = True
                    self._deadline = min(self._deadline, now+8)
            except Exception:
                if self._dispatch_rejected:
                    return self._finish('BLOCKED', 'thermal_dispatch_guard_denied_before_send')
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
            self._last_read_point = point
            if not self._current() or not precheck(
                    self._printer.maintenance.snapshot,
                    live_safety_context(self._printer, evidence, queue_max_age=5.)).allowed:
                raise ValueError('thermal_guard_failed')
            self._series.add(point)
            if self.feature_id in PID:
                # Keep continuity proof without retaining a 15-minute trace.
                self._series.samples[:] = self._series.samples[-2:]
                self._pid_saw_power |= point.power > 0
                self._pid_reached |= point.temperature >= self._contract.target - 5
                if proof:
                    self._pid_proof = proof
            c = self._contract
            if not c.min_temp <= point.temperature < c.ceiling:
                raise ValueError('thermal_temperature_limit')
            if self.phase == 'verifying' and (point.target != 0 or point.power != 0):
                raise ValueError('heater_reactivated_during_cooling')
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
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'read_or_protocol_error'
            return self._shutdown('thermal_sample_or_safety_invalid_'+reason)
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
                    self._metric_ok = bool(self._pid_proof) and self._pid_saw_power and self._pid_reached
                    self._metrics = self._pid_proof + (('heated_to_target_band', self._pid_reached),)
                else:
                    self._metric_ok, self._metrics = self._series.evaluate(self.feature_id, self._contract.target)
                    if self.feature_id == THERMAL_GROUP[0]:
                        # Calculate all seven criteria once from the *same*
                        # bounded trajectory. No additional actuation or reads.
                        measures = []
                        for feature in THERMAL_GROUP:
                            passed, metrics = self._series.evaluate(feature, self._contract.target)
                            primary = THERMAL_PRIMARY[feature]
                            measured = dict(metrics)
                            # Missing primary evidence is inconclusive, not a
                            # failed measured performance criterion.
                            evidence = tuple(pair for pair in metrics
                                             if pair[0] in (primary, 'samples', 'span_s'))
                            measures.append((feature, passed, primary in measured,
                                             evidence))
                        self._component_metrics = tuple(measures)
            except ValueError:
                return self._finish('INCONCLUSIVE', 'thermal_measurement_incomplete', True)
            self._phase = 'await_observation'
        return None

    def observe(self, seen):
        if self.phase != 'await_observation' or type(seen) is not bool:
            return None
        if self.feature_id == THERMAL_GROUP[0] and self._component_metrics:
            children = []
            for feature, passed, has_evidence, evidence in self._component_metrics:
                status = ('FAILED_USER' if not seen else
                          'INCONCLUSIVE' if not has_evidence else
                          'PASSED_USER' if passed else 'FAILED_METRIC')
                reason = ('user_not_observed' if not seen else
                          'thermal_metric_incomplete' if not has_evidence else
                          'thermal_metric_and_user_observation' if passed else
                          'thermal_metric_not_satisfied')
                children.append(ThermalResult(feature, self._row.device,
                                              status, reason, True, evidence))
            outcomes = tuple(children)
            status = ('FAILED_USER' if not seen else
                      'INCONCLUSIVE' if any(c.status == 'INCONCLUSIVE' for c in outcomes) else
                      'FAILED_METRIC' if any(c.status == 'FAILED_METRIC' for c in outcomes) else
                      'PASSED_USER')
            return self._finish(status, 'thermal_group_seven_independent_results',
                                True, outcomes)
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
    def __init__(self, pulse, heater, motion=None, switches=None, probe=None, resonance=None, filament=None, panel=None, auxiliary=None):
        self._pulse, self._heater = pulse, heater
        self._motion, self._switches, self._probe = motion, switches, probe
        self._resonance, self._filament, self._panel, self._auxiliary = resonance, filament, panel, auxiliary
        self._owners = tuple(x for x in (pulse, heater, motion, switches, probe, resonance, filament, panel, auxiliary) if x is not None)
        self._active = pulse

    def __getattr__(self, key):
        return getattr(self._active, key)

    @property
    def pending(self):
        return any(owner.pending for owner in self._owners)

    def available(self):
        rows = tuple(row for owner in self._owners for row in owner.available())
        # One visible thermal characterization entry per heater, while the
        # seven original discovery/catalog IDs remain independently tracked.
        grouped = {row.device for row in rows if row.feature_id == THERMAL_GROUP[0]}
        return tuple(row for row in rows if row.feature_id not in THERMAL_GROUP[1:]
                     or row.device not in grouped)

    def start(self, feature_id, device=None, **kwargs):
        if self.pending:
            return False, 'maintenance_busy'
        self._active = (self._auxiliary if feature_id in ('O01','O02','O06') else
                        self._panel if feature_id in ('S15','S16','S17') else
                        self._filament if feature_id.startswith('E') else
                        self._resonance if feature_id.startswith('R') else
                        self._probe if feature_id.startswith('P') else
                        self._switches if feature_id in ('M01', 'M10') else
                        self._motion if feature_id.startswith('M') else
                        self._heater if feature_id.startswith('H') else self._pulse)
        if self._active is None:
            self._active = self._pulse
            return False, 'motion_adapter_unavailable'
        return self._active.start(feature_id, device, **kwargs)

    def close(self):
        for owner in self._owners:
            owner.close()
