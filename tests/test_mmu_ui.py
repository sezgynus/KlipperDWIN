from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from test_capabilities import display
from test_mmu_control import mmu_snapshot, hardware_status, add_motor_status, add_led_status, add_multiple_units


class MMUUITests(unittest.TestCase):
    def make(self, **changes):
        data = mmu_snapshot(**changes)
        view = display(data)
        view.lcd.DWIN_WIDTH = 272
        view.lcd.DWIN_HEIGHT = 480
        view.lcd.Line_Color = 0x3A6A
        view.get_encoder_state = Mock(return_value=view.ENCODER_DIFF_NO)
        view.pd.subscription.responses_since.return_value = (0, ())
        view.pd.subscription.request.return_value = Future()
        view.Enter_MMU_Menu()
        return view, data

    def test_menu_controls_work_without_optional_rgb_metadata(self):
        v, data = self.make(gate_color_rgb=[])
        self.assertIsNone(v.pd.mmu)
        self.assertEqual(v._mmu_selection, 1)
        v._mmu_open('gate')
        v._mmu_gate = 2
        v.Draw_MMU_Menu()
        items = v._mmu_items(v.pd.mmu_session.state)
        unload = next(i for i, item in enumerate(items) if item[0] == ('action', 'unload', 2))
        self.assertTrue(items[unload][3])
        self.press(v, unload + 1)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_selection, 1)
        v.pd.subscription.request.assert_not_called()
        self.press(v, 2)
        v.pd.subscription.request.assert_called_once()

    def press(self, view, selection):
        view._mmu_selection = selection
        view.get_encoder_state.return_value = view.ENCODER_DIFF_ENTER
        view._dispatch_input()

    def strings(self, view):
        return [c.args[-1] for c in view.lcd.draw_text.call_args_list]

    def make_hardware(self, selector_type='ServoSelector', always=False, **changes):
        fields = dict(unit=0, is_homed=True, selector={'grip': 'Released'},
                      filament='Unloaded', filament_pos=0)
        fields.update(changes)
        v, data = self.make(**fields)
        data['status']['mmu_machine'] = hardware_status(selector_type, always)
        return v, data

    def test_led_menu_is_capability_specific_and_browsing_sends_nothing(self):
        v, data = self.make_hardware()
        v._mmu_open('options')
        self.assertNotIn('LEDs', [i[1] for i in v._mmu_items(v.pd.mmu_session.state)])
        name = add_led_status(data)
        v.Draw_MMU_Menu()
        items = v._mmu_items(v.pd.mmu_session.state)
        self.press(v, next(i + 1 for i, item in enumerate(items) if item[1] == 'LEDs'))
        self.assertEqual(v._mmu_page, 'leds')
        self.assertIn('Exit: gate_status', self.strings(v))
        v.pd.subscription.request.assert_not_called()
        data['status'][name]['exit'] = 0
        v.Draw_MMU_Menu()
        self.assertEqual(len(v._mmu_items(v.pd.mmu_session.state)), 2)

    def test_led_confirmation_cancel_and_single_dispatch(self):
        for selection, script in ((1, 'MMU_LED UNIT=0 ENABLE=0'),
                                  (2, 'MMU_LED UNIT=0 ANIMATION=1'),
                                  (3, 'MMU_LED UNIT=0 EXIT_EFFECT=off')):
            v, data = self.make_hardware()
            add_led_status(data)
            v._mmu_open('leds')
            self.press(v, selection)
            self.assertEqual(v._mmu_confirmation.script, script)
            self.assertEqual(v._mmu_selection, 1)
            self.press(v, 1)
            self.assertEqual(v._mmu_page, 'leds')
            v.pd.subscription.request.assert_not_called()
            self.press(v, selection)
            self.press(v, 2)
            self.assertEqual(v._mmu_page, 'status')
            v.pd.subscription.request.assert_called_once()

    def test_led_unknown_flags_and_external_changes_lock_dispatch(self):
        v, data = self.make_hardware()
        name = add_led_status(data)
        data['status'][name]['enabled'] = None
        v._mmu_open('leds')
        self.assertFalse(any(i[3] for i in v._mmu_items(v.pd.mmu_session.state)))
        self.press(v, 1)
        v.pd.subscription.request.assert_not_called()
        data['status'][name]['enabled'] = True
        v.Draw_MMU_Menu()
        self.press(v, 1)
        data['status'][name]['animation'] = True
        self.press(v, 2)
        v.pd.subscription.request.assert_not_called()

    def test_unit_browser_keeps_global_gate_numbers_and_requires_motion_confirmation(self):
        v, data = self.make_hardware(gate=0, tool=0)
        v._mmu_open('options')
        self.assertNotIn('Units', [i[1] for i in v._mmu_items(v.pd.mmu_session.state)])
        add_multiple_units(data)
        v.Draw_MMU_Menu()
        items = v._mmu_items(v.pd.mmu_session.state)
        self.press(v, next(i + 1 for i, item in enumerate(items) if item[1] == 'Units'))
        self.assertEqual(v._mmu_page, 'units')
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'unit')
        self.assertEqual(v._mmu_unit_view, 1)
        items = v._mmu_items(v.pd.mmu_session.state)
        self.assertEqual([i[0] for i in items[1:]], [('gate', 2), ('gate', 3)])
        v.pd.subscription.request.assert_not_called()
        self.press(v, 1)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_SELECT GATE=2')
        self.assertEqual(v._mmu_selection, 1)
        self.press(v, 1)
        v.pd.subscription.request.assert_not_called()
        self.press(v, 1)
        self.press(v, 2)
        v.pd.subscription.request.assert_called_once()

    def test_unit_browsing_during_print_remains_readonly(self):
        v, data = self.make_hardware()
        add_multiple_units(data)
        data['status']['print_stats']['state'] = 'printing'
        v._mmu_open('units')
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'unit')
        self.assertFalse(v._mmu_items(v.pd.mmu_session.state)[0][3])
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'gate')
        self.assertEqual(v._mmu_gate, 2)
        v.pd.subscription.request.assert_not_called()

    def test_unit_and_led_rows_and_confirmations_stay_inside_canvas(self):
        v, data = self.make_hardware()
        add_multiple_units(data)
        add_led_status(data, num_gates=2)
        for page, selection in (('units', 2), ('unit', 3), ('leds', 6)):
            v._mmu_unit_view = 1
            v._mmu_open(page)
            v._mmu_selection = selection
            v._mmu_canvas_page = None
            v.lcd.reset_mock()
            v.Draw_MMU_Menu()
            for call in v.lcd.draw_rectangle.call_args_list:
                _, _, x0, y0, x1, y1 = call.args
                self.assertTrue(0 <= x0 <= x1 < 272)
                self.assertTrue(0 <= y0 <= y1 < 480)
            for call in v.lcd.draw_text.call_args_list:
                self.assertTrue(0 <= call.args[5] < 272)
                self.assertTrue(0 <= call.args[6] < 480)
        v._mmu_open('unit')
        self.press(v, 1)
        self.assertIn('May home / move the selector', self.strings(v))

    def test_changed_unit_partition_blocks_stale_selection(self):
        v, data = self.make_hardware()
        add_multiple_units(data)
        v._mmu_unit_view = 1
        v._mmu_open('unit')
        data['status']['mmu_machine']['unit_0']['num_gates'] = 1
        data['status']['mmu_machine']['unit_1'].update(first_gate=1, num_gates=3)
        self.press(v, 1)
        v.pd.subscription.request.assert_not_called()
        self.assertIsNone(getattr(v, '_mmu_confirmation', None))
        self.assertIn('Menu changed', v._mmu_notice)

    def test_maintenance_hides_unsupported_selector_and_release(self):
        v, _ = self.make()
        v._mmu_open('maintenance')
        self.assertEqual([i[1] for i in v._mmu_items(v.pd.mmu_session.state)],
                         ['Check all gates', 'Extruder / bypass'])
        v, _ = self.make_hardware(always=True)
        v._mmu_open('maintenance')
        labels = [i[1] for i in v._mmu_items(v.pd.mmu_session.state)]
        self.assertIn('Grip', labels)
        self.assertNotIn('Release', labels)
        self.assertNotIn('Home selector', labels)

    def test_maintenance_navigation_is_readonly_home_has_cancel_first_confirmation(self):
        v, _ = self.make_hardware(selector_type='LinearServoSelector')
        v._mmu_open('manage')
        self.press(v, 5)
        self.assertEqual(v._mmu_page, 'maintenance')
        self.assertIn('Pico MMU', self.strings(v))
        v.pd.subscription.request.assert_not_called()
        self.press(v, 1)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_HOME UNIT=0 TOOL=2')
        self.assertEqual(v._mmu_selection, 1)
        self.press(v, 1)
        self.assertEqual(v._mmu_page, 'maintenance')
        v.pd.subscription.request.assert_not_called()

    def test_grip_and_check_all_confirm_exact_command_before_live_status(self):
        for selection, script in ((1, 'MMU_CHECK_GATE ALL=1'), (2, 'MMU_GRIP'), (3, 'MMU_RELEASE')):
            v, _ = self.make_hardware()
            v._mmu_open('maintenance')
            self.press(v, selection)
            self.assertEqual(v._mmu_confirmation.script, script)
            self.press(v, 2)
            self.assertEqual(v._mmu_page, 'status')
            v.pd.subscription.request.assert_called_once()

    def test_options_sync_is_guarded_and_capability_specific(self):
        v, _ = self.make()
        v._mmu_open('options')
        self.assertEqual([i[1] for i in v._mmu_items(v.pd.mmu_session.state)], ['Disable MMU', 'Sensors / status'])
        v, _ = self.make_hardware(always=True, filament='Loaded', filament_pos=10)
        v._mmu_open('options')
        self.assertNotIn('Gear sync OFF', [i[1] for i in v._mmu_items(v.pd.mmu_session.state)])
        v, _ = self.make_hardware(filament='Loaded', filament_pos=10)
        v._mmu_open('options')
        self.press(v, 2)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_SYNC_GEAR_MOTOR SYNC=1')

    def test_options_reenable_disabled_mmu_has_cancel_first_confirmation(self):
        v, _ = self.make(enabled=False, filament='Unloaded', filament_pos=0)
        v._mmu_open('options')
        self.assertIn('Enable MMU', self.strings(v))
        self.press(v, 1)
        self.assertEqual(v._mmu_selection, 1)
        self.assertEqual(v._mmu_confirmation.script, 'MMU ENABLE=1')
        self.press(v, 1)
        v.pd.subscription.request.assert_not_called()
        self.press(v, 1)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'status')
        v.pd.subscription.request.assert_called_once()

    def test_options_motor_release_hidden_without_driver_telemetry(self):
        v, data = self.make_hardware()
        v._mmu_open('options')
        self.assertNotIn('Release MMU motors', self.strings(v))
        add_motor_status(data)
        v.Draw_MMU_Menu()
        items = v._mmu_items(v.pd.mmu_session.state)
        row = next(i + 1 for i, item in enumerate(items) if item[0][1] == 'motors_off')
        self.press(v, row)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_MOTORS_OFF UNIT=ALL')
        self.assertIn('All MMU units; home may be lost.', self.strings(v))
        v.pd.subscription.request.assert_not_called()

    def test_maintenance_changed_capability_or_print_state_never_sends(self):
        for case in ('hardware', 'printing', 'epoch'):
            v, data = self.make_hardware()
            v._mmu_open('maintenance')
            self.press(v, 2)
            if case == 'hardware': data['status']['mmu_machine']['unit_0']['selector_type'] = 'VirtualSelector'
            elif case == 'printing': data['status']['print_stats']['state'] = 'printing'
            else: data['epoch'] += 1
            self.press(v, 2)
            v.pd.subscription.request.assert_not_called()

    def test_full_maintenance_rows_stay_inside_lcd(self):
        v, _ = self.make_hardware(selector_type='LinearServoSelector')
        v.lcd.reset_mock()
        v._mmu_open('maintenance')
        for c in v.lcd.draw_rectangle.call_args_list:
            _, _, x0, y0, x1, y1 = c.args
            self.assertTrue(0 <= x0 <= x1 < 272)
            self.assertTrue(0 <= y0 <= y1 < 480)

    def open_spool(self, v):
        v._mmu_gate = 0
        v._mmu_open('filament')
        self.press(v, 1)
        self.assertEqual(v._mmu_page, 'spool')

    def edit_spool(self, v):
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v.HMI_MMU_Menu()
        self.press(v, 1)

    def test_spool_metadata_color_and_encoder_draft_cancel(self):
        v, _ = self.make()
        self.open_spool(v)
        self.assertIn('Color: ff0000', self.strings(v))
        self.edit_spool(v)
        self.assertEqual(v._mmu_spool_draft, 102)
        v.pd.subscription.request.assert_not_called()
        self.press(v, 4)
        self.assertEqual(v._mmu_page, 'filament')
        self.press(v, 1)
        self.assertEqual(v._mmu_spool_draft, 101)

    def test_spool_save_confirm_warns_about_moving_id_and_sends_once(self):
        v, _ = self.make()
        self.open_spool(v)
        self.edit_spool(v)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_selection, 1)
        self.assertIn('Moves ID off: G2', self.strings(v))
        self.press(v, 1)
        self.assertEqual(v._mmu_spool_draft, 102)
        self.press(v, 2)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'status')
        v.pd.subscription.request.assert_called_once()
        self.assertEqual(v.pd.subscription.request.call_args.args,
                         ('printer.gcode.script', {'script': 'MMU_GATE_MAP GATE=0 SPOOLID=102 TEMP=205'}))

    def test_spool_clear_has_separate_confirmation_and_no_zero_id(self):
        v, _ = self.make()
        self.open_spool(v)
        self.press(v, 3)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_confirmation.values, (-1,))
        self.assertIn('Clear spool on G1', self.strings(v))
        v.pd.subscription.request.assert_not_called()
        self.press(v, 2)
        self.assertEqual(v.pd.subscription.request.call_args.args[1]['script'],
                         'MMU_GATE_MAP GATE=0 SPOOLID=-1 TEMP=205')

    def test_spool_pull_unknown_and_missing_temperature_leave_readonly_editor(self):
        for fields in ({'spoolman_support': 'pull'}, {'spoolman_support': None},
                       {'gate_temperature': []}, {'gate_spool_id': []}):
            v, _ = self.make(**fields)
            self.open_spool(v)
            self.press(v, 1)
            self.assertIsNone(v._mmu_edit)
            self.press(v, 2)
            self.assertEqual(v._mmu_page, 'spool')
            self.press(v, 3)
            self.assertEqual(v._mmu_page, 'spool')
            v.pd.subscription.request.assert_not_called()

    def test_spool_first_assignment_bounds_and_noop_save_lock(self):
        v, _ = self.make(gate_spool_id=[-1]*4)
        self.open_spool(v)
        self.assertEqual(v._mmu_spool_draft, 1)
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CCW
        v.HMI_MMU_Menu()
        self.assertEqual(v._mmu_spool_draft, 1)
        self.press(v, 1)
        self.press(v, 2)
        self.assertEqual(v._mmu_confirmation.values, (1,))
        v, _ = self.make()
        self.open_spool(v)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'spool')
        v.pd.subscription.request.assert_not_called()

    def test_spool_external_update_pause_disconnect_epoch_lock_save(self):
        for case in ('ids', 'mode', 'paused', 'printing', 'offline', 'epoch'):
            v, data = self.make()
            self.open_spool(v)
            self.edit_spool(v)
            if case == 'ids': data['status']['mmu']['gate_spool_id'] = [500]*4
            elif case == 'mode': data['status']['mmu']['spoolman_support'] = 'pull'
            elif case == 'offline': data['state'] = 'disconnected'
            elif case == 'epoch': data['epoch'] += 1
            else: data['status']['print_stats']['state'] = case
            self.press(v, 2)
            self.assertEqual(v._mmu_page, 'spool')
            v.pd.subscription.request.assert_not_called()

    def test_spool_confirm_and_open_editor_survive_removed_gate(self):
        for page in ('spool', 'confirm'):
            v, data = self.make()
            v._mmu_gate = 3
            v._mmu_open('filament')
            self.press(v, 1)
            if page == 'confirm': self.press(v, 2)
            data['status']['mmu']['num_gates'] = 2
            v.Draw_MMU_Menu()
            self.press(v, 2)
            self.assertEqual(v._mmu_page, page)
            v.pd.subscription.request.assert_not_called()

    def edit_map(self, v):
        self.press(v, 3)
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v.HMI_MMU_Menu()
        self.press(v, 1)

    def test_map_edit_accept_only_changes_draft_cancel_discards(self):
        v, _ = self.make()
        self.edit_map(v)
        self.assertEqual(v._mmu_map_draft, [1, 1, 2, 3])
        v.pd.subscription.request.assert_not_called()
        self.press(v, len(v._mmu_items(v.pd.mmu_session.state)))
        self.assertEqual(v._mmu_page, 'home')
        self.press(v, 3)
        self.assertEqual(v._mmu_map_draft, [0, 1, 2, 3])

    def test_map_save_cancel_keeps_draft_then_confirm_sends_one_bulk_command(self):
        v, _ = self.make()
        self.edit_map(v)
        self.press(v, 6)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_selection, 1)
        self.assertIn('T0 > G2', self.strings(v))
        self.press(v, 1)
        self.assertEqual(v._mmu_map_draft, [1, 1, 2, 3])
        self.press(v, 6)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'status')
        self.assertEqual(v.pd.subscription.request.call_args.args,
                         ('printer.gcode.script', {'script': 'MMU_TTG_MAP MAP=1,1,2,3'}))
        self.assertEqual(v.pd.subscription.request.call_count, 1)

    def test_map_external_change_and_printing_lock_save(self):
        for change in ('map', 'print'):
            v, data = self.make()
            self.edit_map(v)
            if change == 'map': data['status']['mmu']['ttg_map'] = [3]*4
            else: data['status']['print_stats']['state'] = 'printing'
            self.press(v, 6)
            self.assertEqual(v._mmu_page, 'map')
            v.pd.subscription.request.assert_not_called()

    def test_map_scroll_and_gate_edit_bounds(self):
        v, _ = self.make(num_gates=12, ttg_map=list(range(12)), gate_status=[1]*12,
                         gate_color_rgb=[[1, 0, 0]]*12)
        self.press(v, 3)
        self.press(v, 12)
        for _ in range(3):
            v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
            v.HMI_MMU_Menu()
        self.assertEqual(v._mmu_map_draft[11], 11)
        self.assertIn('[G12]', self.strings(v))
        self.press(v, 12)
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CCW
        v.HMI_MMU_Menu()
        self.assertEqual(v._mmu_map_draft[0], 0)

    def open_endless(self, v):
        self.press(v, 3)
        self.press(v, v.pd.mmu_session.state.num_gates + 1)
        self.assertEqual(v._mmu_page, 'endless')

    def enable_endless(self, v):
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v.HMI_MMU_Menu()
        self.press(v, 1)

    def save_endless(self, v):
        items = v._mmu_items(v.pd.mmu_session.state)
        self.press(v, next(i + 1 for i, item in enumerate(items) if item[0] == ('endless_save',)))

    def test_endless_toggle_membership_cancel_never_sends(self):
        v, _ = self.make()
        self.open_endless(v)
        self.enable_endless(v)
        self.press(v, 2)
        self.press(v, 2)
        self.assertEqual(v._mmu_endless_draft, {'enabled': True, 'groups': [0, 0, 2, 3]})
        self.press(v, 0)
        self.press(v, len(v._mmu_items(v.pd.mmu_session.state)))
        self.assertEqual(v._mmu_page, 'map')
        self.assertIsNone(v._mmu_endless_draft)
        v.pd.subscription.request.assert_not_called()

    def test_endless_confirmation_cancel_retains_draft_then_saves_once(self):
        v, _ = self.make()
        self.open_endless(v)
        self.enable_endless(v)
        self.press(v, 2)
        self.press(v, 2)
        self.press(v, 0)
        self.save_endless(v)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_selection, 1)
        self.assertIn('G2 > Group 1', self.strings(v))
        self.press(v, 1)
        self.assertEqual(v._mmu_endless_draft['groups'], [0, 0, 2, 3])
        self.save_endless(v)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'status')
        v.pd.subscription.request.assert_called_once()
        self.assertEqual(v.pd.subscription.request.call_args.args,
                         ('printer.gcode.script', {'script': 'MMU_ENDLESS_SPOOL ENABLE=1 GROUPS=0,0,2,3'}))

    def test_endless_removing_member_splits_to_unused_group_last_member_stays(self):
        v, _ = self.make(endless_spool_groups=[99, 99, 2, 3])
        self.open_endless(v)
        # IDs 2, 3, 99 appear as groups 1, 2, 3.
        self.press(v, 4)
        self.press(v, 1)
        self.assertEqual(v._mmu_endless_draft['groups'], [0, 99, 2, 3])
        self.press(v, 2)
        self.assertEqual(v._mmu_endless_draft['groups'], [0, 99, 2, 3])

    def test_endless_material_color_compatibility_visible(self):
        v, _ = self.make(endless_spool_groups=[0]*4)
        self.open_endless(v)
        self.press(v, 2)
        self.assertIn('Mixed material / color', self.strings(v))
        self.assertIn('G1 PLA ff0000', self.strings(v))
        v, _ = self.make(endless_spool_groups=[0]*4, gate_material=['PLA']*4,
                         gate_color=['ff0000']*4)
        self.open_endless(v)
        self.press(v, 2)
        self.assertIn('Same material / color', self.strings(v))

    def test_endless_external_change_print_pause_and_disconnect_lock_draft(self):
        for case in ('groups', 'printing', 'paused', 'offline'):
            v, data = self.make()
            self.open_endless(v)
            self.enable_endless(v)
            if case == 'groups': data['status']['mmu']['endless_spool_groups'] = [3]*4
            elif case == 'offline': data['state'] = 'disconnected'
            else: data['status']['print_stats']['state'] = case
            self.save_endless(v)
            self.assertEqual(v._mmu_page, 'endless')
            v.pd.subscription.request.assert_not_called()

    def test_endless_missing_telemetry_remains_unknown_and_locked(self):
        v, _ = self.make(endless_spool_enabled=None, endless_spool_groups=[])
        self.open_endless(v)
        self.assertIsNone(v._mmu_endless_draft['enabled'])
        self.press(v, 1)
        self.assertIsNone(v._mmu_endless_draft['enabled'])
        self.save_endless(v)
        self.assertEqual(v._mmu_page, 'endless')
        v.pd.subscription.request.assert_not_called()

    def test_endless_navigation_preserves_unsaved_tool_map_draft(self):
        v, _ = self.make()
        self.edit_map(v)
        self.press(v, 5)
        self.press(v, 0)
        self.assertEqual(v._mmu_map_draft, [1, 1, 2, 3])

    def test_endless_enabled_value_uses_press_rotate_press_and_can_disable(self):
        v, _ = self.make(endless_spool_enabled=1)
        self.open_endless(v)
        self.press(v, 1)
        self.assertTrue(v._mmu_endless_draft['enabled'])
        self.assertEqual(v._mmu_edit, ('endless', 'enabled'))
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CCW
        v.HMI_MMU_Menu()
        self.assertFalse(v._mmu_endless_draft['enabled'])
        self.press(v, 1)
        self.assertIsNone(v._mmu_edit)
        self.save_endless(v)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_ENDLESS_SPOOL ENABLE=0 GROUPS=0,1,2,3')
        v.pd.subscription.request.assert_not_called()

    def test_endless_large_group_summary_and_rows_fit_screen(self):
        count = 16
        v, _ = self.make(num_gates=count, ttg_map=list(range(count)), gate_status=[1]*count,
                         gate_color_rgb=[[1, 0, 0]]*count, endless_spool_groups=[0]*count)
        self.open_endless(v)
        self.assertIn('G1 G2 G3 +13', self.strings(v))
        self.press(v, 2)
        v._mmu_selection = count
        v.Draw_MMU_Menu()
        self.assertTrue(any('G16' in s for s in self.strings(v)))
        for c in v.lcd.draw_text.call_args_list:
            x, _, value = c.args[-3:]
            font = c.args[2]
            cell = 6 if font == v.lcd.font6x12 else 8
            self.assertLessEqual(x + len(value)*cell, 272)

    def test_endless_gate_count_shrink_keeps_old_editor_and_confirmation_safe(self):
        for page in ('group', 'confirm'):
            v, data = self.make()
            self.open_endless(v)
            if page == 'group':
                self.press(v, 2)
            else:
                self.enable_endless(v)
                self.save_endless(v)
            data['status']['mmu']['num_gates'] = 2
            v.Draw_MMU_Menu()
            self.press(v, 2)
            v.pd.subscription.request.assert_not_called()

    def test_endless_confirmation_rejects_new_print_and_connection_epoch(self):
        for case in ('printing', 'epoch'):
            v, data = self.make()
            self.open_endless(v)
            self.enable_endless(v)
            self.save_endless(v)
            if case == 'printing': data['status']['print_stats']['state'] = 'printing'
            else: data['epoch'] += 1
            self.press(v, 2)
            self.assertEqual(v._mmu_page, 'confirm')
            v.pd.subscription.request.assert_not_called()

    def test_home_uses_full_canvas_but_keeps_original_dashboard_untouched(self):
        v, _ = self.make()
        self.assertIn((1, 0x0000, 0, 0, 271, 479), [c.args for c in v.lcd.draw_rectangle.call_args_list])
        self.assertIn('T2 > G3  LOADED', self.strings(v))
        v.lcd.reset_mock()
        v.Draw_Status_Area(True)
        v.lcd.assert_not_called()
        v.lcd.draw_rectangle.assert_not_called()
        v.lcd.draw_text.assert_not_called()
        v.Draw_MMU_Menu()
        v.lcd.draw_rectangle.assert_not_called()
        v.lcd.draw_text.assert_not_called()

    def test_browse_gates_and_open_details_never_moves(self):
        v, _ = self.make()
        self.press(v, 1)
        self.assertEqual(v._mmu_page, 'gates')
        self.press(v, 3)
        self.assertEqual(v._mmu_page, 'gate')
        self.assertEqual(v._mmu_gate, 2)
        v.pd.sendGCode.assert_not_called()
        v.pd.subscription.request.assert_not_called()
        self.assertIn('Unload', self.strings(v))

    def test_confirmation_defaults_to_cancel_and_cancel_does_not_send(self):
        v, _ = self.make()
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_selection, 1)
        self.assertEqual(v._mmu_confirmation.script, 'MMU_UNLOAD')
        self.press(v, 1)
        self.assertEqual(v._mmu_page, 'home')
        v.pd.subscription.request.assert_not_called()

    def test_only_explicit_confirm_submits_once_then_live_status(self):
        v, _ = self.make()
        self.press(v, 2)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'status')
        v.pd.subscription.request.assert_called_once()
        self.assertEqual(v.pd.subscription.request.call_args.args,
                         ('printer.gcode.script', {'script': 'MMU_UNLOAD'}))
        self.press(v, 0)
        self.press(v, 2)
        self.assertEqual(v.pd.subscription.request.call_count, 1)

    def test_external_target_change_closes_confirm_and_never_dispatches(self):
        v, data = self.make()
        self.press(v, 2)
        data['status']['mmu']['gate'] = 1
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertIn('Unavailable', v._mmu_notice)
        v.pd.subscription.request.assert_not_called()

    def test_disabled_action_is_visible_but_not_executable(self):
        v, _ = self.make(enabled=False)
        self.assertIn('MMU DISABLED', self.strings(v))
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'home')
        v.pd.subscription.request.assert_not_called()

    def test_scroll_all_gates_and_operation_rows(self):
        count = 12
        v, _ = self.make(num_gates=count, gate_status=[1]*count,
                         gate_color_rgb=[[1,0,0]]*count, ttg_map=list(range(count)))
        self.press(v, 1)
        v._mmu_selection = 12
        v.Draw_MMU_Menu()
        self.assertIn('G12 --', self.strings(v))
        self.press(v, 12)
        self.assertEqual(v._mmu_gate, 11)
        v._mmu_selection = 8
        v.Draw_MMU_Menu()
        self.assertIn('Filament details', self.strings(v))
        self.press(v, 8)
        self.assertEqual(v._mmu_page, 'filament')

    def test_multiple_tools_are_not_misrepresented_on_spool(self):
        v, _ = self.make(ttg_map=[2,2,2,3])
        self.assertIn('T*', self.strings(v))
        self.assertIn('--', self.strings(v))

    def test_live_progress_sensors_unknown_and_absent_are_distinct(self):
        v, data = self.make(bowden_progress=68, action='Loading')
        self.press(v, 6)
        strings = self.strings(v)
        self.assertIn('Bowden: 68%', strings)
        self.assertIn('mmu_shared_exit: UNKNOWN/OFF', strings)
        self.assertIn('extruder: CLEAR', strings)
        self.assertIn('toolhead: TRIGGERED', strings)
        data['status']['mmu']['sensors'].pop('toolhead')
        data['status']['mmu']['bowden_progress'] = -1
        v.Draw_MMU_Menu()
        self.assertIn('toolhead: ABSENT', self.strings(v))
        self.assertIn('Stage: Loading', self.strings(v))

    def test_focus_change_does_not_erase_full_canvas_or_spools(self):
        v, _ = self.make()
        v.lcd.reset_mock()
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v.HMI_MMU_Menu()
        self.assertTrue(v.lcd.draw_rectangle.called)
        for c in v.lcd.draw_rectangle.call_args_list:
            self.assertGreaterEqual(c.args[3], 5)
            self.assertNotEqual(c.args[2:], (0,0,271,479))
        self.assertNotIn('78%', self.strings(v))

    def test_back_restores_bottom_dashboard_and_home_cursor(self):
        v, _ = self.make()
        v.select_page.set(4)
        v.Draw_Status_Area = Mock()
        self.press(v, 0)
        self.assertEqual(v.checkkey, v.MainMenu)
        self.assertEqual(v.select_page.now, 4)
        v.Draw_Status_Area.assert_called_once_with(False)

    def test_disconnect_in_operation_keeps_error_and_does_not_replay(self):
        v, data = self.make()
        self.press(v, 2)
        self.press(v, 2)
        data['state'] = 'disconnected'
        v.pd.connection_error = 'offline'
        v._poll_mmu()
        self.assertEqual(v.pd.mmu_session.phase, 'error')
        self.assertIn('OFFLINE', self.strings(v))
        self.assertEqual(v.pd.subscription.request.call_count, 1)
        self.press(v, 1)
        self.assertEqual(v.pd.mmu_session.phase, 'idle')

    def test_recovery_manual_editor_is_draft_until_apply_and_confirm(self):
        v, _ = self.make(print_state='pause_locked', filament='Unknown', filament_pos=-1)
        v._mmu_open('recover')
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'manual')
        self.press(v, 1)
        v.get_encoder_state.return_value = v.ENCODER_DIFF_CW
        v.HMI_MMU_Menu()
        self.assertEqual(v._mmu_manual['tool'], 3)
        self.press(v, 1)
        self.press(v, 4)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertEqual(v._mmu_confirmation.script, 'MMU_RECOVER TOOL=3 GATE=2 LOADED=0')
        v.pd.subscription.request.assert_not_called()

    def test_bypass_load_is_locked_until_unloaded_and_selected(self):
        v, _ = self.make()
        self.press(v, 4)
        items = v._mmu_items(v.pd.mmu_session.state)
        self.assertEqual([i[3] for i in items], [True,False,False,False])
        self.press(v, 2)
        v.pd.subscription.request.assert_not_called()

    def test_print_state_update_does_not_take_over_mmu_page(self):
        v, _ = self.make()
        v.pd.status = 'paused'
        v._present_print_state()
        self.assertEqual(v.checkkey, v.MMUMenu)

    def test_mmu_error_pause_routes_directly_to_recovery(self):
        v, data = self.make(print_state='pause_locked', reason_for_pause='Filament missing')
        v.checkkey = v.PrintProcess
        v.pd.status = 'paused'
        v._present_print_state()
        self.assertEqual(v.checkkey, v.MMUMenu)
        self.assertEqual(v._mmu_page, 'recover')

    def test_all_page_primitives_stay_inside_lcd(self):
        v, _ = self.make()
        self.press(v, 2)  # Supplies a confirmation target.
        for page in v.MMU_TITLES:
            v._mmu_page = page
            v._mmu_selection = 1
            v._mmu_canvas_page = None
            v.lcd.reset_mock()
            v.Draw_MMU_Menu()
            for c in v.lcd.draw_rectangle.call_args_list:
                _, _, x0, y0, x1, y1 = c.args
                with self.subTest(page=page, coords=c.args):
                    self.assertTrue(0 <= x0 <= x1 < 272)
                    self.assertTrue(0 <= y0 <= y1 < 480)
            for c in v.lcd.draw_text.call_args_list:
                x,y,value = c.args[-3:]
                self.assertGreaterEqual(x,0)
                self.assertLess(x,272)
                self.assertGreaterEqual(y,0)
                self.assertLess(y,480)

    def test_gate_removal_rejects_stale_enter_instead_of_selecting_new_target(self):
        v, data = self.make()
        self.press(v, 1)
        v._mmu_selection = 4
        data['status']['mmu']['num_gates'] = 2
        self.press(v, 4)
        self.assertEqual(v._mmu_page, 'gates')
        self.assertIn('Menu changed', v._mmu_notice)
        self.assertLessEqual(v._mmu_selection, 2)
        v.pd.subscription.request.assert_not_called()

    def test_changed_load_unload_button_cannot_execute_old_enter(self):
        v, data = self.make()
        data['status']['mmu'].update(filament='Unloaded', filament_pos=0)
        self.press(v, 2)
        self.assertEqual(v._mmu_page, 'home')
        self.assertIn('Menu changed', v._mmu_notice)
        v.pd.subscription.request.assert_not_called()

    def test_manual_draft_cannot_apply_after_external_state_change(self):
        v, data = self.make()
        v._mmu_open('recover')
        self.press(v, 2)
        data['status']['mmu']['tool'] = 1
        self.press(v, 4)
        self.assertEqual(v._mmu_page, 'manual')
        self.assertIn('reopen editor', v._mmu_notice)
        v.pd.subscription.request.assert_not_called()

    def test_pending_operation_cannot_leave_mmu_and_start_another_ui_action(self):
        v, _ = self.make()
        self.press(v, 2)
        self.press(v, 2)
        self.press(v, 0)  # Return to MMU home.
        self.press(v, 0)  # Exit is deferred until MMU completes.
        self.assertEqual(v.checkkey, v.MMUMenu)
        self.assertEqual(v._mmu_page, 'status')
        self.assertIn('Wait', v._mmu_notice)
        self.assertEqual(v.pd.subscription.request.call_count, 1)

    def test_uart_reconnect_rebuilds_current_page_and_cache(self):
        from test_regressions import ui
        from unittest.mock import patch
        v, _ = self.make()
        self.press(v, 1)
        v._closed = False
        v._settings = ('/dev/fake',)
        v._uart_online = False
        v._next_uart_retry = 0
        v._uart_epoch = 0
        v.HMI_Init = Mock()
        port = Mock()
        with patch.object(ui, 'T5UIC1Display', return_value=port):
            self.assertTrue(v._ensure_uart())
        self.assertEqual(v._mmu_page, 'gates')
        self.assertIn((1,0x0000,0,0,271,479), [c.args for c in port.draw_rectangle.call_args_list])
        self.assertIn('G1 PLA', [c.args[-1] for c in port.draw_text.call_args_list])
        v.pd.subscription.request.assert_not_called()

    def test_offline_encoder_navigation_can_back_out_but_never_sends_motion(self):
        from ui_events import InputEvent
        v, data = self.make()
        v._closed = False
        v._uart_online = True
        v._uart_epoch = 1
        v._encoder_event = v.ENCODER_DIFF_NO
        v.get_encoder_state = lambda: v._encoder_event
        data['state'] = 'disconnected'
        data['error'] = 'offline'
        v._process_input(InputEvent('press',1,1,1))  # Old Gates selection changed safely.
        self.assertEqual(v.checkkey,v.MMUMenu)
        v._process_input(InputEvent('rotate',1,1,1))  # CCW to Back.
        v.Draw_Status_Area = Mock()
        v._process_input(InputEvent('press',1,1,1))
        if v.checkkey == v.MMUMenu:
            v._mmu_selection = 0
            v._process_input(InputEvent('press',1,1,1))
        self.assertEqual(v.checkkey,v.MainMenu)
        v.pd.subscription.request.assert_not_called()

    def test_tick_keeps_full_screen_and_updates_only_changed_telemetry(self):
        v, data = self.make()
        v.last_status = v.pd.status
        v._offline = False
        v.lcd.reset_mock()
        data['status']['extruder']['temperature'] = 201
        v.EachMomentUpdate()
        self.assertEqual(v.checkkey,v.MMUMenu)
        self.assertIn('Nozzle 201/205 C', self.strings(v))
        self.assertNotIn((1,0x0000,0,0,271,479), [c.args for c in v.lcd.draw_rectangle.call_args_list])
        self.assertFalse(any(c.args[3] == v.STATUS_Y for c in v.lcd.draw_rectangle.call_args_list))
