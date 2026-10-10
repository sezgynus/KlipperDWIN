"""MMU integration uses the actual master LCD driver, not permissive LCD mocks."""
import ast
from pathlib import Path
import unittest
import test_mmu_ui as mmu_fixtures
import test_t5uic1_driver as transport
from t5uic1_driver import T5UIC1Display
from lcd_atlas import ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED


def lcd():
    result = transport.driver()
    result._atlas_synced = True
    result._atlas_virtual_areas_loaded = True
    result._virtual_area_pictures = {0: 14}
    return result


class MMUDriverIntegrationTests(unittest.TestCase):
    def test_every_mmu_page_emits_valid_new_driver_packets_without_commands(self):
        fixture = mmu_fixtures.MMUUITests()
        view, _ = fixture.make()
        fixture.press(view, 2)
        view.lcd = lcd()
        for page in view.MMU_TITLES:
            with self.subTest(page=page):
                view._mmu_page = page
                view._mmu_selection = 1
                view._mmu_canvas_page = None
                view.lcd.serial.frames.clear()
                view.Draw_MMU_Menu()
                frames = view.lcd.serial.frames
                self.assertTrue(frames)
                self.assertTrue(all(f.startswith(b'\xAA') and f.endswith(T5UIC1Display.TAIL) for f in frames))
                self.assertNotIn(0x31, [f[1] for f in frames])
                self.assertNotIn(0x33, [f[1] for f in frames])
                view.pd.subscription.request.assert_not_called()

    def test_home_mmu_icon_is_an_atlas_copy_for_both_selections(self):
        view, _ = mmu_fixtures.MMUUITests().make()
        view.lcd = lcd()
        for selected, source_x in ((False, 0), (True, 80)):
            view.lcd.serial.frames.clear()
            view.Draw_MMU_Home_Icon(145, 170, selected)
            self.assertEqual(len(view.lcd.serial.frames), 1)
            frame = view.lcd.serial.frames[0]
            self.assertEqual(frame[1], 0x27)
            self.assertEqual(int.from_bytes(frame[3:5], 'big'), source_x)
            self.assertEqual(int.from_bytes(frame[11:13], 'big'), 161)
            self.assertEqual(int.from_bytes(frame[13:15], 'big'), 186)

    def test_all_production_lcd_calls_exist_on_complete_driver(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                obj = node.func.value
                if isinstance(obj, ast.Attribute) and obj.attr == 'lcd':
                    with self.subTest(file=path.name, method=node.func.attr):
                        self.assertTrue(callable(getattr(T5UIC1Display, node.func.attr, None)))
