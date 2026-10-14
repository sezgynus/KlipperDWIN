"""Graphite background colors and icon compositing policy."""

BACKGROUND_COLOR = 0x2125
# Expand the LCD RGB565 value exactly, so opaque JPEG backing matches the UI.
_r, _g, _b = BACKGROUND_COLOR >> 11, (BACKGROUND_COLOR >> 5) & 63, BACKGROUND_COLOR & 31
BACKGROUND_RGB = ((_r << 3) | (_r >> 2), (_g << 2) | (_g >> 4), (_b << 3) | (_b >> 2))


def show_icon(lcd, library, icons, x, y):
    # Filter the source JPEG's black backing to preserve the current surface.
    lcd.show_icon(library, icons, x, y, background=False, enhanced=True)
