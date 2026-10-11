#!/usr/bin/env python3
"""Force reload the managed JPEG icon sources after reinstalling LCD resources."""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from icon_library import sync_library
from tools.flash_icon_library import ManualDisplay
from tools.lcd_connection import configured_port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default=configured_port())
    args = parser.parse_args()
    if not args.serial_port:
        parser.error('UART not configured')
    state = subprocess.run(['systemctl', 'is-active', 'KlipperDWIN.service'],
                           capture_output=True, text=True).stdout.strip()
    if state not in ('inactive', 'failed', 'unknown'):
        parser.error('Stop KlipperDWIN.service first')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    lcd = ManualDisplay(args.serial_port)
    try:
        sync_library(lcd, force=True, automatic=False)
    finally:
        lcd.close()


if __name__ == '__main__':
    main()
