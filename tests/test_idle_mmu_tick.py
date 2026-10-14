"""Idle MMU overview must not run at the animation refresh rate."""
import time
import unittest
from unittest.mock import Mock

from test_regressions import ui
from mmu_filament_view import MMUFilamentView


class IdleMMUPollTests(unittest.TestCase):
    def test_idle_tick_reduces_frequency_without_running_animation(self):
        view = ui.PetrelDisplay.__new__(ui.PetrelDisplay)
        view.pd = Mock()
        view.lcd = Mock()
        view._uart_online = True
        view._loop = Mock()
        view._mmu_page = 'home'
        view.checkkey = view.MMUMenu
        view._next_uart_probe = time.monotonic() + 100
        view._mmu_status_at = time.monotonic() + 100
        view._poll_panel_power = Mock()
        view._sync_case_light_tracking = Mock()
        view._power_hold_tick = Mock(return_value=False)
        view._power_popup_tick = Mock(return_value=False)
        view._mmu_animation_tick = Mock()
        view._mmu_animation_state = Mock(action='Idle')
        view._mmu_filament_view = MMUFilamentView(view.lcd)
        view._ui_tick()
        view._loop.set_interval.assert_called_with(.5)
        view._mmu_animation_tick.assert_not_called()
        view._mmu_animation_state.action = 'Purging'
        view._ui_tick()
        view._loop.set_interval.assert_called_with(.05)
        view._mmu_animation_tick.assert_called_once()

    def test_filament_interpolation_is_the_only_idle_high_frequency_case(self):
        view = MMUFilamentView(Mock())
        idle = Mock(action='Idle')
        self.assertFalse(view.animating(idle, now=100))
        view._from = 4
        view._target = 30
        view._changed = 100
        self.assertTrue(view.animating(idle, now=100.1))
        self.assertFalse(view.animating(idle, now=100.6))
