#!/usr/bin/env python3
"""Repack a DWIN ICO without splitting JPEG icons across Flash blocks."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BLOCK_SIZE = 32768
DIRECTORY_SIZE = 4096


def entries(data):
    if len(data) < DIRECTORY_SIZE:
        raise ValueError('Missing ICO directory')
    for index in range(256):
        entry = data[index * 16:(index + 1) * 16]
        if not any(entry):
            continue
        width = int.from_bytes(entry[:2], 'big')
        height = int.from_bytes(entry[2:4], 'big')
        offset = int.from_bytes(entry[4:8], 'big')
        length = int.from_bytes(entry[8:11], 'big')
        if not width or not height or not 0 < length <= BLOCK_SIZE:
            raise ValueError(f'Invalid icon dimensions/length: {index}')
        if offset < DIRECTORY_SIZE or offset + length > len(data):
            raise ValueError(f'Invalid icon offset: {index}')
        payload = data[offset:offset + length]
        if not payload.startswith(b'\xff\xd8') or not payload.endswith(b'\xff\xd9'):
            raise ValueError(f'Invalid JPEG: {index}')
        yield index, entry, offset, payload


def pack(data):
    from icon_library import pack_records
    return pack_records([(index, int.from_bytes(entry[:2], 'big'),
                          int.from_bytes(entry[2:4], 'big'), payload)
                         for index, entry, old_offset, payload in entries(data)])


def validate_block_layout(data, library):
    if not 0 <= library <= 15 or len(data) > (16 - library) * BLOCK_SIZE:
        raise ValueError('Icon library exceeds available Picture Flash')
    for index, entry, offset, payload in entries(data):
        if offset // BLOCK_SIZE != (offset + len(payload) - 1) // BLOCK_SIZE:
            raise ValueError(f'Icon {index} crosses a 32 KiB boundary; repack first')
        if (offset + len(payload) - 1) % BLOCK_SIZE == BLOCK_SIZE - 1:
            raise ValueError(f'Icon {index} uses the reserved last block byte')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--library', type=int, default=7)
    args = parser.parse_args()
    if args.source.is_dir():
        from icon_library import build_library
        data = build_library(args.source)
    else:
        data = pack(args.source.read_bytes())
    validate_block_layout(data, args.library)
    args.destination.write_bytes(data)
    print(f'{len(data)} bytes; {(len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE} blocks')


if __name__ == '__main__':
    main()
