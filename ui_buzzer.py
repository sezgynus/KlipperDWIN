from lcd_resources import ICON_BUZZER, ICON_SOUND_OFF
"""Display-menu buzzer selection and sound preferences."""
from dataclasses import replace
from buzzer_control import Settings, Player, outputs, resolve_output, TONES
from t5uic1_driver import T5UIC1ProtocolError


class BuzzerViewMixin:
    def _buzzer_settings(self):
        value = getattr(self, '_buzzer_values', None)
        value = value if isinstance(value, Settings) else Settings()
        name = resolve_output(value.output, self._buzzer_outputs())
        return replace(value, output=name) if name and name != value.output else value

    def _buzzer_outputs(self):
        return outputs(self.pd.state.settings, self.pd.state.objects)

    def _buzzer_enabled(self):
        return self._buzzer_settings().output in self._buzzer_outputs()

    def _buzzer_feedback(self, kind):
        settings = self._buzzer_settings()
        if settings.output and settings.volume and self._buzzer_enabled():
            if getattr(self, '_buzzer_player', None) is None:
                self._buzzer_player = Player(self.pd.subscription)
            self._buzzer_player.play(settings, kind)

    def _save_buzzer(self, values):
        if getattr(self, '_buzzer_save_future', None) is not None:
            raise RuntimeError('Buzzer save already pending')
        if values != getattr(self, '_buzzer_saved', None):
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self._buzzer_save_target = values
                self._panel_flash_lcd = self.lcd
                self._buzzer_save_future = self.lcd.begin_flash_write_verified(
                    self.lcd.BUZZER_SETTINGS_ADDRESS, values.encode())
                self._display_save_message = 'Saving...'
                self._buzzer_values = values
            else:
                self.lcd.save_buzzer_settings(values)
                self._buzzer_values = self._buzzer_saved = values
        else:
            self._buzzer_values = values
        player = getattr(self, '_buzzer_player', None)
        if player is not None:
            player.cancel()

    def _buzzer_rows(self):
        settings = self._buzzer_settings()
        rows = [('Buzzer', settings.output or 'Disabled', False)]
        if self._buzzer_enabled():
            rows.extend((('Volume', str(settings.volume) + '%', True),
                         ('Click tone', TONES[settings.click], True),
                         ('Encoder tone', TONES[settings.encoder], True)))
        return rows

    def _buzzer_display_input(self, event):
        if getattr(self, '_buzzer_save_future', None) is not None:
            return True
        if event == self.ENCODER_DIFF_NO:
            return False
        selection = getattr(self, '_display_selection', 0)
        if selection >= 5 and not self._buzzer_enabled():
            self._display_selection = selection = 4
            self._display_edit = False
        if selection < 4:
            return False
        if event == self.ENCODER_DIFF_ENTER and selection == 4:
            self._buzzer_selection = 0
            self._buzzer_save_error = False
            self._display_edit = False
            self.checkkey = self.BuzzerMenu
            self.Draw_Buzzer_Menu()
            self.lcd.update()
            return True
        if selection >= 5 and getattr(self, '_display_edit', False):
            if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                delta = 1 if event == self.ENCODER_DIFF_CW else -1
                value = self._buzzer_settings()
                field = ('volume', 'click', 'encoder')[selection - 5]
                current = getattr(value, field)
                updated = max(0, min(100, current + delta * 10)) if field == 'volume' else (current + delta) % len(TONES)
                self._buzzer_values = replace(value, **{field: updated})
            elif event == self.ENCODER_DIFF_ENTER:
                try:
                    self._save_buzzer(self._buzzer_settings())
                    self._display_edit = False
                    self._display_save_message = ''
                except (OSError, TimeoutError, T5UIC1ProtocolError):
                    self._display_save_message = 'Not saved. Press to retry'
            self.Draw_Display_Menu()
            self.lcd.update()
            return True
        if selection >= 5 and event == self.ENCODER_DIFF_ENTER:
            self._display_edit = True
            self.Draw_Display_Menu()
            self.lcd.update()
            return True
        return False

    def Draw_Buzzer_Menu(self):
        selected = self._buzzer_settings().output
        names = ('',) + self._buzzer_outputs()
        entries = [('Back', self.ICON_Back, None, None)]
        for name in names:
            checked = name == selected
            painter = self._menu_checkbox_painter(checked)
            entries.append(((name or 'Disabled')[:20], ICON_BUZZER if name else ICON_SOUND_OFF, checked, painter))
        self._buzzer_selection = min(getattr(self, '_buzzer_selection', 0), len(entries) - 1)
        title = 'Buzzer - not saved' if getattr(self, '_buzzer_save_error', False) else 'Buzzer'
        self._draw_list_menu(title, entries, self._buzzer_selection)

    def HMI_Buzzer_Menu(self):
        if getattr(self, '_buzzer_save_future', None) is not None:
            return
        event = self.get_encoder_state()
        names = ('',) + self._buzzer_outputs()
        selection = getattr(self, '_buzzer_selection', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            delta = 1 if event == self.ENCODER_DIFF_CW else -1
            self._buzzer_selection = max(0, min(len(names), selection + delta))
        elif event == self.ENCODER_DIFF_ENTER:
            if selection:
                if selection > len(names):
                    self.Draw_Buzzer_Menu()
                    return
                try:
                    self._save_buzzer(replace(self._buzzer_settings(), output=names[selection - 1]))
                except (OSError, TimeoutError, T5UIC1ProtocolError):
                    self._buzzer_save_error = True
                    self.Draw_Buzzer_Menu()
                    self.lcd.update()
                    return
                self._buzzer_save_error = False
                self._display_save_message = ''
            self._display_selection = 4
            self.checkkey = self.DisplayMenu
            self.Draw_Display_Menu()
            self.lcd.update()
            return
        else:
            return
        self.Draw_Buzzer_Menu()
        self.lcd.update()
