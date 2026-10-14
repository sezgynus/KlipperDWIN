import unittest
import time
from dataclasses import replace
from unittest.mock import Mock, patch
import test_mmu_control as control
import test_mmu_ui as ui
from test_mmu_control import mmu_snapshot
from mmu_control import MMUState
from mmu_filament_view import MMUFilamentView, filament_height


class LiveMMUStateTests(unittest.TestCase):
    def test_live_position_and_residue_sources(self):
        data = mmu_snapshot(filament='Unknown', filament_pos=3, filament_position=123.4,
                            filament_direction=1, bowden_progress=25)
        data['status']['save_variables'] = {'variables': {
            'mmu_state_filament_remaining': 8.5, 'mmu_state_filament_remaining_color': 'ff0000'}}
        state = MMUState.from_snapshot(data)
        self.assertEqual((state.filament_pos, state.filament_position, state.bowden_progress), (3, 123.4, 25))
        self.assertEqual((state.filament_remaining, state.filament_remaining_color), (8.5, 'ff0000'))
        data['status']['mmu'].update(filament_remaining=0, filament_remaining_color='00ff00')
        state = MMUState.from_snapshot(data)
        self.assertEqual((state.filament_remaining, state.filament_remaining_color), (0, '00ff00'))

    def test_bad_position_is_not_promoted_to_known(self):
        for value in (True, '123', float('nan'), float('inf')):
            self.assertIsNone(MMUState.from_snapshot(mmu_snapshot(filament_position=value)).filament_position)
        for pos in (-2, 11, True, '3'):
            self.assertIsNone(MMUState.from_snapshot(mmu_snapshot(filament_pos=pos)).filament_pos)

    def test_gate_sensor_supports_both_happy_hare_names(self):
        for name in ('mmu_gate', 'mmu_shared_exit'):
            for value in (True, False, None):
                state = MMUState.from_snapshot(mmu_snapshot(sensors={name: value}))
                self.assertIs(state.sensor('mmu_gate'), value)

    def test_partial_filament_can_unload_but_unknown_cannot(self):
        helper = control.MMUControlTests()
        for pos in range(1, 10):
            _, _, session = helper.make(filament='Unknown', filament_pos=pos)
            self.assertEqual(session.prepare('unload', gate=2).script, 'MMU_UNLOAD')
        for pos in (-1, None, 0):
            _, _, session = helper.make(filament='Unknown', filament_pos=pos)
            with self.assertRaises(ValueError): session.prepare('unload', gate=2)

    def test_exact_tool_is_used_for_shared_gate(self):
        _, data, session = control.MMUControlTests().make(ttg_map=[2, 2, 2, 3])
        operation = session.prepare('change', gate=2, tool=1)
        self.assertEqual(operation.script, 'MMU_CHANGE_TOOL TOOL=1 STANDALONE=1')
        data['status']['mmu']['ttg_map'][1] = 0
        with self.assertRaises(ValueError): session.start(operation)


class LiveMMUViewTests(unittest.TestCase):
    def test_tool_click_dispatches_exact_mapping_once_and_stays_on_overview(self):
        fixture = ui.MMUUITests()
        view, data = fixture.make(ttg_map=[2, 2, 2, 3])
        fixture.press(view, 2)
        self.assertEqual(view._mmu_page, 'home')
        self.assertEqual(view.pd.subscription.request.call_args.args,
                         ('printer.gcode.script', {'script': 'MMU_CHANGE_TOOL TOOL=1 STANDALONE=1'}))
        fixture.press(view, 2)
        self.assertEqual(view.pd.subscription.request.call_count, 1)

    def test_partial_unload_and_more_navigation(self):
        fixture = ui.MMUUITests()
        view, _ = fixture.make(filament='Unknown', filament_pos=4)
        fixture.press(view, 5)
        self.assertEqual(view._mmu_page, 'home')
        self.assertEqual(view.pd.subscription.request.call_args.args[1], {'script': 'MMU_UNLOAD'})
        fixture.press(view, 6)
        self.assertEqual(view._mmu_page, 'more')

    def test_tool_bank_scrolls_and_uses_tool_mapping(self):
        view, _ = ui.MMUUITests().make(num_gates=8, ttg_map=[7, 6, 5, 4, 3, 2, 1, 0],
                                      gate_status=[1] * 8, gate_color=['ff0000'] * 8)
        view._mmu_selection = 8
        view.Draw_MMU_Menu()
        self.assertEqual(view._mmu_spool_page[1], 4)
        self.assertEqual([i[0] for i in view._mmu_items(view.pd.mmu_session.state)[:2]],
                         [('tool', 0, 7), ('tool', 1, 6)])

    def test_idle_and_focus_updates_do_not_redraw_filament_or_spool_images(self):
        view, _ = ui.MMUUITests().make()
        view.lcd.reset_mock()
        view.Draw_MMU_Menu()
        view.lcd.draw_rectangle.assert_not_called()
        view.lcd.draw_circle.assert_not_called()
        view._mmu_selection = 2
        view.Draw_MMU_Menu()
        view.lcd.show_icon.assert_not_called()
        for call in view.lcd.draw_rectangle.call_args_list:
            self.assertGreaterEqual(call.args[3], 109)
            self.assertLessEqual(call.args[5], 128)

    def test_mainsail_height_mapping_and_bowden_direction(self):
        state = MMUState.from_snapshot(mmu_snapshot(filament='Unknown', filament_pos=3,
                                                   sensors={'mmu_gate': True, 'toolhead': True}, bowden_progress=0))
        self.assertEqual(filament_height(state), 135)
        self.assertEqual(filament_height(replace(state, bowden_progress=100)), 290)
        for direction in (1, -1):
            self.assertEqual(filament_height(replace(state, bowden_progress=50, filament_direction=direction)), 212.5)
        self.assertEqual(filament_height(replace(state, filament_pos=9, sensors=(('toolhead', False),))), 315)

    def test_native_incremental_pixels_match_fresh_render_after_progress_and_purge(self):
        from test_t5uic1_driver import driver
        from dwin_emulator.assets import PanelAssets, rgb565
        from dwin_emulator.framebuffer import Framebuffer
        assets = PanelAssets()
        def canvas():
            lcd = driver()
            framebuffer = Framebuffer(assets)
            lcd._packet_observer = framebuffer
            return MMUFilamentView(lcd), framebuffer
        state = MMUState.from_snapshot(mmu_snapshot(filament='Unknown', filament_pos=3,
                                                   sensors={'mmu_gate': True}, bowden_progress=0,
                                                   filament_remaining=8, filament_remaining_color='ff0000'))
        view, frame = canvas()
        view.draw(state, now=0)
        state = replace(state, bowden_progress=100)
        view.draw(state, now=1)
        self.assertLess(view._painted['height'], 145)
        view.draw(state, now=1.5)
        fresh, reference = canvas()
        fresh.draw(state, now=1.5)
        view.lcd.update()
        fresh.lcd.update()
        self.assertEqual(frame.snapshot()[0].tobytes(), reference.snapshot()[0].tobytes())
        state = replace(state, filament_pos=10, filament='loaded', action='Purging')
        view.draw(state, now=2)
        view.draw(state, now=2.5)
        view.lcd.update()
        self.assertEqual(frame.snapshot()[0].getpixel((63, 351)), rgb565(0xF800))
        state = replace(state, action='Idle', filament_remaining=0, filament_remaining_color='0000ff')
        view.draw(state, now=4)
        fresh, reference = canvas()
        fresh.draw(state, now=4)
        view.lcd.update()
        fresh.lcd.update()
        self.assertEqual(frame.snapshot()[0].tobytes(), reference.snapshot()[0].tobytes())

    def test_sensor_changes_only_repaint_the_circle(self):
        lcd = Mock()
        view = MMUFilamentView(lcd)
        state = MMUState.from_snapshot(mmu_snapshot(sensors={'mmu_gate': False}))
        view.draw(state, now=0)
        lcd.reset_mock()
        view.draw(replace(state, sensors=(('mmu_gate', True),)), now=1)
        lcd.fill_circle.assert_called_once_with(0x07E0, 75, view.GATE_Y, 5)
        lcd.draw_rectangle.assert_called_once_with(1, view.BLOCK, 69, view.GATE_Y - 7, 81, view.GATE_Y + 7)

    def test_retarget_advances_previous_trajectory_before_starting_next(self):
        view = MMUFilamentView(Mock())
        state = MMUState.from_snapshot(mmu_snapshot(filament='Unknown', filament_pos=0,
                                                   sensors={'mmu_gate': False}))
        view.draw(state, now=0)
        heights = []
        for i, progress in enumerate((0, 25, 50, 75, 100), 1):
            view.draw(replace(state, filament_pos=3, bowden_progress=progress), now=i * .5)
            heights.append(view._painted['height'])
        self.assertTrue(all(a < b for a, b in zip(heights, heights[1:])), heights)
        self.assertGreater(heights[-1], 100)

    def test_gate_detection_immediately_confirms_filament_at_same_height(self):
        view = MMUFilamentView(Mock())
        state = MMUState.from_snapshot(mmu_snapshot(filament='Unknown', filament_pos=0,
                                                   sensors={'mmu_gate': False}))
        view.draw(state, now=0)
        view.draw(replace(state, sensors=(('mmu_gate', True),)), now=.05)
        self.assertEqual(view._painted['height'], view.GATE_Y - view.TOP)

    def test_animation_ticks_do_not_poll_status_or_redraw_overview(self):
        view, _ = ui.MMUUITests().make()
        view._uart_online = True
        view._next_uart_probe = float('inf')
        view._poll_panel_power = Mock()
        view._sync_case_light_tracking = Mock()
        view._display_idle_tick = Mock()
        view._draw_header_clock = Mock(return_value=False)
        view.EachMomentUpdate = Mock()
        view._mmu_animation_tick = Mock()
        view._loop = Mock()
        for now in (100, 100.05, 100.1, 100.5):
            with patch.object(time, 'monotonic', return_value=now):
                view._ui_tick()
        self.assertEqual(view.EachMomentUpdate.call_count, 2)
        self.assertEqual(view._mmu_animation_tick.call_count, 0)
        view._loop.set_interval.assert_called_with(.5)
