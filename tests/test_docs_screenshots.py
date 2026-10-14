"""Published documentation must never pair fresh panel pixels with stale frames."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from PIL import Image, ImageChops
from tools import render_docs_screenshots as renderer


class DocumentationPublicationTests(unittest.TestCase):
    def test_finish_waits_for_mesh_drawing_and_rejects_emulator_errors(self):
        image = Image.new('RGB', (272, 480))
        view = SimpleNamespace(_mesh_pending_points=object(), _emulator_errors=[],
                               lcd=Mock(), framebuffer=Mock())
        slices = [False, True]
        def advance(**kwargs):
            if slices.pop(0):
                view._mesh_pending_points = None
        view._advance_mesh_render = Mock(side_effect=advance)
        view.framebuffer.snapshot.return_value = (image, 1)
        self.assertIs(renderer.finish(view, dashboard=False), image)
        self.assertEqual(view._advance_mesh_render.call_count, 2)
        view.lcd.update.assert_called_once()
        view._emulator_errors.append(ValueError('Unsupported packet'))
        with self.assertRaisesRegex(RuntimeError, 'Emulator failed'):
            renderer.finish(view, dashboard=False)

    def invoke(self, root, color, *arguments):
        scene = ('example', 'printing', 'Example', 'Örnek',
                 lambda: Image.new('RGB', (272, 480), color))
        with patch.object(renderer, 'ROOT', root), patch.object(renderer, 'SCENES', [scene]), \
                patch.object(sys, 'argv', ['render_docs_screenshots.py', *arguments]):
            renderer.main()

    def test_default_repository_refresh_keeps_frames_and_galleries_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for color in ('red', 'blue'):
                self.invoke(root, color)
                folder = root/'docs/assets/screens'
                with Image.open(folder/'example.png') as panel, Image.open(folder/'framed/example.png') as frame:
                    self.assertIsNone(ImageChops.difference(panel, frame.convert('RGB').crop((128, 122, 400, 602))).getbbox())
                    self.assertEqual(panel.getpixel((0, 0)), Image.new('RGB', (1, 1), color).getpixel((0, 0)))
                for filename, label in [('screenshots.md', 'Full-size PNG'), ('screenshots_TR.md', 'Tam boyut PNG')]:
                    gallery = (root/'docs'/filename).read_text(encoding='utf-8')
                    self.assertIn('href="assets/screens/example.png"', gallery)
                    self.assertIn('assets/screens/framed/example.png', gallery)
                    self.assertIn(label, gallery)

    def test_frame_failure_leaves_previous_native_and_gallery_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root/'docs/assets/screens'; folder.mkdir(parents=True)
            panel = folder/'example.png'; panel.write_bytes(b'previous panel')
            gallery = root/'docs/screenshots.md'; gallery.write_text('previous gallery')
            with patch('dwin_emulator.presentation.with_frame', side_effect=OSError('Cannot render frame')):
                with self.assertRaises(OSError): self.invoke(root, 'blue')
            self.assertEqual(panel.read_bytes(), b'previous panel')
            self.assertEqual(gallery.read_text(), 'previous gallery')

    def test_custom_review_directory_remains_native_unless_frame_requested(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); review = root/'review'
            self.invoke(root, 'red', '--output-directory', str(review))
            self.assertTrue((review/'example.png').is_file())
            self.assertFalse((review/'framed').exists())
            self.assertFalse((root/'docs').exists())
            self.invoke(root, 'blue', '--output-directory', str(review), '--frame')
            self.assertTrue((review/'framed/example.png').is_file())
            self.assertFalse((root/'docs').exists())
