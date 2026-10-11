import hashlib
import ast
import json
from pathlib import Path
import unittest
from lcd_resources import ICON_LIBRARY_ID

ROOT = Path(__file__).resolve().parents[1]


class AssetContracts(unittest.TestCase):
    def test_ui_icon_ids_match_verified_stock_manifest(self):
        manifest = json.loads((ROOT / 'docs/lcd-assets.json').read_text())
        tree = ast.parse((ROOT / 'dwinlcd.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DWIN_LCD')
        constants = {n.targets[0].id: n.value.value for n in cls.body
                     if isinstance(n, ast.Assign) and len(n.targets) == 1
                     and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
        icon = next(n for n in cls.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'ICON' for t in n.targets))
        self.assertIsInstance(icon.value, ast.Name)
        self.assertEqual(icon.value.id, 'ICON_LIBRARY_ID')
        self.assertEqual(ICON_LIBRARY_ID, manifest['library'])
        # The legacy English JPEG cache is intentionally not a UI constant:
        # the UI uses native icon-library rendering.
        self.assertNotIn('Language_English', constants)
        for name, entry in manifest['icons'].items():
            self.assertEqual(constants[name], entry['id'], name)
            self.assertGreater(entry['width'], 0)
            self.assertGreater(entry['height'], 0)

    def test_icon_library_asset_matches_manifest_and_fits_reserved_flash(self):
        from dwin_emulator.assets import PanelAssets
        from lcd_resources import ICON_LIBRARY_FILENAME
        manifest = json.loads((ROOT / 'docs/lcd-assets.json').read_text())
        data = (ROOT / 'assets/emulator' / ICON_LIBRARY_FILENAME).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['sha256'][ICON_LIBRARY_FILENAME])
        self.assertLessEqual(len(data), (16 - ICON_LIBRARY_ID) * 32768)
        assets = PanelAssets()
        for icon in (92, 93):
            self.assertEqual(assets.icon(ICON_LIBRARY_ID, icon).size, (110, 100))
        with self.assertRaisesRegex(ValueError, 'Missing icon library 9'):
            assets.icon(9, 90)

    def test_legacy_virtual_area_cache_is_not_used_by_ui(self):
        source = (ROOT / 'dwinlcd.py').read_text()
        tree = ast.parse(source)
        forbidden = {'cache_jpeg', 'show_jpeg', 'copy_cache', 'copy_cache1'}
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden:
                    calls.append((node.func.attr, node.lineno))
        self.assertEqual(calls, [])

