#!/usr/bin/env python3
"""Render Graphite SVGs as panel-compatible baseline 4:2:0 JPEG icons."""
import argparse
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def main():
    import cairosvg  # Optional developer tool, not a service dependency.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, default=ROOT / 'assets/icon-source')
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'assets/icons')
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.source_directory.glob('*.svg')):
        root = ET.fromstring(path.read_bytes())
        width, height = int(root.attrib['width']), int(root.attrib['height'])
        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=width * 4,
                              output_height=height * 4)
        with Image.open(BytesIO(png)) as image:
            rendered = image.convert('RGB').resize((width, height), Image.Resampling.LANCZOS)
            icon_id = int(path.stem)
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
                quality=100 if fan_frame or button_frame else 94, subsampling=2, progressive=False)


if __name__ == '__main__':
    main()
