#!/usr/bin/env python3
"""Repack a DWIN ICO without splitting JPEG icons across Flash blocks."""
import argparse
from pathlib import Path

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
    result = bytearray(data[:DIRECTORY_SIZE])
    for index, entry, old_offset, payload in entries(data):
        remaining = BLOCK_SIZE - len(result) % BLOCK_SIZE
        if len(payload) > remaining:
            result.extend(bytes(remaining))
        offset = len(result)
        result[index * 16 + 4:index * 16 + 8] = offset.to_bytes(4, 'big')
        result.extend(payload)
    return bytes(result)


def validate_block_layout(data, library):
    if not 0 <= library <= 15 or len(data) > (16 - library) * BLOCK_SIZE:
        raise ValueError('Icon library exceeds available Picture Flash')
    for index, entry, offset, payload in entries(data):
        if offset // BLOCK_SIZE != (offset + len(payload) - 1) // BLOCK_SIZE:
            raise ValueError(f'Icon {index} crosses a 32 KiB boundary; repack first')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--library', type=int, default=7)
    args = parser.parse_args()
    data = pack(args.source.read_bytes())
    validate_block_layout(data, args.library)
    args.destination.write_bytes(data)
    print(f'{len(data)} bytes; {(len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE} blocks')


if __name__ == '__main__':
    main()
