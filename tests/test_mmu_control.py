import copy
from concurrent.futures import Future
import unittest
from unittest.mock import Mock, patch

from mmu_control import MMUState
from test_capabilities import snapshot, printer


def mmu_snapshot(**changes):
    data = snapshot()
    data['objects'] += ['mmu', 'mmu_machine']
    raw = dict(num_gates=4, enabled=True, gate=2, tool=2, action='Idle',
               print_state='ready', filament='Loaded', filament_pos=10,
               gate_status=[1, 1, 1, 0], ttg_map=[0, 1, 2, 3],
               gate_color_rgb=[[1, 0, 0], [1, 1, 1], [0, 0, 1], [1, 1, 0]],
               gate_material=['PLA', 'PLA', 'PLA', 'PETG'],
               gate_spool_id=[101, 102, 104, -1],
               sensors={'toolhead': True, 'extruder': False, 'mmu_shared_exit': None},
               sync_drive=False, bowden_progress=-1)
    raw.update(endless_spool_enabled=0, endless_spool_groups=[0, 1, 2, 3],
               gate_color=['ff0000', 'ffffff', '0000ff', 'ffff00'],
               spoolman_support='push', gate_temperature=[205, 210, 215, 230])
    raw.update(changes)
    data['status']['mmu'] = raw
    return data


def hardware_status(selector='ServoSelector', always=False):
    return {'num_units': 1, 'num_gates': 4,
            'unit_0': {'name': 'pico', 'display_name': 'Pico MMU', 'num_gates': 4,
                       'first_gate': 0, 'selector_type': selector,
                       'filament_always_gripped': always, 'is_homed': False}}


def add_motor_status(data):
    data['settings']['mmu_unit pico'] = {'gear_stepper': 'gear', 'selector_stepper': 'selector'}
    data['status']['stepper_enable'] = {'steppers': {
        'mmu_stepper gear': True, 'mmu_stepper selector': True, 'stepper_x': True}}


def add_led_status(data, unit_name='pico', num_gates=4):
    name = 'mmu_leds ' + unit_name
    data['objects'].append(name)
    data['status'][name] = dict(num_gates=num_gates, exit=num_gates, entry=0,
                                status=1, logo=0, enabled=True, animation=False,
                                exit_effect='gate_status')
    return name


def add_multiple_units(data):
    machine = hardware_status()
    machine['num_units'] = 2
    machine['unit_0']['num_gates'] = 2
    machine['unit_1'] = dict(machine['unit_0'], name='second', display_name='Second MMU', first_gate=2)
    data['status']['mmu_machine'] = machine


class MMUControlTests(unittest.TestCase):
    def make(self, **changes):
        data = mmu_snapshot(**changes)
        p = printer(data)
        p.subscription.responses_since.return_value = (0, ())
        p.subscription.request.return_value = Future()
        return p, data, p.mmu_session

    def test_control_without_optional_home_metadata_preserves_dispatch_guards(self):
        for colors in (None, [], [[1, 0, 0]], 'invalid'):
            p, data, session = self.make(gate_color_rgb=colors)
            self.assertIsNone(p.mmu)
            op = session.prepare('unload', gate=2)
            session.start(op)
            guard = p.subscription.request.call_args.kwargs['guard']
            self.assertTrue(guard())
            data['status']['print_stats']['state'] = 'printing'
            self.assertFalse(guard())

    def test_missing_home_metadata_does_not_relax_physical_state_requirements(self):
        for changes in ({'enabled': None}, {'action': 'Loading'}, {'filament_pos': None},
                        {'filament': 'unknown'}, {'num_gates': 0}):
            p, data, session = self.make(gate_color_rgb=[], **changes)
            with self.assertRaises(ValueError):
                session.prepare('unload', gate=2)
            p.subscription.request.assert_not_called()

    def make_hardware(self, selector_type='ServoSelector', always=False, **changes):
        fields = dict(unit=0, is_homed=True, selector={'grip': 'Released'},
                      filament='Unloaded', filament_pos=0)
        fields.update(changes)
        p, data, s = self.make(**fields)
        data['status']['mmu_machine'] = hardware_status(selector_type, always)
        return p, data, s

    def test_led_commands_scope_to_active_unit_and_whitelist_modes(self):
        for action, kwargs, argument in (
                ('led_enable', {'enabled': False}, 'ENABLE=0'),
                ('led_animation', {'enabled': True}, 'ANIMATION=1'),
                ('led_mode', {'values': ('filament_color',)}, 'EXIT_EFFECT=filament_color')):
            p, data, session = self.make_hardware()
            add_multiple_units(data)
            data['status']['mmu']['unit'] = 1
            add_led_status(data, 'second', 2)
            op = session.prepare(action, **kwargs)
            self.assertEqual(op.script, 'MMU_LED UNIT=1 ' + argument)
            p.subscription.request.assert_not_called()
        for value in ('custom', 'off\nM112', 1, None):
            _, data, session = self.make_hardware()
            add_led_status(data)
            with self.assertRaises(ValueError): session.prepare('led_mode', values=(value,))

    def test_led_missing_unknown_or_mismatched_telemetry_locks_actions(self):
        for case in ('missing', 'unknown', 'count', 'empty', 'unit'):
            p, data, session = self.make_hardware()
            name = add_led_status(data)
            if case == 'missing': del data['status'][name]
            elif case == 'unknown': data['status'][name]['enabled'] = 'True'
            elif case == 'count': data['status'][name]['num_gates'] = 3
            elif case == 'empty': data['status'][name].update(exit=0, status=0)
            else: data['status']['mmu']['unit'] = None
            with self.assertRaises(ValueError): session.prepare('led_enable', enabled=False)
            p.subscription.request.assert_not_called()

    def test_led_query_requires_actual_object_and_verifies_mode_and_unit(self):
        for case in ('success', 'unchanged', 'missing', 'wrong_unit', 'unrelated_change'):
            p, data, session = self.make_hardware()
            name = add_led_status(data)
            session.start(session.prepare('led_mode', values=('slicer_color',)))
            status = copy.deepcopy(data['status'])
            if case != 'unchanged': status[name]['exit_effect'] = 'slicer_color'
            if case == 'missing': del status[name]
            elif case == 'wrong_unit': status['mmu']['unit'] = -1
            elif case == 'unrelated_change': status[name]['animation'] = True
            self.complete(session, p, status)
            self.assertEqual(set(p.subscription.request.call_args.args[1]['objects']),
                             {'mmu', 'print_stats', 'mmu_machine', name})
            self.assertEqual(session.phase, 'complete' if case == 'success' else 'error')

    def test_led_flags_are_verified_not_just_dispatch_acknowledged(self):
        for action, field, value in (('led_enable', 'enabled', False), ('led_animation', 'animation', True)):
            for changed in (False, True):
                p, data, session = self.make_hardware()
                name = add_led_status(data)
                session.start(session.prepare(action, enabled=value))
                status = copy.deepcopy(data['status'])
                if changed: status[name][field] = value
                self.complete(session, p, status)
                self.assertEqual(session.phase, 'complete' if changed else 'error')

    def test_led_noop_no_exit_print_pause_and_queue_state_changes_are_guarded(self):
        p, data, session = self.make_hardware()
        name = add_led_status(data)
        for action, kwargs in (('led_enable', {'enabled': True}), ('led_animation', {'enabled': False}),
                               ('led_mode', {'values': ('gate_status',)})):
            with self.assertRaises(ValueError): session.prepare(action, **kwargs)
        data['status'][name]['exit'] = 0
        with self.assertRaises(ValueError): session.prepare('led_mode', values=('off',))
        for state in ('printing', 'paused'):
            data['status']['print_stats']['state'] = state
            with self.assertRaises(ValueError): session.prepare('led_enable', enabled=False)
        data['status']['print_stats']['state'] = 'standby'
        op = session.prepare('led_enable', enabled=False)
        session.start(op)
        data['status'][name]['animation'] = True
        self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_unit_select_uses_first_global_gate_without_sending_on_prepare(self):
        p, data, session = self.make_hardware(gate=0, tool=0)
        add_multiple_units(data)
        for index, gate in ((0, 0), (1, 2)):
            op = session.prepare('unit_select', values=(index,))
            self.assertEqual(op.script, 'MMU_SELECT GATE=%d' % gate)
            self.assertEqual(op.gate, gate)
        p.subscription.request.assert_not_called()

    def test_unit_select_requires_valid_partition_index_and_unloaded_offprint_state(self):
        for case in ('single', 'partition', 'loaded', 'printing', 'paused', 'index', 'boolean'):
            p, data, session = self.make_hardware()
            if case != 'single': add_multiple_units(data)
            index = 1
            if case == 'partition': data['status']['mmu_machine']['unit_1']['first_gate'] = 1
            elif case == 'loaded': data['status']['mmu'].update(filament='Loaded', filament_pos=10)
            elif case in ('printing', 'paused'): data['status']['print_stats']['state'] = case
            elif case == 'index': index = 2
            elif case == 'boolean': index = True
            with self.assertRaises(ValueError): session.prepare('unit_select', values=(index,))
            p.subscription.request.assert_not_called()

    def test_unit_completion_requires_queried_partition_active_unit_and_gate(self):
        for case in ('success', 'gate_only', 'unit_only', 'partition', 'missing'):
            p, data, session = self.make_hardware(gate=0, tool=0)
            add_multiple_units(data)
            session.start(session.prepare('unit_select', values=(1,)))
            status = copy.deepcopy(data['status'])
            status['mmu'].update(unit=1, gate=2)
            if case == 'gate_only': status['mmu']['unit'] = 0
            elif case == 'unit_only': status['mmu']['gate'] = 0
            elif case == 'partition': status['mmu_machine']['unit_1']['name'] = 'reconfigured'
            elif case == 'missing': del status['mmu_machine']
            self.complete(session, p, status)
            self.assertEqual(session.phase, 'complete' if case == 'success' else 'error')

    def test_unit_partition_change_invalidates_confirmation_and_queued_dispatch(self):
        p, data, session = self.make_hardware()
        add_multiple_units(data)
        op = session.prepare('unit_select', values=(1,))
        data['status']['mmu_machine']['unit_1']['name'] = 'changed'
        with self.assertRaises(ValueError): session.start(op)
        p.subscription.request.assert_not_called()
        session.start(session.prepare('unit_select', values=(1,)))
        data['status']['mmu_machine']['unit_1']['display_name'] = 'changed again'
        self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_enable_disable_use_native_command_and_allow_reenable_only_when_disabled(self):
        for current in (True, False):
            p, _, s = self.make(enabled=current, filament='Unloaded', filament_pos=0)
            op = s.prepare('enable', enabled=not current)
            self.assertEqual(op.script, 'MMU ENABLE=%d' % (not current))
            p.subscription.request.assert_not_called()
            s.start(op)
            self.assertTrue(p.subscription.request.call_args.kwargs['guard']())
        for fields in ({'enabled': None}, {'filament': 'Loaded', 'filament_pos': 10}, {'action': 'Loading'}):
            _, _, s = self.make(**fields)
            with self.assertRaises(ValueError): s.prepare('enable', enabled=False)

    def test_enable_result_checks_desired_flag_including_disabled_result(self):
        for current in (True, False):
            for changed in (True, False):
                p, data, s = self.make(enabled=current, filament='Unloaded', filament_pos=0)
                s.start(s.prepare('enable', enabled=not current))
                status = copy.deepcopy(data['status'])
                if changed: status['mmu']['enabled'] = not current
                self.complete(s, p, status)
                self.assertEqual(s.phase, 'complete' if changed else 'error')

    def test_enable_print_pause_epoch_and_unknown_desired_value_are_guarded(self):
        for ps in ('printing', 'paused'):
            _, data, s = self.make(enabled=False, filament='Unloaded', filament_pos=0)
            data['status']['print_stats']['state'] = ps
            with self.assertRaises(ValueError): s.prepare('enable', enabled=True)
        for value in (None, 1, '1', True):
            _, _, s = self.make(enabled=True, filament='Unloaded', filament_pos=0)
            with self.assertRaises(ValueError): s.prepare('enable', enabled=value)
        p, data, s = self.make(enabled=False, filament='Unloaded', filament_pos=0)
        op = s.prepare('enable', enabled=True)
        data['epoch'] += 1
        with self.assertRaises(ValueError): s.start(op)
        p.subscription.request.assert_not_called()

    def test_motors_off_uses_only_configured_mmu_drivers_and_global_native_release(self):
        p, data, s = self.make_hardware(selector_type='LinearServoSelector')
        add_motor_status(data)
        self.assertEqual(s.state.motors, (('mmu_stepper gear', True), ('mmu_stepper selector', True)))
        op = s.prepare('motors_off')
        self.assertEqual(op.script, 'MMU_MOTORS_OFF UNIT=ALL')
        self.assertNotIn('stepper_x', op.values)
        p.subscription.request.assert_not_called()

    def test_motors_missing_unknown_malformed_or_loaded_state_blocks_release(self):
        for case in ('missing', 'unknown', 'malformed', 'loaded', 'config'):
            p, data, s = self.make_hardware()
            add_motor_status(data)
            if case == 'missing': del data['status']['stepper_enable']
            elif case == 'unknown': data['status']['stepper_enable']['steppers']['mmu_stepper gear'] = None
            elif case == 'malformed': data['status']['stepper_enable'] = []
            elif case == 'loaded': data['status']['mmu'].update(filament='Loaded', filament_pos=10)
            else: data['settings']['mmu_unit pico']['gear_stepper'] = ''
            with self.assertRaises(ValueError): s.prepare('motors_off')
            p.subscription.request.assert_not_called()

    def test_motor_release_queries_and_verifies_drivers_not_only_unsync(self):
        for released in (True, False):
            p, data, s = self.make_hardware(selector_type='LinearServoSelector')
            add_motor_status(data)
            s.start(s.prepare('motors_off'))
            status = copy.deepcopy(data['status'])
            if released:
                status['stepper_enable']['steppers'].update({'mmu_stepper gear': False, 'mmu_stepper selector': False})
            self.complete(s, p, status)
            self.assertIn('stepper_enable', p.subscription.request.call_args.args[1]['objects'])
            self.assertEqual(s.phase, 'complete' if released else 'error')

    def test_motors_queue_guard_rejects_configuration_or_driver_changes(self):
        for change in ('driver', 'config'):
            p, data, s = self.make_hardware()
            add_motor_status(data)
            s.start(s.prepare('motors_off'))
            if change == 'driver': data['status']['stepper_enable']['steppers']['mmu_stepper gear'] = False
            else: data['settings']['mmu_unit pico']['gear_stepper'] = 'other'
            self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_hardware_partition_and_live_grip_homing_are_separate_from_static_data(self):
        _, _, s = self.make_hardware(selector_type='LinearServoSelector')
        self.assertTrue(s.state.homed)  # Static unit is deliberately not homed.
        self.assertFalse(s.state.grip)
        self.assertEqual(s.state.active_unit.name, 'Pico MMU')
        _, _, s = self.make_hardware(selector={'servo': 'Down'})
        self.assertTrue(s.state.grip)

    def test_malformed_hardware_partition_and_grip_are_unknown(self):
        for fields in ({'num_units': True}, {'num_units': 2}, {'num_gates': 5},
                       {'unit_0': {'first_gate': 1, 'num_gates': 4}},
                       {'unit_0': []}):
            _, data, s = self.make_hardware()
            data['status']['mmu_machine'].update(fields)
            self.assertEqual(s.state.units, ())
            with self.assertRaises(ValueError): s.prepare('grip')
        _, _, s = self.make_hardware(selector={'grip': [], 'servo': {}})
        self.assertIsNone(s.state.grip)
        with self.assertRaises(ValueError): s.prepare('grip')

    def test_home_and_check_all_have_explicit_targets(self):
        p, _, s = self.make_hardware(selector_type='LinearServoSelector')
        op = s.prepare('home_selector')
        self.assertEqual(op.script, 'MMU_HOME UNIT=0 TOOL=2')
        self.assertEqual(op.tool, 2)
        self.assertEqual(s.prepare('check_all').script, 'MMU_CHECK_GATE ALL=1')
        p.subscription.request.assert_not_called()
        _, _, s = self.make_hardware()
        with self.assertRaises(ValueError): s.prepare('home_selector')
        _, _, s = self.make_hardware(gate=-2, tool=-2)
        with self.assertRaises(ValueError): s.prepare('check_all')

    def test_grip_release_capability_and_loaded_filament_guards(self):
        for kind in ('ServoSelector', 'RotarySelector', 'LinearServoSelector', 'LinearMGServoSelector'):
            _, _, s = self.make_hardware(selector_type=kind)
            self.assertEqual(s.prepare('grip').script, 'MMU_GRIP')
            self.assertEqual(s.prepare('release').script, 'MMU_RELEASE')
        for fields in ({'always': True}, {'always': None}, {'selector_type': 'VirtualSelector'},
                       {'filament': 'Loaded', 'filament_pos': 10}, {'unit': 1}, {'gate': -2}):
            _, _, s = self.make_hardware(**fields)
            with self.assertRaises(ValueError): s.prepare('release')

    def test_gear_sync_requires_loaded_active_unit_and_allows_no_unsafe_unsync(self):
        _, _, s = self.make_hardware(filament='Loaded', filament_pos=10)
        self.assertEqual(s.prepare('sync_on').script, 'MMU_SYNC_GEAR_MOTOR SYNC=1')
        self.assertEqual(s.prepare('sync_off').script, 'MMU_SYNC_GEAR_MOTOR SYNC=0')
        for fields in ({}, {'always': True, 'filament': 'Loaded', 'filament_pos': 10},
                       {'always': None, 'filament': 'Loaded', 'filament_pos': 10},
                       {'unit': None, 'filament': 'Loaded', 'filament_pos': 10}):
            _, _, s = self.make_hardware(**fields)
            with self.assertRaises(ValueError): s.prepare('sync_off')

    def test_maintenance_confirmation_guard_rejects_changed_hardware_and_current_gate(self):
        for field in ('hardware', 'gate', 'grip'):
            p, data, s = self.make_hardware()
            s.start(s.prepare('grip'))
            if field == 'hardware': data['status']['mmu_machine']['unit_0']['selector_type'] = 'VirtualSelector'
            elif field == 'gate': data['status']['mmu']['gate'] = 1
            else: data['status']['mmu']['selector']['grip'] = 'Gripped'
            self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_maintenance_completion_checks_each_live_postcondition(self):
        for action in ('grip', 'release', 'home_selector', 'check_all', 'sync_on', 'sync_off'):
            for matches in (True, False):
                fields = dict(selector={'grip': 'Gripped' if action == 'release' else 'Released'},
                              is_homed=action != 'home_selector', gate_status=[-1]*4, sync_drive=action == 'sync_off')
                if action.startswith('sync_'): fields.update(filament='Loaded', filament_pos=10)
                p, data, s = self.make_hardware(selector_type='LinearServoSelector', **fields)
                s.start(s.prepare(action))
                status = copy.deepcopy(data['status'])
                if matches:
                    if action in ('grip', 'release'): status['mmu']['selector'] = {'grip': 'Gripped' if action == 'grip' else 'Released'}
                    elif action == 'home_selector': status['mmu']['is_homed'] = True
                    elif action == 'check_all': status['mmu']['gate_status'] = [0, 1, 2, 1]
                    else: status['mmu']['sync_drive'] = action == 'sync_on'
                self.complete(s, p, status)
                with self.subTest(action=action, matches=matches):
                    self.assertEqual(s.phase, 'complete' if matches else 'error')

    def test_unhomed_linear_selector_cannot_grip_or_change_drive_sync(self):
        for homed in (False, None):
            _, _, s = self.make_hardware(selector_type='LinearServoSelector', is_homed=homed)
            with self.assertRaises(ValueError): s.prepare('grip')
            _, _, s = self.make_hardware(selector_type='LinearServoSelector', is_homed=homed,
                                         filament='Loaded', filament_pos=10)
            with self.assertRaises(ValueError): s.prepare('sync_on')

    def test_grip_query_with_changed_hardware_does_not_confirm_success(self):
        p, data, s = self.make_hardware()
        s.start(s.prepare('grip'))
        status = copy.deepcopy(data['status'])
        status['mmu']['selector']['grip'] = 'Gripped'
        status['mmu_machine']['unit_0']['selector_type'] = 'VirtualSelector'
        self.complete(s, p, status)
        self.assertEqual(s.phase, 'error')

    def test_multiple_units_keep_global_gate_target_and_reject_ambiguous_home(self):
        _, data, s = self.make_hardware(unit=1)
        machine = hardware_status()
        machine['num_units'] = 2
        machine['unit_0']['num_gates'] = 2
        machine['unit_1'] = dict(machine['unit_0'], name='second', display_name='Second MMU', first_gate=2)
        data['status']['mmu_machine'] = machine
        self.assertEqual(s.state.active_unit.name, 'Second MMU')
        op = s.prepare('grip')
        self.assertEqual(op.gate, 2)
        self.assertEqual(op.label, 'Grip G3')
        self.assertEqual(op.values[0], 1)
        with self.assertRaises(ValueError): s.prepare('home_selector')
        data['status']['mmu']['gate'] = 0
        with self.assertRaises(ValueError): s.prepare('grip')

    def test_grip_result_at_other_gate_and_maintenance_during_print_are_rejected(self):
        p, data, s = self.make_hardware()
        s.start(s.prepare('grip'))
        status = copy.deepcopy(data['status'])
        status['mmu'].update(gate=1, selector={'grip': 'Gripped'})
        self.complete(s, p, status)
        self.assertEqual(s.phase, 'error')
        for state in ('printing', 'paused'):
            _, data, s = self.make_hardware()
            data['status']['print_stats']['state'] = state
            for action in ('grip', 'release', 'check_all', 'home_selector'):
                with self.assertRaises(ValueError): s.prepare(action)

    def test_missing_and_malformed_fields_stay_unknown(self):
        data = mmu_snapshot()
        for key in ('enabled', 'tool', 'action', 'print_state', 'sensors', 'sync_drive'):
            data['status']['mmu'].pop(key)
        m = MMUState.from_snapshot(data)
        self.assertIsNone(m.enabled)
        self.assertIsNone(m.tool)
        self.assertIsNone(m.locked)
        self.assertTrue(m.busy)
        self.assertEqual(m.sensors, ())
        self.assertIsNone(m.sync_drive)
        for value in (False, '4', 0, 257):
            data['status']['mmu']['num_gates'] = value
            self.assertIsNone(MMUState.from_snapshot(data))

    def test_position_and_sensor_truth_are_distinct(self):
        m = MMUState.from_snapshot(mmu_snapshot(filament_pos=3, bowden_progress=68.2))
        self.assertEqual(m.filament, 'unknown')
        self.assertEqual(m.bowden_progress, 68)
        self.assertEqual(dict(m.sensors), {'toolhead': True, 'extruder': False, 'mmu_shared_exit': None})
        for value in (-1, 101, float('nan'), True, '68'):
            self.assertIsNone(MMUState.from_snapshot(mmu_snapshot(bowden_progress=value)).bowden_progress)

    def test_paused_unlocked_ignores_deprecated_is_locked_alias(self):
        m = MMUState.from_snapshot(mmu_snapshot(print_state='paused', is_locked=True))
        self.assertFalse(m.locked)

    def test_many_tools_can_map_to_one_gate(self):
        m = MMUState.from_snapshot(mmu_snapshot(ttg_map=[2, 2, 2, 3]))
        self.assertEqual(m.tools_for_gate(2), (0, 1, 2))

    def test_map_bulk_save_preserves_many_to_one_and_never_moves(self):
        p, _, s = self.make()
        op = s.prepare('map', values=[2, 2, 2, 0])
        self.assertEqual(op.script, 'MMU_TTG_MAP MAP=2,2,2,0')
        self.assertEqual(op.values, (2, 2, 2, 0))
        p.subscription.request.assert_not_called()

    def test_map_rejects_incomplete_invalid_or_unknown_mapping(self):
        for values in ([], [0, 1], [0, 1, 2, 4], [0, 1, 2, -1],
                       [0, 1, 2, True], [0, 1, 2, '3']):
            _, _, s = self.make()
            with self.subTest(values=values), self.assertRaises(ValueError):
                s.prepare('map', values=values)
        _, _, s = self.make(ttg_map=[0, 1])
        with self.assertRaises(ValueError): s.prepare('map', values=[0, 1, 2, 3])

    def test_map_print_pause_busy_and_external_map_change_are_guarded(self):
        for state in ('printing', 'paused'):
            p, data, s = self.make()
            data['status']['print_stats']['state'] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                s.prepare('map', values=[2]*4)
        p, data, s = self.make()
        op = s.prepare('map', values=[2]*4)
        data['status']['mmu']['ttg_map'] = [1]*4
        with self.assertRaises(ValueError): s.start(op)
        p.subscription.request.assert_not_called()
        _, _, s = self.make(action='Loading')
        with self.assertRaises(ValueError): s.prepare('map', values=[2]*4)

    def test_map_completion_checks_entire_result_not_rpc_acceptance(self):
        for matches in (True, False):
            p, data, s = self.make()
            s.start(s.prepare('map', values=[2]*4))
            status = copy.deepcopy(data['status'])
            if matches: status['mmu']['ttg_map'] = [2]*4
            self.complete(s, p, status)
            self.assertEqual(s.phase, 'complete' if matches else 'error')

    def test_endless_state_accepts_integer_switch_and_preserves_group_ids(self):
        m = MMUState.from_snapshot(mmu_snapshot(endless_spool_enabled=1,
                                               endless_spool_groups=[10, 10, 99, 99]))
        self.assertTrue(m.endless_enabled)
        self.assertEqual(m.endless_groups, (10, 10, 99, 99))
        for value in ('1', 2, None):
            self.assertIsNone(MMUState.from_snapshot(mmu_snapshot(endless_spool_enabled=value)).endless_enabled)
        data = mmu_snapshot(endless_spool=1)
        del data['status']['mmu']['endless_spool_enabled']
        self.assertTrue(MMUState.from_snapshot(data).endless_enabled)

    def test_endless_saves_whole_draft_in_single_non_motion_command(self):
        p, _, s = self.make()
        op = s.prepare('endless', enabled=True, values=[99, 99, 2, 3])
        self.assertEqual(op.script, 'MMU_ENDLESS_SPOOL ENABLE=1 GROUPS=99,99,2,3')
        p.subscription.request.assert_not_called()
        s.start(op)
        self.assertTrue(p.subscription.request.call_args.kwargs['guard']())

    def test_endless_rejects_invalid_draft_before_partial_enable_is_possible(self):
        for values in ([0], [0, 1, 2, -1], [0, 1, 2, True], [0, 1, 2, '3']):
            p, _, s = self.make()
            with self.subTest(values=values), self.assertRaises(ValueError):
                s.prepare('endless', enabled=True, values=values)
            p.subscription.request.assert_not_called()
        for fields in ({'endless_spool_enabled': None}, {'endless_spool_groups': [0, 1]},
                       {'endless_spool_groups': [0, 1, 2, -1]}):
            _, _, s = self.make(**fields)
            with self.assertRaises(ValueError): s.prepare('endless', enabled=True, values=[0]*4)
        _, _, s = self.make()
        with self.assertRaises(ValueError): s.prepare('endless', enabled=1, values=[0]*4)

    def test_endless_confirmation_guard_rejects_group_material_color_changes(self):
        for field, values in (('endless_spool_groups', [2]*4),
                              ('gate_material', ['ABS']*4), ('gate_color', ['000000']*4)):
            p, data, s = self.make()
            s.start(s.prepare('endless', enabled=True, values=[0]*4))
            data['status']['mmu'][field] = values
            self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_endless_completion_requires_both_enabled_and_group_result(self):
        for result in ('both', 'groups', 'enabled'):
            p, data, s = self.make()
            s.start(s.prepare('endless', enabled=True, values=[0]*4))
            status = copy.deepcopy(data['status'])
            if result != 'groups': status['mmu']['endless_spool_enabled'] = 1
            if result != 'enabled': status['mmu']['endless_spool_groups'] = [0]*4
            self.complete(s, p, status)
            self.assertEqual(s.phase, 'complete' if result == 'both' else 'error')

    def test_spool_assignment_and_clear_preserve_temperature_and_global_indices(self):
        for mode in ('off', 'readonly', 'push'):
            p, _, s = self.make(spoolman_support=mode)
            op = s.prepare('spool', gate=1, values=(501,))
            self.assertEqual(op.script, 'MMU_GATE_MAP GATE=1 SPOOLID=501 TEMP=210')
            self.assertIn('G2', op.label)
            self.assertEqual(op.expected_spool_ids, (101, 501, 104, -1))
            self.assertEqual(s.prepare('spool', gate=1, values=(-1,)).script,
                             'MMU_GATE_MAP GATE=1 SPOOLID=-1 TEMP=210')
            p.subscription.request.assert_not_called()

    def test_spool_accepts_exact_whole_temperature_reported_as_float(self):
        _, _, s = self.make(gate_temperature=[200.0]*4)
        self.assertEqual(s.prepare('spool', gate=0, values=(501,)).script,
                         'MMU_GATE_MAP GATE=0 SPOOLID=501 TEMP=200')

    def test_spool_invalid_id_gate_mode_and_metadata_never_enable_assignment(self):
        for sid in (0, -2, True, '45', None, 1.5):
            _, _, s = self.make()
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                s.prepare('spool', gate=0, values=(sid,))
        for gate in (-1, 4, None, True):
            _, _, s = self.make()
            with self.assertRaises(ValueError): s.prepare('spool', gate=gate, values=(1,))
        for fields in ({'spoolman_support': 'pull'}, {'spoolman_support': None},
                       {'spoolman_support': 'unexpected'}, {'gate_spool_id': [101]},
                       {'gate_temperature': [0]*4}, {'gate_temperature': [205.5]*4},
                       {'gate_temperature': []}):
            p, _, s = self.make(**fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                s.prepare('spool', gate=0, values=(501,))
            p.subscription.request.assert_not_called()
        p, data, s = self.make()
        del data['status']['mmu']['spoolman_support']
        with self.assertRaises(ValueError): s.prepare('spool', gate=0, values=(501,))

    def test_spool_confirmation_and_queue_guard_revalidate_ids_mode_temperature(self):
        for field, value in (('gate_spool_id', [5]*4), ('spoolman_support', 'pull'),
                             ('gate_temperature', [230]*4)):
            p, data, s = self.make()
            op = s.prepare('spool', gate=0, values=(501,))
            data['status']['mmu'][field] = value
            with self.assertRaises(ValueError): s.start(op)
            p.subscription.request.assert_not_called()
            p, data, s = self.make()
            s.start(s.prepare('spool', gate=0, values=(501,)))
            data['status']['mmu'][field] = value
            self.assertFalse(p.subscription.request.call_args.kwargs['guard']())

    def test_spool_result_checks_assignment_and_duplicate_removal(self):
        for ids, success in (([102, -1, 104, -1], True), ([102, 102, 104, -1], False),
                             ([101, 102, 104, -1], False), ([102, -1, -1, -1], False)):
            p, data, s = self.make()
            s.start(s.prepare('spool', gate=0, values=(102,)))
            status = copy.deepcopy(data['status'])
            status['mmu']['gate_spool_id'] = ids
            self.complete(s, p, status)
            self.assertEqual(s.phase, 'complete' if success else 'error')

    def test_spool_clear_verifies_other_gate_assignments_are_unchanged(self):
        p, data, s = self.make()
        s.start(s.prepare('spool', gate=0, values=(-1,)))
        status = copy.deepcopy(data['status'])
        status['mmu']['gate_spool_id'][0] = -1
        self.complete(s, p, status)
        self.assertEqual(s.phase, 'complete')

    def test_spool_printing_pause_busy_disabled_and_pending_are_locked(self):
        for ps in ('printing', 'paused'):
            p, data, s = self.make()
            data['status']['print_stats']['state'] = ps
            with self.assertRaises(ValueError): s.prepare('spool', gate=0, values=(501,))
        for fields in ({'action': 'Loading'}, {'enabled': False}):
            _, _, s = self.make(**fields)
            with self.assertRaises(ValueError): s.prepare('spool', gate=0, values=(501,))
        _, _, s = self.make()
        s.start(s.prepare('spool', gate=0, values=(501,)))
        with self.assertRaises(ValueError): s.prepare('spool', gate=1, values=(502,))

    def test_commands_use_zero_based_gates_and_explicit_eject(self):
        for action, script in [('unload', 'MMU_UNLOAD'), ('eject', 'MMU_EJECT GATE=2 FORCE=1')]:
            p, _, session = self.make()
            op = session.prepare(action, gate=2)
            self.assertEqual(op.script, script)
            self.assertIn('G3', op.label)
            p.subscription.request.assert_not_called()

    def test_empty_filament_actions_and_bypass(self):
        p, _, s = self.make(filament='Unloaded', filament_pos=0)
        for action, script in [('select', 'MMU_SELECT GATE=1'), ('preload', 'MMU_PRELOAD GATE=1'), ('check', 'MMU_CHECK_GATE GATE=1')]:
            self.assertEqual(s.prepare(action, gate=1).script, script)
        self.assertEqual(s.prepare('load', gate=2).script, 'MMU_LOAD')
        self.assertEqual(s.prepare('bypass').script, 'MMU_SELECT BYPASS=1')
        with self.assertRaises(ValueError): s.prepare('load', gate=1)
        with self.assertRaises(ValueError): s.prepare('unload', gate=2)
        with self.assertRaises(ValueError): s.prepare('load_extruder')

    def test_change_uses_tool_mapping_and_preserves_current_mapped_tool(self):
        _, _, s = self.make(ttg_map=[1, 1, 2, 3])
        op = s.prepare('change', gate=1)
        self.assertEqual(op.tool, 0)
        self.assertEqual(op.script, 'MMU_CHANGE_TOOL TOOL=0 STANDALONE=1')
        _, _, s = self.make(ttg_map=[1, 1, 1, 3])
        self.assertEqual(s.prepare('change', gate=1).tool, 2)

    def test_motion_is_locked_for_unknown_busy_disabled_and_wrong_target(self):
        for fields in ({'enabled': False}, {'enabled': None}, {'action': 'Loading'},
                       {'action': None}, {'filament': 'Unknown'}, {'print_state': 'pause_locked'}):
            _, _, s = self.make(**fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                s.prepare('unload', gate=2)
        _, _, s = self.make()
        for action, gate in [('unload', 1), ('eject', 1), ('select', 0), ('change', 3), ('unload', True), ('unload', -1), ('unload', 4)]:
            with self.subTest(action=action, gate=gate), self.assertRaises(ValueError):
                s.prepare(action, gate=gate)

    def test_paused_print_allows_recovery_but_not_routine_movement(self):
        p, data, s = self.make(print_state='pause_locked', filament='Unknown', filament_pos=-1)
        data['status']['print_stats']['state'] = 'paused'
        self.assertEqual(s.prepare('recover').script, 'MMU_RECOVER')
        self.assertEqual(s.prepare('unlock').script, 'MMU_UNLOCK')
        op = s.prepare('manual', gate=2, tool=2, loaded=False)
        self.assertEqual(op.script, 'MMU_RECOVER TOOL=2 GATE=2 LOADED=0')
        with self.assertRaises(ValueError): s.prepare('resume')
        with self.assertRaises(ValueError): s.prepare('change', gate=1)
        data['status']['mmu'].update(print_state='paused', filament='Loaded', filament_pos=10)
        self.assertEqual(s.prepare('resume').script, 'RESUME')
        data['status']['print_stats']['state'] = 'printing'
        with self.assertRaises(ValueError): s.prepare('recover')

    def test_confirmation_revalidates_external_changes_and_epoch(self):
        p, data, s = self.make()
        op = s.prepare('unload', gate=2)
        data['status']['mmu']['gate'] = 1
        with self.assertRaises(ValueError): s.start(op)
        p.subscription.request.assert_not_called()
        data['status']['mmu']['gate'] = 2
        data['epoch'] = 2
        with self.assertRaises(ValueError): s.start(op)

    def test_queue_guard_rejects_state_change_without_mutating_session(self):
        p, data, s = self.make()
        s.start(s.prepare('unload', gate=2))
        pending = s.pending
        guard = p.subscription.request.call_args.kwargs['guard']
        self.assertTrue(guard())
        self.assertIs(s.pending, pending)
        data['status']['print_stats']['state'] = 'printing'
        self.assertFalse(guard())
        self.assertIs(s.pending, pending)

    def test_duplicate_submission_is_rejected(self):
        p, _, s = self.make()
        op = s.prepare('unload', gate=2)
        s.start(op)
        with self.assertRaises(ValueError): s.start(op)
        self.assertEqual(p.subscription.request.call_count, 1)

    def test_command_completion_requires_actual_result_query(self):
        p, data, s = self.make()
        s.start(s.prepare('unload', gate=2))
        command = s.pending
        s.update()
        self.assertEqual(s.phase, 'running')
        query = Future()
        p.subscription.request.return_value = query
        command.set_result('ok')
        s.update()
        self.assertEqual(s.phase, 'confirming')
        self.assertIs(s.pending, query)
        status = copy.deepcopy(data['status'])
        status['mmu'].update(filament='Unloaded', filament_pos=0)
        query.set_result({'status': status})
        s.update()
        self.assertEqual(s.phase, 'complete')
        self.assertIsNone(s.pending)

    def test_accepted_noop_is_not_reported_as_completed(self):
        p, data, s = self.make()
        s.start(s.prepare('unload', gate=2))
        s.pending.set_result('ok')
        query = Future()
        p.subscription.request.return_value = query
        s.update()
        query.set_result({'status': data['status']})
        s.update()
        self.assertEqual(s.phase, 'error')
        self.assertIn('unconfirmed', s.message)

    def test_error_disconnect_timeout_never_replay(self):
        for case in ('error', 'disconnect', 'timeout', 'gcode'):
            p, data, s = self.make()
            s.start(s.prepare('unload', gate=2))
            if case == 'error': s.pending.set_exception(RuntimeError('failed'))
            elif case == 'disconnect': data['epoch'] += 1
            elif case == 'gcode': p.subscription.responses_since.return_value = (1, ('!! no filament',))
            with patch('mmu_control.time.monotonic', return_value=s.started + (301 if case == 'timeout' else 1)):
                s.update()
            self.assertEqual(s.phase, 'error')
            self.assertEqual(p.subscription.request.call_count, 1)
            self.assertIsNone(s.pending)

    def test_independent_error_cursor_does_not_consume_other_sessions(self):
        p, _, s = self.make()
        p.pop_gcode_response = Mock()
        s.start(s.prepare('unload', gate=2))
        s.update()
        p.pop_gcode_response.assert_not_called()

    def test_other_calibration_session_blocks_mmu(self):
        p, _, s = self.make()
        p.bed_mesh.pending = Future()
        with self.assertRaises(ValueError): s.prepare('unload', gate=2)

    def test_malformed_lock_and_filament_position_do_not_enable_motion(self):
        _, _, s = self.make(print_state='garbage')
        with self.assertRaises(ValueError): s.prepare('unload', gate=2)
        for value in ('10', True, float('nan')):
            _, _, s = self.make(filament_pos=value)
            with self.assertRaises(ValueError): s.prepare('unload', gate=2)

    def test_failed_result_requires_acknowledgement_before_new_operation(self):
        _, _, s = self.make()
        s.phase = 'error'
        with self.assertRaisesRegex(ValueError, 'Acknowledge'):
            s.prepare('unload', gate=2)

    def complete(self, session, p, status):
        session.pending.set_result('ok')
        query = Future()
        p.subscription.request.return_value = query
        session.update()
        query.set_result({'status': status})
        session.update()

    def test_bypass_and_extruder_only_completion_use_actual_state(self):
        p, data, s = self.make(filament='Unloaded', filament_pos=0)
        s.start(s.prepare('bypass'))
        status = copy.deepcopy(data['status'])
        status['mmu'].update(gate=-2, tool=-2)
        self.complete(s, p, status)
        self.assertEqual(s.phase, 'complete')
        p, data, s = self.make(gate=-2, tool=-2, filament='Unloaded', filament_pos=0)
        op = s.prepare('load_extruder')
        self.assertEqual(op.script, 'MMU_LOAD EXTRUDER_ONLY=1')
        s.start(op)
        status = copy.deepcopy(data['status'])
        status['mmu'].update(filament='Loaded', filament_pos=10)
        self.complete(s, p, status)
        self.assertEqual(s.phase, 'complete')

    def test_auto_manual_unlock_and_resume_are_separate_verified_results(self):
        for action in ('recover', 'manual', 'unlock', 'resume'):
            p, data, s = self.make(print_state='pause_locked', filament='Unknown', filament_pos=-1)
            data['status']['print_stats']['state'] = 'paused'
            if action == 'resume':
                data['status']['mmu'].update(print_state='paused', filament='Loaded', filament_pos=10)
            op = s.prepare(action, gate=2, tool=2, loaded=False) if action == 'manual' else s.prepare(action)
            s.start(op)
            status = copy.deepcopy(data['status'])
            if action in ('recover', 'manual'):
                status['mmu'].update(filament='Unloaded', filament_pos=0)
            elif action == 'unlock':
                status['mmu']['print_state'] = 'paused'
            else:
                status['mmu']['print_state'] = 'printing'
                status['print_stats']['state'] = 'printing'
            self.complete(s, p, status)
            with self.subTest(action=action):
                self.assertEqual(s.phase, 'complete')
                scripts = [call.args[1]['script'] for call in p.subscription.request.call_args_list
                           if call.args[0] == 'printer.gcode.script']
                self.assertEqual(scripts, [op.script])
                if action != 'resume': self.assertNotIn('RESUME', scripts)

    def test_disabled_mmu_and_error_lock_at_result_never_report_success(self):
        for field in ('enabled', 'print_state'):
            p, data, s = self.make()
            s.start(s.prepare('unload', gate=2))
            status = copy.deepcopy(data['status'])
            status['mmu'].update(filament='Unloaded', filament_pos=0)
            status['mmu'][field] = False if field == 'enabled' else 'pause_locked'
            self.complete(s, p, status)
            self.assertEqual(s.phase, 'error')

    def test_mmu_pending_blocks_all_calibration_entry_points(self):
        from test_bed_mesh import data as mesh_data
        from test_probe_wizard import data as probe_data
        from test_screws_tilt import data as screws_data
        for source, name in ((mesh_data(), 'bed_mesh'), (probe_data(), 'probe_wizard'), (screws_data(), 'screws_tilt')):
            p = printer(source)
            p.mmu_session.pending = Future()
            with self.subTest(name=name), self.assertRaises(ValueError):
                getattr(p, name).start()
            p.subscription.request.assert_not_called()
            p.sendGCode.assert_not_called()
