"""Regression tests for on-entry-only Maintenance discovery UI integration."""
from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from test_capabilities import display, snapshot


class InlineWorker:
    def __init__(self):
        self.calls = 0

    def submit(self, work, queue_timeout=0):
        self.calls += 1
        f = Future()
        try:
            f.set_result(work())
        except Exception as error:
            f.set_exception(error)
        return f

    def close(self):
        pass


class MaintenanceEntryTests(unittest.TestCase):
    def screen(self, data=None):
        d = display(data or snapshot())
        d.pd._read_worker = InlineWorker()
        d.pd.client.get = Mock(return_value={'result': {}})
        d.checkkey = d.MainMenu
        d.get_encoder_state = Mock(return_value=d.ENCODER_DIFF_ENTER)
        d.select_page.set(next(i for i, e in enumerate(d._home_entries())
                               if e[0] == 'MAINTENANCE'))
        return d

    def test_idle_entry_is_lazy_and_uses_existing_worker(self):
        d = self.screen()
        self.assertIsNone(getattr(d, '_maintenance_session', None))
        d.HMI_MainMenu()
        self.assertEqual(d.checkkey, d.MaintenanceMenu)
        session = d._maintenance_session
        self.assertIsNotNone(session.snapshot)
        self.assertEqual(d.pd._read_worker.calls, 1)
        session.poll(d.pd.state)
        self.assertEqual(d.pd._read_worker.calls, 1)
        d.HMI_Maintenance_Menu()
        self.assertEqual(d.checkkey, d.MainMenu)
        self.assertIsNone(d._maintenance_session)
        self.assertIsNone(session.snapshot)

    def test_printing_and_pausing_deny_entry(self):
        for state in ('printing', 'paused', 'pausing'):
            with self.subTest(state=state):
                data = snapshot()
                data['status']['print_stats']['state'] = state
                data['status']['virtual_sdcard']['is_active'] = True
                d = self.screen(data)
                d.HMI_MainMenu()
                self.assertNotEqual(d.checkkey, d.MaintenanceMenu)
                self.assertIsNone(getattr(d, '_maintenance_session', None))
                self.assertEqual(d.pd._read_worker.calls, 0)

    def test_print_transition_drops_snapshot(self):
        d = self.screen()
        d.HMI_MainMenu()
        session = d._maintenance_session
        d._focus_print_open = Mock()
        d.Goto_PrintProcess()
        self.assertIsNone(d._maintenance_session)
        self.assertIsNone(session.snapshot)

    def test_shutdown_clears_discovery(self):
        d = self.screen()
        d.HMI_MainMenu()
        session = d._maintenance_session
        d._closed = False
        d._panel_probe = None
        d.button = None
        d.encoder = None
        d._close_resources()
        self.assertIsNone(session.snapshot)
        self.assertIsNone(d._maintenance_session)


if __name__ == '__main__':
    unittest.main()
