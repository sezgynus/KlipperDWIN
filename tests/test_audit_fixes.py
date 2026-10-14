"""Regressions for the source audit, including physical UART packet budgets."""
import io
import json
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image, ImageChops
from test_capabilities import printer, display, snapshot
from test_t5uic1_driver import driver
from moonraker_subscription import MoonrakerSubscription
from moonraker_client import MoonrakerError
from dwin_emulator.assets import PanelAssets
from dwin_emulator.framebuffer import Framebuffer
from ui_events import InputEvent


class AuditRegressionTests(unittest.TestCase):
    def test_write_and_read_io_failures_close_uart(self):
        for operation in ('write','read'):
            lcd=driver()
            if operation == 'write':
                lcd.serial.write=Mock(side_effect=OSError('port lost'))
                call=lambda:lcd.draw_rectangle(1,0,0,0,1,1)
            else:
                lcd.serial.chunks.append(b"x")
                lcd.serial.read=Mock(side_effect=OSError('port lost'))
                call=lcd._read_available
            lcd.serial.close=Mock()
            with self.assertRaises(OSError): call()
            self.assertTrue(lcd._closed)
            lcd.serial.close.assert_called_once()

    def test_job_pin_lowercase_configuration_retains_command_spelling(self):
        data=snapshot();name='Turn_OFF_Heaters_After_Job';obj='output_pin '+name
        data['objects'].append(obj);data['settings'][obj.casefold()]={'pwm':False}
        data['status'][obj]={'value':0};p=printer(data)
        self.assertIn('pin@'+name,[s.key for s in p.print_settings()])
        p.set_print_setting('pin@'+name,1)
        p.sendGCode.assert_called_with('SET_PIN PIN='+name+' VALUE=1')

