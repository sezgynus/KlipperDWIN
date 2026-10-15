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

    def test_storage_capability_from_registered_roots_without_directory_listing(self):
        from maintenance_discovery import discover, INFORMATION
        roots = '/server/files/roots'
        positive = parse_evidence({roots: {'result': [
            {'name': 'config', 'permissions': 'rw'},
            {'name': 'gcodes', 'permissions': 'rw'}]}})
        self.assertIn('machine.disk', positive)
        snap = discover(State(), positive)
        self.assertEqual(snap.method('S04'), INFORMATION)
        for bad in (
                {'result': [{'name': 'gcodes', 'permissions': ''}]},
                {'result': [{'name': 'logs', 'permissions': 'r'}]},
                {'error': 'access denied'},
                {'result': None}):
            self.assertNotIn('machine.disk', parse_evidence({roots: bad}))

    def test_tmc_thermal_monitor_is_structured_api_evidence(self):
        from maintenance_discovery import discover, NONE, AUTOMATIC
        evidence = parse_evidence({
            '/printer/objects/query?heaters=available_monitors': {
                'result': {'status': {'heaters': {
                    'available_monitors': ['tmc2240 stepper_x', 'temperature_sensor cabinet',
                                           'tmc2209 stepper_z', None]}}}}
        })
        self.assertIn('maintenance.driver_thermal_monitor:tmc2240 stepper_x', evidence)
        self.assertIn('maintenance.driver_thermal_monitor:tmc2209 stepper_z', evidence)
        self.assertNotIn('maintenance.driver_thermal_monitor:temperature_sensor cabinet', evidence)
        state = SimpleNamespace(ready=True, epoch=1,
                                objects=('tmc2240 stepper_x', 'tmc2209 stepper_z',
                                         'tmc2209 stepper_y'), settings={}, status={})
        caps = discover(state, evidence)
        self.assertEqual(caps.method('M08', 'tmc2240 stepper_x'),
                         AUTOMATIC | INFORMATION)
        self.assertEqual(caps.method('M08', 'tmc2209 stepper_z'),
                         AUTOMATIC | INFORMATION)
        self.assertEqual(caps.method('M08', 'tmc2209 stepper_y'), NONE)

    def test_service_responses_are_released_before_next_request(self):
        import weakref

        seen = []
        class Response(dict):
            pass

        class Client:
            def get(self, path):
                self.assert_freed()
                response = Response({'result': {'components': ['update_manager']}})
                seen.append(weakref.ref(response))
                return response

            def assert_freed(self):
                self.assert_all = all(ref() is None for ref in seen)
                if not self.assert_all:
                    raise AssertionError('Prior API response retained')

        self.assertIn('update_manager', probe(Client()))
        self.assertTrue(all(ref() is None for ref in seen))

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
        self.assertTrue(all(path.startswith(('/server/', '/machine/', '/printer/objects/query'))
                            for path in calls))
        self.assertNotIn('/server/files/directory?path=gcodes', calls)

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

    def test_lifecycle_logs_only_at_ready_evidence_and_invalidation(self):
        s = State()
        manager = MaintenanceDiscoveryManager()
        worker = Worker()
        class Client:
            def get(self, path):
                if path == '/server/history/totals':
                    return {'result': {'job_totals': {}}}
                return {'result': {}}

        with self.assertLogs('maintenance_session', level='INFO') as captured:
            first = manager.ready(s, Client(), worker, lambda: s)
            self.assertIs(manager.ready(s, Client(), worker, lambda: s), first)
            worker.drain()
            enriched = manager.snapshot
            self.assertIs(manager.ready(s, Client(), worker, lambda: s), enriched)
            manager.clear()

        lines = [record.getMessage() for record in captured.records]
        self.assertEqual(
            [line.split(': ')[1].split()[0] for line in lines],
            ['READY', 'EVIDENCE', 'CLEAR'])
        self.assertIn('epoch=3', lines[0])
        self.assertIn('services=1', lines[1])
        self.assertEqual(worker.calls, 1)

    def test_no_evidence_still_completes_ready_lifecycle_once(self):
        manager = MaintenanceDiscoveryManager()
        worker = Worker()
        s = State()
        class Client:
            def get(self, path):
                return {'result': {}}

        with self.assertLogs('maintenance_session', level='INFO') as captured:
            manager.ready(s, Client(), worker, lambda: s)
            worker.drain()
        lines = [r.getMessage() for r in captured.records]
        self.assertEqual(len(lines), 2)
        self.assertIn('READY epoch=3', lines[0])
        self.assertIn('EVIDENCE epoch=3 services=0', lines[1])

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
