"""Validated, versioned LCD settings record; independent of atlas metadata."""
import struct
import zlib

RECORD_SIZE = 16

def encode(brightness, idle_minutes):
    if not 0 <= brightness <= 100 or not 0 <= idle_minutes <= 60:
        raise ValueError('Invalid display settings')
    payload = struct.pack('>8sBB2x', b'KDWDSPL1', brightness, idle_minutes)
    return payload + struct.pack('>I', zlib.crc32(payload))

def decode(record):
    if len(record) != RECORD_SIZE:
        return None
    payload, checksum = record[:12], record[12:]
    magic, brightness, minutes = struct.unpack('>8sBB2x', payload)
    if (magic != b'KDWDSPL1' or zlib.crc32(payload) != struct.unpack('>I', checksum)[0]
            or brightness > 100 or minutes > 60):
        return None
    return brightness, minutes

def raw_brightness(percent):
    return (percent * 255 + 50) // 100
