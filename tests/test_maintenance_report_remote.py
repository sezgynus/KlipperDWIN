"""Last explicit diagnostic export uses the existing remote HTTP boundary."""
import json
import unittest
from unittest.mock import Mock
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import test_remote_display as fixture
from dwin_emulator.remote import RemoteDisplayServer
from test_t5uic1_driver import driver


class DiagnosticRemoteTests(unittest.TestCase):
    def test_download_is_read_only_bounded_and_host_protected(self):
        emulator = fixture.FakeEmulator()
        provider = Mock(return_value=b'{"version":1,"records":[]}')
        server = RemoteDisplayServer(emulator,Mock(),host='127.0.0.1',port=0,report_provider=provider)
        self.addCleanup(server.close)
        base = 'http://127.0.0.1:%d'%server.port
        with urlopen(base+'/maintenance-report.json',timeout=3) as response:
            self.assertEqual(json.loads(response.read())['version'],1)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        with self.assertRaises(HTTPError) as err:
            urlopen(Request(base+'/maintenance-report.json',headers={'Host':'evil.example'}),timeout=3)
        self.assertEqual(err.exception.code,403)
        self.assertEqual(emulator.calls,0)
        provider.return_value = b'x'*65537
        with self.assertRaises(HTTPError) as err:
            urlopen(base+'/maintenance-report.json',timeout=3)
        self.assertEqual(err.exception.code,503)

    def test_uart_counters_preserve_backlight_packet_and_never_read_hardware(self):
        lcd = driver()
        lcd._diagnostic_counts = {}
        lcd.set_backlight(128)
        frame = lcd.serial.frames[-1]
        self.assertEqual(lcd._backlight_raw,128)
        before = len(lcd.serial.frames)
        evidence = lcd.diagnostics()
        self.assertEqual(evidence['tx_frames'],1)
        self.assertEqual(evidence['tx_bytes'],len(frame))
        self.assertEqual(len(lcd.serial.frames),before)

if __name__ == '__main__':
    unittest.main()
