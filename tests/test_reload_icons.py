import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from tools import lcd_connection as connection
from tools import reload_icons as tool


class ReloadIconTests(unittest.TestCase):
    def test_reads_configured_uart_without_executing_environment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / '.config/KlipperDWIN/KlipperDWIN.env'
            config.parent.mkdir(parents=True)
            config.write_text('DWIN_SERIAL_PORT="/dev/serial0"\nIGNORED=$(false)\n')
            with patch.dict(os.environ, {}, clear=True), patch.object(connection.Path, 'home', return_value=Path(tmp)):
                self.assertEqual(connection.configured_port(), '/dev/serial0')

    def test_active_service_cannot_open_uart(self):
        with patch.object(tool, 'configured_port', return_value='/dev/serial0'), \
                patch.object(tool.sys, 'argv', ['reload_icons.py']), \
                patch.object(tool.subprocess, 'run', return_value=Mock(stdout='active\n')), \
                patch.object(tool, 'ManualDisplay') as display:
            with self.assertRaises(SystemExit):
                tool.main()
            display.assert_not_called()

    def test_force_reload_and_uart_close_on_success_or_failure(self):
        for error in (None, TimeoutError('upload failed')):
            lcd = Mock()
            with patch.object(tool, 'configured_port', return_value='/dev/serial0'), \
                    patch.object(tool.sys, 'argv', ['reload_icons.py']), \
                    patch.object(tool.subprocess, 'run', return_value=Mock(stdout='inactive\n')), \
                    patch.object(tool, 'ManualDisplay', return_value=lcd) as display, \
                    patch.object(tool, 'sync_library', side_effect=error) as sync:
                if error:
                    with self.assertRaises(TimeoutError):
                        tool.main()
                else:
                    tool.main()
                display.assert_called_once_with('/dev/serial0')
                sync.assert_called_once_with(lcd, force=True, automatic=False)
                lcd.close.assert_called_once_with()
