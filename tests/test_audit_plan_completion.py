import copy
import unittest
from types import SimpleNamespace
from concurrent.futures import Future
from test_capabilities import printer, snapshot

class PresetDraftTests(unittest.TestCase):
    def test_discard_restores_only_selected_profile(self):
        p = printer(snapshot())
        p.material_preset = [SimpleNamespace(name='A', hotend_temp=200), SimpleNamespace(name='B', hotend_temp=210)]
        p._preset_original = copy.deepcopy(p.material_preset)
        p.material_preset[0].hotend_temp = 240
        p.material_preset[1].hotend_temp = 250
        p.discard_preset_edits(0)
        self.assertEqual([x.hotend_temp for x in p.material_preset], [200, 250])
        self.assertEqual(p._preset_refresh_at, 0)

    def test_pending_save_cannot_be_discarded(self):
        p = printer(snapshot()); p._settings_save = Future()
        with self.assertRaises(ValueError): p.discard_preset_edits(0)

class CoordinateValidationTests(unittest.TestCase):
    def test_all_origin_axes_and_malformed_arrays_are_rejected(self):
        for values in ([float('nan'), 0, 0], [0, float('inf'), 0], [0, 0], None, [True, 0, 0]):
            data = snapshot(); p = printer(data)
            data['status']['gcode_move']['homing_origin'] = values
            self.assertFalse(p.update_variable(), values)
            self.assertTrue(p.connection_error)

class NavigationBatchTests(unittest.TestCase):
    def test_selection_batch_clamps_in_one_operation(self):
        from test_regressions import ui
        s = ui.select_t(); s.batch_steps = 1000
        s.inc(18); self.assertEqual(s.now,17)
        s.dec(); self.assertEqual(s.now,0)

class SnapshotReuseTests(unittest.TestCase):
    def test_unchanged_revision_skips_snapshot_copy_but_updates_file_revision(self):
        data = snapshot(); p = printer(data)
        p.subscription.lifecycle.return_value = dict(state='ready',epoch=p.state.epoch,revision=p.state.revision,file_revision=9)
        p.subscription.snapshot.reset_mock()
        self.assertTrue(p.update_variable())
        p.subscription.snapshot.assert_not_called()
        self.assertEqual(p.state.file_revision,9)
        p.subscription.lifecycle.return_value['revision'] += 1
        p.update_variable(); p.subscription.snapshot.assert_called()
