"""Shared library-backed spool with independently changing filament and percentage."""

from lcd_resources import ICON_LIBRARY_ID, ICON_SPOOL_EMPTY, SPOOL_LEFT_FLANGES, SPOOL_RIGHT_FLANGES


class SpoolView:
    HEIGHT = 52
    HUB_COLOR = 0x8410
    HUB_HEIGHT = 12
    FULL_HEIGHT = 50

    def __init__(self, lcd, x, y, width=42, *, color=0x8410,
                 remaining_percent=None, background=0x0000, label_width=None):
        self.lcd = lcd
        self.x, self.y = x, y
        self.width = max(1, min(42, width))
        self.color = color
        self.remaining_percent = remaining_percent
        self.background = background
        self.label_width = self.width if label_width is None else label_width
        self._frame = None
        self._painted = None

    def invalidate(self):
        """Call when the parent canvas has been cleared."""
        self._frame = self._painted = None

    @staticmethod
    def _text_color(color):
        red, green, blue = color >> 11, (color >> 5) & 63, color & 31
        luminance = (299 * red * 255 // 31 + 587 * green * 255 // 63
                     + 114 * blue * 255 // 31) // 1000
        return 0x0000 if luminance >= 140 else 0xFFFF

    def draw(self):
        percent = self.remaining_percent
        percent = None if percent is None else max(0, min(100, int(round(percent))))
        text = '--' if percent is None else '%d%%' % percent
        # Unknown quantity keeps its color visible without inventing a percentage.
        height = self.FULL_HEIGHT if percent is None else (
            self.HUB_HEIGHT + 2 * round((self.FULL_HEIGHT - self.HUB_HEIGHT) * percent / 200))
        color = self.HUB_COLOR if percent == 0 else self.color
        frame = (id(self.lcd), self.x, self.y, self.width, self.background, self.label_width)
        painted = (height, color, text if self.label_width >= 28 else None)
        if frame != self._frame:
            if self.width == 42:
                self.lcd.show_icon(ICON_LIBRARY_ID, ICON_SPOOL_EMPTY, self.x, self.y)
            else:
                # Native icon commands cannot crop: use only wooden flange
                # JPEGs, preserving the shared dynamic filament component.
                flange = min(max(1, round(self.width / 6)), max(0, (self.width - 1) // 2))
                self.lcd.draw_rectangle(1, self.background, self.x, self.y,
                                        self.x + self.width - 1, self.y + self.HEIGHT - 1)
                if flange:
                    self.lcd.show_icon(ICON_LIBRARY_ID, SPOOL_LEFT_FLANGES[flange],
                                       self.x, self.y)
                    self.lcd.show_icon(ICON_LIBRARY_ID, SPOOL_RIGHT_FLANGES[flange],
                                       self.x + self.width - flange, self.y)
            self._frame = frame
            self._painted = None
        if painted == self._painted:
            return False

        flange = (7 if self.width == 42 else
                  min(max(1, round(self.width / 6)), max(0, (self.width - 1) // 2)))
        left, right = self.x + flange, self.x + self.width - flange - 1
        body_changed = self._painted is None or self._painted[:2] != painted[:2]
        if body_changed:
            self.lcd.draw_rectangle(1, self.background, left, self.y + 1, right, self.y + 50)
            top = self.y + (self.HEIGHT - height) // 2
            self.lcd.draw_rectangle(1, color, left, top, right, top + height - 1)

        # Preserve the existing compact-lane policy: never overlap another spool.
        if self.label_width >= 28:
            center = self.x + self.width // 2
            text_y = self.y + 20
            if right - left + 1 < 24:
                # Narrow lanes need the same black backing as the previous UI.
                self.lcd.draw_rectangle(1, self.background,
                    center - 14, text_y, center + 13, text_y + 11)
                foreground = 0xFFFF
            else:
                if not body_changed:
                    length = max(len(text), len(self._painted[2]))
                    self.lcd.draw_rectangle(1, color, center - 3 * length,
                        text_y, center + 3 * length - 1, text_y + 11)
                foreground = self._text_color(color)
            self.lcd.draw_text(False, False, self.lcd.font6x12, foreground,
                self.background, center - 3 * len(text), text_y, text)
        self._painted = painted
        return True
