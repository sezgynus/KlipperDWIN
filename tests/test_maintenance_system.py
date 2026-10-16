"""CI-only system evidence, bounded persistence and local panel observation."""
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
import test_maintenance_probe as fixture
from maintenance_records import MaintenanceBook,read_json
from maintenance_system import read_fields,path_for
from maintenance_panel import MaintenancePanelController,COLORS
from maintenance_discovery import MaintenanceSnapshot,_add,USER
from maintenance_services import parse_evidence
from maintenance_catalog import definition_for


class SystemFieldTests(unittest.TestCase):
    def test_capacity_does_not_retain_directory_filenames(self):
        reply = {'result':{'files':[{'filename':'private-name'}],
                           'disk_usage':{'total':100,'used':40,'free':60}}}
        evidence = read_fields('S04',reply)
        self.assertEqual(dict(evidence)['free_bytes'],60)
        self.assertNotIn('private-name',str(evidence))

    def test_mcu_instances_and_can_nulls_do_not_become_pass_or_fault(self):
        reply = {'result':{'eventtime':1.,'status':{
            'mcu':{'last_stats':{'mcu_awake':.1}},
            'mcu aux':{'last_stats':{'mcu_awake':.2}}}}}
        self.assertEqual(len(read_fields('S06',reply)),2)
        self.assertEqual(read_fields('S07',{'result':{'eventtime':1.,'status':{'canbus_stats mcu':{'rx_error':None}}}},'canbus_stats mcu'),())

    def test_events_export_only_classified_errors_not_tokens_or_paths(self):
        reply = {'result':{'gcode_store':[{'message':'!! Shutdown due to webhooks request secret=/tmp/private'},
                                          {'message':'Authorization: abc'}]}}
        evidence = dict(read_fields('S09',reply))
        self.assertEqual(evidence['last_error_code'],'webhook_shutdown')
        self.assertNotIn('private',str(evidence))
        self.assertNotIn('abc',str(evidence))
        self.assertIn('gcode_store',parse_evidence({'/server/info':{'result':{'components':['data_store']}}}))

    def test_travel_never_falls_back_to_sampled_commanded_position(self):
        state = SimpleNamespace(objects=('motion_report',))
        with patch('maintenance_system.travel_profile',return_value=None):
            with self.assertRaises(ValueError):
                path_for('S13',None,state)
        self.assertEqual(read_fields('S13',{'result':{'eventtime':1.,'status':{'motion_report':{'live_position':[1,2,3]}}}}),())

    def test_absent_warning_source_is_not_fabricated_zero(self):
        from maintenance_executor import _read_fields
        self.assertEqual(_read_fields('S08',{'result':{'status':{'webhooks':{'state':'ready'}}}}),
                         (('webhooks_state','ready'),))
        fields = dict(_read_fields('S08',{'result':{'status':{
            'webhooks':{'state':'ready'},'configfile':{'warnings':['one','two']}}}}))
        self.assertEqual(fields['configuration_warnings'],2)

    def test_visual_lcd_method_is_registered_without_removing_information(self):
        from maintenance_discovery import INFORMATION
        self.assertTrue(definition_for('S16').methods & USER)
        self.assertTrue(definition_for('S16').methods & INFORMATION)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = patch('maintenance_records.root',return_value=Path(self.temp.name))
        p.start()
        self.addCleanup(p.stop)
        self.worker = fixture.Worker()
        self.book = MaintenanceBook(self.worker)
        self.state = SimpleNamespace(ready=True,epoch=1,software_version='v1',
            settings={'fan':{}},status={'fan':{'speed':1.}})

    def test_usage_excludes_unobserved_long_intervals(self):
        for stamp in (0.,1.,10.):
            self.book.note(self.state,stamp)
        self.book.flush()
        data = read_json('maintenance-usage.json',{})
        self.assertEqual(data['sampled_on_s']['fan'],1.)
        self.assertEqual(data['coverage'],'sampled_lower_bound_not_lifetime')

    def test_history_and_explicit_export_are_sanitized_and_versioned(self):
        result = SimpleNamespace(feature_id='H01',device='extruder',status='PASSED',
            reason='measured',evidence=(('temperature',60.),('token','https://private/secret')))
        self.book.record(result,1,self.state)
        self.worker.drain()
        self.assertEqual(dict(self.book.read('S11'))['recorded_results'],1)
        evidence = dict(self.book.read('S20'))
        self.assertTrue(evidence['report_ready'])
        exported = self.book.exported().decode()
        self.assertIn('config_digest',exported)
        self.assertNotIn('private',exported)
        self.assertNotIn('secret',exported)

    def test_bad_or_oversized_records_fail_closed(self):
        target = Path(self.temp.name)/'maintenance-history.json'
        target.write_text('x'*65537)
        with self.assertRaises(ValueError):
            self.book.read('S11')


class PanelTests(unittest.TestCase):
    def setUp(self):
        fixture.ProbeWorkflowTests.setUp(self)
        self.owner = MaintenancePanelController(self.p,self.worker,self.client)
        modes = _add(_add(_add(0,'S15',USER),'S16',USER),'S17',USER)
        self.p.maintenance.snapshot = MaintenanceSnapshot(12,global_modes=modes,
                                          config_marker=id(self.p.state.settings))
        self.calls = []
        def api(action,*args):
            self.calls.append((action,args))
            if action=='info':
                return {'uart_epoch':9}
            if action=='capture':
                return 156
            return True
        self.p._maintenance_panel_api = api

    get = fixture.ProbeWorkflowTests.get
    request = fixture.ProbeWorkflowTests.request
    responses = fixture.ProbeWorkflowTests.responses

    def arm(self,feature):
        self.assertTrue(self.owner.start(feature)[0])
        self.worker.drain()
        self.owner.poll()
        self.assertEqual(self.owner.phase,'await_confirmation')
        self.assertEqual(self.calls,[])
        self.clock += 100000
        self.assertIsNone(self.owner.poll())
        self.owner.confirm()
        self.worker.drain()
        self.owner.poll()

    def test_backlight_three_explicit_stages_restore_without_saving(self):
        self.arm('S17')
        for i in range(2):
            self.owner.choose(0)
            self.worker.drain()
            self.owner.poll()
        self.owner.choose(0)
        self.assertEqual(self.owner.phase,'await_observation')
        self.assertEqual([args[0] for action,args in self.calls if action=='brightness'],[10,50,100])
        self.assertIn(('restore',(156,9)),self.calls)
        result = self.owner.observe(True)
        self.assertEqual(result.status,'PASSED_USER')

    def test_worker_pressure_does_not_skip_a_visible_backlight_stage(self):
        self.arm('S17')
        with patch.object(self.worker,'submit',side_effect=RuntimeError('full')):
            self.assertFalse(self.owner.choose(0)[0])
        self.assertEqual(self.owner.phase,'workflow')
        self.assertEqual(self.owner._index,0)
        self.assertIn('10%',self.owner.workflow_choices[0][0])

    def test_restore_failure_keeps_a_valid_retryable_panel_stage(self):
        self.arm('S17')
        for i in range(2):
            self.owner.choose(0)
            self.worker.drain()
            self.owner.poll()
        api = self.p._maintenance_panel_api
        def fail_restore(action,*args):
            if action=='restore':
                raise IOError('offline')
            return api(action,*args)
        self.p._maintenance_panel_api = fail_restore
        self.assertFalse(self.owner.choose(0)[0])
        self.assertEqual(self.owner.phase,'workflow')
        self.assertIn('100%',self.owner.workflow_choices[0][0])

    def test_encoder_requires_new_physical_steps_both_ways_and_a_click(self):
        gpio = {'uart_epoch':9,'gpio_positive_steps':0,'gpio_negative_steps':0,'gpio_button_presses':0}
        self.p._maintenance_panel_api = lambda action,*args:dict(gpio)
        self.arm('S15')
        self.assertFalse(self.owner.choose(0)[0])
        gpio.update(gpio_positive_steps=1,gpio_negative_steps=1,gpio_button_presses=1)
        self.assertTrue(self.owner.choose(0)[0])
        result = self.owner.observe(True)
        self.assertEqual(result.status,'PASSED_USER')
        self.assertEqual(dict(result.evidence)['gpio_button_presses'],1)

    def test_color_sequence_is_observation_only_and_cancel_restores(self):
        self.arm('S16')
        seen = [self.owner.display_color]
        for i in range(4):
            self.owner.choose(0)
            self.worker.drain()
            self.owner.poll()
            seen.append(self.owner.display_color)
        self.assertEqual(seen,[v for name,v in COLORS])
        self.assertEqual(self.owner.cancel().status,'ABORTED')
        self.assertIn(('restore',(156,9)),self.calls)


if __name__ == '__main__':
    unittest.main()
