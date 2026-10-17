"""Explicit motion consent, completion RPCs, measured travel and verification."""
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from urllib.parse import quote
import uuid
from maintenance_homing import begin_homing, poll_homing
from maintenance_catalog import definition_for
from maintenance_discovery import USER, EXTERNAL, CALIBRATION
from maintenance_planner import AdapterRegistration, build_plan, visible_plan
from maintenance_runtime import read_queue_evidence, live_safety_context
from maintenance_safety import precheck
from maintenance_motion import (compile_motion, return_program, verify_motion,
    idle_heaters, vector, position_matches, modes_match, modal, number, dispatch_compatible)

METHODS={'M03':CALIBRATION,'M04':USER,'M05':USER,'M06':EXTERNAL,'M12':CALIBRATION}

def motion_adapters():
    return tuple(AdapterRegistration(f,m,'maintenance.motion.'+f,
        definition_for(f).evidence_contract,definition_for(f).safety_profile) for f,m in METHODS.items())

def motion_plan(snapshot):
    return tuple(r for r in visible_plan(build_plan(snapshot,motion_adapters()))
                 if (r.feature_id=='M03' and r.device is None)
                 or (r.device in ('stepper_x','stepper_y','stepper_z') and r.feature_id!='M03'))

@dataclass(frozen=True,slots=True)
class MotionResult:
    feature_id:str
    device:str|None
    status:str
    reason:str
    restore_verified:bool=False
    evidence:tuple=()

class MaintenanceMotionController:
    def __init__(self,printer,worker,client):
        self._printer,self._worker,self._client=printer,worker,client
        self._phase=self._row=self._future=self._program=self._command=None
        self._queue=None
        self._closed=self._blocked=False
        self._deadline=self._next=self._last_stamp=0.
        self._matches=0
        self._return_requested=False
        self._measurement=None
        self._outward=None
        self._evidence=()
        self._safety_reason=None
        self._queue_age_s=None
        self._consented_program=None
        self._confirm_attempts=0
        self._refresh_reason=None
        self._dispatch_guard_reason=None
        self._homing=None
        self._home_attempted=self._homing_verified=self._auto_continue=False

    @property
    def preparing_home(self):
        return self._homing is not None
    @property
    def preparation_stage(self):
        return self._homing.phase if self._homing is not None else ('homing_verified' if self._homing_verified else None)

    @property
    def refreshing_consent(self):
        return self._consented_program is not None and self.phase=='preflight'

    @property
    def pending(self):
        return self._phase is not None
    @property
    def phase(self):
        return self._homing.phase if self._homing is not None else self._phase
    @property
    def feature_id(self):
        return self._row.feature_id if self._row else None
    @property
    def returning(self):
        return bool(self._program and self._program.returning)
    @property
    def measurement_value(self):
        return self._measurement if self._measurement is not None else abs(self._program.distance) if self._program is not None else 0.
    @property
    def observation_details(self):
        if self.feature_id!='M12' or self.phase!='await_observation':
            return ()
        phase=dict(self._evidence).get('trigger_phase','unknown')
        return (self._row.device, 'Homing cycles: '+str(self._program.homing_runs),
                'Trigger phase: '+str(phase), 'Pending config: YES',
                'Saved to file: NO', 'G-code modes restored',
                'No independent accuracy measurement')

    @property
    def observation_prompt(self):
        return {'M03':'Homing completed safely?', 'M04':'Correct motor and return?',
                'M05':'Correct axis and return?', 'M06':'Travel measured and back?',
                'M12':'Phase result observed?'}.get(self.feature_id,'Motion observed?')
    @property
    def live_text(self):
        p=self._program
        if self.preparing_home:
            return ('Home XYZ, then selected test','Clear bed and homing path','Stop = Klipper shutdown')
        if self.refreshing_consent:
            return ('Refreshing safety data','Your confirmation is kept','Cancel to stop checks')
        if p is None:
            return ()
        if p.feature_id=='M03':
            return ('Clear bed and homing path','Configured XYZ homing','Stop = Klipper shutdown')
        if p.feature_id=='M12':
            return (p.device,'10 random starts / selected-axis G28',
                    'Z lifts once if needed; no SAVE_CONFIG')
        distance=-p.distance if p.returning else p.distance
        return ('%s %+.1f mm'%('XYZ'[p.axis],distance),
                'Clear travel path / hands',
                'Stop = Klipper shutdown')
    def available(self):
        return motion_plan(self._printer.maintenance.snapshot)
    def _current(self):
        try:
            row=self._row
            live=self._printer.subscription.lifecycle()
            return (row in self.available() and self._printer.state.ready
                    and live.get('state')=='ready' and live.get('epoch')==row.epoch
                    and self._printer.state.epoch==row.epoch
                    and id(self._printer.state.settings)==row.config_marker)
        except Exception:
            return False
    def _safe(self,queue,*,queue_max_age=3.):
        return self._current() and precheck(self._printer.maintenance.snapshot,
                    live_safety_context(self._printer,queue,queue_max_age=queue_max_age)).allowed
    def _read(self):
        row=self._row
        queue=read_queue_evidence(self._client,row.epoch,row.config_marker)
        if not self._safe(queue):
            raise ValueError('motion_safety_denied')
        state=self._printer.state
        fields={'toolhead':'position,homed_axes,axis_minimum,axis_maximum,max_velocity',
                'gcode_move':'position,homing_origin,speed,speed_factor,extrude_factor,absolute_coordinates,absolute_extrude',
                'stepper_enable':'steppers'}
        if 'bed_mesh' in state.settings:
            fields['bed_mesh']='profile_name,mesh_min,mesh_max'
        if row.feature_id=='M12':
            fields['endstop_phase']='last_home'
            fields['configfile']='save_config_pending,save_config_pending_items'
        for name,cfg in state.settings.items():
            if isinstance(cfg,Mapping) and 'heater_pin' in cfg:
                fields[name]='temperature,target,power'
        if len(fields)>22:
            raise ValueError('motion_inventory_exceeds_bound')
        path='/printer/objects/query?'+'&'.join(quote(k,safe='')+'='+v for k,v in fields.items())
        reply=self._client.get(path)
        result=reply.get('result') if isinstance(reply,Mapping) else None
        values=result.get('status') if isinstance(result,Mapping) else None
        stamp=result.get('eventtime') if isinstance(result,Mapping) else None
        if not isinstance(values,Mapping) or not number(stamp) or stamp<0:
            raise ValueError('motion_read_invalid')
        idle_heaters(state.settings,values)
        return queue,values,float(stamp)
    def _prepare(self,returning):
        queue,values,stamp=self._read()
        token='_PETREL_M_'+uuid.uuid4().hex
        axes=values.get('toolhead',{}).get('homed_axes')
        if (not returning and not self._home_attempted and self.feature_id!='M03'
                and isinstance(axes,str) and set(axes)<=set('xyz')
                and not set('xyz')<=set(axes)):
            raise ValueError('home_xyz_before_motion_test')
        program=(return_program(self._outward,self._printer.state,values,token)
                 if returning else compile_motion(self._row,self._printer.state,values,token))
        consent=self._consented_program
        if consent is not None:
            if (program.phase_count!=consent.phase_count or
                    not dispatch_compatible(consent,self._row,self._printer.state,values,token)):
                raise ValueError('motion_consent_context_changed')
            program=consent
        return queue,program,stamp
    def _preflight(self,returning=False):
        self._return_requested=returning
        self._phase='preflight'
        self._deadline=monotonic()+12
        try:
            self._future=self._worker.submit(lambda:self._prepare(returning),queue_timeout=8)
        except Exception:
            self._phase=None
            return False,'motion_worker_rejected'
        return True,'motion_preflight_queued'
    def start(self,feature_id,device=None,**kwargs):
        if self._closed or self._blocked or self.pending:
            return False,'motion_busy_or_locked'
        row=next((r for r in self.available() if r.feature_id==feature_id and r.device==device),None)
        if row is None:
            return False,'motion_adapter_unavailable'
        self._row=row
        self._homing=None
        self._home_attempted=self._homing_verified=self._auto_continue=False
        self._consented_program=None
        self._confirm_attempts=0
        self._refresh_reason=None
        self._program=None
        self._measurement=None
        self._evidence=()
        return self._preflight()
    def confirm(self):
        if self._homing is not None:
            return self._homing.confirm()
        if self.phase!='await_confirmation':
            return False,'not_waiting_for_motion_consent'
        self._confirm_attempts+=1
        if not self._safe(self._queue) or monotonic()>=self._deadline:
            self._consented_program=self._program
            self._refresh_reason='motion_confirmation_evidence_expired'
            return self._preflight(self._return_requested)
        return self._dispatch()

    def _dispatch(self):
        p=self._program
        def guard():
            if self._phase not in ('await_confirmation','running'):
                self._dispatch_guard_reason='motion_phase_changed'
                return False
            if not self._safe(self._queue):
                self._dispatch_guard_reason='motion_dispatch_safety_denied'
                return False
            try:
                state=live_safety_context(self._printer,self._queue).state
                allowed=dispatch_compatible(p,self._row,state,state.status,
                    '_PETREL_M_'+uuid.uuid4().hex)
                self._dispatch_guard_reason=('allowed' if allowed else 'motion_program_changed')
                return allowed
            except Exception as exc:
                codes={'motion_velocity_unknown','keep_xyz_motors_enabled',
                       'motion_requires_cold_idle_heaters','clear_mesh_before_motion_test',
                       'home_xyz_before_motion_test','motion_status_missing',
                       'gcode_modes_unknown','gcode_factors_unknown',
                       'motion_limits_or_position_invalid','motion_coordinates_unknown',
                       'move_away_from_axis_limits','raise_z_for_xy_clearance'}
                self._dispatch_guard_reason=(str(exc) if isinstance(exc,ValueError)
                    and str(exc) in codes else 'motion_dispatch_evidence_unverified')
                return False
        try:
            self._command=self._printer.subscription.request('printer.gcode.script',
                {'script':p.script},guard=guard,request_timeout=min(900. if p.feature_id=='M12' else 180.,
                                                       p.deadline_s))
        except Exception:
            self._shutdown('motion_dispatch_unknown')
            return True,'motion_shutdown_requested'
        self._phase='running'
        self._deadline=monotonic()+p.deadline_s+4
        self._next=monotonic()
        self._future=None
        self._matches=0
        return True,'guarded_motion_queued'
    def _finish(self,status,reason,restored=False):
        result=MotionResult(self.feature_id,self._row.device,status,reason,restored,self._evidence)
        self._phase=self._future=self._command=None
        self._consented_program=None
        self._homing=None
        self._auto_continue=False
        return result
    def _shutdown(self,reason):
        if self.phase!='stopping':
            self._phase='stopping'
            self._blocked=True
            self._stop_reason=reason
            self._deadline=monotonic()+8
            try:
                epoch=self._row.epoch
                self._stop=self._printer.subscription.request('printer.emergency_stop',
                    guard=lambda:self._printer.subscription.lifecycle().get('epoch')==epoch)
            except Exception:
                self._stop=None
        return None
    def poll(self):
        if self._homing is not None:
            stage,result=poll_homing(self)
            if stage=='failed':
                self._blocked=result.status=='INCONCLUSIVE'
                return self._finish(result.status,'preparation_'+result.reason)
            if stage=='complete':
                self._auto_continue=True
                accepted,reason=self._preflight()
                if not accepted:
                    return self._finish('BLOCKED',reason)
            return None
        now=monotonic()
        if self.phase=='stopping':
            if self._stop is not None and self._stop.done():
                try:
                    self._stop.result()
                    return self._finish('INCONCLUSIVE',self._stop_reason+'_klipper_shutdown')
                except Exception:
                    return self._finish('INCONCLUSIVE',self._stop_reason+'_SHUTDOWN_UNCONFIRMED')
            if now>=self._deadline:
                return self._finish('INCONCLUSIVE',self._stop_reason+'_SHUTDOWN_UNCONFIRMED')
            return None
        if self.phase in (None,'await_confirmation','await_observation','await_measurement','measurement_edit'):
            return None
        if self.phase=='preflight':
            if not self._current() or now>=self._deadline:
                self._future.cancel()
                return self._finish('BLOCKED','motion_preflight_stale')
            if not self._future.done():
                return None
            try:
                queue,program,stamp=self._future.result()
                if not self._safe(queue):
                    raise ValueError('motion_guard_failed')
            except Exception as exc:
                code=str(exc) if isinstance(exc,ValueError) else ''
                if (code in ('home_xyz_before_motion_test','home_axis_before_phase_calibration',
                             'axis_not_homed_for_phase') and not self._home_attempted
                        and not self._return_requested and self.feature_id!='M03'):
                    self._consented_program=None
                    try:
                        begin_homing(self)
                    except Exception:
                        return self._finish('BLOCKED','homing_preparation_unavailable')
                    return None
                safe_codes={
                    'motion_consent_context_changed',
                    'home_xyz_before_motion_test','move_away_from_axis_limits',
                    'clear_mesh_before_motion_test','raise_z_for_xy_clearance',
                    'keep_xyz_motors_enabled','motion_requires_cold_idle_heaters',
                    'existing_or_unknown_pending_config','home_axis_before_phase_calibration',
                    'axis_not_homed_for_phase','individual_motor_kinematics_profile_required',
                    'independent_multi_z_buzz_not_safe','clear_xyz_offsets_before_homing_test',
                    'motion_command_overridden','motion_kinematics_profile_required',
                    'motion_transform_profile_required','insufficient_test_travel',
                    'phase_stepper_not_supported_for_kinematics',
                    'insufficient_phase_calibration_travel','phase_homing_speed_invalid',
                    'phase_calibration_duration_exceeds_transport_limit'}
                reason=(code if code in safe_codes else 'motion_geometry_or_evidence_unverified')
                return self._finish('BLOCKED','return_position_unverified_manual_recovery'
                                    if self._return_requested else reason)
            self._queue,self._program,self._last_stamp=queue,program,stamp
            self._phase='await_confirmation'
            self._future=None
            self._deadline=min(now+3,queue.observed_at+3)
            if self._consented_program is not None or self._auto_continue:
                self._auto_continue=False
                self._consented_program=None
                self._dispatch()
            return None
        # A completed read can already contain newer queue proof. Consume
        # that proof before judging the previous sample's age.
        if self._future is not None and self._future.done():
            try:
                self._queue=self._future.result()[0]
            except Exception:
                return self._shutdown('motion_read_or_safety_unknown')
        self._queue_age_s=(now-self._queue.observed_at
                           if self._queue is not None else None)
        if not self._current():
            self._safety_reason='lifecycle_changed'
            return self._shutdown('motion_safety_or_lifecycle_changed')
        # Admission and dispatch stay at 3 s. Once a finite command is sent,
        # use the existing 5 s read-watchdog bound, as in thermal workflows.
        # Subscription print/SD/pause/MMU/other-owner checks remain live.
        decision=precheck(self._printer.maintenance.snapshot,
                         live_safety_context(self._printer,self._queue,queue_max_age=5.))
        self._safety_reason=decision.reason
        if not decision.allowed:
            return self._shutdown('motion_runtime_'+decision.reason)
        if self._command.done():
            try:
                self._command.result()
            except Exception:
                if getattr(self._command,'dispatch_stage',None)=='guard_denied':
                    # The transport rejected before any socket send. There
                    # is no uncertain movement to stop or automatically retry.
                    return self._finish('BLOCKED',self._dispatch_guard_reason or
                                        'motion_dispatch_guard_denied')
                return self._shutdown('motion_script_failed_or_ambiguous')
            if self.phase=='running':
                self._phase='verifying'
                self._deadline=min(self._deadline,now+8)
        if now>=self._deadline:
            return self._shutdown('motion_completion_or_restore_timeout')
        if self._future is None:
            if now<self._next:
                return None
            try:
                self._future=self._worker.submit(self._read,queue_timeout=3)
                self._read_deadline=now+5
            except Exception:
                return self._shutdown('motion_read_worker_unavailable')
            return None
        if not self._future.done():
            if now>=self._read_deadline:
                return self._shutdown('motion_read_timeout')
            return None
        try:
            queue,values,stamp=self._future.result()
            if not self._safe(queue,queue_max_age=5.) or stamp<=self._last_stamp:
                raise ValueError('motion_read_stale')
            self._queue,self._last_stamp=queue,stamp
        except Exception:
            return self._shutdown('motion_read_or_safety_unknown')
        self._future=None
        self._next=now+.3
        if self.phase!='verifying':
            return None
        if verify_motion(self._program,values):
            self._matches+=1
        else:
            self._matches=0
        if self._matches<2:
            return None
        if self.feature_id=='M06' and not self._program.returning:
            self._phase='await_measurement'
        else:
            if self.feature_id=='M12':
                value=values['configfile']['save_config_pending_items']['endstop_phase '+self._row.device]['trigger_phase']
                self._evidence=(('homing_cycles',self._program.homing_runs),
                                 ('trigger_phase',value))
            self._phase='await_observation'
        return None
    def begin_measurement(self):
        if self.phase!='await_measurement':
            return False,'not_waiting_for_external_measurement'
        self._phase='measurement_edit'
        return True,'enter_actual_external_mm'
    def adjust_measurement(self,delta):
        if self.phase=='measurement_edit' and number(delta):
            self._measurement=round(min(100.,max(.1,self.measurement_value+delta)),2)
        return self.measurement_value
    def record_measurement(self,value):
        if self.phase!='measurement_edit' or not number(value) or not .1<=value<=100:
            return False,'external_measurement_invalid'
        self._measurement=float(value)
        self._outward=self._program
        expected=abs(self._program.distance)
        self._evidence=(('measured_mm',round(value,3)),('commanded_mm',expected),
                        ('error_mm',round(value-expected,3)))
        return self._preflight(True)
    def observe(self,seen):
        if self.phase!='await_observation' or type(seen) is not bool:
            return None
        if self.feature_id=='M12':
            return self._finish('OBSERVED_USER' if seen else 'FAILED_USER','phase_pending_no_save_config',False)
        if self.feature_id=='M06' and abs(self._measurement-abs(self._program.distance))>.2:
            return self._finish('FAILED_USER','external_travel_outside_0_2_mm',True)
        return self._finish('PASSED_USER' if seen else 'FAILED_USER','motion_user_observation_after_readback',True)
    def cancel(self):
        if self._homing is not None:
            result=self._homing.cancel()
            if result is not None:
                return self._finish(result.status,'preparation_'+result.reason)
            return None
        if self.phase in ('running','verifying','stopping'):
            return self._shutdown('user_cancelled_motion')
        if self.pending:
            if self._future is not None:
                self._future.cancel()
            moved=self.feature_id=='M06' and self._program is not None
            return self._finish('ABORTED','measured_position_not_returned' if moved else 'cancelled_before_motion')
        return None
    def close(self):
        self.cancel()
        self._closed=True
