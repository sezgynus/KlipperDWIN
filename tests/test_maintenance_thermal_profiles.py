import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from maintenance_thermal_profiles import profile_services, profile_for
from maintenance_thermal import contract
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, CALIBRATION, _add
from maintenance_heater import thermal_plan

class ThermalProfileTests(unittest.TestCase):
    def setUp(self):
        self.name = 'heater_generic dryer'
        self.state = SimpleNamespace(ready=True, objects=(self.name,), settings={
            self.name: {'min_temp': 0., 'max_temp': 100., 'heater_pin': 'PA1'}})
        self.profile = {'version': 1, 'heaters': [{
            'object': self.name, 'target': 45., 'ceiling': 55., 'duration_s': 120.}]}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'profile.json'

    def write(self):
        self.path.write_text(json.dumps(self.profile))
        return profile_services(self.state, self.path)

    def test_exact_application_profile_enables_generic_pid_and_no_other_target(self):
        services = self.write()
        snap = MaintenanceSnapshot(1, (DeviceCapabilities(self.name, 'heater',
            _add(0, 'H04', CALIBRATION)),), service_key=services)
        self.assertEqual(profile_for(snap, self.name), (45., 120.))
        self.assertEqual(len(thermal_plan(snap)), 1)
        self.assertIsNone(profile_for(snap, 'heater_generic other'))
        c = contract(self.name, self.state.settings,
            {self.name: {'temperature': 25., 'target': 0., 'power': 0.}},
            'H04', profile_for(snap, self.name))
        self.assertEqual(c.target, 45.)
        self.assertEqual(c.duration, 900.)
        self.assertIn('HEATER=dryer TARGET=0', c.off)

    def test_missing_duplicate_out_of_bounds_unknown_fields_fail_closed(self):
        self.assertEqual(profile_services(self.state, self.path), ())
        # A legacy ceiling value is ignored; target/duration remain bounded.
        self.profile['heaters'][0]['ceiling'] = 120.
        self.assertEqual(len(self.write()), 1)
        self.profile['heaters'][0]['target'] = 120.
        self.assertEqual(self.write(), ())
        self.profile['heaters'][0]['target'] = 45.
        self.profile['heaters'].append(dict(self.profile['heaters'][0]))
        self.assertEqual(self.write(), ())
        self.profile['heaters'].pop()
        self.profile['heaters'][0]['macro'] = 'M112'
        self.assertEqual(self.write(), ())

    def test_new_profile_without_ceiling_and_legacy_snapshot_are_supported(self):
        del self.profile['heaters'][0]['ceiling']
        services = self.write()
        snap = MaintenanceSnapshot(1, (DeviceCapabilities(self.name, 'heater',
            _add(0, 'H04', CALIBRATION)),), service_key=services)
        self.assertEqual(profile_for(snap, self.name), (45., 120.))
        legacy = MaintenanceSnapshot(1, snap.devices,
            service_key=('maintenance.thermal_profile:'+self.name+'|45,55,120',))
        self.assertEqual(profile_for(legacy, self.name), (45., 120.))
        self.profile['heaters'][0]['duration_s'] = 200.
        self.assertEqual(self.write(), ())

    def test_unprofiled_generic_has_no_runnable_row(self):
        snap = MaintenanceSnapshot(1, (DeviceCapabilities(self.name, 'heater',
            _add(0, 'H04', CALIBRATION)),))
        self.assertEqual(thermal_plan(snap), ())
