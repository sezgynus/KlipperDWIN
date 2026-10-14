#!/usr/bin/env python3
"""Render Graphite SVGs as panel-compatible baseline 4:2:0 JPEG icons."""
import argparse
from io import BytesIO
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import cairosvg  # Optional developer tool, not a service dependency.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, default=ROOT / 'assets/icon-source')
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'assets/icons')
    parser.add_argument('--ids', type=int, nargs='*', help='Render only these icon IDs')
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.source_directory.glob('*.svg')):
        if args.ids is not None and int(path.stem) not in args.ids:
            continue
        root = ET.fromstring(path.read_bytes())
        width, height = int(root.attrib['width']), int(root.attrib['height'])
        scale = 1 if int(path.stem) == 155 else 4
        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=width * scale,
                              output_height=height * scale)
        with Image.open(BytesIO(png)) as image:
            rendered = image.convert('RGB').resize((width, height), Image.Resampling.LANCZOS)
            icon_id = int(path.stem)
            if icon_id == 0:
                # Antialiased brand edges blend into Graphite; empty pixels stay
                # pure black for the panel's enhanced transparency filter.
                from graphite_theme import BACKGROUND_RGB
                rgba = image.convert('RGBA').resize((width, height), Image.Resampling.LANCZOS)
                coverage = rgba.getchannel('A')
                rendered = Image.new('RGB', (width, height), BACKGROUND_RGB)
                rendered.paste(rgba.convert('RGB'), (0, 0), coverage)
                rendered.paste((0, 0, 0), (0, 0), coverage.point(lambda a: 255 if a <= 8 else 0))
            button_frame = 125 <= icon_id <= 133 or 243 <= icon_id <= 247
            if button_frame:
                # Keep the SVG's antialiased round outline. Runtime clears only
                # the changed button, so transparency cannot retain stale ink.
                pass
            fan_frame = 235 <= icon_id <= 242
            if fan_frame:
                # Neutral chroma prevents 4:2:0 color bleeding into the black
                # transparency matte. Remove supersampling ringing before JPEG.
                rendered = rendered.convert('L').point(lambda v: 0 if v < 24 else v).convert('RGB')
            rendered.save(
                args.output_directory / (path.stem + '.jpg'), 'JPEG',
                # Physical T5UIC1 testing showed corrupted selected tiles and
                # homing artwork with 4:4:4, even after verified SRAM transfer.
                quality=100 if icon_id in (0, 155) or fan_frame or button_frame else 94, subsampling=2, progressive=False)


if __name__ == '__main__':
    main()
