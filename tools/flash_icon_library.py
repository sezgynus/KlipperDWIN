#!/usr/bin/env python3
"""Manually upload the bundled icon library with the display service stopped."""
import argparse
import hashlib
import logging
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lcd_resources import ICON_LIBRARY_FILENAME, ICON_LIBRARY_ID
from t5uic1_driver import T5UIC1Display
from tools.pack_icon_library import BLOCK_SIZE, entries, validate_block_layout
from tools.lcd_connection import configured_port


class ManualDisplay(T5UIC1Display):
    def _startup_sync_icons(self):
        return False


def validate_upload(data, allow_cross_block=False):
    if not allow_cross_block:
        validate_block_layout(data, ICON_LIBRARY_ID)
    else:
        if len(data) > (16 - ICON_LIBRARY_ID) * BLOCK_SIZE:
            raise ValueError('Icon library exceeds available Picture Flash')
        if not list(entries(data)):
            raise ValueError('No icon entries')


def upload(lcd, data, *, allow_cross_block=False, rewrite_last_byte=False,
           post_ack_delay=0):
    if not math.isfinite(post_ack_delay) or not 0 <= post_ack_delay <= 10:
        raise ValueError('Post-ACK delay must be finite and within 0..10 seconds')
    validate_upload(data, allow_cross_block)
    count = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
    lcd.set_animation_mask(0)
    # Commit the new directory only after every payload block is acknowledged.
    for index in list(range(1, count)) + [0]:
        slot = ICON_LIBRARY_ID + index
        chunk = data[index * BLOCK_SIZE:(index + 1) * BLOCK_SIZE].ljust(BLOCK_SIZE, b'\x00')
        print(f'Slot {slot}: uploading...', flush=True)
        lcd.write_sram(0, chunk)
        if rewrite_last_byte:
            # Diagnostic: separate the final-byte write from the 128-byte burst.
            lcd.serial.flush()
            time.sleep(0.1)
            lcd.write_sram(BLOCK_SIZE - 1, chunk[-1:])
            print(f'Slot {slot}: separate 0x7FFF write = {chunk[-1]:02X}', flush=True)
        lcd.serial.flush()
        time.sleep(0.1)
        lcd.store_sram_as_picture(slot, timeout=5)
        print(f'Slot {slot}: panel acknowledged write.', flush=True)
        if post_ack_delay:
            print(f'Slot {slot}: waiting {post_ack_delay:g} seconds after ACK...', flush=True)
            time.sleep(post_ack_delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default=configured_port())
    parser.add_argument('--file', type=Path, help='Use an explicitly selected ICO file')
    parser.add_argument('--sha256', help='Required hash for diagnostic files')
    parser.add_argument('--allow-cross-block', action='store_true',
                        help='Diagnostic only: allow JPEGs spanning Flash blocks; requires --file and --sha256')
    parser.add_argument('--rewrite-last-byte', action='store_true',
                        help='Diagnostic: write SRAM address 0x7FFF again in a separate one-byte command')
    parser.add_argument('--post-ack-delay', type=float, default=0,
                        help='Diagnostic: extra wait after every Picture Flash ACK, in seconds (0..10)')
    args = parser.parse_args()
    if not args.serial_port:
        parser.error('UART not configured; specify --serial-port')
    if not math.isfinite(args.post_ack_delay) or not 0 <= args.post_ack_delay <= 10:
        parser.error('--post-ack-delay must be finite and within 0..10 seconds')
    if args.allow_cross_block and (not args.file or not args.sha256):
        parser.error('--allow-cross-block requires --file and --sha256')
    state = subprocess.run(['systemctl', 'is-active', 'KlipperDWIN.service'],
                           capture_output=True, text=True).stdout.strip()
    if state not in ('inactive', 'failed', 'unknown'):
        parser.error('Stop KlipperDWIN.service before uploading')
    root = Path(__file__).resolve().parent.parent
    path = args.file or (root / 'assets/emulator' / ICON_LIBRARY_FILENAME)
    if args.file:
        data = path.read_bytes()
    else:
        from icon_library import build_library
        data = build_library(root / 'assets/icons')
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
        upload(lcd, data, allow_cross_block=args.allow_cross_block,
               rewrite_last_byte=args.rewrite_last_byte, post_ack_delay=args.post_ack_delay)
        print('Upload acknowledged. Check Leveling and Cooldown on the physical display.')
    finally:
        lcd.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'STOPPED: {error}. Service remains stopped; no automatic retry.', file=sys.stderr)
        sys.exit(1)
