import hashlib
import ast
import json
from pathlib import Path
import unittest
import lcd_resources
from lcd_resources import ICON_LIBRARY_ID

ROOT = Path(__file__).resolve().parents[1]


class AssetContracts(unittest.TestCase):
    def test_every_shipped_icon_is_baseline_420_and_export_matches_sources(self):
        from PIL import Image, JpegImagePlugin
        from icon_library import build_library
        from lcd_resources import ICON_LIBRARY_FILENAME
        source = ROOT / 'assets/icons'
        paths = sorted(source.glob('*.jpg'))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(icon=path.name), Image.open(path) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertFalse(image.info.get('progressive') or image.info.get('progression'))
                self.assertEqual(JpegImagePlugin.get_sampling(image), 2)
                image.load()
        self.assertEqual(build_library(source),
                         (ROOT / 'assets/emulator' / ICON_LIBRARY_FILENAME).read_bytes())

    def test_ui_icon_ids_match_verified_stock_manifest(self):
        manifest = json.loads((ROOT / 'docs/lcd-assets.json').read_text())
        tree = ast.parse((ROOT / 'petrel_ui.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PetrelDisplay')
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
            binding = next(n.value for n in cls.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
            actual = binding.value if isinstance(binding, ast.Constant) else getattr(lcd_resources, binding.id)
            self.assertEqual(actual, entry['id'], name)
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
        source = (ROOT / 'petrel_ui.py').read_text()
        tree = ast.parse(source)
        forbidden = {'cache_jpeg', 'show_jpeg', 'copy_cache1'}
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden:
                    calls.append((node.func.attr, node.lineno))
        self.assertEqual(calls, [])
        copies = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'copy_cache']
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].args[0].value, 0)  # Restore splash backing only.

