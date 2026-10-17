"""TEMPORARY MAINTENANCE TEST TRACE. Opt-in observation; no hardware owner."""
from collections import deque
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
from io import BytesIO
from itertools import islice
from pathlib import Path
from threading import Lock
from time import monotonic, time
import hashlib
import json
import math
import re
import subprocess
import uuid
import zipfile

MAX_LINE = 8192
MAX_PENDING = 128
MAX_FILE = 4 * 1024 * 1024
MAX_EXPORT = 10 * 1024 * 1024
PRIVATE = re.compile(r'password|secret|token|api.?key|filename|file_path|ssid|hostname|address|serial', re.I)
TEXT = re.compile(r'[A-Za-z0-9_ .,:>+%=?()/\[\]-]{0,240}')
STATUS_FIELDS = frozenset(('temperature target power speed value enabled state is_active '
    'is_paused filament_detected position homed_axes axis_minimum axis_maximum '
    'absolute_coordinates absolute_extrude speed_factor extrude_factor homing_origin '
    'steppers profile_name mesh_min mesh_max max_velocity '
    'z_position last_query last_z_result pressure force raw_force tare_offset '
    'diameter width humidity rpm pulse_width color_data can_extrude '
    'save_config_pending queue_state eventtime frequency acceleration drv_status '
    'filament filament_pos grip locked action homed gate tool sync_drive').split())


def clean(value, depth=0):
    if depth > 5:
        return None
    if value is None or type(value) is bool:
        return value
    if type(value) in (int, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value if (len(value)<=240 and TEXT.fullmatch(value)
                         and not re.search(r'(?<! )/|/(?! )',value)) else '[omitted]'
    if isinstance(value, (tuple, list)):
        return [clean(v,depth+1) for v in value[:32]
                if not (isinstance(v,(tuple,list)) and len(v)==2
                    and isinstance(v[0],str) and PRIVATE.search(v[0]))]
    if isinstance(value, Mapping):
        return {k:clean(v,depth+1) for k,v in islice(value.items(),32)
                if isinstance(k,str) and TEXT.fullmatch(k) and not PRIVATE.search(k)}
    return None


# Exact Petrel MMU guard messages only; arbitrary exception text stays private.
_MMU_ERRORS = {
    "MMU unavailable": "mmu_mmu_unavailable",
    "Wait for MMU operation": "mmu_wait_for_mmu_operation",
    "Acknowledge MMU result first": "mmu_acknowledge_mmu_result_first",
    "MMU disabled or unknown": "mmu_mmu_disabled_or_unknown",
    "MMU busy or recovery needed": "mmu_mmu_busy_or_recovery_needed",
    "Another operation is active": "mmu_another_operation_is_active",
    "Print state unknown": "mmu_print_state_unknown",
    "Printing; monitoring only": "mmu_printing_monitoring_only",
    "Use recovery during a pause": "mmu_use_recovery_during_a_pause",
    "MMU lock state unknown": "mmu_mmu_lock_state_unknown",
    "Invalid gate": "mmu_invalid_gate",
    "Unload filament first": "mmu_unload_filament_first",
    "Known filament position required": "mmu_known_filament_position_required",
    "Choose a different known MMU enable state": "mmu_choose_a_different_known_mmu_enable_state",
    "Known MMU driver states required": "mmu_known_mmu_driver_states_required",
    "Choose a valid MMU unit": "mmu_choose_a_valid_mmu_unit",
    "Validated multiple units required": "mmu_validated_multiple_units_required",
    "Known unit LED state required": "mmu_known_unit_led_state_required",
    "Unsupported LED exit mode": "mmu_unsupported_led_exit_mode",
    "Choose a different supported exit mode": "mmu_choose_a_different_supported_exit_mode",
    "Choose a different known LED state": "mmu_choose_a_different_known_led_state",
    "Select an available gate first": "mmu_select_an_available_gate_first",
    "Mapped available gate required": "mmu_mapped_available_gate_required",
    "Tool mapping changed": "mmu_tool_mapping_changed",
    "Unload the current gate": "mmu_unload_the_current_gate",
    "Unload current filament first": "mmu_unload_current_filament_first",
    "Select bypass first": "mmu_select_bypass_first",
    "Choose actual tool/gate/state": "mmu_choose_actual_tool_gate_state",
    "MMU is not locked": "mmu_mmu_is_not_locked",
    "Complete valid tool map required": "mmu_complete_valid_tool_map_required",
    "Complete EndlessSpool state required": "mmu_complete_endlessspool_state_required",
    "Spoolman mode blocks local assignment": "mmu_spoolman_mode_blocks_local_assignment",
    "Known spool IDs and valid assignment required": "mmu_known_spool_ids_and_valid_assignment_required",
    "Known filament temperature required": "mmu_known_filament_temperature_required",
    "Select an MMU gate first": "mmu_select_an_mmu_gate_first",
    "Single homing selector required": "mmu_single_homing_selector_required",
    "Valid tool map required": "mmu_valid_tool_map_required",
    "Known active unit and gate required": "mmu_known_active_unit_and_gate_required",
    "Home selector before drive operations": "mmu_home_selector_before_drive_operations",
    "Grip-capable selector telemetry required": "mmu_grip_capable_selector_telemetry_required",
    "Selector cannot release filament": "mmu_selector_cannot_release_filament",
    "Loaded filament and known sync state required": "mmu_loaded_filament_and_known_sync_state_required",
    "Always-gripped unit cannot unsync": "mmu_always_gripped_unit_cannot_unsync",
    "Recover and unlock first": "mmu_recover_and_unlock_first",
    "Unsupported MMU operation": "mmu_unsupported_mmu_operation",
}

_RPC_ERRORS = {
    'Moonraker command failed; check printer':'moonraker_server_error',
    'Printer state changed before command dispatch':'rpc_guard_denied',
    'Printer connection changed before command dispatch':'rpc_connection_changed',
    'Connection changed during dispatch guard':'rpc_connection_changed_during_guard',
    'Moonraker subscription is not ready':'rpc_subscription_not_ready',
    'Moonraker request timed out':'rpc_request_timeout',
    'WebSocket command dispatch failed':'rpc_dispatch_failed',
    'Subscription command queue is full':'rpc_queue_full',
    'Too many outstanding Moonraker requests':'rpc_pending_limit',
}

def error_info(exc):
    message = str(exc)
    code=_RPC_ERRORS.get(message,_MMU_ERRORS.get(message))
    diagnostic=getattr(exc,'diagnostic_code',None)
    if diagnostic in {'moonraker_server_error','klipper_unknown_command',
                      'klipper_unknown_stepper','klipper_home_required',
                      'klipper_move_out_of_range','klipper_not_ready'}:
        code=diagnostic
    out={'type':type(exc).__name__, 'code':code or
         (message if re.fullmatch(r'[a-z][a-z0-9_]{0,159}',message) else 'details_omitted')}
    rpc_code=getattr(exc,'rpc_code',None)
    if type(rpc_code) is int:
        out['rpc_code']=rpc_code
    return out


def measurements(reply):
    result = reply.get('result',{}) if isinstance(reply,Mapping) else {}
    if not isinstance(result,Mapping):
        return {}
    out = {}
    status = result.get('status',{})
    if isinstance(status,Mapping):
        for name,values in islice(status.items(),32):
            if isinstance(name,str) and isinstance(values,Mapping) and TEXT.fullmatch(name):
                out[name] = {k:clean(v) for k,v in values.items() if k in STATUS_FIELDS}
    for key in ('eventtime','queue_state'):
        if key in result:
            out[key] = clean(result[key])
    if isinstance(result.get('queued_jobs'),list):
        out['queued_jobs_count'] = len(result['queued_jobs'])
    for key,value in islice(result.items(),32):
        if isinstance(key,str) and key.startswith('stepper_') and isinstance(value,str) and value in ('open','TRIGGERED'):
            out[key] = value
    return out


def script_summary(payload):
    script = payload.get('script') if isinstance(payload,Mapping) else None
    if not isinstance(script,str):
        return {}
    commands = []
    for line in script.splitlines()[:64]:
        words = line.split()
        if not words or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,47}',words[0]):
            continue
        numeric = {}
        for word in words[1:24]:
            match = re.fullmatch(r'([A-Z_]+)=?(-?[0-9]+(?:\.[0-9]+)?)',word)
            if match:
                numeric[match[1]] = float(match[2])
        commands.append({'command':words[0],'numeric':numeric})
    return {'sha256':hashlib.sha256(script.encode()).hexdigest(),'commands':commands}


def owner_snapshot(owner):
    try:
        if hasattr(owner,'_owners'):
            owner = owner._active
        out = {}
        for key in ('_phase','_action','_index','_step','_stop_reason','_blocked','_locked',
                    '_sent','_off_matches','_metric_ok','_measurement','_evidence','_metrics',
                    '_pid_proof','_gpio_start','_restore','_last_read_point','_safety_reason','_queue_age_s','_confirm_attempts','_refresh_reason','_dispatch_guard_reason'):
            value = getattr(owner,key,None)
            if is_dataclass(value):
                value = {f.name:getattr(value,f.name) for f in fields(value)}
            if value is not None:
                out[key.lstrip('_')] = clean(value)
        if getattr(owner,'_homing',None) is not None:
            out['phase']=clean(owner.phase)
            out['preparation']=owner_snapshot(owner._homing)
        row = getattr(owner,'_row',None)
        if row is not None:
            out['plan'] = {k:clean(getattr(row,k,None)) for k in
                ('feature_id','device','method','epoch','config_marker','adapter_id')}
        for key in ('_contract','_program'):
            value = getattr(owner,key,None)
            if value is not None:
                out[key[1:]] = {k:clean(getattr(value,k,None)) for k in
                    ('target','duration','ceiling','min_temp','distance','axis','returning','deadline_s')}
        for key in ('live_text','workflow_choices','f12_status','pwm_levels','measurement_value','preparing_home','preparation_stage'):
            try:
                value = getattr(owner,key,None)
                if value is not None:
                    out[key] = clean(value)
            except Exception:
                pass
        return out
    except Exception:
        return {'snapshot':'unavailable'}


class TestTrace:
    def __init__(self,printer,directory=None):
        self.printer = printer
        self.directory = Path(directory) if directory is not None else Path.home()/'.config'/'Petrel'/'maintenance-test-trace'
        self.active = False
        self.session = self.run = None
        self.sequence = self.attempt = 0
        self.dropped = self.write_errors = self.rotations = 0
        self._pending = deque()
        self._lock,self._disk = Lock(),Lock()
        self._context = ContextVar('maintenance_test_trace',default=None)
        self._future = None
        self._next_flush = 0.
        self._undo = []
        self._last_ui = self._lifecycle = None
        self._metadata = False
        self._configs = deque(maxlen=8)
        self._config_key = None

    @property
    def label(self):
        return ('Stop recording (gaps)' if self.active else 'Start recording (gaps)') if self.dropped or self.write_errors else (
            'Stop test recording' if self.active else 'Start test recording')

    def context(self):
        return self._context.get() or {'session':self.session,'run':self.run}

    def emit(self,event,data=None,context=None):
        try:
            with self._lock:
                self.sequence += 1
                item = dict(context or self.context(),seq=self.sequence,utc=time(),
                            mono=monotonic(),event=event,data=clean(data))
                raw = json.dumps(item,allow_nan=False,separators=(',',':')).encode()+b'\n'
                if len(raw)>MAX_LINE:
                    item['data'] = {'omitted':'event_size_limit'}
                    raw = json.dumps(item,separators=(',',':')).encode()+b'\n'
                    self.dropped += 1
                if len(self._pending)>=MAX_PENDING:
                    self._pending.popleft()
                    self.dropped += 1
                self._pending.append(raw)
        except Exception:
            self.dropped += 1

    def replace(self,obj,key,value):
        self._undo.append((obj,key,getattr(obj,key)))
        setattr(obj,key,value)

    def start(self):
        if self.active:
            return False
        self.active = True
        self.session,self.run = uuid.uuid4().hex,None
        self._last_ui = None
        self._metadata = True
        self.emit('session_start',{'schema':1,'acceptance':'operator_observation_required'})
        router = self.printer.maintenance_pulse
        try:
            for owner in tuple(router._owners)+(self.printer.maintenance_reader,):
                self.replace(owner,'_printer',PrinterProxy(owner._printer,self))
                self.replace(owner,'_client',ClientProxy(owner._client,self))
                self.replace(owner,'_worker',WorkerProxy(owner._worker,self))
                executor = getattr(owner,'_executor',None)
                if executor is not None:
                    self.replace(executor,'_client',ClientProxy(executor._client,self))
                    self.replace(executor,'_worker',WorkerProxy(executor._worker,self))
                if hasattr(owner,'_shutdown'):
                    original = owner._shutdown
                    def shutdown(reason,_call=original,_owner=owner):
                        self.emit('safety_shutdown',{'reason':reason,'snapshot':owner_snapshot(_owner)})
                        return _call(reason)
                    self.replace(owner,'_shutdown',shutdown)
            self.replace(self.printer,'maintenance_pulse',OwnerProxy(router,self))
            self.replace(self.printer,'maintenance_reader',OwnerProxy(self.printer.maintenance_reader,self))
        except Exception:
            self.stop()
            raise
        return True

    def stop(self):
        if self.active:
            self.emit('session_stop',{'dropped':self.dropped,'write_errors':self.write_errors})
        self.active = False
        while self._undo:
            obj,key,value = self._undo.pop()
            setattr(obj,key,value)
        self.tick(None)

    def ui(self,view,kind='tick',event=None,title=None,entries=None):
        if not self.active:
            return
        try:
            screen = getattr(view,'checkkey',None)
            on_menu = screen==getattr(view,'MaintenanceMenu',object())
            state = {'screen':screen,'screen_name':next((k for k in (
                'MaintenanceMenu','MainMenu','RecoveryScreen','PrintErrorDetails',
                'Popup_Window','Info','PrintProcess') if getattr(view,k,object())==screen),'other'),
                'page':getattr(view,'_maintenance_page',None) if on_menu else None,
                'selection':getattr(view,'_maintenance_selection',None) if on_menu else None,
                'parent':getattr(view,'_maintenance_result_parent',None) if on_menu else None,
                'parent_selection':getattr(view,'_maintenance_result_selection',None) if on_menu else None,
                'physical':owner_snapshot(self.printer.maintenance_pulse),
                'read_phase':getattr(self.printer.maintenance_reader,'_phase',None)}
            if title is not None:
                view._maintenance_trace_drawn = {'title':clean(title),
                    'row_count':len(entries),
                    'selected_label':clean(entries[state['selection']][0]) if state['selection'] is not None and 0<=state['selection']<len(entries) else None,
                    'nearby_rows':[(i,clean(entries[i][0])) for i in range(
                        max(0,(state['selection'] or 0)-2),min(len(entries),(state['selection'] or 0)+4))]}
            if on_menu:
                state['drawn'] = getattr(view,'_maintenance_trace_drawn',None)
            state['pending_offscreen'] = bool((self.printer.maintenance_pulse.pending or self.printer.maintenance_reader.pending) and not on_menu)
            # Only transitions on ticks/draws; every real input has before/after.
            comparison = {k:v for k,v in state.items() if k!='physical'}
            comparison['phase'] = state['physical'].get('phase')
            if event is not None or comparison!=self._last_ui:
                previous = self._last_ui
                self._last_ui = comparison
                value = {'kind':kind,'from':previous,'to':state}
                if event is not None:
                    value['input'] = {k:getattr(event,k,None) for k in
                        ('kind','value','epoch','ui_epoch','rate','accelerated_value')}
                self.emit('ui',value)
                if previous is not None:
                    if (previous.get('page')=='pulse' and
                            previous.get('phase')=='await_confirmation' and
                            comparison.get('phase')=='preflight'):
                        self.emit('ui_flow',{'code':'confirmation_safety_refresh',
                            'from_title':(previous.get('drawn') or {}).get('title'),
                            'to_title':(comparison.get('drawn') or {}).get('title'),
                            'physical':state['physical']})
                    if (previous.get('page')=='pulse' and
                            (state['page']!='pulse' or not on_menu) and
                            self.printer.maintenance_pulse.pending):
                        self.emit('ui_anomaly',{'code':'left_test_while_pending',
                            'from':previous,'to':state})
        except Exception:
            self.dropped += 1

    def tick(self,state):
        try:
            if self.active and state is not None:
                lifecycle = (state.ready,state.epoch)
                if lifecycle!=self._lifecycle:
                    self._lifecycle = lifecycle
                    self.emit('lifecycle',{'ready':state.ready,'epoch':state.epoch})
            if self._future is not None:
                if not self._future.done():
                    return
                self._future.result()
                self._future = None
            if monotonic()<self._next_flush or not (self._pending or self._metadata or self._configs):
                return
            self._next_flush = monotonic()+1.
            # Existing non-maintenance worker; never ahead of a safety read.
            self._future = self.printer._read_worker.submit(self.flush,queue_timeout=5)
        except Exception:
            self.write_errors += 1
            self._future = None

    def flush(self):
        with self._disk:
            batch = b''
            try:
                if self._metadata:
                    self._metadata = False
                    sha = 'unavailable'
                    try:
                        sha = subprocess.run(['git','-C',str(Path(__file__).resolve().parent),
                            'rev-parse','HEAD'],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
                        if not re.fullmatch(r'[0-9a-f]{40,64}',sha):
                            sha = 'unavailable'
                    except (OSError,subprocess.SubprocessError):
                        pass
                    self.emit('source',{'head':sha})
                while self._configs:
                    context,settings,epoch,firmware = self._configs.popleft()
                    digest = hashlib.sha256(json.dumps(settings,sort_keys=True,default=str).encode()).hexdigest()
                    self.emit('config_context',{'epoch':epoch,'firmware':firmware,'sha256':digest},context)
                if self.directory.is_symlink():
                    raise ValueError('trace_directory_symlink')
                self.directory.mkdir(parents=True,exist_ok=True)
                path,old = self.directory/'events.jsonl',self.directory/'events.previous.jsonl'
                if path.is_symlink() or old.is_symlink():
                    raise ValueError('trace_file_symlink')
                with self._lock:
                    batch = b''.join(self._pending)
                    self._pending.clear()
                if not batch:
                    return
                if path.exists() and path.stat().st_size+len(batch)>MAX_FILE:
                    path.replace(old)
                    self.rotations += 1
                with path.open('ab') as stream:
                    stream.write(batch)
                    stream.flush()
            except Exception:
                self.write_errors += 1
                self.dropped += batch.count(b'\n')

    def exported(self):
        """Read-only snapshot includes pending tail, without flushing or reset."""
        with self._disk:
            if self.directory.is_symlink():
                raise ValueError('trace_directory_symlink')
            output = BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                for name in ('events.previous.jsonl','events.jsonl'):
                    path = self.directory/name
                    if path.is_symlink():
                        raise ValueError('trace_file_symlink')
                    if path.is_file():
                        if path.stat().st_size>MAX_FILE:
                            raise ValueError('trace_file_oversize')
                        archive.writestr(name,path.read_bytes())
                with self._lock:
                    pending = b''.join(self._pending)
                    manifest = dict(schema=1,session=self.session,active=self.active,
                        last_seq=self.sequence,dropped_events=self.dropped,write_errors=self.write_errors,
                        rotations=self.rotations,retention_bytes=2*MAX_FILE,pending_events=len(self._pending),
                        coverage='event_trace_not_physical_acceptance')
                archive.writestr('pending.jsonl',pending)
                archive.writestr('manifest.json',json.dumps(manifest,indent=2))
                archive.writestr('README.txt',
                    'Read previous, current, pending JSONL in order; group by session/run.\n'
                    'utc = Unix time; mono = process monotonic time. RPC OK is not physical PASS.\n'
                    'UI from/to + input identify unexpected returns and hidden active tests.\n'
                    'No result after start = unfinished; never inferred PASS.\n'
                    'Dropped events/write errors/rotations indicate gaps or bounded retention.\n'
                    'Raw firmware messages, config, filenames, URLs and secrets are omitted.\n')
            return output.getvalue()


class Proxy:
    def __init__(self,target,trace):
        self._target,self._trace = target,trace
    def __getattr__(self,key):
        return getattr(self._target,key)


class OwnerProxy(Proxy):
    ACTIONS = frozenset(('start','confirm','choose','observe','cancel','close','poll',
        'begin_measurement','adjust_measurement','record_measurement','f12_confirm_stopped'))
    def __init__(self,target,trace):
        super().__init__(target,trace)
        self._last,self._sample_at = None,0.
    def __getattr__(self,key):
        call = getattr(self._target,key)
        if key not in self.ACTIONS or not callable(call):
            return call
        def invoke(*args,**kwargs):
            trace = self._trace
            if not trace.active:
                return call(*args,**kwargs)
            if key=='start' and not getattr(self._target,'pending',False):
                trace.attempt += 1
                trace.run = trace.attempt
                self._last = None
                state = trace.printer.state
                identity = (state.epoch,id(state.settings),trace.session)
                if identity!=trace._config_key:
                    trace._config_key = identity
                    if len(trace._configs)==8:
                        trace.dropped += 1
                    trace._configs.append((dict(trace.context()),state.settings,
                        state.epoch,getattr(state,'software_version',None)))
            context = dict(trace.context())
            if key!='poll':
                trace.emit('action',{'name':key,'args':args,'options':kwargs,
                                    'before':owner_snapshot(self._target)},context)
            try:
                result = call(*args,**kwargs)
            except Exception as exc:
                trace.emit('action_error',{'name':key,'error':error_info(exc)},context)
                raise
            snapshot = owner_snapshot(self._target)
            transition = {k:v for k,v in snapshot.items() if k not in ('live_text','last_read_point','queue_age_s')}
            changed = transition!=self._last
            if changed or (getattr(self._target,'pending',False) and monotonic()>=self._sample_at):
                trace.emit('stage' if changed else 'sample',snapshot,context)
                self._last,self._sample_at = transition,monotonic()+1.
            if result is not None:
                if hasattr(result,'reason') and hasattr(result,'feature_id'):
                    trace.emit('result',{k:getattr(result,k,None) for k in
                        ('feature_id','device','status','reason','restore_verified','evidence')},context)
                elif key!='poll':
                    trace.emit('action_return',{'name':key,'value':result},context)
            return result
        return invoke


class WorkerProxy(Proxy):
    def submit(self,work,*args,**kwargs):
        trace,context = self._trace,dict(self._trace.context())
        def observed():
            token = trace._context.set(context)
            try:
                return work()
            except Exception as exc:
                trace.emit('worker_error',error_info(exc),context)
                raise
            finally:
                trace._context.reset(token)
        return self._target.submit(observed,*args,**kwargs)


class ClientProxy(Proxy):
    def get(self,path,*args,**kwargs):
        try:
            result = self._target.get(path,*args,**kwargs)
        except Exception as exc:
            self._trace.emit('read_error',error_info(exc))
            raise
        try:
            self._trace.emit('read',{'values':measurements(result)})
        except Exception:
            self._trace.dropped += 1
        return result


def traced_request(trace,call,method,payload,args,kwargs):
    context = dict(trace.context())
    try:
        trace.emit('rpc_submit',{'method':method,'script':script_summary(payload)},context)
    except Exception:
        trace.dropped += 1
    try:
        future = call(method,payload,*args,**kwargs) if payload is not None else call(method,*args,**kwargs)
    except Exception as exc:
        trace.emit('rpc_error',error_info(exc),context)
        raise
    def completed(done):
        try:
            if done.cancelled():
                trace.emit('rpc_cancelled',{},context)
            else:
                error = done.exception()
                trace.emit('rpc_error' if error else 'rpc_complete',
                    dict(error_info(error),dispatch_stage=getattr(done,'dispatch_stage',None)) if error else
                    {'cleanup_complete':getattr(done,'cleanup_complete',None),
                     'dispatch_stage':getattr(done,'dispatch_stage',None)},context)
        except Exception:
            trace.dropped += 1
    try:
        future.add_done_callback(completed)
    except Exception:
        trace.dropped += 1
    return future


class SubscriptionProxy(Proxy):
    def request(self,method,payload=None,*args,**kwargs):
        return traced_request(self._trace,self._target.request,method,payload,args,kwargs)


class PrinterProxy(Proxy):
    def __init__(self,target,trace):
        super().__init__(target,trace)
        self.subscription = SubscriptionProxy(target.subscription,trace)
    def postREST(self,path,payload,*args,**kwargs):
        return traced_request(self._trace,self._target.postREST,path,payload,args,kwargs)
