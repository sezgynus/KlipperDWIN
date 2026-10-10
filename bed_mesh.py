"""Completion-tracked bed calibration and read-only profile snapshots."""
from operation_guards import motion_dispatch_guard, config_save_guard
import copy
from dataclasses import dataclass
import math
import re
import time
from collections.abc import Mapping


def finite(value):
    if isinstance(value, bool):
        raise ValueError('Invalid mesh number')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Invalid mesh number')
    return number


@dataclass(frozen=True)
class MeshData:
    name: str
    points: tuple
    minimum: tuple
    maximum: tuple

    @classmethod
    def parse(cls, name, points, minimum, maximum):
        if not isinstance(points, (tuple, list)) or not 2 <= len(points) <= 25:
            raise ValueError('Mesh data unavailable')
        matrix = tuple(tuple(finite(z) for z in row) for row in points)
        if not 2 <= len(matrix[0]) <= 25 or any(len(row) != len(matrix[0]) for row in matrix):
            raise ValueError('Invalid mesh dimensions')
        low, high = tuple(map(finite, minimum)), tuple(map(finite, maximum))
        if len(low) != 2 or len(high) != 2 or any(a >= b for a, b in zip(low, high)):
            raise ValueError('Invalid mesh limits')
        return cls(name, matrix, low, high)

    @classmethod
    def current(cls, status):
        return cls.parse(status.get('profile_name', '') or 'Current Mesh',
                         status['probed_matrix'], status['mesh_min'], status['mesh_max'])

    @classmethod
    def profile(cls, name, status):
        profile = status['profiles'][name]
        params = profile['mesh_params']
        mesh = cls.parse(name, profile['points'],
                         (params['min_x'], params['min_y']), (params['max_x'], params['max_y']))
        if (params['x_count'] != len(mesh.points[0]) or params['y_count'] != len(mesh.points)):
            raise ValueError('Invalid profile dimensions')
        return mesh

    @property
    def extrema(self):
        values = [z for row in self.points for z in row]
        return min(values), max(values)


class BedMeshSession:
    TIMEOUT = 900
    PROBE_RESPONSE = re.compile(r'probe at\s+([-+\d.eE]+),\s*([-+\d.eE]+).*?\bz\s*=\s*([-+\d.eE]+)', re.I)

    def __init__(self, printer):
        self.printer = printer
        self.phase, self.message = 'idle', ''
        self.pending = None
        self.epoch = None
        self.mesh = None
        self.profile_name = ''
        self.progress = {}
        self.layout = None
        self.status = {}
        self.revision = 0
        self._cursor = 0
        self._calibrated_mesh = None

    def _guard(self, motion=False):
        p = self.printer
        snapshot = p.subscription.snapshot()
        if (not p.state.ready or p.connection_error or not p.capabilities.bed_mesh
                or snapshot['state'] != 'ready' or snapshot['epoch'] != p.state.epoch):
            raise ValueError('Bed mesh unavailable; check printer')
        if self.pending:
            raise ValueError('Wait for the mesh operation')
        if motion and (not p.capabilities.probe or p.jog_recovery_required
                or p.status in ('printing', 'paused', 'pausing')
                or p.state.status.get('manual_probe', {}).get('is_active')
                or p.screws_tilt.pending or p.probe_wizard.pending
                or getattr(getattr(p, 'mmu_session', None), 'pending', None)):
            raise ValueError('Calibration unavailable; check printer')

    def _submit(self, phase, method, params, message, dispatch_guard=None):
        self.epoch = self.printer.state.epoch
        self.started = time.monotonic()
        self.phase, self.message = phase, message
        if phase == 'measuring' or dispatch_guard is not None:
            guard = dispatch_guard or motion_dispatch_guard(self.printer, owner='bed_mesh')
            self.pending = self.printer.subscription.request(method, params, guard=guard)
        else:
            self.pending = self.printer.subscription.request(method, params)
        self.revision += 1

    def refresh(self):
        self._guard()
        self.status, self.mesh = {}, None
        self._submit('profiles', 'printer.objects.query', {'objects': {'bed_mesh': None}}, 'Reading mesh profiles...')

    def entries(self):
        profiles = self.status.get('profiles', {})
        return (None,) + tuple(sorted(profiles, key=lambda n: (n.casefold(), n)))

    def view(self, name=None):
        self._guard()
        if self.epoch != self.printer.state.epoch:
            raise ValueError('Mesh connection changed')
        try:
            mesh = MeshData.current(self.status) if name is None else MeshData.profile(name, self.status)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError('Selected mesh unavailable') from error
        self.mesh = mesh
        self.phase, self.message = 'viewing', ''
        self.revision += 1
        return mesh

    def _configured_layout(self):
        cfg = self.printer.state.settings['bed_mesh']
        if 'mesh_radius' in cfg:
            radius = finite(cfg['mesh_radius'])
            origin = cfg.get('mesh_origin', (0, 0))
            if isinstance(origin, str): origin = origin.split(',')
            x, y = map(finite, origin)
            count = int(cfg.get('round_probe_count', 5))
            low, high = (x-radius, y-radius), (x+radius, y+radius)
            counts = (count, count)
        else:
            def pair(key):
                raw = cfg[key]
                return raw.split(',') if isinstance(raw, str) else raw
            low, high = tuple(map(finite, pair('mesh_min'))), tuple(map(finite, pair('mesh_max')))
            counts = tuple(map(int, pair('probe_count')))
            if len(counts) == 1: counts *= 2
        if len(counts) != 2 or any(not 3 <= n <= 25 for n in counts):
            raise ValueError('Unsupported mesh dimensions')
        # Reuse the same validation for coordinate bounds.
        MeshData.parse('', [[0, 0], [0, 0]], low, high)
        return counts, low, high

    def start(self):
        self._guard(motion=True)
        config = self.printer.state.status.get('configfile', {})
        has_pending = config.get('save_config_pending') or config.get('save_config_pending_items')
        if has_pending and (self.epoch != self.printer.state.epoch
                or not self._owned_pending(config, self._calibrated_mesh)):
            raise ValueError('Resolve existing config changes first')
        try:
            self.layout = self._configured_layout()
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError('Check bed mesh configuration') from error
        profiles = self.printer.state.status.get('bed_mesh', {}).get('profiles', {})
        # A new session name avoids overwriting an existing user profile.
        index = 1
        while 'lcd_mesh_' + str(index) in profiles:
            index += 1
        if not has_pending:
            self.profile_name = 'lcd_mesh_' + str(index)
        self.mesh, self.status, self.progress = None, {}, {}
        self._cursor, _ = self.printer.subscription.responses_since(None)
        homed = self.printer.state.status['toolhead'].get('homed_axes', '')
        script = ('G28\n' if not all(a in homed for a in 'xyz') else '')
        script += 'BED_MESH_CALIBRATE PROFILE=' + self.profile_name + ' ADAPTIVE=0'
        self._submit('measuring', 'printer.gcode.script', {'script': script}, 'Probing bed...')

    def cancel(self):
        if self.phase != 'measuring' or not self.pending:
            raise ValueError('No measurement to stop')
        # G-code cancellation is queued behind probing. Emergency RPC is immediate.
        p = self.printer
        snapshot = p.subscription.snapshot()
        if (p.state.epoch != self.epoch or not p.state.ready or p.connection_error
                or snapshot['state'] != 'ready' or snapshot['epoch'] != self.epoch):
            raise ValueError('Printer connection changed')
        self.pending.cancel()
        self.mesh, self.progress = None, {}
        self._submit('stopping', 'printer.emergency_stop', {}, 'Stopping; Klipper shutdown')

    def save(self):
        self._guard(motion=True)
        if self.phase != 'complete' or self.mesh is None or self.epoch != self.printer.state.epoch:
            raise ValueError('No confirmed calibration to save')
        self._submit('save_check', 'printer.objects.query',
                     {'objects': {'bed_mesh': None, 'configfile': ['save_config_pending', 'save_config_pending_items']}},
                     'Checking profile before save...')

    def _owned_pending(self, config, mesh):
        """SAVE_CONFIG must contain only the exact profile measured here."""
        if mesh is None or mesh.name != self.profile_name or not config.get('save_config_pending'):
            return False
        try:
            items = config['save_config_pending_items']
            if set(items) != {'bed_mesh ' + self.profile_name}:
                return False
            fields = items['bed_mesh ' + self.profile_name]
            profile = self.status['profiles'][self.profile_name]
            expected_keys = {'version', 'points'} | set(profile['mesh_params'])
            if set(fields) != expected_keys or int(fields['version']) != 1:
                return False
            points = tuple(tuple(finite(z) for z in line.strip().rstrip(',').split(','))
                           for line in fields['points'].strip().splitlines() if line.strip())
            if len(points) != len(mesh.points) or any(len(a) != len(b) for a,b in zip(points,mesh.points)):
                return False
            if any(abs(a-b) > .000001 for row, measured in zip(points,mesh.points) for a,b in zip(row,measured)):
                return False
            for key, value in profile['mesh_params'].items():
                if isinstance(value, str):
                    if fields[key] != value: return False
                elif abs(finite(fields[key])-finite(value)) > .000001:
                    return False
            return True
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            return False

    def _progress(self):
        self._cursor, responses = self.printer.subscription.responses_since(self._cursor)
        counts, low, high = self.layout
        cfg = self.printer.state.settings
        probe = cfg.get('probe', cfg.get('bltouch', {}))
        offset = (finite(probe.get('x_offset', 0)), finite(probe.get('y_offset', 0)))
        for response in responses:
            for match in self.PROBE_RESPONSE.finditer(response):
                try:
                    x, y, z = map(finite, match.groups())
                    # Probe reports nozzle XY; grid is defined in probe coordinates.
                    pos = (x + offset[0], y + offset[1])
                    indices = tuple(round((pos[a]-low[a])/(high[a]-low[a])*(counts[a]-1)) for a in (0, 1))
                    expected = tuple(low[a]+indices[a]*(high[a]-low[a])/(counts[a]-1) for a in (0, 1))
                    if any(not 0 <= indices[a] < counts[a] or abs(pos[a]-expected[a]) > .1 for a in (0, 1)):
                        continue
                    self.progress[indices] = z
                    self.message = 'Probing: ' + str(len(self.progress)) + ' points'
                    self.revision += 1
                except (ValueError, OverflowError):
                    continue

    def _fail(self, message, phase='error'):
        if self.pending:
            self.pending.cancel()
        self.pending, self.mesh, self.status = None, None, {}
        self.progress = {}
        self.phase, self.message = phase, message
        self.revision += 1

    def update(self):
        if self.epoch is None:
            return
        p = self.printer
        if not p.state.ready or p.connection_error or p.state.epoch != self.epoch:
            if self.phase == 'saving':
                self._fail('Save requested; check after restart', 'interrupted')
            elif self.phase == 'stopping':
                self._fail('Stop unconfirmed; check printer', 'interrupted')
            elif self.phase != 'interrupted':
                self._fail('Connection changed; check printer', 'interrupted')
            return
        if not self.pending:
            return
        if time.monotonic() - self.started > self.TIMEOUT:
            self._fail('Timed out; check printer')
            return
        if self.phase == 'measuring':
            try:
                self._progress()
            except (TypeError, ValueError, OverflowError):
                self._fail('Invalid probe progress; check config')
                return
        if not self.pending.done():
            return
        try:
            result = self.pending.result()
            phase = self.phase
            self.pending = None
            if phase == 'measuring':
                self._submit('reading', 'printer.objects.query', {'objects': {'bed_mesh': None}}, 'Reading measured mesh...')
                return
            if phase in ('reading', 'profiles'):
                status = result['status']['bed_mesh']
                if not isinstance(status.get('profiles', {}), Mapping) or any(not isinstance(n, str) for n in status.get('profiles', {})):
                    raise ValueError('Invalid profiles')
                self.status = copy.deepcopy(status)
                if phase == 'reading':
                    mesh = MeshData.current(status)
                    if mesh.name != self.profile_name or MeshData.profile(self.profile_name, status) != mesh:
                        raise ValueError('Unconfirmed calibration')
                    self.mesh = self._calibrated_mesh = mesh
                    self.phase, self.message = 'complete', ''
                else:
                    self.phase, self.message = 'listed', ''
            elif phase == 'save_check':
                status = result['status']
                current = MeshData.current(status['bed_mesh'])
                profile = MeshData.profile(self.profile_name, status['bed_mesh'])
                config = status['configfile']
                if current != self.mesh or profile != self.mesh or not self._owned_pending(config, self.mesh):
                    raise ValueError('Resolve other config changes first')
                expected_mesh, name = self.mesh, self.profile_name
                def verify(live):
                    return (MeshData.current(live['bed_mesh']) == expected_mesh
                            and MeshData.profile(name, live['bed_mesh']) == expected_mesh)
                guard = config_save_guard(p, config, 'bed_mesh', verify)
                self._submit('saving', 'printer.gcode.script', {'script': 'SAVE_CONFIG'},
                             'Saving; Klipper restarts', dispatch_guard=guard)
                return
            elif phase == 'saving':
                self.phase, self.message = 'saved', 'Save requested; Klipper restarts'
            elif phase == 'stopping':
                self._fail('Stopped; Klipper shutdown', 'stopped')
                return
            self.revision += 1
        except Exception:
            message = ('Save unconfirmed; check after restart' if self.phase == 'saving'
                       else 'Stop unconfirmed; check printer' if self.phase == 'stopping'
                       else 'Mesh operation failed; check log')
            self._fail(message)
