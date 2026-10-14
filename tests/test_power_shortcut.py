"""Real GPIO edges -> owner queue -> global power popup, without hardware."""
from concurrent.futures import Future
from threading import Lock
import unittest
from unittest.mock import Mock, patch
from test_capabilities import display, snapshot
from test_regressions import ui
from test_t5uic1_driver import driver
from ui_events import InputEvent


class PowerShortcutTests(unittest.TestCase):
    def view(self):
        v = display(snapshot())
        v.lcd = driver()
        v._closed = False
        v._input_lock = Lock()
        v._last_press = float('-inf')
        v._uart_online = True
        v._uart_epoch = 1
        v._boot_active = False
        v._encoder_event = v.ENCODER_DIFF_NO
        v._loop = Mock()
        v._sync_input_state = Mock(return_value=True)
        v._buzzer_feedback = Mock()
        v._sync_case_light_tracking = Mock()
        v._power_origin = None
        v._power_focus = False
        v.checkkey = v.Control
        v.power_on_hold_ms = 2000
        v.pd.power_off_if_on = Mock(return_value=Future())
        return v

    def drain(self, v):
        events = [c.args[0] for c in v._loop.post.call_args_list]
        v._loop.post.reset_mock()
        for event in events:
            v._process_input(event)

    def gesture(self, v, duration):
        with patch.object(ui.time, 'monotonic', return_value=10):
            v._button_pressed()
            self.drain(v)
        with patch.object(ui.time, 'monotonic', return_value=10 + duration):
            v._button_released()
            self.drain(v)

    def input(self, v, kind, value):
        v._process_input(InputEvent(kind, value, v.pd.state.epoch, v._uart_epoch))

    def test_hold_capsule_uses_bounded_native_bitmap_packets(self):
        v = self.view()
        with patch('t5uic1_driver.time.sleep'):
            v._draw_pill(v.lcd, 28, 160, 216, 98, v.lcd.Color_Bg_Window)
        frames = v.lcd.MYSERIAL1.frames
        self.assertLessEqual(len(frames), 8)
        self.assertLess(sum(map(len, frames)), 1600)
        self.assertEqual(sum(frame[1] == 0x08 for frame in frames), 6)

    def test_short_click_runs_once_on_release_with_no_extra_timeout(self):
        v = self.view()
        v._dispatch_input = Mock()
        self.gesture(v, .1)
        v._dispatch_input.assert_called_once()
        v.pd.power_off_if_on.assert_not_called()
        self.assertIsNone(v._power_hold_started)

    def test_hold_release_consumes_enter_on_every_representative_screen(self):
        for name in ('Control', 'MainMenu', 'FilePreview', 'MotionValue', 'Move_X',
                     'DisplayMenu', 'BuzzerMenu', 'MMUMenu', 'ProbeWizardID', 'PrintProcess'):
            with self.subTest(screen=name):
                v = self.view();v.checkkey = getattr(v,name)
                before = v.checkkey
                v._dispatch_input = Mock()
                self.gesture(v,1.2)
                self.assertEqual(v.checkkey,v.PowerConfirm)
                self.assertEqual(v._power_origin,before)
                self.assertFalse(v._power_confirm_yes)
                v._dispatch_input.assert_not_called()
                v.pd.power_off_if_on.assert_not_called()

    def test_threshold_only_marks_ready_until_button_is_released(self):
        v=self.view()
        with patch.object(ui.time,'monotonic',return_value=10):
            v._button_pressed();self.drain(v)
        with patch.object(ui.time,'monotonic',return_value=11.3):
            self.assertTrue(v._power_hold_tick())
            v._button_held()
        self.assertTrue(v._power_hold_ready)
        self.assertEqual(v.checkkey,v.Control)
        v.pd.power_off_if_on.assert_not_called()
        v.pd.power_on_if_off=Mock()
        v._button_held();v.pd.power_on_if_off.assert_not_called()

    def test_aborted_hold_and_rotations_do_not_edit_or_select(self):
        v=self.view();v._dispatch_input=Mock()
        with patch.object(ui.time,'monotonic',return_value=10):
            v._button_pressed();self.drain(v)
        self.input(v,'rotate',-4)
        with patch.object(ui.time,'monotonic',return_value=10.8):
            v._button_released();self.drain(v)
        v._dispatch_input.assert_not_called()
        self.assertEqual(v.checkkey,v.Control)

    def test_power_selection_draws_buttons_without_erasing_popup(self):
        v = self.view()
        self.gesture(v, 1.3)
        v.Clear_Popup_Area = Mock()
        v.Draw_Title = Mock()
        v.Draw_Popup_Bkgd_105 = Mock()
        v.lcd.serial.frames.clear()
        self.input(v, 'rotate', -1)
        self.assertTrue(v._power_confirm_yes)
        v.Clear_Popup_Area.assert_not_called()
        v.Draw_Title.assert_not_called()
        v.Draw_Popup_Bkgd_105.assert_not_called()
        frames = list(v.lcd.serial.frames)
        self.assertLess(len(frames), 12)
        self.assertEqual(sum(f[1] == 0x08 for f in frames), 4)
        v.lcd.serial.frames.clear()
        self.input(v, 'rotate', -1)
        self.assertFalse(v.lcd.serial.frames)
        self.input(v, 'rotate', 1)
        self.assertFalse(v._power_confirm_yes)
        self.assertLess(len(v.lcd.serial.frames), 12)

    def test_separate_rotation_and_click_confirm_once(self):
        v=self.view();self.gesture(v,1.3)
        self.input(v,'rotate',-1)  # Native encoder CW.
        self.assertTrue(v._power_confirm_yes)
        self.input(v,'press',1)
        self.input(v,'press',1)
        v.pd.power_off_if_on.assert_called_once_with()

    def test_cancel_restores_motion_editor_without_committing_draft(self):
        v=self.view();v.checkkey=v.MotionValue
        v._motion_field='max_velocity';v._motion_target=321
        v.select_motion.set(1)
        v.Draw_Motion_Menu=Mock()
        self.gesture(v,1.3);self.input(v,'press',1)
        self.assertEqual(v.checkkey,v.MotionValue)
        self.assertEqual(v._motion_target,321)
        v.Draw_Motion_Menu.assert_called_once()
        v.pd.sendGCode.assert_not_called()

    def test_printing_and_operation_guards_block_shutdown(self):
        for busy in ('printing','paused','operation','start'):
            with self.subTest(busy=busy):
                v=self.view();v.Draw_Control_Menu=Mock()
                if busy in ('printing','paused'):v.pd.status=busy
                if busy=='operation':v._action_feedback=Mock()
                if busy=='start':v._pending_start=Mock()
                self.gesture(v,1.3)
                self.assertTrue(v._power_blocked)
                self.input(v,'rotate',-1);self.input(v,'press',1)
                v.pd.power_off_if_on.assert_not_called()
                self.assertEqual(v.checkkey,v.Control)

    def test_epoch_change_during_hold_discards_release_and_clears_bar(self):
        v=self.view();v._dispatch_input=Mock()
        with patch.object(ui.time,'monotonic',return_value=10):
            v._button_pressed();self.drain(v)
        data=snapshot();data['epoch']=v.pd.state.epoch+1
        v.pd.subscription.snapshot.return_value=data
        with patch.object(ui.time,'monotonic',return_value=11.3):
            v._button_released();self.drain(v)
        self.assertIsNone(v._power_hold_started)
        self.assertEqual(v.checkkey,v.Control)
        v._dispatch_input.assert_not_called()

    def test_offline_power_on_hold_is_kept_and_release_cannot_click(self):
        v=self.view();v._uart_online=False
        with patch.object(ui.time,'monotonic',return_value=10):v._button_pressed()
        v._button_held();self.drain(v)
        v.pd.power_on_if_off=Mock()
        v._button_held();self.drain(v)
        v.pd.power_on_if_off.assert_called_once()
        with patch.object(ui.time,'monotonic',return_value=12):v._button_released()
        self.assertEqual(v._loop.post.call_count,0)
        v.pd.power_off_if_on.assert_not_called()

    def test_failed_shutdown_remains_cancelable(self):
        v=self.view();self.gesture(v,1.3);self.input(v,'rotate',-1);self.input(v,'press',1)
        future=v._power_off_future;future.set_exception(ValueError('relay unavailable'))
        v._power_popup_tick()
        self.assertFalse(v._power_shutdown_requested)
        self.assertFalse(v._power_confirm_yes)
        self.assertEqual(v._power_blocked,'Power off failed')

    def test_waking_dimmed_screen_consumes_short_press(self):
        v=self.view();v._display_dimmed=True;v._display_values=[80,0,10]
        v._dispatch_input=Mock();self.gesture(v,.1)
        v._dispatch_input.assert_not_called()
        self.assertFalse(v._display_dimmed)

    def test_hold_progress_only_appends_new_pixels(self):
        v = self.view()
        with patch.object(ui.time, 'monotonic', return_value=10):
            v._button_pressed(); self.drain(v)
        with patch.object(ui.time, 'monotonic', return_value=10.45):
            v._power_hold_tick()
        v.lcd = Mock(wraps=v.lcd)
        for now in (10.5, 10.6, 10.7):
            with patch.object(ui.time, 'monotonic', return_value=now):
                v._power_hold_tick()
        rectangles = [c.args for c in v.lcd.draw_rectangle.call_args_list]
        self.assertEqual(len(rectangles), 3)
        self.assertTrue(all(c[1] == 0x063B for c in rectangles))
        self.assertEqual([c[2] for c in rectangles], [44, 56, 81])
        v._loop.set_interval.assert_called_with(.02)

    def test_normal_click_never_paints_hold_popup(self):
        v = self.view(); v._dispatch_input = Mock()
        v.lcd = Mock(wraps=v.lcd)
        with patch.object(ui.time, 'monotonic', return_value=10):
            v._button_pressed(); self.drain(v)
        with patch.object(ui.time, 'monotonic', return_value=10.3):
            v._power_hold_tick()
        v.lcd.draw_rectangle.assert_not_called()
        v.lcd.draw_text.assert_not_called()
        with patch.object(ui.time, 'monotonic', return_value=10.3):
            v._button_released(); self.drain(v)
        v._dispatch_input.assert_called_once()

    def test_aborted_visible_popup_restores_original_screen(self):
        v = self.view(); v.Draw_Control_Menu = Mock()
        with patch.object(ui.time, 'monotonic', return_value=10):
            v._button_pressed(); self.drain(v)
        with patch.object(ui.time, 'monotonic', return_value=10.6):
            v._power_hold_tick()
            v._button_released(); self.drain(v)
        v.Draw_Control_Menu.assert_called_once()
        self.assertEqual(v.checkkey, v.Control)
