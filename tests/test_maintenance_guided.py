"""Regression coverage for Stage-8 guided adapter consent; NO actuation."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance_catalog import definition_for
from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, AUTOMATIC, _add
from maintenance_guided import guided_adapters, guided_plan, GuidedConsentGate
from maintenance_safety import SafetyContext


def snapshot_with_devices(services=()):
    devices = (
        DeviceCapabilities('fan', 'fan', _add(0, 'F01', USER)),
        DeviceCapabilities('fan_generic extruder', 'fan', _add(0, 'F04', USER)),
        DeviceCapabilities('fan_generic tach', 'fan', _add(0, 'F04', AUTOMATIC)),
        DeviceCapabilities('output_pin enclosure', 'actuator', _add(0, 'O03', USER)),
        DeviceCapabilities('output_pin heater_enable', 'actuator', _add(0, 'O03', USER)),
        DeviceCapabilities('neopixel frame', 'led', _add(0, 'O04', USER)),
        DeviceCapabilities('servo mmu', 'actuator', _add(0, 'O02', USER)),
        DeviceCapabilities('pwm_cycle_time alert', 'actuator', _add(0, 'S18', USER)),
    )
    return MaintenanceSnapshot(
        7, devices, 0, 111, tuple(services))


def safety_context(snap):
    state = SimpleNamespace(
        ready=True, epoch=snap.epoch, settings=None,
        status={'webhooks': {'state': 'ready'},
                'print_stats': {'state': 'standby'},
                'virtual_sdcard': {'is_active': False},
                'pause_resume': {'is_paused': False}})
    return state


class Stage8GuidedTests(unittest.TestCase):
    def test_registry_contracts_match_original_catalog(self):
        adapters = guided_adapters()
        self.assertEqual({a.feature_id for a in adapters},
                         {'F01', 'F02', 'F04', 'F12', 'O03', 'O04', 'S18'})
        self.assertTrue(all(a.method == USER and
                            a.evidence_contract == definition_for(a.feature_id).evidence_contract
                            and a.safety_profile == definition_for(a.feature_id).safety_profile
                            for a in adapters))

    def test_printer_backend_exposes_passive_guided_candidates_without_io(self):
        # This is a routing contract: pure planner correctness and device
        # filtering have separate explicit-snapshot tests below.
        from test_regressions import backend
        from unittest.mock import patch
        pd = backend.PrinterData.__new__(backend.PrinterData)
        original = snapshot_with_devices()
        pd.maintenance = SimpleNamespace(snapshot=original)
        expected = (object(), object())
        with patch.object(backend, 'guided_plan', return_value=expected) as planner:
            self.assertIs(pd.maintenance_guided_plan(), expected)
            planner.assert_called_once_with(original)
        self.assertIs(pd.maintenance.snapshot, original)

    def test_never_guess_pin_safety_or_buzzer_registration(self):
        snap = snapshot_with_devices()
        rows = guided_plan(snap)
        self.assertEqual({(r.feature_id, r.device) for r in rows},
                         {('F01', 'fan')})
        self.assertFalse(any(r.device == 'fan_generic tach' for r in rows))
        self.assertFalse(any(r.device == 'output_pin heater_enable' for r in rows))
        self.assertFalse(any(r.feature_id == 'S18' for r in rows))

    def test_explicit_service_evidence_enables_buzzer_and_case_light(self):
        snap = snapshot_with_devices((
            'maintenance.visual:output_pin enclosure',
            'maintenance.audible:pwm_cycle_time alert',
            'maintenance.safe_fan:fan_generic extruder',
            'maintenance.safe_led:neopixel frame'))
        keys = {(r.feature_id, r.device) for r in guided_plan(snap)}
        self.assertIn(('O03', 'output_pin enclosure'), keys)
        self.assertIn(('S18', 'pwm_cycle_time alert'), keys)
        self.assertIn(('F04', 'fan_generic extruder'), keys)
        self.assertIn(('O04', 'neopixel frame'), keys)
        self.assertNotIn(('O03', 'output_pin heater_enable'), keys)

    def test_consent_requires_positive_safety_and_never_claims_pass(self):
        settings = {}
        snap = snapshot_with_devices()
        snap = MaintenanceSnapshot(snap.epoch, snap.devices, snap.global_modes,
                                   id(settings), snap.service_key)
        row = guided_plan(snap)[0]
        state = SimpleNamespace(
            ready=True, epoch=7, settings=settings,
            status={'webhooks': {'state': 'ready'},
                    'print_stats': {'state': 'standby'},
                    'virtual_sdcard': {'is_active': False},
                    'pause_resume': {'is_paused': False}})
        ctx = SafetyContext(state, True, {'queue_state': 'ready', 'queued_jobs': []},
                            True, False)
        gate = GuidedConsentGate()
        self.assertEqual(gate.arm(row, snap, SafetyContext(state))[1],
                         'queue_unknown')
        token, why = gate.arm(row, snap, ctx)
        self.assertEqual(why, 'awaiting_user_consent')
        self.assertTrue(gate.active)
        self.assertEqual(gate.approve(token + 1, snap, ctx)[1],
                         'invalid_consent_session')
        result, reason = gate.approve(token, snap, ctx)
        self.assertEqual(result.status, 'CONSENTED')
        self.assertEqual(result.reason, 'no_hardware_command_dispatched')
        self.assertFalse(gate.active)
        self.assertNotEqual(result.status, 'PASSED')
        self.assertEqual(gate.approve(token, snap, ctx)[1], 'invalid_consent_session')

    def test_print_started_or_epoch_changed_revokes_approval(self):
        settings = {}
        snap = snapshot_with_devices()
        snap = MaintenanceSnapshot(7, snap.devices, snap.global_modes,
                                   id(settings), snap.service_key)
        row = guided_plan(snap)[0]
        state = SimpleNamespace(
            ready=True, epoch=7, settings=settings,
            status={'webhooks': {'state': 'ready'},
                    'print_stats': {'state': 'standby'},
                    'virtual_sdcard': {'is_active': False},
                    'pause_resume': {'is_paused': False}})
        ctx = SafetyContext(state, True, None, True, False)
        gate = GuidedConsentGate()
        token, _ = gate.arm(row, snap, ctx)
        state.status['print_stats']['state'] = 'printing'
        self.assertEqual(gate.approve(token, snap, ctx)[1],
                         'unsafe_or_stale_consent')
        self.assertFalse(gate.active)
        state.status['print_stats']['state'] = 'standby'
        token, _ = gate.arm(row, snap, ctx)
        new_snap = MaintenanceSnapshot(8, snap.devices, snap.global_modes,
                                       snap.config_marker, snap.service_key)
        self.assertEqual(gate.approve(token, new_snap, ctx)[1],
                         'unsafe_or_stale_consent')

    def test_invalid_target_timeout_and_cancel_do_not_arm(self):
        settings = {}
        snap = snapshot_with_devices()
        row = guided_plan(snap)[0]
        ctx = SafetyContext(None)
        gate = GuidedConsentGate()
        for timeout in (True, 0, -1, 31, float('nan')):
            self.assertEqual(gate.arm(row, snap, ctx, timeout=timeout)[1],
                             'invalid_timeout')
        self.assertEqual(gate.arm(row, MaintenanceSnapshot(20), ctx)[1],
                         'unregistered_or_stale_target')
        gate.cancel()
        self.assertFalse(gate.active)
        gate.close()


if __name__ == '__main__':
    unittest.main()
