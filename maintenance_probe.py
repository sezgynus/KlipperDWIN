"""Probe diagnostics and firmware calibrations, excluding Leveling duplicates."""
from collections.abc import Mapping
import math
import re

from maintenance_discovery import AUTOMATIC, USER, EXTERNAL, CALIBRATION
from maintenance_workflow import FirmwareWorkflow, safe_name
from maintenance_motion import number, vector

# Probe offset, all bed-mesh items and screws-tilt belong to Leveling.
LEVELING_ONLY = frozenset(('P05','P07','P08','P09','P10','P11'))
METHODS = {**{f:AUTOMATIC for f in ('P01','P02','P03','P04','P20')},
           **{f:CALIBRATION for f in ('P06','P12','P13','P14','P15','P16','P17','P18','P22')},
           'P19':USER, 'P21':EXTERNAL}
_FLOAT = r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)'


def probe_measurement(feature, lines):
    """Strictly recognize firmware's documented numerical result, never RPC ok."""
    text = '\n'.join(lines)
    if feature == 'P03':
        match = re.search(r'probe accuracy results: maximum '+_FLOAT+
            r', minimum '+_FLOAT+r', range '+_FLOAT+r', average '+_FLOAT+
            r', median '+_FLOAT+r', standard deviation '+_FLOAT, text)
        if match:
            values = tuple(map(float, match.groups()))
            hi, low, span, avg, median, std = values
            if (all(math.isfinite(v) for v in values) and low <= avg <= hi
                    and low <= median <= hi and span >= 0 and std >= 0
                    and abs((hi-low)-span) <= .00002):
                return tuple(zip(('maximum_mm','minimum_mm','range_mm',
                                  'average_mm','median_mm','stddev_mm'),values))
    if feature == 'P04':
        match = re.search(r'(?:probe at |Result: at )'+_FLOAT+r','+_FLOAT+r'(?: is z=| estimate contact at z=)'+_FLOAT, text)
        if match:
            values = tuple(map(float,match.groups()))
            if all(math.isfinite(v) for v in values):
                return tuple(zip(('x_mm','y_mm','z_mm'),values))
    return ()


class MaintenanceProbeController(FirmwareWorkflow):
    methods, domain = METHODS, 'probe'

    def __init__(self, *args):
        super().__init__(*args)
        self._stage = 0
        self._dimensions = [100.,100.,70.]
        self._dimension = None
        self._initial_force = None
        self._measured = set()

    @property
    def moving(self):
        return self.feature_id not in ('P01','P02','P20','P21')

    @property
    def live_text(self):
        if self.feature_id == 'P01':
            return (('Release probe','Hold probe triggered','Release probe')[min(self._stage,2)],
                    'Read only; no axis movement')
        if self.feature_id == 'P02':
            return ('Tap only after starting', 'One tap / 60 s active capture')
        if self.feature_id == 'P19':
            return ('Keep pin clear of bed', 'Deploy / observe / stow')
        if self.feature_id == 'P21':
            return ('Use measured skew print', 'AC / BD diagonals, AD side')
        if self.feature_id == 'P22':
            return ('No automatic heater command', 'Externally controlled warming')
        return ('Home XYZ / clear tool path', 'Pending config is NOT saved')

    @property
    def workflow_choices(self):
        if self.feature_id == 'P01':
            return ((self.live_text[0]+' / read','query'),)
        if self._owned_manual:
            return (('Z +1.00 mm','zup1'),('Z +0.10 mm','zup'),
                    ('Z +0.01 mm','zupfine'),('Z -0.01 mm','zdownfine'),
                    ('Z -0.10 mm','zdown'),('Accept this point','accept'))
        if self.feature_id == 'P12':
            return (('Screw unchanged / next','accept'),
                    ('Screw adjusted / next','adjusted'))
        if self.feature_id == 'P19':
            return (('Pin deployed: stow now','stow'),)
        if self.feature_id == 'P20':
            return (('Sample force again','sample'),('Finish force observation','finish'))
        if self.feature_id == 'P21':
            return tuple(('%s %.2f mm'%(k,v),'dimension'+str(i))
                         for i,(k,v) in enumerate(zip(('AC','BD','AD'),self._dimensions)))+(
                             ('Calculate measured skew','calculate'),)
        if self.feature_id == 'P22':
            return (('Next temperature sample','next'),('Complete drift calibration','complete'))
        return (('Observe firmware result','finish'),)

    @property
    def measurement_value(self):
        return self._dimensions[self._dimension] if self._dimension is not None else 0.

    def adjust_measurement(self, delta):
        if self.phase == 'measurement_edit' and number(delta):
            self._dimensions[self._dimension] = round(min(1000.,max(.01,self.measurement_value+delta)),2)
        return self.measurement_value

    def record_measurement(self, value):
        if self.phase != 'measurement_edit' or not number(value) or not .01 <= value <= 1000:
            return False, 'skew_measurement_invalid'
        self._dimensions[self._dimension] = float(value)
        self._measured.add(self._dimension)
        self._dimension = None
        self._phase = 'workflow'
        return True, 'skew_measurement_recorded'

    def choose(self, selected):
        if self.phase == 'workflow' and type(selected) is int:
            choices = self.workflow_choices
            if 0 <= selected < len(choices):
                action = choices[selected][1]
                if action.startswith('dimension'):
                    self._dimension = int(action[-1])
                    self._phase = 'measurement_edit'
                    return True, 'enter_external_mm'
        return super().choose(selected)

    def cancel(self):
        if self.phase == 'workflow' and self.feature_id == 'P19':
            self._cancel_after_stow = True
            self._schedule('stow', True)
            return None
        if self.phase == 'workflow' and self.feature_id in ('P12','P22'):
            self._schedule('abort', True)
            return None
        return super().cancel()

    def start(self, *args, **kwargs):
        self._cancel_after_stow = False
        self._stage, self._dimension, self._initial_force = 0, None, None
        self._measured = set()
        return super().start(*args, **kwargs)

    def fields(self):
        fields = super().fields()
        names = set(self._printer.state.objects)
        for name in ('probe','bltouch','bed_screws','z_tilt','quad_gantry_level',
                     'bed_tilt','axis_twist_compensation','load_cell_probe'):
            if name in names:
                fields[name] = ''
        for name in names:
            if name.startswith(('probe_eddy_current ','temperature_probe ')):
                fields[name] = ''
        return fields

    def _eddy(self, prefix):
        names = sorted(n for n in self._printer.state.objects if n.startswith(prefix+' '))
        if len(names) != 1:
            raise ValueError('select_unambiguous_eddy_sensor')
        return safe_name(names[0].split(' ',1)[1])

    def validate(self, values, action):
        super().validate(values,action)
        if self.feature_id in ('P03','P04'):
            th = values['toolhead']
            low, high = vector(th['axis_minimum']), vector(th['axis_maximum'])
            pos = vector(th['position'])
            cfg = self._printer.state.settings.get('probe',
                  self._printer.state.settings.get('bltouch',{}))
            xy = tuple(pos[i]+float(cfg.get(k,0)) for i,k in enumerate(('x_offset','y_offset')))
            if any(not math.isfinite(p) or not low[i]+1 <= p <= high[i]-1 for i,p in enumerate(xy)):
                raise ValueError('probe_point_outside_safe_limits')
            if pos[2] < max(5.,low[2]+1):
                raise ValueError('raise_z_before_probe_test')
        if self.feature_id == 'P19':
            th = values['toolhead']
            if vector(th['position'])[2] < 10:
                raise ValueError('raise_z_before_pin_deploy')
        if self.feature_id == 'P16' and self._printer.state.settings.get('printer',{}).get('kinematics') != 'delta':
            raise ValueError('delta_kinematics_required')
        if action.startswith('z'):
            if not self._owned_manual or values.get('manual_probe',{}).get('is_active') is not True:
                raise ValueError('owned_manual_probe_required')
            step = {'zup1':1.,'zup':.1,'zupfine':.01,'zdownfine':-.01,'zdown':-.1}[action]
            th = values['toolhead']
            pos, low, high = (vector(th[k]) for k in ('position','axis_minimum','axis_maximum'))
            if not low[2] <= pos[2]+step <= high[2]:
                raise ValueError('manual_z_step_outside_limits')

    def script(self, action, values):
        f = self.feature_id
        if action == 'abort':
            return 'ABORT'
        if action.startswith('z'):
            return 'TESTZ Z='+{'zup1':'1','zup':'.1','zupfine':'.01','zdownfine':'-.01','zdown':'-.1'}[action]
        if action in ('accept','adjusted'):
            return action.upper()
        if f == 'P01':
            return 'QUERY_PROBE'
        if f == 'P02':
            return 'LOAD_CELL_TEST_TAP TAPS=1 TIMEOUT=60'
        if f == 'P03':
            return 'PROBE_ACCURACY SAMPLES=10 SAMPLE_RETRACT_DIST=2'
        if f == 'P04':
            return 'PROBE'
        if f == 'P06':
            return 'Z_ENDSTOP_CALIBRATE'
        if f == 'P12':
            return 'BED_SCREWS_ADJUST'
        if f in ('P13','P14','P15','P16','P17'):
            return {'P13':'Z_TILT_ADJUST','P14':'QUAD_GANTRY_LEVEL',
                    'P15':'BED_TILT_CALIBRATE','P16':'DELTA_CALIBRATE',
                    'P17':'AXIS_TWIST_COMPENSATION_CALIBRATE'}[f]
        if f == 'P18':
            return 'PROBE_EDDY_CURRENT_CALIBRATE CHIP='+self._eddy('probe_eddy_current')
        if f == 'P19':
            return 'BLTOUCH_DEBUG COMMAND='+('pin_up' if action == 'stow' else 'pin_down')
        if f == 'P20':
            return 'LOAD_CELL_DIAGNOSTIC LOAD_CELL=load_cell_probe'
        if f == 'P21':
            if action == 'calculate':
                if self._measured != {0,1,2}:
                    raise ValueError('enter_all_three_external_measurements')
                ac,bd,ad = self._dimensions
                side2 = 2*ad*ad
                if not abs(ac*ac-bd*bd) < side2:
                    raise ValueError('skew_measurements_impossible')
                return 'CALC_MEASURED_SKEW AC=%.3f BD=%.3f AD=%.3f'%(ac,bd,ad)
            return 'GET_CURRENT_SKEW'
        if f == 'P22':
            return ({'next':'TEMPERATURE_PROBE_NEXT','complete':'TEMPERATURE_PROBE_COMPLETE'}.get(action)
                    or 'TEMPERATURE_PROBE_CALIBRATE PROBE='+self._eddy('temperature_probe'))
        raise ValueError('probe_workflow_unregistered')

    def completed(self, values, lines):
        self._values = values
        f = self.feature_id
        if self._action == 'abort':
            if values.get('manual_probe',{}).get('is_active') is True:
                return self._finish('INCONCLUSIVE','manual_abort_unconfirmed')
            return self._finish('ABORTED','owned_calibration_aborted_no_save')
        if f == 'P01':
            states = re.findall(r'probe:\s*(open|TRIGGERED)', '\n'.join(lines))
            expected = ('open','TRIGGERED','open')[self._stage]
            if not states or states[-1] != expected:
                self._phase = 'workflow'
                return None
            self._stage += 1
            if self._stage == 3:
                return self._finish('PASSED','probe_open_triggered_open',
                    (('transitions','open > TRIGGERED > open'),), True)
            self._phase = 'workflow'
            return None
        if f in ('P03','P04'):
            evidence = probe_measurement(f,lines)
            if not evidence:
                return self._finish('INCONCLUSIVE','probe_numeric_result_missing')
            return self._finish('PASSED','probe_measurement_not_absolute_accuracy',evidence)
        if f == 'P02':
            # A tap capture completing successfully proves the requested tap;
            # preserve firmware evidence, rather than interpreting plain RPC ok.
            if not any(re.search(r'Test complete, 1 taps detected',s) for s in lines):
                return self._finish('INCONCLUSIVE','tap_capture_evidence_missing')
            return self._finish('PASSED','firmware_tap_capture',(('requested_taps',1),))
        if f == 'P20':
            force = values.get('load_cell_probe',values.get('probe',{})).get('force_g')
            if not number(force):
                return self._finish('INCONCLUSIVE','calibrated_force_unavailable')
            if self._initial_force is None:
                self._initial_force = force
            self._evidence = (('force_g',force),('change_g',force-self._initial_force))
            self._phase = 'workflow'
            return None
        if f == 'P19':
            if self._action != 'stow':
                self._phase = 'workflow'
                return None
            if getattr(self,'_cancel_after_stow',False):
                return self._finish('ABORTED','pin_stow_completed_after_cancel')
            self._evidence = (('deploy_rpc',True),('stow_rpc',True))
            self._phase = 'await_observation'
            return None
        if f == 'P21':
            if self._action != 'calculate':
                self._phase = 'workflow'
                return None
            text = '\n'.join(lines)
            # Firmware reports the calculated angle, while actual lengths
            # remain the operator's external measurements.
            if not re.search(r'[Ss]kew.*(?:radians|degrees)',text):
                return self._finish('INCONCLUSIVE','skew_calculation_evidence_missing')
            self._evidence = tuple(zip(('AC_mm','BD_mm','AD_mm'),self._dimensions))
            self._phase = 'await_observation'
            return None
        active = values.get('manual_probe',{}).get('is_active')
        if active is True:
            self._owned_manual = True
            self._manual_position = values.get('manual_probe',{}).get('z_position')
            self._phase = 'workflow'
            return None
        self._owned_manual = False
        if f == 'P12':
            screw = values.get('bed_screws',{})
            if screw.get('is_active') is True:
                self._phase = 'workflow'
                return None
            if screw.get('is_active') is not False or not any('Bed screws tool completed successfully' in line for line in lines):
                return self._finish('INCONCLUSIVE','bed_screws_completion_missing')
        if f == 'P22' and self._action != 'complete':
            self._phase = 'workflow'
            return None
        config = values.get('configfile',{})
        pending = config.get('save_config_pending_items')
        if f in ('P06','P15','P16','P17','P18','P22'):
            sections = {'P06':'stepper_z','P15':'bed_tilt','P16':'delta_calibrate',
                        'P17':'axis_twist_compensation'}
            if f == 'P18':
                sections[f] = 'probe_eddy_current '+self._eddy('probe_eddy_current')
            if f == 'P22':
                sections[f] = 'temperature_probe '+self._eddy('temperature_probe')

            if not isinstance(pending,Mapping) or sections[f] not in pending:
                return self._finish('INCONCLUSIVE','calibration_pending_result_missing')
            self._evidence = (('pending_section',sections[f]),('saved',False))
        elif f in ('P13','P14'):
            section = 'z_tilt' if f == 'P13' else 'quad_gantry_level'
            if values.get(section,{}).get('applied') is not True:
                return self._finish('INCONCLUSIVE','gantry_adjustment_not_applied')
            self._evidence = (('applied',True),)
        else:
            self._evidence = (('firmware_guided_completed',True),('saved',False))
        self._phase = 'await_observation'
        return None
