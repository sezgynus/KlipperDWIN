"""Case-light screen rendering and interaction mixin."""

import logging
from concurrent.futures import Future
from ui_events import InputEvent


class CaseLightMixin:
    def Draw_Case_Light_Menu(self):
        self.Clear_Main_Window()
        self.Draw_Title('Case Light')
        self.Draw_Back_First(self.select_light.now == 0)
        self.Draw_Menu_Line(1, self.ICON_CaseLight, 'Light')
        self.Draw_Menu_Line(2, self.ICON_CaseLight, 'Brightness')
        if self.select_light.now:
            self.Draw_Menu_Cursor(self.select_light.now)
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 224, self.MBASE(1),
                             '[X]' if getattr(self, '_case_light_on', False) else '[ ]')
        self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                               self.lcd.Color_White, self.lcd.Color_Bg_Black,
                               3, 208, self.MBASE(2), getattr(self, '_case_light_brightness', 0))
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 232, self.MBASE(2), '%')

    def _sync_case_light_tracking(self):
        screen = getattr(self, 'checkkey', None)
        enabled = screen in (self.CaseLight, self.CaseLightBrightness)
        if screen == self.PowerConfirm and getattr(self, '_power_origin', None) == self.CaseLight:
            enabled = True
        enabled = enabled and getattr(self, '_uart_online', True)
        snapshot = self.pd.subscription.snapshot()
        key = (bool(enabled), snapshot['epoch'], getattr(self, '_uart_epoch', 0))
        if key == getattr(self, '_case_light_tracking_key', None):
            return
        self._case_light_tracking_key = key
        if not enabled and not getattr(self, '_case_light_tracking_active', False):
            return
        self._case_light_tracking_active = enabled
        loop = getattr(self, '_loop', None)
        callback = (lambda: loop.post(InputEvent('case_light_status', 0, key[1], key[2]))) if loop else None
        self.pd.subscription.set_case_light_tracking(enabled, callback)

    def _poll_case_light_state(self, redraw=True):
        if self.checkkey not in (self.CaseLight, self.CaseLightBrightness):
            return False
        state = self.pd.case_light_state()
        if not isinstance(state, tuple) or len(state) != 2:
            return False
        changed = state != (getattr(self, '_case_light_on', None),
                            getattr(self, '_case_light_brightness', None))
        self._case_light_on, self._case_light_brightness = state
        if state[1] > 0:
            self._case_light_restore_brightness = state[1]
        if changed and redraw and self.checkkey == self.CaseLight:
            self.Draw_Case_Light_Menu()
            self.lcd.update()
        return changed

    def _poll_case_light_live(self):
        future = getattr(self, '_case_light_live_future', None)
        epoch = getattr(self, '_case_light_live_epoch', None)
        if epoch is not None and epoch != (self.pd.subscription.snapshot()['epoch'],
                                           getattr(self, '_uart_epoch', 0)):
            if isinstance(future, Future):
                future.cancel()
            self._case_light_live_future = None
            self._case_light_live_pending = None
            self._case_light_live_refresh = False
            self._case_light_live_epoch = None
            return
        if isinstance(future, Future):
            if not future.done():
                return
            if future.cancelled() or future.exception():
                logging.warning('Case light brightness command failed')
            self._case_light_live_future = None
        target = getattr(self, '_case_light_live_pending', None)
        if target is not None:
            self._case_light_live_pending = None
            epoch = (self.pd.subscription.snapshot()['epoch'], getattr(self, '_uart_epoch', 0))
            self._case_light_live_epoch = epoch
            try:
                future = self.pd.set_case_light_brightness(target)
            except ValueError:
                logging.warning('Case light brightness unavailable', exc_info=True)
                future = None
            if isinstance(future, Future):
                self._case_light_live_future = future
                loop = getattr(self, '_loop', None)
                if loop is not None:
                    future.add_done_callback(lambda _done: loop.post(
                        InputEvent('case_light_flush', 0, epoch[0], epoch[1])))
                if not future.done():
                    return
                self._case_light_live_future = None
        if getattr(self, '_case_light_live_refresh', False):
            self._case_light_live_refresh = False
            self._poll_case_light_state()

    def HMI_Case_Light(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_CW:
            self.select_light.inc(3)
            self.Draw_Case_Light_Menu()
        elif event == self.ENCODER_DIFF_CCW:
            self.select_light.dec()
            self.Draw_Case_Light_Menu()
        elif event == self.ENCODER_DIFF_ENTER:
            if self.select_light.now == 0:
                self.checkkey = self.Control
                self.select_control.set(self.CONTROL_CASE_LIGHT)
                self._sync_case_light_tracking()
                self.Draw_Control_Menu()
            elif self.select_light.now == 1:
                self._case_light_live_pending = (0 if getattr(self, '_case_light_on', False)
                                                 else getattr(self, '_case_light_restore_brightness', 100))
                self._poll_case_light_live()
            else:
                self.checkkey = self.CaseLightBrightness
                self._case_light_brightness_target = getattr(self, '_case_light_brightness', 0)
                self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                                       self.lcd.Color_White, self.lcd.Select_Color,
                                       3, 208, self.MBASE(2), self._case_light_brightness_target)
        self.lcd.update()

    def HMI_Case_Light_Brightness(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_ENTER:
            self.checkkey = self.CaseLight
            # After editing, the subscribed pin state becomes authoritative again.
            self._case_light_brightness = self._case_light_brightness_target
            self._case_light_live_refresh = True
            self.Draw_Case_Light_Menu()
            self._poll_case_light_live()
        elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            delta = self._encoder_move_value if event == self.ENCODER_DIFF_CW else -self._encoder_move_value
            previous = self._case_light_brightness_target
            self._case_light_brightness_target = max(0, min(100, previous + delta))
            self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                                   self.lcd.Color_White, self.lcd.Select_Color,
                                   3, 208, self.MBASE(2), self._case_light_brightness_target)
            if previous != self._case_light_brightness_target:
                self._case_light_live_pending = self._case_light_brightness_target
                self._poll_case_light_live()
        self.lcd.update()
