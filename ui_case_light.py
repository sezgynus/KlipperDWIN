"""Case-light screen rendering and interaction mixin."""

import logging
import time
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

    def _poll_case_light_query(self):
        if not getattr(self, '_case_light_query_pending', False):
            return False
        import re
        while True:
            response = self.pd.pop_gcode_response()
            if response is None:
                return False
            match = re.search(r'Light is (ON|OFF),\s*Brightness=(\d+)', response, re.IGNORECASE)
            if match:
                self._case_light_on = match.group(1).upper() == 'ON'
                raw_brightness = max(0, min(255, int(match.group(2))))
                self._case_light_brightness = int(round(raw_brightness * 100.0 / 255.0))
                self._case_light_query_pending = False
                if self.checkkey == self.CaseLight:
                    self.Draw_Case_Light_Menu()
                    self.lcd.update()
                return True

    def _refresh_case_light_state(self):
        # Commit displayed light state only after a successful command and a
        # fresh M355 query response; never optimistically change the UI.
        self._case_light_query_pending = True
        self.pd.query_case_light()

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
                future = self.pd.sendGCodeObserved('M355 P{}'.format(int(round(target * 255.0 / 100.0))))
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
            self._case_light_query_pending = True
            self.pd.query_case_light(report_error=False)
            self._case_light_next_query = time.monotonic() + 2
        elif (self.checkkey == self.CaseLight
                and not getattr(self, '_case_light_query_pending', False)
                and time.monotonic() >= getattr(self, '_case_light_next_query', 0)):
            self._case_light_query_pending = True
            self.pd.query_case_light(report_error=False)
            self._case_light_next_query = time.monotonic() + 2

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
                self.Draw_Control_Menu()
            elif self.select_light.now == 1:
                target = not getattr(self, '_case_light_on', False)
                self._action(
                    "Case light",
                    lambda: self.pd.sendGCode('M355 S{}'.format(1 if target else 0)),
                    on_accept=self._refresh_case_light_state)
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
            # Keep the last handwheel value until a fresh M355 response arrives.
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
