"""Declared benign buttons, safe servo ranges and user-performed servicing."""
from collections.abc import Mapping
from concurrent.futures import Future
import json
import math
from pathlib import Path
import re
import textwrap
from maintenance_discovery import USER
from maintenance_motion import number
from maintenance_workflow import FirmwareWorkflow,safe_name

METHODS = {'O01':USER,'O02':USER,'O06':USER}


def profile():
    try:
        path = Path.home()/'.config'/'Petrel'/'maintenance-auxiliary.json'
        if path.stat().st_size>8192:
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data,dict) or type(data.get('version')) is not int
                or data['version']!=1 or set(data)-{'version','buttons','servos','ambient_sensor','tasks'}):
            return {}
        return data
    except (OSError,ValueError,TypeError):
        return {}


def benign_button(state,name):
    if name not in state.objects or not name.startswith('gcode_button '):
        return False
    cfg = state.settings.get(name,{})
    if not isinstance(cfg,Mapping):
        return False
    for key in ('press_gcode','release_gcode'):
        script = cfg.get(key,'')
        if not isinstance(script,str) or len(script)>512 or '{' in script or '}' in script:
            return False
        # Only empty/message-only actions are registered. A safety declaration
        # never authorizes arbitrary macro execution during a manual press.
        if any(line.strip() and not line.strip().upper().startswith('M117 ')
               for line in script.splitlines()):
            return False
    return True


def servo_profile(state,item):
    if not isinstance(item,dict) or set(item)!={'object','minimum_angle','maximum_angle','angles'}:
        raise ValueError('servo_profile_invalid')
    name = item['object']
    if not isinstance(name,str) or name not in state.objects or not name.startswith('servo '):
        raise ValueError('servo_object_unverified')
    safe_name(name.split(' ',1)[1])
    cfg = state.settings.get(name,{})
    low,high = item['minimum_angle'],item['maximum_angle']
    angles = item['angles']
    maximum = cfg.get('maximum_servo_angle',180.)
    widths = cfg.get('minimum_pulse_width',.001),cfg.get('maximum_pulse_width',.002)
    if (not all(number(v) for v in (low,high,maximum,*widths))
            or not 0 <= low < high <= maximum or not 0 < widths[0] < widths[1] < .02
            or not isinstance(angles,list) or not 2 <= len(angles) <= 5
            or not all(number(a) and low <= a <= high for a in angles)):
        raise ValueError('servo_safe_range_invalid')
    return name,low,high,tuple(angles),maximum,widths


def tasks(data):
    items = data.get('tasks',[])
    if not isinstance(items,list) or len(items)>8:
        return ()
    seen = set()
    for item in items:
        if (not isinstance(item,dict) or set(item)!={'id','label','steps'}
                or not isinstance(item['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',item['id'])
                or item['id'] in seen or not isinstance(item['label'],str) or not 1<=len(item['label'])<=48
                or not isinstance(item['steps'],list) or not 1<=len(item['steps'])<=12
                or any(not isinstance(v,str) or not 1<=len(v)<=160 or any(ord(c)<32 for c in v) for v in item['steps'])):
            return ()
        seen.add(item['id'])
    return tuple(items)


def auxiliary_services(state):
    data = profile()
    services = []
    buttons = data.get('buttons',[])
    if isinstance(buttons,list) and len(buttons)<=8 and len(set(str(n) for n in buttons))==len(buttons):
        for name in buttons:
            if isinstance(name,str) and benign_button(state,name):
                services.append('maintenance.safe_button:'+name)
    servos = data.get('servos',[])
    if isinstance(servos,list) and len(servos)<=8:
        seen = set()
        for item in servos:
            try:
                name,*rest = servo_profile(state,item)
                if name in seen:
                    return ()
                seen.add(name)
                services.append('maintenance.safe_servo:'+name)
            except (ValueError,TypeError):
                continue
    ambient = data.get('ambient_sensor')
    if isinstance(ambient,str) and ambient in state.objects and ambient.startswith('temperature_sensor '):
        services.append('maintenance.ambient_sensor')
    if tasks(data):
        services.append('maintenance.guided_service')
    return tuple(services)


class MaintenanceAuxiliaryController(FirmwareWorkflow):
    methods,domain = METHODS,'auxiliary'

    def __init__(self,*args):
        super().__init__(*args)
        self._profile = {}
        self._index = 0
        self._original = None
        self._expected = None
        self._restored = False
        self._restoring = False
        self._outcome = None
        self._task = None

    @property
    def moving(self):
        return self.feature_id=='O02'

    @property
    def live_text(self):
        if self.feature_id=='O01':
            return (('Release button','Hold button pressed','Release button')[min(self._index,2)],
                    'Only benign button actions')
        if self.feature_id=='O02':
            return ('Clear entire servo path','Only declared safe angles')
        if self._task is not None:
            return tuple(textwrap.wrap(self._task['steps'][self._index],26))
        return ('Cold heaters / motors OFF','User-performed maintenance')

    @property
    def workflow_choices(self):
        if self.feature_id=='O01':
            return ((self.live_text[0]+' / read','sample'),)
        if self.feature_id=='O02':
            return (('Angle seen / next','next'),)
        if self._task is None:
            return tuple((t['label'][:26],'task:'+t['id']) for t in tasks(self._profile))
        return (('Step physically done / next','step_done'),)

    def start(self,*args,**kwargs):
        self._profile = profile()
        self._index,self._original,self._expected = 0,None,None
        self._restored,self._restoring,self._outcome,self._task = False,False,None,None
        return super().start(*args,**kwargs)

    def fields(self):
        result = super().fields()
        if self._row.device in self._printer.state.objects:
            result[self._row.device] = ''
        if self.feature_id=='O06':
            result['stepper_enable'] = 'steppers'
        return result

    def _servo(self):
        matches = [p for p in self._profile.get('servos',[])
                   if isinstance(p,dict) and p.get('object')==self._row.device]
        if len(matches)!=1:
            raise ValueError('servo_role_unavailable')
        return servo_profile(self._printer.state,matches[0])

    def validate(self,values,action):
        super().validate(values,action)
        if self.feature_id=='O01':
            if not benign_button(self._printer.state,self._row.device):
                raise ValueError('button_action_not_benign')
        if self.feature_id=='O02':
            name,low,high,angles,maximum,widths = self._servo()
            value = values.get(name,{}).get('value')
            if not number(value) or value<=0:
                raise ValueError('servo_initial_position_unknown')
            angle = (value*.02-widths[0])/(widths[1]-widths[0])*maximum
            if not low-.01 <= angle <= high+.01:
                raise ValueError('servo_initial_position_outside_safe_range')
            if self._sent and self._expected is not None and abs(value-self._expected)>.00001:
                raise ValueError('servo_changed_externally')
            if not self._sent:
                self._original = value
        if self.feature_id=='O06':
            motors = values.get('stepper_enable',{}).get('steppers')
            if not isinstance(motors,Mapping) or not motors or any(v is not False for v in motors.values()):
                raise ValueError('disable_motors_before_physical_servicing')
            if not tasks(self._profile):
                raise ValueError('declared_service_tasks_missing')

    def script(self,action,values):
        if self.feature_id=='O01':
            return 'QUERY_BUTTON BUTTON='+safe_name(self._row.device.split(' ',1)[1])
        if self.feature_id=='O06':
            return 'STATUS'  # Local-only dispatch below; never sent as G-code.
        if self.feature_id=='O02':
            name,low,high,angles,maximum,widths = self._servo()
            if action=='restore':
                self._expected = self._original
                setting = 'WIDTH=%.9f'%(self._original*.02)
            else:
                angle = angles[self._index]
                self._expected = (widths[0]+angle/maximum*(widths[1]-widths[0]))/.02
                setting = 'ANGLE=%.6f'%angle
            return 'SET_SERVO SERVO='+safe_name(name.split(' ',1)[1])+' '+setting+'\nG4 P500\nM400'
        raise ValueError('auxiliary_workflow_unavailable')

    def dispatch(self,script,guard):
        if self.feature_id in ('O01','O06'):
            # Button state comes from the subsequent fresh object query.
            if not guard():
                raise ValueError('auxiliary_read_guard_denied')
            result = Future()
            result.set_result(True)
            return result
        return self._printer.subscription.request('printer.gcode.script',{'script':script},
                                                  guard=guard,request_timeout=15.)

    def completed(self,values,lines):
        self._values = values
        if self.feature_id=='O01':
            value = values.get(self._row.device,{}).get('state')
            if value not in ('RELEASED','PRESSED'):
                return self._finish('INCONCLUSIVE','button_state_unavailable')
            if value==('RELEASED','PRESSED','RELEASED')[self._index]:
                self._index += 1
            if self._index==3:
                return self._finish('PASSED','button_released_pressed_released',
                    (('transitions','released > pressed > released'),),True)
            self._phase = 'workflow'
            return None
        if self.feature_id=='O02':
            actual = values.get(self._row.device,{}).get('value')
            if not number(actual) or abs(actual-self._expected)>.00001:
                return self._finish('INCONCLUSIVE','servo_pwm_readback_unverified')
            if self._action=='restore':
                self._restored = True
                if self._outcome is not None:
                    status,reason,evidence = self._outcome
                    return super()._finish(status,reason+'_servo_pwm_restored',evidence,True)
                self._evidence = (('declared_angles',len(self._servo()[3])),('pwm_restore_verified',True))
                self._phase = 'await_observation'
            else:
                self._phase = 'workflow'
            return None
        self._phase = 'workflow'
        return None

    def choose(self,selected):
        if self.phase!='workflow' or type(selected) is not int or not 0 <= selected < len(self.workflow_choices):
            return False,'auxiliary_choice_invalid'
        action = self.workflow_choices[selected][1]
        if action.startswith('task:'):
            self._task = next(t for t in tasks(self._profile) if t['id']==action.split(':',1)[1])
            self._index = 0
            return True,'perform_service_step'
        if action=='step_done':
            self._index += 1
            if self._index==len(self._task['steps']):
                self._phase = 'await_observation'
                self._evidence = (('task',self._task['id']),('acknowledged_steps',self._index))
            return True,'service_step_acknowledged'
        if action=='next':
            self._index += 1
            if self._index==len(self._servo()[3]):
                return self._schedule('restore',True)
        return super().choose(selected) if action!='next' else self._schedule('next',True)

    def _finish(self,status,reason,evidence=(),restored=False):
        if self.feature_id=='O02' and self._sent and not self._restored:
            if not self._restoring and not self._locked and self._current():
                self._outcome,self._restoring = (status,reason,evidence),True
                self._schedule('restore',True)
                return None
            self._locked = True
            reason += '_servo_restore_unverified'
        return super()._finish(status,reason,evidence,restored)

    def observe(self,seen):
        if self.phase!='await_observation' or type(seen) is not bool:
            return None
        if self.feature_id=='O06':
            return self._finish('OBSERVED_USER' if seen else 'INCONCLUSIVE',
                'user_performed_service_not_sensor_health')
        return self._finish('PASSED_USER' if seen else 'FAILED_USER',
            'coarse_servo_observation_not_position_metrology',restored=self._restored)

    def cancel(self):
        if self.feature_id=='O02' and self.phase in ('workflow','await_confirmation') and self._sent:
            self._outcome,self._restoring = ('ABORTED','user_cancelled_servo',()),True
            self._schedule('restore',True)
            return None
        return super().cancel()
