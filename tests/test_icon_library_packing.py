from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from PIL import Image
from io import BytesIO
from tools.pack_icon_library import BLOCK_SIZE, entries, pack, validate_block_layout
from tools.flash_icon_library import upload, validate_upload

ROOT = Path(__file__).resolve().parents[1]


class IconLibraryPackingTests(TestCase):
    def test_all_bundled_icons_decode_and_stay_inside_one_block(self):
        data = (ROOT / 'assets/emulator/7.ICO').read_bytes()
        validate_block_layout(data, 7)
        self.assertEqual(pack(data), data)
        for index, entry, offset, payload in entries(data):
            with self.subTest(icon=index):
                image = Image.open(BytesIO(payload))
                image.load()
                self.assertEqual(image.size, (int.from_bytes(entry[:2], 'big'),
                                              int.from_bytes(entry[2:4], 'big')))

    def test_repack_preserves_payload_and_adds_boundary_padding(self):
        data = bytearray(4096)
        payloads = [b'\xff\xd8' + b'x' * 27996 + b'\xff\xd9',
                    b'\xff\xd8' + b'y' * 1996 + b'\xff\xd9']
        for index, payload in enumerate(payloads):
            entry = bytes.fromhex('006e0064') + len(data).to_bytes(4, 'big')
            entry += len(payload).to_bytes(3, 'big') + bytes(5)
            data[index * 16:(index + 1) * 16] = entry
            data.extend(payload)
        with self.assertRaisesRegex(ValueError, 'crosses'):
            validate_block_layout(data, 7)
        with self.assertRaisesRegex(ValueError, 'crosses'):
            validate_upload(data)
        validate_upload(data, allow_cross_block=True)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            validate_upload(bytes(9 * BLOCK_SIZE + 1), allow_cross_block=True)
        with self.assertRaisesRegex(ValueError, 'No icon entries'):
            validate_upload(bytes(4096), allow_cross_block=True)
        result = pack(data)
        validate_block_layout(result, 7)
        original = list(entries(data))
        packed = list(entries(result))
        self.assertEqual(packed[1][2], BLOCK_SIZE)
        for before, after in zip(original, packed):
            self.assertEqual(before[3], after[3])
            self.assertEqual(before[1][:4] + before[1][8:], after[1][:4] + after[1][8:])

    @patch('tools.flash_icon_library.time.sleep')
    def test_upload_exact_blocks_directory_last_and_stop_on_failure(self, sleep):
        data = (ROOT / 'assets/emulator/7.ICO').read_bytes()
        lcd = Mock()
        upload(lcd, data)
        order = list(range(1, 8)) + [0]
        self.assertEqual([c.args[0] for c in lcd.store_sram_as_picture.call_args_list],
                         [7 + i for i in order])
        self.assertEqual([c.args for c in lcd.write_sram.call_args_list],
                         [(0, data[i * BLOCK_SIZE:(i + 1) * BLOCK_SIZE].ljust(BLOCK_SIZE, b'\x00'))
                          for i in order])
        lcd = Mock()
        lcd.store_sram_as_picture.side_effect = RuntimeError('ACK timeout')
        with self.assertRaisesRegex(RuntimeError, 'ACK timeout'):
            upload(lcd, data)
        self.assertEqual(lcd.write_sram.call_count, 1)
