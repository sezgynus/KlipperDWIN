"""Verified Picture Flash slot 1, shared by cached UI artwork."""
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import time

SOURCE = Path(__file__).resolve().parent / 'assets/petrel_shared.jpg'
PICTURE_ID = 1
ADDRESS = 0x0150
SIZE = 40
MAGIC = b'PETPAGE1'
from shared_artwork_layout import QR_BOX, JPEG_SHA256
_attempts = set()


def sync(lcd, source=SOURCE, *, force=False):
    from PIL import Image, JpegImagePlugin
    data = Path(source).read_bytes()
    if len(data) > 32767:
        raise ValueError('Shared JPEG must fit before SRAM address 0x7FFF')
    with Image.open(BytesIO(data)) as image:
        if (image.format != 'JPEG' or image.size != (480, 272)
                or image.info.get('progressive') or JpegImagePlugin.get_sampling(image) != 2):
            raise ValueError('Shared artwork must be a baseline 480x272 4:2:0 JPEG')
        image.load()
    digest = hashlib.sha256(data).digest()
    if digest.hex() != JPEG_SHA256:
        raise ValueError('Shared JPEG/layout mismatch; regenerate with tools/pack_shared_artwork.py')
    record = MAGIC + digest
    if not force and lcd.read_flash(ADDRESS, SIZE) == record:
        return False
    if record in _attempts:
        raise RuntimeError('Shared Picture Flash write already failed; restart to retry')
    logging.info('Uploading shared UI artwork to picture slot 1')
    from lcd_resources import ICON_LIBRARY_ID
    lcd.configure_animation(0, False, ICON_LIBRARY_ID, 250, 254, 0, 320, 10)
    lcd.write_sram(0, data)
    lcd.serial.flush()
    time.sleep(.1)
    _attempts.add(record)
    lcd.store_sram_as_picture(PICTURE_ID, timeout=5)
    lcd.write_flash(ADDRESS, record)
    if lcd.read_flash(ADDRESS, SIZE) != record:
        raise RuntimeError('Shared artwork metadata verification failed')
    _attempts.discard(record)
    return True
