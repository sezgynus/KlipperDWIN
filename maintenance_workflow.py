"""Explicit, operator-paced firmware workflows on Petrel's existing owners.

A command completion is not physical acceptance. User questions have no clock.
Fresh queue/lifecycle evidence is acquired before every explicit dispatch.
"""
from collections.abc import Mapping
from dataclasses import dataclass, replace
from time import monotonic
from urllib.parse import quote
import math
import re

from maintenance_catalog import definition_for
from maintenance_planner import AdapterRegistration, build_plan, visible_plan
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import precheck
from maintenance_motion import idle_heaters, vector, number


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    feature_id: str
    device: str | None
    status: str
    reason: str
    restore_verified: bool = False
    evidence: tuple = ()


def adapters(methods, domain):
    return tuple(AdapterRegistration(f, m, 'maintenance.'+domain+'.'+f,
        definition_for(f).evidence_contract, definition_for(f).safety_profile)
        for f, m in methods.items())


def query(client, fields):
    if len(fields) > 32:
        raise ValueError('workflow_inventory_too_large')
    reply = client.get('/printer/objects/query?'+
        '&'.join(quote(k, safe='')+'='+v for k, v in fields.items()))
    result = reply.get('result') if isinstance(reply, Mapping) else None
    status = result.get('status') if isinstance(result, Mapping) else None
    stamp = result.get('eventtime') if isinstance(result, Mapping) else None
    if not isinstance(status, Mapping) or not number(stamp) or stamp < 0:
        raise ValueError('workflow_status_invalid')
    return status, stamp


def safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,48}', name):
        raise ValueError('workflow_name_invalid')
    return name


class FirmwareWorkflow:
    methods = {}
    domain = ''
    moving = True

    def __init__(self, printer, worker, client):
        self._printer, self._worker, self._client = printer, worker, client
        self._phase = self._row = self._future = self._command = None
        self._closed = self._locked = False
        self._action = None
        self._queue = None
        self._cursor = None
        self._lines = ()
        self._values = {}
        self._evidence = ()
        self._owned_manual = False
        self._sent = False
        self._manual_position = None
        self._safety_future = None
        self._next_safety = 0.

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
    def live_text(self):
        return ('Clear tool / travel path', 'No automatic SAVE_CONFIG')
    @property
    def observation_prompt(self):
        return 'Result physically observed?'
    @property
    def workflow_choices(self):
        return ()

    def available(self):
        return visible_plan(build_plan(self._printer.maintenance.snapshot,
                            adapters(self.methods, self.domain)))

    def _current(self):
        try:
            row = self._row
            live = self._printer.subscription.lifecycle()
            return (row in self.available() and self._printer.state.ready
                and live.get('state') == 'ready' and live.get('epoch') == row.epoch
                and self._printer.state.epoch == row.epoch
                and id(self._printer.state.settings) == row.config_marker)
        except Exception:
            return False

    def _safe(self, queue):
        if not self._current():
            return False
        context = self.context(queue)
        if self._owned_manual and context.state is not None:
            # Only this workflow's observed manual session may continue.
            # All print, queue, MMU and other-owner checks still apply.
            state = context.state
            if state.status.get('manual_probe', {}).get('is_active') is True:
                from types import SimpleNamespace
                status = dict(state.status)
                status['manual_probe'] = {'is_active': False}
                context = replace(context, state=SimpleNamespace(
                    ready=state.ready, epoch=state.epoch,
                    settings=state.settings, status=status))
        return precheck(self._printer.maintenance.snapshot, context).allowed

    def fields(self):
        fields = {'toolhead':'position,homed_axes,axis_minimum,axis_maximum',
                  'manual_probe':'is_active,z_position',
                  'configfile':'save_config_pending,save_config_pending_items'}
        for name, cfg in self._printer.state.settings.items():
            if isinstance(cfg, Mapping) and 'heater_pin' in cfg:
                fields[name] = 'temperature,target,power'
        return fields

    def validate(self, values, action):
        settings = self._printer.state.settings
        idle_heaters(settings, values)
        if self.moving:
            th = values.get('toolhead', {})
            if not set('xyz') <= set(th.get('homed_axes', '')):
                raise ValueError('home_xyz_before_workflow')
            pos, low, high = (vector(th.get(k)) for k in
                             ('position','axis_minimum','axis_maximum'))
            if any(not lo <= p <= hi for lo, p, hi in zip(low, pos, high)):
                raise ValueError('workflow_position_invalid')
        manual = values.get('manual_probe', {}).get('is_active')
        if manual is True and not self._owned_manual:
            raise ValueError('unowned_manual_probe')
        if manual not in (True, False):
            raise ValueError('manual_probe_status_unknown')
        if action == 'start':
            config = values.get('configfile', {})
            if (config.get('save_config_pending') is not False or
                    config.get('save_config_pending_items') not in ({}, None)):
                raise ValueError('existing_pending_config')

    def script(self, action, values):
        raise NotImplementedError

    def _prepare(self, action):
        row = self._row
        queue = read_queue_evidence(self._client, row.epoch, row.config_marker)
        if not self._safe(queue):
            raise ValueError('workflow_safety_denied')
        values, stamp = query(self._client, self.fields())
        self.validate(values, action)
        script = self.script(action, values)
        if (not isinstance(script, str) or not script or len(script) > 4096
                or any(line.split()[0] == 'SAVE_CONFIG' for line in script.splitlines() if line.strip())):
            raise ValueError('workflow_script_invalid')
        for line in script.splitlines():
            command = line.split()[0].lower()
            if any(str(k).lower() == 'gcode_macro '+command for k in self._printer.state.settings):
                raise ValueError('workflow_command_overridden')
        return queue, values, stamp, script

    def _schedule(self, action, dispatch):
        self._action, self._dispatch = action, dispatch
        self._phase, self._deadline = 'preflight', monotonic()+12
        self._future = self._worker.submit(lambda:self._prepare(action), queue_timeout=8)
        return True, 'workflow_preflight_queued'

    def start(self, feature_id, device=None, **kwargs):
        if self._closed or self._locked or self.pending:
            return False, 'workflow_busy_or_locked'
        row = next((r for r in self.available()
                    if r.feature_id == feature_id and r.device == device), None)
        if row is None:
            return False, 'workflow_adapter_unavailable'
        self._row, self._owned_manual, self._sent = row, False, False
        self._safety_future = None
        self._next_safety = 0.
        self._evidence, self._lines, self._values = (), (), {}
        try:
            return self._schedule('start', False)
        except Exception:
            self._phase = None
            return False, 'workflow_worker_rejected'

    def confirm(self):
        if self.phase != 'await_confirmation':
            return False, 'workflow_not_waiting_for_consent'
        try:
            return self._schedule(self._action, True)
        except Exception:
            return False, 'workflow_worker_rejected'

    def _finish(self, status, reason, evidence=(), restored=False):
        result = WorkflowResult(self.feature_id, self._row.device, status, reason,
                                restored, tuple(evidence or self._evidence)[:12])
        self._phase = self._future = self._command = None
        self._owned_manual = False
        return result

    def _shutdown(self, reason):
        # No ordinary G-code behind an uncertain moving command.
        self._locked = True
        self._stop_reason = reason
        self._phase, self._deadline = 'stopping', monotonic()+8
        try:
            self._command = self._printer.subscription.request('printer.emergency_stop')
        except Exception:
            self._command = None
        return None

    def completed(self, values, lines):
        self._values = values
        self._phase = 'await_observation'
        self._evidence = (('firmware_rpc_completed', True),)
        return None

    def poll(self):
        if self.phase in (None, 'await_confirmation', 'workflow', 'await_observation',
                          'measurement_edit'):
            return None
        now = monotonic()
        if self.phase == 'stopping':
            if self._command is not None and self._command.done():
                try:
                    self._command.result()
                    return self._finish('INCONCLUSIVE', self._stop_reason+'_klipper_shutdown')
                except Exception:
                    pass
            if now >= self._deadline:
                return self._finish('INCONCLUSIVE', self._stop_reason+'_SHUTDOWN_UNCONFIRMED')
            return None
        if not self._current():
            if self._sent and self.moving:
                return self._shutdown('workflow_lifecycle_changed')
            return self._finish('INCONCLUSIVE', 'workflow_lifecycle_changed')
        if now >= self._deadline:
            if self._sent and self.moving:
                return self._shutdown('workflow_command_unconfirmed')
            return self._finish('INCONCLUSIVE', 'workflow_read_timeout')
        if self.phase == 'preflight':
            if not self._future.done():
                return None
            try:
                queue, values, stamp, script = self._future.result()
                if not self._safe(queue):
                    raise ValueError('workflow_state_changed')
            except Exception as exc:
                code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[a-z0-9_]{1,80}', str(exc)) else 'workflow_preflight_failed'
                return self._finish('BLOCKED', code)
            self._queue, self._values, self._stamp = queue, values, stamp
            self._future = None
            if not self._dispatch:
                self._phase = 'await_confirmation'
                return None
            self._cursor, _ = self._printer.subscription.responses_since(None)
            self._lines = ()
            def guard():
                return (self.phase in ('preflight','running') and self._safe(self._queue)
                        and self.dispatch_valid(values))
            try:
                self._command = self.dispatch(script,guard)
            except Exception:
                return self._shutdown('workflow_dispatch_ambiguous') if self.moving else self._finish('INCONCLUSIVE','workflow_dispatch_failed')
            self._sent = True
            self._phase, self._deadline = 'running', now+905
            return None
        if self.phase == 'running':
            if not self._command.done():
                if self._safety_future is not None and self._safety_future.done():
                    try:
                        queue = self._safety_future.result()
                        if not self._safe(queue):
                            raise ValueError('workflow_runtime_unsafe')
                        self._queue = queue
                    except Exception:
                        return self._shutdown('workflow_runtime_safety_changed') if self.moving else self._finish('INCONCLUSIVE','workflow_runtime_safety_changed')
                    self._safety_future = None
                    self._next_safety = now+1
                if self._safety_future is None and now >= self._next_safety:
                    row = self._row
                    self._safety_future = self._worker.submit(
                        self.runtime_evidence,
                        queue_timeout=2)
                if not self._safe(self._queue):
                    return self._shutdown('workflow_runtime_safety_unknown') if self.moving else self._finish('INCONCLUSIVE','workflow_runtime_safety_unknown')
            self._cursor, lines = self._printer.subscription.responses_since(self._cursor)
            self._lines = (self._lines + tuple(str(s)[:2048] for s in lines))[-32:]
            if not self._command.done():
                return None
            try:
                self._command.result()
                self._future = self._worker.submit(
                    lambda:query(self._client,self.fields()), queue_timeout=5)
            except Exception:
                return self._shutdown('workflow_command_failed') if self.moving else self._finish('INCONCLUSIVE','workflow_command_failed')
            self._phase, self._deadline = 'verifying', now+10
            return None
        if self.phase == 'verifying':
            if not self._future.done():
                return None
            try:
                values, stamp = self._future.result()
                if stamp <= self._stamp:
                    raise ValueError('workflow_result_stale')
                self._cursor, lines = self._printer.subscription.responses_since(self._cursor)
                self._lines = (self._lines+tuple(str(s)[:2048] for s in lines))[-32:]
                return self.completed(values, self._lines)
            except Exception:
                return self._shutdown('workflow_evidence_unverified') if self.moving else self._finish('INCONCLUSIVE', 'workflow_evidence_unverified')

    def context(self, queue):
        return live_safety_context(self._printer,queue)

    def runtime_evidence(self):
        row = self._row
        return read_queue_evidence(self._client,row.epoch,row.config_marker)

    def dispatch(self, script, guard):
        return self._printer.subscription.request('printer.gcode.script',
                    {'script':script},guard=guard,request_timeout=900.)

    def dispatch_valid(self, prepared):
        try:
            raw = self._printer.subscription.snapshot(include_settings=False)
            live = raw['status']['toolhead']
            prior = prepared.get('toolhead', {})
            if self.moving:
                return (live.get('homed_axes') == prior.get('homed_axes') and
                    all(abs(a-b) <= .05 for a,b in zip(
                        vector(live.get('position')), vector(prior.get('position')))))
            return True
        except Exception:
            return False

    def choose(self, selected):
        if self.phase != 'workflow' or type(selected) is not int:
            return False, 'workflow_choice_invalid'
        choices = self.workflow_choices
        if not 0 <= selected < len(choices):
            return False, 'workflow_choice_invalid'
        action = choices[selected][1]
        if action == 'finish':
            self._phase = 'await_observation'
            return True, 'observe_result'
        return self._schedule(action, True)

    def observe(self, seen):
        if self.phase != 'await_observation' or type(seen) is not bool:
            return None
        return self._finish('OBSERVED_USER' if seen else 'FAILED_USER',
                            'firmware_result_user_observed_no_auto_save')

    def cancel(self):
        if self.phase in ('running','verifying','stopping') and self.moving:
            return self._shutdown('user_cancelled_workflow')
        if self._owned_manual:
            # Cancelling the owned interactive wizard is explicit, not timeout.
            return self._schedule('abort', True) and None
        if self.pending:
            if self._future is not None:
                self._future.cancel()
            return self._finish('ABORTED', 'user_cancelled_workflow')
        return None

    def close(self):
        if self._owned_manual:
            self._shutdown('workflow_closed_with_manual_probe')
        else:
            self.cancel()
        self._closed = True
