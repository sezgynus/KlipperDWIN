"""Moonraker evidence and entry-only session contracts."""
import sys
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_services import parse_evidence, probe, _ENDPOINTS
from maintenance_session import MaintenanceDiscoverySession
from maintenance_discovery import INFORMATION


class State:
    ready = True
    epoch = 3
    objects = ('fan',)
    settings = {'fan': {'max_power': 1.}}
    status = {'print_stats': {'state': 'standby'},
              'virtual_sdcard': {'is_active': False}}


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

    def test_session_remains_lazy_and_reuses_snapshot(self):
        s = State()
        sess = MaintenanceDiscoverySession()
        self.assertIsNone(sess.snapshot)
        first = sess.enter(s)
        self.assertIs(first, sess.enter(s))
        self.assertEqual(first.method('F01', 'fan'), 2)
        sess.cancel()
        self.assertIsNone(sess.snapshot)

    def test_session_service_result_no_retained_client(self):
        s = State()
        calls = []
        class Client:
            def get(self, path):
                calls.append(path)
                return {'result': {'job_totals': {}}} if path == '/server/history/totals' else {'result': {}}
        class Worker:
            def submit(self, run, queue_timeout=0):
                self.job = Future()
                self.job.set_result(run())
                return self.job
        sess = MaintenanceDiscoverySession()
        sess.enter(s, Client(), Worker())
        self.assertTrue(sess.poll(s))
        self.assertEqual(sess.snapshot.method('S10'), INFORMATION)
        self.assertFalse(sess.poll(s))
        self.assertEqual(calls, list(_ENDPOINTS))

    def test_active_print_and_unknown_state_deny_entry(self):
        idle = State()
        active = SimpleNamespace(ready=True, epoch=3, objects=idle.objects,
                                 settings=idle.settings,
                                 status={'print_stats': {'state': 'printing'},
                                         'virtual_sdcard': {'is_active': True}})
        session = MaintenanceDiscoverySession()
        self.assertIsNone(session.enter(active))
        self.assertIsNone(session.snapshot)
        unknown = SimpleNamespace(ready=True, epoch=3, objects=idle.objects,
                                  settings=idle.settings, status={})
        self.assertIsNone(session.enter(unknown))
        self.assertIsNotNone(session.enter(idle))
        self.assertIsNone(session.enter(active))
        self.assertIsNone(session.snapshot)

    def test_stale_epoch_response_discarded(self):
        s = State()
        class Worker:
            def submit(self, run, **kwargs):
                self.f = Future()
                return self.f
        w = Worker()
        sess = MaintenanceDiscoverySession()
        sess.enter(s, object(), w)
        s = SimpleNamespace(ready=True, epoch=4, objects=s.objects, settings=s.settings, status=s.status)
        w.f.set_result(('history',))
        self.assertFalse(sess.poll(s))
        self.assertIsNone(sess.snapshot)


if __name__ == '__main__':
    unittest.main()
