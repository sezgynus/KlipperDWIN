"""Maintenance navigation must reuse the Klipper READY capability snapshot."""
import unittest
from unittest.mock import Mock
from test_capabilities import display, snapshot, printer


class MaintenanceEntryTests(unittest.TestCase):
    def screen(self, data=None):
        d = display(data or snapshot())
        d.checkkey = d.MainMenu
        d.get_encoder_state = Mock(return_value=d.ENCODER_DIFF_ENTER)
        d.select_page.set(next(i for i, e in enumerate(d._home_entries())
                               if e[0] == 'MAINTENANCE'))
        return d

    def test_three_menu_entries_do_not_requery_or_clear_snapshot(self):
        d = self.screen()
        prior = d.pd.maintenance.snapshot
        self.assertIsNotNone(prior)
        d.pd.client.get.reset_mock()
        for _ in range(3):
            d.HMI_MainMenu()
            self.assertEqual(d.checkkey, d.MaintenanceMenu)
            d.HMI_Maintenance_Menu()
            self.assertEqual(d.checkkey, d.MainMenu)
            self.assertIs(d.pd.maintenance.snapshot, prior)
        d.pd.client.get.assert_not_called()

    def test_printing_and_pausing_deny_menu_but_preserve_snapshot(self):
        for state in ('printing', 'paused', 'pausing'):
            with self.subTest(state=state):
                data = snapshot()
                data['status']['print_stats']['state'] = state
                data['status']['virtual_sdcard']['is_active'] = True
                d = self.screen(data)
                prior = d.pd.maintenance.snapshot
                d.HMI_MainMenu()
                self.assertNotEqual(d.checkkey, d.MaintenanceMenu)
                self.assertIs(d.pd.maintenance.snapshot, prior)

    def test_print_screen_does_not_clear_ready_snapshot(self):
        d = self.screen()
        d.HMI_MainMenu()
        prior = d.pd.maintenance.snapshot
        d._focus_print_open = Mock()
        d.Goto_PrintProcess()
        self.assertIs(d.pd.maintenance.snapshot, prior)

    def test_backend_telemetry_updates_reuse_ready_snapshot(self):
        data = snapshot()
        p = printer(data)
        first = p.maintenance.snapshot
        self.assertIsNotNone(first)
        for count in range(2, 5):
            data['revision'] = count
            data['status']['extruder']['temperature'] = 185 + count
            p.update_variable()
            self.assertIs(p.maintenance.snapshot, first)

    def test_backend_restarts_discovery_only_for_new_epoch(self):
        data = snapshot()
        p = printer(data)
        first = p.maintenance.snapshot
        data['epoch'] += 1
        data['revision'] += 1
        p.update_variable()
        self.assertIsNot(first, p.maintenance.snapshot)
        self.assertEqual(p.maintenance.snapshot.epoch, data['epoch'])

    def test_shutdown_releases_snapshot(self):
        d = self.screen()
        self.assertIsNotNone(d.pd.maintenance.snapshot)
        d.pd.maintenance.clear()
        self.assertIsNone(d.pd.maintenance.snapshot)


if __name__ == '__main__':
    unittest.main()
