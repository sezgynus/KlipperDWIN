"""Scrollable offline recovery view; encoder remains usable without Klipper READY."""
import textwrap

from t5uic1_driver import T5UIC1Display


class RecoveryViewMixin:
    RecoveryScreen = 50

    def _recovery_entries(self):
        recovery = self.pd.recovery
        confirmation = getattr(self, '_recovery_confirm', None)
        labels = {'restart': 'Restart Klipper', 'firmware': 'Firmware Restart',
                  'service': 'Restart Klipper service'}
        if confirmation:
            detail = ('Reset Klipper and MCUs' if confirmation == 'firmware' else
                      'Restart Klipper service' if confirmation == 'service' else
                      'Reload Klipper config')
            return 'Confirm restart', (
                ('Cancel', self.ICON_Back, None, None),
                (labels[confirmation], self.ICON_Info, None, None),
                ('Check printer is safe', self.ICON_Info, None, None),
                (detail, self.ICON_Info, None, None))
        entries = [('Refresh connection', self.ICON_Info, None, None)]
        if not recovery.busy:
            entries.extend((labels[a], self.ICON_Info, None, None) for a in recovery.state.actions)
        entries.append(('Check printer is safe', self.ICON_Info, None, None))
        if recovery.notice:
            entries.extend((line, self.ICON_Info, None, None)
                           for line in textwrap.wrap(recovery.notice, 26))
        message = T5UIC1Display._panel_text(recovery.state.message)
        for paragraph in message.splitlines() or ('No error details available',):
            entries.extend((line, self.ICON_Info, None, None)
                           for line in textwrap.wrap(paragraph, 26) or (' ',))
        return recovery.state.title, tuple(entries)

    def Draw_Recovery(self):
        title, entries = self._recovery_entries()
        self._recovery_selection = max(0, min(
            getattr(self, '_recovery_selection', 0), len(entries)-1))
        self._draw_list_menu(title, entries, self._recovery_selection)
        self.lcd.update()

    def _poll_recovery_ui(self):
        recovery = getattr(self.pd, 'recovery', None)
        if recovery is None or not isinstance(getattr(recovery.state, 'kind', None), str):
            return False
        recovery.poll()
        if not self.pd.connection_error:
            if getattr(self, 'checkkey', None) == self.RecoveryScreen:
                self._recovery_confirm = None
                self._recovery_render = None
                self._offline = False
                # A recovery is a fresh printer session, never resume an old
                # heat/motion editor, test, or pending print dialog.
                self.Goto_MainMenu()
                self.lcd.update()
            return False
        if getattr(self, '_relay_status', None) == 'off':
            return False
        if getattr(self, '_boot_active', False) and recovery.state.kind == 'checking':
            return False
        first = getattr(self, 'checkkey', None) != self.RecoveryScreen
        if first:
            # Stop the splash animation before allowing offline input.
            if getattr(self, '_boot_animation_running', False):
                self.lcd.configure_animation(
                    0, False, self._boot_animation_active_library, 250, 254,
                    self._boot_animation_x, 320, 10)
                self._boot_animation_running = False
            self._boot_active = False
            self.checkkey = self.RecoveryScreen
            self._recovery_confirm = None
            self._recovery_selection = 0
            self._recovery_actions = recovery.state.actions
            self.Clear_Popup_Area()
        if recovery.state.actions != getattr(self, '_recovery_actions', ()):
            self._recovery_confirm = None
            self._recovery_selection = 0
            self._recovery_actions = recovery.state.actions
        signature = (recovery.state, recovery.notice, recovery.busy,
                     getattr(self, '_recovery_confirm', None))
        if first or signature != getattr(self, '_recovery_render', None):
            self._recovery_render = signature
            self.Draw_Recovery()
        self._offline = True
        return True

    def _recovery_input(self, event):
        # Called after UART/session checks, before normal Klipper READY gates.
        kind = event.kind
        if kind == 'button_release':
            # Physical buttons produce release events; remote clicks produce
            # press events. A long/aborted hold must never confirm a restart.
            if event.value >= self.SHORT_PRESS_MS:
                return
            kind = 'press'
        if kind not in ('rotate', 'press'):
            return
        if self._display_activity():
            return
        recovery = self.pd.recovery
        _, entries = self._recovery_entries()
        selected = getattr(self, '_recovery_selection', 0)
        if kind == 'rotate':
            delta = -event.value  # Same wheel/encoder direction as normal menus.
            self._recovery_selection = max(0, min(len(entries)-1, selected+delta))
        else:
            action = getattr(self, '_recovery_confirm', None)
            if action:
                self._recovery_confirm = None
                self._recovery_selection = 0
                if selected == 1:
                    recovery.request(action)
            elif selected == 0:
                recovery.refresh()
            elif not recovery.busy and 1 <= selected <= len(recovery.state.actions):
                self._recovery_confirm = recovery.state.actions[selected-1]
                self._recovery_selection = 0  # Explicit second press on Restart.
        self._recovery_render = None
        self.Draw_Recovery()
