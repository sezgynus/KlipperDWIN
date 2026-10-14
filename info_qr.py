"""Opaque managed project QR with bounded display-area translation."""
from lcd_resources import ICON_LIBRARY_ID, ICON_PROJECT_QR

PROJECT_URL = 'https://github.com/sezgynus/Petrel'
def draw_project_qr(lcd, y, top=92, bottom=360):
    """Render QR safely, then translate inside the menu with native area move."""
    # The opaque icon must be fully on-screen. Its 168px box stays inside
    # the menu before translating; move mode 1 fills exposed pixels (no wrap).
    if y >= bottom or y + 168 <= top:
        return
    anchor = top
    # Never filter black QR modules: the entire white-backed symbol is opaque.
    lcd.show_icon(ICON_LIBRARY_ID, ICON_PROJECT_QR, 52, anchor,
                  background=True, enhanced=False)
    distance = y - anchor
    if distance:
        lcd.move_area(1, 3 if distance > 0 else 2, abs(distance),
                      lcd.Color_Bg_Black, 52, top, 219, bottom - 1)
