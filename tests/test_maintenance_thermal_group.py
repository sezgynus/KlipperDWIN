"""CI-only bundled thermal result recording; no printer, emulator or local tests."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from maintenance_heater import ThermalResult, MaintenancePhysicalRouter
from maintenance_records import MaintenanceBook
from test_maintenance_controller import Worker, printer


FEATURES = ('H01', 'H05', 'H06', 'H07', 'H08', 'H09', 'H13')


class ThermalGroupRecordTests(unittest.TestCase):
    def test_one_operation_persists_seven_independent_records_in_one_write(self):
        state, _ = printer()
        worker = Worker()
        book = MaintenanceBook(worker)
        children = tuple(ThermalResult(feature, 'extruder',
            'FAILED_METRIC' if feature == 'H07' else 'PASSED_USER',
            'thermal_metric_not_satisfied' if feature == 'H07' else
            'thermal_metric_and_user_observation', True,
            (('overshoot_c', 10.) if feature == 'H07' else
             ('rise_c', 12.5),))
            for feature in FEATURES)
        result = ThermalResult('H01', 'extruder', 'FAILED_METRIC',
            'thermal_group_seven_independent_results', True, (), children)
        with patch('maintenance_records.read_json',
                   return_value={'version': 1, 'records': []}), patch(
                       'maintenance_records.write_json') as saved:
            book.record(result, 1, state.state)
            self.assertEqual(len(worker.jobs), 1)
            worker.drain()
            saved.assert_called_once()
        records = saved.call_args.args[1]['records']
        self.assertEqual(tuple(r['feature'] for r in records), FEATURES)
        self.assertEqual(len(set(r['timestamp'] for r in records)), 1)
        self.assertEqual(records[3]['status'], 'FAILED_METRIC')
        self.assertEqual(records[3]['evidence'][0], ('overshoot_c', 10.))
        self.assertTrue(all(r['epoch'] == state.state.epoch for r in records))

    def test_router_hides_six_duplicate_heater_runs_but_preserves_pid(self):
        def row(feature, device):
            return SimpleNamespace(feature_id=feature, device=device)
        rows = tuple(row(f, 'extruder') for f in FEATURES) + (
            row('H02', 'extruder'), row('H03', 'heater_bed'),
            row('H05', 'heater_bed'))
        heater = SimpleNamespace(available=lambda: rows)
        router = MaintenancePhysicalRouter(None, heater)
        visible = router.available()
        self.assertEqual([(r.feature_id,r.device) for r in visible],
                         [('H01','extruder'),('H02','extruder'),
                          ('H03','heater_bed'),('H05','heater_bed')])
