import unittest
from unittest.mock import Mock, patch
from tools.test_sram_transfer import check_range


class SramTransferTests(unittest.TestCase):
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
