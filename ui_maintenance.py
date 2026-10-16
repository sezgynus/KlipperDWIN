"""Graphite Maintenance menu: opt-in diagnostics and guided physical tests.

No Moonraker I/O on menu entry. Only the explicit second confirmation
can dispatch a guarded physical test. Navigation never implies a PASS.
"""
from types import SimpleNamespace


class MaintenanceViewMixin:
    def _maintenance_back_home(self):
        self._maintenance_page = 'root'
        self._maintenance_selection = 0
        self.select_page.set(next(
            i for i, entry in enumerate(self._home_entries())
            if entry[0] == 'MAINTENANCE'))
        self.Goto_MainMenu()
        self.lcd.update()

    def _maintenance_rows(self):
        page = getattr(self, '_maintenance_page', 'root')
        back = ('Back', self.ICON_Back, None, None)
        if page == 'root':
            return 'Maintenance', (back, ('Self Tests', self.ICON_FanSpeed, None, None),
                                   ('Diagnostics', self.ICON_Info, None, None))
        if page == 'tests':
            options = tuple(self.pd.maintenance_guided_plan())
            self._maintenance_test_rows = options
            entries = [back]
            for item in options:
                label = item.feature_id + ' ' + (item.device or 'global')
                entries.append((label[:26], self.ICON_FanSpeed
                                if item.feature_id.startswith('F') else
                                self.ICON_CaseLight, None, None))
            if not options:
                entries.append(('No safe tests', self.ICON_Info, None, None))
            return 'Self Tests', tuple(entries)
        if page == 'diagnostics':
            options = tuple(self.pd.maintenance_read_plan())
            self._maintenance_read_rows = options
            entries = [back]
            for item in options:
                entries.append((item.feature_id + ' ' + {
                    'S01': 'Host', 'S02': 'CPU temp', 'S03': 'Throttling',
                    'S05': 'Network', 'S08': 'Klipper', 'S10': 'History',
                    'M11': 'Stepper enable', 'M13': 'Angle telemetry',
                    'M14': 'Motion state', 'M16': 'Carriage mode'
                }.get(item.feature_id, getattr(item, 'device', None) or 'Info'), self.ICON_Info, None, None))
            if not options:
                entries.append(('No information', self.ICON_Info, None, None))
            return 'Diagnostics', tuple(entries)
        if page == 'pulse':
            phase = self.pd.maintenance_pulse.phase
            if phase == 'workflow':
                owner = self.pd.maintenance_pulse
                return 'Guided '+str(owner.feature_id), (
                    ('Cancel workflow', self.ICON_Back, None, None),
                    *((label[:26], self.ICON_Info, None, None)
                      for label, action in owner.workflow_choices),
                    *((text[:26], self.ICON_Info, None, None) for text in owner.live_text))
            if phase == 'await_confirmation':
                # The physical controller owns the active feature identity;
                # avoid calling multi-step tests a short pulse.
                feature_id = getattr(self.pd.maintenance_pulse, 'feature_id', None)
                action = {'M01': 'Read released switch', 'M03': 'Home XYZ (clear path)',
                          'M04': 'Run stepper buzz', 'M05': 'Move 1mm and return',
                          'M06': 'Move measured 10mm', 'M12': 'Calibrate phase (no save)', 'F02': 'Run speed steps',
                          'F12': 'Run PWM sweep',
                          'O04': 'Run color sequence'}.get(
                              feature_id, 'Run PID (no save)' if feature_id in ('H02', 'H03', 'H04') else 'Run thermal test' if feature_id and feature_id.startswith('H') else 'Run short pulse')
                if feature_id and feature_id.startswith(('P','R')):
                    return 'Confirm '+feature_id, (
                        ('Cancel', self.ICON_Back, None, None),
                        ('Start firmware workflow', self.ICON_Info, None, None),
                        *((text[:26], self.ICON_Info, None, None)
                          for text in self.pd.maintenance_pulse.live_text))
                if feature_id and feature_id.startswith('H'):
                    live = getattr(self.pd.maintenance_pulse, 'live_text', ())
                    return 'Confirm HEAT test', (
                        ('Cancel', self.ICON_Back, None, None),
                        (action, self.ICON_FanSpeed, None, None),
                        *((text[:26], self.ICON_Info, None, None) for text in live[:1]),
                        ('Cancel = Klipper shutdown', self.ICON_Info, None, None))
                if feature_id in ('M03','M04','M05','M06','M12'):
                    if feature_id == 'M06' and self.pd.maintenance_pulse.returning:
                        action = 'Return to start'
                    return 'Confirm clear path', (
                        ('Cancel', self.ICON_Back, None, None),
                        (action[:26], self.ICON_Info, None, None),
                        *((text[:26], self.ICON_Info, None, None) for text in self.pd.maintenance_pulse.live_text))
                if feature_id == 'M01':
                    return self.pd.maintenance_pulse.prompt, (
                        ('Cancel', self.ICON_Back, None, None),
                        ('Read switch now', self.ICON_Info, None, None),
                        *((text[:26], self.ICON_Info, None, None) for text in self.pd.maintenance_pulse.live_text))
                return 'Confirm test', (('Cancel', self.ICON_Back, None, None),
                                        (action, self.ICON_FanSpeed, None, None))
            if phase == 'await_measurement':
                return 'Measure actual travel', (
                    ('Cancel: stays here', self.ICON_Back, None, None),
                    ('Enter measured distance', self.ICON_Info, None, None),
                    ('Use ruler / caliper', self.ICON_Info, None, None))
            if phase == 'measurement_edit':
                return 'Actual measured mm', (
                    ('%.2f mm' % self.pd.maintenance_pulse.measurement_value, self.ICON_Info, None, None),
                    ('Turn: change actual value', self.ICON_Info, None, None),
                    ('ENTER: confirm / return', self.ICON_Info, None, None))
            if phase in ('await_press', 'await_release'):
                return self.pd.maintenance_pulse.prompt, (
                    ('Cancel', self.ICON_Back, None, None),
                    ('Read switch now', self.ICON_Info, None, None),
                    *((text[:26], self.ICON_Info, None, None) for text in self.pd.maintenance_pulse.live_text))
            if phase == 'f12_await_stop':
                return 'Fan fully stopped?', (('Cancel', self.ICON_Back, None, None),
                                              ('Yes, stopped', self.ICON_Info, None, None))
            if phase == 'await_observation' and getattr(self.pd.maintenance_pulse, 'feature_id', None) == 'F12':
                levels = self.pd.maintenance_pulse.pwm_levels
                return 'First fan startup?', ((('None stable', self.ICON_Back, None, None),)
                    + tuple(('%d: %d/255' % (i + 1, val), self.ICON_FanSpeed, None, None)
                            for i, val in enumerate(levels)))
            if phase == 'await_observation':
                question = getattr(self.pd.maintenance_pulse,
                                   'observation_prompt', None) or 'Did it work?'
                return question[:27], (('Not observed', self.ICON_Back, None, None),
                                       ('Yes, observed', self.ICON_Info, None, None))
            if phase in ('analysis','saving_baseline'):
                return 'Measured data', (
                    ('Cancel processing', self.ICON_Back, None, None),
                    ('Processing result...', self.ICON_Info, None, None))
            if phase in ('preflight', 'running', 'verifying', 'f12_next_preflight'):
                if phase == 'running' and getattr(self.pd.maintenance_pulse, 'feature_id', None) == 'F12':
                    info = self.pd.maintenance_pulse.f12_status
                    if info:
                        round_no, step, pwm, low, high = info
                        return ('F12 Round %d Step %d' % (round_no, step)), (
                            ('Cancel test', self.ICON_Back, None, None),
                            ('PWM %d / 255' % pwm, self.ICON_FanSpeed, None, None),
                            ('Range %d - %d' % (low, high), self.ICON_Info, None, None))
                if (getattr(self.pd.maintenance_pulse, 'feature_id', '') or '').startswith(('P','R')):
                    return 'Firmware workflow', (
                        ('Stop / cancel workflow', self.ICON_Back, None, None),
                        *((text[:26], self.ICON_Info, None, None)
                          for text in self.pd.maintenance_pulse.live_text))
                if getattr(self.pd.maintenance_pulse, 'feature_id', '').startswith('H'):
                    live = getattr(self.pd.maintenance_pulse, 'live_text', ())
                    return 'Thermal test', (
                        ('Stop: Klipper shutdown', self.ICON_Back, None, None),
                        *((text[:26], self.ICON_Info, None, None) for text in live))
                if getattr(self.pd.maintenance_pulse, 'feature_id', '') in ('M03','M04','M05','M06','M12'):
                    return 'Motion test', (
                        ('Cancel checks' if phase == 'preflight' else 'Stop: Klipper shutdown', self.ICON_Back, None, None),
                        *((text[:26], self.ICON_Info, None, None) for text in self.pd.maintenance_pulse.live_text))
                text = {'preflight': 'Safety checks...', 'running': 'Testing...',
                        'verifying': 'Checking restore...',
                        'f12_next_preflight': 'Next stage safety...'}[phase]
                return 'Self Test', (('Cancel test', self.ICON_Back, None, None),
                                     (text, self.ICON_Info, None, None))
            if phase == 'stopping':
                return 'Stopping test', (('Shutdown requested', self.ICON_Info, None, None),
                                         ('Check printer is safe', self.ICON_Info, None, None))
            return 'Self Test', (('Back', self.ICON_Back, None, None),)
        if page == 'reading':
            return 'Diagnostics', (('Cancel read', self.ICON_Back, None, None),
                                   ('Reading...', self.ICON_Info, None, None))
        if page == 'result':
            outcome = getattr(self, '_maintenance_result', None)
            status = str(getattr(outcome, 'status', None) or 'OBSERVED')
            reason = str(getattr(outcome, 'reason', 'unknown'))
            entries = [back,
                       (status[:25], self.ICON_Info, None, None),
                       (reason.replace('_', ' ')[:25], self.ICON_Info, None, None)]
            if 'SHUTDOWN_UNCONFIRMED' in reason:
                entries.extend((('CHECK PRINTER SAFETY NOW', self.ICON_Info, None, None),
                                ('Use physical power switch', self.ICON_Info, None, None)))
            if reason == 'f12_kick_start_active':
                entries.extend((
                    ('Set kick_start_time: 0', self.ICON_Info, None, None),
                    ('RESTART Klipper', self.ICON_Info, None, None)))
            elif reason == 'f12_kick_start_unknown':
                entries.append(('Check fan config', self.ICON_Info, None, None))
            for key, value in getattr(outcome, 'evidence', ())[:6]:
                entries.append(((str(key) + ': ' + str(value))[:25],
                                self.ICON_Info, None, None))
            return 'Result', tuple(entries)
        return 'Maintenance', (back,)

    def Draw_Maintenance_Menu(self):
        title, entries = self._maintenance_rows()
        self._maintenance_selection = max(0, min(
            getattr(self, '_maintenance_selection', 0), len(entries) - 1))
        self._draw_list_menu(title, entries, self._maintenance_selection)

    def _maintenance_show(self, page, selection=0):
        self._maintenance_page = page
        self._maintenance_selection = selection
        self.Draw_Maintenance_Menu()
        self.lcd.update()

    def HMI_Maintenance_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        page = getattr(self, '_maintenance_page', 'root')
        _, entries = self._maintenance_rows()
        selected = getattr(self, '_maintenance_selection', 0)
        if (page == 'pulse' and self.pd.maintenance_pulse.phase == 'measurement_edit'
                and event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW)):
            steps = max(1, int(getattr(self, '_menu_batch_steps', 1)))
            self.pd.maintenance_pulse.adjust_measurement(
                .01 * steps * (1 if event == self.ENCODER_DIFF_CW else -1))
            self._maintenance_show('pulse')
            return
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            steps = max(1, int(getattr(self, '_menu_batch_steps', 1)))
            delta = steps if event == self.ENCODER_DIFF_CW else -steps
            self._maintenance_selection = max(0, min(
                len(entries) - 1, selected + delta))
            self.Draw_Maintenance_Menu()
            self.lcd.update()
            return
        if event != self.ENCODER_DIFF_ENTER:
            return
        if page == 'root':
            if selected == 0:
                self._maintenance_back_home()
            elif selected == 1:
                self._maintenance_show('tests')
            elif selected == 2:
                self._maintenance_show('diagnostics')
            return
        if page in ('tests', 'diagnostics'):
            if selected == 0:
                self._maintenance_show('root')
                return
            rows = (getattr(self, '_maintenance_test_rows', ())
                    if page == 'tests'
                    else getattr(self, '_maintenance_read_rows', ()))
            if selected > len(rows):
                return
            row = rows[selected - 1]
            # A test/diagnostic result belongs to the list it was opened
            # from, not the Maintenance root. Retain the selected device
            # when returning so the operator can test adjacent entries.
            self._maintenance_result_parent = page
            self._maintenance_result_selection = selected
            if page == 'tests':
                accepted, why = self.pd.start_maintenance_physical(
                    row.feature_id, row.device)
            else:
                accepted, why = (self.pd.start_maintenance_read(row.feature_id, device=row.device)
                                 if getattr(row, 'device', None) is not None else
                                 self.pd.start_maintenance_read(row.feature_id))
            if not accepted:
                self._maintenance_result = SimpleNamespace(
                    status='BLOCKED', reason=why)
                self._maintenance_show('result')
            else:
                self._maintenance_show('pulse' if page == 'tests' else 'reading')
            return
        if page == 'pulse':
            phase = self.pd.maintenance_pulse.phase
            if phase == 'workflow':
                if selected == 0:
                    outcome = self.pd.cancel_maintenance_physical()
                    if outcome is not None:
                        self._maintenance_result = outcome
                        self._maintenance_show('result')
                    else:
                        self._maintenance_show('pulse')
                elif selected <= len(self.pd.maintenance_pulse.workflow_choices):
                    accepted, why = self.pd.maintenance_pulse.choose(selected-1)
                    if accepted:
                        self._maintenance_show('pulse')
                return
            if phase == 'await_confirmation':
                if selected == 1:
                    accepted, why = self.pd.confirm_maintenance_physical()
                    if not accepted:
                        self._maintenance_result = SimpleNamespace(
                            status='BLOCKED', reason=why)
                        self._maintenance_show('result')
                    else:
                        self._maintenance_show('pulse')
                elif selected == 0:
                    outcome = self.pd.cancel_maintenance_physical()
                    self._maintenance_result = outcome or SimpleNamespace(
                        status='ABORTED', reason='user_cancelled')
                    self._maintenance_show('result')
            elif phase == 'await_measurement':
                if selected == 1:
                    self.pd.maintenance_pulse.begin_measurement()
                    self._maintenance_show('pulse')
                elif selected == 0:
                    self._maintenance_result = self.pd.cancel_maintenance_physical()
                    self._maintenance_show('result')
            elif phase == 'measurement_edit':
                accepted, why = self.pd.maintenance_pulse.record_measurement(
                    self.pd.maintenance_pulse.measurement_value)
                if accepted:
                    self._maintenance_show('pulse')
            elif phase == 'await_observation':
                seen = (selected if getattr(self.pd.maintenance_pulse, 'feature_id', None) == 'F12'
                        else selected == 1)
                outcome = self.pd.observe_maintenance_physical(seen)
                if outcome is not None:
                    self._maintenance_result = outcome
                    self._maintenance_show('result')
                elif self.pd.maintenance_pulse.phase != phase:
                    # Multi-round F12 changes state without producing a
                    # terminal result. Redraw immediately on the ENTER event;
                    # otherwise the previous choice menu stays visible until
                    # the next encoder rotation.
                    self._maintenance_show('pulse')
            elif phase in ('await_press', 'await_release'):
                if selected == 1:
                    accepted, why = self.pd.confirm_maintenance_physical()
                    if not accepted:
                        self._maintenance_result = SimpleNamespace(status='BLOCKED', reason=why)
                        self._maintenance_show('result')
                    else:
                        self._maintenance_show('pulse')
                elif selected == 0:
                    self._maintenance_result = self.pd.cancel_maintenance_physical()
                    self._maintenance_show('result')
            elif phase == 'f12_await_stop':
                if selected == 0:
                    outcome = self.pd.cancel_maintenance_physical()
                    self._maintenance_result = outcome
                    self._maintenance_show('result')
                else:
                    outcome, reason = self.pd.confirm_maintenance_f12_stopped()
                    if outcome is True:
                        self._maintenance_show('pulse')
                    else:
                        self._maintenance_result = outcome if outcome is not None else SimpleNamespace(
                            status='BLOCKED', reason=reason)
                        self._maintenance_show('result')
            elif selected == 0:
                # During a sent pulse cancel means 'abort after restoration'.
                outcome = self.pd.cancel_maintenance_physical()
                if outcome is not None:
                    self._maintenance_result = outcome
                    self._maintenance_show('result')
            return
        if page == 'reading':
            self._maintenance_result = self.pd.cancel_maintenance_read()
            self._maintenance_show('result')
            return
        if page == 'result' and selected == 0:
            parent = getattr(self, '_maintenance_result_parent', None)
            if parent in ('tests', 'diagnostics'):
                self._maintenance_show(
                    parent, getattr(self, '_maintenance_result_selection', 0))
            else:
                # Defensive fallback for results without a known list origin.
                self._maintenance_show('root')

    def _poll_maintenance_ui(self):
        # Invoked from the normal UI owner tick; zero additional I/O when idle.
        pulse = getattr(self.pd, 'maintenance_pulse', None)
        reading = getattr(self.pd, 'maintenance_reader', None)
        page = getattr(self, '_maintenance_page', None)
        if self.checkkey == self.MaintenanceMenu and page == 'pulse' and pulse is not None:
            before = pulse.phase
            result = self.pd.poll_maintenance_physical()
            if result is not None:
                self._maintenance_result = result
                self._maintenance_show('result')
                return
            f12_live = (pulse.phase == 'running' and
                        getattr(pulse, 'feature_id', None) == 'F12')
            f12_step = (pulse.f12_status[1] if f12_live and pulse.f12_status else None)
            thermal_live = (getattr(pulse, 'feature_id', '') or '').startswith('H') and pulse.phase in ('running', 'verifying')
            thermal_second = int(__import__('time').monotonic()) if thermal_live else None
            if (thermal_live and getattr(self, '_maintenance_thermal_second', None) != thermal_second) or before != pulse.phase or (f12_live and
                    getattr(self, '_maintenance_f12_step_seen', None) != f12_step):
                self._maintenance_thermal_second = thermal_second
                self._maintenance_f12_step_seen = f12_step
                self._maintenance_selection = 0
                self.Draw_Maintenance_Menu()
                self.lcd.update()
            if pulse.pending and hasattr(self, '_loop'):
                self._loop.set_interval(.1)
        elif self.checkkey == self.MaintenanceMenu and page == 'reading' and reading is not None:
            result = self.pd.poll_maintenance_read()
            if result is not None:
                # Keep the executor's already allowlisted scalar evidence.
                # Never print full Moonraker payloads or private filenames.
                self._maintenance_result = result
                self._maintenance_show('result')
            elif reading.pending and hasattr(self, '_loop'):
                self._loop.set_interval(.1)
        elif pulse is not None and pulse.pending:
            # An unrelated popup must not abandon a dispatched pulse.
            result = self.pd.poll_maintenance_physical()
            if result is not None:
                self._maintenance_result = result
        elif reading is not None and reading.pending:
            self.pd.poll_maintenance_read()
