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
from maintenance_pulse import compile_pulse, compile_mmu_led_pulse, restored
from maintenance_hh_leds import mmu_led_owners, auto_happy_hare_led_services

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

    def test_hh_generates_segment_specific_native_timed_commands(self):
        for segment in ('exit', 'entry', 'status', 'logo'):
            with self.subTest(segment=segment):
                owner = {'mmu_leds unit5': {
                    segment + '_leds': 'neopixel:diagnostic (1-4)'}}
                row, snap, physical, settings = fixture(extra_settings=owner)
                owners = mmu_led_owners(settings, TARGET)
                self.assertEqual(owners[0].unit, 'unit5')
                self.assertEqual(owners[0].segments, ((segment, (1, 2, 3, 4)),))
                status = {'mmu_leds unit5': {
                    'enabled': True, 'animation': True, segment: 4}}
                pulse = compile_mmu_led_pulse(
                    row, snap, physical, settings, status, {'action': 'Idle'})
                self.assertTrue(pulse.managed_hh)
                self.assertTrue(pulse.script.startswith(
                    'MMU_SET_LED UNIT=unit5 %s_EFFECT=(' % segment.upper()))
                self.assertTrue(pulse.script.endswith(
                    ') DURATION=1 FADETIME=0'))
                values = pulse.script.split('_EFFECT=(', 1)[1].split(')', 1)[0]
                rgb = tuple(float(x) for x in values.split(','))
                self.assertEqual(len(rgb), 3)
                for original in COLORS:
                    self.assertTrue(any(abs(a - b) >= .08
                                        for a, b in zip(rgb, original)))
                self.assertNotIn('SET_LED LED=', pulse.script)
                self.assertNotIn('ENABLE=0', pulse.script)
                self.assertTrue(restored(pulse, status))
                changed = {k: dict(v) for k, v in status.items()}
                changed['mmu_leds unit5']['enabled'] = False
                self.assertFalse(restored(pulse, changed))
                changed['mmu_leds unit5'] = {'enabled': True, 'animation': False}
                self.assertFalse(restored(pulse, changed))
                self.assertFalse(restored(pulse, {
                    'neopixel diagnostic': {'color_data': COLORS}}))

    def test_mixed_segments_indexes_and_multiple_units(self):
        owner = {
            'mmu_leds north': {
                'exit_leds': 'neopixel:diagnostic (1-2)',
                'status_leds': 'neopixel:diagnostic (3)'},
            'mmu_leds south': {'logo_leds': 'neopixel:diagnostic (4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        owners = mmu_led_owners(settings, TARGET)
        self.assertEqual(len(owners), 2)
        self.assertEqual(owners[0].segments,
                         (('exit', (1, 2)), ('status', (3,))))
        self.assertEqual(owners[1].segments, (('logo', (4,)),))
        live = {
            'mmu_leds north': {'enabled': True, 'animation': True,
                               'exit': 2, 'status': 1},
            'mmu_leds south': {'enabled': True, 'animation': False, 'logo': 1},
        }
        pulse = compile_mmu_led_pulse(
            row, snap, physical, settings, live, {'action': 'Idle'})
        self.assertEqual(len(pulse.script.splitlines()), 2)
        self.assertIn('UNIT=north EXIT_EFFECT=', pulse.script)
        self.assertIn(' STATUS_EFFECT=', pulse.script)
        self.assertIn('UNIT=south LOGO_EFFECT=', pulse.script)
        self.assertNotIn('ENTRY_EFFECT=', pulse.script)
        self.assertEqual(pulse.hh_controls, ('mmu_leds north', 'mmu_leds south'))
        self.assertTrue(restored(pulse, live))
        live['mmu_leds south']['animation'] = True
        self.assertFalse(restored(pulse, live))

    def test_hh_sparse_ordered_and_reversed_index_mapping(self):
        owner = {'mmu_leds unit1': {
            'entry_leds': 'neopixel:diagnostic (4,2-3,1)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        entries = mmu_led_owners(settings, TARGET)
        self.assertEqual(entries[0].segments, (('entry', (4, 2, 3, 1)),))
        p = compile_mmu_led_pulse(
            row, snap, physical, settings,
            {'mmu_leds unit1': {'enabled': True, 'animation': False, 'entry': 4}},
            {'action': 'Idle'})
        self.assertIn('ENTRY_EFFECT=', p.script)

    def test_hh_partial_chain_and_static_segment_allowed(self):
        owner = {'mmu_leds unit2': {
            'logo_leds': 'neopixel:diagnostic (2-3)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        p = compile_mmu_led_pulse(
            row, snap, physical, settings,
            {'mmu_leds unit2': {'enabled': True, 'animation': False, 'logo': 2}},
            {'action': 'Idle'})
        self.assertIn('LOGO_EFFECT=', p.script)
        self.assertIn('mapped MMU LEDs', p.observation)

    def test_hh_invalid_overlap_ambiguous_and_cross_chain_fail_closed(self):
        variants = [
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (0-4)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-5)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1,1)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-3)',
                                'status_leds': 'neopixel:diagnostic (3-4)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)'},
             'mmu_leds unit1': {'entry_leds': 'neopixel:diagnostic (4)'}},
            {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)\n'
                                            'neopixel:other (1)'}},
            {'mmu_leds malicious;M112': {'exit_leds': 'neopixel:diagnostic (1-4)'}},
        ]
        for managed in variants:
            with self.subTest(managed=managed):
                row, snap, physical, settings = fixture(extra_settings=managed)
                with self.assertRaises(ValueError):
                    mmu_led_owners(settings, TARGET)
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(
                        row, snap, physical, settings, {},
                        {'action': 'Idle'})

    def test_hh_missing_or_busy_status_and_external_effect_fail_closed(self):
        owner = {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        for controls, mmu in [
            ({'mmu_leds unit0': {'enabled': False, 'animation': True, 'exit': 4}},
             {'action': 'Idle'}),
            ({'mmu_leds unit0': {'enabled': True, 'animation': True, 'exit': 4}},
             {'action': 'Loading'}),
            ({'mmu_leds unit0': {'enabled': True, 'exit': 4}},
             {'action': 'Idle'}),
            ({'mmu_leds unit0': {'enabled': True, 'animation': True, 'exit': 3}},
             {'action': 'Idle'}),
            ({'mmu_leds unit0': {'enabled': True, 'animation': True}},
             {'action': 'Idle'}),
        ]:
            with self.subTest(controls=controls, mmu=mmu):
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(
                        row, snap, physical, settings, controls, mmu)
        settings['led_effect standalone'] = {
            'leds': 'neopixel:diagnostic (1-4)'}
        with self.assertRaisesRegex(ValueError, 'independent_led_effect_owner'):
            compile_mmu_led_pulse(
                row, snap, physical, settings,
                {'mmu_leds unit0': {
                    'enabled': True, 'animation': True, 'exit': 4}},
                {'action': 'Idle'})

    def test_hh_auto_discovers_configured_objects_without_manual_profiles(self):
        owner = {'mmu_leds unit7': {
            'logo_leds': 'neopixel:diagnostic (1-4)'}}
        _, snap, _, settings = fixture(extra_settings=owner)
        state = SimpleNamespace(
            ready=True, epoch=42, objects=(TARGET, 'mmu_leds unit7'),
            settings=settings, status={})
        keys = auto_happy_hare_led_services(state)
        self.assertEqual(keys, ('maintenance.safe_led:' + TARGET,))
        self.assertEqual(keys, approved_integrations(state, ()))
        discovery = discover(state, keys)
        self.assertTrue(any(row.feature_id == 'O04' and row.device == TARGET
                            for row in guided_plan(discovery)))
        state.objects = (TARGET,)  # MMU controller absent -> no automatic role
        self.assertEqual(auto_happy_hare_led_services(state), ())
        state.objects = (TARGET, 'mmu_leds unit7')
        state.settings['mmu_leds unit7']['logo_leds'] = (
            'neopixel:diagnostic (0-4)')
        self.assertEqual(auto_happy_hare_led_services(state), ())

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
