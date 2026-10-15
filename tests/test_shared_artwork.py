import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile

import shared_artwork as artwork


class SharedArtworkTests(unittest.TestCase):
    def setUp(self):
        artwork._attempts.clear()
        self.addCleanup(artwork._attempts.clear)

    @patch('shared_artwork.time.sleep')
    def test_sync_commits_only_after_picture_ack_and_skips_unchanged(self, _):
        lcd = Mock()
        memory = {}
        lcd.read_flash.side_effect = lambda address, size: memory.get(address, bytes(size))
        lcd.write_flash.side_effect = lambda address, data: memory.update({address: data})
        self.assertTrue(artwork.sync(lcd))
        lcd.store_sram_as_picture.assert_called_once_with(1, timeout=5)
        lcd.write_sram.assert_called_once_with(0, artwork.SOURCE.read_bytes())
        names = [call[0] for call in lcd.mock_calls]
        self.assertLess(names.index('store_sram_as_picture'), names.index('write_flash'))
        lcd.reset_mock()
        self.assertFalse(artwork.sync(lcd))
        lcd.write_sram.assert_not_called()
        self.assertTrue(artwork.sync(lcd, force=True))
        lcd.store_sram_as_picture.assert_called_once_with(1, timeout=5)

    @patch('shared_artwork.time.sleep')
    def test_failed_picture_never_checkpoints_or_retries_in_same_process(self, _):
        lcd = Mock()
        lcd.read_flash.return_value = bytes(artwork.SIZE)
        lcd.store_sram_as_picture.side_effect = TimeoutError('missing ACK')
        with self.assertRaises(TimeoutError):
            artwork.sync(lcd)
        lcd.write_flash.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'already failed'):
            artwork.sync(lcd)
        self.assertEqual(lcd.store_sram_as_picture.call_count, 1)

    def test_invalid_artwork_does_not_touch_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'bad.jpg'; p.write_bytes(bytes(32768))
            lcd = Mock()
            with self.assertRaises(ValueError):
                artwork.sync(lcd, p)
            self.assertEqual(lcd.mock_calls, [])

    def test_mismatched_jpeg_and_generated_layout_do_not_touch_panel(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'different.jpg'
            Image.new('RGB', (480,272), 'red').save(p, 'JPEG', subsampling=2)
            lcd = Mock()
            with self.assertRaisesRegex(ValueError, 'JPEG/layout mismatch'):
                artwork.sync(lcd, p)
            self.assertEqual(lcd.mock_calls, [])

    def test_ico_no_longer_contains_qr_and_reserved_flash_ranges_do_not_overlap(self):
        from icon_library import build_library, METADATA_ADDRESS
        import boot_artwork
        self.assertFalse(any(build_library()[155*16:156*16]))
        self.assertGreaterEqual(artwork.ADDRESS, boot_artwork.ADDRESS + boot_artwork.SIZE)
        self.assertLessEqual(artwork.ADDRESS + artwork.SIZE, METADATA_ADDRESS)
