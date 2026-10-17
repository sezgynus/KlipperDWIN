"""Pure bounded motion protocols. Commanded coordinates are not metrology."""
from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import re

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


def geometry(settings, status, homed=True, homing=False):
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
        if any(not lo+2 <= p <= hi-2 for lo, hi, p in zip(low, high, position)):
            raise ValueError('move_away_from_axis_limits')
        if 'bed_mesh' in settings:
            mesh = status.get('bed_mesh')
            if not isinstance(mesh, Mapping) or mesh.get('profile_name') or mesh.get('mesh_matrix'):
                raise ValueError('clear_mesh_before_motion_test')
            if 'mesh_matrix' not in mesh:
                if vector(mesh.get('mesh_min'), 2) != vector(mesh.get('mesh_max'), 2):
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


def _script(axis, distance, speed, token, roundtrip):
    if not _TOKEN.fullmatch(token):
        raise ValueError('motion_state_identifier_invalid')
    lines = ['SAVE_GCODE_STATE NAME='+token, 'G91', 'M220 S100',
             'G1 %s%.4f F%.3f' % (axis, distance, speed*60), 'M400']
    if roundtrip:
        lines += ['G4 P500', 'M400', 'G1 %s%.4f F%.3f' % (axis, -distance, speed*60), 'M400']
    lines += ['RESTORE_GCODE_STATE NAME='+token+' MOVE=0']
    return '\n'.join(lines)


def compile_motion(row, state, status, token):
    feature, name = row.feature_id, row.device
    if feature not in _MOVE:
        raise ValueError('motion_feature_unavailable')
    settings = state.settings
    position, low, high, velocity = geometry(settings, status, homed=feature not in ('M03', 'M12'),
                                             homing=feature == 'M03')
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
        pin = settings.get(name, {}).get('endstop_pin', '')
        if not pin or 'virtual_endstop' in pin:
            raise ValueError('phase_physical_endstop_required')
        cfg = status.get('configfile', {})
        if cfg.get('save_config_pending') is not False:
            raise ValueError('existing_or_unknown_pending_config')
        home = status.get('endstop_phase', {}).get('last_home', {}).get(name, {})
        phase, count = home.get('phase'), home.get('phases')
        if type(phase) is not int or type(count) is not int or not 0 <= phase < count <= 4096:
            raise ValueError('home_axis_before_phase_calibration')
        if name[-1] not in status['toolhead']['homed_axes']:
            raise ValueError('axis_not_homed_for_phase')
        return MotionProgram(feature, name, 'ENDSTOP_PHASE_CALIBRATE STEPPER='+name,
                             position, position, modes, None, 0., 12., phase_count=count)
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
        if any(not lo <= p <= hi for lo,hi,p in zip(low,high,actual)):
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
        actual, low, high, velocity = geometry(state.settings,status,homed=False)
        cfg=status.get('configfile',{})
        return (program.device[-1] in status['toolhead']['homed_axes']
                and cfg.get('save_config_pending') is False
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
