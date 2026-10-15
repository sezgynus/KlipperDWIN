"""CI-only regressions for live Maintenance safety evidence and owners."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from printer_state import PrinterState
from maintenance_discovery import MaintenanceSnapshot
from maintenance_safety import precheck
from maintenance_runtime import (
    QueueEvidence, read_queue_evidence, conflicting_petrel_operation,
    live_safety_context,
)


class Client:
    def __init__(self, queue=None, components=('job_queue',)):
        self.paths = []
        self.queue = queue if queue is not None else {
            'queue_state': 'ready', 'queued_jobs': []}
        self.components = components

    def get(self, path):
        self.paths.append(path)
        if path == '/server/info':
            return {'result': {'components': list(self.components)}}
        if path == '/server/job_queue/status':
            return {'result': self.queue}
        raise AssertionError('Unexpected Maintenance GET: ' + path)


def fake_printer():
    data = {'state': 'ready', 'epoch': 8, 'settings': {},
            'status': {'webhooks': {'state': 'ready'},
                       'print_stats': {'state': 'standby'},
                       'virtual_sdcard': {'is_active': False},
                       'pause_resume': {'is_paused': False}}}
    state = PrinterState.from_snapshot(data)
    owners = [SimpleNamespace(pending=None, phase='idle')
              for _ in range(4)]
    printer = SimpleNamespace(
        state=state, connection_error=None,
        subscription=SimpleNamespace(snapshot=Mock(return_value=data)),
        jog_recovery_required=False, _jog_restore=None, _settings_save=None,
        bed_mesh=owners[0], screws_tilt=owners[1],
        probe_wizard=owners[2], mmu_session=owners[3])
    return printer, data


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.printer, self.data = fake_printer()
        self.snapshot = MaintenanceSnapshot(
            8, config_marker=id(self.printer.state.settings))

    def test_queue_positive_presence_requires_structured_empty_status(self):
        client = Client()
        ev = read_queue_evidence(client, 8, self.snapshot.config_marker)
        self.assertTrue(ev.component_present)
        self.assertTrue(ev.is_empty)
        self.assertEqual(client.paths,
                         ['/server/info', '/server/job_queue/status'])
        ctx = live_safety_context(self.printer, ev, now=ev.observed_at)
        self.assertTrue(precheck(self.snapshot, ctx).allowed)
        self.assertEqual(ctx.job_queue['queued_jobs'], ())

    def test_verified_absence_is_not_guessed(self):
        client = Client(components=('history', 'update_manager'))
        ev = read_queue_evidence(client, 8, self.snapshot.config_marker)
        self.assertFalse(ev.component_present)
        self.assertEqual(client.paths, ['/server/info'])
        self.assertTrue(precheck(self.snapshot, live_safety_context(
            self.printer, ev, now=ev.observed_at)).allowed)
        for invalid in (
                {'components': 'job_queue'},
                {'components': [True]},
                {},
                {'components': list(range(129))}):
            class Bad:
                def get(self, path):
                    return {'result': invalid}
            self.assertIsNone(read_queue_evidence(Bad(), 8,
                                                  self.snapshot.config_marker))

    def test_queue_loading_starting_and_queued_jobs_are_blocked(self):
        for queue in (
                {'queue_state': 'loading', 'queued_jobs': []},
                {'queue_state': 'starting', 'queued_jobs': []},
                {'queue_state': 'ready', 'queued_jobs': [{'filename': 'private.gcode'}]},
                {'queue_state': 'ready', 'queued_jobs': None}):
            with self.subTest(queue=queue):
                evidence = read_queue_evidence(
                    Client(queue=queue), 8, self.snapshot.config_marker)
                context = live_safety_context(
                    self.printer, evidence,
                    now=evidence.observed_at if evidence else 0)
                self.assertFalse(precheck(self.snapshot, context).allowed)
                self.assertNotIn('private.gcode', str(context))

    def test_stale_epoch_config_and_time_are_not_trusted(self):
        ev = read_queue_evidence(Client(), 8, self.snapshot.config_marker)
        for bad in (
                QueueEvidence(9, ev.config_marker, ev.observed_at, True, 'ready', True),
                QueueEvidence(8, -1, ev.observed_at, True, 'ready', True)):
            self.assertFalse(precheck(self.snapshot, live_safety_context(
                self.printer, bad, now=ev.observed_at)).allowed)
        self.assertFalse(precheck(self.snapshot, live_safety_context(
            self.printer, ev, now=ev.observed_at + 4)).allowed)
        self.data['epoch'] = 9
        self.assertFalse(precheck(self.snapshot, live_safety_context(
            self.printer, ev, now=ev.observed_at)).allowed)

    def test_existing_petrel_owners_block_until_idle(self):
        ev = read_queue_evidence(Client(), 8, self.snapshot.config_marker)
        for name in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session'):
            with self.subTest(name=name):
                getattr(self.printer, name).pending = object()
                self.assertTrue(conflicting_petrel_operation(self.printer))
                self.assertFalse(precheck(self.snapshot, live_safety_context(
                    self.printer, ev, now=ev.observed_at)).allowed)
                getattr(self.printer, name).pending = None
        self.printer.probe_wizard.phase = 'active'
        self.assertTrue(conflicting_petrel_operation(self.printer))
        self.printer.probe_wizard.phase = 'idle'
        self.printer.jog_recovery_required = True
        self.assertTrue(conflicting_petrel_operation(self.printer))
        self.printer.jog_recovery_required = False
        self.printer._settings_save = object()
        self.assertTrue(conflicting_petrel_operation(self.printer))

    def test_disconnect_and_missing_subscription_status_are_blocked(self):
        ev = read_queue_evidence(Client(), 8, self.snapshot.config_marker)
        self.data['status'].pop('pause_resume')
        self.assertFalse(precheck(self.snapshot, live_safety_context(
            self.printer, ev, now=ev.observed_at)).allowed)
        self.data['status']['pause_resume'] = {'is_paused': False}
        self.printer.connection_error = 'not ready'
        self.assertFalse(precheck(self.snapshot, live_safety_context(
            self.printer, ev, now=ev.observed_at)).allowed)


if __name__ == '__main__':
    unittest.main()
