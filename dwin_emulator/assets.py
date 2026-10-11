"""Read original binary panel assets without substituting host fonts."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image
from lcd_resources import ICON_LIBRARY_ID, ICON_LIBRARY_FILENAME

ROOT = Path(__file__).resolve().parent.parent
SIZES = (6, 8, 10, 12, 14, 16, 20, 24, 28, 32)


def rgb565(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def panel_colors(image):
    """Quantize JPEG decoder output to the LCD's RGB565 color space."""
    r, g, b = image.convert('RGB').split()
    return Image.merge('RGB', (r.point([((v >> 3) << 3) | (v >> 5) for v in range(256)]),
                               g.point([((v >> 2) << 2) | (v >> 6) for v in range(256)]),
                               b.point([((v >> 3) << 3) | (v >> 5) for v in range(256)])))


class PanelAssets:
    def __init__(self, root=ROOT, font_path=None):
        self.root = Path(root)
        self.font = Path(font_path or self.root / 'assets/emulator/0T5UIC1.HZK').expanduser().read_bytes()
        from icon_library import build_library
        sources = self.root / 'assets/icons'
        self.ico = (build_library(sources) if sources.is_dir() else
                    (self.root / 'assets/emulator' / ICON_LIBRARY_FILENAME).read_bytes())
        if len(self.ico) < 4096:
            raise ValueError(f'Truncated {ICON_LIBRARY_FILENAME} directory')
        self.glyph = lru_cache(maxsize=1280)(self.glyph)
        self.icon = lru_cache(maxsize=256)(self.icon)
        self.picture = lru_cache(maxsize=16)(self.picture)
        self.offsets = {}
        offset = 0
        widths = range(4, 65) if len(self.font) == 3082752 else SIZES
        for width in widths:
            self.offsets[width] = offset
            offset += 128 * ((width + 7) // 8) * width * 2
        if len(self.font) != 3082752 and len(self.font) < offset - 256:
            raise ValueError('Truncated T5UIC1 ASCII font banks')

    def glyph(self, font, code):
        if not 0 <= font < len(SIZES) or not 0 <= code < 128:
            raise ValueError('Only the supplied ASCII fonts are available')
        width = SIZES[font]
        height, row_bytes = width * 2, (width + 7) // 8
        offset = self.offsets[width] + code * row_bytes * height
        # HZK rows are MSB-first, byte aligned, with padding on the right.
        raw = self.font[offset:offset + row_bytes * height]
        if len(raw) != row_bytes * height:
            raise ValueError(f'Missing font {font}, character {code}')
        return Image.frombytes('1', (row_bytes * 8, height), raw).crop((0, 0, width, height)).convert('L')

    def icon(self, library, icon):
        if library != ICON_LIBRARY_ID or not 0 <= icon <= 255:
            raise ValueError(f'Missing icon library {library}, icon {icon}')
        entry = self.ico[icon * 16:(icon + 1) * 16]
        width, height = int.from_bytes(entry[:2], 'big'), int.from_bytes(entry[2:4], 'big')
        offset, length = int.from_bytes(entry[4:8], 'big'), int.from_bytes(entry[8:11], 'big')
        if not width or not height or offset < 4096 or offset + length > len(self.ico):
            raise ValueError(f'Missing or invalid icon {icon}')
        with Image.open(BytesIO(self.ico[offset:offset + length])) as image:
            if image.size != (width, height):
                raise ValueError(f'Icon {icon} dimensions differ from its directory')
            return panel_colors(image)

    def picture(self, slot):
        paths = {0: 'assets/klipperdwin_bootsplash.jpg'}
        if slot not in paths:
            raise ValueError(f'No host image for picture slot {slot}')
        with Image.open(self.root / paths[slot]) as image:
            if image.size != (480, 272):
                raise ValueError('Expected physical 480x272 JPEG')
            return panel_colors(image)
