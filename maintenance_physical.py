"""On-demand, consented Maintenance pulse runner using existing Petrel transports.

One bounded G-code script contains the output's original-state restore.
A transport failure may be ambiguous: NEVER report user PASS without fresh
readback confirming the restored value. No timers/threads/polling at startup.
"""
from collections.abc import Mapping
from concurrent.futures import CancelledError
from dataclasses import dataclass
import logging
import math
import re
from time import monotonic
from urllib.parse import quote

from maintenance_guided import guided_plan, GuidedConsentGate
from maintenance_pulse import compile_pulse, compile_mmu_led_pulse, restored, f12_round_program, f12_stage_program
from maintenance_f12 import F12Bracket
from maintenance_hh_leds import mmu_led_owners
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import MaintenanceSafetyCoordinator

_OUTPUT = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
_MMU_UNIT = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,47}\Z')
# Allow the bounded pulse to complete and Moonraker status to catch up.
# No sleeps or extra threads: the existing UI tick schedules read-only GETs.
_VERIFY_MIN_AFTER_ACK_S = 0.25
_VERIFY_MIN_AFTER_DISPATCH_S = 0.35
_VERIFY_RETRY_INTERVAL_S = 0.30
_VERIFY_WINDOW_S = 6.0
_VERIFY_MATCHES_REQUIRED = 2


@dataclass(frozen=True, slots=True)
class PhysicalResult:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False


def _object_name(row):
    name = row.device
    if row.feature_id in ('S18', 'O03'):
        prefix = 'pwm_cycle_time ' if row.feature_id == 'S18' else 'output_pin '
        if (not isinstance(name, str) or not name.startswith(prefix)
                or not _OUTPUT.fullmatch(name[len(prefix):])):
            raise ValueError('invalid_actuator_target')
    return name


def _read_target(client, name):
    """Small exact-object GET; never store the entire Moonraker reply."""
    if not isinstance(name, str) or not name or len(name) > 96:
        return None
    reply = client.get('/printer/objects/query?' + quote(name, safe=''))
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    return status if isinstance(status, Mapping) else None



def _read_targets(client, names):
    """Read bounded, specifically identified objects in one Moonraker call."""
    if (not isinstance(names, (tuple, list)) or not 1 <= len(names) <= 10
            or len(names) != len(set(names))
            or any(not isinstance(name, str) or len(name) > 96
                   or not (name in ('mmu', 'mmu_machine') or
                           (name.startswith('mmu_leds ') and
                            _MMU_UNIT.fullmatch(name.split(' ', 1)[1])))
                   for name in names)):
        raise ValueError('mmu_led_query_targets_invalid')
    reply = client.get('/printer/objects/query?' +
                       '&'.join(quote(name, safe='') for name in names))
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    return status if isinstance(status, Mapping) else None




def _resolve_pin_gcode_name(client, object_name, settings):
    """Resolve the *case-sensitive* SET_PIN mux name from original config.

    Klipper's configfile.settings lowercases section names, while its
    configfile.config preserves the actual section spelling used when
    registering the SET_PIN PIN mux value. Never guess capitalization or
    accept a name based only on the HTTP error's suggested options.
    """
    if not isinstance(object_name, str) or not isinstance(settings, Mapping):
        raise ValueError('invalid_output_target')
    kind, sep, configured_name = object_name.partition(' ')
    if (kind not in ('pwm_cycle_time', 'output_pin') or not sep
            or not _OUTPUT.fullmatch(configured_name)):
        raise ValueError('invalid_output_target')
    expected_pin = settings.get('pin')
    if not isinstance(expected_pin, str) or not expected_pin.strip():
        raise ValueError('buzzer_config_pin_missing')
    reply = client.get('/printer/objects/query?configfile')
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    configfile = status.get('configfile') if isinstance(status, Mapping) else None
    raw = configfile.get('config') if isinstance(configfile, Mapping) else None
    if not isinstance(raw, Mapping):
        raise ValueError('buzzer_original_config_unavailable')
    matches = []
    for section, section_config in raw.items():
        if not isinstance(section, str) or not section.startswith(kind + ' '):
            continue
        actual = section.split(' ', 1)[1]
        if actual.casefold() != configured_name.casefold():
            continue
        if not _OUTPUT.fullmatch(actual) or not isinstance(section_config, Mapping):
            raise ValueError('buzzer_original_config_invalid')
        original_pin = section_config.get('pin')
        if (not isinstance(original_pin, str)
                or original_pin.strip().casefold() != expected_pin.strip().casefold()):
            raise ValueError('buzzer_original_config_pin_mismatch')
        matches.append(actual)
    if len(matches) != 1:
        raise ValueError('buzzer_name_missing_or_ambiguous')
    return matches[0]


class MaintenancePulseController:
    """Explicit interactive state machine; no automatic test entry or PASS."""

    __slots__ = ('_printer', '_client', '_worker', '_gate', '_safety',
                 '_row', '_program', '_evidence', '_future', '_phase',
                 '_deadline', '_token', '_buzzer', '_cancelled', '_closed',
                 '_blocked', '_command_started', '_verify_next_at',
                 '_verify_matches', '_verify_problem', '_f12_bracket', '_f12_round_started', '_f12_levels',
                 '_f12_index', '_f12_session')

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
        self._command_started = 0.0
        self._verify_next_at = 0.0
        self._verify_matches = 0
        self._verify_problem = None
        self._f12_bracket = None
        self._f12_round_started = 0.0
        self._f12_levels = ()
        self._f12_index = 0
        self._f12_session = None

    @property
    def phase(self):
        return self._phase

    @property
    def pending(self):
        return self._phase is not None

    @property
    def feature_id(self):
        """Public active-test identity for context-appropriate LCD labels."""
        return self._row.feature_id if self._row is not None else None

    @property
    def f12_status(self):
        if self._f12_bracket is None or not self._f12_levels:
            return None
        # Exact commanded stage, updated on guarded stage dispatch, never
        # inferred from elapsed time or mistaken for measured rotor speed.
        index = self._f12_index
        return (self._f12_bracket.stage + 1, index + 1,
                self._f12_levels[index], self._f12_bracket.low,
                self._f12_bracket.high)

    @property
    def pwm_levels(self):
        return (self._program.pwm_levels if self._program is not None
                and self._phase == 'await_observation' else ())

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
        self._f12_bracket = None
        self._f12_round_started = 0.0
        self._f12_levels = ()
        self._f12_index = 0
        self._f12_session = None
        self._gate.cancel()
        self._safety.clear()
        self._row = self._program = self._evidence = self._future = None
        self._phase = None
        self._deadline = 0.0
        self._token = self._buzzer = None
        self._cancelled = False
        self._command_started = 0.0
        self._verify_next_at = 0.0
        self._verify_matches = 0
        self._verify_problem = None

    def _finish(self, status, reason, verified=False):
        row = self._row
        result = PhysicalResult(row.feature_id, row.device, status, reason, verified)
        self._release()
        return result

    def start(self, feature_id, device=None, *, timeout=12.0):
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
            target = _object_name(row)
        except ValueError:
            return False, 'invalid_hardware_identifier'
        self._row, self._buzzer = row, None
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
            if row.feature_id in ('S18', 'O03'):
                # Raw Klipper config is the authority for the case-sensitive
                # SET_PIN mux spelling. Both pin identities must agree.
                pin_command_name = _resolve_pin_gcode_name(
                    self._client, target, self._printer.state.settings.get(target, {}))
                state = {} if row.feature_id == 'S18' else _read_target(self._client, target)
                if state is None:
                    return None
            else:
                pin_command_name = None
                state = _read_target(self._client, target)
                if state is None:
                    return None
            settings = self._printer.state.settings
            owners = (mmu_led_owners(settings, target)
                      if row.feature_id == 'O04' else None)
            if owners is not None:
                live = _read_targets(self._client, (
                    'mmu', 'mmu_machine', *(owner.section for owner in owners)))
                if live is None:
                    raise ValueError('mmu_led_live_status_unknown')
                program = compile_mmu_led_pulse(
                    row, snap, state, settings, live, live.get('mmu', {}),
                    live.get('mmu_machine'))
            else:
                program = compile_pulse(
                    row, snap, state, settings,
                    pin_command_name=pin_command_name)
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
            except Exception as exc:
                # Avoid logging raw Moonraker exception payloads, which can
                # contain arbitrary printer data. Compiler ValueError codes
                # are fixed, safe diagnostic identifiers for field support.
                code = (str(exc) if isinstance(exc, ValueError)
                        else type(exc).__name__)
                logging.warning(
                    'Maintenance physical preflight blocked: '
                    'feature=%s reason=%s', self._row.feature_id, code)
                if (self._row.feature_id == 'F12' and
                        code in ('f12_kick_start_active',
                                 'f12_kick_start_unknown')):
                    return self._finish('BLOCKED', code)
                return self._finish('BLOCKED', 'preflight_failed')
            if found is None:
                return self._finish('BLOCKED', 'preflight_not_verified')
            evidence, program = found
            if self._row.feature_id == 'F12':
                if self._f12_bracket is None:
                    self._f12_bracket = F12Bracket(0, 127)
                program = f12_round_program(program, self._f12_bracket)
                self._f12_levels = program.pwm_levels
                self._f12_index = 0
                program = f12_stage_program(program, 0)
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
        if self._phase == 'f12_next_preflight':
            if not self._current() or now >= self._deadline:
                if self._future is not None:
                    self._future.cancel()
                return self._finish('INCONCLUSIVE', 'f12_next_stage_preflight_timeout_or_changed', True)
            if self._future is None or not self._future.done():
                return None
            try:
                evidence, state = self._future.result()
            except Exception:
                return self._finish('INCONCLUSIVE', 'f12_next_stage_preflight_failed', True)
            if (evidence is None or not isinstance(state, Mapping)
                    or not isinstance(state.get('fan'), Mapping)
                    or state['fan'].get('speed') != 0
                    or not self._safety_check(self._snapshot(), evidence)):
                return self._finish('INCONCLUSIVE', 'f12_next_stage_not_safe_or_fan_not_off', True)
            self._evidence = evidence
            next_index = self._f12_index + 1
            if next_index >= len(self._f12_levels):
                return self._finish('INCONCLUSIVE', 'f12_step_out_of_bounds', True)
            program = f12_stage_program(self._program, next_index)
            session = self._f12_session
            def guard():
                return (self._current() and self._safety.guard(
                    session, self._snapshot(), self._context()).allowed)
            if not guard():
                return self._finish('INCONCLUSIVE', 'f12_next_stage_guard_failed', True)
            try:
                self._future = self._printer.postREST(
                    '/printer/gcode/script', json={'script': program.script},
                    report_error=False, dispatch_guard=guard, request_timeout=9.0)
            except Exception:
                return self._finish('INCONCLUSIVE', 'f12_stage_dispatch_failed', True)
            self._program = program
            self._f12_index = next_index
            self._command_started = now
            self._phase = 'running'
            self._deadline = now + 13
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
            # Completion of the HTTP request is not proof that Klipper has
            # executed the queued dwell AND restore. Wait at least the whole
            # stimulus period plus margin from dispatch before reading.
            self._phase = 'verifying'
            self._verify_next_at = max(
                now + _VERIFY_MIN_AFTER_ACK_S,
                self._command_started + self._program.duration_ms / 1000
                + _VERIFY_MIN_AFTER_DISPATCH_S)
            # The readback window starts after the entire script is
            # expected to have ended, not at an early HTTP acknowledgement.
            # Otherwise a long F02 sequence would exhaust the window
            # before its first legal restoration read.
            self._deadline = self._verify_next_at + _VERIFY_WINDOW_S
            self._verify_matches = 0
            self._verify_problem = None
            self._future = None
            return None
        if self._phase == 'verifying':
            if not self._current():
                if self._future is not None:
                    self._future.cancel()
                return self._finish('INCONCLUSIVE', 'state_changed_during_restore_check')
            if self._program.feature_id == 'S18':
                # A full-script HTTP acknowledgement and elapsed pulse time
                # are not equivalent to output readback. User observation is
                # the ONLY evidence for buzzer sound and stopping.
                if now >= self._deadline:
                    return self._finish('INCONCLUSIVE', 'buzzer_completion_unconfirmed')
                if now < self._verify_next_at:
                    return None
                if self._cancelled:
                    return self._finish('ABORTED', 'buzzer_cancelled_restore_unverified')
                self._phase = 'await_observation'
                self._deadline = now + 30
                return None
            if now >= self._deadline:
                if self._future is not None:
                    self._future.cancel()
                    return self._finish('INCONCLUSIVE', 'restore_readback_timeout')
                if self._verify_matches:
                    return self._finish('INCONCLUSIVE', 'restore_not_stable')
                return self._finish(
                    'INCONCLUSIVE', self._verify_problem or 'restore_readback_timeout')
            if self._future is None:
                if now < self._verify_next_at:
                    return None
                try:
                    self._future = self._worker.submit(
                        (lambda: _read_targets(self._client, self._program.hh_controls)
                         if self._program.managed_hh else
                         _read_target(self._client, self._program.object_name)),
                        queue_timeout=min(2.0, self._deadline - now))
                except Exception:
                    return self._finish('INCONCLUSIVE', 'verification_unavailable')
                return None
            if not self._future.done():
                return None
            try:
                values = self._future.result()
            except Exception:
                values = None  # Transient GET error; retry within the same window.
            self._future = None
            if not self._current():
                return self._finish('INCONCLUSIVE', 'state_changed_during_restore_check')
            if restored(self._program, values):
                self._verify_matches += 1
                if self._verify_matches >= _VERIFY_MATCHES_REQUIRED:
                    if self._cancelled:
                        return self._finish('ABORTED', 'user_cancelled_after_restore', True)
                    if (self._program.feature_id == 'F12' and
                            self._f12_index + 1 < len(self._f12_levels)):
                        self._phase = 'f12_next_preflight'
                        self._deadline = now + 12
                        self._verify_matches = 0
                        try:
                            self._future = self._worker.submit(
                                lambda: (read_queue_evidence(
                                    self._client, self._row.epoch,
                                    self._row.config_marker),
                                    _read_target(self._client, 'fan')),
                                queue_timeout=6.0)
                        except Exception:
                            return self._finish(
                                'INCONCLUSIVE', 'f12_preflight_worker_unavailable', True)
                        return None
                    self._phase = 'await_observation'
                    self._deadline = now + 30
                    return None
            else:
                # Do not treat a single stale intermediate PWM as a failure;
                # conversely, one baseline-shaped sample is not a PASS.
                self._verify_matches = 0
                self._verify_problem = (
                    'restore_value_mismatch' if values is not None
                    else 'restore_readback_unavailable')
            self._verify_next_at = now + _VERIFY_RETRY_INTERVAL_S
            return None
        if self._phase == 'f12_await_stop' and now >= self._deadline:
            return self._finish('INCONCLUSIVE', 'fan_stop_not_confirmed', True)
        if self._phase == 'await_observation' and now >= self._deadline:
            # S18 has no Klipper readback: an expired user-observation window
            # must never imply that the output was restored.
            return self._finish('INCONCLUSIVE', 'observation_timeout',
                                self._program.feature_id != 'S18'
                                and not self._program.managed_hh)
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

        # Long F02 stages and synchronized Happy Hare O04 frames can exceed
        # the default 5-second HTTP timeout (G4 + M400 waits in real time).
        # Bound the override to these two compiled Maintenance protocols:
        # other commands retain their normal timeout, and failures never
        # replay ambiguous physical writes.
        extended = (program.feature_id in ('F02', 'F12')
                    or (program.feature_id == 'O04' and program.managed_hh))
        http_timeout = (min(27.0, program.duration_ms / 1000 + 6.0)
                        if program.feature_id == 'F12' else
                        min(15.0, program.duration_ms / 1000 + 4.0)
                        if extended else None)
        options = {'json': {'script': program.script},
                   'report_error': False, 'dispatch_guard': guard}
        if program.feature_id == 'F12':
            options['request_timeout'] = 9.0
            self._f12_session = session
        elif extended:
            options['request_timeout'] = http_timeout
        try:
            self._command_started = monotonic()
            if program.feature_id == 'F12':
                self._f12_round_started = self._command_started
            self._future = self._printer.postREST(
                '/printer/gcode/script', **options)
        except Exception:
            self._release()
            return False, 'command_queue_rejected'
        self._phase = 'running'
        # Each F12 command now contains only one 2-second bounded stage.
        self._deadline = monotonic() + (
            13.0 if program.feature_id == 'F12' else
            min(18.0, http_timeout + 4.0) if extended else 9.0)
        return True, 'bounded_pulse_queued'

    def observe(self, seen):
        """Human observation is separate from a command or reported PWM."""
        if self._phase != 'await_observation':
            return None
        if self._program.feature_id == 'F12':
            if type(seen) is not int or not 0 <= seen <= 5:
                return None
            try:
                self._f12_bracket = self._f12_bracket.next(seen)
            except ValueError:
                return self._finish('INCONCLUSIVE', 'f12_contradictory_or_invalid_observation', True)
            self._phase = 'f12_await_stop'
            self._deadline = monotonic() + 30
            return None
        if type(seen) is not bool:
            return None
        if self._program.managed_hh:
            # HH controls its own timed effect and returns to its policy.
            # Two MMU enabled/animation reads cannot prove that a dynamic
            # animation returned to the exact original colors. This is
            # human-observed only; NEVER declare electronic restore verified.
            return self._finish(
                'OBSERVED_USER' if seen else 'FAILED_USER',
                'hh_timed_effect_observed_policy_active_no_pixel_restore_proof'
                if seen else 'hh_timed_effect_not_observed',
                False)
        if self._program.feature_id == 'S18':
            # Unlike F01/O03, no Klipper status exists for pwm_cycle_time:
            # human observation is recorded, but telemetry restore is NEVER
            # claimed. A 'yes' must mean the sound occurred AND stopped.
            return self._finish(
                'OBSERVED_USER' if seen else 'FAILED_USER',
                'audible_pulse_and_stop_reported_no_readback' if seen
                else 'buzzer_not_observed_or_not_stopped', False)
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
                            'explicit_user_observation', True)

    def f12_confirm_stopped(self):
        """Operator confirms physical zero RPM; Klipper speed=0 was already read back."""
        if self._phase != 'f12_await_stop' or self._f12_bracket is None:
            return None, 'not_waiting_for_stop'
        bracket = self._f12_bracket
        if bracket.high == bracket.low == 255:
            return self._finish('FAILED_USER', 'fan_never_started_at_full_pwm', True), 'finished'
        if bracket.resolved:
            return self._finish('PASSED_USER',
                                'f12_observed_M106_threshold_S%d_to_S%d' %
                                (bracket.low, bracket.high), True), 'finished'
        # Fresh preflight + fresh explicit user consent before another round.
        # Release the previous consent/transport state but retain search data.
        self._release()
        allowed, reason = self.start('F12', 'fan')
        if allowed:
            self._f12_bracket = bracket
        return allowed, reason

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
