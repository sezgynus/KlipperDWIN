"""CI-only Maintenance safety admission / stale session regression tests."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import MaintenanceSnapshot
from maintenance_safety import (
    MaintenanceSafetyCoordinator, SafetyContext, precheck,
)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.settings = {}
        self.state = SimpleNamespace(
            ready=True, epoch=10, settings=self.settings,
            status={'webhooks': {'state': 'ready'},
                    'print_stats': {'state': 'standby'},
                    'virtual_sdcard': {'is_active': False},
                    'pause_resume': {'is_paused': False}})
        self.snapshot = MaintenanceSnapshot(10, config_marker=id(self.settings))
        self.coordinator = MaintenanceSafetyCoordinator()

    def ctx(self, **kwargs):
        data = {'state': self.state, 'queue_checked': True,
                'job_queue': None, 'operations_checked': True,
                'conflicting_operation': False}
        data.update(kwargs)
        return SafetyContext(**data)

    def test_precheck_does_not_trust_ui_idle_alone(self):
        self.assertEqual(precheck(self.snapshot, self.ctx()).reason, 'allowed')
        self.assertFalse(precheck(self.snapshot, self.ctx(queue_checked=False)).allowed)
        self.assertFalse(precheck(self.snapshot, self.ctx(operations_checked=False)).allowed)
        self.assertFalse(precheck(self.snapshot, self.ctx(conflicting_operation=True)).allowed)
        self.assertFalse(precheck(self.snapshot, SafetyContext(self.state)).allowed)
        self.assertFalse(precheck(None, self.ctx()).allowed)
        self.assertFalse(precheck(self.snapshot, None).allowed)

    def test_print_pause_sdcard_webhooks_missing_fields_fail_closed(self):
        checks = (
            ('webhooks', {}, 'webhooks_not_ready'),
            ('print_stats', {}, 'print_not_idle'),
            ('virtual_sdcard', {}, 'sdcard_unknown_or_active'),
            ('pause_resume', {}, 'pause_unknown_or_active'),
        )
        for name, value, reason in checks:
            with self.subTest(field=name):
                original = self.state.status[name]
                self.state.status[name] = value
                self.assertEqual(precheck(self.snapshot, self.ctx()).reason, reason)
                self.state.status[name] = original
        for state in ('printing', 'paused', 'pausing'):
            with self.subTest(print_state=state):
                self.state.status['print_stats']['state'] = state
                self.assertFalse(precheck(self.snapshot, self.ctx()).allowed)
        self.state.status['print_stats']['state'] = 'standby'
        self.state.status['virtual_sdcard']['is_active'] = True
        self.assertFalse(precheck(self.snapshot, self.ctx()).allowed)

    def test_epoch_config_disconnect_and_busy_sessions(self):
        decision, session = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertTrue(decision.allowed)
        self.assertEqual(session.epoch, 10)
        decision2, second = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertFalse(decision2.allowed)
        self.assertIsNone(second)
        self.assertTrue(self.coordinator.guard(session, self.snapshot, self.ctx()).allowed)
        self.state.epoch = 11
        self.assertEqual(self.coordinator.guard(session, self.snapshot, self.ctx()).reason,
                         'epoch_or_config_changed')
        self.assertIsNone(self.coordinator.active)
        self.assertFalse(self.coordinator.end(session))
        self.state.epoch = 10
        self.state.settings = {}
        self.assertFalse(precheck(self.snapshot, self.ctx()).allowed)

    def test_queue_check_deny_autostart_and_missing_provenance(self):
        for queue in (
                {'queue_state': 'loading', 'queued_jobs': []},
                {'queue_state': 'starting', 'queued_jobs': []},
                {'queue_state': 'ready', 'queued_jobs': [{'job': 1}]},
                {'queue_state': 'ready'},
                {'queue_state': 'unknown', 'queued_jobs': []},
                'ready'):
            with self.subTest(queue=queue):
                self.assertFalse(precheck(
                    self.snapshot, self.ctx(job_queue=queue)).allowed)
        self.assertTrue(precheck(self.snapshot, self.ctx(
            job_queue={'queue_state': 'paused', 'queued_jobs': []})).allowed)

    def test_external_print_start_cancels_session_before_next_command(self):
        _, session = self.coordinator.begin(self.snapshot, self.ctx())
        self.state.status['print_stats']['state'] = 'printing'
        self.assertEqual(self.coordinator.guard(session, self.snapshot, self.ctx()).reason,
                         'print_not_idle')
        self.assertIsNone(self.coordinator.active)
        self.assertFalse(self.coordinator.guard(session, self.snapshot, self.ctx()).allowed)

    def test_mmu_and_probe_activity_deny_admission(self):
        self.state.status['manual_probe'] = {'is_active': True}
        self.assertEqual(precheck(self.snapshot, self.ctx()).reason, 'manual_probe_active')
        self.state.status['manual_probe'] = {'is_active': False}
        self.state.status['mmu'] = {'action': 'Selecting'}
        self.assertEqual(precheck(self.snapshot, self.ctx()).reason, 'mmu_busy')
        self.state.status['mmu'] = {'action': 'idle'}
        self.assertTrue(precheck(self.snapshot, self.ctx()).allowed)

    def test_cancel_stale_callback_cannot_finish_next_session(self):
        _, first = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertTrue(self.coordinator.end(first))
        self.assertFalse(self.coordinator.end(first))
        _, second = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertNotEqual(first.token, second.token)
        self.assertEqual(self.coordinator.guard(first, self.snapshot, self.ctx()).reason,
                         'stale_session')
        self.assertEqual(self.coordinator.active, second)
        self.coordinator.clear()
        self.assertIsNone(self.coordinator.active)
        self.assertFalse(self.coordinator.end(second))
        _, third = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertGreater(third.token, second.token)

    def test_guard_rechecks_conflicts_each_dispatch_and_never_restores(self):
        _, session = self.coordinator.begin(self.snapshot, self.ctx())
        self.assertTrue(self.coordinator.guard(session, self.snapshot, self.ctx()).allowed)
        self.assertEqual(self.coordinator.guard(
            session, self.snapshot,
            self.ctx(conflicting_operation=True)).reason, 'conflicting_operation')
        self.assertIsNone(self.coordinator.active)
        self.assertFalse(self.coordinator.guard(session, self.snapshot, self.ctx()).allowed)


if __name__ == '__main__':
    unittest.main()
