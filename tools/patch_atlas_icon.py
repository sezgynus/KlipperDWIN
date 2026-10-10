"""Add a sprite in free Atlas 0 JPEG blocks without re-encoding old icons.

Build-only dependencies: Pillow, numpy, jpeglib (pip install jpeglib).
Usage: python tools/patch_atlas_icon.py sprite.png output.jpg
Chooses the first free 16-pixel-aligned block rectangle whose decoded old
icon pixels remain identical. Prints the portrait icon source rectangle.
"""
import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import jpeglib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lcd_atlas


def panel_jpeg_headers(data):
    """Keep stock JFIF/component IDs: DWIN expects RGB components 1/2/3."""
    result = bytearray(data[:2])
    offset, jfif_seen = 2, False
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError('Invalid JPEG marker')
        marker = data[offset + 1]
        length = int.from_bytes(data[offset+2:offset+4], 'big')
        segment = bytearray(data[offset:offset+2+length])
        if marker == 0xE0 and segment[4:9] == b'JFIF\0':
            if jfif_seen:
                offset += 2 + length
                continue
            jfif_seen = True
        if marker == 0xC0:
            if segment[9] != 3:
                raise ValueError('Atlas must have three JPEG components')
            for index in range(3):
                segment[10 + index * 3] = index + 1
        elif marker == 0xDA:
            if segment[4] != 3:
                raise ValueError('Atlas must have one interleaved scan')
            for index in range(3):
                segment[5 + index * 2] = index + 1
            result.extend(segment)
            result.extend(data[offset+2+length:])
            return bytes(result)
        result.extend(segment)
        offset += 2 + length
    raise ValueError('Missing JPEG scan')


def patch(sprite_path, output):
    atlas_path = Path(lcd_atlas.__file__).parent / lcd_atlas.ATLAS_FILES[0][0]
    if Path(output).resolve() == atlas_path.resolve():
        raise ValueError('Use a separate output file; never overwrite the source atlas')
    old = atlas_path.read_bytes()
    portrait = Image.open(io.BytesIO(old)).transpose(Image.Transpose.ROTATE_270).convert('RGB')
    sprite = Image.open(sprite_path).convert('RGBA')
    width, height = sprite.size
    tile_width, tile_height = (width + 15) // 16 * 16, (height + 15) // 16 * 16
    occupied = [rect[1:] for rect in lcd_atlas.ICON_COORDINATES.values() if rect[0] == 0]
    tile = Image.new('RGB', (tile_width, tile_height), 'black')
    tile.paste(sprite, (0, 0), sprite)
    original = jpeglib.read_dct(str(atlas_path))
    patch_path = Path(output).with_suffix('.patch.jpg')
    tile.transpose(Image.Transpose.ROTATE_90).save(patch_path, qtables=Image.open(io.BytesIO(old)).quantization, subsampling=2)
    fragment = jpeglib.read_dct(str(patch_path))
    assert np.array_equal(original.qt, fragment.qt)
    try:
        for y in range(0, 480 - tile_height + 1, 16):
            for x in range(0, 272 - tile_width + 1, 16):
                if any(x < ox + w and x + tile_width > ox and y < oy + h and y + tile_height > oy
                       for ox, oy, w, h in occupied):
                    continue
                px, py = y, 272 - x - tile_width
                candidate = jpeglib.read_dct(str(atlas_path))
                for component, step in (('Y', 8), ('Cb', 16), ('Cr', 16)):
                    target = getattr(candidate, component)
                    source = getattr(fragment, component)
                    row, col = py // step, px // step
                    target[row:row+source.shape[0], col:col+source.shape[1]] = source
                candidate.write_dct(str(output))
                Path(output).write_bytes(panel_jpeg_headers(Path(output).read_bytes()))
                result = Image.open(output).transpose(Image.Transpose.ROTATE_270).convert('RGB')
                if all(portrait.crop((ox, oy, ox+w, oy+h)).tobytes() == result.crop((ox, oy, ox+w, oy+h)).tobytes()
                       for ox, oy, w, h in occupied):
                    assert Path(output).stat().st_size <= 32768
                    print((0, x, y, width, height))
                    return
        raise ValueError('No free JPEG block rectangle preserves every existing icon')
    finally:
        patch_path.unlink(missing_ok=True)


if __name__ == '__main__':
    patch(sys.argv[1], sys.argv[2])
