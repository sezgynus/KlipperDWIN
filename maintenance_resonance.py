"""Sensor-specific resonance measurements and bounded local PSD comparisons.

Klipper owns acquisition/FFT. Petrel reads only its unique result CSVs, on the
shared read worker, and never substitutes commanded motion for sensor data.
"""
from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

from maintenance_discovery import AUTOMATIC, CALIBRATION
from maintenance_workflow import FirmwareWorkflow, safe_name
from maintenance_motion import number, vector

METHODS = {f:AUTOMATIC for f in ('R01','R02','R03','R05','R06')}
METHODS['R04'] = CALIBRATION
_FLOAT = r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)'


def profile_path():
    return Path.home()/'.config'/'Petrel'/'maintenance-resonance.json'


def records_path():
    return Path.home()/'.config'/'Petrel'/'maintenance-resonance-baselines.json'


def read_profile():
    try:
        path = profile_path()
        if path.stat().st_size > 2048:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value,dict) or set(value) != {'version','mount_id','belt_test'}
                or type(value['version']) is not int or value['version'] != 1 or type(value['belt_test']) is not bool
                or not isinstance(value['mount_id'],str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',value['mount_id'])):
            return {}
        return value
    except (OSError,ValueError,TypeError):
        return {}


def read_baselines():
    try:
        path = records_path()
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value,dict) or value.get('version') != 1
                or not isinstance(value.get('records'),dict)
                or len(value['records']) > 32):
            return {}
        records = value['records']
        for key,item in records.items():
            if (not re.fullmatch(r'[a-f0-9]{64}',key) or not isinstance(item,dict)
                    or not number(item.get('peak_hz')) or not 0 < item['peak_hz'] <= 450
                    or not isinstance(item.get('bins'),list) or not 4 <= len(item['bins']) <= 128
                    or any(not isinstance(p,list) or len(p)!=2 or not all(number(x) and x>=0 for x in p) for p in item['bins'])):
                return {}
        return records
    except (OSError,ValueError,TypeError):
        return {}


def resonance_services(state):
    profile = read_profile()
    if not profile:
        return ()
    services = []
    if read_baselines():
        services.append('maintenance.resonance_baseline')
    if (profile['belt_test'] and state.settings.get('printer',{}).get('kinematics')
            in ('corexy','corexz')):
        services.append('maintenance.belt_resonance_profile')
    return tuple(services)


def read_spectrum(path, token):
    """Reject remote/unrelated files, symlinks, malformed or oversized PSDs."""
    target = Path(path)
    if (target.parent != Path('/tmp') or target.is_symlink()
            or not re.fullmatch(r'(?:resonances|calibration_data)_[a-z0-9_=.,-]+_'+re.escape(token)+r'\.csv',target.name)
            or target.stat().st_size > 2*1024*1024):
        raise ValueError('resonance_csv_untrusted')
    points = []
    previous = -1.
    with target.open(encoding='utf-8',newline='') as stream:
        rows = csv.reader(stream)
        header = next(rows)
        if not header or header[0] != 'freq':
            raise ValueError('resonance_csv_header')
        # Older Klipper writes psd_xyz; newer multi-chip datasets use the
        # selected chip's total PSD in one column.
        index = header.index('psd_xyz') if 'psd_xyz' in header else 1
        for count,row in enumerate(rows):
            if count >= 8192 or len(row) <= index:
                raise ValueError('resonance_csv_bounds')
            freq,power = float(row[0]),float(row[index])
            if not (math.isfinite(freq) and math.isfinite(power)
                    and previous < freq <= 450 and power >= 0):
                raise ValueError('resonance_csv_invalid')
            previous = freq
            if freq >= 5:
                points.append((freq,power))
    if len(points)<4 or max(p for f,p in points)<=0:
        raise ValueError('resonance_spectrum_empty')
    peak = max(points,key=lambda item:item[1])[0]
    stride = max(1,math.ceil(len(points)/128))
    bins = tuple(points[::stride])
    return {'peak_hz':peak,'bins':bins}


def comparison(reference, current):
    a,b = reference['bins'],current['bins']
    if len(a)!=len(b) or any(abs(x[0]-y[0])>.051 for x,y in zip(a,b)):
        raise ValueError('resonance_frequency_grid_changed')
    norm_a = math.sqrt(sum(p*p for f,p in a))
    norm_b = math.sqrt(sum(p*p for f,p in b))
    if not norm_a or not norm_b:
        raise ValueError('resonance_zero_spectrum')
    cosine = sum(x[1]*y[1] for x,y in zip(a,b))/(norm_a*norm_b)
    return (('peak_shift_hz',round(current['peak_hz']-reference['peak_hz'],3)),
            ('spectral_similarity',round(max(0.,min(1.,cosine)),5)))


class MaintenanceResonanceController(FirmwareWorkflow):
    methods,domain = METHODS,'resonance'

    def __init__(self,*args):
        super().__init__(*args)
        self._axis = None
        self._token = ''
        self._profile = {}
        self._spectra = []
        self._axis_choice = False

    @property
    def moving(self):
        return self.feature_id not in ('R01','R03')

    @property
    def live_text(self):
        if self.feature_id == 'R05':
            return ('Same sensor mount required',self._profile.get('mount_id','No declared mount'))
        if self.feature_id == 'R06':
            return ('Clear diagonal travel paths','Frequency ratio is NOT force')
        return (self._row.device or 'Assigned sensor','Clear configured test points')

    @property
    def observation_prompt(self):
        if self.feature_id == 'R02':
            return 'Klipper PSD recorded?'
        return super().observation_prompt

    @property
    def workflow_choices(self):
        if self._axis_choice:
            return tuple(('Measure '+axis.upper(),'axis_'+axis)
                         for i,axis in enumerate('xyz') if self._row.axes & (1<<i))
        if self.feature_id == 'R06' and len(self._spectra)==1:
            return (('Measure second belt direction','second_belt'),)
        if self.feature_id == 'R02' and self._profile:
            return (('Finish Klipper PSD','finish'),('Save mount baseline / finish','baseline'))
        return ((('Finish Klipper PSD' if self.feature_id == 'R02' else 'Finish measured result'),'finish'),)

    def available(self):
        rows = []
        snapshot = self._printer.maintenance.snapshot
        devices = getattr(snapshot,'devices',())
        for row in super().available():
            if row.feature_id in ('R05','R06'):
                rows.extend(replace(row,device=d.name,axes=d.axes)
                            for d in devices if d.family=='accelerometer' and d.axes)
            elif row.device is not None:
                rows.append(row)
        return tuple(rows)

    def start(self,feature_id,device=None,**kwargs):
        self._profile,self._spectra = read_profile(),[]
        self._axis,self._axis_choice = None,False
        self._resolved_device = None
        self._token = 'petrelr_'+uuid.uuid4().hex
        row = next((r for r in self.available()
                    if r.feature_id==feature_id and r.device==device),None)
        if row is not None and row.axes:
            axes = [a for i,a in enumerate('xyz') if row.axes & (1<<i)]
            self._axis = axes[0]
            self._axis_choice = len(axes)>1 and feature_id in ('R02','R04','R05')
        # Resolve the axis before a worker can run, even for synchronous
        # test workers. Axis questions never enqueue a discarded read.
        return super().start(feature_id,device,**kwargs)

    def _schedule(self,action,dispatch):
        if action=='start' and self._axis_choice and not dispatch:
            self._action,self._phase,self._future = action,'workflow',None
            return True,'choose_assigned_measurement_axis'
        return super()._schedule(action,dispatch)

    def fields(self):
        fields = super().fields()
        if 'input_shaper' in self._printer.state.objects:
            fields['input_shaper'] = ''
        return fields

    def _chip(self):
        device = self._row.device
        if not isinstance(device,str) or len(device.split()) not in (1,2):
            raise ValueError('accelerometer_instance_required')
        return ' '.join(safe_name(s) for s in device.split())

    def validate(self,values,action):
        super().validate(values,action)
        if self.feature_id in ('R02','R04','R05','R06'):
            if self.feature_id in ('R05','R06') and not self._profile:
                raise ValueError('declare_resonance_mount')
            if self.feature_id in ('R05','R06') and self._row.device is None:
                # Global trend/comparison resolves to exactly one assigned
                # sensor; ambiguity is never silently resolved.
                devices = [d for d in self._printer.maintenance.snapshot.devices
                           if d.family=='accelerometer' and d.axes]
                if len(devices)!=1:
                    raise ValueError('resonance_sensor_selection_ambiguous')
                self._resolved_device = devices[0].name
            if self.feature_id in ('R02','R05','R06'):
                if urlsplit(getattr(self._client,'url','')).hostname not in ('localhost','127.0.0.1','::1'):
                    raise ValueError('local_klipper_result_access_required')
            if self.feature_id == 'R06':
                kin = self._printer.state.settings.get('printer',{}).get('kinematics')
                if not self._profile.get('belt_test') or kin not in ('corexy','corexz'):
                    raise ValueError('belt_geometry_profile_required')
            if self.feature_id=='R05' and self._key() not in read_baselines():
                raise ValueError('compatible_resonance_baseline_missing')
            cfg = self._printer.state.settings.get('resonance_tester',{})
            points = cfg.get('probe_points')
            if isinstance(points,str):
                points = [line.split(',') for line in points.strip().splitlines()]
            if not isinstance(points,(tuple,list)) or not 1 <= len(points) <= 8:
                raise ValueError('resonance_test_points_invalid')
            low,high = vector(values['toolhead']['axis_minimum']),vector(values['toolhead']['axis_maximum'])
            for point in points:
                xyz = tuple(float(x) for x in point)
                if len(xyz)!=3 or any(not math.isfinite(x) or not low[i]+5 <= x <= high[i]-5 for i,x in enumerate(xyz)):
                    raise ValueError('resonance_test_point_clearance')

    def _device(self):
        return self._row.device or getattr(self,'_resolved_device',None)

    def _key(self):
        settings = self._printer.state.settings
        version = getattr(self._printer.state,'software_version','unknown')
        if version == 'unknown':
            raise ValueError('baseline_firmware_identity_unknown')
        payload = (self._device(),self._axis,self._profile.get('mount_id'),settings,version)
        return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()

    def script(self,action,values):
        f = self.feature_id
        if f == 'R01':
            return 'ACCELEROMETER_QUERY CHIP='+safe_name(self._chip().split()[-1])
        if f == 'R03':
            return 'MEASURE_AXES_NOISE MEAS_TIME=2'
        if f in ('R02','R04','R05','R06'):
            if f in ('R05','R06') and self._axis is None:
                devices = [d for d in self._printer.maintenance.snapshot.devices
                           if d.name==self._device()]
                self._axis = next((a for i,a in enumerate('xyz')
                                   if devices and devices[0].axes & (1<<i)),None)
            if self._axis is None:
                raise ValueError('resonance_axis_unassigned')
            chip = self._device()
            if not isinstance(chip,str):
                raise ValueError('resonance_chip_unassigned')
            chip = ' '.join(safe_name(s) for s in chip.split())
            axis = self._axis.upper()
            if f == 'R06':
                plane = self._printer.state.settings['printer']['kinematics']
                axis = ('1,1,0' if plane=='corexy' else '1,0,1') if not self._spectra else (
                       '1,-1,0' if plane=='corexy' else '1,0,-1')
            command = 'SHAPER_CALIBRATE' if f=='R04' else 'TEST_RESONANCES'
            return command+' AXIS='+axis+' CHIPS="'+chip+'" NAME='+self._token+(
                       '' if f=='R04' else ' OUTPUT=resonances')
        raise ValueError('resonance_action_invalid')

    def _parse(self,values,lines):
        text = '\n'.join(lines)
        if self.feature_id == 'R01':
            match = re.search(r'accelerometer values \(x, y, z\): '+_FLOAT+r', '+_FLOAT+r', '+_FLOAT,text)
            if not match:
                raise ValueError('accelerometer_sample_missing')
            sample = tuple(map(float,match.groups()))
            if not all(math.isfinite(v) for v in sample):
                raise ValueError('accelerometer_sample_invalid')
            return tuple(zip(('x_mm_s2','y_mm_s2','z_mm_s2'),sample))
        if self.feature_id == 'R03':
            matches = re.findall(r'Axes noise for ([xyz]+)-axis accelerometer: '+_FLOAT+
                                 r' \(x\), '+_FLOAT+r' \(y\), '+_FLOAT+r' \(z\)',text)
            wanted = {a for i,a in enumerate('xyz') if self._row.axes & (1<<i)}
            evidence = []
            for axes,*nums in matches:
                if set(axes)&wanted:
                    for coordinate,value in zip('xyz',map(float,nums)):
                        if not math.isfinite(value) or value<0:
                            raise ValueError('accelerometer_noise_invalid')
                        evidence.append((axes+'.'+coordinate+'_psd',value))
            if not evidence:
                raise ValueError('assigned_sensor_noise_missing')
            return tuple(evidence)
        if self.feature_id == 'R04':
            axis = self._axis
            match = re.search(r'Recommended shaper_type_'+axis+r' = ([a-z0-9_]+), shaper_freq_'+axis+r' = '+_FLOAT+r' Hz',text)
            pending = values.get('configfile',{}).get('save_config_pending_items',{}).get('input_shaper',{})
            if not match or not 0 < float(match[2]) <= 300:
                raise ValueError('shaper_recommendation_missing')
            if (str(pending.get('shaper_type_'+axis))!=match[1]
                    or abs(float(pending.get('shaper_freq_'+axis,0))-float(match[2]))>.051):
                raise ValueError('shaper_pending_result_missing')
            return (('axis',axis),('shaper',match[1]),('frequency_hz',float(match[2])),('saved',False))
        matches = re.findall(r'Resonances data written to (\S+) file',text)
        if len(matches)!=1:
            raise ValueError('resonance_csv_result_missing')
        result = read_spectrum(matches[0],self._token)
        if self.feature_id == 'R05':
            reference = read_baselines().get(self._key())
            if reference is None:
                raise ValueError('compatible_resonance_baseline_missing')
            result['comparison'] = comparison(reference,result)
        return result

    def completed(self,values,lines):
        self._future = self._worker.submit(lambda:self._parse(values,lines),queue_timeout=6)
        from time import monotonic
        self._phase,self._deadline = 'analysis',monotonic()+12
        return None

    def poll(self):
        if self.phase == 'saving_baseline':
            from time import monotonic
            if not self._current() or monotonic() >= self._deadline:
                return self._finish('INCONCLUSIVE','baseline_save_unconfirmed')
            if not self._future.done():
                return None
            try:
                self._future.result()
                self._phase = 'await_observation'
                self._evidence += (('baseline_saved',True),)
                return None
            except Exception:
                return self._finish('INCONCLUSIVE','baseline_save_failed')
        if self.phase != 'analysis':
            return super().poll()
        from time import monotonic
        if not self._current() or monotonic() >= self._deadline:
            self._future.cancel()
            return self._finish('INCONCLUSIVE','resonance_analysis_stale')
        if not self._future.done():
            return None
        try:
            result = self._future.result()
            if self.feature_id in ('R01','R03'):
                return self._finish('PASSED','measured_firmware_evidence_no_auto_save',result)
            if self.feature_id == 'R04':
                # Klipper has already selected and staged the shaper parameters.
                # Only display its verified recommendation; Petrel does not
                # score vibrations or choose an alternative input shaper.
                return self._finish('OBSERVED','klipper_shaper_recommendation_not_saved',result)
            self._spectra.append(result)
            self._evidence = (('axis',self._axis),('peak_hz',result['peak_hz']))
            if self.feature_id == 'R02':
                # The internal PSD peak remains available to an explicitly
                # selected R05 trend baseline. It is not a shaper recommendation.
                self._evidence = (('axis',self._axis.upper()),
                                  ('data','Klipper PSD recorded'),
                                  ('next','Run R04 for Klipper fit'))
            if self.feature_id == 'R05':
                self._evidence += result['comparison']
            if self.feature_id == 'R06' and len(self._spectra)==2:
                a,b = self._spectra
                self._evidence = (('belt_a_peak_hz',a['peak_hz']),('belt_b_peak_hz',b['peak_hz']),
                    ('frequency_ratio',round(a['peak_hz']/b['peak_hz'],5)))
            self._phase = 'workflow'
            return None
        except Exception:
            return self._finish('INCONCLUSIVE','resonance_numeric_evidence_unavailable')

    def choose(self,selected):
        if self.phase != 'workflow' or type(selected) is not int or not 0 <= selected < len(self.workflow_choices):
            return False,'resonance_choice_invalid'
        action = self.workflow_choices[selected][1]
        if action.startswith('axis_'):
            self._axis = action[-1]
            self._axis_choice = False
            return self._schedule('start',False)
        if action == 'second_belt':
            return self._schedule(action,True)
        if action == 'baseline':
            # Bounded atomic persistence is performed on the existing worker.
            def save():
                records = read_baselines()
                if len(records)>=32 and self._key() not in records:
                    raise ValueError('resonance_baseline_capacity')
                records[self._key()] = self._spectra[-1]
                target = records_path()
                target.parent.mkdir(parents=True,exist_ok=True)
                temp = target.with_suffix('.tmp')
                temp.write_text(json.dumps({'version':1,'records':records}),encoding='utf-8')
                temp.replace(target)
                return True
            self._future = self._worker.submit(save,queue_timeout=4)
            from time import monotonic
            self._phase,self._deadline = 'saving_baseline',monotonic()+8
            return True,'saving_baseline'
        if action == 'finish':
            self._phase = 'await_observation'
            return True,'show_measurement'
        return False,'resonance_choice_invalid'

    def observe(self,seen):
        if self.phase != 'await_observation' or type(seen) is not bool:
            return None
        return self._finish('PASSED' if seen else 'INCONCLUSIVE',
            ('klipper_resonance_psd_recorded_no_petrel_rating'
             if self.feature_id == 'R02' else
             'measured_comparison_not_fault_or_belt_tension'))
