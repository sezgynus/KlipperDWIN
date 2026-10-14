"""T5UIC1 packet interpreter. It never reads or writes the real serial port."""
from io import BytesIO
import struct
import time
from threading import RLock

from PIL import Image, ImageDraw, ImageChops

from .assets import PanelAssets, rgb565


class Framebuffer:
    TAIL = b'\xcc\x33\xc3\x3c'
    # Nonvisual commands intentionally do not affect screenshots/backlight pixels.
    NONVISUAL = {0x00, 0x30, 0x32, 0x38, 0x39}

    def __init__(self, assets=None):
        self.assets = assets or PanelAssets()
        self.lock = RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.direction = 1
            splash = self.assets.picture(0).transpose(Image.Transpose.ROTATE_270)
            self.image = splash.copy()
            self.areas = {0: splash.copy(), 1: Image.new('RGB', (272, 480))}
            self.sram = bytearray(32768)
            self.pictures = {}
            self.flash_blocks = {}
            self.errors = set()
            self.animations = {}
            self.presented = None
            self.sequence = 0

    def snapshot(self):
        with self.lock:
            if self.errors:
                raise RuntimeError('Incomplete emulation: ' + '; '.join(sorted(self.errors)))
            if self.presented is None:
                raise RuntimeError('No completed LCD update yet')
            image = self.presented.copy()
            self._render_animations(image)
            return image, self.sequence

    def _render_animations(self, image):
        now = time.monotonic()
        for animation in self.animations.values():
            x, y, mode, library, first, last, interval, started, backing = animation
            elapsed = int((now - started) / max(.01, interval * .01))
            step = 1 if last >= first else -1
            icon = first + step * (elapsed % (abs(last - first) + 1))
            sprite = self.assets.icon(library, icon)
            image.paste(backing, (x, y))
            if mode & 0x80:
                # Animation icon black pixels are transparent on the panel.
                maximum = ImageChops.lighter(ImageChops.lighter(*sprite.split()[:2]), sprite.split()[2])
                image.paste(sprite, (x, y), maximum.point([0] + [255] * 255))

    @staticmethod
    def words(data):
        if len(data) % 2:
            raise ValueError('Unaligned coordinate payload')
        return struct.unpack('>' + 'H' * (len(data) // 2), data)

    def _picture(self, slot):
        physical = self.pictures.get(slot)
        if physical is None:
            if slot in self.flash_blocks:
                from .assets import panel_colors
                with Image.open(BytesIO(self.flash_blocks[slot])) as image:
                    physical = panel_colors(image)
                self.pictures[slot] = physical
            else:
                physical = self.assets.picture(slot)
        turns = {0: None, 1: Image.Transpose.ROTATE_270,
                 2: Image.Transpose.ROTATE_180, 3: Image.Transpose.ROTATE_90}
        return physical.copy() if self.direction == 0 else physical.transpose(turns[self.direction])

    def _paste(self, image, x, y, mode=0x80):
        if mode & 0x80:
            self.image.paste(image, (x, y))
            return
        if mode & 0x40:
            self.image.paste(self.areas[0].crop((x, y, x + image.width, y + image.height)), (x, y))
        # Enhanced filtering suppresses near-black JPEG ringing as well as black.
        limit = 31 if mode & 0x20 else 0
        channels = image.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        mask = maximum.point([255 if v > limit else 0 for v in range(256)])
        self.image.paste(image, (x, y), mask)

    def _text(self, mode, color, background, x, y, data):
        font = mode & 15
        for code in data:
            if code == 0:
                break
            glyph = self.assets.glyph(font, code)
            if mode & 0x80:
                bbox = glyph.getbbox()
                glyph = glyph.crop((bbox[0], 0, bbox[2], glyph.height)) if bbox else glyph
            if mode & 0x40:
                self.image.paste(rgb565(background), (x, y, x + glyph.width, y + glyph.height))
            self.image.paste(rgb565(color), (x, y), glyph)
            x += glyph.width

    def feed(self, frame):
        if not frame.startswith(b'\xaa') or not frame.endswith(self.TAIL) or len(frame) < 6:
            raise ValueError('Invalid complete T5UIC1 frame')
        opcode, p = frame[1], frame[2:-4]
        with self.lock:
            self._render_animations(self.image)
            if opcode in self.NONVISUAL:
                return
            if opcode == 0x3D:
                self.presented = self.image.copy()
                self.sequence += 1
            elif opcode == 0x01:
                self.image.paste(rgb565(self.words(p)[0]), (0, 0, *self.image.size))
            elif opcode == 0x02:
                color = rgb565(self.words(p[:2])[0]); width, height = p[2:4]
                coords = self.words(p[4:]); draw = ImageDraw.Draw(self.image)
                for x, y in zip(coords[::2], coords[1::2]):
                    draw.rectangle((x, y, x + width - 1, y + height - 1), fill=color)
            elif opcode == 0x03:
                color = rgb565(self.words(p[:2])[0]); coords = self.words(p[2:])
                ImageDraw.Draw(self.image).line(list(zip(coords[::2], coords[1::2])), fill=color, width=1)
            elif opcode == 0x05:
                mode = p[0]; color, x0, y0, x1, y1 = self.words(p[1:])
                draw = ImageDraw.Draw(self.image)
                if mode == 2:
                    patch = self.image.crop((x0, y0, x1 + 1, y1 + 1))
                    channels = patch.split()
                    patch = Image.merge('RGB', tuple(channel.point([v ^ component for v in range(256)])
                                                     for channel, component in zip(channels, rgb565(color))))
                    self.image.paste(patch, (x0, y0))
                else:
                    draw.rectangle((x0, y0, x1, y1), **{'fill' if mode else 'outline': rgb565(color)})
            elif opcode == 0x08:
                x, y, width, one, zero = self.words(p[:10])
                row = (width + 7) // 8; height = len(p[10:]) // row
                mask = Image.frombytes('1', (row * 8, height), p[10:]).crop((0, 0, width, height)).convert('L')
                patch = Image.new('RGB', mask.size, rgb565(zero)); patch.paste(rgb565(one), (0, 0), mask)
                self.image.paste(patch, (x, y))
            elif opcode == 0x09:
                distance, color, x0, y0, x1, y1 = self.words(p[1:])
                x1, y1 = min(x1, self.image.width - 1), min(y1, self.image.height - 1)
                patch = self.image.crop((x0, y0, x1 + 1, y1 + 1))
                dx, dy = ((-distance, 0), (distance, 0), (0, -distance), (0, distance))[p[0] & 3]
                if p[0] & 128:
                    moved = Image.new('RGB', patch.size, rgb565(color)); moved.paste(patch, (dx, dy))
                else:
                    moved = ImageChops.offset(patch, dx, dy)
                self.image.paste(moved, (x0, y0))
            elif opcode == 0x11:
                color, bg, x, y = self.words(p[1:9]); self._text(p[0], color, bg, x, y, p[9:])
            elif opcode == 0x14:
                mode = p[0]; color, bg = self.words(p[1:5]); integer, fractional = p[5:7]
                x, y = self.words(p[7:11])
                value = int.from_bytes(p[11:], 'big', signed=bool(mode & 0x40))
                digits = str(abs(value)).rjust(fractional + 1, '0')
                if fractional:
                    digits = digits[:-fractional] + '.' + digits[-fractional:]
                width = integer + (fractional + 1 if fractional else 0)
                if mode & 0x20:
                    digits = digits.rjust(width, '0' if mode & 0x10 else ' ')
                if mode & 0x40:
                    digits = ('-' if value < 0 else ' ') + digits
                self._text((mode & 15) | (0x40 if mode & 0x80 else 0), color, bg, x, y, digits.encode('ascii'))
            elif opcode == 0x21:
                import qrcode
                x, y = self.words(p[:4]); scale = p[4]
                qr = qrcode.QRCode(version=7, error_correction=qrcode.constants.ERROR_CORRECT_L,
                                   box_size=scale, border=0)
                qr.add_data(p[5:], optimize=0); qr.make(fit=False)
                code = qr.make_image(fill_color='black', back_color='white').convert('RGB')
                patch = Image.new('RGB', (46 * scale, 46 * scale), 'white')
                patch.paste(code, (0, 0)); self.image.paste(patch, (x, y))
            elif opcode in (0x22, 0x25):
                picture = self._picture(p[1]); self.areas[p[0]] = picture.copy()
                if opcode == 0x22:
                    self.image = picture.copy()
            elif opcode == 0x23:
                x, y = self.words(p[:4]); mode = p[4]
                for icon in p[5:]:
                    image = self.assets.icon(mode & 15, icon); self._paste(image, x, y, mode); x += image.width
            elif opcode == 0x24:
                x, y = self.words(p[:4]); address = self.words(p[5:7])[0]
                with Image.open(BytesIO(self.sram[address:])) as image:
                    from .assets import panel_colors
                    self._paste(panel_colors(image), x, y, p[4])
            elif opcode in (0x26, 0x27):
                mode = 0x81 if opcode == 0x26 else p[0]
                x0, y0, x1, y1, x, y = self.words(p if opcode == 0x26 else p[1:])
                self._paste(self.areas[mode & 1].crop((x0, y0, x1 + 1, y1 + 1)), x, y, mode)
            elif opcode == 0x28:
                if len(p) != 9:
                    raise ValueError('Invalid animation payload')
                x, y = self.words(p[:4])
                mode, library, first, last, interval = p[4:]
                animation_id = mode & 15
                previous = self.animations.pop(animation_id, None)
                if mode & 0x80:
                    sprites = [self.assets.icon(library, i) for i in range(min(first,last), max(first,last)+1)]
                    width, height = max(i.width for i in sprites), max(i.height for i in sprites)
                    backing = self.image.crop((x, y, x + width, y + height))
                    started = time.monotonic()
                    if previous and not mode & 0x40 and previous[:2] == (x, y) and previous[3:6] == (library, first, last):
                        old_interval, old_started, backing = previous[6:]
                        phase = int((started - old_started) / max(.01, old_interval * .01))
                        started -= (phase % (abs(last - first) + 1)) * max(.01, interval * .01)
                    self.animations[animation_id] = (x, y, mode, library, first, last,
                                                     interval, started, backing)
                    self._render_animations(self.image)
            elif opcode == 0x29:
                mask, = self.words(p)
                self.animations = {i:a for i,a in self.animations.items() if mask & (1 << i)}
            elif opcode == 0x31:
                address = self.words(p[1:3])[0]
                if p[0] == 0x5A:
                    end = address + len(p[3:])
                    if end > len(self.sram):
                        raise ValueError('SRAM write out of bounds')
                    self.sram[address:end] = p[3:]
            elif opcode == 0x33:
                # Flash holds ICO blocks as well as pictures. Decode only when
                # a picture command actually requests this slot.
                self.flash_blocks[p[2]] = bytes(self.sram)
                self.pictures.pop(p[2], None)
            elif opcode == 0x34:
                if p[:2] != b'\x5a\xa5' or p[2] not in range(4):
                    raise ValueError('Invalid orientation')
                if self.direction != p[2]:
                    self.direction = p[2]
                    self.image = self._picture(0)
                    self.areas = {0: self.image.copy(), 1: Image.new('RGB', self.image.size)}
            else:
                raise NotImplementedError(f'Unsupported visual opcode 0x{opcode:02x}')
