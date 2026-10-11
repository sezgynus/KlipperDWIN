#!/usr/bin/env python3
"""Manually upload the bundled icon library with the display service stopped."""
import argparse
import hashlib
import logging
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lcd_resources import ICON_LIBRARY_FILENAME, ICON_LIBRARY_ID
from t5uic1_driver import T5UIC1Display
from tools.pack_icon_library import BLOCK_SIZE, validate_block_layout
from tools.reload_atlases import configured_port


class ManualDisplay(T5UIC1Display):
    def _startup_sync_atlases(self, **kwargs):
        return False


def upload(lcd, data):
    validate_block_layout(data, ICON_LIBRARY_ID)
    count = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
    lcd.set_animation_mask(0)
    # Commit the new directory only after every payload block is acknowledged.
    for index in list(range(1, count)) + [0]:
        slot = ICON_LIBRARY_ID + index
        chunk = data[index * BLOCK_SIZE:(index + 1) * BLOCK_SIZE].ljust(BLOCK_SIZE, b'\x00')
        print(f'Slot {slot}: uploading...', flush=True)
        lcd.write_sram(0, chunk)
        lcd.serial.flush()
        time.sleep(0.1)
        lcd.store_sram_as_picture(slot, timeout=5)
        print(f'Slot {slot}: panel acknowledged write.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default=configured_port())
    args = parser.parse_args()
    if not args.serial_port:
        parser.error('UART not configured; specify --serial-port')
    state = subprocess.run(['systemctl', 'is-active', 'KlipperDWIN.service'],
                           capture_output=True, text=True).stdout.strip()
    if state not in ('inactive', 'failed', 'unknown'):
        parser.error('Stop KlipperDWIN.service before uploading')
    root = Path(__file__).resolve().parent.parent
    data = (root / 'assets/emulator' / ICON_LIBRARY_FILENAME).read_bytes()
    validate_block_layout(data, ICON_LIBRARY_ID)
    print(f'{ICON_LIBRARY_FILENAME}: {len(data)} bytes; SHA256 {hashlib.sha256(data).hexdigest()}')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    lcd = ManualDisplay(args.serial_port)
    try:
        upload(lcd, data)
        print('Upload acknowledged. Check Leveling and Cooldown on the physical display.')
    finally:
        lcd.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'STOPPED: {error}. Service remains stopped; no automatic retry.', file=sys.stderr)
        sys.exit(1)
