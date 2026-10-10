"""Four-corner screws tilt session using authoritative Klipper RPC results."""
from operation_guards import motion_dispatch_guard
import math
import re
import time


class ScrewsTiltSession:
    TOLERANCE = .05  # mm, same peak-to-peak criterion as the reference UI
    TIMEOUT = 600

    def __init__(self, printer):
        self.printer = printer
        self.phase = 'idle'
        self.message = ''
        self.pending = None
        self.epoch = None
        self.corners = ()
        self.results = {}
        self.recommendation = None
        self.leveled = False

    def _layout(self):
        settings = self.printer.state.settings.get('screws_tilt_adjust', {})
        keys = sorted((key for key in settings if re.fullmatch(r'screw\d+', key)),
                      key=lambda key: int(key[5:]))
        if keys != ['screw1', 'screw2', 'screw3', 'screw4']:
            raise ValueError('Four configured screws required')
        points = []
        for key in keys:
            raw = settings[key]
            if isinstance(raw, str):
                raw = raw.split(',')
            x, y = map(float, raw)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('Invalid screw coordinates')
            points.append((key, x, y))
        front = sorted(sorted(points, key=lambda p: p[2])[:2], key=lambda p: p[1])
        back = sorted(sorted(points, key=lambda p: p[2])[2:], key=lambda p: p[1])
        if (max(p[2] for p in front) >= min(p[2] for p in back)
                or front[0][1] >= front[1][1] or back[0][1] >= back[1][1]):
            raise ValueError('Four distinct corner positions required')
        return ((front[0][0], 25, 277, 'Front Left'),
                (front[1][0], 247, 277, 'Front Right'),
                (back[1][0], 247, 55, 'Back Right'),
                (back[0][0], 25, 55, 'Back Left'))

    def start(self):
        p = self.printer
        if self.pending:
            raise ValueError('Calculation already running')
        if (not p.state.ready or p.connection_error or not p.capabilities.screws_tilt_adjust
                or not p.capabilities.probe
                or p.jog_recovery_required or p.bed_mesh.pending
                or getattr(getattr(p, 'mmu_session', None), 'pending', None)):
            raise ValueError('Screws tilt unavailable; check printer')
        if p.status in ('printing', 'paused', 'pausing'):
            raise ValueError('Calibration unavailable during print')
        if p.state.status.get('manual_probe', {}).get('is_active'):
            raise ValueError('Another manual probe is active')
        try:
            corners = self._layout()
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError('Check four-corner screw configuration') from error
        snapshot = p.subscription.snapshot()
        if snapshot['state'] != 'ready' or snapshot['epoch'] != p.state.epoch:
            raise ValueError('Printer connection changed')
        # Reference firmware homes missing axes before probing. No SAVE_CONFIG.
        homed = p.state.status['toolhead'].get('homed_axes', '')
        script = ('G28\n' if not all(a in homed for a in 'xyz') else '') + 'SCREWS_TILT_CALCULATE'
        self.epoch = p.state.epoch
        self.corners = corners
        self.results = {}
        self.recommendation = None
        self.leveled = False
        self.phase, self.message = 'measuring', 'Probing corners...'
        self.started = time.monotonic()
        guard = motion_dispatch_guard(p, owner='screws_tilt')
        self.pending = p.subscription.request('printer.gcode.script', {'script': script}, guard=guard)

    def _read_results(self, payload):
        raw = payload['status']['screws_tilt_adjust']['results']
        expected = {corner[0] for corner in self.corners}
        if set(raw) != expected:
            raise ValueError('Incomplete screw results')
        results = {}
        for key, value in raw.items():
            z = float(value['z'])
            adjust = value['adjust']
            if not math.isfinite(z) or not isinstance(adjust, str) or not re.fullmatch(r'\d+:\d{2}', adjust):
                raise ValueError('Invalid screw result')
            turns, minutes = map(int, adjust.split(':'))
            # Klipper may round 59.5 minutes to 60; normalize the displayed value.
            if minutes > 60 or value['sign'] not in ('CW', 'CCW') or type(value['is_base']) is not bool:
                raise ValueError('Invalid screw result')
            total = turns * 60 + minutes
            results[key] = dict(z=z, sign=value['sign'], is_base=value['is_base'],
                                minutes=total, adjust=f'{total // 60:02d}:{total % 60:02d}')
        bases = [v for v in results.values() if v['is_base']]
        if len(bases) != 1 or bases[0]['minutes'] != 0:
            raise ValueError('Invalid reference screw')
        self.results = results
        heights = [v['z'] for v in results.values()]
        self.leveled = max(heights) - min(heights) < self.TOLERANCE
        candidates = sorted((key for key in expected if not results[key]['is_base']),
                            key=lambda key: int(key[5:]))
        self.recommendation = max(candidates, key=lambda key: results[key]['minutes'])

    def update(self):
        p = self.printer
        if self.epoch is None:
            return
        if not p.state.ready or p.connection_error or p.state.epoch != self.epoch:
            if self.pending:
                self.pending.cancel()
            self.pending = None
            self.results = {}
            self.phase, self.message = 'interrupted', 'Connection changed'
            return
        if not self.pending:
            return
        if time.monotonic() - self.started > self.TIMEOUT:
            self.pending.cancel()
            self.pending = None
            self.results = {}
            self.phase, self.message = 'error', 'Check printer; timed out'
            return
        if not self.pending.done():
            return
        try:
            payload = self.pending.result()
            if self.phase == 'measuring':
                # Query after completion, including identical repeated measurements.
                self.pending = p.subscription.request('printer.objects.query',
                    {'objects': {'screws_tilt_adjust': None}})
                self.phase, self.message = 'reading', 'Reading results...'
                return
            self._read_results(payload)
            self.phase, self.message = 'complete', ''
        except Exception:
            self.results = {}
            self.phase, self.message = 'error', 'Calculation failed; check log'
        self.pending = None
