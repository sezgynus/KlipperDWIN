"""Validated, versioned LCD settings record; independent of atlas metadata."""
import struct
import zlib

RECORD_SIZE = 16

def encode(brightness, idle_minutes, dim_brightness=10):
    if not 0 <= brightness <= 100 or not 0 <= idle_minutes <= 60 or not 0 <= dim_brightness <= 100:
        raise ValueError('Invalid display settings')
    payload = struct.pack('>8sBBB1x', b'KDWDSPL2', brightness, idle_minutes, dim_brightness)
    return payload + struct.pack('>I', zlib.crc32(payload))

def decode(record):
    if len(record) != RECORD_SIZE:
        return None
    payload, checksum = record[:12], record[12:]
    magic, brightness, minutes, dim = struct.unpack('>8sBBB1x', payload)
    if magic == b'KDWDSPL1':
        dim = 10
    if (magic not in (b'KDWDSPL1', b'KDWDSPL2') or zlib.crc32(payload) != struct.unpack('>I', checksum)[0]
            or brightness > 100 or minutes > 60 or dim > 100):
        return None
    return brightness, minutes, dim

def raw_brightness(percent):
    return (percent * 255 + 50) // 100
