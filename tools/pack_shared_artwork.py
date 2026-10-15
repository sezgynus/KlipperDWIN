#!/usr/bin/env python3
"""Pack named source JPEGs into slot 1 and generate matching Python coordinates."""
import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = (272, 480)
MAX_BYTES = 32767


@dataclass
class Artwork:
    path: Path
    name: str
    image: Image.Image
    digest: str

    @property
    def width(self):
        return self.image.width

    @property
    def height(self):
        return self.image.height


def identifier(stem):
    text = unicodedata.normalize('NFKD', stem.replace('ı', 'i'))
    text = text.encode('ascii', 'ignore').decode().upper()
    text = re.sub('[^A-Z0-9]+', '_', text).strip('_')
    if not text or not re.search('[A-Z]', text):
        raise ValueError(f'Filename needs a descriptive letter-based name: {stem}')
    if text[0].isdigit():
        text = 'IMAGE_' + text
    return text


def load_sources(directory):
    items, names = [], set()
    paths = sorted(Path(directory).iterdir(), key=lambda p: p.name)
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in ('.jpg', '.jpeg'):
            continue
        name = identifier(path.stem)
        symbols = {name + '_BOX', name + '_SIZE'}
        if symbols & (names | {'PAGE_SIZE', 'PHYSICAL_SIZE', 'JPEG_SHA256', 'JPEG_QUALITY', 'SOURCE_SHA256', 'BOXES'}):
            raise ValueError(f'Duplicate or reserved generated name: {path.name} -> {name}')
        names.update(symbols)
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as image:
            if image.format != 'JPEG':
                raise ValueError(f'Not a JPEG: {path.name}')
            image.load()
            if image.width > PAGE_SIZE[0] or image.height > PAGE_SIZE[1]:
                raise ValueError(f'{path.name} does not fit the {PAGE_SIZE[0]}x{PAGE_SIZE[1]} page')
            items.append(Artwork(path, name, image.convert('RGB'), hashlib.sha256(data).hexdigest()))
    if not items:
        raise ValueError(f'No JPEG sources in {directory}')
    if sum(item.width * item.height for item in items) > PAGE_SIZE[0] * PAGE_SIZE[1]:
        raise ValueError('JPEG source area exceeds the shared page capacity')
    return items


def contains(outer, inner):
    x, y, w, h = outer
    a, b, c, d = inner
    return x <= a and y <= b and a+c <= x+w and b+d <= y+h


def split_free(free, placed):
    """MaxRects split: remove a placement from every overlapping free rectangle."""
    px, py, pw, ph = placed
    result = []
    for x, y, w, h in free:
        if px >= x+w or py >= y+h or px+pw <= x or py+ph <= y:
            result.append((x, y, w, h))
            continue
        if px > x:
            result.append((x, y, px-x, h))
        if px+pw < x+w:
            result.append((px+pw, y, x+w-px-pw, h))
        if py > y:
            result.append((x, y, w, py-y))
        if py+ph < y+h:
            result.append((x, py+ph, w, y+h-py-ph))
    result = sorted(set(result))
    return [rect for i, rect in enumerate(result)
            if not any(i != j and contains(other, rect) for j, other in enumerate(result))]


def attempt(order, width, strategy):
    free, boxes = [(0, 0, width, PAGE_SIZE[1])], {}
    for item in order:
        fits = []
        for x, y, w, h in free:
            if item.width <= w and item.height <= h:
                dx, dy = w-item.width, h-item.height
                score = ((min(dx, dy), max(dx, dy), y, x) if strategy == 0 else
                         (w*h-item.width*item.height, min(dx, dy), y, x) if strategy == 1 else
                         (y+item.height, x, min(dx, dy), max(dx, dy)))
                fits.append((score, x, y))
        if not fits:
            return None
        _, x, y = min(fits)
        boxes[item.name] = (x, y, x+item.width, y+item.height)
        free = split_free(free, (x, y, item.width, item.height))
    return boxes


def pack(items):
    """Deterministic multi-start MaxRects; no resizing or rotation of source art."""
    orders = [sorted(items, key=lambda a: (*key(a), a.name)) for key in (
        lambda a: (-a.width*a.height, -max(a.width, a.height)),
        lambda a: (-max(a.width, a.height), -a.width*a.height),
        lambda a: (-a.height, -a.width),
        lambda a: (-a.width, -a.height))]
    # Try narrow bins too, to consolidate empty space rather than scatter gaps.
    minimum = max(a.width for a in items)
    widths = sorted({minimum, PAGE_SIZE[0], *range(minimum, PAGE_SIZE[0]+1, 8)})
    best = None
    for width in widths:
        for order in orders:
            for strategy in range(3):
                boxes = attempt(order, width, strategy)
                if boxes is None:
                    continue
                right = max(box[2] for box in boxes.values())
                bottom = max(box[3] for box in boxes.values())
                score = (right*bottom, bottom, right, tuple(sorted(boxes.items())))
                if best is None or score < best[0]:
                    best = score, boxes
    if best is None:
        raise ValueError('No tested layout fits without resizing or rotation; reduce source dimensions')
    return best[1]


def build(directory, quality=100):
    if not 1 <= quality <= 100:
        raise ValueError('JPEG quality must be 1..100')
    items = load_sources(directory)
    boxes = pack(items)
    page = Image.new('RGB', PAGE_SIZE, 'black')
    for item in items:
        page.paste(item.image, boxes[item.name][:2])
    buffer = BytesIO()
    page.transpose(Image.Transpose.ROTATE_90).save(
        buffer, 'JPEG', quality=quality, subsampling=2, progressive=False, optimize=True)
    data = buffer.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError(f'Shared JPEG is {len(data)} bytes; slot 1 permits {MAX_BYTES}. '
                         'Simplify sources or explicitly choose a lower --quality.')
    lines = ['"""Generated by tools/pack_shared_artwork.py; do not edit by hand.',
             'Portrait source rectangles: (left, top, right, bottom), exclusive ends.',
             '"""', f'PAGE_SIZE = {PAGE_SIZE!r}', 'PHYSICAL_SIZE = (480, 272)',
             f'JPEG_QUALITY = {quality}',
             f'JPEG_SHA256 = {hashlib.sha256(data).hexdigest()!r}', '', 'SOURCE_SHA256 = {']
    lines += [f'    {item.path.name!r}: {item.digest!r},' for item in sorted(items, key=lambda a: a.path.name)]
    lines += ['}', '']
    for item in sorted(items, key=lambda a: a.name):
        lines += [f'# Source: {item.path.name!r}',
                  f'{item.name}_BOX = {boxes[item.name]!r}',
                  f'{item.name}_SIZE = {(item.width, item.height)!r}']
    lines += ['', 'BOXES = {']
    lines += [f'    {name!r}: {name}_BOX,' for name in sorted(boxes)]
    lines += ['}', '']
    return data, '\n'.join(lines).encode(), boxes


def publish(outputs):
    """Stage both outputs before replacing either; roll back a failed replacement."""
    staged, backups, replaced = {}, {}, []
    try:
        for path, data in outputs.items():
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            backups[path] = path.read_bytes() if path.exists() else None
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name,
                                             delete=False) as stream:
                staged[path] = Path(stream.name)
                stream.write(data)
            staged[path].chmod(0o644)
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except OSError:
        for path in reversed(replaced):
            old = backups[path]
            if old is None:
                path.unlink()
            else:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    stream.write(old)
                    restore = Path(stream.name)
                restore.chmod(0o644)
                os.replace(restore, path)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, default=ROOT/'assets/shared-artwork')
    parser.add_argument('--output', type=Path, default=ROOT/'assets/petrel_shared.jpg')
    parser.add_argument('--layout', type=Path, default=ROOT/'shared_artwork_layout.py')
    parser.add_argument('--quality', type=int, default=100)
    args = parser.parse_args()
    if args.output.resolve() == args.layout.resolve():
        parser.error('JPEG and layout outputs must be different paths')
    try:
        data, source, boxes = build(args.source_directory, args.quality)
        if args.layout.resolve() == (ROOT/'shared_artwork_layout.py').resolve() and 'QR' not in boxes:
            raise ValueError('Info requires QR_BOX; keep qr.jpg in the shared source folder')
        publish({args.output: data, args.layout: source})
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    for name, box in sorted(boxes.items()):
        print(f'{name}_BOX = {box}')
    print(f'{len(boxes)} images; {len(data)}/{MAX_BYTES} JPEG bytes')


if __name__ == '__main__':
    main()
