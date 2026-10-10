import unittest
from unittest.mock import Mock
from test_capabilities import snapshot,display


class HomePageTests(unittest.TestCase):
    def make(self,mesh=True):
        view=display(snapshot(probe=mesh))
        view.lcd.DWIN_WIDTH = 272
        view.lcd.DWIN_HEIGHT = 480
        view.checkkey=view.MainMenu
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_NO)
        return view

    def step(self,view,event):
        view.get_encoder_state.return_value=event
        view.HMI_MainMenu()

    def test_forward_and_reverse_page_crossing_skips_empty_slots(self):
        view=self.make()
        self.assertEqual([e[0] for e in view._home_entries()],['PRINT','PREPARE','CONTROL','LEVEL','MMU','INFO'])
        for index in range(1,5):
            self.step(view,view.ENCODER_DIFF_CW)
            self.assertEqual(view.select_page.now,index)
        view.lcd.reset_mock();view._draw_home_page()
        icons=[c.args[1:] for c in view.lcd.show_icon.call_args_list]
        self.assertEqual(icons,[(view.ICON_Info_0,145,130)])
        self.step(view,view.ENCODER_DIFF_CW)
        self.assertEqual(view.select_page.now,5)
        self.step(view,view.ENCODER_DIFF_CW)
        self.assertEqual(view.select_page.now,5)
        self.step(view,view.ENCODER_DIFF_CCW)
        self.assertEqual(view.select_page.now,4)
        self.step(view,view.ENCODER_DIFF_CCW)
        self.assertEqual(view.select_page.now,3)
        self.assertIn((view.ICON_Leveling_1,145,246),[c.args[1:] for c in view.lcd.show_icon.call_args_list])
        for _ in range(8):self.step(view,view.ENCODER_DIFF_CCW)
        self.assertEqual(view.select_page.now,0)
        view.pd.sendGCode.assert_not_called()

    def test_without_mesh_mmu_first_page_and_info_second_page(self):
        view=self.make(False)
        self.assertEqual([e[0] for e in view._home_entries()],['PRINT','PREPARE','CONTROL','MMU','INFO'])
        for _ in range(8):self.step(view,view.ENCODER_DIFF_CW)
        self.assertEqual(view.select_page.now,4)
        view.lcd.reset_mock();view._draw_home_page()
        self.assertIn((view.ICON_Info_1,17,130),[c.args[1:] for c in view.lcd.show_icon.call_args_list])
        self.assertFalse(any(c.args[-1]=='1/1' for c in view.lcd.draw_text.call_args_list))

    def test_home_info_enter_returns_to_same_page(self):
        view=self.make();view.select_page.set(5);view.Draw_Info_Menu=Mock()
        self.step(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.Info)
        self.assertEqual(view._info_origin,view.MainMenu)
        view._info_items=Mock(return_value=[])
        view.HMI_Info()
        self.assertEqual(view.checkkey,view.MainMenu)
        self.assertEqual(view.select_page.now,5)
        self.assertIn((view.ICON_Info_1,145,130),[c.args[1:] for c in view.lcd.show_icon.call_args_list])

    def test_control_info_returns_to_control(self):
        view=self.make();view.checkkey=view.Control
        view.select_control.set(view.CONTROL_CASE_INFO);view.Draw_Info_Menu=Mock()
        view.get_encoder_state.return_value=view.ENCODER_DIFF_ENTER
        view.HMI_Control();self.assertEqual(view._info_origin,view.Control)
        view._info_items=Mock(return_value=[]);view.HMI_Info()
        self.assertEqual(view.checkkey,view.Control)
        self.assertEqual(view.select_control.now,view.CONTROL_CASE_INFO)

    def test_leveling_and_other_first_page_actions_keep_routing(self):
        view=self.make();view.HMI_Leveling=Mock();view.select_page.set(3)
        self.step(view,view.ENCODER_DIFF_ENTER)
        view.HMI_Leveling.assert_called_once();self.assertEqual(view.checkkey,view.Leveling)
        for index,key,draw in [(0,view.SelectFile,'Draw_Print_File_Menu'),(1,view.Prepare,'Draw_Prepare_Menu'),(2,view.Control,'Draw_Control_Menu')]:
            view.checkkey=view.MainMenu;view.select_page.set(index)
            setattr(view,draw,Mock());view._refresh_file_snapshot=Mock()
            self.step(view,view.ENCODER_DIFF_ENTER)
            self.assertEqual(view.checkkey,key);getattr(view,draw).assert_called_once()

    def test_paging_never_erases_dashboard_or_mmu(self):
        view=self.make();view.select_page.set(3)
        view.Draw_Status_Area=Mock();view.Draw_MMU_Status=Mock()
        self.step(view,view.ENCODER_DIFF_CW)
        for c in view.lcd.draw_rectangle.call_args_list:
            self.assertGreaterEqual(c.args[3],126)
            self.assertLess(c.args[5],view.STATUS_Y)
        view.Draw_Status_Area.assert_not_called();view.Draw_MMU_Status.assert_not_called()
        self.assertIn('2/2',[c.args[-1] for c in view.lcd.draw_text.call_args_list])

    def test_capability_removal_clamps_cursor_to_existing_info(self):
        view=self.make();view.select_page.set(5);view.pd.HAS_ONESTEP_LEVELING=False
        view._draw_home_page();self.assertEqual(view.select_page.now,4)
        self.assertIn((view.ICON_Info_1,17,130),[c.args[1:] for c in view.lcd.show_icon.call_args_list])

    def test_mmu_entry_and_back_preserve_home_selection(self):
        for mesh in (True, False):
            view=self.make(mesh)
            index=next(i for i,e in enumerate(view._home_entries()) if e[0]=='MMU')
            view.select_page.set(index)
            self.step(view,view.ENCODER_DIFF_ENTER)
            self.assertEqual(view.checkkey,view.MMUMenu)
            self.assertEqual(view._mmu_page,'home')
            self.assertEqual(view._mmu_selection,0)
            view.get_encoder_state.return_value=view.ENCODER_DIFF_ENTER
            view._dispatch_input()
            self.assertEqual(view.checkkey,view.MainMenu)
            self.assertEqual(view.select_page.now,index)
            view.pd.sendGCode.assert_not_called()

    def test_mmu_icon_uses_managed_atlas_for_both_selection_states(self):
        from lcd_atlas import ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED
        view=self.make()
        for x,y in ((17,130),(145,246)):
            for selected,icon_id in (
                (False,ICON_MMU_HOME_NORMAL),
                (True,ICON_MMU_HOME_SELECTED),
            ):
                view.lcd.reset_mock();view.Draw_MMU_Home_Icon(x,y,selected)
                view.lcd.draw_atlas_icon.assert_called_once_with(icon_id,x+16,y+16)
                view.lcd.draw_rectangle.assert_not_called()
                view.lcd.draw_line.assert_not_called()
