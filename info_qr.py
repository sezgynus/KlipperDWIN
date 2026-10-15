"""Copy the visible project QR region from shared picture Area 1."""
from shared_artwork import PICTURE_ID
from shared_artwork_layout import QR_BOX

PROJECT_URL = 'https://github.com/sezgynus/Petrel'


def extra_info_rows():
    """QR height plus two spacer rows before the update control."""
    return (QR_BOX[3] - QR_BOX[1] + 23) // 24 + 2


def draw_project_qr(lcd, y, top=92, bottom=360):
    """Clip both source and destination; never draw over surrounding rows."""
    x0, y0, x1, y1 = QR_BOX
    first, last = max(y, top), min(y + y1 - y0, bottom)
    if first >= last:
        return
    lcd.ensure_cached_picture(PICTURE_ID)
    x = (lcd.DWIN_WIDTH - (x1-x0)) // 2
    lcd.copy_cache1(x0, y0 + first - y, x1 - 1, y0 + last - y - 1, x, first)
