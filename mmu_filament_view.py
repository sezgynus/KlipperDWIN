"""Incremental LCD adaptation of Mainsail's vertical Happy Hare filament view."""
import time


def filament_color(value, fallback=0x8410):
    value = str(value).lstrip('#')
    if len(value) == 8:
        value = value[:6]
    if len(value) != 6:
        return fallback
    try:
        rgb = int(value, 16)
    except ValueError:
        return fallback
    return ((rgb >> 19) << 11) | (((rgb >> 10) & 63) << 5) | ((rgb >> 3) & 31)


def filament_height(m):
    """Mainsail positions relative to the top of its filament tube (371px)."""
    pos = m.filament_pos
    if pos is None:
        pos = 10 if m.filament == 'loaded' else 0 if m.filament == 'unloaded' else -1
    if m.gate == -2:
        if pos in (7, 8, 9, 10):
            return {7: 315, 8: 325, 9: 338, 10: 371}[pos]
        return (325 if m.sensor('toolhead') is True else 295 if m.sensor('extruder') is True
                else 70 if m.sensor('mmu_gear') is True else 40 if m.sensor('mmu_pre_gate') is True else 20)
    if pos == 0:
        return 70 if m.sensor('mmu_gear') is True else 40 if m.sensor('mmu_pre_gate') is True else 20
    if pos == 1:
        return {'mmu_gear': 55, 'mmu_gate': 85, 'mmu_shared_exit': 85, 'extruder': 295}.get(m.gate_homing_endstop, 100)
    end = (290 if isinstance(m.sensor('toolhead'), bool) and not m.extruder_force_homing else
           308 if m.extruder_homing_endstop in ('none', 'collision', 'mmu_gear_touch', 'filament_compression') else
           295 if m.extruder_homing_endstop == 'extruder' else 290)
    if pos in (2, 3) and m.bowden_progress is not None:
        return 135 + (end - 135) * m.bowden_progress / 100
    if pos == 4:
        return end
    if pos == 9:
        return 315 if m.sensor('toolhead') is False else 338
    return {2: 135, 3: 221, 5: 295, 6: 308, 7: 315, 8: 325, 10: 371}.get(pos, 8)


class MMUFilamentView:
    BG = 0x2125
    BLOCK = 0x39C8
    TUBE = 0x8471
    X = 59
    TOP = 168
    BODY = 186
    GATE_HEIGHT = round(85 * (BODY - 1) / 371)
    GATE_Y = TOP + GATE_HEIGHT

    def __init__(self, lcd):
        self.lcd = lcd
        self._painted = {}
        self._target = self._from = None
        self._changed = 0

    def animating(self, state, now=None):
        now = time.monotonic() if now is None else now
        if state.action in ('Forming Tip', 'Purging', 'Cutting Tip', 'Cutting Filament'):
            return True
        return (self._target is not None and self._from is not None
                and self._target != self._from and now - self._changed < .5)

    def _rect(self, color, x0, y0, x1, y1):
        if x0 <= x1 and y0 <= y1:
            self.lcd.draw_rectangle(1, color, x0, y0, x1, y1)

    def _tube_segment(self, start, end, color):
        self._rect(color, self.X + 1, self.TOP + start, self.X + 8, self.TOP + end - 1)

    def _height_at(self, now):
        fraction = min(1, max(0, (now - self._changed) / .5))
        return self._from + (self._target - self._from) * fraction

    def draw(self, m, now=None, active_color=None):
        now = time.monotonic() if now is None else now
        before = self._painted.copy()
        if not self._painted:
            self._rect(self.BLOCK, 12, 176, 145, 244)
            self._rect(self.BLOCK, 12, 340, 145, 373)
            self._rect(self.TUBE, self.X, self.TOP, self.X + 9, self.TOP + self.BODY - 1)
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0xFFFF, self.BLOCK, 84, self.GATE_Y - 6, 'Gate')
        color = filament_color(m.colors[m.gate]) if m.gate is not None and 0 <= m.gate < m.num_gates else 0x8410
        if active_color is not None:
            color = active_color
        target = max(0, min(self.BODY - 1, round(filament_height(m) * (self.BODY - 1) / 371)))
        if self._target is None:
            self._target = self._from = target
        elif target != self._target:
            self._from = self._height_at(now)
            self._target, self._changed = target, now
        height = round(self._height_at(now))
        # A triggered sensor confirms that filament has already reached Gate.
        if m.gate != -2 and m.sensor('mmu_gate') is True:
            height = max(height, self.GATE_HEIGHT)
        if m.action == 'Forming Tip':
            height = round((338 if int(now * 2) % 2 else 371) * (self.BODY - 1) / 371)
        previous = self._painted.get('height', 0)
        color_changed = self._painted.get('color') != color
        if color_changed:
            self._tube_segment(0, height, color)
        elif height > previous:
            self._tube_segment(previous, height, color)
        if height < previous:
            self._tube_segment(height, previous, self.TUBE)
        self._painted.update(height=height, color=color)

        residual_color = filament_color(m.filament_remaining_color, color)
        upper = residual_color if m.filament_remaining > 0 else color if m.filament_pos == 10 or m.filament == 'loaded' else self.TUBE
        if self._painted.get('residue') != upper or height != previous or color_changed:
            # A separate nozzle region retains the old material after withdrawal.
            if m.filament_remaining > 0:
                self._tube_segment(self.BODY - 8, self.BODY, upper)
            else:
                self._tube_segment(self.BODY - 8, self.BODY, self.TUBE)
                self._tube_segment(self.BODY - 8, min(height, self.BODY), color)
            self._painted['residue'] = upper
        loaded = m.filament_pos == 10 or m.filament == 'loaded'
        tip = residual_color if m.filament_remaining > 0 or m.filament_remaining_color else color if loaded else self.TUBE
        if self._painted.get('tip') != tip:
            # Fill only within the pointed tube, never below its outline.
            for row in range(5):
                inset = row
                self._rect(tip, self.X + inset, self.TOP + self.BODY + row,
                           self.X + 9 - inset, self.TOP + self.BODY + row)
            self._painted['tip'] = tip

        sensor = m.sensor('mmu_gate')
        signature = (sensor, m.gate == -2)
        if self._painted.get('sensor') != signature:
            self._rect(self.BLOCK, 69, self.GATE_Y - 7, 81, self.GATE_Y + 7)
            if m.gate != -2:
                self.lcd.fill_circle(0x07E0 if sensor is True else self.BLOCK, 75, self.GATE_Y, 5)
                self.lcd.draw_circle(0x07E0 if sensor is not None else 0x8410, 75, self.GATE_Y, 5)
            self._painted['sensor'] = signature

        purge_frame = int(now * 2) % 8 if m.action == 'Purging' else -1
        signature = (purge_frame, tip)
        if self._painted.get('purge') != signature:
            self._rect(self.BLOCK, 52, 359, 76, 373)
            self._rect(self.BG, 52, 374, 76, 389)
            if purge_frame >= 1:
                self.lcd.fill_circle(tip, 64, 363 + purge_frame, min(6, purge_frame))
            self._painted['purge'] = signature

        cut = (m.action, int(now) % 2) if m.action in ('Cutting Tip', 'Cutting Filament') else None
        if self._painted.get('cut') != cut:
            self._rect(self.BLOCK, 35, 220, 54, 234)
            self._rect(self.BG, 35, 336, 54, 339)
            self._rect(self.BLOCK, 35, 340, 54, 350)
            if cut:
                y = 220 if m.action == 'Cutting Filament' else 336
                self.lcd.draw_circle(0xFFFF, 39, y + 3, 2)
                self.lcd.draw_circle(0xFFFF, 39, y + 11, 2)
                delta = 2 if cut[1] else 0
                self.lcd.draw_line(0xFFFF, 41, y + 3, 54, y + 11 - delta)
                self.lcd.draw_line(0xFFFF, 41, y + 11, 54, y + 3 + delta)
            self._painted['cut'] = cut

        return before != self._painted
