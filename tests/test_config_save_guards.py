import copy
from concurrent.futures import Future
import unittest
from printerInterface import PrinterData
from test_capabilities import printer
from test_probe_wizard import data as probe_data
import test_bed_mesh as mesh_fixtures
from test_bed_mesh import payload


class SaveDispatchTests(unittest.TestCase):
    def test_probe_save_binds_exact_pending_values_print_state_and_epoch(self):
        for change in ('section', 'field', 'value', 'print', 'epoch'):
            source = probe_data()
            source['status']['configfile'].update(save_config_pending=True, save_config_pending_items={'bltouch': {'z_offset': 2.1}})
            p = printer(source)
            p.sendGCode = PrinterData.sendGCode.__get__(p)
            p.client.post.return_value = Future()
            session = p.probe_wizard
            session.phase, session.section, session.accepted_offset = 'accepted', 'bltouch', 2.1
            session.epoch = p.state.epoch
            session.save()
            guard = p.client.post.call_args.kwargs['guard']
            self.assertTrue(guard())
            items = source['status']['configfile']['save_config_pending_items']
            if change == 'section': items['extruder'] = {'pid_kp': 99}
            elif change == 'field': items['bltouch']['x_offset'] = 1
            elif change == 'value': items['bltouch']['z_offset'] = 2.2
            elif change == 'print': source['status']['print_stats']['state'] = 'printing'
            else: source['epoch'] += 1
            self.assertFalse(guard())

    def test_mesh_save_rejects_changes_after_verified_query(self):
        for change in ('section', 'point', 'profile', 'print'):
            fixture = mesh_fixtures.MeshTests()
            p, session = fixture.make()
            session.start();fixture.complete(session);session.save()
            result = payload(session.profile_name)
            profile = result['status']['bed_mesh']['profiles'][session.profile_name]
            fields = dict(profile['mesh_params'], version='1', points='\n'.join(','.join(str(z) for z in row) for row in profile['points']))
            result['status']['configfile'] = {'save_config_pending': True,
                'save_config_pending_items': {'bed_mesh ' + session.profile_name: fields}}
            source = copy.deepcopy(p.subscription.snapshot())
            source['status'].update(copy.deepcopy(result['status']))
            p.subscription.snapshot.return_value = source
            session.pending.set_result(result);session.update()
            guard = p.subscription.request.call_args.kwargs['guard']
            self.assertTrue(guard())
            if change == 'section': source['status']['configfile']['save_config_pending_items']['extruder'] = {'pid_kp': 1}
            elif change == 'point': source['status']['bed_mesh']['probed_matrix'][0][0] = 9
            elif change == 'profile': source['status']['bed_mesh']['profiles'][session.profile_name]['points'][0][0] = 9
            else: source['status']['print_stats']['state'] = 'printing'
            self.assertFalse(guard())
