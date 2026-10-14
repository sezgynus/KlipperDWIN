import unittest
from unittest.mock import Mock, patch
from tools.test_sram_transfer import check_range, check_full_block
from pathlib import Path


class SramTransferTests(unittest.TestCase):
    @patch('tools.test_sram_transfer.time.sleep')
    def test_full_block_writes_32768_but_never_reads_last_byte(self, sleep):
        lcd = Mock()
        original = b'x' * 32767
        pattern = (Path(__file__).resolve().parents[1] / 'assets/emulator/3.ICO').read_bytes()[:32768]
        lcd.read_sram.side_effect = [original, pattern[:32767], original]
        check_full_block(lcd, 3)
        self.assertEqual([call.args for call in lcd.write_sram.call_args_list],
                         [(0, pattern), (0, original)])
        self.assertTrue(all(call.args == (0, 32767) for call in lcd.read_sram.call_args_list))
        lcd.store_sram_as_picture.assert_not_called()
        lcd.write_flash.assert_not_called()

    @patch('tools.test_sram_transfer.time.sleep')
    def test_full_block_mismatch_restores_readable_contents(self, sleep):
        lcd = Mock()
        original = b'x' * 32767
        lcd.read_sram.side_effect = [original, bytes(32767)]
        with self.assertRaisesRegex(RuntimeError, 'Full-block mismatch'):
            check_full_block(lcd, 3)
        self.assertEqual(lcd.write_sram.call_args_list[-1].args, (0, original))
        lcd.store_sram_as_picture.assert_not_called()

    @patch('tools.test_sram_transfer.time.sleep')
    def test_success_restores_original_at_last_address(self, sleep):
        lcd = Mock()
        address = 0x7FFF
        pattern = bytes(((address + 19) & 255,))
        lcd.read_sram.side_effect = [b'x', pattern, b'x']
        check_range(lcd, address, 1, 3)
        self.assertEqual(lcd.write_sram.call_args_list[-1].args, (address, b'x'))
        lcd.store_sram_as_picture.assert_not_called()

    @patch('tools.test_sram_transfer.time.sleep')
    def test_read_failure_does_not_write_and_transfer_failure_restores(self, sleep):
        lcd = Mock()
        lcd.read_sram.side_effect = TimeoutError('no response')
        with self.assertRaises(TimeoutError):
            check_range(lcd, 0, 1, 3)
        lcd.write_sram.assert_not_called()
        lcd = Mock()
        lcd.read_sram.side_effect = [b'x', TimeoutError('no response')]
        with self.assertRaises(TimeoutError):
            check_range(lcd, 0, 1, 3)
        self.assertEqual(lcd.write_sram.call_args_list[-1].args, (0, b'x'))
        lcd.store_sram_as_picture.assert_not_called()
