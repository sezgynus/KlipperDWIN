"""CI-only recorder regressions: actual controllers, UI routing and HTTP."""
from concurrent.futures import Future
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import unittest
import zipfile

import test_maintenance_heater as thermal
from test_maintenance_controller import Worker
from maintenance_controller import MaintenanceReadController
from maintenance_heater import MaintenancePhysicalRouter
from maintenance_test_trace import TestTrace, OwnerProxy, WorkerProxy, SubscriptionProxy, MAX_PENDING, clean
from printerInterface import PrinterData


def unpack(trace):
    with zipfile.ZipFile(BytesIO(trace.exported())) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        events = []
        for name in ('events.previous.jsonl','events.jsonl','pending.jsonl'):
            if name in archive.namelist():
                events.extend(json.loads(line) for line in archive.read(name).splitlines())
    return manifest,events


class TestRecorder(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = thermal.ThermalControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.p = self.fixture.p
        self.p.maintenance_pulse = MaintenancePhysicalRouter(None,self.fixture.c)
        self.p.maintenance_reader = MaintenanceReadController(self.p,self.fixture.worker,self.fixture.client)
        self.p._read_worker = Worker()
        self.trace = TestTrace(self.p,Path(self.temp.name)/'trace')
        self.p.maintenance_test_trace = self.trace

    def arm(self):
        self.assertTrue(self.trace.start())
        self.assertTrue(self.p.maintenance_pulse.start('H01','extruder')[0])
        self.fixture.worker.drain()
        self.p.maintenance_pulse.poll()
        self.assertEqual(self.p.maintenance_pulse.phase,'await_confirmation')
        self.assertEqual(self.fixture.requests,[])

    def test_real_heat_shutdown_keeps_reason_temperature_and_exact_future(self):
        self.arm()
        self.p.maintenance_pulse.confirm()
        self.assertIs(self.fixture.c._command,self.fixture.heat)
        self.fixture.clock = 2.
        self.fixture.data['status']['extruder'].update(temperature=70.38,power=0.)
        self.p.maintenance_pulse.poll()
        self.fixture.worker.drain()
        self.p.maintenance_pulse.poll()
        self.assertEqual(self.fixture.requests[-1][0],'printer.emergency_stop')
        result = self.p.maintenance_pulse.poll()
        self.assertEqual(result.status,'INCONCLUSIVE')
        _,events = unpack(self.trace)
        shutdown = next(e for e in events if e['event']=='safety_shutdown')
        self.assertIn('thermal_temperature_limit',shutdown['data']['reason'])
        self.assertEqual(shutdown['data']['snapshot']['last_read_point']['temperature'],70.38)
        self.assertTrue(any(e['event']=='result' and e['data']['reason']==result.reason for e in events))
        self.assertEqual(len(self.fixture.requests),2)

    def test_long_wait_remains_waiting_and_stop_restores_original_owners(self):
        pulse,reader = self.p.maintenance_pulse,self.p.maintenance_reader
        client,printer = self.fixture.c._client,self.fixture.c._printer
        self.arm()
        self.fixture.clock = 10000.
        self.p.maintenance_pulse.poll()
        self.assertEqual(self.p.maintenance_pulse.phase,'await_confirmation')
        self.assertEqual(self.fixture.requests,[])
        # UI toggle cannot stop an active test or implicitly cancel it.
        self.assertFalse(PrinterData.toggle_maintenance_test_recording(self.p))
        self.p.maintenance_pulse.cancel()
        self.trace.stop()
        self.assertIs(self.p.maintenance_pulse,pulse)
        self.assertIs(self.p.maintenance_reader,reader)
        self.assertIs(self.fixture.c._client,client)
        self.assertIs(self.fixture.c._printer,printer)

    def test_command_guard_kwargs_and_ambiguous_errors_are_never_replayed(self):
        self.arm()
        self.fixture.data['status']['extruder']['temperature'] = 55.
        self.p.maintenance_pulse.confirm()
        result = self.p.maintenance_pulse.poll()
        self.assertEqual(result.status,'BLOCKED')
        self.assertEqual(len(self.fixture.requests),1)
        self.assertFalse(self.fixture.c._blocked)

    def test_read_controller_slots_and_worker_error_keep_original_reason(self):
        self.trace.start()
        worker = WorkerProxy(Worker(),self.trace)
        def fail():
            raise ValueError('home_xyz_before_workflow')
        future = worker.submit(fail)
        worker._target.drain()
        with self.assertRaisesRegex(ValueError,'home_xyz_before_workflow'):
            future.result()
        self.assertTrue(any(e['event']=='worker_error' and
            e['data']['code']=='home_xyz_before_workflow' for e in unpack(self.trace)[1]))
        self.trace.stop()

    def test_late_rpc_completion_keeps_original_attempt_identity(self):
        self.trace.start()
        self.trace.run = 7
        future = Future()
        call = Mock(return_value=future)
        transport = SubscriptionProxy(SimpleNamespace(request=call),self.trace)
        guard = lambda:False
        self.assertIs(transport.request('printer.gcode.script',{'script':'G1 X1'},guard=guard),future)
        self.trace.run = 8
        future.set_exception(ValueError('command_ambiguous'))
        error = next(e for e in unpack(self.trace)[1] if e['event']=='rpc_error')
        self.assertEqual(error['run'],7)
        self.assertIs(call.call_args.kwargs['guard'],guard)
        call.assert_called_once()

    def test_rpc_guard_and_server_errors_retain_safe_diagnostics(self):
        from moonraker_client import MoonrakerError
        self.trace.start()
        for message,stage,expected in (
                ('Printer state changed before command dispatch','guard_denied','rpc_guard_denied'),
                ('Moonraker command failed; check printer','server_error','moonraker_server_error')):
            future=Future()
            future.dispatch_stage=stage
            error=MoonrakerError(message)
            if stage=='server_error':
                error.rpc_code=400
            future.set_exception(error)
            SubscriptionProxy(SimpleNamespace(request=Mock(return_value=future)),self.trace).request(
                'printer.gcode.script',{'script':'M400'})
            event=[e for e in unpack(self.trace)[1] if e['event']=='rpc_error'][-1]
            self.assertEqual(event['data']['code'],expected)
            self.assertEqual(event['data']['dispatch_stage'],stage)
            if stage=='server_error':
                self.assertEqual(event['data']['rpc_code'],400)

    def test_motion_read_records_motor_mesh_and_velocity_guard_evidence(self):
        from maintenance_test_trace import measurements
        values=measurements({'result':{'status':{
            'toolhead':{'max_velocity':300},
            'stepper_enable':{'steppers':{'stepper_x':True,'stepper_y':True,'stepper_z':True}},
            'bed_mesh':{'profile_name':'','mesh_min':[0,0],'mesh_max':[0,0],
                        'mesh_matrix':[[1]*100]*100}}}})
        self.assertEqual(values['toolhead']['max_velocity'],300)
        self.assertTrue(values['stepper_enable']['steppers']['stepper_x'])
        self.assertEqual(values['bed_mesh']['mesh_min'],[0,0])
        self.assertNotIn('mesh_matrix',values['bed_mesh'])

    def test_static_mmu_errors_and_spaced_ui_labels_survive_without_paths(self):
        from maintenance_test_trace import error_info,measurements
        self.assertEqual(error_info(ValueError('Unload filament first'))['code'],'mmu_unload_filament_first')
        self.assertEqual(error_info(ValueError('secret token=123'))['code'],'details_omitted')
        self.assertEqual(clean('Red seen / next'),'Red seen / next')
        for value in ('/etc/private','home/pi/private','http://secret.local'):
            self.assertEqual(clean(value),'[omitted]')
        self.assertEqual(measurements({'result':{'status':{
            'tmc2208 stepper_x':{'drv_status':None},
            'mmu':{'filament':'unloaded','gate':0,'locked':False,'password':'never'}
        }}})['tmc2208 stepper_x'],{'drv_status':None})
        self.assertNotIn('password',measurements({'result':{'status':{'mmu':{'password':'never'}}}})['mmu'])

    def test_zip_includes_unsaved_tail_is_read_only_and_sanitizes_secrets(self):
        self.trace.emit('example',{'password':'bad','filename':'private.gcode',
            'evidence':(('api_key','bad'),('temperature',60.)),
            'url':'http://secret.local/path','value':float('nan')})
        before = tuple(self.trace._pending)
        manifest,events = unpack(self.trace)
        self.assertEqual(tuple(self.trace._pending),before)
        self.assertFalse(self.trace.directory.exists())
        raw = json.dumps(events)
        self.assertNotIn('private.gcode',raw)
        self.assertNotIn('bad',raw)
        self.assertNotIn('secret.local',raw)
        self.assertEqual(manifest['pending_events'],1)

    def test_bounded_retention_gap_manifest_and_failed_disk_do_not_stop_heat(self):
        for i in range(MAX_PENDING+5):
            self.trace.emit('fill',{'n':i})
        manifest,_ = unpack(self.trace)
        self.assertEqual(manifest['dropped_events'],5)
        self.assertEqual(manifest['pending_events'],MAX_PENDING)
        self.arm()
        with patch.object(Path,'mkdir',side_effect=OSError('disk_full')):
            self.trace.flush()
        self.assertGreater(self.trace.write_errors,0)
        self.assertTrue(self.p.maintenance_pulse.confirm()[0])
        self.assertEqual(self.fixture.requests[0][0],'printer.gcode.script')

    def test_rotated_files_survive_restart_and_report_rotation(self):
        from maintenance_test_trace import MAX_LINE
        self.trace.emit('first')
        with patch('maintenance_test_trace.MAX_FILE',MAX_LINE):
            self.trace.flush()
            for i in range(20):
                self.trace.emit('fill',{'values':['x'*200]*8})
            self.trace.flush()
        self.assertGreater(self.trace.rotations,0)
        later = TestTrace(self.p,self.trace.directory)
        manifest,events = unpack(later)
        self.assertTrue(any(e['event']=='first' for e in events))

    def test_ui_logs_selected_row_parent_and_unexpected_list_return(self):
        self.arm()
        view = SimpleNamespace(checkkey=42,MaintenanceMenu=42,RecoveryScreen=43,
            _maintenance_page='pulse',_maintenance_selection=1,
            _maintenance_result_parent='tests',_maintenance_result_selection=19)
        event = SimpleNamespace(kind='press',value=1,epoch=12,ui_epoch=2)
        self.trace.ui(view,'input_before',event,'Confirm H01',
            [('Cancel',),('Run thermal test',)])
        view._maintenance_page='tests'
        view._maintenance_selection=19
        self.trace.ui(view,'input_after',event,'Self Tests',[(str(i),) for i in range(25)])
        event_log = [e for e in unpack(self.trace)[1] if e['event']=='ui'][-1]['data']
        self.assertEqual(event_log['from']['page'],'pulse')
        self.assertEqual(event_log['to']['page'],'tests')
        self.assertEqual(event_log['to']['drawn']['selected_label'],'19')
        self.assertEqual(event_log['to']['physical']['phase'],'await_confirmation')
        self.assertTrue(any(e['event']=='ui_anomaly' and
            e['data']['code']=='left_test_while_pending' for e in unpack(self.trace)[1]))
        view.checkkey=43
        self.trace.ui(view)
        self.assertTrue([e for e in unpack(self.trace)[1] if e['event']=='ui'][-1]['data']['to']['pending_offscreen'])

    def test_confirmation_refresh_is_explicit_in_ui_flow_log(self):
        self.arm()
        view=SimpleNamespace(checkkey=42,MaintenanceMenu=42,
            _maintenance_page='pulse',_maintenance_selection=1)
        self.trace.ui(view,'draw',title='Confirm clear path',
                      entries=[('Cancel',),('Home XYZ',)])
        self.fixture.c._phase='preflight'
        self.fixture.c._confirm_attempts=1
        self.fixture.c._refresh_reason='motion_confirmation_evidence_expired'
        self.trace.ui(view,'draw',title='Refreshing safety',entries=[('Cancel checks',)])
        flow=next(e for e in unpack(self.trace)[1] if e['event']=='ui_flow')
        self.assertEqual(flow['data']['code'],'confirmation_safety_refresh')
        self.assertEqual(flow['data']['physical']['confirm_attempts'],1)
        self.assertEqual(flow['data']['physical']['refresh_reason'],
                         'motion_confirmation_evidence_expired')


class TestRecorderUI(unittest.TestCase):
    def test_start_stop_recording_menu_does_not_dispatch_any_test(self):
        from test_capabilities import display,snapshot
        d = display(snapshot())
        d._maintenance_page='root'
        d._maintenance_selection=3
        d.pd.maintenance_test_recording_label=Mock(return_value='Start test recording')
        d.pd.toggle_maintenance_test_recording=Mock(return_value=True)
        d.pd.start_maintenance_physical=Mock()
        d.pd.start_maintenance_read=Mock()
        d.get_encoder_state=Mock(return_value=d.ENCODER_DIFF_ENTER)
        self.assertEqual(d._maintenance_rows()[1][3][0],'Start test recording')
        d.HMI_Maintenance_Menu()
        d.pd.toggle_maintenance_test_recording.assert_called_once()
        d.pd.start_maintenance_physical.assert_not_called()
        d.pd.start_maintenance_read.assert_not_called()

    def test_input_and_periodic_wrappers_record_after_early_recovery_return(self):
        from test_capabilities import display,snapshot
        d = display(snapshot())
        trace = Mock(active=True)
        d.pd.maintenance_test_trace=trace
        d._process_input_untraced=Mock(return_value='recovery')
        event = SimpleNamespace(kind='press')
        self.assertEqual(d._process_input(event),'recovery')
        self.assertEqual([call.args[1] for call in trace.ui.call_args_list],
                         ['input_before','input_after'])
        d._each_moment_update_untraced=Mock(return_value=None)
        d.EachMomentUpdate()
        self.assertEqual(trace.ui.call_args.args[1],'tick')


class TestRecorderHTTP(unittest.TestCase):
    def test_zip_endpoint_is_bounded_read_only_host_and_origin_protected(self):
        from dwin_emulator.remote import RemoteDisplayServer
        from test_remote_display import FakeEmulator
        emulator = FakeEmulator()
        provider = Mock(return_value=b'zip bytes')
        server = RemoteDisplayServer(emulator,Mock(),host='127.0.0.1',port=0,trace_provider=provider)
        self.addCleanup(server.close)
        base = 'http://127.0.0.1:%d'%server.port
        with urlopen(base+'/maintenance-test-trace.zip',timeout=3) as response:
            self.assertEqual(response.read(),b'zip bytes')
            self.assertEqual(response.headers['Content-Type'],'application/zip')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(emulator.calls,0)
        for headers in ({'Host':'evil.example'},{'Origin':'http://evil.example'}):
            with self.assertRaises(HTTPError) as err:
                urlopen(Request(base+'/maintenance-test-trace.zip',headers=headers),timeout=3)
            self.assertEqual(err.exception.code,403)
        provider.return_value=b'x'*(10*1024*1024+1)
        with self.assertRaises(HTTPError) as err:
            urlopen(base+'/maintenance-test-trace.zip',timeout=3)
        self.assertEqual(err.exception.code,503)


if __name__=='__main__':
    unittest.main()
