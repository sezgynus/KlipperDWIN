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
                    'S05': 'Network', 'S08': 'Klipper', 'S10': 'History'
                }.get(item.feature_id, 'Info'), self.ICON_Info, None, None))
            if not options:
                entries.append(('No information', self.ICON_Info, None, None))
            return 'Diagnostics', tuple(entries)
        if page == 'pulse':
            phase = self.pd.maintenance_pulse.phase
            if phase == 'await_confirmation':
                # The physical controller owns the active feature identity;
                # avoid calling multi-step tests a short pulse.
                feature_id = getattr(self.pd.maintenance_pulse, 'feature_id', None)
                action = {'F02': 'Run speed steps',
                          'O04': 'Run color sequence'}.get(
                              feature_id, 'Run short pulse')
                return 'Confirm test', (('Cancel', self.ICON_Back, None, None),
                                        (action, self.ICON_FanSpeed, None, None))
            if phase == 'await_observation':
                question = getattr(self.pd.maintenance_pulse,
                                   'observation_prompt', None) or 'Did it work?'
                return question[:27], (('Not observed', self.ICON_Back, None, None),
                                       ('Yes, observed', self.ICON_Info, None, None))
            if phase in ('preflight', 'running', 'verifying'):
                text = {'preflight': 'Safety checks...', 'running': 'Testing...',
                        'verifying': 'Checking restore...'}[phase]
                return 'Self Test', (('Cancel test', self.ICON_Back, None, None),
                                     (text, self.ICON_Info, None, None))
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

    def _maintenance_show(self, page):
        self._maintenance_page = page
        self._maintenance_selection = 0
        self.Draw_Maintenance_Menu()
        self.lcd.update()

    def HMI_Maintenance_Menu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        page = getattr(self, '_maintenance_page', 'root')
        _, entries = self._maintenance_rows()
        selected = getattr(self, '_maintenance_selection', 0)
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
            if page == 'tests':
                accepted, why = self.pd.start_maintenance_physical(
                    row.feature_id, row.device)
            else:
                accepted, why = self.pd.start_maintenance_read(row.feature_id)
            if not accepted:
                self._maintenance_result = SimpleNamespace(
                    status='BLOCKED', reason=why)
                self._maintenance_show('result')
            else:
                self._maintenance_show('pulse' if page == 'tests' else 'reading')
            return
        if page == 'pulse':
            phase = self.pd.maintenance_pulse.phase
            if phase == 'await_confirmation':
                if selected == 1:
                    accepted, why = self.pd.confirm_maintenance_physical()
                    if not accepted:
                        self._maintenance_result = SimpleNamespace(
                            status='BLOCKED', reason=why)
                        self._maintenance_show('result')
                    else:
                        self._maintenance_show('pulse')
                else:
                    outcome = self.pd.cancel_maintenance_physical()
                    self._maintenance_result = outcome or SimpleNamespace(
                        status='ABORTED', reason='user_cancelled')
                    self._maintenance_show('result')
            elif phase == 'await_observation':
                outcome = self.pd.observe_maintenance_physical(selected == 1)
                if outcome is not None:
                    self._maintenance_result = outcome
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
            if before != pulse.phase:
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
