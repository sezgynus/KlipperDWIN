"""Moonraker API evidence and Klipper READY discovery lifecycle."""
import sys
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_services import parse_evidence, probe, _ENDPOINTS
from maintenance_session import MaintenanceDiscoveryManager, idle
from maintenance_discovery import INFORMATION


class State:
    ready = True
    epoch = 3
    objects = ('fan',)
    settings = {'fan': {'max_power': 1.}}
    status = {'print_stats': {'state': 'standby'},
              'virtual_sdcard': {'is_active': False}}


class Worker:
    def __init__(self):
        self.calls = 0
        self.jobs = []

    def submit(self, work):
        self.calls += 1
        self.jobs.append(work)
        return Future()

    def drain(self):
        while self.jobs:
            self.jobs.pop(0)()


class Tests(unittest.TestCase):
    def test_structured_service_evidence_only(self):
        result = parse_evidence({
            '/server/info': {'result': {'components': ['history', 'update_manager']}},
            '/machine/proc_stats': {'result': {
                'system_cpu_usage': {'cpu': .2}, 'cpu_temp': 53,
                'throttled_state': {'bits': 0}, 'network': {'eth0': {'rx_bytes': 10}}}},
            '/server/history/totals': {'result': {'job_totals': {'total_jobs': 4}}}})
        for key in ('history', 'machine.proc_stats', 'machine.cpu_temp',
                    'machine.throttled_state', 'machine.network', 'update_manager'):
            self.assertIn(key, result)
        self.assertNotIn('gcode_store', result)
        self.assertNotIn('machine.disk', result)
        self.assertNotIn('maintenance.records', result)
        self.assertNotIn('maintenance.travel_counter', result)
        self.assertEqual(parse_evidence({'/server/history/totals': {'error': 'bad'}}), ())

    def test_optional_endpoint_failures_and_no_gcode(self):
        calls = []
        class Client:
            def get(self, path):
                calls.append(path)
                if path == '/server/history/totals':
                    return {'result': {'job_totals': {'total_jobs': 2}}}
                raise RuntimeError('not enabled')
        self.assertEqual(probe(Client()), ('history',))
        self.assertEqual(tuple(calls), _ENDPOINTS)
        self.assertTrue(all('gcode' not in path for path in calls))

    def test_ready_runs_once_and_keeps_result_on_menu_reentry(self):
        s = State()
        manager = MaintenanceDiscoveryManager()
        worker = Worker()
        class Client:
            def get(self, path):
                return {'result': {'job_totals': {}}} if path == '/server/history/totals' else {'result': {}}
        client = Client()
        first = manager.ready(s, client, worker, lambda: s)
        self.assertEqual(first.method('F01', 'fan'), 2)
        self.assertIs(manager.ready(s, client, worker, lambda: s), first)
        self.assertEqual(worker.calls, 1)
        worker.drain()
        self.assertEqual(manager.snapshot.method('S10'), INFORMATION)
        with_services = manager.snapshot
        self.assertIs(manager.ready(s, client, worker, lambda: s), with_services)
        self.assertEqual(worker.calls, 1)

    def test_discovery_can_run_at_ready_even_during_print_but_entry_cannot(self):
        s = SimpleNamespace(ready=True, epoch=3, objects=('fan',),
                            settings={'fan': {'max_power': 1.}},
                            status={'print_stats': {'state': 'printing'},
                                    'virtual_sdcard': {'is_active': True}})
        manager = MaintenanceDiscoveryManager()
        self.assertIsNotNone(manager.ready(s))
        self.assertFalse(idle(s))
        self.assertIsNotNone(manager.snapshot)

    def test_old_service_result_cannot_overwrite_new_epoch(self):
        s = State()
        current = [s]
        manager = MaintenanceDiscoveryManager()
        worker = Worker()
        class Client:
            def get(self, path):
                return {'result': {'job_totals': {}}} if path == '/server/history/totals' else {'result': {}}
        client = Client()
        manager.ready(s, client, worker, lambda: current[0])
        replacement = SimpleNamespace(ready=True, epoch=4, objects=s.objects,
                                      settings=s.settings, status=s.status)
        current[0] = replacement
        manager.ready(replacement, client, worker, lambda: current[0])
        worker.jobs.pop(0)()
        self.assertEqual(manager.snapshot.epoch, 4)
        self.assertEqual(manager.snapshot.method('S10'), 0)
        worker.drain()
        self.assertEqual(manager.snapshot.method('S10'), INFORMATION)

    def test_disconnect_releases_snapshot_and_next_ready_recalculates(self):
        s = State()
        manager = MaintenanceDiscoveryManager()
        original = manager.ready(s)
        manager.clear()
        self.assertIsNone(manager.snapshot)
        self.assertIsNot(original, manager.ready(s))


if __name__ == '__main__':
    unittest.main()
