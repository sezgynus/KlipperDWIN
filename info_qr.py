"""Project QR uses native rendering and bounded display-area translation.
"""

PROJECT_URL = 'https://github.com/sezgynus/KlipperDWIN'
def draw_project_qr(lcd, y, top=92, bottom=360):
    """Render QR safely, then translate inside the menu with native area move."""
    # Native QR must be fully on-screen. Its reserved 168px box stays inside
    # the menu before translating; move mode 1 fills exposed pixels (no wrap).
    if y >= bottom or y + 168 <= top:
        return
    anchor = top
    lcd.draw_rectangle(1, lcd.Color_White, 52, anchor, 219, anchor + 167)
    lcd.draw_qr(64, anchor + 12, 3, PROJECT_URL)
    distance = y - anchor
    if distance:
        lcd.move_area(1, 3 if distance > 0 else 2, abs(distance),
                      lcd.Color_Bg_Black, 52, top, 219, bottom - 1)
