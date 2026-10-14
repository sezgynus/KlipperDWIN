"""MMU integration uses the actual master LCD driver, not permissive LCD mocks."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
import test_mmu_ui as mmu_fixtures
import test_t5uic1_driver as transport
from t5uic1_driver import T5UIC1Display
from lcd_resources import ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED


def lcd():
    result = transport.driver()
    result.load_buzzer_settings = Mock(return_value=None)
    return result


class MMUDriverIntegrationTests(unittest.TestCase):
    def test_every_mmu_page_emits_valid_new_driver_packets_without_commands(self):
        fixture = mmu_fixtures.MMUUITests()
        view, _ = fixture.make()
        view._mmu_open('more')
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

    def test_home_mmu_icon_is_native_library_7_for_both_selections(self):
        view, _ = mmu_fixtures.MMUUITests().make()
        view.lcd = lcd()
        index = next(i for i, entry in enumerate(view._home_entries()) if entry[0] == 'MMU')
        slot = index % 4
        x, y = (17 if slot % 2 == 0 else 145), (130 if slot < 2 else 246)
        for selected, icon in ((False, ICON_MMU_HOME_NORMAL), (True, ICON_MMU_HOME_SELECTED)):
            view.lcd.serial.frames.clear()
            view.select_page.set(index if selected else index - 1)
            view._draw_home_page()
            frames = [f for f in view.lcd.serial.frames if f[1] == 0x23 and f[6:8] == bytes((0x23, icon))]
            self.assertEqual(len(frames), 1)
            frame = frames[0]
            self.assertEqual(frame[1], 0x23)
            self.assertEqual(int.from_bytes(frame[2:4], 'big'), x)
            self.assertEqual(int.from_bytes(frame[4:6], 'big'), y)
            self.assertEqual(frame[6:8], bytes((0x23, icon)))

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
