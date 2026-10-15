"""GitHub CI regressions for the Pi read-only acceptance smoke logic.

These mock-only tests DO NOT run the real Pi smoke or touch Moonraker.
"""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / 'tools' / 'validate_maintenance_pi.py'
spec = importlib.util.spec_from_file_location('maintenance_pi_acceptance', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Clock:
    def __init__(self):
        self.at = 0
    def now(self):
        return self.at
    def sleep(self, seconds):
        self.at += seconds


class Printer:
    def __init__(self, features=('S01', 'S08')):
        self.state = SimpleNamespace(ready=True)
        self.features = features
        self.calls = []
        self.poll_calls = 0
        self.denied = None
        self.status_override = None
    def update_variable(self):
        pass
    def maintenance_read_plan(self):
        return [SimpleNamespace(feature_id=feature) for feature in self.features]
    def start_maintenance_read(self, feature, timeout=8):
        self.calls.append(('start', feature))
        if self.denied == feature:
            return False, 'job_queue_pending'
        return True, 'preflight_queued'
    def poll_maintenance_read(self):
        self.poll_calls += 1
        self.calls.append(('poll',))
        feature = next(call[1] for call in reversed(self.calls)
                       if call[0] == 'start')
        if self.status_override is not None:
            return SimpleNamespace(status=self.status_override,
                                   evidence=(), reason='unsafe')
        return SimpleNamespace(status=None, evidence=(('value', 23),),
                               reason='observed_information')
    def cancel_maintenance_read(self):
        self.calls.append(('cancel',))


class PiAcceptanceLogicTests(unittest.TestCase):
    def run_smoke(self, printer, seconds=5):
        clk = Clock()
        return module.smoke(printer, seconds=seconds,
                            clock=clk.now, nap=clk.sleep)

    def test_required_readonly_evidence_must_be_observed(self):
        p = Printer()
        report = self.run_smoke(p)
        self.assertEqual(report['verdict'], 'READ_ONLY_SMOKE_OK')
        self.assertEqual(set(report['observations']),
                         {'S01', 'S08', 'S02', 'S03', 'S05', 'S10'})
        self.assertTrue(all(
            report['observations'][key]['status'] == 'UNAVAILABLE'
            for key in ('S02', 'S03', 'S05', 'S10')))
        self.assertTrue(report['ready'])
        self.assertEqual(report['observations']['S01']['status'], 'OBSERVED')
        self.assertIn('not physical hardware PASS', report['note'])
        self.assertEqual([c[1] for c in p.calls if c[0] == 'start'],
                         ['S01', 'S08'])

    def test_not_ready_or_no_verified_capability_is_incomplete(self):
        missing = Printer(features=('S01',))
        result = self.run_smoke(missing)
        self.assertFalse(result['ready'])
        self.assertEqual(result['verdict'], 'INCOMPLETE')
        self.assertEqual(missing.calls, [])
        disconnected = Printer()
        disconnected.state.ready = False
        self.assertFalse(self.run_smoke(disconnected)['ready'])

    def test_busy_job_queue_and_inconclusive_fail_required_checks(self):
        blocked = Printer()
        blocked.denied = 'S01'
        report = self.run_smoke(blocked)
        self.assertEqual(report['observations']['S01']['status'], 'BLOCKED')
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertEqual([c for c in blocked.calls if c[0] == 'start'],
                         [('start', 'S01')])
        failed = Printer()
        failed.status_override = 'INCONCLUSIVE'
        report = self.run_smoke(failed)
        self.assertEqual(report['observations']['S01']['status'], 'INCONCLUSIVE')
        self.assertEqual(report['verdict'], 'INCOMPLETE')

    def test_optional_information_is_not_physical_pass(self):
        p = Printer(features=('S01', 'S08', 'S02', 'S03', 'S05', 'S10'))
        report = self.run_smoke(p)
        self.assertEqual(report['verdict'], 'READ_ONLY_SMOKE_OK')
        self.assertTrue(all(v['status'] == 'OBSERVED'
                            for v in report['observations'].values()))
        self.assertTrue(all(v['status'] != 'PASSED'
                            for v in report['observations'].values()))

    def test_direct_script_imports_printer_backend_from_other_cwd(self):
        # -I removes PYTHONPATH/current-directory shortcuts; exercise the
        # entry script exactly as Pi operators launch it from tools/.
        snippet = ("import runpy; runpy.run_path(%r, run_name='maint_test'); "
                   "from printerInterface import PrinterData; "
                   "assert PrinterData is not None") % str(SCRIPT)
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, '-I', '-c', snippet], cwd=cwd,
                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_cli_help_does_not_need_pi_or_moonraker(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, '-I', str(SCRIPT), '--help'], cwd=cwd,
                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--moonraker', result.stdout)

    def test_invalid_timeout_is_rejected_without_printer_access(self):
        printer = Printer()
        for seconds in (0, 4.9, True, float('nan'), float('inf')):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                module.smoke(printer, seconds=seconds)


if __name__ == '__main__':
    unittest.main()
