"""MMU menu and Happy Hare home-screen rendering mixin."""

from lcd_atlas import ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED

class MMUViewMixin:
    def Draw_MMU_Home_Icon(self, x, y, selected):
        icon_id = ICON_MMU_HOME_SELECTED if selected else ICON_MMU_HOME_NORMAL
        self.lcd.draw_atlas_icon(icon_id, x + 16, y + 16)

    @staticmethod
    def _rgb565(rgb):
        r, g, b = (int(round(max(0.0, min(1.0, value)) * 31)) for value in rgb)
        # Green has 6 bits in RGB565.
        g = int(round(max(0.0, min(1.0, rgb[1])) * 63))
        return (r << 11) | (g << 5) | b

    def Draw_MMU_Status(self):
        mmu = self.pd.mmu
        if not mmu:
            return
        count = mmu['num_gates']
        active = mmu['gate']
        # Fill nearly the entire strip above the main menu icons.
        left, top, width = 8, 39, 256
        gap = 5 if count <= 4 else 2 if count <= 8 else 1
        if count > 32:
            gap = 0
        slot = max(1, min(60, (width - gap * (count - 1)) // count))
        total = slot * count + gap * (count - 1)
        start = left + max(0, (width - total) // 2)
        title = str(mmu.get('name') or 'MMU')[:22]
        title_x = max(4, (self.lcd.DWIN_WIDTH - 6 * len(title)) // 2)
        self.lcd.draw_text(False, True, self.lcd.font6x12,
                             self.lcd.Color_White, self.lcd.Color_Bg_Black,
                             title_x, 32, title)

        percentages = mmu.get('remaining_percent', ())
        for gate in range(count):
            x = start + gate * (slot + gap)
            status = mmu['gate_status'][gate]
            color = self._rgb565(mmu['gate_color_rgb'][gate]) if status > 0 else 0x8410
            cx = x + slot // 2
            flange = 0x9B46
            flange_edge = 0xD58A
            # Keep lane spacing unchanged, but narrow the reel itself so its
            # height-to-width ratio resembles a physical filament spool.
            reel_w = min(max(8, int(slot * 0.70)), max(1, slot - 2))
            reel_x = x + (slot - reel_w) // 2
            flange_w = max(1, min(max(2, reel_w // 9), max(1, (reel_w - 2) // 2)))
            body_left = reel_x + flange_w
            body_right = reel_x + reel_w - flange_w - 1
            y0, y1 = top + 13, top + 52

            # Warm cardboard/wood flanges stand out against the black UI.
            self.lcd.draw_rectangle(1, flange, reel_x + 1, top + 7,
                                    reel_x + flange_w, top + 58)
            self.lcd.draw_rectangle(0, flange_edge, reel_x + 1, top + 7,
                                    reel_x + flange_w, top + 58)
            self.lcd.draw_rectangle(1, flange, reel_x + reel_w - flange_w - 1, top + 7,
                                    reel_x + reel_w - 2, top + 58)
            self.lcd.draw_rectangle(0, flange_edge, reel_x + reel_w - flange_w - 1, top + 7,
                                    reel_x + reel_w - 2, top + 58)
            self.lcd.draw_rectangle(1, color, body_left, y0, body_right, y1)

            winding = self.lcd.Color_White if sum(mmu['gate_color_rgb'][gate]) < 0.7 else flange
            for line_x in range(body_left + 5, body_right, 7):
                self.lcd.draw_line(winding, line_x, y0, line_x, y1)

            percent = percentages[gate] if gate < len(percentages) else None
            # Percent text needs enough horizontal room. Compact high-gate
            # layouts prioritize distinct lanes over overlapping text.
            if slot >= 28:
                pct = '--' if percent is None else '%d%%' % percent
                # Black backing keeps the percentage readable on white/yellow filament.
                pct_w = 6 * len(pct) + 4
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                        cx - pct_w // 2, top + 27,
                                        cx + pct_w // 2, top + 41)
                self.lcd.draw_text(False, True, self.lcd.font6x12,
                                     self.lcd.Color_White, self.lcd.Color_Bg_Black,
                                     cx - 3 * len(pct), top + 28, pct)

            label = str(gate + 1)
            label_w = max(1, min(38, slot - 2 if slot > 2 else slot))
            lx0, lx1 = cx - label_w // 2, cx + label_w // 2
            exit_leds = mmu.get('exit_led_rgb', ())
            led_color = None
            if gate < len(exit_leds):
                rgb = exit_leds[gate]
                peak = max(rgb)
                # Mirror the LED hue, not its physical brightness.  Happy Hare
                # may deliberately drive a color at low intensity (e.g. red
                # at 0.1), which is too dark on the LCD if copied literally.
                normalized_rgb = (tuple(channel / peak for channel in rgb)
                                  if peak > 0 else rgb)
                led_color = self._rgb565(normalized_rgb)
            active_green = 0x07E0
            indicator = led_color if led_color is not None else (
                active_green if gate == active else self.lcd.Line_Color)
            # Every lane mirrors its live Happy Hare exit LED continuously.
            # Black/off LEDs therefore render as black rather than falling back.
            label_bg = indicator
            border = indicator
            self.lcd.draw_rectangle(1, label_bg, lx0, top + 64, lx1, top + 78)
            self.lcd.draw_rectangle(0, border, lx0, top + 64, lx1, top + 78)
            # Choose black or white text for maximum contrast against
            # the live lane color.  This keeps bright green/yellow/cyan lane
            # numbers readable without sacrificing dark-color visibility.
            r5 = (label_bg >> 11) & 0x1F
            g6 = (label_bg >> 5) & 0x3F
            b5 = label_bg & 0x1F
            luminance = (299 * r5 * 255 // 31 +
                         587 * g6 * 255 // 63 +
                         114 * b5 * 255 // 31) // 1000
            label_fg = 0x0000 if luminance >= 140 else self.lcd.Color_White
            self.lcd.draw_text(False, True, self.lcd.font6x12,
                                 label_fg, label_bg,
                                 cx - 3 * len(label), top + 65, label)

    # Dedicated MMU pages own the complete 272x480 canvas. The home dashboard
    # above is intentionally independent and keeps its existing appearance.
    MMU_TITLES = {'home': 'MMU', 'gates': 'GATES', 'gate': 'GATE',
                  'filament': 'FILAMENT', 'map': 'TOOL MAP', 'manage': 'MANAGE',
                  'status': 'MMU STATUS', 'bypass': 'BYPASS', 'recover': 'RECOVER STATE',
                  'manual': 'SET MMU STATE', 'confirm': 'CONFIRM',
                  'endless': 'ENDLESS SPOOL', 'group': 'GROUP MEMBERS', 'spool': 'ASSIGN SPOOL',
                  'maintenance': 'MAINTENANCE', 'options': 'MMU OPTIONS',
                  'leds': 'MMU LEDS', 'units': 'MMU UNITS', 'unit': 'UNIT GATES'}

    def Enter_MMU_Menu(self, page='home'):
        self.checkkey = self.MMUMenu
        self._mmu_page = page
        self._mmu_selection = 1 if self.pd.mmu_session.state is not None else 0
        self._mmu_gate = 0
        self._mmu_history = []
        self._mmu_notice = ''
        self._mmu_edit = None
        self._mmu_map_draft = None
        self._mmu_endless_draft = None
        self._mmu_spool_draft = None
        self._mmu_unit_view = 0
        self._mmu_canvas_page = None
        self.Draw_MMU_Menu()

    def _mmu_open(self, page):
        self._mmu_edit = None
        if page == 'map':
            self._mmu_begin_map()
        if page == 'endless':
            self._mmu_begin_endless()
        if page == 'spool':
            self._mmu_begin_spool()
        self._mmu_history.append((self._mmu_page, self._mmu_selection))
        self._mmu_page, self._mmu_selection = page, 1
        self._mmu_notice = ''
        self.Draw_MMU_Menu()

    def _mmu_back(self):
        self._mmu_edit = None
        if self._mmu_page == 'map':
            self._mmu_map_draft = None
        if self._mmu_page == 'endless':
            self._mmu_endless_draft = None
        if self._mmu_page == 'spool':
            self._mmu_spool_draft = None
        if self._mmu_history:
            self._mmu_page, self._mmu_selection = self._mmu_history.pop()
            self._mmu_notice = ''
            self.Draw_MMU_Menu()
        elif self.pd.mmu_session.pending is not None:
            self._mmu_page, self._mmu_selection = 'status', 0
            self._mmu_notice = 'Wait for MMU operation'
            self.Draw_MMU_Menu()
        else:
            self._mmu_canvas_page = None
            self.Goto_MainMenu()
            self.Draw_Status_Area(False)
        self.lcd.update()

    def _mmu_text(self, key, value, x, y, cells=31, small=False, color=0xFFFF, bg=0x0000):
        value = str(value).replace('\n', ' ').replace('\r', ' ')
        value = value[:cells] if len(value) <= cells else value[:max(0, cells - 1)] + '~'
        width, height = (6, 12) if small else (8, 16)
        cells = min(cells, (272 - x) // width)
        value = value[:cells]
        signature = (value, x, y, cells, small, color, bg)
        if self._mmu_render.get(key) == signature:
            return
        self._mmu_render[key] = signature
        self.lcd.draw_rectangle(1, bg, x, y, min(271, x + cells * width - 1), y + height - 1)
        self.lcd.draw_text(False, False, self.lcd.font6x12 if small else self.lcd.font8x16,
                             color, bg, x, y, value)

    def _mmu_row(self, key, label, value, x, y, width, selected, enabled=True):
        label = str(label).replace('\n', ' ').replace('\r', ' ')
        value = str(value).replace('\n', ' ').replace('\r', ' ')
        signature = (label, value, selected, enabled, x, y, width)
        if self._mmu_render.get(key) == signature:
            return
        self._mmu_render[key] = signature
        bg = 0x33BD if selected else 0x18E4
        fg = 0xFFFF if enabled else 0x8410
        self.lcd.draw_rectangle(1, bg, x, y, x + width - 1, y + 39)
        if selected:
            self.lcd.draw_rectangle(0, 0xFFFF, x, y, x + width - 1, y + 39)
        cells = (width - 16) // 8
        value = str(value)[:max(0, cells - 3)]
        available = cells - (len(value) + 1 if value else 0)
        label = label[:available] if len(label) <= available else label[:max(0, available - 1)] + '~'
        self.lcd.draw_text(False, False, self.lcd.font8x16, fg, bg, x + 8, y + 12, label)
        if value:
            self.lcd.draw_text(False, False, self.lcd.font8x16, fg, bg,
                                 x + width - 8 - 8 * len(value), y + 12, value)

    @staticmethod
    def _mmu_gate_label(gate):
        return 'Bypass' if gate == -2 else 'G%d' % (gate + 1) if gate is not None and gate >= 0 else 'G?'

    @staticmethod
    def _mmu_tool_label(tool):
        return 'Bypass' if tool == -2 else 'T%d' % tool if tool is not None and tool >= 0 else 'T?'

    def _mmu_action_item(self, action, label, gate=None, desired_enabled=None):
        key = ('action', action, gate) if desired_enabled is None else ('action', action, gate, desired_enabled)
        try:
            self.pd.mmu_session.prepare(action, gate=gate, enabled=desired_enabled)
        except ValueError:
            return (key, label, 'LOCK', False)
        return (key, label, '>', True)

    def _mmu_begin_map(self):
        m = self.pd.mmu_session.state
        self._mmu_map_draft = list(m.ttg_map) if m else []
        self._mmu_map_base = m.fingerprint if m else None
        self._mmu_map_original = tuple(self._mmu_map_draft)

    def _mmu_map_writable(self, m):
        if m is None or m.fingerprint != getattr(self, '_mmu_map_base', None):
            return False
        try:
            self.pd.mmu_session.prepare('map', values=self._mmu_map_draft)
        except ValueError:
            return False
        return True

    def _mmu_begin_endless(self):
        m = self.pd.mmu_session.state
        self._mmu_endless_draft = {'enabled': m.endless_enabled if m else None,
                                   'groups': list(m.endless_groups) if m else []}
        self._mmu_endless_base = m.fingerprint if m else None
        self._mmu_endless_original = (self._mmu_endless_draft['enabled'], tuple(self._mmu_endless_draft['groups']))
        self._mmu_group = next((g for g in self._mmu_endless_draft['groups'] if g is not None), 0)

    def _mmu_endless_writable(self, m):
        if m is None or m.fingerprint != getattr(self, '_mmu_endless_base', None):
            return False
        draft = self._mmu_endless_draft
        try:
            self.pd.mmu_session.prepare('endless', values=draft['groups'], enabled=draft['enabled'])
        except ValueError:
            return False
        return True

    def _mmu_group_summary(self, group):
        gates = [self._mmu_gate_label(i) for i, g in enumerate(self._mmu_endless_draft['groups']) if g == group]
        return ' '.join(gates[:3]) + (' +%d' % (len(gates) - 3) if len(gates) > 3 else '')

    def _mmu_begin_spool(self):
        m = self.pd.mmu_session.state
        sid = m.spool_ids[self._mmu_gate] if m and self._mmu_gate < m.num_gates else None
        self._mmu_spool_draft = sid if sid is not None and sid > 0 else 1
        self._mmu_spool_original = sid
        self._mmu_spool_base = m.fingerprint if m else None

    def _mmu_spool_writable(self, m):
        if m is None or m.fingerprint != getattr(self, '_mmu_spool_base', None):
            return False
        try:
            self.pd.mmu_session.prepare('spool', gate=self._mmu_gate, values=(self._mmu_spool_draft,))
        except ValueError:
            return False
        return True

    def _mmu_items(self, m):
        page = self._mmu_page
        nav = lambda key, label: (('page', key), label, '>', True)
        if page == 'confirm':
            return [(('cancel',), 'Cancel', '', True),
                    (('execute',), 'Confirm', '', self._mmu_confirmation_valid())]
        if page == 'home':
            current = m.gate if m and m.gate is not None and m.gate >= 0 else None
            primary = ('unload', 'Unload') if m and m.filament == 'loaded' else ('load', 'Load')
            return [nav('gates', 'Gates'), self._mmu_action_item(*primary, gate=current),
                    nav('map', 'Tool map'), nav('bypass', 'Bypass'),
                    nav('manage', 'Manage'), nav('status', 'Status')]
        if page == 'gates':
            if not m:
                return []
            return [(('gate', gate), '%s %s' % (self._mmu_gate_label(gate), m.materials[gate] or '--'),
                     self._mmu_percent(gate), True) for gate in range(m.num_gates)]
        if page == 'gate':
            gate = self._mmu_gate
            return [self._mmu_action_item(action, label, gate) for action, label in
                    [('select', 'Select only'), ('load', 'Load selected'), ('change', 'Load / change'),
                     ('unload', 'Unload'), ('eject', 'Eject spool'), ('preload', 'Preload'), ('check', 'Check')]] + [nav('filament', 'Filament details')]
        if page == 'bypass':
            current = m.gate if m and m.gate is not None and m.gate >= 0 else None
            return [self._mmu_action_item('unload', 'Unload current gate', current),
                    self._mmu_action_item('bypass', 'Select bypass'),
                    self._mmu_action_item('load_extruder', 'Load extruder'),
                    self._mmu_action_item('unload_extruder', 'Unload extruder')]
        if page == 'manage':
            return [nav('recover', 'Recover state'), nav('status', 'Sensors / status'),
                    nav('bypass', 'Extruder / bypass'), (('web',), 'Calibration', 'WEB', False),
                    nav('maintenance', 'Maintenance'), nav('options', 'Options')]
        if page == 'maintenance':
            items = [self._mmu_action_item('check_all', 'Check all gates')]
            unit = m.active_unit if m else None
            session = self.pd.mmu_session
            if unit and len(m.units) == 1 and unit.selector_type in session.HOME_SELECTORS:
                items.insert(0, self._mmu_action_item('home_selector', 'Home selector'))
            if unit and unit.selector_type in session.GRIP_SELECTORS:
                items += [self._mmu_action_item('grip', 'Grip')]
                if unit.always_gripped is False:
                    items += [self._mmu_action_item('release', 'Release')]
            return items + [nav('bypass', 'Extruder / bypass')]
        if page == 'options':
            unit = m.active_unit if m else None
            desired = not m.enabled if m and m.enabled is not None else None
            label = 'MMU enable / disable' if desired is None else 'Enable MMU' if desired else 'Disable MMU'
            items = [self._mmu_action_item('enable', label, desired_enabled=desired)]
            if unit and unit.always_gripped is not None:
                items.append(self._mmu_action_item('sync_on', 'Gear sync ON'))
                if not unit.always_gripped:
                    items.append(self._mmu_action_item('sync_off', 'Gear sync OFF'))
            if m and m.motors and all(v is not None for _, v in m.motors):
                items.append(self._mmu_action_item('motors_off', 'Release MMU motors'))
            if m and m.leds is not None:
                items.append(nav('leds', 'LEDs'))
            if m and len(m.units) > 1:
                items.append(nav('units', 'Units'))
            return items + [nav('status', 'Sensors / status')]
        if page == 'units':
            return [(('unit', i), 'U%d %s' % (i + 1, unit.name),
                     'G%d-G%d%s' % (unit.first_gate + 1, unit.first_gate + unit.num_gates,
                                     ' ACTIVE' if m.unit == i else ''), True)
                    for i, unit in enumerate(m.units if m else ())]
        if page == 'unit':
            index = getattr(self, '_mmu_unit_view', 0)
            if not m or not 0 <= index < len(m.units):
                return []
            unit = m.units[index]
            try:
                self.pd.mmu_session.prepare('unit_select', values=(index,))
                enabled = True
            except ValueError:
                enabled = False
            return [(('unit_select', index, unit.first_gate), 'Select this unit', '>' if enabled else 'LOCK', enabled)] + [
                (('gate', gate), '%s %s' % (self._mmu_gate_label(gate), m.materials[gate] or '--'),
                 self._mmu_percent(gate), True) for gate in range(unit.first_gate, unit.first_gate + unit.num_gates)]
        if page == 'leds':
            if not m or not m.leds:
                return []
            leds = m.leds
            items = [self._mmu_action_item('led_enable', 'LEDs OFF' if leds.enabled else 'LEDs ON', desired_enabled=not leds.enabled if leds.enabled is not None else None),
                     self._mmu_action_item('led_animation', 'Animation OFF' if leds.animation else 'Animation ON', desired_enabled=not leds.animation if leds.animation is not None else None)]
            if leds.segments[0]:
                for mode in self.pd.mmu_session.LED_MODES:
                    try:
                        self.pd.mmu_session.prepare('led_mode', values=(mode,))
                        enabled = True
                    except ValueError:
                        enabled = False
                    items.append((('led_mode', mode), mode.replace('_', ' ').title(), '>' if enabled else 'LOCK', enabled))
            return items
        if page == 'filament':
            return [nav('spool', 'Assign spool ID')]
        if page == 'spool':
            writable = self._mmu_spool_writable(m)
            return [(('spool_edit',), 'Spool ID', '#%d' % self._mmu_spool_draft, writable),
                    (('spool_save',), 'Save', '>' if writable else 'LOCK',
                     writable and self._mmu_spool_draft != self._mmu_spool_original),
                    (('spool_clear',), 'Clear assignment', '>', writable and self._mmu_spool_original is not None and self._mmu_spool_original > 0),
                    (('cancel',), 'Cancel', '', True)]
        if page == 'recover':
            return [self._mmu_action_item('recover', 'Auto recover'), nav('manual', 'Set state manually'),
                    self._mmu_action_item('unlock', 'Unlock / reheat'),
                    self._mmu_action_item('resume', 'Resume print')]
        if page == 'map':
            draft = self._mmu_map_draft
            writable = self._mmu_map_writable(m)
            return [(('map_edit', tool), 'T%d' % tool, self._mmu_gate_label(gate), writable)
                    for tool, gate in enumerate(draft)] + [
                        nav('endless', 'EndlessSpool'),
                        (('map_save',), 'Save', '>' if writable else 'LOCK',
                         writable and tuple(draft) != self._mmu_map_original),
                        (('cancel',), 'Cancel', '', True)]
        if page in ('endless', 'group'):
            draft = self._mmu_endless_draft
            writable = self._mmu_endless_writable(m)
            groups = draft['groups']
            if page == 'group':
                return [(('member', gate), '%s %s %s' % (self._mmu_gate_label(gate),
                         (m.materials[gate] or '--') if m and gate < m.num_gates else '--',
                         (m.colors[gate] or '--') if m and gate < m.num_gates else '--'),
                         'IN' if group == self._mmu_group else 'OUT', writable)
                        for gate, group in enumerate(groups)] + [(('cancel',), 'Back', '', True)]
            ids = sorted({g for g in groups if g is not None})
            changed = (draft['enabled'], tuple(groups)) != self._mmu_endless_original
            return [(('endless_toggle',), 'Enabled', {True: 'ON', False: 'OFF', None: '--'}[draft['enabled']], writable)] + [
                (('group', group), 'Group %d' % (i + 1), self._mmu_group_summary(group), True)
                for i, group in enumerate(ids)] + [
                (('endless_save',), 'Save', '>' if writable else 'LOCK', writable and changed),
                (('cancel',), 'Cancel', '', True)]
        if page == 'manual':
            draft = self._mmu_manual
            return [(('edit', 'tool'), 'Tool', self._mmu_tool_label(draft['tool']), True),
                    (('edit', 'gate'), 'Gate', self._mmu_gate_label(draft['gate']), True),
                    (('edit', 'loaded'), 'Filament', 'LOADED' if draft['loaded'] else 'UNLOADED', True),
                    (('apply',), 'Apply', '>', m is not None), (('cancel',), 'Cancel', '', True)]
        if page == 'status':
            if self.pd.mmu_session.phase == 'error':
                return [(('ack',), 'Acknowledge', '', True), nav('recover', 'Recover state')]
            return []
        return []

    def _mmu_percent(self, gate):
        percentages = (self.pd.mmu or {}).get('remaining_percent', ())
        value = percentages[gate] if gate < len(percentages) else None
        return '--' if value is None else '%d%%' % value

    def _mmu_spools(self, m):
        count = min(4, m.num_gates)
        start = (max(0, m.gate) // 4) * 4 if m.gate is not None and m.gate >= 0 else 0
        start = min(start, ((m.num_gates - 1) // 4) * 4)
        home = self.pd.mmu or {}
        colors = home.get('gate_color_rgb', ())
        signature = (start, m.gate, m.gate_status, m.ttg_map, colors, home.get('remaining_percent', ()))
        if self._mmu_render.get('spools') == signature:
            return
        self._mmu_render['spools'] = signature
        self.lcd.draw_rectangle(1, 0x0000, 8, 59, 263, 164)
        for slot, gate in enumerate(range(start, min(m.num_gates, start + count))):
            x = 14 + slot * 66
            rgb = colors[gate] if gate < len(colors) else (0.5, 0.5, 0.5)
            color = self._rgb565(rgb) if m.gate_status[gate] in (1, 2) else 0x8410
            tools = m.tools_for_gate(gate)
            label = 'T%d' % tools[0] if len(tools) == 1 else 'T*' if tools else '--'
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0xFFFF, 0x0000, x + 6, 61, label)
            self.lcd.draw_rectangle(1, color, x + 6, 85, x + 35, 123)
            for fx in (x, x + 36):
                self.lcd.draw_rectangle(1, 0x9B46, fx, 79, fx + 5, 129)
            percent = self._mmu_percent(gate)
            self.lcd.draw_rectangle(1, 0x0000, x + 3, 99, x + 38, 113)
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0xFFFF, 0x0000, x + 6, 100, percent)
            bg = 0x07E0 if gate == m.gate else 0x18E4
            self.lcd.draw_rectangle(1, bg, x, 138, x + 41, 158)
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0x0000 if bg == 0x07E0 else 0xFFFF,
                                 bg, x + 12, 142, 'G%d' % (gate + 1))
        if m.num_gates > 4:
            self._mmu_render.pop('gatepage', None)
            self._mmu_text('gatepage', '%d/%d' % (start // 4 + 1, (m.num_gates + 3) // 4), 218, 165, 8, small=True)

    def _mmu_nozzle(self, y):
        temps = self.pd.thermalManager['temp_hotend'][0]
        value = 'Nozzle %d/%d C' % (temps['celsius'], temps['target']) if self.pd.HAS_HOTEND else 'Nozzle unavailable'
        self._mmu_text('nozzle', value, 12, y)

    def _mmu_path(self, m, y):
        signature = (m.filament, y)
        if self._mmu_render.get('path') == signature:
            return
        self._mmu_render['path'] = signature
        self.lcd.draw_rectangle(1, 0x0000, 12, y, 259, y + 40)
        color = 0x249F if m.filament == 'loaded' else 0x8410
        for x, name in ((14, 'GATE'), (82, 'BOWDEN'), (200, 'NOZZLE')):
            self.lcd.draw_text(False, False, self.lcd.font6x12, 0x8410, 0x0000, x, y, name)
        self.lcd.draw_line(color, 30, y + 24, 233, y + 24)
        for x in (26, 106, 229):
            self.lcd.draw_rectangle(1, color, x, y + 20, x + 7, y + 27)

    def _mmu_confirmation_valid(self):
        op = getattr(self, '_mmu_confirmation', None)
        if op is None:
            return False
        try:
            return self.pd.mmu_session.prepare(op.action, op.gate, op.tool, op.loaded,
                                               values=op.values, enabled=op.enabled) == op
        except ValueError:
            return False

    def Draw_MMU_Menu(self):
        if not hasattr(self, '_mmu_page'):
            self._mmu_page, self._mmu_selection = 'home', 0
            self._mmu_gate, self._mmu_history, self._mmu_notice = 0, [], ''
        page = self._mmu_page
        m = self.pd.mmu_session.state
        if getattr(self, '_mmu_canvas_page', None) != page:
            self.lcd.draw_rectangle(1, 0x0000, 0, 0, 271, 479)
            self.lcd.draw_rectangle(1, 0x1105, 0, 0, 271, 29)
            self._mmu_canvas_page, self._mmu_render = page, {}
            self._draw_power_icon(getattr(self, '_power_focus', False))
        if page == 'map' and getattr(self, '_mmu_map_draft', None) is None:
            self._mmu_begin_map()
        if page in ('endless', 'group') and getattr(self, '_mmu_endless_draft', None) is None:
            self._mmu_begin_endless()
        if page == 'spool' and getattr(self, '_mmu_spool_draft', None) is None:
            self._mmu_begin_spool()
        if page == 'manual' and not hasattr(self, '_mmu_manual'):
            self._mmu_manual_base = m.fingerprint if m else None
            self._mmu_manual = {'tool': m.tool if m and m.tool is not None and m.tool >= 0 else 0,
                                'gate': m.gate if m and m.gate is not None and m.gate >= 0 else 0,
                                'loaded': bool(m and m.filament == 'loaded')}
        items = self._mmu_items(m)
        self._mmu_drawn_keys = tuple(item[0] for item in items)
        self._mmu_selection = min(self._mmu_selection, len(items))
        self._mmu_text('back', '<', 8, 5, 2, bg=0x33BD if self._mmu_selection == 0 else 0x1105)
        title = self.MMU_TITLES[page]
        if page in ('gate', 'filament', 'spool'):
            title += ' / ' + self._mmu_gate_label(self._mmu_gate)
        self._mmu_text('title', title, 34, 5, 25, bg=0x1105)
        connection = 'OFFLINE' if self.pd.connection_error else 'MMU unavailable' if not m else (
            'MMU DISABLED' if m.enabled is not True else m.action.upper())
        self._mmu_text('connection', connection, 10, 36, 42, small=True,
                       color=0xFD20 if not m or m.enabled is not True else 0x8410)
        first_y, visible = 67, 8
        if page == 'home':
            if m:
                self._mmu_spools(m)
                self._mmu_text('active', '%s > %s  %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate), m.filament.upper()), 12, 182, color=0x07E0)
                self._mmu_path(m, 209)
                self._mmu_nozzle(253)
            else:
                self._mmu_text('unavailable', 'Happy Hare unavailable', 12, 100)
                self._mmu_text('hint', 'Check MMU / Moonraker', 12, 126)
            for i, (_, label, _, enabled) in enumerate(items):
                self._mmu_row('item%d' % i, label, '', 8 + (i % 2) * 132,
                              283 + (i // 2) * 54, 124, self._mmu_selection == i + 1, enabled)
            self._mmu_text('notice', self._mmu_notice, 10, 438, 42, small=True, color=0xFD20)
            first_y = None
        elif page == 'gate':
            gate = self._mmu_gate
            if m and gate < m.num_gates:
                tools = ','.join('T%d' % t for t in m.tools_for_gate(gate)) or 'Unmapped'
                self._mmu_text('summary', tools + ' / ' + (m.materials[gate] or '--'), 12, 68)
                state = m.filament.upper() if gate == m.gate else {-1: 'UNKNOWN', 0: 'EMPTY', 1: 'AVAILABLE', 2: 'BUFFERED'}.get(m.gate_status[gate], 'UNKNOWN')
                self._mmu_text('gatestate', state + ' / ' + self._mmu_percent(gate), 12, 98)
            first_y, visible = 132, 7
        elif page == 'filament':
            gate = self._mmu_gate
            if m and gate < m.num_gates:
                for i, (label, value) in enumerate((('Name', m.names[gate]), ('Material', m.materials[gate]),
                        ('Color', m.colors[gate]),
                        ('Spool ID', '#%s' % m.spool_ids[gate] if m.spool_ids[gate] and m.spool_ids[gate] > 0 else '--'),
                        ('Remaining', self._mmu_percent(gate)), ('Temperature', '%s C' % m.temperatures[gate] if m.temperatures[gate] is not None else '--'),
                        ('Spoolman', m.spoolman_support))):
                    self._mmu_text('meta%d' % i, label + ': ' + str(value or '--'), 12, 70 + 37 * i)
                self._mmu_text('readonly', 'Metadata: read-only; use web UI', 12, 338, 40, small=True)
            first_y, visible = 376, 1
        elif page == 'spool':
            writable = self._mmu_spool_writable(m)
            old = self._mmu_spool_original
            self._mmu_text('oldspool', 'Current: ' + ('#%d' % old if old and old > 0 else '--'), 12, 66)
            self._mmu_text('spoolmode', 'Spoolman: ' + (m.spoolman_support if m else 'Unknown'), 12, 99, 40, small=True)
            self._mmu_text('spoolhint', 'Press ID, turn number, press again', 12, 124, 40, small=True)
            self._mmu_text('spooldraft', 'Changes wait for Save' if writable else 'Locked; check mode/state/metadata', 12, 148, 40, small=True, color=0x8410 if writable else 0xFD20)
            first_y, visible = 180, 6
        elif page in ('maintenance', 'options'):
            unit = m.active_unit if m else None
            self._mmu_text('unitname', unit.name if unit else 'Hardware data unavailable', 12, 66)
            self._mmu_text('unittype', unit.selector_type if unit else 'Unsupported controls hidden', 12, 94, 40, small=True)
            self._mmu_text('maintstate', 'Filament: ' + (m.filament.upper() if m else 'UNKNOWN'), 12, 123)
            detail = ('Grip: ' + {True: 'GRIPPED', False: 'RELEASED', None: '--'}[m.grip]
                      if page == 'maintenance' and m else 'Gear sync: ' + {True: 'ON', False: 'OFF', None: '--'}[m.sync_drive]
                      if m else 'Live state unavailable')
            self._mmu_text('maintdetail', detail, 12, 152)
            first_y, visible = 191, 5
        elif page in ('unit', 'units'):
            index = getattr(self, '_mmu_unit_view', 0)
            unit = m.units[index] if m and 0 <= index < len(m.units) else None
            self._mmu_text('unitview', unit.name if page == 'unit' and unit else 'Browse units; no movement', 12, 66)
            self._mmu_text('unithelp', 'Select moves to the first gate' if page == 'unit' else 'Gate numbers remain global', 12, 98, 40, small=True)
            first_y, visible = 134, 7
        elif page == 'leds':
            unit = m.active_unit if m else None
            self._mmu_text('ledunit', unit.name if unit else 'LED state unavailable', 12, 66)
            mode = m.leds.exit_effect if m and m.leds else '--'
            self._mmu_text('ledmode', 'Exit: ' + mode, 12, 98, 40, small=True)
            self._mmu_text('ledscope', 'Only the active unit is changed', 12, 119, 40, small=True)
            first_y, visible = 148, 6
        elif page == 'map':
            writable = self._mmu_map_writable(m)
            self._mmu_text('maphint', 'Press row, turn gate, press again', 12, 66, 40, small=True)
            self._mmu_text('mapdraft', 'Changes wait for Save' if writable else 'Locked; reopen after state change',
                           12, 87, 40, small=True, color=0x8410 if writable else 0xFD20)
            first_y, visible = 114, 7
        elif page in ('endless', 'group'):
            writable = self._mmu_endless_writable(m)
            hint = 'Changes wait for Save' if writable else 'Locked; reopen after state change'
            if page == 'group':
                members = [i for i, g in enumerate(self._mmu_endless_draft['groups'])
                           if g == self._mmu_group and m and i < m.num_gates]
                materials = {(m.materials[i] or '--').strip().lower() for i in members} if m else set()
                colors = {(m.colors[i] or '--').strip().lower() for i in members} if m else set()
                known = members and '--' not in materials and '--' not in colors
                compatibility = ('Mixed material / color' if len(materials) > 1 or len(colors) > 1
                                 else 'Same material / color' if known else 'Compatibility unknown')
                self._mmu_text('groupcompat', compatibility, 12, 66, 40, small=True, color=0xFD20)
                self._mmu_text('grouphelp', 'Press gate: join / split group', 12, 87, 40, small=True)
                self._mmu_text('grouplock', hint, 12, 108, 40, small=True)
                first_y, visible = 134, 7
            else:
                self._mmu_text('endlesshint', hint, 12, 66, 40, small=True, color=0x8410 if writable else 0xFD20)
                self._mmu_text('endlesshelp', 'Open group to choose member gates', 12, 87, 40, small=True)
                first_y, visible = 114, 7
        elif page == 'status':
            session = self.pd.mmu_session
            self._mmu_text('result', session.message or 'Live MMU telemetry', 12, 66, 40, small=True, color=0xFD20 if session.phase == 'error' else 0xFFFF)
            if m:
                self._mmu_text('active', '%s / %s / %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate), m.filament.upper()), 12, 100)
                self._mmu_path(m, 132)
                progress = 'Bowden: %d%%' % m.bowden_progress if m.bowden_progress is not None else 'Stage: ' + m.action
                self._mmu_text('progress', progress, 12, 186)
                sensors = dict(m.sensors)
                for i, sensor in enumerate(('mmu_shared_exit', 'extruder', 'toolhead')):
                    value = 'ABSENT' if sensor not in sensors else {True: 'TRIGGERED', False: 'CLEAR', None: 'UNKNOWN/OFF'}[sensors[sensor]]
                    self._mmu_text('sensor%d' % i, sensor + ': ' + value, 12, 218 + i * 27, 40, small=True)
                self._mmu_text('sync', 'Gear sync: ' + {True: 'ON', False: 'OFF', None: '--'}[m.sync_drive], 12, 306)
                self._mmu_nozzle(336)
            first_y, visible = 376, 2
        elif page == 'bypass':
            self._mmu_text('filament', 'Filament: ' + (m.filament.upper() if m else 'UNKNOWN'), 12, 75)
            self._mmu_text('hint', 'Unload before selecting bypass', 12, 105, 40, small=True)
            first_y, visible = 156, 6
        elif page == 'recover':
            if m:
                reason = m.reason or ('MMU locked' if m.locked else 'Check physical filament state')
                for i in range(3):
                    self._mmu_text('reason%d' % i, reason[i * 40:(i + 1) * 40], 12, 66 + i * 17, 40, small=True, color=0xFD20)
                self._mmu_text('active', '%s / %s / %s' % (self._mmu_tool_label(m.tool), self._mmu_gate_label(m.gate), m.filament.upper()), 12, 131)
            first_y, visible = 186, 6
        elif page == 'manual':
            self._mmu_text('hint', 'Report actual state; no movement', 12, 70, 40, small=True)
            first_y, visible = 113, 7
        elif page == 'confirm':
            op = self._mmu_confirmation
            self._mmu_text('target', op.label, 12, 82)
            summary = 'Physical state: ' + (m.filament.upper() if m else 'UNKNOWN')
            self._mmu_text('details', summary, 12, 120, 40, small=True)
            self._mmu_text('valid', 'Target changed; cancel and retry' if not self._mmu_confirmation_valid() else 'Check target before confirming', 12, 170, 40, small=True, color=0xFD20)
            message = {'unload': 'Filament returns to MMU.', 'eject': 'Spool removed from MMU.',
                       'manual': 'Reports state; does not move.', 'map': 'Saves mapping; no filament movement.',
                       'endless': 'Saves groups; no filament movement.', 'resume': 'Print motion will resume.'}.get(op.action, 'This may move filament/motors.')
            if op.action == 'spool':
                message = 'Saves spool ID; no filament movement.'
            if op.action in ('grip', 'release'):
                message = 'Moves grip/selector at current gate.'
            if op.action in ('sync_on', 'sync_off'):
                message = 'Changes gear drive and grip state.'
            if op.action == 'home_selector':
                message = 'Homes selector, then selects tool.'
            if op.action == 'check_all':
                message = 'Moves filament across all gates.'
            if op.action == 'enable':
                message = 'Resets MMU state.' if op.enabled else 'Disables MMU and releases motors.'
            if op.action == 'motors_off':
                message = 'All MMU units; home may be lost.'
            if op.action.startswith('led_'):
                message = 'Changes LEDs on the target unit.'
            if op.action == 'unit_select':
                message = 'May home / move the selector'
            self._mmu_text('effect', message, 12, 210, 40, small=True)
            if op.action.startswith('led_') or op.action == 'unit_select':
                index = op.values[1] if op.action.startswith('led_') else op.values[0]
                unit = m.units[index] if m and 0 <= index < len(m.units) else None
                self._mmu_text('targetunit', unit.name if unit else 'Target unit unavailable', 12, 241, 40, small=True)
            if op.action == 'map':
                old = m.ttg_map if m else ()
                changes = [(tool, gate) for tool, gate in enumerate(op.values)
                           if tool >= len(old) or old[tool] != gate]
                for row in range(5):
                    value = ('T%d > %s' % (changes[row][0], self._mmu_gate_label(changes[row][1]))
                             if row < min(4, len(changes)) else
                             '+%d more changes' % (len(changes) - 4) if row == 4 and len(changes) > 4 else '')
                    self._mmu_text('change%d' % row, value, 12, 241 + row * 20, 40, small=True)
            if op.action == 'endless':
                self._mmu_text('enablechange', 'Enabled: ' + ('ON' if op.enabled else 'OFF'), 12, 241)
                changes = [(gate, group) for gate, group in enumerate(op.values)
                           if m and (gate >= m.num_gates or m.endless_groups[gate] != group)]
                ids = sorted(set(op.values))
                for row in range(4):
                    value = ('%s > Group %d' % (self._mmu_gate_label(changes[row][0]), ids.index(changes[row][1]) + 1)
                             if row < min(3, len(changes)) else
                             '+%d more changes' % (len(changes) - 3) if row == 3 and len(changes) > 3 else '')
                    self._mmu_text('groupchange%d' % row, value, 12, 269 + row * 20, 40, small=True)
            if op.action == 'spool':
                old = m.spool_ids[op.gate] if m and op.gate < m.num_gates else None
                self._mmu_text('spoolchange', '%s: %s > %s' % (self._mmu_gate_label(op.gate),
                               '#%d' % old if old and old > 0 else '--',
                               '#%d' % op.values[0] if op.values[0] > 0 else '--'), 12, 241, 40, small=True)
                moved = [self._mmu_gate_label(gate) for gate, sid in enumerate(m.spool_ids if m else ())
                         if gate != op.gate and sid == op.values[0] and sid > 0]
                warning = 'Moves ID off: ' + ', '.join(moved) if moved else 'Other assignments preserved'
                self._mmu_text('spoolmove', warning, 12, 271, 40, small=True, color=0xFD20)
            for i, (_, label, _, enabled) in enumerate(items):
                self._mmu_row('item%d' % i, label, '', 8 + i * 132, 374, 124,
                              self._mmu_selection == i + 1, enabled)
            first_y = None
        if first_y is not None:
            start = max(0, self._mmu_selection - visible)
            for row in range(visible):
                i = start + row
                if i < len(items):
                    _, label, value, enabled = items[i]
                    if page == 'map' and items[i][0][0] == 'map_edit' and getattr(self, '_mmu_edit', None) == ('map', items[i][0][1]):
                        value = '[' + value + ']'
                    if page == 'endless' and items[i][0][0] == 'endless_toggle' and getattr(self, '_mmu_edit', None) == ('endless', 'enabled'):
                        value = '[' + value + ']'
                    if page == 'spool' and items[i][0][0] == 'spool_edit' and getattr(self, '_mmu_edit', None) == ('spool', 'id'):
                        value = '[' + value + ']'
                    if page == 'manual' and items[i][0][0] == 'edit' and getattr(self, '_mmu_edit', None) == items[i][0][1]:
                        value = '[' + value + ']'
                    self._mmu_row('row%d' % row, label, value, 8, first_y + row * 43, 256,
                                  self._mmu_selection == i + 1, enabled)
                elif self._mmu_render.get('row%d' % row) is not None:
                    self.lcd.draw_rectangle(1, 0x0000, 8, first_y + row * 43, 263, first_y + row * 43 + 39)
                    self._mmu_render.pop('row%d' % row, None)
            if len(items) > visible:
                self._mmu_text('pagination', '%d-%d / %d' % (start + 1, min(len(items), start + visible), len(items)), 12, 436, 40, small=True)
        self._mmu_text('footer', self._mmu_notice or ('Turn: edit   Press: accept' if getattr(self, '_mmu_edit', None) else 'Turn: select   Press: open'), 10, 463, 42, small=True, color=0xFD20 if self._mmu_notice else 0x8410)
        self.lcd.update()

    def HMI_MMU_Menu(self):
        if not hasattr(self, '_mmu_page'):
            self.Draw_MMU_Menu()
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        m = self.pd.mmu_session.state
        edit = getattr(self, '_mmu_edit', None)
        if edit:
            if event == self.ENCODER_DIFF_ENTER:
                self._mmu_edit = None
            elif isinstance(edit, tuple) and edit[0] == 'map':
                if not self._mmu_map_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    delta = 1 if event == self.ENCODER_DIFF_CW else -1
                    tool = edit[1]
                    self._mmu_map_draft[tool] = max(0, min(m.num_gates - 1, self._mmu_map_draft[tool] + delta))
            elif edit == ('endless', 'enabled'):
                if not self._mmu_endless_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    self._mmu_endless_draft['enabled'] = event == self.ENCODER_DIFF_CW
            elif edit == ('spool', 'id'):
                if not self._mmu_spool_writable(m):
                    self._mmu_edit = None
                    self._mmu_notice = 'MMU changed; reopen editor'
                elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    delta = 1 if event == self.ENCODER_DIFF_CW else -1
                    self._mmu_spool_draft = max(1, self._mmu_spool_draft + delta)
            elif m and event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                delta = 1 if event == self.ENCODER_DIFF_CW else -1
                self._mmu_manual[edit] = (not self._mmu_manual[edit] if edit == 'loaded'
                    else max(0, min(m.num_gates - 1, self._mmu_manual[edit] + delta)))
            self.Draw_MMU_Menu()
            return
        items = self._mmu_items(m)
        if event == self.ENCODER_DIFF_ENTER and tuple(item[0] for item in items) != self._mmu_drawn_keys:
            self._mmu_notice = 'Menu changed; select again'
            self.Draw_MMU_Menu()
            return
        self._mmu_selection = min(self._mmu_selection, len(items))
        if event == self.ENCODER_DIFF_CW:
            self._mmu_selection = min(len(items), self._mmu_selection + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self._mmu_selection = max(0, self._mmu_selection - 1)
        elif event == self.ENCODER_DIFF_ENTER:
            if self._mmu_selection == 0:
                self._mmu_back()
                return
            key, _, _, enabled = items[self._mmu_selection - 1]
            if not enabled:
                self._mmu_notice = 'Unavailable in current state'
            elif key[0] == 'page':
                if key[1] == 'manual':
                    self._mmu_manual_base = m.fingerprint if m else None
                    self._mmu_manual = {'tool': m.tool if m and m.tool is not None and m.tool >= 0 else 0,
                                        'gate': m.gate if m and m.gate is not None and m.gate >= 0 else 0,
                                        'loaded': bool(m and m.filament == 'loaded')}
                    self._mmu_edit = None
                self._mmu_open(key[1])
                return
            elif key[0] == 'gate':
                self._mmu_gate = key[1]
                self._mmu_open('gate')
                return
            elif key[0] == 'unit':
                self._mmu_unit_view = key[1]
                self._mmu_open('unit')
                return
            elif key[0] == 'map_edit':
                self._mmu_edit = ('map', key[1])
            elif key[0] == 'endless_toggle':
                self._mmu_edit = ('endless', 'enabled')
            elif key[0] == 'spool_edit':
                self._mmu_edit = ('spool', 'id')
            elif key[0] == 'group':
                self._mmu_group = key[1]
                self._mmu_open('group')
                return
            elif key[0] == 'member':
                groups = self._mmu_endless_draft['groups']
                gate = key[1]
                if groups[gate] != self._mmu_group:
                    groups[gate] = self._mmu_group
                elif groups.count(self._mmu_group) > 1:
                    new_group = 0
                    while new_group in groups:
                        new_group += 1
                    groups[gate] = new_group
            elif key[0] in ('action', 'apply', 'map_save', 'endless_save', 'spool_save', 'spool_clear', 'unit_select', 'led_mode'):
                try:
                    if key[0] == 'apply' and (m is None or m.fingerprint != self._mmu_manual_base):
                        raise ValueError('MMU changed; reopen editor')
                    if key[0] == 'unit_select':
                        self._mmu_confirmation = self.pd.mmu_session.prepare('unit_select', values=(key[1],))
                    elif key[0] == 'led_mode':
                        self._mmu_confirmation = self.pd.mmu_session.prepare('led_mode', values=(key[1],))
                    elif key[0] in ('spool_save', 'spool_clear'):
                        if not self._mmu_spool_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        sid = -1 if key[0] == 'spool_clear' else self._mmu_spool_draft
                        self._mmu_confirmation = self.pd.mmu_session.prepare('spool', gate=self._mmu_gate, values=(sid,))
                    elif key[0] == 'endless_save':
                        if not self._mmu_endless_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        draft = self._mmu_endless_draft
                        self._mmu_confirmation = self.pd.mmu_session.prepare('endless', values=draft['groups'], enabled=draft['enabled'])
                    elif key[0] == 'map_save':
                        if not self._mmu_map_writable(m):
                            raise ValueError('MMU changed; reopen editor')
                        self._mmu_confirmation = self.pd.mmu_session.prepare('map', values=self._mmu_map_draft)
                    else:
                        self._mmu_confirmation = (self.pd.mmu_session.prepare(key[1], gate=key[2], enabled=key[3] if len(key) > 3 else None)
                            if key[0] == 'action' else self.pd.mmu_session.prepare('manual', **self._mmu_manual))
                except ValueError as error:
                    self._mmu_notice = str(error)
                else:
                    self._mmu_open('confirm')
                    self._mmu_selection = 1  # Cancel always owns initial focus.
                    self.Draw_MMU_Menu()
                    return
            elif key[0] == 'execute':
                try:
                    self.pd.mmu_session.start(self._mmu_confirmation)
                except ValueError as error:
                    self._mmu_notice = str(error)
                else:
                    # Drop confirmation so Back can never submit it again.
                    if self._mmu_confirmation.action == 'map':
                        self._mmu_map_draft = None
                    if self._mmu_confirmation.action == 'endless':
                        self._mmu_endless_draft = None
                    if self._mmu_confirmation.action == 'spool':
                        self._mmu_spool_draft = None
                    self._mmu_page, self._mmu_selection = 'status', 0
                    self.Draw_MMU_Menu()
                    return
            elif key[0] == 'cancel':
                self._mmu_back()
                return
            elif key[0] == 'edit':
                self._mmu_edit = key[1]
            elif key[0] == 'ack':
                self.pd.mmu_session.phase, self.pd.mmu_session.message = 'idle', ''
        self.Draw_MMU_Menu()

    def _mmu_power_popup_stale(self):
        return (getattr(self, 'checkkey', None) == self.PowerConfirm and getattr(self, '_power_origin', None) == self.MMUMenu
                and (self.pd.connection_error or not self.pd.state.ready
                     or getattr(self, '_power_origin_epoch', None) != self.pd.state.epoch))

    def _poll_mmu(self):
        session = self.pd.mmu_session
        was_pending = session.pending is not None
        session.update()
        if self._mmu_power_popup_stale():
            self._restore_power_origin()
        if self.checkkey == self.MMUMenu:
            if self.pd.connection_error and getattr(self, '_power_focus', False):
                self._power_focus = False
                self._draw_power_icon(False, clear=True)
            if was_pending and getattr(self, '_mmu_page', 'home') != 'status' and session.phase == 'error':
                self._mmu_page, self._mmu_selection = 'status', 1
            self.Draw_MMU_Menu()
