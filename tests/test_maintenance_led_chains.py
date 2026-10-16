"""Regression: bounded indexed LED-chain pulses, full restore and ownership denial.

No real LED, MMU, G-code transport or local printer is used.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_discovery import discover
from maintenance_guided import guided_plan
from maintenance_profiles import approved_integrations
from maintenance_pulse import (compile_pulse, compile_mmu_led_pulse,
                               mmu_led_owner, restored)

TARGET = 'neopixel diagnostic'
COLORS = [(0.1, 0.2, 0.3, 0.0),
          (0.9, 0.1, 0.0, 0.0),
          (0.0, 0.35, 0.0, 0.0),
          (0.0, 0.0, 0.1, 0.0)]


def fixture(colors=None, *, order='GRB', extra_settings=None):
    colors = list(COLORS if colors is None else colors)
    settings = {TARGET: {'pin': 'PA7', 'chain_count': len(colors),
                         'color_order': order}}
    settings.update(extra_settings or {})
    state = SimpleNamespace(
        ready=True, epoch=42, objects=(TARGET,),
        settings=settings, status={TARGET: {'color_data': colors}})
    services = approved_integrations(state, (('led', TARGET),))
    snapshot = discover(state, services)
    row = next(r for r in guided_plan(snapshot) if r.feature_id == 'O04')
    return row, snapshot, {TARGET: {'color_data': colors}}, settings


class LedChainTests(unittest.TestCase):
    def test_four_leds_indexed_batched_and_full_restore(self):
        row, snap, status, settings = fixture()
        p = compile_pulse(row, snap, status, settings)
        self.assertEqual(p.duration_ms, 750)
        self.assertEqual(len(p.original), 4)
        self.assertEqual(len(p.stimulus.splitlines()), 4)
        self.assertEqual(len(p.restore.splitlines()), 4)
        self.assertIn('G4 P750', p.script)
        self.assertNotIn('WHITE=', p.script)
        for i, line in enumerate(p.stimulus.splitlines(), 1):
            self.assertIn('INDEX=%d' % i, line)
            self.assertIn('TRANSMIT=%d' % (i == 4), line)
            self.assertIn('SYNC=0', line)
        for i, line in enumerate(p.restore.splitlines(), 1):
            self.assertIn('INDEX=%d' % i, line)
            self.assertIn('TRANSMIT=%d' % (i == 4), line)
            self.assertIn('RED=%.4f' % COLORS[i - 1][0], line)
            self.assertIn('GREEN=%.4f' % COLORS[i - 1][1], line)
            self.assertIn('BLUE=%.4f' % COLORS[i - 1][2], line)
        self.assertEqual(p.script.count('TRANSMIT=1'), 2)
        self.assertTrue(restored(p, status))
        status[TARGET]['color_data'][3] = (1, 0, 0, 0)
        self.assertFalse(restored(p, status))
        status[TARGET]['color_data'][3] = COLORS[3]
        self.assertTrue(restored(p, status))
        status[TARGET]['color_data'].pop()
        self.assertFalse(restored(p, status))

    def test_single_led_and_original_green_still_changes(self):
        row, snap, status, settings = fixture([COLORS[2]])
        p = compile_pulse(row, snap, status, settings)
        self.assertIn('INDEX=1 TRANSMIT=1', p.stimulus)
        self.assertNotEqual(p.stimulus, p.restore)
        self.assertEqual(p.original, (COLORS[2],))
        self.assertTrue(restored(p, status))

    def test_uniform_rgbw_restores_white_including_zero_values(self):
        colors = [(0, 0, 0, 0.3), (.1, .2, .3, 0)]
        row, snap, status, settings = fixture(colors, order='GRBW')
        p = compile_pulse(row, snap, status, settings)
        self.assertEqual(p.restore.count('WHITE='), 2)
        self.assertIn('WHITE=0.3000', p.restore)
        self.assertIn('WHITE=0.0000', p.restore)
        self.assertTrue(restored(p, status))
        status[TARGET]['color_data'][0] = (0, 0, 0, .4)
        self.assertFalse(restored(p, status))

    def test_invalid_chain_count_pixels_white_mix_and_bounded_length(self):
        variants = [
            ([COLORS[0]] * 33, 'GRB', None),
            ([], 'GRB', None),
            ([(.1, .2, .3)], 'GRB', None),
            ([COLORS[0], (.1, .2, .3, .9)], 'GRB', None),
            ([COLORS[0], COLORS[1]], 'GRB,GRBW', None),
            ([COLORS[0], COLORS[1]], 'BAD', None),
            ([COLORS[0], COLORS[1]], 'GRB', {'chain_count': 1}),
        ]
        for colors, order, overrides in variants:
            with self.subTest(colors=len(colors), order=order, overrides=overrides):
                row, snap, status, settings = fixture(colors, order=order)
                settings[TARGET].update(overrides or {})
                with self.assertRaises(ValueError):
                    compile_pulse(row, snap, status, settings)
        row, snap, status, settings = fixture()
        status[TARGET]['color_data'][2] = (0, float('nan'), 0, 0)
        with self.assertRaises(ValueError):
            compile_pulse(row, snap, status, settings)

    def test_mmu_and_animation_ownership_blocks_even_when_mmu_idle(self):
        settings_variants = [
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)',
                                'enabled': False, 'animation': False}},
            {'led_effect rainbow': {'leds': 'neopixel:diagnostic (1-4)'}},
            {'_led_effect hidden': {'leds': 'neopixel:diagnostic'}},
        ]
        for managed in settings_variants:
            with self.subTest(managed=managed):
                row, snap, status, settings = fixture(extra_settings=managed)
                with self.assertRaisesRegex(ValueError, 'led_managed'):
                    compile_pulse(row, snap, status, settings)
        # Similar names must not match unrelated chains.
        row, snap, status, settings = fixture(extra_settings={
            'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic_extra (1-4)'}})
        self.assertTrue(restored(compile_pulse(row, snap, status, settings), status))

    def test_happy_hare_native_transient_is_unit_scoped_and_user_observed(self):
        owner = {'mmu_leds unit5': {'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        self.assertEqual(mmu_led_owner(settings, TARGET),
                         ('mmu_leds unit5', 'unit5', 4))
        pulse = compile_mmu_led_pulse(
            row, snap, physical, settings,
            {'enabled': True, 'animation': True}, {'action': 'Idle'})
        self.assertTrue(pulse.managed_hh)
        self.assertEqual(
            pulse.script,
            'MMU_SET_LED UNIT=unit5 EXIT_EFFECT=(0,0.35,0) '
            'DURATION=1 FADETIME=0')
        self.assertNotIn('SET_LED LED=', pulse.script)
        self.assertNotIn('ENABLE=0', pulse.script)
        self.assertTrue(restored(pulse, {
            'mmu_leds unit5': {'enabled': True, 'animation': True}}))
        self.assertFalse(restored(pulse, {
            'mmu_leds unit5': {'enabled': False, 'animation': True}}))
        self.assertFalse(restored(pulse, {
            'mmu_leds unit5': {'enabled': True, 'animation': False}}))
        self.assertFalse(restored(pulse, {
            'neopixel diagnostic': {'color_data': COLORS}}))

    def test_happy_hare_direct_handoff_denies_shared_or_partial_led_chain(self):
        variants = [
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (2-4)'}},
            {'mmu_leds unit0': {'entry_leds': 'neopixel:diagnostic (1-4)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)',
                                'status_leds': 'neopixel:diagnostic (1)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)'},
             'mmu_leds unit1': {'exit_leds': 'neopixel:diagnostic (1-4)'}},
            {'mmu_leds malicious;M112': {'exit_leds': 'neopixel:diagnostic (1-4)'}},
        ]
        for managed in variants:
            with self.subTest(managed=managed):
                row, snap, physical, settings = fixture(extra_settings=managed)
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(
                        row, snap, physical, settings,
                        {'enabled': True, 'animation': True},
                        {'action': 'Idle'})

    def test_happy_hare_failed_live_state_refuses_transient(self):
        owner = {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        for unit, mmu in [
            ({'enabled': False, 'animation': True}, {'action': 'Idle'}),
            ({'enabled': True, 'animation': True}, {'action': 'Loading'}),
            ({'enabled': True}, {'action': 'Idle'}),
            ({'enabled': True, 'animation': True}, {}),
        ]:
            with self.subTest(unit=unit, mmu=mmu):
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(row, snap, physical, settings, unit, mmu)
        settings['led_effect standalone'] = {
            'leds': 'neopixel:diagnostic (1-4)'}
        with self.assertRaisesRegex(ValueError, 'independent_led_effect_owner'):
            compile_mmu_led_pulse(
                row, snap, physical, settings,
                {'enabled': True, 'animation': False}, {'action': 'Idle'})

    def test_missing_explicit_profile_not_even_guided(self):
        row, snap, status, settings = fixture()
        from maintenance_discovery import MaintenanceSnapshot
        denied = MaintenanceSnapshot(snap.epoch, snap.devices, snap.global_modes,
                                     snap.config_marker, ())
        self.assertNotIn(row, guided_plan(denied))
        with self.assertRaises(ValueError):
            compile_pulse(row, denied, status, settings)


if __name__ == '__main__':
    unittest.main()
