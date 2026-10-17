"""Measured extrusion, filament sensors, load cells and declared drying roles."""
from collections.abc import Mapping
from dataclasses import replace
import json
import math
from pathlib import Path
import re
import uuid

from maintenance_discovery import AUTOMATIC, USER, EXTERNAL, CALIBRATION
from maintenance_workflow import FirmwareWorkflow, safe_name, query
from maintenance_motion import number, modal, vector
from maintenance_runtime import read_queue_evidence
from mmu_control import MMUState

METHODS = {'E01':USER,'E02':EXTERNAL,'E03':USER,'E04':AUTOMATIC,
    'E05':AUTOMATIC,'E06':AUTOMATIC,'E07':USER,'E08':AUTOMATIC,
    'E09':EXTERNAL,'E11':USER,'E12':USER,'E14':CALIBRATION}
EXTRUSION = frozenset(('E01','E02','E04','E07'))


def profile_path():
    return Path.home()/'.config'/'Petrel'/'maintenance-filament.json'


def profile():
    try:
        path = profile_path()
        if path.stat().st_size>8192:
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data,dict) or type(data.get('version')) is not int
                or data['version']!=1 or set(data)-{'version','dryers','chamber_sensor','material_history','loadcell_reference'}):
            return {}
        return data
    except (OSError,ValueError,TypeError):
        return {}


def filament_services(state):
    data = profile()
    result = []
    if isinstance(data.get('loadcell_reference'),str) and 1 <= len(data['loadcell_reference']) <= 64:
        result.append('maintenance.loadcell_reference')
    if isinstance(data.get('material_history'),list) and data['material_history']:
        result.append('maintenance.material_usage')
    name = data.get('chamber_sensor')
    if isinstance(name,str) and name in state.objects:
        result.append('maintenance.chamber_humidity_sensor')
    if isinstance(data.get('dryers'),list):
        for item in data['dryers'][:4]:
            if isinstance(item,dict) and item.get('object') in state.objects:
                result.append('maintenance.dryer_profile')
                break
    if 'mmu' in state.objects and 'mmu_machine' in state.objects:
        result.append('petrel.mmu_test_adapter')
    return tuple(result)


class MaintenanceFilamentController(FirmwareWorkflow):
    methods,domain = METHODS,'filament'

    def __init__(self,*args):
        super().__init__(*args)
        self._stage = 0
        self._sensor = None
        self._sensor_restore = None
        self._measurement = None
        self._measured = False
        self._samples = []
        self._gram_edit = False
        self._owned_loadcell = False
        self._operation = None
        self._profile = {}
        self._remaining = 0.
        self._mechanical_seen = 0
        self._tare_done = self._calibrated = False
        self._sensor_disabled = self._restoring = False
        self._restore_outcome = None
        self._motion_seen = False

    def available(self):
        rows = []
        for row in super().available():
            if row.feature_id=='E14':
                dryers = profile().get('dryers',[])
                if isinstance(dryers,list):
                    rows.extend(replace(row,device=p['object']) for p in dryers[:4]
                        if isinstance(p,dict) and isinstance(p.get('object'),str)
                        and p['object'] in self._printer.state.objects)
            else:
                rows.append(row)
        return tuple(rows)

    @property
    def requires_homing(self):
        # Extruder/MMU/dryer operations do not move the printer XYZ axes.
        return False

    @property
    def moving(self):
        return self.feature_id in EXTRUSION or self.feature_id in ('E12','E14')

    @property
    def live_text(self):
        if self.feature_id in EXTRUSION:
            return ('Preheat in Temperature menu','Watch actual filament feed')
        if self.feature_id == 'E03':
            return (('Remove filament','Insert filament','Remove filament')[min(self._stage,2)],
                    'Sensor macros held disabled')
        if self.feature_id == 'E11':
            return ('Disable MMU in normal menu','Insert/remove sensor fragment')
        if self.feature_id == 'E09':
            return ('Use traceable reference mass','Tare / load / enter grams')
        if self.feature_id == 'E14':
            return ('Declared dryer only','Heater OFF at each segment')
        return ('No inferred clog diagnosis','Evidence is sensor-specific')

    @property
    def measurement_value(self):
        return self._measurement if self._measurement is not None else (100. if self.feature_id=='E09' else 10.)

    @property
    def measurement_unit(self):
        return 'g' if self.feature_id=='E09' else 'mm'

    @property
    def workflow_choices(self):
        f = self.feature_id
        if f=='E04':
            return (('Run 5mm sensor feed','extrude'),)
        if f=='E03':
            return ((self.live_text[0]+' / read','sample'),)
        if f=='E11':
            if self._sensor:
                return ((self._sensor[:16]+' / read','sample'),)
            sensors = self._values.get('mmu',{}).get('sensors',{})
            return tuple((str(name)[:26],'sensor:'+str(name)) for name,v in sorted(sensors.items())
                         if type(v) is bool)[:32]
        if f=='E12':
            return (('Grip drive','mmu:grip'),('Release drive','mmu:release'),
                    ('Home selector','mmu:home_selector'),('Finish mechanical check','finish'))
        if f=='E09':
            return (('Tare with no reference','tare'),('Enter reference grams','measure'),
                    ('Calibrate loaded reference','calibrate'),('Accept pending calibration','accept'))
        if f=='E02':
            return (('Enter measured feed mm','measure'),)
        if f in ('E05','E06','E08'):
            return (('Capture again','sample'),('Finish sensor evidence','finish'))
        return (('Observe actual result','finish'),)

    def start(self,*args,**kwargs):
        self._stage,self._sensor,self._sensor_restore = 0,None,None
        self._measurement,self._measured = None,False
        self._samples,self._owned_loadcell = [],False
        self._operation = None
        self._profile = profile()
        self._remaining = 0.
        self._token = 'PETREL_E_'+uuid.uuid4().hex
        return super().start(*args,**kwargs)

    def fields(self):
        fields = super().fields()
        fields['toolhead'] += ',extruder'
        names = set(self._printer.state.objects)
        if self._row.device in names:
            fields[self._row.device] = ''
        if self.feature_id in EXTRUSION:
            fields['gcode_move'] = ''
            for name in names:
                if re.fullmatch(r'extruder[0-9]*',name):
                    fields[name] = ''
        if self.feature_id in ('E11','E12'):
            fields['mmu'] = ''
            fields['mmu_machine'] = ''
        if self.feature_id in ('E14','E15'):
            if self.feature_id=='E15':
                name = self._profile.get('chamber_sensor')
                if isinstance(name,str) and name in self._printer.state.objects:
                    fields[name] = 'humidity'
        return fields

    def _dryer(self):
        dryers = self._profile.get('dryers')
        if not isinstance(dryers,list) or not 1 <= len(dryers) <= 4:
            raise ValueError('declare_one_unambiguous_dryer')
        selected = [p for p in dryers if isinstance(p,dict) and p.get('object')==self._row.device]
        if len(selected)!=1:
            raise ValueError('dryer_instance_unverified')
        p = selected[0]
        if not isinstance(p,dict) or set(p)!={'object','target','ceiling','duration_s'}:
            raise ValueError('dryer_profile_invalid')
        name = p['object']
        if not isinstance(name,str) or not name.startswith('heater_generic '):
            raise ValueError('explicit_generic_dryer_required')
        safe_name(name.split(' ',1)[1])
        cfg = self._printer.state.settings.get(name,{})
        if (name not in self._printer.state.objects or
                not all(number(p[k]) for k in ('target','ceiling','duration_s'))
                or not number(cfg.get('min_temp')) or not number(cfg.get('max_temp'))
                or not cfg['min_temp'] < p['target'] < p['ceiling'] < cfg['max_temp']
                or not 5 <= p['ceiling']-p['target'] <= 15
                or not 30 <= p['duration_s'] <= 21600):
            raise ValueError('dryer_limits_unverified')
        return p

    def validate(self,values,action):
        # The selected extruder/dryer has its own positive thermal contract.
        masked = dict(values)
        heater = None
        if self.feature_id in EXTRUSION:
            th = values.get('toolhead',{})
            heater = th.get('extruder')
            if heater is None:
                # Older firmware exposes extruder separately in toolhead;
                # absence must never silently choose a different tool.
                raise ValueError('active_extruder_unknown')
            if heater!='extruder' and not re.fullmatch(r'extruder[0-9]+',str(heater)):
                raise ValueError('active_extruder_invalid')
            cfg = self._printer.state.settings.get(heater,{})
            status = values.get(heater,{})
            minimum = cfg.get('min_extrude_temp',170.)
            maximum = cfg.get('max_temp')
            if (not number(minimum) or not number(maximum)
                    or not all(number(status.get(k)) for k in ('temperature','target','power'))
                    or not minimum+5 <= status['temperature'] <= maximum-15
                    or not minimum+5 <= status['target'] <= maximum-15
                    or abs(status['temperature']-status['target'])>10
                    or status.get('can_extrude') is not True):
                raise ValueError('preheat_active_extruder_before_test')
            if self.feature_id=='E04':
                cfg_sensor = self._printer.state.settings.get(self._row.device,{})
                if cfg_sensor.get('extruder') != heater:
                    raise ValueError('motion_sensor_extruder_mismatch')
            if action!='restore':
                self._modes = modal(values)
        elif self.feature_id=='E14':
            p = self._dryer()
            heater = p['object']
            actual = values.get(heater,{})
            if (actual.get('target') != 0 or not number(actual.get('temperature'))
                    or actual['temperature'] >= p['ceiling']):
                raise ValueError('dryer_not_idle_or_too_hot')
        if heater:
            masked[heater] = {'temperature':20.,'target':0.,'power':0.}
        super().validate(masked,action)
        if self.feature_id in ('E03','E04'):
            status = values.get(self._row.device,{})
            if type(status.get('enabled')) is not bool or type(status.get('filament_detected')) is not bool:
                raise ValueError('filament_sensor_state_unknown')
            if action=='start':
                self._sensor_restore = status['enabled']
            if self.feature_id=='E04' and action=='extrude' and status['filament_detected'] is not False:
                raise ValueError('motion_sensor_fresh_transition_required')
        if self.feature_id=='E11':
            mmu = values.get('mmu',{})
            if mmu.get('enabled') is not False:
                raise ValueError('disable_mmu_before_manual_sensor_test')
            sensors = mmu.get('sensors')
            if not isinstance(sensors,Mapping) or len(sensors)>32:
                raise ValueError('mmu_sensor_inventory_invalid')

    def _loadcell(self):
        name = self._row.device
        if name=='load_cell':
            return name
        if isinstance(name,str) and name.startswith('load_cell '):
            return safe_name(name.split(' ',1)[1])
        raise ValueError('loadcell_instance_unverified')

    def script(self,action,values):
        f = self.feature_id
        if action=='abort':
            return 'ABORT'
        if f in EXTRUSION:
            if f=='E04' and action=='start':
                return 'SET_FILAMENT_SENSOR SENSOR='+safe_name(self._row.device.split(' ',1)[1])+' ENABLE=0'
            if f=='E04' and action=='restore':
                return 'SET_FILAMENT_SENSOR SENSOR='+safe_name(self._row.device.split(' ',1)[1])+' ENABLE='+str(int(self._sensor_restore))

            distance = 10. if f=='E02' else 5.
            return ('SAVE_GCODE_STATE NAME='+self._token+'\nM83\nM221 S100\nG1 E%.3f F60\nM400\nRESTORE_GCODE_STATE NAME='%distance+self._token+' MOVE=0')
        if f=='E03':
            name = safe_name(self._row.device.split(' ',1)[1])
            return ('SET_FILAMENT_SENSOR SENSOR='+name+' ENABLE='+str(int(self._sensor_restore))) if action=='restore' else (
                'SET_FILAMENT_SENSOR SENSOR='+name+' ENABLE=0') if action=='start' else 'QUERY_FILAMENT_SENSOR SENSOR='+name
        if f in ('E05','E06'):
            return 'QUERY_FILAMENT_WIDTH'
        if f=='E08':
            return 'LOAD_CELL_DIAGNOSTIC LOAD_CELL='+self._loadcell()
        if f=='E09':
            if action=='start':
                return 'LOAD_CELL_CALIBRATE LOAD_CELL='+self._loadcell()
            if action=='tare':
                return 'TARE'
            if action=='calibrate':
                if not self._tare_done or not self._measured or not 50 <= self.measurement_value <= 25000:
                    raise ValueError('tare_and_enter_traceable_reference_grams')
                return 'CALIBRATE GRAMS=%.3f'%self.measurement_value
            if action=='accept':
                if not self._calibrated:
                    raise ValueError('calibrate_reference_before_accept')
                return 'ACCEPT'
        if f=='E11':
            return 'MMU_SENSORS'
        if f=='E12':
            if action=='start':
                return 'MMU_STATUS'
            requested = action.removeprefix('mmu:')
            if requested not in ('grip','release','home_selector'):
                raise ValueError('mmu_mechanical_action_invalid')
            self._operation = self._printer.mmu_session.prepare(requested,tool=0 if requested=='home_selector' else None)
            return self._operation.script
        if f=='E13':
            return 'STATUS'
        if f=='E15':
            return 'STATUS'
        if f=='E14':
            p = self._dryer()
            if not self._remaining:
                self._remaining = p['duration_s']
            self._segment = min(600.,self._remaining)
            heater = p['object'].split(' ',1)[1]
            return ('SET_HEATER_TEMPERATURE HEATER='+heater+' TARGET=%.3f\n'%p['target']+
                    'TEMPERATURE_WAIT SENSOR="'+p['object']+'" MINIMUM=%.3f\n'%(p['target']-1)+
                    'G4 P%d\n'%int(self._segment*1000)+
                    'SET_HEATER_TEMPERATURE HEATER='+heater+' TARGET=0\nM400')
        raise ValueError('filament_action_unavailable')

    def dispatch(self,script,guard):
        if self.feature_id in ('E03','E04') and self._action=='start':
            self._sensor_disabled = True
        if script.startswith('SAVE_GCODE_STATE NAME='):
            return self._printer.subscription.request_script_with_cleanup(script,
                'RESTORE_GCODE_STATE NAME='+self._token+' MOVE=0',guard)
        return super().dispatch(script,guard)

    def context(self,queue):
        context = super().context(queue)
        if self.feature_id=='E12' and self._operation is not None and self.phase=='running' and context.state is not None:
            from types import SimpleNamespace
            state = context.state
            mmu = state.status.get('mmu',{})
            if mmu.get('enabled') is True and mmu.get('locked') is False:
                status = dict(state.status)
                status['mmu'] = dict(mmu,action='Idle')
                context = replace(context,state=SimpleNamespace(ready=state.ready,
                    epoch=state.epoch,settings=state.settings,status=status))
        return context

    def runtime_evidence(self):
        queue = super().runtime_evidence()
        if self.feature_id=='E14':
            p = self._dryer()
            values,stamp = query(self._client,{p['object']:'temperature,target,power'})
            actual = values.get(p['object'],{})
            if (not number(actual.get('temperature')) or actual['temperature']>=p['ceiling']
                    or actual.get('target') not in (0,p['target'])):
                raise ValueError('dryer_thermal_limit')
        return queue

    def completed(self,values,lines):
        self._values = values
        f = self.feature_id
        if self._action=='abort':
            self._owned_loadcell = False
            return self._finish('ABORTED','loadcell_calibration_aborted')
        if f in ('E03','E04') and self._action=='restore':
            restored = values.get(self._row.device,{}).get('enabled') is self._sensor_restore
            if not restored:
                self._locked = True
                return super()._finish('INCONCLUSIVE','filament_sensor_restore_unverified')
            self._sensor_disabled = False
            if self._restore_outcome is not None:
                status,reason,evidence = self._restore_outcome
                self._restore_outcome = None
                return super()._finish(status,reason+'_sensor_restored',evidence,True)
        if f=='E03':
            status = values.get(self._row.device,{})
            if self._action=='restore':
                if status.get('enabled') is not self._sensor_restore:
                    return self._finish('INCONCLUSIVE','filament_sensor_restore_unverified')
                return self._finish('PASSED' if self._stage==3 else 'ABORTED',
                    'filament_absent_present_absent_restored',(('transitions','absent > present > absent'),),True)
            if status.get('enabled') is not False:
                return self._finish('INCONCLUSIVE','filament_sensor_not_disabled')
            if self._action=='sample':
                expected = (False,True,False)[self._stage]
                if status.get('filament_detected') is expected:
                    self._stage += 1
                if self._stage==3:
                    self._schedule('restore',True)
                    return None
            self._phase = 'workflow'
            return None
        if f in EXTRUSION:
            if f=='E04':
                if self._action=='start':
                    self._phase = 'workflow'
                    return None
                if self._action=='restore':
                    restored = values.get(self._row.device,{}).get('enabled') is self._sensor_restore
                    return self._finish('PASSED' if restored and self._motion_seen else 'INCONCLUSIVE',
                        'motion_sensor_signal_not_length_measurement',restored=restored)
                if modal(values)!=self._modes:
                    return self._shutdown('extrusion_modal_restore_unverified')
                self._motion_seen = values.get(self._row.device,{}).get('filament_detected') is True
                self._schedule('restore',True)
                return None
            if modal(values)!=self._modes:
                return self._shutdown('extrusion_modal_restore_unverified')
            self._evidence = (('commanded_mm',10. if f=='E02' else 5.),('modal_restore_verified',True))
            self._phase = 'workflow' if f=='E02' else 'await_observation'
            return None
        if f in ('E05','E06'):
            status = values.get(self._row.device,{})
            diameter = status.get('Diameter',status.get('diameter'))
            if not number(diameter) or not 0 < diameter < 5:
                return self._finish('INCONCLUSIVE','filament_width_sample_unavailable')
            self._samples.append(float(diameter))
            self._samples = self._samples[-64:]
            self._evidence = (('diameter_mm',diameter),('samples',len(self._samples)),
                ('minimum_mm',min(self._samples)),('maximum_mm',max(self._samples)),
                ('mean_mm',sum(self._samples)/len(self._samples)))
            if f=='E06':
                from maintenance_width_history import capture
                state = self._printer.state
                self._future = self._worker.submit(lambda:capture(self._row.device,
                    state.settings.get(self._row.device),state.software_version,diameter),queue_timeout=4)
                from time import monotonic
                self._phase,self._deadline = 'analysis',monotonic()+8
            else:
                self._phase = 'workflow'
            return None
        if f=='E08':
            match = re.search(r'Samples Collected: ([0-9]+)','\n'.join(lines))
            if not match or int(match[1])<=0:
                return self._finish('INCONCLUSIVE','loadcell_samples_missing')
            text = '\n'.join(lines)
            if 'Sensor reported no errors' not in text:
                return self._finish('FAILED','loadcell_sensor_errors_reported',(('samples',int(match[1])),))
            self._evidence = (('samples',int(match[1])),('reported_errors',0))
            self._phase = 'workflow'
            return None
        if f=='E09':
            text = '\n'.join(lines)
            if self._action=='tare':
                self._tare_done = 'Load cell tare value:' in text
            if self._action=='calibrate':
                match = re.search(r'Counts/gram: ([0-9.]+)',text)
                self._calibrated = bool(match and float(match[1])>0)
            if self._action=='accept':
                pending = values.get('configfile',{}).get('save_config_pending_items',{})
                if self._row.device not in pending:
                    return self._finish('INCONCLUSIVE','loadcell_calibration_result_missing')
                self._owned_loadcell = False
                self._evidence = (('reference_grams',self.measurement_value),('saved',False))
                self._phase = 'await_observation'
            else:
                self._owned_loadcell = True
                self._phase = 'workflow'
            return None
        if f=='E11':
            if self._sensor and self._action=='sample':
                state = values.get('mmu',{}).get('sensors',{}).get(self._sensor)
                if state is (False,True,False)[self._stage]:
                    self._stage += 1
                if self._stage==3:
                    return self._finish('PASSED','mmu_sensor_absent_present_absent',
                        (('sensor',self._sensor),('transitions','absent > present > absent')))
            self._phase = 'workflow'
            return None
        if f=='E12':
            if self._operation is not None:
                from mmu_control import MMUSession
                verifier = MMUSession(self._printer)
                verifier.operation = self._operation
                raw = self._printer.subscription.snapshot()
                raw['status'] = dict(raw.get('status',{}),**values)
                if not verifier._confirmed(MMUState.from_snapshot(raw),values):
                    return self._finish('INCONCLUSIVE','mmu_mechanical_state_unverified')
                self._mechanical_seen += 1
                self._evidence = (('action',self._operation.action),('firmware_state_confirmed',True))
            self._phase = 'workflow'
            return None
        if f=='E13':
            records = self._profile.get('material_history')
            if not isinstance(records,list) or not 1 <= len(records) <= 16:
                return self._finish('INCONCLUSIVE','linked_material_history_missing')
            valid = [r for r in records if isinstance(r,dict) and type(r.get('spool_id')) is int
                and r['spool_id']>0 and number(r.get('used_mm')) and r['used_mm']>=0
                and isinstance(r.get('material'),str) and len(r['material'])<=32
                and isinstance(r.get('source'),str) and len(r['source'])<=48]
            if len(valid)!=len(records):
                return self._finish('INCONCLUSIVE','linked_material_history_invalid')
            return self._finish('OBSERVED','declared_linked_usage_not_measured_wear',
                (('spool_records',len(valid)),('recorded_used_mm',sum(r['used_mm'] for r in valid))))
        if f=='E15':
            humidity = values.get(self._profile.get('chamber_sensor'),{}).get('humidity')
            if not number(humidity) or not 0 <= humidity <= 100:
                return self._finish('INCONCLUSIVE','chamber_humidity_missing')
            return self._finish('OBSERVED','chamber_humidity_not_filament_moisture',
                                (('relative_humidity_pct',humidity),))
        if f=='E14':
            p = self._dryer()
            if values.get(p['object'],{}).get('target')!=0:
                return self._shutdown('dryer_off_unverified')
            self._remaining -= self._segment
            if self._remaining>0:
                self._schedule('next_segment',True)
                return None
            return self._finish('OBSERVED','declared_drying_program_completed_not_moisture_measurement',
                (('duration_s',p['duration_s']),('target_c',p['target']),('heater_off',True)))

    def poll(self):
        if self.phase=='analysis':
            from time import monotonic
            if not self._current() or monotonic()>=self._deadline:
                return self._finish('INCONCLUSIVE','width_history_capture_unconfirmed')
            if not self._future.done():
                return None
            try:
                self._evidence = self._future.result()
                self._phase = 'workflow'
                return None
            except Exception:
                return self._finish('INCONCLUSIVE','width_history_unavailable')
        return super().poll()

    def choose(self,selected):
        if self.phase!='workflow' or type(selected) is not int or not 0 <= selected < len(self.workflow_choices):
            return False,'filament_choice_invalid'
        action = self.workflow_choices[selected][1]
        if action=='measure':
            self._phase = 'measurement_edit'
            return True,'enter_external_measurement'
        if action.startswith('sensor:'):
            self._sensor = action.split(':',1)[1]
            self._stage = 0
            return True,'prepare_sensor_fragment'
        return super().choose(selected)

    def adjust_measurement(self,delta):
        if self.phase=='measurement_edit' and number(delta):
            self._measurement = round(max(50. if self.feature_id=='E09' else .01,min(25000. if self.feature_id=='E09' else 10000.,self.measurement_value+delta)),2)
        return self.measurement_value

    def record_measurement(self,value):
        if self.phase!='measurement_edit' or not number(value) or not (50. if self.feature_id=='E09' else .01) <= value <= (25000. if self.feature_id=='E09' else 10000.):
            return False,'external_measurement_invalid'
        self._measurement,self._measured = float(value),True
        if self.feature_id=='E02':
            self._evidence += (('measured_mm',value),('error_mm',value-10.))
            self._phase = 'await_observation'
        else:
            self._phase = 'workflow'
        return True,'measurement_recorded'

    def _finish(self,status,reason,evidence=(),restored=False):
        if self.feature_id in ('E03','E04') and self._sensor_disabled:
            if not self._locked and not self._restoring and self._current():
                self._restore_outcome = (status,reason,evidence)
                self._restoring = True
                self._schedule('restore',True)
                return None
            self._locked = True
            reason += '_sensor_restore_unverified'
            restored = False
        return super()._finish(status,reason,evidence,restored)

    def observe(self,seen):
        if self.phase!='await_observation' or type(seen) is not bool:
            return None
        if self.feature_id=='E12' and not self._mechanical_seen:
            return self._finish('INCONCLUSIVE','no_mmu_mechanical_action_performed')
        if self.feature_id=='E02' and abs(self.measurement_value-10.)>.2:
            return self._finish('FAILED_USER','measured_extrusion_outside_0_2_mm')
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
                            'physical_filament_observation_not_automatic_flow_measurement')

    def cancel(self):
        if self.phase=='workflow' and self.feature_id in ('E03','E04') and self._sensor_restore is not None:
            self._restore_outcome = ('ABORTED','user_cancelled_sensor_test',())
            self._restoring = True
            self._schedule('restore',True)
            return None
        if self._owned_loadcell:
            self._schedule('abort',True)
            return None
        return super().cancel()
