"""Happy Hare state and guarded, completion-tracked MMU operations.

Gate indices stay zero based here; the LCD alone presents G1 for gate 0.
Missing telemetry remains unknown and never enables a motion operation.
"""
from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import time


def integer(value, default=None):
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def boolean(value):
    return value if isinstance(value, bool) else None


def switch(value):
    if isinstance(value, bool):
        return value
    return bool(value) if integer(value) in (0, 1) else None


def text(value, default='Unknown'):
    return value if isinstance(value, str) and value else default


@dataclass(frozen=True)
class MMUUnit:
    name: str
    first_gate: int
    num_gates: int
    selector_type: str
    always_gripped: bool | None
    config_name: str = ''


def units_from_snapshot(snapshot, gates):
    raw = snapshot.get('status', {}).get('mmu_machine')
    if not isinstance(raw, Mapping):
        return ()
    count = integer(raw.get('num_units'))
    if count is None or not 1 <= count <= gates or integer(raw.get('num_gates')) != gates:
        return ()
    units, first = [], 0
    for i in range(count):
        unit = raw.get('unit_%d' % i)
        if not isinstance(unit, Mapping):
            return ()
        n = integer(unit.get('num_gates'))
        if integer(unit.get('first_gate')) != first or n is None or n <= 0 or first + n > gates:
            return ()
        units.append(MMUUnit(text(unit.get('display_name'), text(unit.get('name'), 'Unit %d' % (i + 1))),
                             first, n, text(unit.get('selector_type')), boolean(unit.get('filament_always_gripped')),
                             text(unit.get('name'), '')))
        first += n
    return tuple(units) if first == gates else ()


def motor_states(snapshot, units):
    settings = snapshot.get('settings', {})
    driver_status = snapshot.get('status', {}).get('stepper_enable', {})
    drivers = driver_status.get('steppers', {}) if isinstance(driver_status, Mapping) else {}
    if not isinstance(settings, Mapping) or not isinstance(drivers, Mapping) or not units:
        return ()
    names = set()
    for unit in units:
        config = settings.get('mmu_unit ' + unit.config_name)
        if not isinstance(config, Mapping):
            return ()
        gears = config.get('gear_steppers', config.get('gear_stepper'))
        if isinstance(gears, str):
            gears = [v.strip() for v in gears.split(',')]
        if (not isinstance(gears, (tuple, list)) or not gears
                or any(not isinstance(v, str) or not v or any(c.isspace() for c in v) for v in gears)):
            return ()
        names.update('mmu_stepper ' + v for v in gears)
        if unit.selector_type in {'LinearSelector', 'LinearServoSelector', 'LinearMGSelector',
                                  'LinearMGServoSelector', 'RotarySelector', 'IndexedSelector'}:
            selector = config.get('selector_stepper')
            if not isinstance(selector, str) or not selector or any(c.isspace() for c in selector):
                return ()
            names.add('mmu_stepper ' + selector)
        elif unit.selector_type not in {'ServoSelector', 'VirtualSelector'}:
            return ()
    return tuple((name, boolean(drivers.get(name))) for name in sorted(names))


@dataclass(frozen=True)
class MMULeds:
    object_name: str
    enabled: bool | None
    animation: bool | None
    exit_effect: str
    segments: tuple


def led_state(snapshot, units, unit_index):
    if unit_index is None or not 0 <= unit_index < len(units):
        return None
    unit = units[unit_index]
    name = 'mmu_leds ' + unit.config_name
    raw = snapshot.get('status', {}).get(name)
    if not isinstance(raw, Mapping) or integer(raw.get('num_gates')) != unit.num_gates:
        return None
    counts = tuple(integer(raw.get(k)) for k in ('exit', 'entry', 'status', 'logo'))
    if any(n is None or n < 0 for n in counts) or not any(counts):
        return None
    return MMULeds(name, switch(raw.get('enabled')), switch(raw.get('animation')),
                   text(raw.get('exit_effect')), counts)


@dataclass(frozen=True)
class MMUState:
    epoch: int
    num_gates: int
    gate: int | None
    tool: int | None
    enabled: bool | None
    action: str
    print_state: str
    filament: str
    locked: bool | None
    gate_status: tuple
    ttg_map: tuple
    materials: tuple
    names: tuple
    temperatures: tuple
    spool_ids: tuple
    sensors: tuple
    sync_drive: bool | None
    bowden_progress: int | None
    reason: str
    spoolman_support: str
    endless_enabled: bool | None
    endless_groups: tuple
    colors: tuple
    units: tuple
    unit: int | None
    homed: bool | None
    grip: bool | None
    motors: tuple
    leds: MMULeds | None

    @classmethod
    def from_snapshot(cls, snapshot):
        if snapshot.get('state') != 'ready':
            return None
        raw = snapshot.get('status', {}).get('mmu')
        if not isinstance(raw, Mapping):
            return None
        count = integer(raw.get('num_gates'))
        if count is None or not 1 <= count <= 256:
            return None
        def values(key, parse):
            seq = raw.get(key, ())
            if not isinstance(seq, (tuple, list)):
                seq = ()
            return tuple(parse(seq[i]) if i < len(seq) else None for i in range(count))
        def index(value):
            n = integer(value)
            return n if n is not None and -2 <= n < count else None
        status = text(raw.get('print_state'))
        known_states = {'initialized', 'ready', 'started', 'printing', 'complete',
                        'cancelled', 'error', 'pause_locked', 'paused', 'standby', 'idle'}
        locked = (status == 'pause_locked' if status in known_states
                  else boolean(raw.get('is_locked')))
        filament = text(raw.get('filament')).lower()
        if filament not in ('loaded', 'unloaded'):
            filament = 'unknown'
        # Never promote an intermediate/contradictory physical state to loaded/empty.
        pos = integer(raw.get('filament_pos'))
        if 'filament_pos' in raw and pos != {'loaded': 10, 'unloaded': 0}.get(filament):
            filament = 'unknown'
        progress = raw.get('bowden_progress')
        if (isinstance(progress, bool) or not isinstance(progress, (int, float))
                or not math.isfinite(progress) or not 0 <= progress <= 100):
            progress = None
        else:
            progress = round(progress)
        sensors = raw.get('sensors', {})
        if not isinstance(sensors, Mapping):
            sensors = {}
        selector = raw.get('selector', {})
        selector = selector if isinstance(selector, Mapping) else {}
        grip = {'Gripped': True, 'Released': False}.get(text(selector.get('grip')))
        if grip is None:
            grip = {'Down': True, 'Up': False}.get(text(selector.get('servo')))
        units = units_from_snapshot(snapshot, count)
        return cls(snapshot.get('epoch', 0), count, index(raw.get('gate')),
                   index(raw.get('tool')), boolean(raw.get('enabled')),
                   text(raw.get('action')), status, filament, locked,
                   values('gate_status', lambda v: integer(v) if integer(v) in (-1, 0, 1, 2) else None),
                   values('ttg_map', index), values('gate_material', lambda v: text(v, '--')),
                   values('gate_filament_name', lambda v: text(v, '--')),
                   values('gate_temperature', lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None),
                   values('gate_spool_id', integer),
                   tuple(sorted((str(k), boolean(v)) for k, v in sensors.items())),
                   boolean(raw.get('sync_drive')), progress,
                   text(raw.get('reason_for_pause'), ''), text(raw.get('spoolman_support')),
                   switch(raw.get('endless_spool_enabled', raw.get('endless_spool'))),
                   values('endless_spool_groups', lambda v: integer(v) if integer(v) is not None and v >= 0 else None),
                   values('gate_color', lambda v: text(v, '--')), units,
                   integer(raw.get('unit')), boolean(raw.get('is_homed')), grip, motor_states(snapshot, units),
                   led_state(snapshot, units, integer(raw.get('unit'))))

    @property
    def busy(self):
        return self.action.lower() != 'idle'

    @property
    def fingerprint(self):
        return (self.epoch, self.num_gates, self.gate, self.tool, self.enabled,
                self.action, self.print_state, self.filament, self.locked,
                self.gate_status, self.ttg_map, self.endless_enabled, self.endless_groups,
                self.materials, self.colors, self.spool_ids, self.spoolman_support,
                self.temperatures, self.units, self.unit, self.homed, self.grip, self.sync_drive, self.motors, self.leds)

    @property
    def active_unit(self):
        return self.units[self.unit] if self.unit is not None and 0 <= self.unit < len(self.units) else None

    def tools_for_gate(self, gate):
        return tuple(i for i, mapped in enumerate(self.ttg_map) if mapped == gate)


@dataclass(frozen=True)
class MMUOperation:
    action: str
    gate: int | None
    tool: int | None
    loaded: bool | None
    fingerprint: tuple
    script: str
    label: str
    values: tuple = ()
    enabled: bool | None = None
    expected_spool_ids: tuple = ()


class MMUSession:
    TIMEOUT = 300.0
    GATE_ACTIONS = {'select', 'load', 'change', 'unload', 'eject', 'preload', 'check'}
    RECOVERY_ACTIONS = {'recover', 'manual', 'unlock', 'resume'}
    GRIP_SELECTORS = {'ServoSelector', 'RotarySelector', 'LinearServoSelector', 'LinearMGServoSelector'}
    HOME_SELECTORS = {'LinearSelector', 'LinearServoSelector', 'LinearMGSelector', 'LinearMGServoSelector'}
    LED_MODES = ('off', 'gate_status', 'filament_color', 'slicer_color')

    def __init__(self, printer):
        self.printer = printer
        self.pending = None
        self.phase, self.message = 'idle', ''
        self.operation = None
        self._cursor = None

    @property
    def state(self):
        return MMUState.from_snapshot(self.printer.subscription.snapshot())

    def prepare(self, action, gate=None, tool=None, loaded=None, snapshot=None, ignore_pending=False, values=(), enabled=None):
        p = self.printer
        expected_spool_ids = ()
        snap = p.subscription.snapshot() if snapshot is None else snapshot
        m = MMUState.from_snapshot(snap)
        if (p.connection_error or not p.state.ready or snap.get('epoch') != p.state.epoch
                or m is None):
            raise ValueError('MMU unavailable')
        if self.pending is not None and not ignore_pending:
            raise ValueError('Wait for MMU operation')
        if self.phase == 'error':
            raise ValueError('Acknowledge MMU result first')
        if m.enabled is not True and not (action == 'enable' and m.enabled is False and enabled is True):
            raise ValueError('MMU disabled or unknown')
        if m.busy or p.jog_recovery_required:
            raise ValueError('MMU busy or recovery needed')
        if snap.get('status', {}).get('manual_probe', {}).get('is_active') or any(
                getattr(getattr(p, name, None), 'pending', None)
                for name in ('bed_mesh', 'screws_tilt', 'probe_wizard')):
            raise ValueError('Another operation is active')
        ps = snap.get('status', {}).get('print_stats', {}).get('state')
        if ps not in ('standby', 'complete', 'cancelled', 'error', 'paused', 'printing'):
            raise ValueError('Print state unknown')
        if ps == 'printing' or m.print_state in ('started', 'printing'):
            raise ValueError('Printing; monitoring only')
        if action not in self.RECOVERY_ACTIONS:
            if ps == 'paused' or m.print_state in ('paused', 'pause_locked'):
                raise ValueError('Use recovery during a pause')
            if m.locked is not False:
                raise ValueError('MMU lock state unknown')
        elif m.locked is None:
            raise ValueError('MMU lock state unknown')
        if action in self.GATE_ACTIONS or action == 'spool':
            if integer(gate) is None or not 0 <= gate < m.num_gates:
                raise ValueError('Invalid gate')
            target = 'G%d' % (gate + 1)
        else:
            target = ''
        if action in ('select', 'load', 'preload', 'check', 'bypass', 'home_selector', 'check_all', 'grip', 'release', 'enable', 'motors_off', 'unit_select') and m.filament != 'unloaded':
            raise ValueError('Unload filament first')
        if action in ('unload', 'unload_extruder') and m.filament != 'loaded':
            raise ValueError('Loaded filament required')
        if action == 'enable':
            if not isinstance(enabled, bool) or m.enabled == enabled:
                raise ValueError('Choose a different known MMU enable state')
            script, label = 'MMU ENABLE=%d' % enabled, 'Enable MMU' if enabled else 'Disable MMU'
        elif action == 'motors_off':
            if not m.motors or any(v is None for _, v in m.motors) or m.sync_drive is None:
                raise ValueError('Known MMU driver states required')
            values = tuple(name for name, _ in m.motors)
            script, label = 'MMU_MOTORS_OFF UNIT=ALL', 'Release all MMU motors'
        elif action == 'unit_select':
            if not isinstance(values, (tuple, list)) or not values or integer(values[0]) is None:
                raise ValueError('Choose a valid MMU unit')
            index = values[0]
            if len(m.units) < 2 or not 0 <= index < len(m.units):
                raise ValueError('Validated multiple units required')
            gate = m.units[index].first_gate
            values = (index, m.units)
            script = 'MMU_SELECT GATE=%d' % gate
            label = 'Select U%d / G%d' % (index + 1, gate + 1)
        elif action in ('led_enable', 'led_animation', 'led_mode'):
            leds = m.leds
            if m.active_unit is None or leds is None or leds.enabled is None or leds.animation is None:
                raise ValueError('Known unit LED state required')
            mode = None
            if action == 'led_mode':
                if not isinstance(values, (tuple, list)) or not values or not isinstance(values[0], str) or values[0] not in self.LED_MODES:
                    raise ValueError('Unsupported LED exit mode')
                mode = values[0]
                if not leds.segments[0] or mode == leds.exit_effect:
                    raise ValueError('Choose a different supported exit mode')
                desired = replace(leds, exit_effect=mode)
                argument, label = 'EXIT_EFFECT=' + mode, 'Exit: ' + mode.replace('_', ' ')
            else:
                field = 'enabled' if action == 'led_enable' else 'animation'
                if not isinstance(enabled, bool) or getattr(leds, field) == enabled:
                    raise ValueError('Choose a different known LED state')
                desired = replace(leds, **{field: enabled})
                argument = ('ENABLE' if action == 'led_enable' else 'ANIMATION') + '=%d' % enabled
                label = ('LEDs ' if action == 'led_enable' else 'Animation ') + ('ON' if enabled else 'OFF')
            values = (mode, m.unit, m.units, desired)
            script = 'MMU_LED UNIT=%d %s' % (m.unit, argument)
            label = 'U%d ' % (m.unit + 1) + label
        elif action == 'select':
            script, label = 'MMU_SELECT GATE=%d' % gate, 'Select ' + target
        elif action == 'load':
            if gate != m.gate or m.gate_status[gate] not in (1, 2):
                raise ValueError('Select an available gate first')
            script, label = 'MMU_LOAD', 'Load ' + target
        elif action == 'change':
            tools = m.tools_for_gate(gate)
            if not tools or m.gate_status[gate] not in (1, 2) or m.filament == 'unknown' or m.gate == -2:
                raise ValueError('Mapped available gate required')
            tool = m.tool if m.tool in tools else tools[0]
            script, label = 'MMU_CHANGE_TOOL TOOL=%d STANDALONE=1' % tool, 'Load/change T%d / %s' % (tool, target)
        elif action == 'unload':
            if gate != m.gate:
                raise ValueError('Unload the current gate')
            script, label = 'MMU_UNLOAD', 'Unload ' + target
        elif action == 'eject':
            if m.filament == 'unknown' or (m.filament == 'loaded' and gate != m.gate):
                raise ValueError('Unload current filament first')
            # FORCE explicitly ejects the spool after unloading the current gate.
            script, label = 'MMU_EJECT GATE=%d FORCE=1' % gate, 'Eject spool ' + target
        elif action in ('preload', 'check'):
            script = '%s GATE=%d' % ('MMU_PRELOAD' if action == 'preload' else 'MMU_CHECK_GATE', gate)
            label = action.title() + ' ' + target
        elif action == 'bypass':
            script, label = 'MMU_SELECT BYPASS=1', 'Select bypass'
        elif action in ('load_extruder', 'unload_extruder'):
            if m.gate != -2:
                raise ValueError('Select bypass first')
            if action == 'load_extruder' and m.filament != 'unloaded':
                raise ValueError('Unload filament first')
            script = ('MMU_LOAD' if action == 'load_extruder' else 'MMU_UNLOAD') + ' EXTRUDER_ONLY=1'
            label = action.replace('_', ' ').title()
        elif action == 'recover':
            script, label = 'MMU_RECOVER', 'Auto recover'
        elif action == 'manual':
            if integer(tool) is None or integer(gate) is None or not 0 <= tool < m.num_gates or not 0 <= gate < m.num_gates or not isinstance(loaded, bool):
                raise ValueError('Choose actual tool/gate/state')
            script = 'MMU_RECOVER TOOL=%d GATE=%d LOADED=%d' % (tool, gate, loaded)
            label = 'Set T%d / G%d %s' % (tool, gate + 1, 'loaded' if loaded else 'unloaded')
        elif action == 'unlock':
            if m.locked is not True:
                raise ValueError('MMU is not locked')
            script, label = 'MMU_UNLOCK', 'Unlock / reheat'
        elif action == 'map':
            if (not isinstance(values, (tuple, list)) or len(values) != m.num_gates
                    or any(integer(v) is None or not 0 <= v < m.num_gates for v in values)
                    or any(v is None or v < 0 for v in m.ttg_map)):
                raise ValueError('Complete valid tool map required')
            values = tuple(values)
            script = 'MMU_TTG_MAP MAP=' + ','.join(str(v) for v in values)
            label = 'Save tool map'
        elif action == 'endless':
            if (not isinstance(enabled, bool) or m.endless_enabled is None
                    or any(v is None for v in m.endless_groups)
                    or not isinstance(values, (tuple, list)) or len(values) != m.num_gates
                    or any(integer(v) is None or v < 0 for v in values)):
                raise ValueError('Complete EndlessSpool state required')
            values = tuple(values)
            script = 'MMU_ENDLESS_SPOOL ENABLE=%d GROUPS=%s' % (enabled, ','.join(str(v) for v in values))
            label = 'Save EndlessSpool'
        elif action == 'spool':
            if m.spoolman_support not in ('off', 'readonly', 'push'):
                raise ValueError('Spoolman mode blocks local assignment')
            if (not isinstance(values, (tuple, list)) or len(values) != 1
                    or integer(values[0]) is None or (values[0] != -1 and values[0] < 1)
                    or any(sid is None or (sid != -1 and sid < 1) for sid in m.spool_ids)):
                raise ValueError('Known spool IDs and valid assignment required')
            temperature = m.temperatures[gate]
            if temperature is None or temperature <= 0 or int(temperature) != temperature:
                raise ValueError('Known filament temperature required')
            temperature = int(temperature)
            values = tuple(values)
            script = 'MMU_GATE_MAP GATE=%d SPOOLID=%d TEMP=%d' % (gate, values[0], temperature)
            label = ('Clear spool on ' if values[0] == -1 else 'Assign #%d to ' % values[0]) + target
            expected_spool_ids = tuple(values[0] if i == gate else -1 if values[0] > 0 and sid == values[0] else sid
                                       for i, sid in enumerate(m.spool_ids))
        elif action == 'check_all':
            if m.gate is None or m.gate < 0:
                raise ValueError('Select an MMU gate first')
            script, label = 'MMU_CHECK_GATE ALL=1', 'Check all %d gates' % m.num_gates
        elif action == 'home_selector':
            unit = m.active_unit
            if len(m.units) != 1 or unit is None or unit.selector_type not in self.HOME_SELECTORS:
                raise ValueError('Single homing selector required')
            tools = [i for i, gate in enumerate(m.ttg_map) if gate is not None and gate >= 0]
            if not tools or any(gate is None or gate < 0 for gate in m.ttg_map):
                raise ValueError('Valid tool map required')
            tool = m.tool if m.tool in tools else tools[0]
            values = (m.units,)
            script, label = 'MMU_HOME UNIT=0 TOOL=%d' % tool, 'Home selector / T%d' % tool
        elif action in ('grip', 'release', 'sync_on', 'sync_off'):
            unit = m.active_unit
            if (unit is None or m.gate is None or not unit.first_gate <= m.gate < unit.first_gate + unit.num_gates):
                raise ValueError('Known active unit and gate required')
            if unit.selector_type in self.HOME_SELECTORS and m.homed is not True:
                raise ValueError('Home selector before drive operations')
            gate, values = m.gate, (m.unit, m.units)
            if action in ('grip', 'release'):
                if unit.selector_type not in self.GRIP_SELECTORS or m.grip is None:
                    raise ValueError('Grip-capable selector telemetry required')
                if action == 'release' and unit.always_gripped is not False:
                    raise ValueError('Selector cannot release filament')
                script = 'MMU_GRIP' if action == 'grip' else 'MMU_RELEASE'
                label = '%s G%d' % (action.title(), m.gate + 1)
            else:
                if m.filament != 'loaded' or m.sync_drive is None or unit.always_gripped is None:
                    raise ValueError('Loaded filament and known sync state required')
                if action == 'sync_off' and unit.always_gripped:
                    raise ValueError('Always-gripped unit cannot unsync')
                script = 'MMU_SYNC_GEAR_MOTOR SYNC=%d' % (action == 'sync_on')
                label = 'Gear sync ' + ('ON' if action == 'sync_on' else 'OFF')
        elif action == 'resume':
            if ps != 'paused' or m.locked is not False or m.filament != 'loaded':
                raise ValueError('Recover and unlock first')
            script, label = 'RESUME', 'Resume print'
        else:
            raise ValueError('Unsupported MMU operation')
        return MMUOperation(action, gate, tool, loaded, m.fingerprint, script, label, tuple(values), enabled, expected_spool_ids)

    def start(self, operation):
        fresh = self.prepare(operation.action, operation.gate, operation.tool, operation.loaded,
                             values=operation.values, enabled=operation.enabled)
        if fresh != operation:
            raise ValueError('MMU changed; select again')
        self.operation = operation
        self.started = time.monotonic()
        self._cursor, _ = self.printer.subscription.responses_since(None)
        self._dispatch_operation = operation
        self.pending = self.printer.subscription.request(
            'printer.gcode.script', {'script': operation.script}, guard=self._dispatch_guard)
        self.phase, self.message = 'running', 'Waiting: ' + operation.label

    def _dispatch_guard(self):
        try:
            op = self._dispatch_operation
            return self.prepare(op.action, op.gate, op.tool, op.loaded,
                                ignore_pending=True, values=op.values, enabled=op.enabled) == op
        except ValueError:
            return False

    def _fail(self, message):
        if self.pending is not None:
            self.pending.cancel()  # Cancels a queued request; never replays motion.
        self.pending = None
        self.phase, self.message = 'error', message

    def _confirmed(self, m, status):
        op = self.operation
        if op.action == 'resume':
            return status.get('print_stats', {}).get('state') == 'printing' and m.locked is False
        if op.action == 'unlock':
            return m.locked is False
        if op.action == 'manual':
            return (m.tool == op.tool and m.gate == op.gate and
                    m.filament == ('loaded' if op.loaded else 'unloaded'))
        if op.action == 'recover':
            return m.filament != 'unknown'
        if m.locked is not False:
            return False
        if op.action == 'enable': return m.enabled == op.enabled
        if op.action == 'unit_select': return m.units == op.values[1] and m.unit == op.values[0] and m.gate == op.gate and m.filament == 'unloaded'
        if op.action.startswith('led_'): return m.unit == op.values[1] and m.units == op.values[2] and m.leds == op.values[3]
        if op.action == 'motors_off': return tuple(name for name, _ in m.motors) == op.values and all(v is False for _, v in m.motors) and m.sync_drive is False and m.filament == 'unloaded'
        if op.action == 'map': return m.ttg_map == op.values
        if op.action == 'endless': return m.endless_enabled == op.enabled and m.endless_groups == op.values
        if op.action == 'spool':
            return m.spool_ids == op.expected_spool_ids
        if op.action == 'check_all': return m.filament == 'unloaded' and all(v in (0, 1, 2) for v in m.gate_status)
        if op.action == 'home_selector': return m.units == op.values[0] and m.homed is True and m.tool == op.tool and m.gate == m.ttg_map[op.tool] and m.filament == 'unloaded'
        if op.action in ('grip', 'release'): return m.units == op.values[1] and m.gate == op.gate and m.unit == op.values[0] and m.grip == (op.action == 'grip') and m.filament == 'unloaded'
        if op.action in ('sync_on', 'sync_off'): return m.units == op.values[1] and m.gate == op.gate and m.unit == op.values[0] and m.sync_drive == (op.action == 'sync_on') and m.filament == 'loaded'
        if op.action == 'select': return m.gate == op.gate and m.filament == 'unloaded'
        if op.action == 'bypass': return m.gate == -2 and m.filament == 'unloaded'
        if op.action in ('load', 'change'): return m.gate == op.gate and m.filament == 'loaded' and (op.action != 'change' or m.tool == op.tool)
        if op.action in ('unload', 'unload_extruder'): return m.filament == 'unloaded'
        if op.action == 'load_extruder': return m.gate == -2 and m.filament == 'loaded'
        if op.action == 'eject': return m.gate_status[op.gate] == 0
        if op.action in ('preload', 'check'): return m.gate_status[op.gate] in (0, 1, 2) and m.filament == 'unloaded'
        return False

    def _query_objects(self):
        objects = {'mmu': None, 'print_stats': None}
        if self.operation.action == 'motors_off':
            objects['stepper_enable'] = None
        if self.operation.action.startswith('led_'):
            objects[self.operation.values[3].object_name] = None
        if self.operation.action == 'unit_select' or self.operation.action.startswith('led_'):
            objects['mmu_machine'] = None
        return objects

    def update(self):
        if self.pending is None:
            return
        p = self.printer
        m = self.state
        if p.connection_error or m is None or m.epoch != self.operation.fingerprint[0]:
            self._fail('Connection changed; check MMU')
            return
        if time.monotonic() - self.started > self.TIMEOUT:
            self._fail('Result unconfirmed; check MMU')
            return
        self._cursor, responses = p.subscription.responses_since(self._cursor)
        error = next((line for line in responses if line.startswith('!!')), None)
        if error:
            self._fail(error[2:].strip() or 'MMU command failed')
            return
        if not self.pending.done():
            return
        try:
            result = self.pending.result()
            if self.phase == 'running':
                self.pending = p.subscription.request('printer.objects.query',
                    {'objects': self._query_objects()})
                self.phase, self.message = 'confirming', 'Checking MMU result'
                return
            status = result['status']
            if not isinstance(status, Mapping) or not self._query_objects().keys() <= status.keys():
                self._fail('Incomplete MMU result; check status')
                return
            snap = p.subscription.snapshot()
            snap = dict(snap, status=dict(snap['status'], **status))
            m = MMUState.from_snapshot(snap)
            if (m is None or m.epoch != self.operation.fingerprint[0]
                    or m.num_gates != self.operation.fingerprint[1]
                    or (m.enabled != self.operation.enabled if self.operation.action == 'enable' else m.enabled is not True)
                    or m.busy or not self._confirmed(m, status)):
                self._fail(m.reason if m and m.reason else 'State unconfirmed; check MMU')
                return
        except Exception:
            self._fail('Command failed; check MMU/log')
            return
        self.pending = None
        self.phase, self.message = 'complete', 'Completed: ' + self.operation.label
