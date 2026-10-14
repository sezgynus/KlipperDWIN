"""Bounded thumbnail conversion for volatile LCD picture memory."""
from io import BytesIO
import posixpath
import time
import logging
from urllib.parse import quote
from PIL import Image
from preview_metadata import PreviewData, details_from_metadata

MIN_FOREGROUND_LUMA = 48


def _protect_dark_foreground(rgba):
    """Reserve black for transparency; lift dark model pixels before alpha blend."""
    pixels = []
    for r, g, b, alpha in rgba.getdata():
        if not alpha:
            pixels.append((0, 0, 0, 0))
            continue
        luma = (299 * r + 587 * g + 114 * b) // 1000
        while luma < MIN_FOREGROUND_LUMA:
            lift = MIN_FOREGROUND_LUMA - luma
            r, g, b = (min(255, c + lift) for c in (r, g, b))
            luma = (299 * r + 587 * g + 114 * b) // 1000
        pixels.append((r, g, b, alpha))
    protected = Image.new('RGBA', rgba.size)
    protected.putdata(pixels)
    return protected


def image_jpeg(data, size=128):
    """Reserve black backing for filtered drawing, protecting dark model details."""
    if size not in (88, 128):
        raise ValueError('Unsupported panel thumbnail size')
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 4_000_000:
            raise ValueError('Thumbnail too large')
        source.thumbnail((size, size), Image.Resampling.LANCZOS)
        rgba = _protect_dark_foreground(source.convert('RGBA'))
        canvas = Image.new('RGB', (size, size), 'black')
        canvas.paste(rgba, ((size-rgba.width)//2, (size-rgba.height)//2), rgba)
    output = BytesIO()
    canvas.save(output, format='JPEG', quality=94, subsampling=2,
                progressive=False, optimize=False)
    jpeg = output.getvalue()
    if len(jpeg) > 32768:
        raise ValueError('JPEG exceeds LCD SRAM')
    return jpeg


def load_thumbnail(client, filename, metadata=None, size=128):
    started = time.monotonic()
    if metadata is None:
        metadata = client.get('/server/files/metadata?filename=' + quote(filename, safe=''))['result']
    thumbs = metadata.get('thumbnails', [])
    candidates = [t for t in thumbs if isinstance(t, dict) and isinstance(t.get('relative_path'), str)
                  and all(isinstance(t.get(k), int) and 0 < t[k] <= 4080 for k in ('width', 'height'))]
    # Prefer a source large enough for the preview, rather than a tiny icon.
    candidates.sort(key=lambda t: (max(t['width'], t['height']) < 128,
                                   abs(max(t['width'], t['height'])-128)))
    for thumb in candidates:
        relative = thumb['relative_path']
        path = posixpath.normpath(posixpath.join(posixpath.dirname(filename), relative))
        if relative.startswith('/') or path.startswith('../') or path == '..':
            continue
        data = client.get_bytes('/server/files/gcodes/' + quote(path, safe='/'), max_bytes=2_000_000)
        downloaded = time.monotonic()
        jpeg = image_jpeg(data,size=size)
        logging.info('Thumbnail %s: download %.3fs, conversion %.3fs, %d JPEG bytes',
                     filename, downloaded-started, time.monotonic()-downloaded, len(jpeg))
        return jpeg
    raise ValueError('No thumbnail')


def load_preview(client, filename, size=128):
    metadata = client.get('/server/files/metadata?filename=' + quote(filename, safe=''))['result']
    details = details_from_metadata(metadata)
    try:
        jpeg = load_thumbnail(client, filename, metadata=metadata, size=size)
    except Exception as error:
        logging.info('Thumbnail unavailable %s: %s', filename, error)
        jpeg = None
    return PreviewData(jpeg, details)
