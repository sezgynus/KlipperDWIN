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

    def _submit(self, action, script, dispatch_guard=None):
        guard = motion_dispatch_guard(self.printer, owner='probe_wizard',
                                      manual_active=action in ('step', 'accept', 'abort'), position=action == 'step')
        future = self.printer.sendGCode(script, dispatch_guard=dispatch_guard or guard)
        self.pending = (action, future, time.monotonic())
        self.message = 'Waiting for ' + action
        return future

    def start(self):
        self._guard()
        if (self.printer.bed_mesh.pending or self.printer.screws_tilt.pending
                or getattr(getattr(self.printer, 'mmu_session', None), 'pending', None)):
            raise ValueError('Another calibration is running')
        if self.active():
            raise ValueError('Another manual probe is active')
        if self.printer.state.status['configfile'].get('save_config_pending'):
            raise ValueError('Resolve existing config changes first')
        if not all(axis in self.printer.state.status['toolhead'].get('homed_axes', '') for axis in 'xyz'):
            raise ValueError('Home XYZ before calibration')
        settings = self.printer.state.settings
        self.section = 'bltouch' if 'bltouch' in settings else 'probe' if 'probe' in settings else None
        if self.section is None:
            raise ValueError('Probe configuration is unidentified')
        self.epoch = self.printer.state.epoch
        self.phase = 'starting'
        return self._submit('start', 'PROBE_CALIBRATE')

    def testz(self, distance):
        self._guard()
        distance = float(distance)
        if self.phase != 'active' or not self.active():
            raise ValueError('Owned manual probe is not active')
        if not math.isfinite(distance) or distance not in (-.1, -.01, .01, .1):
            raise ValueError('Use a supported TESTZ step')
        return self._submit('step', 'TESTZ Z={:g}'.format(distance))

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

    def update(self):
        if self.epoch is None:
            return
        state = self.printer.state
        if not state.ready or state.epoch != self.epoch:
            self.pending = None
            self.phase = 'interrupted'
            self.message = 'Connection changed; check printer'
            return
        if not self.pending:
            if self.phase == 'active' and not self.active():
                self.phase = 'interrupted'
                self.message = 'Manual probe ended externally'
            return
        action, future, started = self.pending
        if future.done():
            if future.cancelled() or future.exception():
                self.pending = None
                self.phase = 'error'
                self.message = 'Command failed; check printer'
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
                    if time.monotonic() - started <= 30:
                        return
                    self.phase, self.message = 'error', 'Accept failed; no probe offset'
            elif action == 'save':
                self.phase, self.message = 'saved', 'Save requested; Klipper restarts'
            else:
                if time.monotonic() - started <= 30:
                    return
                self.phase, self.message = 'interrupted', 'Result unconfirmed; check printer'
            self.pending = None
        elif time.monotonic() - started > 30:
            future.cancel()
            self.pending = None
            self.phase, self.message = 'interrupted', 'Command unconfirmed; check printer'
