"""Build and synchronize the managed JPEG icon library."""
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import re
import struct
import time
import zlib

from PIL import Image
from lcd_resources import ICON_LIBRARY_ID

BLOCK_SIZE = 32768
USABLE_SIZE = BLOCK_SIZE - 1
DIRECTORY_SIZE = 4096
SOURCE_DIRECTORY = Path(__file__).resolve().parent / 'assets/icons'
METADATA_ADDRESS = 0x0200
METADATA_SIZE = 384
MAGIC = b'KDWICO01'
MAX_BLOCKS = 16 - ICON_LIBRARY_ID
_ATTEMPTS = set()


def pack_records(records):
    """Best-fit decreasing; directory IDs are independent of physical order."""
    blocks = [bytearray(BLOCK_SIZE)]
    used = [DIRECTORY_SIZE]
    if not records:
        raise ValueError('Icon source directory is empty')
    seen = set()
    for index, width, height, payload in sorted(records, key=lambda r: (-len(r[3]), r[0])):
        if index in seen or not 0 <= index <= 255:
            raise ValueError(f'Duplicate or invalid icon ID: {index}')
        seen.add(index)
        if not 0 < len(payload) <= USABLE_SIZE:
            raise ValueError(f'Icon {index} exceeds usable block capacity')
        fits = [i for i, end in enumerate(used) if USABLE_SIZE - end >= len(payload)]
        if fits:
            block = min(fits, key=lambda i: (USABLE_SIZE - used[i] - len(payload), i))
        else:
            if len(blocks) >= MAX_BLOCKS:
                raise ValueError('Icons exceed reserved Picture Flash slots 7..15')
            block = len(blocks)
            blocks.append(bytearray(BLOCK_SIZE))
            used.append(0)
        start = used[block]
        offset = block * BLOCK_SIZE + start
        blocks[block][start:start + len(payload)] = payload
        used[block] += len(payload)
        entry = struct.pack('>HHI', width, height, offset) + len(payload).to_bytes(3, 'big') + bytes(5)
        blocks[0][index * 16:(index + 1) * 16] = entry
    return b''.join(blocks)


def build_library(directory=SOURCE_DIRECTORY):
    records = []
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg'):
            continue
        match = re.fullmatch(r'(\d{1,3})(?:[-_].*)?', path.stem)
        if not match:
            raise ValueError(f'JPEG filename must start with icon ID: {path.name}')
        payload = path.read_bytes()
        with Image.open(BytesIO(payload)) as image:
            if image.format != 'JPEG' or image.info.get('progressive') or image.info.get('progression'):
                raise ValueError(f'Use baseline JPEG: {path.name}')
            image.load()
            width, height = image.size
        records.append((int(match[1]), width, height, payload))
    return pack_records(records)


def metadata(hashes):
    body = MAGIC + bytes((ICON_LIBRARY_ID, len(hashes)))
    body += b''.join(hashes) + bytes(32 * (MAX_BLOCKS - len(hashes)))
    body = body.ljust(METADATA_SIZE - 4, b'\x00')
    return body + zlib.crc32(body).to_bytes(4, 'big')


def parse_metadata(raw):
    if len(raw) != METADATA_SIZE or raw[:8] != MAGIC or raw[8] != ICON_LIBRARY_ID:
        return []
    if not 1 <= raw[9] <= MAX_BLOCKS or int.from_bytes(raw[-4:], 'big') != zlib.crc32(raw[:-4]):
        return []
    return [raw[10 + i * 32:42 + i * 32] for i in range(raw[9])]


def sync_library(lcd, *, directory=SOURCE_DIRECTORY, force=False, automatic=True):
    data = build_library(directory)
    blocks = [data[i:i + BLOCK_SIZE] for i in range(0, len(data), BLOCK_SIZE)]
    wanted = [hashlib.sha256(block).digest() for block in blocks]
    stored_metadata = lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE)
    current = parse_metadata(stored_metadata)
    changed = [i for i, digest in enumerate(wanted)
               if force or i >= len(current) or current[i] != digest]
    if not changed:
        logging.info('Icon library: unchanged; no Flash writes')
        return False
    lcd.configure_animation(0, False, ICON_LIBRARY_ID, 250, 254, 0, 320, 10)
    # Whenever any payload changes, commit the directory last, even if its
    # bytes happen to match. Its checkpoint denotes a completed upload.
    current = (current + [bytes(32)] * len(wanted))[:len(wanted)]
    current[0] = bytes(32)

    def checkpoint():
        nonlocal stored_metadata
        raw = metadata(current)
        if raw == stored_metadata:
            return
        lcd.write_flash(METADATA_ADDRESS, raw)
        if lcd.read_flash(METADATA_ADDRESS, METADATA_SIZE) != raw:
            raise RuntimeError('Icon metadata verification failed')
        stored_metadata = raw

    checkpoint()
    for index in [i for i in changed if i != 0] + [0]:
        slot = ICON_LIBRARY_ID + index
        key = (slot, wanted[index])
        if automatic and key in _ATTEMPTS:
            raise RuntimeError('Automatic icon rewrite blocked after an earlier failed attempt; restart or reload explicitly')
        logging.info('Icon library: uploading slot %d (%d/%d)', slot, index + 1, len(blocks))
        # Never send a write that includes SRAM address 0x7FFF. The copied
        # Flash byte is unused padding and no directory/JPEG references it.
        lcd.write_sram(0, blocks[index][:USABLE_SIZE])
        lcd.serial.flush()
        time.sleep(0.1)
        if automatic:
            _ATTEMPTS.add(key)
        lcd.store_sram_as_picture(slot, timeout=5)
        current[index] = wanted[index]
        checkpoint()
        _ATTEMPTS.discard(key)
    logging.info('Icon library: upload complete')
    return True
