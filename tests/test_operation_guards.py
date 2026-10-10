from concurrent.futures import Future
import unittest
from moonraker_client import MoonrakerError
from printerInterface import PrinterData
from test_capabilities import printer, snapshot
import test_jog_recovery as jog_fixtures
from test_moonraker_client import response
from test_bed_mesh import data as mesh_data
from test_screws_tilt import data as screws_data
from test_probe_wizard import data as probe_data


class DispatchTests(unittest.TestCase):
    def test_jog_rejects_same_epoch_changes_before_dispatch(self):
        for change in ('print', 'homing', 'position', 'limits', 'cold'):
            source = snapshot()
            p = printer(source)
            p.sendGCode = PrinterData.sendGCode.__get__(p)
            p.client.post.return_value = Future()
            p.moveRelative('E' if change == 'cold' else 'X', 1, 300)
            guard = p.client.post.call_args.kwargs['guard']
            self.assertTrue(guard())
            if change == 'print': source['status']['print_stats']['state'] = 'printing'
            elif change == 'homing': source['status']['toolhead']['homed_axes'] = 'yz'
            elif change == 'position': source['status']['gcode_move']['position'][0] = 200
            elif change == 'limits': source['status']['toolhead']['axis_maximum'][0] = .5
            else: source['status']['extruder']['can_extrude'] = False
            with self.subTest(change=change): self.assertFalse(guard())

    def test_calibration_dispatch_checks_live_print_and_other_session(self):
        for source, name in ((mesh_data(), 'bed_mesh'), (screws_data(), 'screws_tilt'), (probe_data(), 'probe_wizard')):
            p = printer(source)
            p.subscription.request.return_value = Future()
            p.subscription.responses_since.return_value = (0, ())
            getattr(p, name).start()
            call = p.sendGCode.call_args if name == 'probe_wizard' else p.subscription.request.call_args
            guard = call.kwargs['dispatch_guard' if name == 'probe_wizard' else 'guard']
            self.assertTrue(guard())
            source['status']['print_stats']['state'] = 'paused'
            self.assertFalse(guard())
            source['status']['print_stats']['state'] = 'standby'
            p.mmu_session.pending = Future()
            self.assertFalse(guard())

    def test_home_blocks_queued_print_start_but_thermal_control_remains_allowed(self):
        source = snapshot();p = printer(source)
        p.sendGCodeObserved('G28')
        guard = p.subscription.notify.call_args.kwargs['guard']
        source['status']['print_stats']['state'] = 'printing'
        self.assertFalse(guard())
        p.sendGCode = PrinterData.sendGCode.__get__(p)
        p.setExtTemp(200)
        self.assertTrue(p.client.post.call_args.kwargs['guard']())


class JogDispatchTransportTests(unittest.TestCase):
    setup_printer = jog_fixtures.JogRecoveryTests.setup_printer
    scripts = jog_fixtures.JogRecoveryTests.scripts

    def test_print_start_after_save_never_sends_motion(self):
        p, opener = self.setup_printer([])
        source = snapshot()
        def save(*args, **kwargs):
            source['status']['print_stats']['state'] = 'printing'
            p.subscription.snapshot.return_value = source
            return response({'result': 'ok'})
        opener.open.side_effect = save
        with self.assertRaises(MoonrakerError): p.moveRelative('X', 1, 300).result(2)
        self.assertEqual(len(self.scripts(opener)), 1)
        self.assertFalse(p.jog_recovery_required)

    def test_cleanup_still_restores_after_motion_changes_position(self):
        p, opener = self.setup_printer([])
        calls = 0
        def respond(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                source = snapshot();source['status']['gcode_move']['position'][0] = 1
                p.subscription.snapshot.return_value = source
                raise MoonrakerError('motion result lost')
            return response({'result': 'ok'})
        opener.open.side_effect = respond
        with self.assertRaises(MoonrakerError): p.moveRelative('X', 1, 300).result(2)
        self.assertEqual(len(self.scripts(opener)), 3)
        self.assertTrue(self.scripts(opener)[-1].endswith('MOVE=0'))
        self.assertFalse(p.jog_recovery_required)
