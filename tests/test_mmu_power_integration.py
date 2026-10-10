"""Power focus, popup restoration and MMU dirty-canvas integration."""
import unittest
from unittest.mock import Mock
import test_mmu_ui as mmu_fixtures
from lcd_atlas import ICON_POWER


class MMUPowerIntegrationTests(unittest.TestCase):
    def view(self):
        v, data = mmu_fixtures.MMUUITests().make()
        v._power_focus = False
        v.pd.power_off_if_on = Mock()
        return v, data

    def event(self, view, event):
        view.get_encoder_state = Mock(return_value=event)
        view._dispatch_input()

    def popup(self, view):
        view._mmu_selection = 0
        self.event(view, view.ENCODER_DIFF_CCW)
        self.assertTrue(view._power_focus)
        self.event(view, view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey, view.PowerConfirm)
        self.assertTrue(view._power_confirm_yes)

    def test_power_icon_on_every_mmu_page_without_repainting_idle_page(self):
        v, _ = self.view()
        mmu_fixtures.MMUUITests().press(v, 2)
        for page in v.MMU_TITLES:
            with self.subTest(page=page):
                v._mmu_page, v._mmu_canvas_page = page, None
                v.lcd.reset_mock()
                v.Draw_MMU_Menu()
                v.lcd.draw_atlas_icon.assert_called_once_with(ICON_POWER, 244, 5)
                title = v._mmu_render['title']
                self.assertLessEqual(title[1] + title[3] * 8, 241)
                v.lcd.reset_mock()
                v.Draw_MMU_Menu()
                v.lcd.draw_atlas_icon.assert_not_called()
        v.pd.subscription.request.assert_not_called()

    def test_ccw_reaches_back_before_power_and_cw_restores_back(self):
        v, _ = self.view()
        v._mmu_selection = 2
        for selection in (1, 0):
            self.event(v, v.ENCODER_DIFF_CCW)
            self.assertEqual(v._mmu_selection, selection)
            self.assertFalse(v._power_focus)
        self.event(v, v.ENCODER_DIFF_CCW)
        self.assertTrue(v._power_focus)
        self.event(v, v.ENCODER_DIFF_CW)
        self.assertFalse(v._power_focus)
        self.assertEqual(v._mmu_selection, 0)
        v.pd.subscription.request.assert_not_called()

    def test_power_does_not_capture_mmu_numeric_edit_rotations(self):
        v, _ = self.view()
        v._mmu_open('map')
        v._mmu_edit = ('map', 0)
        v._mmu_selection = 0
        original = v._mmu_map_draft[0]
        self.event(v, v.ENCODER_DIFF_CW)
        self.assertEqual(v._mmu_map_draft[0], original + 1)
        self.assertFalse(v._power_focus)
        v.pd.power_off_if_on.assert_not_called()

    def test_no_restores_entire_canvas_draft_and_read_only_selection(self):
        v, _ = self.view()
        v._mmu_open('map')
        v._mmu_map_draft[0] = 3
        draft = list(v._mmu_map_draft)
        self.popup(v)
        v.lcd.reset_mock()
        self.event(v, v.ENCODER_DIFF_CW)
        self.event(v, v.ENCODER_DIFF_ENTER)
        self.assertEqual(v.checkkey, v.MMUMenu)
        self.assertEqual(v._mmu_page, 'map')
        self.assertEqual(v._mmu_map_draft, draft)
        self.assertEqual(v._mmu_selection, 0)
        self.assertIn((1, 0, 0, 0, 271, 479), [c.args for c in v.lcd.draw_rectangle.call_args_list])
        v.lcd.draw_atlas_icon.assert_called_with(ICON_POWER, 244, 5)
        v.pd.power_off_if_on.assert_not_called()
        v.pd.subscription.request.assert_not_called()

    def test_cancel_power_restores_mmu_confirmation_without_executing_it(self):
        v, _ = self.view()
        mmu_fixtures.MMUUITests().press(v, 2)
        op = v._mmu_confirmation
        self.popup(v)
        self.event(v, v.ENCODER_DIFF_CW)
        self.event(v, v.ENCODER_DIFF_ENTER)
        self.assertEqual(v._mmu_page, 'confirm')
        self.assertIs(v._mmu_confirmation, op)
        self.assertEqual(v._mmu_selection, 0)
        v.pd.subscription.request.assert_not_called()
        v.pd.power_off_if_on.assert_not_called()
