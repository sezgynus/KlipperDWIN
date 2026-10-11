from io import BytesIO
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from dwin_emulator.assets import PanelAssets, rgb565
from dwin_emulator.framebuffer import Framebuffer
from dwin_emulator.runtime import Emulator, ScreenshotServer
from tools.screenshot import capture
from test_t5uic1_driver import driver


class EmulatorRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = PanelAssets()

    def setUp(self):
        self.model = Framebuffer(self.assets)
        self.lcd = driver()
        self.lcd._packet_observer = self.model

    def test_managed_ico_flash_blocks_do_not_require_jpeg_decoding(self):
        from icon_library import build_library
        packed = build_library()
        for index in range(len(packed) // 32768):
            block = packed[index * 32768:(index + 1) * 32768]
            self.model.sram[:] = block
            self.model.feed(b'\xaa\x33\x5a\xa5' + bytes((7 + index,)) + self.model.TAIL)
            self.assertEqual(self.model.flash_blocks[7 + index], block)
        self.lcd.show_icon(7, 101, 17, 130)
        self.lcd.update()
        self.assertEqual(self.model.snapshot()[0].size, (272, 480))
        self.assertFalse(self.model.errors)

    def test_flash_picture_decodes_when_displayed_and_replacement_invalidates_cache(self):
        for color in ('red', 'green'):
            stream = BytesIO()
            Image.new('RGB', (480, 272), color).save(stream, format='JPEG')
            data = stream.getvalue()
            self.model.sram[:] = data + bytes(32768 - len(data))
            self.model.feed(b'\xaa\x33\x5a\xa5\x05' + self.model.TAIL)
            self.assertNotIn(5, self.model.pictures)
            self.lcd.show_jpeg(5)
            self.lcd.update()
            expected = self.model.pictures[5].getpixel((0, 0))
            self.assertEqual(self.model.snapshot()[0].getpixel((0, 0)), expected)
        self.assertFalse(self.model.errors)

    def test_transmitted_packets_and_completed_updates_are_the_only_input(self):
        self.lcd.clear(0xF800)
        with self.assertRaisesRegex(RuntimeError, 'completed'):
            self.model.snapshot()
        self.lcd.update()
        original, sequence = self.model.snapshot()
        self.assertEqual(original.size, (272, 480))
        self.assertEqual(original.getpixel((0, 0)), (255, 0, 0))
        self.lcd.draw_rectangle(1, 0x07E0, 4, 5, 10, 11)
        previous, _ = self.model.snapshot()
        self.assertEqual(previous.tobytes(), original.tobytes())
        self.lcd.update()
        current, newer = self.model.snapshot()
        self.assertGreater(newer, sequence)
        self.assertEqual(current.getpixel((4, 5)), (0, 255, 0))
        self.assertEqual(current.getpixel((3, 5)), (255, 0, 0))

    def test_native_animation_capture_advances_stops_and_moves_without_traces(self):
        with patch('dwin_emulator.framebuffer.time.monotonic', return_value=100):
            self.lcd.clear(0)
            self.lcd.configure_animation(0, True, 7, 250, 254, 12, 40, 10)
            self.lcd.update()
            first, _ = self.model.snapshot()
        with patch('dwin_emulator.framebuffer.time.monotonic', return_value=100.11):
            second, _ = self.model.snapshot()
            self.assertNotEqual(first.tobytes(), second.tobytes())
            self.lcd.configure_animation(0, False, 7, 250, 254, 12, 40, 10)
            self.lcd.clear(0)
            self.lcd.configure_animation(0, True, 7, 250, 254, 70, 40, 10)
            self.lcd.update()
            moved, _ = self.model.snapshot()
            width, height = self.assets.icon(7, 250).size
            self.assertIsNone(moved.crop((12, 40, 12+width, 40+height)).getbbox())
            self.lcd.configure_animation(0, False, 7, 250, 254, 70, 40, 10)
            self.lcd.update()
            stopped, _ = self.model.snapshot()
        with patch('dwin_emulator.framebuffer.time.monotonic', return_value=200):
            self.assertEqual(stopped.tobytes(), self.model.snapshot()[0].tobytes())
        self.assertFalse(self.model.errors)

    def test_animation_mask_disables_configured_animation(self):
        self.lcd.configure_animation(2, True, 7, 250, 254, 10, 10, 10)
        self.assertIn(2, self.model.animations)
        self.lcd.set_animation_mask(0)
        self.assertFalse(self.model.animations)
        self.lcd.update()
        self.model.snapshot()

    def test_original_hzk_offsets_and_msb_first_rows(self):
        # Native T5UIC1: 128 6x12 glyphs precede the 8x16 bank.
        offset = 128 * 12 + 65 * 16
        raw = self.assets.font[offset:offset + 16]
        expected = bytes(255 if byte & (128 >> bit) else 0 for byte in raw for bit in range(8))
        self.assertEqual(self.assets.glyph(1, 65).tobytes(), expected)
        self.lcd.clear(0x001F)
        self.lcd.draw_text(False, True, 1, 0xFFFF, 0, 8, 10, 'A')
        self.lcd.update(); image, _ = self.model.snapshot()
        for y in range(16):
            for x in range(8):
                self.assertEqual(image.getpixel((8 + x, 10 + y)),
                                 (255, 255, 255) if expected[y * 8 + x] else (0, 0, 0))

    def test_supplied_dgus_library_is_supported_as_an_explicit_override(self):
        supplied = PanelAssets(font_path=self.assets.root / 'assets/emulator/0_DWIN_ASC.HZK')
        self.assertEqual(supplied.offsets[8], 0x1600)
        self.assertEqual(supplied.glyph(1, 65).size, (8, 16))

    def test_real_ui_home_and_prepare_packets_render_without_a_second_ui(self):
        from test_capabilities import display, snapshot
        view = display(snapshot()); view.lcd = self.lcd; view.checkkey = view.MainMenu
        self.lcd.show_jpeg(0)
        view._draw_home_page(); view.Draw_Status_Area(False); self.lcd.update()
        home, _ = self.model.snapshot()
        from lcd_resources import ICON_MMU_HOME_NORMAL
        source = self.assets.icon(7, ICON_MMU_HOME_NORMAL)
        # Native transparency changes black pixels only; compare a colored pixel.
        points = [(x, y) for y in range(2, 65) for x in range(2, 108)
                  if max(source.getpixel((x, y))) > 31]
        self.assertTrue(points)
        x, y = points[len(points) // 2]
        # All home icons use the same native tile coordinates.
        frames = self.lcd.serial.frames
        copies = [f for f in frames if f[1] == 0x23 and f[6:8] == bytes((0x87, ICON_MMU_HOME_NORMAL))]
        self.assertTrue(copies)
        target_x, target_y = self.model.words(copies[-1][2:6])
        self.assertEqual(home.getpixel((target_x + x, target_y + y)), source.getpixel((x, y)))
        view.Draw_Prepare_Menu(); self.lcd.update()
        self.assertNotEqual(self.model.snapshot()[0].tobytes(), home.tobytes())

    def test_picture_rotation_and_both_cache_areas(self):
        self.lcd.show_jpeg(0)
        self.lcd.cache_jpeg(0, 1)
        self.lcd.clear(0x001F)
        self.lcd.copy_cache(0, 224, 32, 243, 51, 10, 20, background=True)
        self.lcd.copy_cache1(0, 0, 9, 9, 40, 50)
        self.lcd.update(); image, _ = self.model.snapshot()
        picture = self.assets.picture(0).transpose(Image.Transpose.ROTATE_270)
        self.assertEqual(image.crop((10, 20, 30, 40)).tobytes(), picture.crop((224, 32, 244, 52)).tobytes())
        self.assertEqual(image.crop((40, 50, 50, 60)).tobytes(), self.model.areas[1].crop((0, 0, 10, 10)).tobytes())
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 255))

    def test_stock_icon_directory_including_sparse_ids(self):
        for icon in (0, 1, 15, 205, 254):
            image = self.assets.icon(7, icon)
            self.lcd.show_icon(7, icon, 0, 0, background=True)
            self.lcd.update(); frame, _ = self.model.snapshot()
            self.assertEqual(frame.crop((0, 0, image.width, image.height)).tobytes(), image.tobytes())
        with self.assertRaises(ValueError):
            self.assets.icon(7, 39)

    def test_move_area_translation_and_wrap_leave_surroundings_unchanged(self):
        for direction, target in ((0, (8, 10)), (1, (12, 10)), (2, (10, 8)), (3, (10, 12))):
            self.lcd.clear(0x001F)
            self.lcd.draw_point(0xF800, 1, 1, 10, 10)
            self.lcd.move_area(1, direction, 2, 0x07E0, 5, 5, 15, 15)
            self.lcd.update(); image, _ = self.model.snapshot()
            self.assertEqual(image.getpixel(target), (255, 0, 0))
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255))
        self.lcd.clear(0)
        self.lcd.draw_point(0xFFFF, 1, 1, 5, 5)
        self.lcd.move_area(0, 0, 1, 0, 5, 5, 15, 15)
        self.lcd.update(); image, _ = self.model.snapshot()
        self.assertEqual(image.getpixel((15, 5)), (255, 255, 255))

    def test_bitmap_xor_and_sram_thumbnail(self):
        self.lcd.clear(0xF800)
        self.lcd.draw_rectangle(2, 0x07E0, 0, 0, 2, 2)
        self.lcd.draw_bitmap(5, 5, 3, 0xFFFF, 0, b'\xa0')
        thumbnail = Image.new('RGB', (12, 9), 'green'); stream = BytesIO()
        thumbnail.save(stream, 'JPEG')
        self.lcd.write_sram(256, stream.getvalue())
        self.lcd.show_sram_jpeg(20, 20, 256)
        self.lcd.update(); image, _ = self.model.snapshot()
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 0))
        self.assertEqual(image.getpixel((5, 5)), (255, 255, 255))
        self.assertEqual(image.getpixel((6, 5)), (0, 0, 0))
        self.assertGreater(image.getpixel((20, 20))[1], 100)

    def test_native_qr_capacity_and_module_scale(self):
        self.lcd.clear(0xF800)
        self.lcd.draw_qr(10, 20, 3, b'x' * 154)
        self.lcd.update(); image, _ = self.model.snapshot()
        self.assertEqual(image.getpixel((10, 20)), (0, 0, 0))
        self.assertEqual(image.getpixel((10 + 3 * 45, 20)), (255, 255, 255))
        self.assertEqual(image.getpixel((9, 20)), (255, 0, 0))

    def test_short_serial_write_is_never_mirrored(self):
        observer = Mock(); self.lcd._packet_observer = observer
        self.lcd.serial.short = True
        with self.assertRaises(IOError):
            self.lcd.clear(0)
        observer.feed.assert_not_called()
        observer.disconnect_panel.assert_called_once()


class EmulatorLifecycleTests(unittest.TestCase):
    def require_socket(self):
        try:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except PermissionError:
            self.skipTest('This execution sandbox disables Unix sockets; Linux CI runs the IPC test')
        else:
            probe.close()

    def test_lossless_file_writer_without_ipc(self):
        emulator = Emulator(True); emulator.reset_panel()
        emulator.feed(bytes.fromhex('AA 01 07 E0 CC 33 C3 3C'))
        emulator.feed(bytes.fromhex('AA 3D CC 33 C3 3C'))
        server = ScreenshotServer.__new__(ScreenshotServer)
        server.emulator = emulator
        with tempfile.TemporaryDirectory() as tmp:
            server.output = Path(tmp)
            image, _ = emulator.snapshot()
            for fmt in ('png', 'bmp'):
                path = server._save(fmt)['path']
                with Image.open(path) as saved:
                    self.assertEqual(saved.tobytes(), image.tobytes())
            self.assertEqual(len(list(Path(tmp).iterdir())), 2)

    def test_disabled_does_not_construct_and_reenable_requires_baseline(self):
        factory = Mock(side_effect=Framebuffer)
        emulator = Emulator(factory=factory)
        emulator.feed(b'bad packet'); factory.assert_not_called()
        emulator.set_enabled(True); factory.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            emulator.snapshot()
        emulator.reset_panel(); emulator.feed(bytes.fromhex('AA 3D CC 33 C3 3C'))
        self.assertEqual(emulator.snapshot()[0].size, (272, 480))
        emulator.disconnect_panel()
        with self.assertRaises(RuntimeError): emulator.snapshot()
        emulator.set_enabled(False)
        self.assertIsNone(emulator.model)
        emulator.set_enabled(True)
        with self.assertRaisesRegex(RuntimeError, 'baseline'): emulator.snapshot()

    def test_unknown_visual_commands_reject_capture_until_panel_reset(self):
        emulator = Emulator(True); emulator.reset_panel()
        emulator.feed(bytes.fromhex('AA 2A CC 33 C3 3C'))
        emulator.feed(bytes.fromhex('AA 3D CC 33 C3 3C'))
        with self.assertRaisesRegex(RuntimeError, '0x2a'): emulator.snapshot()
        emulator.reset_panel(); emulator.feed(bytes.fromhex('AA 3D CC 33 C3 3C'))
        emulator.snapshot()

    def test_ssh_capture_is_lossless_unique_and_only_on_request(self):
        self.require_socket()
        emulator = Emulator(True); emulator.reset_panel()
        emulator.feed(bytes.fromhex('AA 01 F8 00 CC 33 C3 3C'))
        emulator.feed(bytes.fromhex('AA 3D CC 33 C3 3C'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ipc/control.sock'; output = Path(tmp) / 'shots'
            server = ScreenshotServer(emulator, path, output)
            try:
                self.assertFalse(output.exists())
                expected, _ = emulator.snapshot()
                files = [capture(path, fmt)['path'] for fmt in ('png', 'png', 'bmp')]
                self.assertEqual(len(set(files)), 3)
                for name in files:
                    with Image.open(name) as saved:
                        self.assertEqual(saved.tobytes(), expected.tobytes())
                        self.assertEqual(saved.size, (272, 480))
                self.assertGreater(Path(files[0]).stat().st_size, 272 * 480 * 3)
                emulator.set_enabled(False)
                with self.assertRaisesRegex(RuntimeError, 'disabled'): capture(path)
                with self.assertRaises(RuntimeError): ScreenshotServer(emulator, path, output)
            finally:
                server.close(); server.close()
            self.assertFalse(path.exists())

    def test_stale_socket_recovered_without_deleting_regular_files(self):
        self.require_socket()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ipc/control.sock'; path.parent.mkdir(mode=0o700)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as old:
                old.bind(str(path))
            server = ScreenshotServer(Emulator(), path)
            server.close()
            path.write_text('keep')
            with self.assertRaises(ValueError): ScreenshotServer(Emulator(), path)
            self.assertEqual(path.read_text(), 'keep')


class EmulatorSocketPathTests(unittest.TestCase):
    def test_systemd_and_ssh_use_same_default_socket(self):
        from dwin_emulator.runtime import default_socket
        import os
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': '/run/user/1000'}):
            ssh = default_socket()
        with patch.dict(os.environ, {}, clear=True):
            with patch('dwin_emulator.runtime.Path.home', return_value=Path.home()):
                service = default_socket()
        self.assertEqual(ssh, service)
        self.assertEqual(ssh, Path.home() / '.cache/KlipperDWIN-emulator/control.sock')
