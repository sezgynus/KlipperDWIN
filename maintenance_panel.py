"""Explicit LCD color/backlight observation on the existing UI owner."""
from dataclasses import dataclass
from time import monotonic
from maintenance_discovery import USER
from maintenance_planner import build_plan,visible_plan
from maintenance_workflow import adapters,WorkflowResult
from maintenance_runtime import read_queue_evidence,live_safety_context
from maintenance_safety import precheck

METHODS = {'S15':USER,'S16':USER,'S17':USER}
COLORS = (('Red',0xf800),('Green',0x07e0),('Blue',0x001f),('White',0xffff),('Black',0))


class MaintenancePanelController:
    def __init__(self,printer,worker,client):
        self._printer,self._worker,self._client = printer,worker,client
        self._phase = self._row = self._future = None
        self._closed = False
        self._index = 0
        self._restore = None
        self._panel_epoch = None
        self._gpio_start = None
        self._evidence = ()

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
    def display_color(self):
        return COLORS[self._index][1] if self.feature_id=='S16' and self.phase=='workflow' else None
    @property
    def workflow_choices(self):
        if self.feature_id=='S15':
            return (('Both directions + click done','next'),)
        label = COLORS[self._index][0] if self.feature_id=='S16' else str((10,50,100)[self._index])+'%'
        return ((label+' seen / next','next'),)
    @property
    def live_text(self):
        return ('Turn physical knob both ways','Press physical encoder button') if self.feature_id=='S15' else ('Observe the physical LCD','Settings are not saved')
    @property
    def observation_prompt(self):
        return 'Directions and click seen?' if self.feature_id=='S15' else 'Sequence and restore seen?'

    def available(self):
        return visible_plan(build_plan(self._printer.maintenance.snapshot,adapters(METHODS,'panel')))

    def _api(self,action,*args):
        provider = getattr(self._printer,'_maintenance_panel_api',None)
        if not callable(provider):
            raise ValueError('panel_provider_unavailable')
        return provider(action,*args)

    def _safe(self,queue):
        row = self._row
        live = self._printer.subscription.lifecycle()
        return (row in self.available() and live.get('state')=='ready'
            and live.get('epoch')==row.epoch
            and precheck(self._printer.maintenance.snapshot,
                         live_safety_context(self._printer,queue)).allowed)

    def _preflight(self,dispatch):
        self._dispatch = dispatch
        row = self._row
        try:
            future = self._worker.submit(
                lambda:read_queue_evidence(self._client,row.epoch,row.config_marker),queue_timeout=6)
        except Exception:
            return False,'panel_worker_rejected'
        self._future = future
        self._phase,self._deadline = 'preflight',monotonic()+10
        return True,'panel_preflight_queued'

    def start(self,feature_id,device=None,**kwargs):
        if self._closed or self.pending:
            return False,'panel_busy'
        self._row = next((r for r in self.available() if r.feature_id==feature_id and r.device==device),None)
        if self._row is None:
            return False,'panel_adapter_unavailable'
        self._index,self._restore,self._panel_epoch = 0,None,None
        self._gpio_start,self._evidence = None,()
        return self._preflight(False)

    def confirm(self):
        if self.phase!='await_confirmation':
            return False,'panel_not_waiting_for_confirmation'
        return self._preflight(True)

    def _finish(self,status,reason,restored=False):
        result = WorkflowResult(self.feature_id,None,status,reason,restored,
            (('observed_stages',self._index),('settings_saved',False))+self._evidence)
        self._phase,self._future = None,None
        return result

    def _restore_panel(self):
        if self._restore is not None:
            self._api('restore',self._restore,self._panel_epoch)
            self._restore = None

    def _apply(self):
        info = self._api('info')
        if self._panel_epoch is None:
            self._panel_epoch = info['uart_epoch']
            if self.feature_id=='S15':
                keys = ('gpio_positive_steps','gpio_negative_steps','gpio_button_presses')
                if any(type(info.get(k)) is not int or info[k]<0 for k in keys):
                    raise ValueError('physical_gpio_counters_unavailable')
                self._gpio_start = {k:info[k] for k in keys}
            else:
                self._restore = self._api('capture')
        elif info['uart_epoch']!=self._panel_epoch:
            raise ValueError('panel_reconnected')
        if self.feature_id=='S17':
            self._api('brightness',(10,50,100)[self._index],self._panel_epoch)
        self._phase = 'workflow'

    def poll(self):
        if self.phase!='preflight':
            return None
        if monotonic()>=self._deadline:
            return self._finish('INCONCLUSIVE','panel_preflight_timeout')
        if not self._future.done():
            return None
        try:
            if not self._safe(self._future.result()):
                raise ValueError('panel_safety_denied')
            if self._dispatch:
                self._apply()
            else:
                self._phase = 'await_confirmation'
        except Exception:
            try:
                self._restore_panel()
            except Exception:
                pass
            return self._finish('INCONCLUSIVE','panel_safety_or_connection_changed')
        return None

    def choose(self,selected):
        if self.phase!='workflow' or selected!=0:
            return False,'panel_choice_invalid'
        if self.feature_id=='S15':
            info = self._api('info')
            if info.get('uart_epoch')!=self._panel_epoch:
                return False,'panel_session_changed'
            deltas = tuple((k,info.get(k,-1)-v) for k,v in self._gpio_start.items())
            if any(v<1 for k,v in deltas):
                return False,'physical_directions_and_new_click_required'
            self._evidence = deltas
            self._index = 1
            self._phase = 'await_observation'
            return True,'physical_gpio_evidence_observed'
        self._index += 1
        count = len(COLORS) if self.feature_id=='S16' else 3
        if self._index>=count:
            try:
                self._restore_panel()
            except Exception:
                self._index = count-1
                return False,'panel_restore_unconfirmed'
            self._phase = 'await_observation'
            return True,'observe_sequence_restore'
        result = self._preflight(True)
        if not result[0]:
            self._index -= 1
        return result

    def observe(self,seen):
        if self.phase!='await_observation' or type(seen) is not bool:
            return None
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
            'physical_gpio_event_observation' if self.feature_id=='S15' else 'visual_observation_not_optical_metrology',bool(seen))

    def cancel(self):
        if not self.pending:
            return None
        if self._future is not None:
            self._future.cancel()
        try:
            self._restore_panel()
        except Exception:
            return self._finish('INCONCLUSIVE','panel_restore_unconfirmed')
        return self._finish('ABORTED','panel_user_cancelled_restore_requested')

    def close(self):
        self.cancel()
        self._closed = True
