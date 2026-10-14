import unittest
from unittest.mock import Mock, patch
from concurrent.futures import Future
import test_print_tuning
from test_capabilities import display
from test_mmu_control import mmu_snapshot
from test_t5uic1_driver import driver
from PIL import Image
from io import BytesIO
from thumbnail_preview import image_jpeg


class PrintFocusTests(unittest.TestCase):
    def view(self, mmu=False):
        data=test_print_tuning.PrintTuningTests().data()
        data['status']['print_stats'].update(state='printing',filename='part.gcode',print_duration=120,info={'current_layer':85,'total_layer':200})
        data['status']['virtual_sdcard']['progress']=.42
        if mmu:
            data['status']['mmu']=mmu_snapshot()['status']['mmu'];data['objects'].append('mmu')
        v=display(data);v.lcd.DWIN_WIDTH=272;v.lcd.DWIN_HEIGHT=480
        v._sync_thumbnail_cache=Mock();v._print_thumbnail_key=None
        v._sync_fan_animation=Mock();v.checkkey=v.PrintProcess
        v.get_encoder_state=Mock(return_value=v.ENCODER_DIFF_ENTER)
        return v,data


    def test_tune_apply_icon_and_native_preview_keep_runtime_labels(self):
        v, _ = self.view()
        v.lcd = driver()
        v._tune_edit = v.pd.print_settings()[0]
        v._tune_target = 100
        with patch('t5uic1_driver.time.sleep'):
            v._focus_edit_draw()
        packets = v.lcd.MYSERIAL1.frames
        self.assertEqual(sum(p[1] == 0x23 for p in packets), 1)
        self.assertFalse(any(p[1] == 0x08 for p in packets))
        self.assertLess(sum(p[1] == 0x05 for p in packets), 12)
        self.assertIn(b'Apply', [p[11:-4] for p in packets if p[1] == 0x11])
        v.lcd.MYSERIAL1.frames.clear()
        with patch('t5uic1_driver.time.sleep'):
            v._focus_print_open()
        packets = v.lcd.MYSERIAL1.frames
        self.assertIn(b'Preview', [p[11:-4] for p in packets if p[1] == 0x11])
        self.assertTrue(any(p[1] == 0x08 for p in packets))

    def test_tune_selection_bitmap_cap_packet_budget(self):
        v, _ = self.view()
        v.lcd = driver()
        with patch('t5uic1_driver.time.sleep'):
            v._focus_round(10, 64, 252, 20, 0x2967, 5)
        frames = v.lcd.MYSERIAL1.frames
        self.assertLessEqual(len(frames), 6)
        self.assertLess(sum(map(len, frames)), 550)
        self.assertEqual(sum(frame[1] == 0x08 for frame in frames), 2)

    def test_all_seventeen_settings_fit_one_screen(self):
        v,_=self.view();v._focus_tune_open()
        self.assertEqual(len(v._focus_tune_rows()),18)
        self.assertLessEqual(max(y+(24 if s is None else 20) for s,y in v._focus_tune_rows()),480)
        self.assertEqual(v.checkkey,v.Tune)
        v.lcd.reset_mock();v._focus_tune_tick();v.lcd.draw_rectangle.assert_not_called()

    def test_quiet_edit_is_optimistic_and_rejects_without_popup(self):
        v,_=self.view();future=Future();v.pd.set_print_setting=Mock(return_value=future)
        v._focus_tune_open();v._tune_edit=v.pd.print_settings()[0];v._tune_target=125;v.checkkey=v.TuneEdit
        v._show_message=Mock();v._focus_edit_input()
        self.assertEqual(v._quiet_edits['speed']['target'],125)
        v.pd.set_print_setting.assert_called_once_with('speed',125,report_error=False)
        future.set_exception(ValueError('Rejected'));v._focus_tune_tick()
        self.assertNotIn('speed',v._quiet_edits);self.assertIn('speed',v._quiet_blinks)
        v._show_message.assert_not_called()

    def test_late_old_failure_does_not_revert_newer_edit(self):
        v,_=self.view();old=Future();new=Future()
        v._focus_submit('speed',120,lambda:old);v._focus_submit('speed',130,lambda:new)
        old.set_exception(ValueError('Old failure'));v._focus_tick_quiet()
        self.assertEqual(v._quiet_edits['speed']['target'],130);self.assertNotIn('speed',v._quiet_blinks)

    def test_slow_request_is_not_rejected_by_elapsed_time(self):
        v,_=self.view();f=Future()
        with patch('ui_print_focus.time.monotonic',return_value=0):v._focus_submit('speed',130,lambda:f)
        with patch('ui_print_focus.time.monotonic',return_value=1000):v._focus_tick_quiet()
        self.assertIn('speed',v._quiet_edits);self.assertFalse(v._quiet_blinks)

    def test_subscription_confirmation_is_silent_and_epoch_clears_pending(self):
        v,data=self.view();f=Future();v._focus_submit('speed',130,lambda:f)
        data['status']['gcode_move']['speed_factor']=1.3;v.pd.update_variable();v._focus_tick_quiet()
        self.assertNotIn('speed',v._quiet_edits);self.assertFalse(v._quiet_blinks)
        v._focus_submit('speed',140,lambda:Future());data['epoch']+=1;v.pd.update_variable();v._focus_tick_quiet()
        self.assertFalse(v._quiet_edits)


    def test_stop_selection_redraws_only_buttons_and_unchanged_is_free(self):
        view, _ = self.view()
        view.checkkey = view.Print_window
        view.pd.HMI_flag.select_flag = False
        view._focus_stop_draw()
        view.lcd.reset_mock()
        view.Clear_Main_Window = Mock()
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view._focus_stop_input()
        self.assertTrue(view.pd.HMI_flag.select_flag)
        self.assertEqual(view.lcd.show_icon.call_count, 2)
        view.lcd.draw_bitmap.assert_not_called()
        self.assertEqual(view.lcd.draw_text.call_count, 2)
        view.Clear_Main_Window.assert_not_called()
        view.lcd.reset_mock()
        view._focus_stop_input()
        view.lcd.show_icon.assert_not_called()
        view.lcd.draw_bitmap.assert_not_called()
        view.lcd.draw_text.assert_not_called()

    def test_cancel_waits_through_macro_and_only_completes_on_print_status(self):
        v, data = self.view()
        future = Future()
        v.pd.cancel_job = Mock(return_value=future)
        v._show_message = Mock()
        v._restore_action_screen = Mock()
        v.checkkey = v.Print_window
        v.pd.HMI_flag.select_flag = True
        v._focus_stop_input()
        v.pd.cancel_job.assert_called_once()
        self.assertTrue(v._stop_waiting)
        self.assertEqual(v._action_feedback.confirmation_timeout, None)
        self.assertEqual(v.checkkey, v.PrintProcess)
        self.assertEqual(v._focus_buttons()[-1][0], 'Stopping')
        labels = [x.args[-1] for x in v.lcd.draw_text.call_args_list]
        self.assertIn('Stopping', labels)
        self.assertFalse(any('Waiting for current command' in str(x)
                             for x in labels))
        self.assertLessEqual(v.select_print.now, 1)
        with patch('command_feedback.time.monotonic',
                   return_value=v._action_feedback.started + 600):
            self.assertFalse(v._poll_action())
        v._show_message.assert_not_called()
        future.set_result('ok')
        self.assertFalse(v._poll_action())
        self.assertTrue(v._stop_waiting)
        data['status']['print_stats']['state'] = 'cancelled'
        v.pd.update_variable()
        self.assertFalse(v._poll_action())
        self.assertFalse(v._stop_waiting)
        v._restore_action_screen.assert_called_once()
        v._show_message.assert_not_called()

    def test_stopping_button_is_inactive_unselectable_and_live_status_updates(self):
        v, data = self.view()
        future = Future()
        v.pd.cancel_job = Mock(return_value=future)
        v.pd.HMI_flag.select_flag = True
        v.checkkey = v.Print_window
        v.select_print.now = 2
        v._focus_stop_input()
        self.assertEqual(v.checkkey, v.PrintProcess)
        self.assertEqual(v.select_print.now, 1)
        self.assertEqual(v._focus_buttons()[-1][0], 'Stopping')
        v.lcd.reset_mock()
        v._focus_draw_buttons()
        self.assertEqual(v.select_print.now, 1)
        self.assertNotEqual(v._focus_button_render[2][2], True)
        self.assertEqual(v._focus_button_render[2][3], 0x7BEF)

        # Even direct encoder dispatch may not trigger a second cancel.
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CCW
        v._focus_print_input()
        self.assertEqual(v.select_print.now, 0)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_ENTER
        v.select_print.now = 2  # Also guard out-of-band/stale selection.
        v._focus_print_input()
        v.pd.cancel_job.assert_called_once()

        # The dashboard keeps refreshing instead of showing a waiting page.
        v.select_print.now = 1
        v.lcd.reset_mock()
        data['status']['virtual_sdcard']['progress'] = .60
        v.pd.update_variable()
        v._focus_print_tick()
        self.assertEqual(v.checkkey, v.PrintProcess)
        self.assertEqual(v._focus_buttons()[-1][0], 'Stopping')

    def test_cancel_real_rejection_displays_error_and_clears_waiting(self):
        v, _ = self.view()
        future = Future()
        v.pd.cancel_job = Mock(return_value=future)
        v._show_message = Mock()
        v.checkkey = v.Print_window
        v.pd.HMI_flag.select_flag = True
        v._focus_stop_input()
        future.set_exception(RuntimeError('Moonraker rejected cancel'))
        self.assertTrue(v._poll_action())
        self.assertFalse(v._stop_waiting)
        v._show_message.assert_called_once()

    def test_pause_direct_stop_requires_safe_confirmation(self):
        v,_=self.view();v.select_print.set(1);v.pd.pause_job=Mock(return_value=Future())
        v.Popup_window_PauseOrStop=Mock();v.HMI_Printing()
        v.pd.pause_job.assert_called_once_with(report_error=False);v.Popup_window_PauseOrStop.assert_not_called()
        self.assertEqual(v._focus_buttons()[1][0],'Resume')
        v.select_print.set(2);v.HMI_Printing();v.Popup_window_PauseOrStop.assert_called_once()
        self.assertFalse(v.pd.HMI_flag.select_flag)

    def test_power_popup_restores_editor_draft(self):
        v,_=self.view();v._tune_edit=v.pd.print_settings()[0];v._tune_target=137;v.checkkey=v.TuneEdit
        self.assertTrue(v._restore_power_editor());self.assertEqual(v._tune_target,137)

    def test_mmu_error_scroll_only_repaints_viewport_and_unchanged_selection_is_free(self):
        v, data = self.view(mmu=True)
        data['status']['mmu'].update(print_state='pause_locked',
                                     reason_for_pause='Toolhead sensor is active. ' * 30)
        v.pd.update_variable()
        v._focus_error_open()
        v.Clear_Popup_Area = Mock()
        v.Draw_Title = Mock()
        v.lcd.reset_mock()
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v._focus_error_input()
        self.assertEqual(v._focus_error_scroll, 1)
        v.Clear_Popup_Area.assert_not_called()
        v.Draw_Title.assert_not_called()
        v.lcd.draw_rectangle.assert_called_once_with(
            1, v.lcd.Color_Bg_Black, 12, 45, 260, 348)
        v.lcd.draw_bitmap.assert_not_called()
        v.lcd.reset_mock()
        v._focus_error_scroll = max(0, len(v._focus_error_lines) - 15)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v._focus_error_input()
        self.assertEqual(v._focus_error_choice, 1)
        self.assertEqual(v.lcd.show_icon.call_count, 2)
        v.lcd.draw_bitmap.assert_not_called()
        v.lcd.reset_mock()
        v._focus_error_input()
        v.lcd.draw_rectangle.assert_not_called()
        v.lcd.draw_bitmap.assert_not_called()
        v.lcd.draw_text.assert_not_called()

    def test_mmu_full_error_reader_recovery_and_return(self):
        v,data=self.view(mmu=True)
        data['status']['mmu'].update(print_state='pause_locked',reason_for_pause='Toolhead sensor is still active. '*30)
        v.pd.update_variable();self.assertEqual(v._focus_buttons()[1][0],'MMU')
        v._focus_error_open();self.assertGreater(len(v._focus_error_lines),15)
        v._focus_error_input();self.assertEqual(v.checkkey,v.MMUMenu)
        self.assertEqual(v._mmu_page,'recover');self.assertTrue(v._mmu_return_print)
        v.Goto_PrintProcess=Mock();v._mmu_history=[];v.pd.mmu_session.pending=None;v._mmu_back()
        v.Goto_PrintProcess.assert_called_once();self.assertFalse(v._mmu_return_print)

    def test_status_text_changes_do_not_redraw_rounded_backing(self):
        v, _ = self.view()
        v._focus_render = {}
        v._focus_state_panel('Idle', '')
        v.lcd.reset_mock()
        v._focus_state_panel('Loading filament', '')
        v.lcd.draw_bitmap.assert_not_called()
        v.lcd.draw_rectangle.assert_called_once_with(1, 0x2967, 22, 270, 253, 300)
        self.assertEqual(v.lcd.draw_text.call_count, 2)
        v.lcd.reset_mock()
        v._focus_state_panel('Sensor failed', 'Sensor failed')
        self.assertGreater(v.lcd.draw_bitmap.call_count, 0)
        v.lcd.reset_mock()
        v._focus_state_panel('Other error', 'Other error')
        v.lcd.draw_bitmap.assert_not_called()

    def test_print_render_has_no_work_when_unchanged(self):
        v,_=self.view();v._focus_print_open();v.lcd.reset_mock()
        v._focus_print_tick();v.lcd.draw_rectangle.assert_not_called();v.lcd.draw_text.assert_not_called()

    def test_print_preview_is_small_baseline_420_and_dark_foreground_protected(self):
        from PIL import JpegImagePlugin
        stream=BytesIO();Image.new('RGBA',(256,256),(0,0,0,255)).save(stream,'PNG')
        with Image.open(BytesIO(image_jpeg(stream.getvalue(),size=88))) as image:
            self.assertEqual(image.size,(88,88));self.assertEqual(JpegImagePlugin.get_sampling(image),2)
            self.assertGreaterEqual(min(image.getpixel((44,44))),48)

    def test_every_real_draw_stays_inside_panel(self):
        v,_=self.view();v.lcd=driver();v.lcd.DWIN_WIDTH=272;v.lcd.DWIN_HEIGHT=480
        v.Goto_PrintProcess();v._focus_tune_open();v._tune_edit=v.pd.print_settings()[0];v._tune_target=100;v._focus_edit_draw()
        for frame in v.lcd.serial.frames:
            if frame[1]==5:
                x0,y0,x1,y1=[int.from_bytes(frame[i:i+2],'big') for i in (5,7,9,11)]
                self.assertTrue(0<=x0<=x1<272,(x0,y0,x1,y1));self.assertTrue(0<=y0<=y1<480,(x0,y0,x1,y1))

    def test_pause_state_change_updates_fields_without_clearing_screen(self):
        v,data=self.view();v.Goto_PrintProcess();v.Goto_PrintProcess=Mock()
        data['status']['print_stats']['state']='paused';v.pd.update_variable()
        v._present_print_state();v.Goto_PrintProcess.assert_not_called()
        self.assertEqual(v._focus_buttons()[1][0],'Resume')

    def test_selection_sends_two_complete_icons_and_two_labels_only(self):
        v,_=self.view();v.lcd=driver();v._focus_draw_buttons()
        v.lcd.serial.frames.clear();v.select_print.set(1);v._focus_draw_buttons()
        frames=v.lcd.serial.frames
        self.assertEqual([f[1] for f in frames],[0x23,0x11,0x23,0x11])
        self.assertLess(sum(map(len,frames)),80)
        v.lcd.serial.frames.clear();v._focus_draw_buttons()
        self.assertEqual(v.lcd.serial.frames,[])

    def test_pause_resume_replaces_only_middle_button(self):
        v,data=self.view();v.lcd=driver();v._focus_draw_buttons()
        data['status']['print_stats']['state']='paused';v.pd.update_variable()
        v.lcd.serial.frames.clear();v._focus_draw_buttons()
        self.assertEqual([f[1] for f in v.lcd.serial.frames],[0x23,0x11])

    def test_button_states_have_identical_transparency_masks(self):
        from dwin_emulator.assets import PanelAssets
        from lcd_resources import PRINT_BUTTON_SELECTED,ICON_LIBRARY_ID
        assets=PanelAssets()
        for normal,selected in PRINT_BUTTON_SELECTED.items():
            with self.subTest(normal=normal):
                a=assets.icon(ICON_LIBRARY_ID,normal)
                b=assets.icon(ICON_LIBRARY_ID,selected)
                self.assertEqual(a.size,b.size)
                self.assertIn(a.size,((78,36),(119,36)))
                self.assertEqual([max(p)>31 for p in a.getdata()], [max(p)>31 for p in b.getdata()])

    def test_all_button_variants_round_trip_without_pixel_residue(self):
        from dwin_emulator.assets import PanelAssets
        from dwin_emulator.framebuffer import Framebuffer
        from PIL import ImageChops
        v,data=self.view(mmu=True);v.lcd=driver();v.framebuffer=Framebuffer(PanelAssets())
        v.lcd._packet_observer=v.framebuffer;v.lcd.clear(0x2125)
        for state,locked in [('printing',False),('paused',False),('paused',True),('complete',False)]:
            data['status']['print_stats']['state']=state
            data['status']['mmu'].update(print_state='pause_locked' if locked else state,reason_for_pause='Unload failed' if locked else '')
            v.pd.update_variable();v._focus_button_shape=None;v.select_print.set(0);v._focus_draw_buttons();v.lcd.update()
            original=v.framebuffer.snapshot()[0]
            for selected in range(1,len(v._focus_buttons())):
                v.select_print.set(selected);v._focus_draw_buttons();v.select_print.set(0);v._focus_draw_buttons();v.lcd.update()
                self.assertIsNone(ImageChops.difference(original,v.framebuffer.snapshot()[0]).getbbox(),state)

    def test_terminal_layout_erases_old_third_button_once(self):
        v,data=self.view();v._focus_draw_buttons();v.lcd.reset_mock()
        data['status']['print_stats']['state']='complete';v.pd.update_variable();v._focus_draw_buttons()
        v.lcd.draw_rectangle.assert_called_once_with(1,v.lcd.Color_Bg_Black,14,311,258,349)
        self.assertEqual(v.lcd.show_icon.call_count,2)

    def test_small_font_zero_id_is_not_replaced_by_default_font(self):
        v,_=self.view();v.lcd.font6x12=0;v.lcd.font8x16=1
        v._focus_text('PRINT',14,64,font=v.lcd.font6x12)
        self.assertEqual(v.lcd.draw_text.call_args.args[2],0)

    def test_group_headers_have_full_font_height_and_spacing(self):
        v,_=self.view();v.lcd.font6x12=0;v.lcd.font8x16=1
        v._focus_tune_open();group=None
        for setting,y in v._focus_tune_rows():
            if setting and setting.group!=group:
                group=setting.group
                header=next(c for c in v.lcd.draw_text.call_args_list if c.args[-1]==group)
                self.assertEqual(header.args[2],0)
                self.assertEqual(header.args[6]+12,y-2)
