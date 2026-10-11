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
from tools.pack_icon_library import BLOCK_SIZE, entries, validate_block_layout
from tools.reload_atlases import configured_port


class ManualDisplay(T5UIC1Display):
    def _startup_sync_atlases(self, **kwargs):
        return False


def validate_upload(data, allow_cross_block=False):
    if not allow_cross_block:
        validate_block_layout(data, ICON_LIBRARY_ID)
    else:
        if len(data) > (16 - ICON_LIBRARY_ID) * BLOCK_SIZE:
            raise ValueError('Icon library exceeds available Picture Flash')
        if not list(entries(data)):
            raise ValueError('No icon entries')


def upload(lcd, data, *, allow_cross_block=False):
    validate_upload(data, allow_cross_block)
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
    parser.add_argument('--file', type=Path, help='Use an explicitly selected ICO file')
    parser.add_argument('--sha256', help='Required hash for diagnostic files')
    parser.add_argument('--allow-cross-block', action='store_true',
                        help='Diagnostic only: allow JPEGs spanning Flash blocks; requires --file and --sha256')
    args = parser.parse_args()
    if not args.serial_port:
        parser.error('UART not configured; specify --serial-port')
    if args.allow_cross_block and (not args.file or not args.sha256):
        parser.error('--allow-cross-block requires --file and --sha256')
    state = subprocess.run(['systemctl', 'is-active', 'KlipperDWIN.service'],
                           capture_output=True, text=True).stdout.strip()
    if state not in ('inactive', 'failed', 'unknown'):
        parser.error('Stop KlipperDWIN.service before uploading')
    root = Path(__file__).resolve().parent.parent
    path = args.file or (root / 'assets/emulator' / ICON_LIBRARY_FILENAME)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if args.sha256 and digest.lower() != args.sha256.lower():
        parser.error(f'SHA256 mismatch: {digest}; no UART opened')
    validate_upload(data, args.allow_cross_block)
    print(f'{path}: {len(data)} bytes; SHA256 {digest}')
    if args.allow_cross_block:
        print('DIAGNOSTIC: cross-block icon layout; inspect icons before restoring bundled library.')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    lcd = ManualDisplay(args.serial_port)
    try:
        upload(lcd, data, allow_cross_block=args.allow_cross_block)
        print('Upload acknowledged. Check Leveling and Cooldown on the physical display.')
    finally:
        lcd.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'STOPPED: {error}. Service remains stopped; no automatic retry.', file=sys.stderr)
        sys.exit(1)
