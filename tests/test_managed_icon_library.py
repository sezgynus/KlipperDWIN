from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import icon_library as icons
from tools.pack_icon_library import entries, validate_block_layout


class ManagedIconTests(unittest.TestCase):
    def setUp(self):
        icons._ATTEMPTS.clear()

    def tearDown(self):
        icons._ATTEMPTS.clear()

    def test_best_fit_reuses_earlier_hole_with_out_of_order_ids(self):
        large = b'\xff\xd8' + bytes(29996) + b'\xff\xd9'
        small = b'\xff\xd8' + bytes(4996) + b'\xff\xd9'
        data = icons.pack_records([(10, 20, 20, large), (11, 20, 20, small)])
        table = {i: (o, p) for i, e, o, p in entries(data)}
        self.assertEqual(table[10], (32768, large))
        self.assertEqual(table[11], (4096, small))
        validate_block_layout(data, 7)
        self.assertEqual(data[32767], 0)
        self.assertEqual(data[65535], 0)

    def test_oversize_capacity_duplicates_and_final_byte_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'capacity'):
            icons.pack_records([(0, 1, 1, bytes(32768))])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            icons.pack_records([(1, 1, 1, b'x'), (1, 1, 1, b'y')])
        with self.assertRaisesRegex(ValueError, 'exceed'):
            icons.pack_records([(i, 1, 1, bytes(32767)) for i in range(9)])

    def test_sources_decode_ids_are_stable_and_rename_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = BytesIO()
            Image.new('RGB', (20, 20), 'red').save(out, 'JPEG')
            (root / '092-about.jpg').write_bytes(out.getvalue())
            data = icons.build_library(root)
            (root / '092-about.jpg').rename(root / '092-renamed.jpeg')
            self.assertEqual(data, icons.build_library(root))
            (root / '092-duplicate.jpg').write_bytes(out.getvalue())
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                icons.build_library(root)

    def panel(self):
        lcd = Mock()
        memory = bytearray(16384)
        memory[:64] = b'a' * 64
        memory[256:272] = b's' * 16
        lcd.read_flash.side_effect = lambda address, size: bytes(memory[address:address + size])
        def write(address, data):
            memory[address:address + len(data)] = data
        lcd.write_flash.side_effect = write
        return lcd, memory

    @patch('icon_library.time.sleep')
    def test_initial_upload_unchanged_and_one_changed_block(self, sleep):
        data = icons.pack_records([(10, 20, 20, b'x' * 30000), (11, 20, 20, b'y' * 1000)])
        lcd, memory = self.panel()
        with patch('icon_library.build_library', return_value=data):
            self.assertTrue(icons.sync_library(lcd))
            self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list], [8, 7])
            self.assertTrue(all(c.args[0] == 0 and len(c.args[1]) == 32767
                                for c in lcd.write_sram.call_args_list))
            lcd.reset_mock()
            self.assertFalse(icons.sync_library(lcd))
            lcd.write_sram.assert_not_called()
            lcd.write_flash.assert_not_called()
        changed = bytearray(data)
        changed[32768] ^= 1
        with patch('icon_library.build_library', return_value=bytes(changed)):
            self.assertTrue(icons.sync_library(lcd))
            self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list], [8, 7])
        self.assertEqual(memory[:64], b'a' * 64)
        self.assertEqual(memory[256:272], b's' * 16)

    @patch('icon_library.time.sleep')
    def test_partial_upload_resumes_and_reconnect_does_not_repeat_failed_flash(self, sleep):
        data = icons.pack_records([(10, 20, 20, b'x' * 30000), (11, 20, 20, b'y' * 1000)])
        lcd, _ = self.panel()
        lcd.store_sram_as_picture.side_effect = [None, RuntimeError('lost ACK')]
        with patch('icon_library.build_library', return_value=data):
            with self.assertRaisesRegex(RuntimeError, 'lost ACK'):
                icons.sync_library(lcd)
            count = lcd.store_sram_as_picture.call_count
            with self.assertRaisesRegex(RuntimeError, 'blocked'):
                icons.sync_library(lcd)
            self.assertEqual(lcd.store_sram_as_picture.call_count, count)
            icons._ATTEMPTS.clear()  # Next process/service start.
            lcd.reset_mock()
            lcd.store_sram_as_picture.side_effect = None
            self.assertTrue(icons.sync_library(lcd))
            self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list], [7])

    def test_manifest_crc_rejects_partial_or_corrupt_metadata(self):
        raw = icons.metadata([b'x' * 32])
        self.assertEqual(icons.parse_metadata(raw), [b'x' * 32])
        broken = bytearray(raw)
        broken[20] ^= 1
        self.assertEqual(icons.parse_metadata(broken), [])

    def test_startup_syncs_icons_before_boot_animation(self):
        from test_uart import Port, Driver, serial_module
        port = Port([b'\xAA\x00OK' + Driver.TAIL])
        events = []
        def icon_sync(lcd):
            events.append('icons')
        with patch.object(serial_module, 'Serial', return_value=port, create=True), \
                patch('icon_library.sync_library', side_effect=icon_sync):
            lcd = Driver('/dev/fake', wake_delay=0,
                         startup_progress=lambda lcd, value: events.append(('progress', value)))
        lcd.close()
        self.assertNotIn(0x25, [frame[1] for frame in port.frames])
        self.assertNotIn(0x26, [frame[1] for frame in port.frames])
        self.assertEqual(events, ['icons', ('progress', 40), ('progress', 70)])

    def test_checked_in_pack_matches_sources_and_all_payloads_are_preserved(self):
        root = Path(__file__).resolve().parents[1]
        data = icons.build_library(root / 'assets/icons')
        self.assertEqual(data, (root / 'assets/emulator/7.ICO').read_bytes())
        for index, entry, offset, payload in entries(data):
            self.assertEqual(payload, (root / 'assets/icons' / f'{index:03d}.jpg').read_bytes())
        validate_block_layout(data, 7)
