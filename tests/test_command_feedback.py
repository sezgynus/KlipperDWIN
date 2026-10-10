from concurrent.futures import Future
import unittest
from unittest.mock import Mock, patch

import command_feedback
from command_feedback import CommandFeedback
from test_capabilities import snapshot, display
from test_regressions import ui
from printer_state import PrinterState


class FeedbackTests(unittest.TestCase):
    def test_http_acceptance_is_distinct_from_expected_state(self):
        future = Future()
        confirmed = Mock(return_value=False)
        result = CommandFeedback(future, 'Pause', 1, confirmed)
        state = PrinterState.from_snapshot(snapshot())
        self.assertEqual(result.update(state), 'waiting')
        future.set_result({'result': 'ok'})
        self.assertEqual(result.update(state), 'waiting')
        confirmed.return_value = True
        self.assertEqual(result.update(state), 'accepted')

    def test_failure_cancel_disconnect_and_epoch_change_never_succeed(self):
        for case in ('failure', 'cancel', 'offline', 'epoch'):
            future = Future()
            result = CommandFeedback(future, 'Jog', 1)
            source = snapshot()
            if case == 'failure':
                future.set_exception(ValueError('rejected'))
            elif case == 'cancel':
                future.cancel()
            elif case == 'offline':
                source['state'] = 'disconnected'
            else:
                source['epoch'] = 2
            with self.subTest(case=case):
                self.assertEqual(result.update(PrinterState.from_snapshot(source)), 'error')

    def test_unconfirmed_command_times_out_without_retry(self):
        future = Future()
        result = CommandFeedback(future, 'Jog', 1)
        with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 31):
            self.assertEqual(result.update(PrinterState.from_snapshot(snapshot())), 'error')
        self.assertTrue(future.cancelled())

    def test_state_observed_command_has_bounded_confirmation_timeout(self):
        future = Future()
        future.set_result(None)
        confirmed = Mock(return_value=False)
        result = CommandFeedback(future, 'Home', 1, confirmed, confirmation_timeout=300)
        state = PrinterState.from_snapshot(snapshot())
        with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 299):
            self.assertEqual(result.update(state), 'waiting')
        with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 301):
            self.assertEqual(result.update(state), 'error')
        self.assertEqual(result.message, 'State unconfirmed; check printer')

    def test_state_observed_command_accepts_before_confirmation_timeout(self):
        future = Future()
        future.set_result(None)
        confirmed = Mock(return_value=True)
        result = CommandFeedback(future, 'Home', 1, confirmed, confirmation_timeout=300)
        state = PrinterState.from_snapshot(snapshot())
        with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 299):
            self.assertEqual(result.update(state), 'accepted')

    def test_expected_state_pending_future_expires_without_late_success(self):
        for running in (False, True):
            future = Future()
            if running:
                future.set_running_or_notify_cancel()
            confirmed = Mock(return_value=True)
            result = CommandFeedback(future, 'Home', 1, confirmed, confirmation_timeout=10)
            state = PrinterState.from_snapshot(snapshot())
            with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 11):
                self.assertEqual(result.update(state), 'error')
            confirmed.assert_not_called()
            if running:
                future.set_result(None)
            self.assertEqual(result.update(state), 'error')

    def test_confirmation_deadline_rejects_late_result_even_if_state_matches(self):
        future = Future()
        future.set_result(None)
        result = CommandFeedback(future, 'Home', 1, lambda: True, confirmation_timeout=10)
        with patch.object(command_feedback.time, 'monotonic', return_value=result.started + 11):
            self.assertEqual(result.update(PrinterState.from_snapshot(snapshot())), 'error')

    def test_confirmation_timeout_requires_finite_positive_value(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                CommandFeedback(Future(), 'Home', 1, confirmation_timeout=value)

    def display(self):
        result = display(snapshot())
        result.checkkey = result.TemperatureID
        result._show_message = Mock()
        result._restore_action_screen = Mock()
        result.HMI_AudioFeedback = Mock()
        return result

    def test_pending_action_blocks_duplicate_and_restores_only_after_success(self):
        result = self.display()
        future = Future()
        callback = Mock(return_value=future)
        result._action('Bed target', callback)
        result._action('Bed target', callback)
        callback.assert_called_once()
        self.assertTrue(result._poll_action())
        result._restore_action_screen.assert_not_called()
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Temperature = Mock()
        result._dispatch_input()
        result.HMI_Temperature.assert_not_called()
        future.set_result({'result': 'ok'})
        self.assertFalse(result._poll_action())
        result._restore_action_screen.assert_called_once()
        result.HMI_AudioFeedback.assert_called_once_with(True)

    def test_error_is_acknowledged_without_resubmitting(self):
        result = self.display()
        future = Future()
        future.set_exception(ValueError('rejected'))
        callback = Mock(return_value=future)
        result._action('Jog X', callback)
        self.assertTrue(result._poll_action())
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CW)
        result._dispatch_input()
        self.assertIsNotNone(result._action_feedback)
        result.get_encoder_state.return_value = result.ENCODER_DIFF_ENTER
        result._dispatch_input()
        self.assertIsNone(result._action_feedback)
        callback.assert_called_once()
        result.HMI_AudioFeedback.assert_not_called()

    def test_validation_error_becomes_feedback_without_success_sound(self):
        result = self.display()
        callback = Mock(side_effect=ValueError('too cold'))
        result._action('Extrude', callback)
        self.assertTrue(result._poll_action())
        self.assertEqual(result._action_feedback.phase, 'error')
        result.HMI_AudioFeedback.assert_not_called()

    def test_pause_resume_cancel_and_offset_return_futures(self):
        result = self.display().pd
        future = Future()
        result.postREST = Mock(return_value=future)
        result.sendGCode = Mock(return_value=future)
        for action in (result.pause_job, result.resume_job, result.cancel_job):
            self.assertIs(action(), future)
        self.assertIs(result.setZOffset(.1), future)

    def test_cooldown_combines_heaters_and_fan(self):
        result = self.display().pd
        result.cooldown()
        result.sendGCode.assert_called_once_with('TURN_OFF_HEATERS\nM106 S0')

    def test_gpio_error_ack_reaches_owner_but_waiting_and_rotation_do_not(self):
        result = self.display()
        result._closed = False
        result._loop = Mock()
        result._encoder_event = result.ENCODER_DIFF_NO
        future = Future()
        result._action('Jog', Mock(return_value=future))
        result._enqueue_input('press', 1)
        result._loop.post.assert_not_called()
        future.set_exception(ValueError('rejected'))
        result._poll_action()
        result._enqueue_input('rotate', 1)
        result._loop.post.assert_not_called()
        result._enqueue_input('press', 1)
        event = result._loop.post.call_args.args[0]
        result._process_input(event)
        self.assertIsNone(result._action_feedback)
        result._restore_action_screen.assert_called_once()

    def test_unchanged_offset_confirmation_uses_current_editor_value(self):
        result = self.display()
        result.pd.HMI_ValueStruct.offset_value = 125
        result.pd.HMI_ValueStruct.show_mode = -4
        result.dwin_zoffset = 0
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_Zoffset()
        result.pd.sendGCode.assert_called_once_with('SET_GCODE_OFFSET Z=1.25 MOVE=1')
        result.pd.sendGCode.reset_mock()
        for value in (float('nan'), float('inf'), 21):
            with self.assertRaises(ValueError):
                result.pd.setZOffset(value)
        result.pd.sendGCode.assert_not_called()

    def test_offset_editor_survives_status_ticks_and_reopens_from_authoritative_value(self):
        result = self.display()
        result.pd.BABY_Z_VAR = 1.25
        result._open_zoffset(-4, 4)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CW)
        result.HMI_Zoffset()
        self.assertEqual(result._zoffset_target, 126)
        result.pd.update_variable()
        self.assertEqual(result.pd.HMI_ValueStruct.offset_value, 0)
        self.assertEqual(result._zoffset_target, 126)
        result.get_encoder_state.return_value = result.ENCODER_DIFF_ENTER
        result.HMI_Zoffset()
        result.pd.sendGCode.assert_called_once_with('SET_GCODE_OFFSET Z=1.26 MOVE=1')
        result._open_zoffset(0, 4)
        self.assertEqual(result._zoffset_target, 0)
