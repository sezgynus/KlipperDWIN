import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UIModularityTests(unittest.TestCase):
    def _class(self):
        tree = ast.parse((ROOT / 'petrel_ui.py').read_text(encoding='utf-8'))
        return next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == 'PetrelDisplay'
        )

    def test_feature_views_are_composed_as_mixins(self):
        cls = self._class()
        bases = {base.id for base in cls.bases if isinstance(base, ast.Name)}
        self.assertEqual(bases, {'RecoveryViewMixin', 'PrintFocusMixin', 'PowerShortcutMixin', 'BuzzerViewMixin', 'MMUViewMixin', 'CaseLightMixin', 'MaintenanceViewMixin', 'ScrewsTiltMixin', 'BedMeshMixin', 'FilePreviewMixin'})
        methods = {
            node.name for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn('Draw_MMU_Status', methods)
        self.assertNotIn('Draw_Case_Light_Menu', methods)

    def test_removed_legacy_symbols_do_not_return(self):
        cls = self._class()
        assigned = {
            target.id
            for node in cls.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for name in (
            'Language_Chinese', 'PREPARE_CASE_LANG', 'Back_Print',
            'Popup_Window', 'MaxSpeed', 'MaxAcceleration', 'MaxJerk', 'Step',
        ):
            self.assertNotIn(name, assigned, name)


if __name__ == '__main__':
    unittest.main()
