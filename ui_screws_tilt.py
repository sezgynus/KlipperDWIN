from lcd_resources import ICON_CALCULATE_LEVEL
"""Marlin ProUI-style four-corner result view with Klipper turn instructions."""


class ScrewsTiltMixin:
    def Draw_Screws_Menu(self):
        self._draw_list_menu('Screws Tilt Adjust', [
            ('Back', self.ICON_Back, None, None),
            ('Calculate', ICON_CALCULATE_LEVEL, None, None)],
            getattr(self, '_screws_selection', 0))
        self.lcd.update()

    def _screws_text(self, text, y, color=None, font=None, width=8):
        self.lcd.draw_text(False, False, font or self.lcd.font8x16,
                             self.lcd.Color_White if color is None else color,
                             self.lcd.Color_Bg_Black, max(0, (272 - len(text) * width) // 2), y, text)

    def _screws_corner(self, key, x, y, value, base_z, clear=False):
        # Update the local 49x49 corner without erasing other screw markers.
        # The reference grid runs through each circle centre.
        if clear:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    max(0, x - 24), max(0, y - 24),
                                    min(271, x + 24), min(359, y + 24))
            self.lcd.draw_line(0x7BEF, max(25, x - 24), y, min(247, x + 24), y)
            self.lcd.draw_line(0x7BEF, x, max(55, y - 24), x, min(277, y + 24))
            ty = 62 if y < 166 else 235
            # Labels sit inward of each corner and must not leave old text.
            x0, x1 = (52, 150) if x < 136 else (120, 221)
            for row in (ty, ty + 20):
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                        x0, row, x1, row + 15)
        delta = 0 if value is None else value['z'] - base_z
        color = (0x7BEF if value is None else 0x07E0 if abs(delta) < .025
                 else 0xF800 if delta > 0 else 0x001F)
        radius = 14 if value is None else max(5, min(23, round(14 + delta * 45)))
        self._draw_mesh_disk(x, y, color, radius)
        labels = (('...',) if value is None else ('Base',)
                  if value['is_base'] else (value['sign'], value['adjust']))
        ty = 62 if y < 166 else 235
        for line, label in enumerate(labels):
            tx = 52 if x < 136 else 220 - len(label) * 8
            self.lcd.draw_text(False, False, self.lcd.font8x16,
                               self.lcd.Color_White, self.lcd.Color_Bg_Black,
                               tx, ty + line * 20, label)

    def _screws_center(self, session):
        if session.pending:
            self._screws_text(session.message, 140)
        elif session.phase != 'complete':
            self._screws_text(session.message[:32], 140,
                              font=self.lcd.font6x12, width=6)
        elif session.leveled:
            self._screws_text('Corners leveled', 140, color=0x07E0)
            self._screws_text('Tolerance achieved!', 160, color=0x07E0)
        elif session.recommendation in session.results:
            value = session.results[session.recommendation]
            name = next(c[3] for c in session.corners
                        if c[0] == session.recommendation)
            self._screws_text('Adjust ' + name, 140)
            self._screws_text(value['sign'] + ' ' + value['adjust'], 166,
                              font=self.lcd.font10x20, width=10)

    def Draw_Screws_Result(self):
        session = self.pd.screws_tilt
        frame = (id(self.lcd), id(session), session.epoch, tuple(session.corners))
        cache = getattr(self, '_screws_result_cache', None)
        complete_frame = cache is None or cache['frame'] != frame
        if complete_frame:
            self.Clear_Main_Window()
            self.Draw_Title('Screws Tilt Adjust')
            self.lcd.draw_rectangle(0, 0x7BEF, 25, 55, 247, 277)
            cache = {'frame': frame, 'corners': {}, 'center': None, 'button': None}
            self._screws_result_cache = cache
        base_z = next((v['z'] for v in session.results.values()
                       if v['is_base']), 0)
        changed = complete_frame
        for key, x, y, _ in session.corners:
            value = session.results.get(key)
            sig = (x, y, base_z, None if value is None else
                   (value['z'], value['is_base'], value['sign'], value['adjust']))
            previous = cache['corners'].get(key)
            if sig != previous:
                self._screws_corner(key, x, y, value, base_z,
                                    clear=previous is not None)
                cache['corners'][key] = sig
                changed = True
        recommendation = session.results.get(session.recommendation)
        center = (session.phase, session.message, bool(session.pending),
                  session.leveled, session.recommendation,
                  None if recommendation is None else
                  (recommendation['sign'], recommendation['adjust']))
        if center != cache['center']:
            if cache['center'] is not None:
                # Clearing the centered message also erases the grid's vertical
                # edges at x=25 and x=247. Restore only those two segments,
                # keeping the frame continuous without redrawing the screen.
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                        12, 123, 260, 188)
                self.lcd.draw_line(0x7BEF, 25, 123, 25, 188)
                self.lcd.draw_line(0x7BEF, 247, 123, 247, 188)
            self._screws_center(session)
            cache['center'] = center
            changed = True
        has_button = not session.pending
        if has_button != cache['button']:
            if cache['button'] is not None:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                        86, 305, 186, 343)
            if has_button:
                self.lcd.draw_rectangle(1, 0x03B5, 86, 305, 186, 343)
                self._screws_text('Continue', 316)
            cache['button'] = has_button
            changed = True
        if changed:
            self.lcd.update()

    def HMI_Screws_Tilt(self):
        event = self.get_encoder_state()
        if self.checkkey == self.ScrewsTiltResult:
            if not self.pd.screws_tilt.pending and event == self.ENCODER_DIFF_ENTER:
                self.checkkey = self.ScrewsTiltMenu
                self._screws_result_cache = None
                self.Draw_Screws_Menu()
            return
        selection = getattr(self, '_screws_selection', 0)
        if event == self.ENCODER_DIFF_CW:
            self._screws_selection = min(1, selection + getattr(self, '_rotation_steps', 1))
        elif event == self.ENCODER_DIFF_CCW:
            self._screws_selection = max(0, selection - getattr(self, '_rotation_steps', 1))
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self._return_to_mesh_menu()
                return
            try:
                self.pd.screws_tilt.start()
            except ValueError as error:
                self._show_message(str(error))
                return
            self.checkkey = self.ScrewsTiltResult
            self._screws_result_cache = None
            self.Draw_Screws_Result()
            return
        if event != self.ENCODER_DIFF_NO:
            self.Draw_Screws_Menu()

    def _poll_screws_tilt(self):
        session = self.pd.screws_tilt
        session.update()
        if self.checkkey == self.ScrewsTiltResult:
            # The painter compares per-corner signatures. Poll even when phase
            # and message stay the same, to catch a changed probe result.
            self.Draw_Screws_Result()
