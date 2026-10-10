import unittest
from concurrent.futures import Future
from unittest.mock import ANY, Mock, patch

from test_capabilities import snapshot, printer, display
from moonraker_client import MoonrakerError
import screws_tilt


def data():
    source = snapshot(probe=True)
    source['objects'].append('screws_tilt_adjust')
    source['settings']['screws_tilt_adjust'] = {
        'screw1': [30, 30], 'screw2': [200, 200],
        'screw3': [200, 30], 'screw4': [30, 200]}
    source['status']['screws_tilt_adjust'] = {'results': {}}
    return source


def payload():
    return {'status': {'screws_tilt_adjust': {'results': {
        'screw1': dict(z=0, sign='CW', adjust='00:00', is_base=True),
        'screw2': dict(z=.02, sign='CCW', adjust='00:02', is_base=False),
        'screw3': dict(z=.12, sign='CCW', adjust='00:14', is_base=False),
        'screw4': dict(z=-.08, sign='CW', adjust='00:10', is_base=False)}}}}


class SessionTests(unittest.TestCase):
    def make(self, source=None):
        p = printer(source or data())
        p.subscription.request.side_effect = lambda *args, **kwargs: Future()
        return p, p.screws_tilt

    def finish(self, session, result=None):
        session.pending.set_result('ok')
        session.update()
        self.assertEqual(session.phase, 'reading')
        session.pending.set_result(result or payload())
        session.update()

    def test_command_completion_then_fresh_query_and_repeat_identical(self):
        p, session = self.make()
        for _ in range(2):
            session.start()
            p.subscription.request.assert_called_with('printer.gcode.script', {'script': 'SCREWS_TILT_CALCULATE'}, guard=ANY)
            session.update()
            self.assertEqual(session.phase, 'measuring')
            self.finish(session)
            self.assertEqual(session.phase, 'complete')
            self.assertEqual(session.recommendation, 'screw3')
            self.assertFalse(session.leveled)
        self.assertEqual(p.subscription.request.call_count, 4)
        self.assertEqual([c[0] for c in session.corners], ['screw1', 'screw3', 'screw2', 'screw4'])
        p.sendGCode.assert_not_called()

    def test_homing_only_if_missing_and_duplicate_start_rejected(self):
        source = data()
        source['status']['toolhead']['homed_axes'] = 'xy'
        p, session = self.make(source)
        session.start()
        p.subscription.request.assert_called_with('printer.gcode.script', {'script': 'G28\nSCREWS_TILT_CALCULATE'}, guard=ANY)
        with self.assertRaises(ValueError):
            session.start()
        self.assertEqual(p.subscription.request.call_count, 1)

    def test_unavailable_print_manual_probe_recovery_and_layout_block_commands(self):
        for case in ('absent', 'printing', 'paused', 'manual', 'recovery', 'three', 'five', 'duplicate'):
            source = data()
            if case == 'absent': source = snapshot()
            if case in ('printing', 'paused'): source['status']['print_stats']['state'] = case
            if case == 'manual': source['status']['manual_probe'] = {'is_active': True}
            if case == 'three': del source['settings']['screws_tilt_adjust']['screw4']
            if case == 'five': source['settings']['screws_tilt_adjust']['screw5'] = [120, 120]
            if case == 'duplicate': source['settings']['screws_tilt_adjust']['screw4'] = [200, 200]
            p, session = self.make(source)
            if case == 'recovery': p._jog_restore = {"script": "restore"}
            with self.subTest(case=case), self.assertRaises(ValueError): session.start()
            p.subscription.request.assert_not_called()

    def test_disconnect_epoch_timeout_and_command_error_never_use_old_results(self):
        for case in ('disconnect', 'epoch', 'timeout', 'failure'):
            p, session = self.make()
            session.start()
            future = session.pending
            if case == 'disconnect': p.connection_error = 'offline'
            if case == 'epoch': p.state = type(p.state).from_snapshot(dict(data(), epoch=2))
            if case == 'failure': future.set_exception(MoonrakerError('probe failed'))
            with patch.object(screws_tilt.time, 'monotonic', return_value=session.started + (601 if case == 'timeout' else 1)):
                session.update()
            self.assertIn(session.phase, ('error', 'interrupted'))
            self.assertFalse(session.results)
            self.assertIsNone(session.pending)
            self.assertEqual(p.subscription.request.call_count, 1)

    def test_tolerance_and_rounding_of_sixty_minutes(self):
        _, session = self.make()
        session.start()
        result = payload()
        result['status']['screws_tilt_adjust']['results']['screw3']['adjust'] = '00:60'
        self.finish(session, result)
        self.assertEqual(session.results['screw3']['adjust'], '01:00')
        self.assertEqual(session.recommendation, 'screw3')
        session.start()
        result = payload()
        for value in result['status']['screws_tilt_adjust']['results'].values(): value['z'] = .01
        self.finish(session, result)
        self.assertTrue(session.leveled)

    def test_malformed_incomplete_or_multiple_base_results_rejected(self):
        for case in ('incomplete', 'nan', 'direction', 'base', 'format', 'minutes'):
            _, session = self.make()
            session.start()
            result = payload()
            values = result['status']['screws_tilt_adjust']['results']
            if case == 'incomplete': del values['screw4']
            if case == 'nan': values['screw2']['z'] = float('nan')
            if case == 'direction': values['screw2']['sign'] = 'BAD'
            if case == 'base': values['screw2']['is_base'] = True
            if case == 'format': values['screw2']['adjust'] = '-1:20'
            if case == 'minutes': values['screw2']['adjust'] = '00:61'
            self.finish(session, result)
            self.assertEqual(session.phase, 'error')
            self.assertFalse(session.results)


class ViewTests(unittest.TestCase):
    def make(self):
        view = display(data())
        view.lcd.DWIN_WIDTH = 272
        view.lcd.DWIN_HEIGHT = 480
        view.checkkey = view.Prepare
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.pd.subscription.request.side_effect = lambda *args, **kwargs: Future()
        return view

    def test_optional_prepare_menu_and_navigation(self):
        self.assertEqual(display(snapshot()).PREPARE_CASE_SCREWS, -1)
        view = self.make()
        view.select_prepare.set(view.PREPARE_CASE_SCREWS)
        view.HMI_Prepare()
        self.assertEqual(view.checkkey, view.ScrewsTiltMenu)
        view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
        view.HMI_Screws_Tilt()
        view.get_encoder_state.return_value = view.ENCODER_DIFF_ENTER
        view.HMI_Screws_Tilt()
        self.assertEqual(view.checkkey, view.ScrewsTiltResult)
        view.HMI_Screws_Tilt()
        self.assertEqual(view.checkkey, view.ScrewsTiltResult)
        self.assertEqual(view.pd.subscription.request.call_count, 1)
        session = view.pd.screws_tilt
        session.pending.set_result(None)
        session.update()
        session.pending.set_result(payload())
        view._poll_screws_tilt()
        labels = [c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('CCW 00:14', labels)
        self.assertIn('Adjust Front Right', labels)
        self.assertIn('Base', labels)
        self.assertIn('Continue', labels)
        view.HMI_Screws_Tilt()
        self.assertEqual(view.checkkey, view.ScrewsTiltMenu)
        view._screws_selection = 0
        view.HMI_Screws_Tilt()
        self.assertEqual(view.checkkey, view.Prepare)

    def test_only_success_instructions_are_green(self):
        view = self.make()
        session = view.pd.screws_tilt
        session.start()
        session.pending.set_result(None)
        session.update()
        session.pending.set_result(payload())
        session.update()
        for leveled in (False, True):
            session.leveled = leveled
            view.lcd.reset_mock()
            view.Draw_Screws_Result()
            instructions = [c.args for c in view.lcd.draw_text.call_args_list
                            if c.args[6] in (140, 160, 166)]
            self.assertEqual(len(instructions), 2)
            for args in instructions:
                self.assertEqual(args[3], 0x07E0 if leveled else view.lcd.Color_White)

    def test_tramming_menu_uses_marlin_small_stock_icons(self):
        view = self.make()
        row = next(row for row in view._menus['prepare'] if row[0] == 'SCREWS')
        self.assertEqual(row[2], view.ICON_SetEndTemp)
        self.assertEqual(row[2], 46)
        view.Draw_Menu_Line = Mock()
        view.Draw_Screws_Menu()
        view.Draw_Menu_Line.assert_any_call(1, view.ICON_SetEndTemp, 'Calculate')

    def test_long_turn_labels_remain_inside_display(self):
        view = self.make()
        session = view.pd.screws_tilt
        session.start()
        session.pending.set_result(None)
        session.update()
        session.pending.set_result(payload())
        session.update()
        session.results['screw2']['adjust'] = '120:59'
        view.lcd.reset_mock()
        view.Draw_Screws_Result()
        corners = []
        for c in view.lcd.draw_text.call_args_list:
            width = 10 if c.args[2] == view.lcd.font10x20 else 8
            self.assertGreaterEqual(c.args[5], 0)
            self.assertLessEqual(c.args[5] + len(c.args[-1]) * width, 272)
            if c.args[6] in (62, 82, 235, 255):
                corners.append(c.args)
                self.assertEqual(c.args[2], view.lcd.font8x16)
                self.assertGreaterEqual(c.args[5], 52)
                self.assertLessEqual(c.args[5] + len(c.args[-1]) * 8, 220)
        self.assertEqual(len(corners), 7)
        self.assertIn('120:59', [args[-1] for args in corners])
        self.assertIn('CCW', [args[-1] for args in corners])
