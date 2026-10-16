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
    names = tuple(section.split(' ', 1)[1] for section in settings
                  if isinstance(section, str) and section.startswith('mmu_leds '))
    if names:
        settings['mmu_machine'] = {'units': names}
    state = SimpleNamespace(
        ready=True, epoch=42, objects=(TARGET,),
        settings=settings, status={TARGET: {'color_data': colors}})
    services = approved_integrations(state, (('led', TARGET),))
    snapshot = discover(state, services)
    row = next(r for r in guided_plan(snapshot) if r.feature_id == 'O04')
    return row, snapshot, {TARGET: {'color_data': colors}}, settings


class LedChainTests(unittest.TestCase):
    def test_four_leds_full_brightness_red_blue_green_white_and_restore(self):
        row, snap, status, settings = fixture()
        p = compile_pulse(row, snap, status, settings)
        self.assertEqual(p.duration_ms, 2600)
        self.assertEqual(len(p.original), 4)
        self.assertEqual(len(p.stimulus.splitlines()), 16)
        self.assertEqual(len(p.restore.splitlines()), 4)
        self.assertEqual(p.script.count('G4 P650'), 4)
        self.assertNotIn('WHITE=', p.script)
        frames = p.stimulus.splitlines()
        expected = [(1., 0., 0.), (0., 0., 1.),
                    (0., 1., 0.), (1., 1., 1.)]
        for phase, rgb in enumerate(expected):
            for i in range(4):
                line = frames[phase * 4 + i]
                self.assertIn('INDEX=%d' % (i + 1), line)
                self.assertIn('TRANSMIT=%d' % (i == 3), line)
                self.assertIn('SYNC=0', line)
                for channel, intensity in zip(('RED', 'GREEN', 'BLUE'), rgb):
                    self.assertIn('%s=%.4f' % (channel, intensity), line)
        for i, line in enumerate(p.restore.splitlines(), 1):
            self.assertIn('INDEX=%d' % i, line)
            self.assertIn('TRANSMIT=%d' % (i == 4), line)
            self.assertIn('RED=%.4f' % COLORS[i - 1][0], line)
            self.assertIn('GREEN=%.4f' % COLORS[i - 1][1], line)
            self.assertIn('BLUE=%.4f' % COLORS[i - 1][2], line)
        self.assertEqual(p.script.count('TRANSMIT=1'), 5)
        self.assertIn('red, blue, green, white', p.observation)
        self.assertTrue(p.observation.startswith('All LEDs R/B/G/W then back?'))
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
        self.assertEqual(p.stimulus.count('WHITE='), 8)
        for line in p.stimulus.splitlines()[2:4]:
            self.assertIn('BLUE=1.0000', line)
        for line in p.stimulus.splitlines()[-2:]:
            self.assertIn('RED=0.0000', line)
            self.assertIn('GREEN=0.0000', line)
            self.assertIn('BLUE=0.0000', line)
            self.assertIn('WHITE=1.0000', line)
        self.assertIn('WHITE=0.0000', p.restore)
        self.assertTrue(restored(p, status))
        status[TARGET]['color_data'][0] = (0, 0, 0, .4)
        self.assertFalse(restored(p, status))

    def test_klipper_color_order_list_and_tuple_formats(self):
        # Klipper config.getlist records tuple values, serialized to JSON
        # arrays in configfile.settings. Both managed and independent paths
        # must accept the same effective configuration.
        for order, white in (
                (['GRB'], False),
                (('GRB',), False),
                (['GRB', 'GRB', 'GRB', 'GRB'], False),
                (['GRBW'], True),
                (('GRBW', 'GRBW', 'GRBW', 'GRBW'), True)):
            with self.subTest(order=order):
                row, snap, status, settings = fixture()
                settings[TARGET]['color_order'] = order
                p = compile_pulse(row, snap, status, settings)
                self.assertEqual(p.script.count('G4 P650'), 4)
                self.assertEqual(p.stimulus.count('WHITE='), 16 if white else 0)
                self.assertTrue(restored(p, status))

    def test_klipper_color_order_malformed_lists_block_before_gcode(self):
        bad = (
            [], ['GRB', 'GRBW'], ['GRB', 'GRB'],
            ['GRB', 'GRB', 'GRB', 'GRBW'],
            ['GGB'], ['R'], [None], ['RGB', 5],
            [['GRB']], ('GRB', 'GRBW', 'GRB', 'GRBW'))
        for order in bad:
            with self.subTest(order=order):
                row, snap, status, settings = fixture()
                settings[TARGET]['color_order'] = order
                with self.assertRaisesRegex(ValueError, 'led_color_order_unsupported'):
                    compile_pulse(row, snap, status, settings)

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

    def test_monochrome_led_output_refuses_rgb_cycle(self):
        # A one-channel LED cannot emit 4 RGB colors. Fail before sending G-code.
        row, snap, status, settings = fixture()
        from dataclasses import replace
        row = replace(row, device='led mono')
        cfg = {'led mono': {'white_pin': 'PA7', 'chain_count': 1}}
        live = {'led mono': {'color_data': [(0., 0., 0., 0.3)]}}
        from maintenance_discovery import MaintenanceSnapshot, DeviceCapabilities, USER, _add
        snapshot = MaintenanceSnapshot(
            snap.epoch,
            (DeviceCapabilities('led mono', 'led', _add(0, 'O04', USER)),),
            0, id(cfg), ('maintenance.safe_led:led mono',))
        row = replace(row, config_marker=snapshot.config_marker)
        with self.assertRaisesRegex(ValueError, 'led_rgb_channels_not_configured'):
            compile_pulse(row, snapshot, live, cfg)

    def test_maximum_32_rgbw_pixels_stays_bounded(self):
        row, snap, status, settings = fixture([(0., 0., 0., 0.)] * 32,
                                             order='GRBW')
        pulse = compile_pulse(row, snap, status, settings)
        self.assertLess(len(pulse.script), 26000)
        self.assertEqual(pulse.script.count('G4 P650'), 4)
        self.assertEqual(pulse.script.count('TRANSMIT=1'), 5)
        self.assertTrue(restored(pulse, status))

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
                self.assertEqual(pulse.duration_ms, 2600)
                self.assertEqual(len(pulse.script.splitlines()), 12)
                colors = [(1., 0., 0.), (0., 0., 1.),
                          (0., 1., 0.), (1., 1., 1.)]
                for phase, rgb in enumerate(colors):
                    command, dwell, barrier = pulse.script.splitlines()[phase * 3:phase * 3 + 3]
                    self.assertEqual(
                        command,
                        'MMU_SET_LED UNIT=0 %s_EFFECT=(%.3f,%.3f,%.3f) '
                        'DURATION=0.40 FADETIME=0' % (
                            segment.upper(), *rgb))
                    self.assertEqual(dwell, 'G4 P650')
                    self.assertEqual(barrier, 'M400')
                self.assertEqual(pulse.script.count('M400'), 4)
                self.assertIn('red, blue, green, white', pulse.observation)
                self.assertTrue(pulse.observation.startswith('All LEDs R/B/G/W then back?'))
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
        self.assertEqual(len(pulse.script.splitlines()), 16)
        self.assertEqual(pulse.script.count('M400'), 4)
        self.assertIn('UNIT=0 EXIT_EFFECT=', pulse.script)
        self.assertIn(' STATUS_EFFECT=', pulse.script)
        self.assertIn('UNIT=1 LOGO_EFFECT=', pulse.script)
        self.assertNotIn('ENTRY_EFFECT=', pulse.script)
        self.assertEqual(pulse.hh_controls, ('mmu_leds north', 'mmu_leds south'))
        self.assertTrue(restored(pulse, live))
        live['mmu_leds south']['animation'] = True
        self.assertFalse(restored(pulse, live))

    def test_numeric_unit_index_comes_from_machine_order_not_unit_name(self):
        owner = {
            'mmu_leds north': {'exit_leds': 'neopixel:diagnostic (1-2)'},
            'mmu_leds south': {'entry_leds': 'neopixel:diagnostic (3-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        # Reverse the authoritative order despite segment iteration order.
        settings['mmu_machine'] = {'units': ['south', 'north']}
        status = {
            'mmu_leds north': {'enabled': True, 'animation': True, 'exit': 2},
            'mmu_leds south': {'enabled': True, 'animation': False, 'entry': 2}}
        p = compile_mmu_led_pulse(
            row, snap, physical, settings, status, {'action': 'Idle'})
        self.assertIn('MMU_SET_LED UNIT=1 EXIT_EFFECT=', p.script)
        self.assertIn('MMU_SET_LED UNIT=0 ENTRY_EFFECT=', p.script)
        self.assertNotIn('UNIT=north', p.script)
        self.assertNotIn('UNIT=south', p.script)

    def test_unit_index_missing_malformed_or_ambiguous_fail_closed(self):
        owner = {'mmu_leds unit0': {'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        status = {'mmu_leds unit0': {
            'enabled': True, 'animation': True, 'exit': 4}}
        for machine in (None, {}, {'units': []},
                        {'units': ['other']},
                        {'units': ['unit0', 'unit0']},
                        {'units': ['unit0;M112']},
                        {'units': 1}):
            with self.subTest(machine=machine):
                if machine is None:
                    settings.pop('mmu_machine', None)
                else:
                    settings['mmu_machine'] = machine
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(
                        row, snap, physical, settings, status, {'action': 'Idle'})
        # Valid strings from older Klipper config status representations.
        settings['mmu_machine'] = {'units': 'other,unit0'}
        pulse = compile_mmu_led_pulse(
            row, snap, physical, settings, status, {'action': 'Idle'})
        self.assertIn('UNIT=1 EXIT_EFFECT=', pulse.script)

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
            ready=True, epoch=42, objects=(TARGET, 'mmu_leds unit7', 'mmu_machine'),
            settings=settings, status={})
        keys = auto_happy_hare_led_services(state)
        self.assertEqual(keys, ('maintenance.safe_led:' + TARGET,))
        self.assertEqual(keys, approved_integrations(state, ()))
        discovery = discover(state, keys)
        self.assertTrue(any(row.feature_id == 'O04' and row.device == TARGET
                            for row in guided_plan(discovery)))
        state.objects = (TARGET,)  # MMU controller absent -> no automatic role
        self.assertEqual(auto_happy_hare_led_services(state), ())
        state.objects = (TARGET, 'mmu_leds unit7', 'mmu_machine')
        state.settings['mmu_leds unit7']['logo_leds'] = (
            'neopixel:diagnostic (0-4)')
        self.assertEqual(auto_happy_hare_led_services(state), ())

    def test_hh_live_machine_status_enables_discovery_when_settings_units_absent(self):
        owner = {'mmu_leds unit0': {
            'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        settings['mmu_machine'] = {}  # actual effective config can omit units
        machine = {'num_units': 1, 'unit_0': {'name': 'OpenEYE MMU'}}
        state = SimpleNamespace(
            ready=True, epoch=42,
            objects=(TARGET, 'mmu_leds unit0', 'mmu_machine', 'mmu'),
            settings=settings,
            status={'mmu_machine': machine, 'mmu': {'action': 'Idle'}})
        keys = approved_integrations(state, ())
        self.assertIn('maintenance.safe_led:' + TARGET, keys)
        discovery = discover(state, keys)
        self.assertEqual(
            [item.device for item in guided_plan(discovery)
             if item.feature_id == 'O04'], [TARGET])
        live = {'mmu_leds unit0': {
            'enabled': True, 'animation': True, 'exit': 4}}
        program = compile_mmu_led_pulse(
            row, snap, physical, settings, live, {'action': 'Idle'}, machine)
        self.assertIn('MMU_SET_LED UNIT=0 EXIT_EFFECT=', program.script)
        self.assertNotIn('UNIT=unit0', program.script)

    def test_hh_live_machine_order_controls_numeric_dispatch(self):
        owners = {
            'mmu_leds first': {'status_leds': 'neopixel:diagnostic (1-2)'},
            'mmu_leds second': {'logo_leds': 'neopixel:diagnostic (3-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owners)
        settings['mmu_machine'] = {'units': None}
        machine = {
            'num_units': 2,
            'unit_0': {'name': 'second'},
            'unit_1': {'name': 'first'}}
        controls = {
            'mmu_leds first': {'enabled': True, 'animation': True, 'status': 2},
            'mmu_leds second': {'enabled': True, 'animation': False, 'logo': 2}}
        p = compile_mmu_led_pulse(
            row, snap, physical, settings, controls, {'action': 'Idle'},
            machine)
        self.assertIn('UNIT=1 STATUS_EFFECT=', p.script)
        self.assertIn('UNIT=0 LOGO_EFFECT=', p.script)
        self.assertNotIn('UNIT=first', p.script)
        self.assertNotIn('UNIT=second', p.script)

    def test_hh_live_machine_missing_conflicting_or_malformed_fail_closed(self):
        owner = {'mmu_leds unit0': {
            'exit_leds': 'neopixel:diagnostic (1-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        settings['mmu_machine'] = {}
        controls = {'mmu_leds unit0': {
            'enabled': True, 'animation': True, 'exit': 4}}
        state = SimpleNamespace(
            ready=True, epoch=42,
            objects=(TARGET, 'mmu_leds unit0', 'mmu_machine'),
            settings=settings, status={})
        invalid = [
            None,
            {},
            {'num_units': 0},
            {'num_units': True, 'unit_0': {'name': 'unit0'}},
            {'num_units': 2, 'unit_0': {'name': 'unit0'}},
            {'num_units': 1, 'unit_1': {'name': 'unit0'}},
            {'num_units': 1, 'unit_0': {'name': ''}},
            {'num_units': 1, 'unit_0': {'name': 'unit0'},
             'unit_1': {'name': 'extra'}},
            {'num_units': 2, 'unit_0': {'name': 'unit0'},
             'unit_1': {'name': 'unit0'}},
            {'num_units': 1, 'unit_0': {'name': 'unit0;M112'}},
            {'num_units': 1, 'unit_0': 'unit0'},
        ]
        for machine in invalid:
            with self.subTest(machine=machine):
                state.status = {'mmu_machine': machine} if machine is not None else {}
                self.assertEqual(approved_integrations(state, ()), ())
                with self.assertRaises(ValueError):
                    compile_mmu_led_pulse(
                        row, snap, physical, settings, controls,
                        {'action': 'Idle'}, machine)
        machine = {'num_units': 1, 'unit_0': {'name': 'unit0'}}
        settings['mmu_machine']['units'] = 'elsewhere'
        state.status = {'mmu_machine': machine}
        self.assertEqual(approved_integrations(state, ()), ())
        with self.assertRaisesRegex(ValueError, 'unit_order_conflict'):
            compile_mmu_led_pulse(
                row, snap, physical, settings, controls, {'action': 'Idle'},
                machine)

    def test_single_unit_display_name_no_suffix_assumption(self):
        for unit_name, display_name in (
                ('alpha', 'OpenEYE MMU'),
                ('feeder-42', 'Custom Multi Material Feeder')):
            with self.subTest(unit_name=unit_name):
                owner = {'mmu_leds ' + unit_name: {
                    'logo_leds': 'neopixel:diagnostic (1-4)'}}
                row, snap, physical, settings = fixture(extra_settings=owner)
                settings['mmu_machine'] = {}  # no config order
                machine = {'num_units': 1, 'unit_0': {
                    'name': display_name}}
                state = SimpleNamespace(
                    ready=True, epoch=42,
                    objects=(TARGET, 'mmu_machine', 'mmu_leds ' + unit_name),
                    settings=settings, status={'mmu_machine': machine})
                self.assertIn('maintenance.safe_led:' + TARGET,
                              approved_integrations(state, ()))
                program = compile_mmu_led_pulse(
                    row, snap, physical, settings,
                    {'mmu_leds ' + unit_name: {
                        'enabled': True, 'animation': False, 'logo': 4}},
                    {'action': 'Idle'}, machine)
                self.assertIn('UNIT=0 LOGO_EFFECT=', program.script)
                self.assertNotIn(display_name, program.script)
                self.assertNotIn('UNIT=' + unit_name, program.script)

    def test_single_unit_fallback_requires_exclusive_controller(self):
        owner = {
            'mmu_leds primary': {'exit_leds': 'neopixel:diagnostic (1-4)'},
            'mmu_leds ghost': {'entry_leds': 'neopixel:other (1)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        settings['mmu_machine'] = {}
        machine = {'num_units': 1, 'unit_0': {'name': 'Display Name'}}
        state = SimpleNamespace(
            ready=True, epoch=42,
            objects=(TARGET, 'mmu_machine', 'mmu_leds primary',
                     'mmu_leds ghost'),
            settings=settings, status={'mmu_machine': machine})
        self.assertEqual(approved_integrations(state, ()), ())
        with self.assertRaisesRegex(ValueError, 'ownership_ambiguous'):
            compile_mmu_led_pulse(
                row, snap, physical, settings,
                {'mmu_leds primary': {
                    'enabled': True, 'animation': True, 'exit': 4}},
                {'action': 'Idle'}, machine)

    def test_multimachine_display_names_never_guess_numeric_indices(self):
        owner = {
            'mmu_leds north': {'exit_leds': 'neopixel:diagnostic (1-2)'},
            'mmu_leds south': {'entry_leds': 'neopixel:diagnostic (3-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        settings['mmu_machine'] = {}
        machine = {'num_units': 2,
                   'unit_0': {'name': 'North MMU'},
                   'unit_1': {'name': 'South MMU'}}
        state = SimpleNamespace(
            ready=True, epoch=42,
            objects=(TARGET, 'mmu_machine', 'mmu_leds north',
                     'mmu_leds south'),
            settings=settings, status={'mmu_machine': machine})
        self.assertEqual(approved_integrations(state, ()), ())
        with self.assertRaises(ValueError):
            compile_mmu_led_pulse(
                row, snap, physical, settings,
                {'mmu_leds north': {
                    'enabled': True, 'animation': True, 'exit': 2},
                 'mmu_leds south': {
                    'enabled': True, 'animation': True, 'entry': 2}},
                {'action': 'Idle'}, machine)

    def test_machine_config_order_and_live_display_names_coexist(self):
        owner = {
            'mmu_leds first': {'exit_leds': 'neopixel:diagnostic (1-2)'},
            'mmu_leds second': {'status_leds': 'neopixel:diagnostic (3-4)'}}
        row, snap, physical, settings = fixture(extra_settings=owner)
        settings['mmu_machine'] = {'units': ['second', 'first']}
        machine = {'num_units': 2,
                   'unit_0': {'name': 'Another Feeder'},
                   'unit_1': {'name': 'OpenEYE MMU'}}
        status = {
            'mmu_leds first': {'enabled': True, 'animation': True, 'exit': 2},
            'mmu_leds second': {'enabled': True, 'animation': True, 'status': 2}}
        program = compile_mmu_led_pulse(
            row, snap, physical, settings, status, {'action': 'Idle'},
            machine)
        self.assertIn('UNIT=1 EXIT_EFFECT=', program.script)
        self.assertIn('UNIT=0 STATUS_EFFECT=', program.script)

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
