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
