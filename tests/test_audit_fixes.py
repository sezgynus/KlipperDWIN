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

    def test_invalid_command_position_and_origin_are_rejected(self):
        for field,index in (('position',0),('homing_origin',2)):
            data=snapshot();p=printer(data)
            data['status']['gcode_move'][field][index]=float('nan')
            self.assertFalse(p.update_variable())
            self.assertTrue(p.connection_error)

    def test_jog_uses_live_position_and_live_bounds(self):
        data=snapshot();p=printer(data)
        data['status']['gcode_move']['position'][0]=250
        with self.assertRaisesRegex(ValueError,'axis range'): p.moveRelative('X',1,100)
        p.sendGCode.assert_not_called()
        data['status']['gcode_move']['position'][0]=200
        data['status']['toolhead']['axis_maximum'][0]=200
        with self.assertRaisesRegex(ValueError,'axis range'): p.moveRelative('X',1,100)

    def test_power_dispatch_rechecks_after_device_query(self):
        data=snapshot();p=printer(data);p.client.post=Mock()
        p.power_off_if_on();guard=p.client.post.call_args.kwargs['guard']
        def changed(path):
            data['status']['print_stats']['state']='printing'
            return {'result':{'devices':[{'device':'Printer','status':'on'}]}}
        p.client.get.side_effect=changed
        with self.assertRaisesRegex(RuntimeError,"active operation"):guard()

    def test_power_guard_blocks_each_calibration_and_modal_recovery(self):
        p=printer(snapshot())
        for name in ('bed_mesh','screws_tilt','probe_wizard','mmu_session'):
            session=getattr(p,name);session.pending=Future()
            self.assertIsNotNone(p.power_off_block_reason());session.pending=None
        p._jog_restore='RESTORE_GCODE_STATE NAME=LCD_JOG MOVE=0'
        self.assertIsNotNone(p.power_off_block_reason())

    def test_heater_editor_jumps_off_gap_in_both_directions(self):
        v=display(snapshot());v._tune_edit=next(s for s in v.pd.print_settings() if s.key.startswith('nozzle@'))
        v._tune_target=0;v.get_encoder_state=Mock(return_value=v.ENCODER_DIFF_CW)
        v._focus_edit_input();self.assertEqual(v._tune_target,5)
        v.get_encoder_state.return_value=v.ENCODER_DIFF_CCW
        v._focus_edit_input();self.assertEqual(v._tune_target,0)

