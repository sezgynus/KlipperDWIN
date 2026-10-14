#!/usr/bin/env python3
"""Render text-free button backings for the managed DWIN JPEG/ICO library."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BACKINGS = {
    134: (104, 36, 8, 0x39C8, 0),
    135: (104, 36, 8, 0x063B, 0),
    136: (104, 36, 8, 0xB209, 0),
    137: (244, 202, 10, 0x2967, 0),
    144: (244, 30, 8, 0x063B, 0),
    145: (244, 30, 8, 0x2967, 0),
    149: (104, 36, 18, 0x2967, 0x2967),
    150: (104, 36, 18, 0x19E9, 0x2967),
    151: (104, 36, 18, 0xB986, 0x2967),
}

def rgb(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)

def render(index):
    width, height, radius, fill, backing = BACKINGS[index]
    image = Image.new('RGB', (width, height), rgb(backing))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, width - 1, height - 1),
                                           radius=radius, fill=rgb(fill))
    image.save(ROOT / 'assets/icons' / f'{index:03d}.jpg', quality=95,
               subsampling=2, progressive=False)
    color = lambda value: '#%02x%02x%02x' % rgb(value)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" '
           f'fill="{color(backing)}"/><rect width="{width}" height="{height}" '
           f'rx="{radius}" fill="{color(fill)}"/></svg>\n')
    (ROOT / 'assets/icon-source' / f'{index:03d}.svg').write_text(svg)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids', type=int, nargs='*')
    args = parser.parse_args()
    for index in args.ids or BACKINGS:
        render(index)
