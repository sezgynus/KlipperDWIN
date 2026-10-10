import copy
import unittest
from concurrent.futures import Future
from unittest.mock import ANY, Mock, patch

from test_capabilities import snapshot, printer, display
from printer_state import PrinterState
from bed_mesh import BedMeshSession, MeshData
from moonraker_client import MoonrakerError
from moonraker_subscription import MoonrakerSubscription


def data():
    source = snapshot(probe=True)
    source['settings']['bed_mesh'] = {'mesh_min': [20, 30], 'mesh_max': [220, 230], 'probe_count': [3, 3]}
    source['settings']['bltouch'].update(x_offset=-40, y_offset=-10)
    source['status']['configfile'] = {'save_config_pending': False, 'save_config_pending_items': {}}
    source['status']['bed_mesh'] = payload()['status']['bed_mesh']
    return source


def payload(name='lcd_mesh_1'):
    points = [[-.12, -.04, .02], [-.08, 0, .06], [-.03, .05, .12]]
    params = dict(min_x=20, max_x=220, min_y=30, max_y=230, x_count=3, y_count=3)
    return {'status': {'bed_mesh': dict(profile_name=name, mesh_min=[20, 30], mesh_max=[220, 230],
        probed_matrix=points, mesh_matrix=[[999]], profiles={name: dict(points=points, mesh_params=params)})}}


class MeshTests(unittest.TestCase):
    def make(self, source=None):
        p = printer(source or data())
        p.subscription.request.side_effect = lambda *a, **k: Future()
        p.subscription.responses_since.return_value = (0, ())
        return p, p.bed_mesh

    def complete(self, session):
        session.pending.set_result(None)
        session.update()
        self.assertEqual(session.phase, 'reading')
        session.pending.set_result(payload(session.profile_name))
        session.update()
        self.assertEqual(session.phase, 'complete')

    def test_calibration_homing_completion_query_and_identical_repeat(self):
        p, session = self.make()
        for _ in range(2):
            session.start()
            self.assertIsNone(session.mesh)
            self.assertEqual(session.profile_name, 'lcd_mesh_2')
            p.subscription.request.assert_called_with('printer.gcode.script',
                {'script': 'BED_MESH_CALIBRATE PROFILE=lcd_mesh_2 ADAPTIVE=0'}, guard=ANY)
            session.update()
            self.assertEqual(session.phase, 'measuring')
            self.complete(session)
            self.assertEqual(session.mesh.extrema, (-.12, .12))
        self.assertEqual(p.subscription.request.call_count, 4)
        p.sendGCode.assert_not_called()
        source = data(); source['status']['toolhead']['homed_axes'] = 'xy'
        p, session = self.make(source);session.start()
        self.assertTrue(p.subscription.request.call_args.args[1]['script'].startswith('G28\n'))

    def test_start_guards_and_duplicate_submission(self):
        for case in ('printing', 'paused', 'manual', 'probe_missing', 'mesh_missing', 'recovery', 'screws', 'probe_busy', 'pending', 'invalid_grid', 'offline', 'epoch'):
            source = data()
            if case in ('printing', 'paused'):source['status']['print_stats']['state'] = case
            if case == 'manual':source['status']['manual_probe'] = {'is_active': True}
            if case == 'probe_missing':source['objects'].remove('probe')
            if case == 'mesh_missing':source['objects'].remove('bed_mesh')
            if case == 'pending':source['status']['configfile']['save_config_pending'] = True
            if case == 'invalid_grid':source['settings']['bed_mesh']['probe_count'] = [1, 3]
            p, session = self.make(source)
            if case == 'recovery':p._jog_restore = {'script': 'restore'}
            if case == 'screws':p.screws_tilt.pending = Future()
            if case == 'probe_busy':p.probe_wizard.pending = ('step', Future(), 0)
            if case == 'offline':p.connection_error = 'offline'
            if case == 'epoch':p.subscription.snapshot.return_value = dict(source, epoch=2)
            with self.subTest(case=case),self.assertRaises(ValueError):session.start()
            p.subscription.request.assert_not_called()
        p, session = self.make();session.start()
        with self.assertRaises(ValueError):session.start()
        self.assertEqual(p.subscription.request.call_count, 1)

    def test_profile_selection_is_read_only_immutable_and_uses_probed_points(self):
        p, session = self.make();session.refresh()
        result = payload();result['status']['bed_mesh']['profiles']['PLA 60C'] = copy.deepcopy(result['status']['bed_mesh']['profiles']['lcd_mesh_1'])
        session.pending.set_result(result);session.update()
        self.assertEqual(session.entries(), (None, 'lcd_mesh_1', 'PLA 60C'))
        mesh = session.view('PLA 60C')
        self.assertEqual(mesh.points[0][0], -.12)
        result['status']['bed_mesh']['profiles']['PLA 60C']['points'][0][0] = 88
        self.assertEqual(mesh.points[0][0], -.12)
        self.assertEqual(p.subscription.request.call_count, 1)
        p.sendGCode.assert_not_called()
        with self.assertRaises(ValueError):session.view('deleted')
        source = data(); source['epoch'] = 2;p.state = PrinterState.from_snapshot(source)
        with self.assertRaises(ValueError):session.view(None)

    def test_malformed_nonfinite_dimension_and_limits(self):
        for case in ('ragged', 'nan', 'inf', 'empty', 'boolean', 'limits', 'count'):
            result = payload();status = result['status']['bed_mesh']
            if case == 'ragged':status['probed_matrix'][0].pop()
            if case == 'nan':status['probed_matrix'][0][0] = float('nan')
            if case == 'inf':status['probed_matrix'][0][0] = float('inf')
            if case == 'boolean':status['probed_matrix'][0][0] = True
            if case == 'empty':status['probed_matrix'] = [[]]
            if case == 'limits':status['mesh_max'] = status['mesh_min']
            if case == 'count':status['profiles']['lcd_mesh_1']['mesh_params']['x_count'] = 4
            with self.subTest(case=case),self.assertRaises((ValueError,TypeError)):
                mesh = MeshData.current(status);MeshData.profile('lcd_mesh_1',status)

    def test_failure_disconnect_timeout_and_stale_result_never_succeed(self):
        for case in ('command', 'disconnect', 'epoch', 'timeout', 'stale', 'profile_changed'):
            p, session = self.make();session.start()
            if case == 'command':session.pending.set_exception(MoonrakerError('probe'))
            if case == 'disconnect':p.connection_error = 'offline'
            if case == 'epoch':p.state = PrinterState.from_snapshot(dict(data(),epoch=2))
            if case in ('stale', 'profile_changed'):
                session.pending.set_result(None);session.update()
                result = payload(session.profile_name)
                if case == 'stale':result['status']['bed_mesh']['profile_name'] = 'old'
                else:result['status']['bed_mesh']['profiles'][session.profile_name]['points'] = [[1,2,3]]*3
                session.pending.set_result(result)
            with patch('bed_mesh.time.monotonic',return_value=session.started+(901 if case=='timeout' else 1)):
                session.update()
            self.assertIn(session.phase, ('error','interrupted'))
            self.assertIsNone(session.mesh)
            self.assertIsNone(session.pending)
            self.assertEqual(p.subscription.request.call_count, 2 if case in ('stale','profile_changed') else 1)

    def test_progress_deduplicates_samples_and_maps_offset_coordinates(self):
        p, session = self.make();session.start()
        p.subscription.responses_since.return_value = (4, ('probe at 60.000,40.000 is z=2.10',
            'probe at 60.000,40.000 is z=2.11', 'probe at 260,240 is z=2.20', 'probe at 999,999 is z=2.30'))
        session.update()
        self.assertEqual(session.progress, {(0,0):2.11,(2,2):2.20})
        self.assertEqual(session.message, 'Probing: 2 points')
        self.assertIsNone(session.mesh)
        self.complete(session)
        self.assertEqual(session.mesh.points[0][0], -.12)

    def test_stop_uses_emergency_rpc_and_never_marks_result_complete(self):
        p, session = self.make();session.start();future = session.pending
        session.cancel()
        p.subscription.request.assert_called_with('printer.emergency_stop', {})
        session.pending.set_result(None);session.update()
        self.assertEqual(session.phase,'stopped');self.assertIsNone(session.mesh)
        self.assertTrue(future.cancelled())
        with self.assertRaises(ValueError):session.cancel()

    def test_save_validates_owned_profile_and_config_before_restart(self):
        for foreign in (False,True):
            p, session = self.make();session.start();self.complete(session);session.save()
            self.assertEqual(session.phase,'save_check')
            result = payload(session.profile_name)
            profile = result['status']['bed_mesh']['profiles'][session.profile_name]
            fields = dict(profile['mesh_params'],version='1',points='\n'.join(','.join(str(z) for z in row) for row in profile['points']))
            items = {'bed_mesh '+session.profile_name:fields}
            if foreign:items['probe'] = {'z_offset':'2.1'}
            result['status']['configfile'] = dict(save_config_pending=True,save_config_pending_items=items)
            session.pending.set_result(result);session.update()
            if foreign:
                self.assertEqual(session.phase,'error')
                self.assertNotIn({'script':'SAVE_CONFIG'}, [c.args[1] for c in p.subscription.request.call_args_list])
            else:
                p.subscription.request.assert_called_with('printer.gcode.script', {'script':'SAVE_CONFIG'}, guard=ANY)
                p.connection_error = 'restarting';session.update()
                self.assertEqual(session.phase,'interrupted')
                self.assertIn('check after restart',session.message)

    def test_round_layout_and_string_config(self):
        source=data();source['settings']['bed_mesh']=dict(mesh_radius=100,mesh_origin='110,120',round_probe_count=5)
        _, session=self.make(source);session.start()
        self.assertEqual(session.layout,((5,5),(10,20),(210,220)))
        source=data();source['settings']['bed_mesh']=dict(mesh_min='20,30',mesh_max='220,230',probe_count='3,5')
        _,session=self.make(source);session.start();self.assertEqual(session.layout[0],(3,5))


class ResponseTests(unittest.TestCase):
    def test_independent_response_cursors_bounded_history_and_queue(self):
        sub=MoonrakerSubscription('http://localhost:7125',autostart=False)
        self.assertEqual(sub.responses_since(None),(0,()))
        for i in range(300):sub._notification({'method':'notify_gcode_response','params':[str(i)]})
        cursor,responses=sub.responses_since(0)
        self.assertEqual(cursor,300);self.assertEqual(len(responses),256)
        self.assertEqual(responses[0],'44')
        self.assertEqual(sub.responses_since(299),(300,('299',)))
        self.assertEqual(sub.responses_since(cursor),(300,()))
        self.assertEqual(sub.gcode_responses.qsize(),64)
        self.assertEqual(sub.responses_since(299),(300,('299',)))


class MeshViewTests(unittest.TestCase):
    def make(self):
        view=display(data())
        view.lcd.DWIN_WIDTH=272;view.lcd.DWIN_HEIGHT=480
        view.checkkey=view.Prepare
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.pd.subscription.request.side_effect=lambda *a, **k:Future()
        view.pd.subscription.responses_since.return_value=(0,())
        return view

    def complete(self,view):
        session=view.pd.bed_mesh
        session.pending.set_result(None);view._poll_bed_mesh()
        session.pending.set_result(payload(session.profile_name));view._poll_bed_mesh()

    def event(self,view,event):
        view.get_encoder_state.return_value=event;view._dispatch_input()

    def test_home_menu_measure_result_continue_and_back(self):
        view=self.make()
        self.assertEqual(view.PREPARE_CASE_MESH,-1)
        self.assertEqual(view.CONTROL_CASE_MESH,-1)
        view.select_page.set(3)
        view.HMI_Leveling()
        self.assertEqual(view.checkkey,view.BedMeshMenu)
        self.assertIsNone(view.pd.bed_mesh.pending)
        self.event(view,view.ENCODER_DIFF_CW)
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.BedMeshScreen)
        self.assertTrue(view.pd.bed_mesh.pending)
        self.complete(view)
        labels=[c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('Save',labels);self.assertIn('Continue',labels)
        self.event(view,view.ENCODER_DIFF_CW);self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.BedMeshMenu)
        self.assertEqual(view._mesh_menu_selection,1)
        self.assertEqual(view.pd.subscription.request.call_count,2)
        self.event(view,view.ENCODER_DIFF_CCW);self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.MainMenu)
        self.assertEqual(view.select_page.now,3)

    def test_profile_menu_refresh_selection_and_return_without_load(self):
        view=self.make();view.HMI_Leveling()
        view._mesh_menu_selection=2;view.HMI_Bed_Mesh_Menu()
        self.assertEqual(view.checkkey,view.MeshProfiles)
        result=payload('PETG 80C');view.pd.bed_mesh.pending.set_result(result);view._poll_bed_mesh()
        self.event(view,view.ENCODER_DIFF_CW);self.event(view,view.ENCODER_DIFF_CW)
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.MeshProfiles)
        view.pd.bed_mesh.pending.set_result(result);view._poll_bed_mesh()
        self.assertEqual(view.checkkey,view.BedMeshScreen)
        self.assertEqual(view.pd.bed_mesh.mesh.name,'PETG 80C')
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.MeshProfiles)
        view.pd.bed_mesh.pending.set_result(result);view._poll_bed_mesh()
        view._mesh_profile_selection=0;self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.checkkey,view.BedMeshMenu)
        self.assertTrue(all(c.args[0]=='printer.objects.query' for c in view.pd.subscription.request.call_args_list))
        view.pd.sendGCode.assert_not_called()

    def test_deleted_profile_and_absent_current_mesh_show_error(self):
        view=self.make();view._open_mesh_profiles('missing',view_after=True)
        view.pd.bed_mesh.pending.set_result(payload());view._poll_bed_mesh()
        self.assertEqual(view.pd.bed_mesh.phase,'error')
        self.assertIsNone(view.pd.bed_mesh.mesh)
        self.assertEqual(view.checkkey,view.MeshProfiles)
        self.event(view,view.ENCODER_DIFF_ENTER);self.assertEqual(view.checkkey,view.BedMeshMenu)
        view._open_mesh_profiles(None,view_after=True)
        result=payload();result['status']['bed_mesh']['probed_matrix']=[[]]
        view.pd.bed_mesh.pending.set_result(result);view._poll_bed_mesh()
        self.assertEqual(view.pd.bed_mesh.phase,'error')

    def test_cancel_requires_explicit_stop_and_completion_closes_old_confirmation(self):
        view=self.make();view._start_bed_mesh(view.Prepare)
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._mesh_confirmation,'cancel')
        self.assertEqual(view.pd.subscription.request.call_count,1)
        self.event(view,view.ENCODER_DIFF_ENTER)  # default Back
        self.assertIsNone(view._mesh_confirmation)
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.complete(view)
        self.assertIsNone(view._mesh_confirmation)
        self.assertEqual(view.pd.bed_mesh.phase,'complete')
        view._mesh_button_selection=1;self.event(view,view.ENCODER_DIFF_ENTER)
        view._start_bed_mesh(view.Prepare)
        self.event(view,view.ENCODER_DIFF_ENTER);self.event(view,view.ENCODER_DIFF_CW)
        self.event(view,view.ENCODER_DIFF_ENTER)
        view.pd.subscription.request.assert_called_with('printer.emergency_stop',{})
        self.assertEqual(view.pd.bed_mesh.phase,'stopping')

    def test_save_confirmation_has_profile_and_restart_warning(self):
        view=self.make();view._start_bed_mesh(view.Prepare);self.complete(view)
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view._mesh_confirmation,'save')
        labels=[c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn(view.pd.bed_mesh.profile_name,labels)
        self.assertIn('Klipper will restart',labels)
        self.assertEqual(view.pd.subscription.request.call_count,2)
        self.event(view,view.ENCODER_DIFF_CW);self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.pd.bed_mesh.phase,'save_check')
        self.event(view,view.ENCODER_DIFF_ENTER)
        self.assertEqual(view.pd.subscription.request.call_count,3)

    def test_profile_scrolling_and_long_names_fit_six_rows(self):
        view=self.make();session=view.pd.bed_mesh
        session.refresh();result=payload();profile=result['status']['bed_mesh']['profiles']['lcd_mesh_1']
        result['status']['bed_mesh']['profiles']={f'Profile {i:02d} '+('Ç'*50):profile for i in range(12)}
        session.pending.set_result(result);session.update()
        view.checkkey=view.MeshProfiles;view._mesh_profile_selection=13
        view.lcd.reset_mock();view.Draw_Mesh_Profiles()
        labels=[c.args for c in view.lcd.draw_text.call_args_list if c.args[5]==view.LBLX]
        self.assertEqual(len(labels),6)
        for args in labels:
            self.assertLessEqual(args[5]+len(args[-1])*8,272)
            self.assertLess(args[6]+16,360)
            self.assertTrue(args[-1].isascii())
        self.event(view,view.ENCODER_DIFF_CW);self.assertEqual(view._mesh_profile_selection,13)
        self.event(view,view.ENCODER_DIFF_CCW);self.assertEqual(view._mesh_profile_selection,12)

    def test_mesh_orientation_colors_radius_and_text_bounds(self):
        functions=self.make()._draw_mesh_grid.__globals__
        point_style,point_label=functions['point_style'],functions['point_label']
        self.assertEqual(point_style(-.2,5)[0],28)
        self.assertEqual(point_style(0,5)[0],38<<5)
        self.assertEqual(point_style(.2,5)[0],28<<11)
        self.assertLess(point_style(-.2,5)[1],point_style(.2,5)[1])
        view=self.make()
        view._draw_mesh_grid(3,3,{(0,0):-.12,(2,2):.12})
        strings=view.lcd.draw_text.call_args_list
        negative=next(c.args for c in strings if c.args[-1]=='-0.12')
        positive=next(c.args for c in strings if c.args[-1]=='+0.12')
        self.assertEqual(negative[6],271) # low Y at the bottom
        self.assertEqual(positive[6],49)
        self.assertLess(negative[5],positive[5])
        for columns,rows in ((3,3),(5,7),(9,9),(15,15),(25,25)):
            view.lcd.reset_mock()
            view._draw_mesh_grid(columns,rows,{(x,y):(-.2+(x+y)/10) for x in range(columns) for y in range(rows)})
            for call in view.lcd.draw_text.call_args_list:
                args=call.args;self.assertGreaterEqual(args[5],0)
                self.assertLessEqual(args[5]+len(args[-1])*6,272)
                self.assertGreaterEqual(args[6],31);self.assertLessEqual(args[6]+12,300)
            boxes=[(call.args[5],call.args[6],call.args[5]+len(call.args[-1])*6,call.args[6]+12)
                   for call in view.lcd.draw_text.call_args_list]
            for index,(x1,y1,x2,y2) in enumerate(boxes):
                for a1,b1,a2,b2 in boxes[index+1:]:
                    self.assertFalse(x1<a2 and a1<x2 and y1<b2 and b1<y2, 'overlapping mesh labels')
            for call in view.lcd.draw_rectangle.call_args_list:
                _,_,x1,y1,x2,y2=call.args
                self.assertGreaterEqual(x1,0);self.assertLessEqual(x2,271)
                self.assertGreaterEqual(y1,31);self.assertLessEqual(y2,300)
        self.assertEqual(point_label(123,5),'######')

    def test_control_navigation_uses_discovered_rows_while_scrolling(self):
        view=self.make();view.checkkey=view.Control
        view._menus['control'] += [('EXTRA','Extra',view.ICON_Info)]*3
        view._configure_menus=Mock()
        view.select_control.set(5);view.index_control=5
        self.event(view,view.ENCODER_DIFF_CW)
        self.assertEqual(view.select_control.now,6)
        self.assertEqual(view.index_control,6)
        view.pd.subscription.request.assert_not_called()


class MeshSaveRegressionTests(unittest.TestCase):
    make = MeshTests.make
    complete = MeshTests.complete
    def pending_config(self,session):
        profile=session.status['profiles'][session.profile_name]
        fields=dict(profile['mesh_params'],version='1',points='\n'.join(','.join(str(z) for z in row) for row in profile['points']))
        return dict(save_config_pending=True,save_config_pending_items={'bed_mesh '+session.profile_name:fields})

    def test_repeat_with_owned_pending_profile_reuses_name(self):
        p,session=self.make();session.start();self.complete(session)
        name=session.profile_name
        source=data();source['status']['bed_mesh']=copy.deepcopy(session.status)
        source['status']['configfile']=self.pending_config(session)
        p.state=PrinterState.from_snapshot(source)
        p.subscription.snapshot.return_value=source
        session.start();self.assertEqual(session.profile_name,name)
        self.complete(session)
        self.assertEqual(session.phase,'complete')

    def test_modified_pending_points_or_settings_cannot_be_persisted(self):
        for case in ('points','limits','version','missing','foreign','active_changed','profile_changed'):
            p,session=self.make();session.start();self.complete(session);session.save()
            result=payload(session.profile_name);result['status']['configfile']=self.pending_config(session)
            fields=result['status']['configfile']['save_config_pending_items']['bed_mesh '+session.profile_name]
            if case=='points':fields['points']='1,2,3\n4,5,6\n7,8,9'
            if case=='limits':fields['min_x']=99
            if case=='version':fields['version']=2
            if case=='missing':del fields['points']
            if case=='foreign':result['status']['configfile']['save_config_pending_items']['probe']={'z_offset':2}
            if case=='active_changed':result['status']['bed_mesh']['profile_name']='other'
            if case=='profile_changed':result['status']['bed_mesh']['profiles'][session.profile_name]['points']=[[1,2,3]]*3
            session.pending.set_result(result);session.update()
            with self.subTest(case=case):
                self.assertEqual(session.phase,'error')
                self.assertNotIn({'script':'SAVE_CONFIG'},[c.args[1] for c in p.subscription.request.call_args_list])

    def test_no_restart_from_readonly_profile_or_printing(self):
        p,session=self.make();session.refresh();session.pending.set_result(payload());session.update();session.view('lcd_mesh_1')
        with self.assertRaises(ValueError):session.save()
        session.start();self.complete(session);p.status='printing'
        with self.assertRaises(ValueError):session.save()

    def test_conflicting_calibrations_block_on_active_mesh(self):
        p,session=self.make();session.start()
        with self.assertRaises(ValueError):p.screws_tilt.start()
        with self.assertRaises(ValueError):p.probe_wizard.start()

    def test_cancellation_checks_current_transport_epoch(self):
        p,session=self.make();session.start();p.subscription.snapshot.return_value=dict(data(),epoch=2)
        with self.assertRaises(ValueError):session.cancel()
        self.assertEqual(p.subscription.request.call_count,1)


class MeshLifecycleTests(unittest.TestCase):
    make = MeshViewTests.make
    complete = MeshViewTests.complete

    def test_tick_does_not_reuse_encoder_press(self):
        view=self.make();view._start_bed_mesh(view.Prepare)
        view.last_status=view.pd.status
        view._offline=False;view._print_error_visible=False
        view.HMI_Bed_Mesh=Mock();view.HMI_Mesh_Profiles=Mock()
        view._poll_case_light_query=Mock();view._poll_action=Mock(return_value=False)
        view._poll_print_start=Mock(return_value=False)
        view.EachMomentUpdate()
        view.HMI_Bed_Mesh.assert_not_called();view.HMI_Mesh_Profiles.assert_not_called()
        self.assertIsNone(view._mesh_confirmation)
        self.assertEqual(view.pd.subscription.request.call_count,1)

    def test_uart_reconnect_redraws_mesh_without_replaying_commands(self):
        from test_regressions import ui
        view=self.make();view._start_bed_mesh(view.Prepare)
        view._closed=False;view._settings=('/dev/fake',);view._uart_epoch=0
        view._uart_online=False;view._next_uart_retry=0
        view.HMI_Init=Mock();view.HMI_StartFrame=Mock();view.Draw_Bed_Mesh=Mock()
        with patch.object(ui,'T5UIC1Display',return_value=Mock()):
            self.assertTrue(view._ensure_uart())
        view.Draw_Bed_Mesh.assert_called_once()
        self.assertEqual(view.pd.subscription.request.call_count,1)

    def test_offline_mesh_tick_keeps_interruption_message(self):
        view=self.make();view._start_bed_mesh(view.Prepare)
        view.pd.update_variable=Mock(return_value=False);view.pd.connection_error='offline'
        view._show_message=Mock();view.EachMomentUpdate()
        self.assertEqual(view.pd.bed_mesh.phase,'interrupted')
        view._show_message.assert_not_called()
        self.assertIsNone(view.pd.bed_mesh.mesh)

    def test_home_shortcut_opens_menu_without_calibration_even_when_printing(self):
        view=self.make();view.pd.status='printing';view.checkkey=view.Leveling
        view.HMI_Leveling()
        self.assertEqual(view.checkkey,view.BedMeshMenu)
        view.pd.subscription.request.assert_not_called()
        view._mesh_menu_selection=1;view.HMI_Bed_Mesh_Menu()
        self.assertEqual(view.checkkey,view.BedMeshMenu)
        view.pd.subscription.request.assert_not_called()


class MeshPacketTests(unittest.TestCase):
    def test_real_driver_builds_result_and_profile_menu_frames(self):
        from test_t5uic1_driver import driver as make_driver
        view=MeshViewTests.make(self)
        driver=make_driver();driver._needs_update=False
        driver._atlas_synced=True
        driver._atlas_virtual_areas_loaded=True
        driver._virtual_area_pictures={0:14}
        view.lcd=driver
        view.pd.bed_mesh.status=payload()['status']['bed_mesh']
        view.pd.bed_mesh.mesh=MeshData.current(view.pd.bed_mesh.status)
        view.pd.bed_mesh.phase='complete'
        view.Draw_Bed_Mesh()
        frames=driver.MYSERIAL1.frames
        self.assertTrue(all(f.startswith(b'\xaa') and f.endswith(b'\xcc\x33\xc3\x3c') for f in frames))
        self.assertTrue(any(b'Save' in f for f in frames))
        self.assertTrue(any(b'Continue' in f for f in frames))
        self.assertTrue(any(b'-0.12' in f for f in frames))
        self.assertEqual(frames[-1][1],0x3d)
        view.pd.bed_mesh.phase='listed';view.Draw_Mesh_Profiles()
        self.assertTrue(any(b'lcd_mesh_1' in f for f in frames))
        view.pd.subscription.request.assert_not_called()


class MeshMenuTests(unittest.TestCase):
    make=MeshViewTests.make

    def test_mesh_entries_are_only_in_home_submenu(self):
        view=self.make();view.HMI_Leveling()
        self.assertEqual([e[0] for e in view._mesh_menu_entries()],['BACK','CALIBRATE','VIEWER'])
        for name in ('prepare','control'):
            self.assertNotIn('MESH',[e[0] for e in view._menus[name]])
            self.assertFalse(any(e[1] in ('Bed Mesh Calibrate','Mesh Viewer') for e in view._menus[name]))
        labels=[c.args[-1] for c in view.lcd.draw_text.call_args_list]
        self.assertIn('Bed Mesh Calibrate',labels);self.assertIn('Mesh Viewer',labels)
        view.pd.subscription.request.assert_not_called()

    def test_without_probe_home_menu_still_has_profile_viewer(self):
        source=data();source['objects'].remove('probe')
        view=display(source);view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.pd.subscription.request.side_effect=lambda *a, **k:Future()
        self.assertTrue(view.pd.HAS_ONESTEP_LEVELING)
        view.HMI_Leveling()
        self.assertEqual([e[0] for e in view._mesh_menu_entries()],['BACK','VIEWER'])
        view._mesh_menu_selection=1;view.HMI_Bed_Mesh_Menu()
        self.assertEqual(view.checkkey,view.MeshProfiles)
        view.pd.subscription.request.assert_called_once_with('printer.objects.query',{'objects':{'bed_mesh':None}})

    def test_menu_cursor_bounds_and_capability_removal(self):
        view=self.make();view.HMI_Leveling()
        view.get_encoder_state.return_value=view.ENCODER_DIFF_CW
        for _ in range(5):view.HMI_Bed_Mesh_Menu()
        self.assertEqual(view._mesh_menu_selection,2)
        view.pd.capabilities=type(view.pd.capabilities)()
        view.Draw_Bed_Mesh_Menu()
        self.assertEqual(view._mesh_menu_selection,0)
        self.assertEqual([e[0] for e in view._mesh_menu_entries()],['BACK'])
        view.pd.subscription.request.assert_not_called()

    def test_uart_reconnect_redraws_mesh_menu_without_starting_measurement(self):
        from test_regressions import ui
        view=self.make();view.HMI_Leveling();view._mesh_menu_selection=2
        view._closed=False;view._settings=('/dev/fake',);view._uart_epoch=0
        view._uart_online=False;view._next_uart_retry=0
        view.HMI_Init=Mock();view.HMI_StartFrame=Mock();view.Draw_Bed_Mesh_Menu=Mock()
        with patch.object(ui,'T5UIC1Display',return_value=Mock()):
            self.assertTrue(view._ensure_uart())
        view.Draw_Bed_Mesh_Menu.assert_called_once()
        self.assertEqual(view._mesh_menu_selection,2)
        view.pd.subscription.request.assert_not_called()
