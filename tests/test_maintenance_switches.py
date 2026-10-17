from types import SimpleNamespace
from unittest.mock import patch
import unittest
from test_maintenance_controller import printer, Worker
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, AUTOMATIC, _add
from maintenance_switches import MaintenanceSwitchController

class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.p, self.data = printer()
        self.data['settings'] = {'stepper_x': {'endstop_pin': '^PA1'}}
        self.p.state = PrinterState.from_snapshot(self.data)
        self.p.subscription.lifecycle = lambda: {'state': self.data['state'], 'epoch': self.data['epoch']}
        self.p.maintenance.snapshot = MaintenanceSnapshot(12, (
            DeviceCapabilities('stepper_x','stepper',_add(0,'M01',USER)),
            DeviceCapabilities('tmc2208 stepper_x','driver',_add(0,'M10',AUTOMATIC))), config_marker=id(self.p.state.settings))
        self.worker=Worker()
        self.paths=[]
        self.value='open'
        self.flags={}
        self.client=SimpleNamespace(get=self.get)
        self.c=MaintenanceSwitchController(self.p,self.worker,self.client)

    def get(self,path):
        self.paths.append(path)
        if path=='/server/info':
            return {'result':{'components':[]}}
        if path=='/printer/query_endstops/status':
            return {'result':{'stepper_x':self.value,'stepper_y':'open','stepper_z':'TRIGGERED'}}
        return {'result':{'status':{'tmc2208 stepper_x':{'drv_status':self.flags}}}}

    def click(self):
        self.assertTrue(self.c.confirm()[0])
        self.worker.drain()
        return self.c.poll()

    def test_operator_paced_open_pressed_open_and_unlimited_wait(self):
        self.assertTrue(self.c.start('M01','stepper_x')[0])
        self.assertEqual(self.paths,[])
        with patch('maintenance_switches.monotonic',return_value=100000):
            self.assertIsNone(self.c.poll())
        self.click()
        self.assertEqual(self.c.phase,'await_press')
        self.click()  # still open: operator may try again, never fake transition
        self.assertEqual(self.c.phase,'await_press')
        self.value='TRIGGERED'
        self.click()
        self.assertEqual(self.c.phase,'await_release')
        self.value='open'
        self.click()
        self.assertEqual(self.c.phase,'await_observation')
        result=self.c.observe(True)
        self.assertEqual(result.status,'PASSED_USER')
        self.assertTrue(result.restore_verified)

    def test_legacy_short_axis_alias_and_conflicts_are_explicit(self):
        for reply,expected in (
                ({'x':'open'},'await_press'),
                ({'stepper_x':'open','x':'open'},'await_press'),
                ({'stepper_x':'TRIGGERED','x':'open'},None),
                ({'stepper_x':None,'x':'open'},None),
                ({'stepper_y':'open'},None)):
            with self.subTest(reply=reply):
                self.c._phase = None
                original = self.get
                self.client.get = lambda path: {'result':reply} if path=='/printer/query_endstops/status' else original(path)
                self.c.start('M01','stepper_x')
                outcome = self.click()
                self.assertEqual(self.c.phase,expected)
                if expected is None:
                    self.assertEqual(outcome.status,'INCONCLUSIVE')

    def test_virtual_endstop_cannot_be_queried_as_physical(self):
        self.p.state=PrinterState.from_snapshot(dict(self.data,settings={'stepper_x':{'endstop_pin':'tmc2208_stepper_x:virtual_endstop'}}))
        self.p.maintenance.snapshot=MaintenanceSnapshot(12,self.p.maintenance.snapshot.devices,config_marker=id(self.p.state.settings))
        self.c.start('M01','stepper_x')
        self.c.confirm()
        self.worker.drain()
        self.assertEqual(self.c.poll().status,'INCONCLUSIVE')
        self.assertNotIn('/printer/query_endstops/status',self.paths)

    def test_reserved_m10_is_not_an_active_test_even_with_stale_discovery(self):
        from maintenance_switches import switch_adapters, switch_plan
        self.assertEqual([a.feature_id for a in switch_adapters()], ['M01'])
        self.assertEqual([r.feature_id for r in switch_plan(self.p.maintenance.snapshot)],
                         ['M01'])
        self.assertEqual(self.c.start('M10','tmc2208 stepper_x'),
                         (False,'motion_observer_unavailable'))
        self.assertEqual(self.paths, [])

    def test_cancel_and_disconnect_do_not_send_motion(self):
        self.c.start('M01','stepper_x')
        self.assertEqual(self.c.cancel().status,'ABORTED')
        self.c.start('M01','stepper_x')
        self.c.confirm()
        self.data['epoch']=13
        self.assertEqual(self.c.poll().status,'INCONCLUSIVE')
        self.worker.drain()
        self.assertEqual(self.paths,[])
