"""Copy the visible project QR region from shared picture Area 1."""
from shared_artwork import PICTURE_ID, QR_BOX

PROJECT_URL = 'https://github.com/sezgynus/Petrel'


def draw_project_qr(lcd, y, top=92, bottom=360):
    """Clip both source and destination; never draw over surrounding rows."""
    x0, y0, x1, y1 = QR_BOX
    first, last = max(y, top), min(y + y1 - y0, bottom)
    if first >= last:
        return
    lcd.ensure_cached_picture(PICTURE_ID)
    lcd.copy_cache1(x0, y0 + first - y, x1 - 1, y0 + last - y - 1, 52, first)
