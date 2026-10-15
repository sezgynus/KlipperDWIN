"""Atlas generation must preserve layout/asset agreement and existing outputs on failure."""
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, JpegImagePlugin
from tools import pack_shared_artwork as packer


class SharedArtworkPackerTests(unittest.TestCase):
    def source(self, root, name, size, color='white'):
        path = root/name
        Image.new('RGB', size, color).save(path, 'JPEG', quality=100, subsampling=2)
        return path

    def validate_layout(self, boxes):
        for name, a in boxes.items():
            self.assertTrue(0 <= a[0] < a[2] <= 272, name)
            self.assertTrue(0 <= a[1] < a[3] <= 480, name)
            for other, b in boxes.items():
                if name != other:
                    self.assertTrue(a[2] <= b[0] or b[2] <= a[0]
                                    or a[3] <= b[1] or b[3] <= a[1], (name, other))

    def test_filename_constants_dimensions_orientation_and_output_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.source(root, 'qr.jpg', (168, 168))
            self.source(root, 'nozzle-idle.jpeg', (72, 56), 'red')
            self.source(root, 'ışık.jpg', (32, 20), 'green')
            data, code, boxes = packer.build(root)
            namespace = {}; exec(code, namespace)
            self.assertEqual(namespace['BOXES'], boxes)
            self.assertEqual(namespace['QR_SIZE'], (168, 168))
            self.assertEqual(namespace['JPEG_QUALITY'], 100)
            self.assertEqual(namespace['SOURCE_SHA256']['qr.jpg'],
                             hashlib.sha256((root/'qr.jpg').read_bytes()).hexdigest())
            self.assertEqual(namespace['NOZZLE_IDLE_SIZE'], (72, 56))
            self.assertIn('ISIK_BOX', namespace)
            self.assertEqual(namespace['JPEG_SHA256'], hashlib.sha256(data).hexdigest())
            self.validate_layout(boxes)
            with Image.open(BytesIO(data)) as physical:
                self.assertEqual(physical.size, (480, 272))
                self.assertFalse(physical.info.get('progressive'))
                self.assertEqual(JpegImagePlugin.get_sampling(physical), 2)
                portrait = physical.transpose(Image.Transpose.ROTATE_270)
            for name, expected in [('QR', (255,255,255)), ('NOZZLE_IDLE',(255,0,0))]:
                a = boxes[name]
                pixel = portrait.getpixel(((a[0]+a[2])//2, (a[1]+a[3])//2))
                self.assertLess(max(abs(x-y) for x,y in zip(pixel, expected)), 5)
            self.assertLessEqual(len(data), 32767)

    def test_search_recovers_a_layout_that_shelf_rows_cannot_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.source(root, 'tall.jpg', (180, 480))
            self.source(root, 'side-a.jpg', (92, 240))
            self.source(root, 'side-b.jpg', (92, 240))
            _, _, boxes = packer.build(root)
            self.validate_layout(boxes)
            self.assertEqual(max(b[2] for b in boxes.values()), 272)
            self.assertEqual(max(b[3] for b in boxes.values()), 480)

    def test_repeated_generation_is_byte_identical_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.source(root, 'b.JPG', (60, 30), 'red')
            self.source(root, 'a.jpeg', (40, 50), 'blue')
            (root/'notes.md').write_text('ignored')
            (root/'subfolder').mkdir()
            a = packer.build(root)
            b = packer.build(root)
            self.assertEqual(a, b)

    def test_bad_names_oversized_sources_empty_folder_and_collisions_are_rejected(self):
        for names, sizes in [([], []), (['123.jpg'], [(1,1)]),
                             (['a-b.jpg','a_b.jpeg'], [(1,1),(1,1)]),
                             (['page.jpg'], [(1,1)]), (['wide.jpg'], [(273,1)]),
                             (['a.jpg','b.jpg'], [(272,480),(1,1)]),
                             (['a.jpg','b.jpg'], [(180,301),(180,180)])]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name, size in zip(names, sizes):
                    self.source(root, name, size)
                with self.assertRaises(ValueError):
                    packer.build(root)

    def test_compressed_slot_overflow_rejects_before_replacing_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'input'; source.mkdir()
            import random
            image = Image.frombytes('RGB', (272,480), random.Random(1).randbytes(272*480*3))
            image.save(source/'noise.jpg', 'JPEG', quality=100, subsampling=2)
            output, layout = root/'page.jpg', root/'layout.py'
            output.write_bytes(b'previous JPEG'); layout.write_bytes(b'previous layout')
            with patch.object(packer, 'ROOT', root), patch('sys.argv', [
                    'pack_shared_artwork.py', '--source-directory', str(source),
                    '--output', str(output), '--layout', str(layout)]):
                with self.assertRaises(SystemExit) as error:
                    packer.main()
                self.assertEqual(error.exception.code, 1)
            self.assertEqual(output.read_bytes(), b'previous JPEG')
            self.assertEqual(layout.read_bytes(), b'previous layout')

    def test_default_runtime_layout_cannot_lose_the_required_qr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'assets/shared-artwork'; source.mkdir(parents=True)
            self.source(source, 'other.jpg', (32,32))
            output, layout = root/'assets/petrel_shared.jpg', root/'shared_artwork_layout.py'
            output.write_bytes(b'old JPEG'); layout.write_bytes(b'old layout')
            with patch.object(packer, 'ROOT', root), patch('sys.argv', ['pack_shared_artwork.py']):
                with self.assertRaises(SystemExit):
                    packer.main()
            self.assertEqual(output.read_bytes(), b'old JPEG')
            self.assertEqual(layout.read_bytes(), b'old layout')

    def test_failed_second_replacement_rolls_back_the_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); a, b = root/'a.jpg', root/'b.py'
            a.write_bytes(b'old JPEG'); b.write_bytes(b'old layout')
            original = packer.os.replace
            def replace(source, target):
                if target == b:
                    raise OSError('layout replacement failed')
                return original(source, target)
            with patch.object(packer.os, 'replace', side_effect=replace):
                with self.assertRaises(OSError):
                    packer.publish({a:b'new JPEG', b:b'new layout'})
            self.assertEqual(a.read_bytes(), b'old JPEG')
            self.assertEqual(b.read_bytes(), b'old layout')
            self.assertEqual(set(root.iterdir()), {a,b})

    def test_shipped_outputs_match_the_input_folder(self):
        namespace = {}
        exec((packer.ROOT/'shared_artwork_layout.py').read_bytes(), namespace)
        items = packer.load_sources(packer.ROOT/'assets/shared-artwork')
        self.assertEqual(packer.pack(items), namespace['BOXES'])
        self.assertEqual({item.path.name:item.digest for item in items}, namespace['SOURCE_SHA256'])
        for item in items:
            self.assertEqual(namespace[item.name+'_SIZE'], (item.width, item.height))
        data = (packer.ROOT/'assets/petrel_shared.jpg').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), namespace['JPEG_SHA256'])
