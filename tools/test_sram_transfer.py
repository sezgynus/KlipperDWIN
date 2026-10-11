#!/usr/bin/env python3
"""Check small SRAM transfers without writing Picture Flash or Data Flash."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.flash_icon_library import ManualDisplay
from tools.reload_atlases import configured_port


class TracePort:
    """Keep raw responses even if the protocol parser rejects them."""
    def __init__(self, port):
        self.port = port
        self.received = bytearray()

    def __getattr__(self, name):
        return getattr(self.port, name)

    def read(self, size=1):
        data = self.port.read(size)
        self.received.extend(data)
        return data


def check_range(lcd, address, length, timeout):
    print(f'TEST SRAM 0x{address:04X}..0x{address + length - 1:04X} ({length} bytes)', flush=True)
    # Do not overwrite memory unless its original contents can be read first.
    original = lcd.read_sram(address, length, timeout=timeout)
    pattern = bytes((i * 73 + address + 19) & 255 for i in range(length))
    try:
        lcd.write_sram(address, pattern)
        lcd.serial.flush()
        time.sleep(0.1)
        actual = lcd.read_sram(address, length, timeout=timeout)
        if actual != pattern:
            mismatches = [(address + i, expected, found)
                          for i, (expected, found) in enumerate(zip(pattern, actual))
                          if expected != found]
            raise RuntimeError(f'Data mismatch: {mismatches[:8]}; lengths {len(pattern)}/{len(actual)}')
    finally:
        lcd.write_sram(address, original)
        lcd.serial.flush()
        time.sleep(0.1)
    if lcd.read_sram(address, length, timeout=timeout) != original:
        raise RuntimeError('Original SRAM contents did not verify after restoration')
    print('PASS: transfer and restoration match byte for byte.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default=configured_port())
    parser.add_argument('--timeout', type=float, default=3)
    args = parser.parse_args()
    if not args.serial_port or args.timeout <= 0:
        parser.error('Configure UART and use a positive timeout')
    state = subprocess.run(['systemctl', 'is-active', 'KlipperDWIN.service'],
                           capture_output=True, text=True).stdout.strip()
    if state not in ('inactive', 'failed', 'unknown'):
        parser.error('Stop KlipperDWIN.service first')
    lcd = ManualDisplay(args.serial_port)
    trace = TracePort(lcd.serial)
    lcd.serial = trace
    try:
        for address, length in ((0, 1), (0, 16), (0x70, 32), (0x7FC0, 63), (0x7FFF, 1)):
            trace.received.clear()
            try:
                check_range(lcd, address, length, args.timeout)
            except Exception:
                print('RAW RX (last 512 bytes):', trace.received[-512:].hex(' ') or '(no bytes)', flush=True)
                print('Queued parsed frames:', list(lcd._frames), flush=True)
                print('Unparsed RX:', lcd._rx.hex(' ') or '(empty)', flush=True)
                raise
        print('PASS: small SRAM transfers verified. Full-block transfer and Picture Flash remain untested.')
    finally:
        lcd.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'STOPPED: {error}. No Flash write commands were sent.', file=sys.stderr)
        sys.exit(1)
