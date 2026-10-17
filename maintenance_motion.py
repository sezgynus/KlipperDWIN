"""Pure bounded motion protocols. Commanded coordinates are not metrology."""
from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import re
from random import SystemRandom

_MOVE = ('M03', 'M04', 'M05', 'M06', 'M12')
_TOKEN = re.compile(r'_PETREL_M_[a-f0-9]{32}\Z')
_AXES = {'stepper_x': 0, 'stepper_y': 1, 'stepper_z': 2}


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def vector(v, count=3):
    if not isinstance(v, (tuple, list)) or len(v) < count or not all(number(x) for x in v[:count]):
        raise ValueError('motion_coordinates_unknown')
    return tuple(float(x) for x in v[:count])


def modal(status):
    v = status.get('gcode_move')
    if not isinstance(v, Mapping) or any(type(v.get(k)) is not bool for k in ('absolute_coordinates','absolute_extrude')):
        raise ValueError('gcode_modes_unknown')
    nums = tuple(v.get(k) for k in ('speed', 'speed_factor', 'extrude_factor'))
    if not all(number(x) and x > 0 for x in nums):
        raise ValueError('gcode_factors_unknown')
    return (v['absolute_coordinates'], v['absolute_extrude'], *nums,
            *vector(v.get('homing_origin'), 4))


def idle_heaters(settings, status):
    for name, cfg in settings.items():
        if isinstance(cfg, Mapping) and 'heater_pin' in cfg:
            v = status.get(name)
            if (not isinstance(v, Mapping) or not number(v.get('target')) or v['target'] != 0
                    or not number(v.get('power')) or v['power'] != 0
                    or not number(v.get('temperature')) or v['temperature'] > 45):
                raise ValueError('motion_requires_cold_idle_heaters')


def geometry(settings, status, homed=True, homing=False, allow_limit_positions=False):
    if not isinstance(settings, Mapping) or not isinstance(status, Mapping):
        raise ValueError('motion_evidence_unknown')
    printer = settings.get('printer', {})
    if printer.get('kinematics') not in ('cartesian', 'corexy'):
        raise ValueError('motion_kinematics_profile_required')
    for section in settings:
        if str(section).lower() in ('homing_override', 'gcode_macro g28',
                'gcode_macro g1', 'gcode_macro g0', 'gcode_macro g91',
                'gcode_macro m400', 'gcode_macro g4', 'gcode_macro m220',
                'gcode_macro save_gcode_state', 'gcode_macro restore_gcode_state',
                'gcode_macro stepper_buzz', 'gcode_macro endstop_phase_calibrate'):
            raise ValueError('motion_command_overridden')
    if any(k in settings for k in ('dual_carriage','generic_cartesian','skew_correction')):
        raise ValueError('motion_transform_profile_required')
    idle_heaters(settings, status)
    th = status.get('toolhead')
    gm = status.get('gcode_move')
    if not isinstance(th, Mapping) or not isinstance(gm, Mapping):
        raise ValueError('motion_status_missing')
    low, high = vector(th.get('axis_minimum')), vector(th.get('axis_maximum'))
    position = vector(gm.get('position'))
    if any(not lo < hi for lo, hi in zip(low, high)):
        raise ValueError('motion_limits_or_position_invalid')
    axes = th.get('homed_axes')
    if not isinstance(axes, str) or not set(axes) <= set('xyz'):
        raise ValueError('homing_state_unknown')
    if homed and not set('xyz') <= set(axes):
        raise ValueError('home_xyz_before_motion_test')
    # Before G28 an unhomed axis has no measured coordinate. Klipper may
    # report zero even when its configured minimum is positive. Validate all
    # limits, but apply current-position bounds only to known axes for G28.
    # Every ordinary motion/calibration path retains its position checks.
    if any((not homing or 'xyz'[axis] in axes) and not lo <= p <= hi
           for axis,(lo,hi,p) in enumerate(zip(low,high,position))):
        raise ValueError('motion_limits_or_position_invalid')
    velocity = th.get('max_velocity')
    if not number(velocity) or velocity <= 0:
        raise ValueError('motion_velocity_unknown')
    if homed:
        if not allow_limit_positions and any(not lo+2 <= p <= hi-2 for lo, hi, p in zip(low, high, position)):
            raise ValueError('move_away_from_axis_limits')
        if 'bed_mesh' in settings:
            mesh = status.get('bed_mesh')
            if not isinstance(mesh, Mapping) or mesh.get('profile_name') != '':
                raise ValueError('clear_mesh_before_motion_test')
            # Klipper's cleared status has zero bounds and mesh_matrix=[[]].
            # Both the small HTTP preflight and full frozen subscription
            # must apply the same contract. A flat numeric mesh is active.
            if (vector(mesh.get('mesh_min'),2)!=(0.,0.) or
                    vector(mesh.get('mesh_max'),2)!=(0.,0.)):
                raise ValueError('clear_mesh_before_motion_test')
            if 'mesh_matrix' in mesh:
                matrix=mesh['mesh_matrix']
                empty=(isinstance(matrix,(tuple,list)) and
                       (len(matrix)==0 or (len(matrix)==1 and
                        isinstance(matrix[0],(tuple,list)) and len(matrix[0])==0)))
                if not empty:
                    raise ValueError('clear_mesh_before_motion_test')
        enabled = status.get('stepper_enable', {}).get('steppers', {})
        if not isinstance(enabled, Mapping) or any(enabled.get('stepper_'+a) is not True for a in 'xyz'):
            raise ValueError('keep_xyz_motors_enabled')
    modal(status)
    return position, low, high, float(velocity)


@dataclass(frozen=True, slots=True)
class MotionProgram:
    feature_id: str
    device: str | None
    script: str
    original: tuple
    expected: tuple | None
    modes: tuple
    axis: int | None
    distance: float
    deadline_s: float
    returning: bool = False
    phase_count: int | None = None
    homing_runs: int = 0
    phase_endstop: float | None = None
    phase_step_tolerance: float = 0.


def _script(axis, distance, speed, token, roundtrip):
    if not _TOKEN.fullmatch(token):
        raise ValueError('motion_state_identifier_invalid')
    lines = ['SAVE_GCODE_STATE NAME='+token, 'G91', 'M220 S100',
             'G1 %s%.4f F%.3f' % (axis, distance, speed*60), 'M400']
    if roundtrip:
        lines += ['G4 P500', 'M400', 'G1 %s%.4f F%.3f' % (axis, -distance, speed*60), 'M400']
    lines += ['RESTORE_GCODE_STATE NAME='+token+' MOVE=0']
    return '\n'.join(lines)


def phase_pending_allowed(cfg, device):
    """A pending result for another stepper must not block this calibration."""
    if not isinstance(cfg, Mapping):
        return False
    if cfg.get('save_config_pending') is False:
        return True
    items = cfg.get('save_config_pending_items')
    return (cfg.get('save_config_pending') is True and
            isinstance(items, Mapping) and bool(items) and
            'endstop_phase '+device not in items)


def phase_endstop_window(settings, name):
    """Klipper can report up to one full motor step outside axis_minimum
    after homing-phase correction. Only trust configured physical endstops.
    """
    cfg=settings.get(name)
    if not isinstance(cfg, Mapping):
        return None
    pin=cfg.get('endstop_pin')
    endstop=cfg.get('position_endstop')
    distance=cfg.get('rotation_distance')
    steps=cfg.get('full_steps_per_rotation',200)
    if (not isinstance(pin,str) or not pin or 'virtual_endstop' in pin
            or not all(number(x) for x in (endstop,distance,steps))
            or distance<=0 or steps<=0):
        return None
    full_step=distance/steps
    if not number(full_step) or full_step<=0:
        return None
    return float(endstop),full_step+0.001


def compile_motion(row, state, status, token):
    feature, name = row.feature_id, row.device
    if feature not in _MOVE:
        raise ValueError('motion_feature_unavailable')
    settings = state.settings
    position, low, high, velocity = geometry(settings, status, homed=feature != 'M03',
                                             homing=feature == 'M03',
                                             allow_limit_positions=feature == 'M12')
    modes = modal(status)
    if feature == 'M03':
        if name is not None:
            raise ValueError('homing_target_invalid')
        if any(abs(x) > 1e-9 for x in modes[-4:-1]):
            raise ValueError('clear_xyz_offsets_before_homing_test')
        return MotionProgram(feature, None, 'G28\nM400', position, None, modes, None, 0., 180.)
    if feature == 'M12':
        if name not in _AXES or 'endstop_phase '+name not in settings:
            raise ValueError('phase_stepper_unverified')
        axis = _AXES[name]
        if settings['printer']['kinematics'] == 'corexy' and axis in (0, 1):
            raise ValueError('phase_stepper_not_supported_for_kinematics')
        pin = settings.get(name, {}).get('endstop_pin', '')
        if not isinstance(pin, str) or not pin or 'virtual_endstop' in pin:
            raise ValueError('phase_physical_endstop_required')
        if any(abs(v)>1e-9 for v in modes[-4:-1]):
            raise ValueError('clear_xyz_offsets_before_homing_test')
        if not phase_pending_allowed(status.get('configfile'), name):
            raise ValueError('existing_or_unknown_pending_config')
        home = status.get('endstop_phase', {}).get('last_home', {}).get(name, {})
        phase, count = home.get('phase'), home.get('phases')
        if type(phase) is not int or type(count) is not int or not 0<=phase<count<=4096:
            raise ValueError('home_axis_before_phase_calibration')
        if name[-1] not in status['toolhead']['homed_axes']:
            raise ValueError('axis_not_homed_for_phase')
        span = high[axis]-low[axis]
        margin = max(2., min(10., .08*span))
        low_target, high_target = low[axis]+margin, high[axis]-margin
        if high_target-low_target<10.:
            raise ValueError('insufficient_phase_calibration_travel')
        speed = min(40., velocity)
        if axis==2:
            speed = min(speed, settings['printer'].get('max_z_velocity', velocity))
        homing_speed = settings[name].get('homing_speed',5.)
        retract = settings[name].get('homing_retract_dist',5.)
        if (not number(speed) or speed<=0 or not number(homing_speed)
                or homing_speed<=0 or not number(retract) or retract<0):
            raise ValueError('phase_homing_speed_invalid')
        z_target = position[2]
        z_speed = None
        if axis in (0, 1) and position[2]<low[2]+5.:
            z_target = low[2]+5.
            z_speed = settings['printer'].get('max_z_velocity',velocity)
            if not number(z_speed) or z_speed<=0 or z_target>high[2]-2.:
                raise ValueError('raise_z_for_xy_clearance')
            z_speed = min(5.,z_speed,velocity)
        # This API has a maximum per-command timeout of 900 seconds.
        deadline = (45. + 10*(1.2*span/homing_speed + 2*retract/homing_speed
                               + span/speed + 8.)
                    + ((z_target-position[2])/z_speed if z_speed else 0.))
        if deadline>875.:
            raise ValueError('phase_calibration_duration_exceeds_transport_limit')
        rng = SystemRandom()
        width = (high_target-low_target)/10.
        targets = [low_target+(i+rng.uniform(.15,.85))*width
                   for i in range(10)]
        rng.shuffle(targets)
        lines = ['SAVE_GCODE_STATE NAME='+token, 'G90', 'M220 S100']
        if z_speed is not None:
            lines += ['G1 Z%.4f F%.3f' % (z_target,z_speed*60.), 'M400']
        letter='XYZ'[axis]
        for target in targets:
            lines += ['G1 %s%.4f F%.3f' % (letter,target,speed*60.),
                      'M400', 'G28 '+letter, 'M400']
        lines += ['ENDSTOP_PHASE_CALIBRATE STEPPER='+name,
                  'RESTORE_GCODE_STATE NAME='+token+' MOVE=0']
        expected=list(position)
        expected[2]=z_target
        window=phase_endstop_window(settings,name)
        return MotionProgram(feature,name,chr(10).join(lines),position,
                             tuple(expected),modes,axis,0.,deadline,
                             phase_count=count,homing_runs=10,
                             phase_endstop=window[0] if window else None,
                             phase_step_tolerance=window[1] if window else 0.)
    if name not in _AXES:
        raise ValueError('primary_axis_stepper_required')
    axis = _AXES[name]
    if axis in (0,1) and position[2] < low[2]+5:
        raise ValueError('raise_z_for_xy_clearance')
    if feature == 'M04':
        if settings['printer']['kinematics'] != 'cartesian':
            raise ValueError('individual_motor_kinematics_profile_required')
        if axis == 2 and any(str(k).startswith('stepper_z') and k != 'stepper_z' for k in settings):
            raise ValueError('independent_multi_z_buzz_not_safe')
        return MotionProgram(feature, name, 'STEPPER_BUZZ STEPPER='+name+'\nM400',
                             position, position, modes, axis, 1., 30.)
    distance = 10. if feature == 'M06' else 1.
    if position[axis]+distance > high[axis]-2:
        distance = -distance
    if not low[axis]+2 <= position[axis]+distance <= high[axis]-2:
        raise ValueError('insufficient_test_travel')
    speed = min(5., velocity)
    if axis == 2:
        zvel = settings['printer'].get('max_z_velocity', velocity)
        if not number(zvel) or zvel <= 0:
            raise ValueError('z_velocity_unknown')
        speed = min(1., speed, zvel)
    expected = list(position)
    if feature == 'M06':
        expected[axis] += distance
    script = _script('XYZ'[axis], distance, speed, token, feature == 'M05')
    return MotionProgram(feature, name, script, position, tuple(expected), modes, axis,
                         distance, abs(distance)/speed*2+12)


def modes_match(original, current):
    if len(original) != len(current):
        return False
    return original[:2] == current[:2] and all(abs(a-b) <= 1e-6 for a,b in zip(original[2:], current[2:]))


def position_matches(expected, actual):
    return all(abs(a-b) <= .01 for a,b in zip(expected, actual))


def verify_motion(program, status):
    try:
        if not modes_match(program.modes, modal(status)):
            return False
        th = status['toolhead']
        if not set('xyz') <= set(th['homed_axes']) and program.feature_id != 'M12':
            return False
        actual = vector(status['gcode_move']['position'])
        low, high = vector(th['axis_minimum']), vector(th['axis_maximum'])
        if program.feature_id == 'M12':
            if program.device[-1] not in th['homed_axes']:
                return False
            for i, (lo, hi, pos) in enumerate(zip(low,high,actual)):
                if i == program.axis and program.phase_endstop is not None:
                    # A completed Klipper G28 can position this axis just
                    # outside axis_minimum after endstop-phase correction.
                    # Bound it to the configured switch + one full step,
                    # not an arbitrary expansion of general move limits.
                    if abs(pos-program.phase_endstop)>program.phase_step_tolerance:
                        return False
                elif not lo<=pos<=hi:
                    return False
                if i!=program.axis and abs(pos-program.expected[i])>.01:
                    return False
        else:
            if any(not lo<=pos<=hi for lo,hi,pos in zip(low,high,actual)):
                return False
            if program.expected is not None and not position_matches(program.expected, actual):
                return False
        if program.feature_id in ('M04', 'M05', 'M06'):
            enabled = status['stepper_enable']['steppers']
            if any(enabled.get('stepper_'+a) is not True for a in 'xyz'):
                return False
        if program.feature_id == 'M12':
            cfg = status['configfile']
            values = cfg.get('save_config_pending_items', {}).get('endstop_phase '+program.device, {})
            value = values.get('trigger_phase')
            if cfg.get('save_config_pending') is not True or not isinstance(value,str):
                return False
            parts = value.split('/')
            if len(parts) != 2 or not all(x.isdigit() for x in parts):
                return False
            phase,count = map(int,parts)
            return count == program.phase_count and 0 <= phase < count
        return True
    except (KeyError, TypeError, ValueError):
        return False


def return_program(program, state, status, token):
    if program.feature_id != 'M06' or program.returning:
        raise ValueError('not_waiting_for_measured_return')
    actual, low, high, velocity = geometry(state.settings, status)
    if not position_matches(program.expected, actual) or not modes_match(program.modes, modal(status)):
        raise ValueError('measured_position_or_modes_changed')
    speed = min(5., velocity)
    if program.axis == 2:
        zvel=state.settings['printer'].get('max_z_velocity',velocity)
        if not number(zvel) or zvel <= 0:
            raise ValueError('z_velocity_unknown')
        speed=min(1.,speed,zvel)
    script=_script('XYZ'[program.axis],-program.distance,speed,token,False)
    return replace(program, script=script, expected=program.original, returning=True)


def dispatch_compatible(program,row,state,status,token):
    if program.feature_id == 'M12':
        # last_home is deliberately read on demand, not subscribed globally.
        # Fresh queue/epoch/config guards are provided by the controller.
        # At dispatch verify current modes/position/homed axis/pending config
        # from the existing subscription, without requiring last_home there.
        actual, low, high, velocity = geometry(
            state.settings,status,homed=True,allow_limit_positions=True)
        cfg=status.get('configfile',{})
        return (program.device[-1] in status['toolhead']['homed_axes']
                and phase_pending_allowed(cfg,program.device)
                and position_matches(program.original,actual)
                and modes_match(program.modes,modal(status)))
    if program.returning:
        outward=tuple(program.original[i]+(program.distance if i==program.axis else 0) for i in range(3))
        base=replace(program,expected=outward,returning=False)
        fresh=return_program(base,state,status,token)
    else:
        fresh=compile_motion(row,state,status,token)
    normalize=lambda script: re.sub(r'_PETREL_M_[a-f0-9]{32}', '_PETREL_M_STATE', script)
    return (position_matches(program.original,fresh.original)
            and modes_match(program.modes,fresh.modes)
            and program.distance==fresh.distance
            and normalize(program.script)==normalize(fresh.script))
