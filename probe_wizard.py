"""Explicit manual-probe session; no automatic motion or command replay."""
from operation_guards import motion_dispatch_guard, config_save_guard
import math
import time


class ProbeWizard:
    def __init__(self, printer):
        self.printer = printer
        self.phase = 'idle'
        self.message = 'Home XYZ; check probe point'
        self.epoch = None
        self.pending = None
        self.section = None
        self.accepted_offset = None
        self._center_restore = None

    def available(self):
        state = self.printer.state
        return (state.ready and self.printer.capabilities.probe
                and 'is_active' in state.status.get('manual_probe', {})
                and 'save_config_pending' in state.status.get('configfile', {})
                and 'save_config_pending_items' in state.status.get('configfile', {}))

    def active(self):
        return bool(self.printer.state.status.get('manual_probe', {}).get('is_active'))

    def _guard(self):
        if not self.available() or self.printer.connection_error:
            raise ValueError('Probe status unavailable')
        if self.printer.status in ('printing', 'paused', 'pausing'):
            raise ValueError('Calibration unavailable during print')
        if self.epoch is not None and self.epoch != self.printer.state.epoch:
            raise ValueError('Calibration connection changed')
        if self.pending:
            raise ValueError('Wait for the pending probe command')
        if self.printer.jog_recovery_required:
            raise ValueError('Restore G-code state before calibration')

    def _submit(self, action, script, dispatch_guard=None):
        guard = motion_dispatch_guard(self.printer, owner='probe_wizard',
                                      manual_active=action in ('step', 'accept', 'abort'))
        if action == 'start':
            motion_guard = guard
            def guard():
                live = self.printer.subscription.snapshot()['status']['toolhead']
                return (motion_guard() and all(a in live.get('homed_axes', '') for a in 'xyz')
                        and all(abs(live['position'][a]-self.center[a]) <= .05 for a in (0,1)))
        if action == 'center':
            # Completion RPC confirms SAVE before changing modal state,
            # and sends RESTORE separately if movement fails. Never replay G1.
            self._center_restore = 'RESTORE_GCODE_STATE NAME=LCD_PROBE_CENTER MOVE=0'
            future = self.printer.sendGCode(script, cleanup=self._center_restore,
                                            report_error=False, dispatch_guard=guard)
        else:
            future = self.printer.subscription.request('printer.gcode.script', {'script': script},
                                                       guard=dispatch_guard or guard)
        self.pending = (action, future, time.monotonic())
        self.message = 'Waiting for ' + action
        return future

    def start(self):
        if self.phase in ('error', 'interrupted') and not self.pending and not self.active():
            self.epoch = None
        self._guard()
        if (self.printer.bed_mesh.pending or self.printer.screws_tilt.pending
                or getattr(getattr(self.printer, 'mmu_session', None), 'pending', None)):
            raise ValueError('Another calibration is running')
        if self.active():
            raise ValueError('Another manual probe is active')
        settings = self.printer.state.settings
        self.section = 'bltouch' if 'bltouch' in settings else 'probe' if 'probe' in settings else None
        if self.section is None:
            raise ValueError('Probe configuration is unidentified')
        self.epoch = self.printer.state.epoch
        self.accepted_offset = None
        self.phase = 'starting'
        if not all(a in self.printer.state.status['toolhead'].get('homed_axes', '') for a in 'xyz'):
            return self._submit('home', 'G28')
        script, self.center = self._center_script()
        return self._submit('center', script)

    def _center_script(self):
        p = self.printer
        settings, status = p.state.settings, p.state.status
        low, high = p.capabilities.axis_minimum, p.capabilities.axis_maximum
        cfg = settings.get('bed_mesh', {})
        def pair(value):
            return tuple(map(float, value.split(',') if isinstance(value, str) else value))
        if 'mesh_radius' in cfg:
            bed_center = pair(cfg.get('mesh_origin', (0, 0)))
        elif 'mesh_min' in cfg and 'mesh_max' in cfg:
            mesh_low, mesh_high = pair(cfg['mesh_min']), pair(cfg['mesh_max'])
            bed_center = tuple((a+b)/2 for a,b in zip(mesh_low, mesh_high))
        else:
            bed_center = tuple((max(0, low[a])+high[a])/2 for a in (0, 1))
        probe = settings[self.section]
        center = tuple(bed_center[a]-float(probe.get(('x_offset','y_offset')[a], 0)) for a in (0, 1))
        if (len(center) != 2 or any(not math.isfinite(v) or not low[a] <= v <= high[a]
                                  for a,v in enumerate(center))):
            raise ValueError('Probe cannot reach bed center; check offsets')
        homed = status['toolhead'].get('homed_axes', '')
        lift = max(5.0, float(status['toolhead']['position'][2])) if 'z' in homed else 5.0
        if not math.isfinite(lift) or not low[2] <= lift <= high[2]:
            raise ValueError('Insufficient Z clearance for calibration')
        gm = status['gcode_move']
        origin = gm.get('homing_origin', (0,0,0))
        if 'gcode_position' in gm:
            origin = tuple(gm['position'][a]-gm['gcode_position'][a] for a in range(3))
        xyz = (center[0]-origin[0], center[1]-origin[1], lift-origin[2])
        script = ('SAVE_GCODE_STATE NAME=LCD_PROBE_CENTER\nG90\n'
                   'G1 Z{:.3f} F600\nG1 X{:.3f} Y{:.3f} F3000\n'
                   'RESTORE_GCODE_STATE NAME=LCD_PROBE_CENTER MOVE=0\nM400').format(xyz[2],xyz[0],xyz[1])
        return script, center

    def testz(self, distance):
        self._guard()
        if distance in ('--', '-', '+', '++'):
            step = distance
        else:
            distance = float(distance)
            if not math.isfinite(distance) or abs(distance) not in (.005, .01, .05, .1, 1):
                raise ValueError('Use a supported TESTZ step')
            step = '{:g}'.format(distance)
        if self.phase != 'active' or not self.active():
            raise ValueError('Owned manual probe is not active')
        return self._submit('step', 'TESTZ Z=' + step)

    def accept(self):
        self._guard()
        if self.phase != 'active' or not self.active():
            raise ValueError('Owned manual probe is not active')
        return self._submit('accept', 'ACCEPT')

    def abort(self):
        self._guard()
        if self.phase != 'active' or not self.active():
            raise ValueError('Owned manual probe is not active')
        return self._submit('abort', 'ABORT')

    def save(self):
        self._guard()
        config = self.printer.subscription.snapshot()['status']['configfile']
        pending = config.get('save_config_pending_items', {})
        if (self.phase != 'accepted' or self.active() or config.get('save_config_pending') is not True or set(pending) != {self.section}
                or set(pending[self.section] or {}) != {'z_offset'}
                or pending[self.section]['z_offset'] != self.accepted_offset):
            raise ValueError('Only the accepted probe offset may be saved')
        guard = config_save_guard(self.printer, config, 'probe_wizard')
        return self._submit('save', 'SAVE_CONFIG', dispatch_guard=guard)

    def _retain_center_recovery(self, action, future):
        """Require explicit modal-state recovery only if cleanup is unconfirmed."""
        if action != 'center' or getattr(future, 'cleanup_complete', False):
            return False
        with self.printer._jog_lock:
            self.printer._jog_restore = self._center_restore
        return True

    def update(self):
        if self.epoch is None:
            return
        state = self.printer.state
        if not state.ready or state.epoch != self.epoch:
            recovery = (self._retain_center_recovery(self.pending[0], self.pending[1])
                        if self.pending else False)
            self.pending = None
            self.phase = 'interrupted'
            self.message = ('Restore G-code state from Recovery' if recovery
                            else 'Connection changed; check printer')
            return
        if not self.pending:
            if self.phase == 'active' and not self.active():
                self.phase = 'interrupted'
                self.message = 'Manual probe ended externally'
            return
        action, future, started = self.pending
        timeout = 180 if action in ('home', 'center', 'start') else 30
        if future.done():
            if future.cancelled() or future.exception():
                recovery = self._retain_center_recovery(action, future)
                self.pending = None
                # A rejected TESTZ does not end an active Klipper manual session.
                # Keep the controls available without replaying the failed step.
                self.phase = 'active' if action == 'step' and self.active() else 'error'
                self.message = ('Restore G-code state from Recovery' if recovery
                                else 'Step not applied' if self.phase == 'active'
                                else 'Command failed; check printer')
                return
            if action == 'home':
                if not all(a in state.status['toolhead'].get('homed_axes', '') for a in 'xyz'):
                    if time.monotonic()-started <= timeout: return
                    self.pending = None
                    self.phase, self.message = 'error', 'Homing not confirmed'
                    return
                self.pending = None
                script, self.center = self._center_script()
                self._submit('center', script)
                return
            if action == 'center':
                live = self.printer.subscription.snapshot()
                toolhead = live['status']['toolhead']
                if (live['state'] != 'ready' or live['epoch'] != self.epoch
                        or not all(a in toolhead.get('homed_axes', '') for a in 'xyz')):
                    if time.monotonic()-started <= timeout: return
                    self.pending = None
                    self.phase, self.message = 'error', 'Homing not confirmed'
                    return
                if any(abs(toolhead['position'][a]-self.center[a]) > .05 for a in (0, 1)):
                    if time.monotonic()-started <= timeout: return
                    self.pending = None
                    self.phase, self.message = 'error', 'Center position not confirmed'
                    return
                self.pending = None
                self._submit('start', 'PROBE_CALIBRATE')
                return
            if action == 'start' and self.active():
                self.phase, self.message = 'active', 'Adjust with TESTZ; then Accept'
            elif action == 'step' and self.active():
                self.phase, self.message = 'active', 'Step completed'
            elif action == 'abort' and not self.active():
                self.phase, self.message = 'idle', 'Calibration aborted'
                self.epoch = None
            elif action == 'accept' and not self.active():
                config = state.status['configfile']
                items = config.get('save_config_pending_items', {})
                if config.get('save_config_pending') and 'z_offset' in (items.get(self.section) or {}):
                    self.accepted_offset = items[self.section]['z_offset']
                    self.phase, self.message = 'accepted', 'Offset accepted; save separately'
                else:
                    if time.monotonic() - started <= timeout:
                        return
                    self.phase, self.message = 'error', 'Accept failed; no probe offset'
            elif action == 'save':
                self.phase, self.message = 'saved', 'Save requested; Klipper restarts'
            else:
                if time.monotonic() - started <= timeout:
                    return
                self.phase, self.message = 'interrupted', 'Result unconfirmed; check printer'
            self.pending = None
        elif time.monotonic() - started > timeout:
            future.cancel()
            recovery = self._retain_center_recovery(action, future)
            self.pending = None
            self.phase = 'interrupted'
            self.message = ('Restore G-code state from Recovery' if recovery
                            else 'Command unconfirmed; check printer')
