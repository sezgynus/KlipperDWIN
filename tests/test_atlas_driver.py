import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import lcd_atlas
from test_t5uic1_driver import driver
from t5uic1_driver import T5UIC1Display, T5UIC1ProtocolError


JPEG_A = b"\xFF\xD8atlas-a\xFF\xD9"
JPEG_B = b"\xFF\xD8atlas-b\xFF\xD9"


def configured_driver(directory, data_a=JPEG_A, data_b=JPEG_B):
    root = Path(directory)
    path_a = root / "a.jpg"
    path_b = root / "b.jpg"
    path_a.write_bytes(data_a)
    path_b.write_bytes(data_b)

    lcd = driver()
    lcd._atlas_specs, lcd._atlas_icons = lcd._build_atlas_config(
        {
            0: (path_a, 14),
            1: (path_b, 15),
        },
        {
            0x100: (0, 10, 20, 5, 6),
            0x101: (1, 30, 40, 7, 8),
        },
    )
    lcd._virtual_area_pictures = {}
    lcd._atlas_synced = True
    lcd._atlas_virtual_areas_loaded = False
    return lcd, path_a, path_b


class AtlasDriverTests(unittest.TestCase):
    def test_shipped_info_atlas_is_baseline_and_has_visible_icons(self):
        from PIL import Image

        for icon_id in (lcd_atlas.ICON_MCU, lcd_atlas.ICON_MACHINE,
                        lcd_atlas.ICON_HOST, lcd_atlas.ICON_SOFTWARE, lcd_atlas.ICON_DISPLAY):
            with self.subTest(icon_id=icon_id):
                area, x, y, width, height = lcd_atlas.ICON_COORDINATES[icon_id]
                path = Path(lcd_atlas.__file__).parent / lcd_atlas.ATLAS_FILES[area][0]
                self.assertLessEqual(path.stat().st_size, T5UIC1Display.SRAM_SIZE)
                with Image.open(path) as atlas:
                    self.assertEqual(atlas.format, 'JPEG')
                    self.assertEqual(atlas.size, (480, 272))
                    self.assertFalse(atlas.info.get('progressive'))
                    portrait = atlas.transpose(Image.Transpose.ROTATE_270)
                    icon = portrait.crop((x, y, x + width, y + height)).convert('RGB')
                    # Catch missing pixels and incorrectly rotated/placed assets.
                    lit = sum(max(pixel) > 100 for pixel in icon.getdata())
                    self.assertGreater(lit, 80)
                    self.assertLess(lit, width * height)

    def test_display_atlas_addition_preserves_all_previous_icon_pixels_and_bounds(self):
        import hashlib
        from PIL import Image
        expected = {256: 'e8e22b4b1f3e5e77f84c13ccc64aa325c5ee5cdcc3361eaf313d705ec0576c10', 257: '1655db9eaa0d021a3396a34cb9f16a57c81e6ba1e6e4114c1355928cb5c6d29b', 258: '870655e75c2a5913e5cfc6645788ed30c69a2106e3a31f9a2258773a053c12a9', 259: '662a25884180cf6c0314adf33e4ba7c4bdb84af6d2f699fd71fbb37262bd796d', 260: '6312117eb9a47b79b11dcc78d158d3cabf52b70eda88a13c1e8b6e3007c6eda3', 261: 'cd1d363f015cf11564b65ec69aa53764770226b8369faf204b704a89f31dc804', 262: 'b841f8ba6c3cfc3080d1c0c70b8022b85f5eb23421a2300dc1ef24cb2f4cc30b', 263: '27dbf75681c9c528042e25633dfdce85053b8f1af62a31bbc9d5409fb6780ecd'}
        path = Path(lcd_atlas.__file__).parent / lcd_atlas.ATLAS_FILES[0][0]
        with Image.open(path) as image:
            portrait = image.transpose(Image.Transpose.ROTATE_270).convert('RGB')
            for icon_id, digest in expected.items():
                area, x, y, width, height = lcd_atlas.ICON_COORDINATES[icon_id]
                self.assertEqual(hashlib.sha256(portrait.crop((x, y, x+width, y+height)).tobytes()).hexdigest(), digest)
        area, x, y, w, h = lcd_atlas.ICON_COORDINATES[lcd_atlas.ICON_DISPLAY]
        for icon_id, (other_area, ox, oy, ow, oh) in lcd_atlas.ICON_COORDINATES.items():
            if icon_id != lcd_atlas.ICON_DISPLAY and other_area == area:
                self.assertFalse(x < ox+ow and x+w > ox and y < oy+oh and y+h > oy)

    def test_manifest_coordinates_match_current_custom_static_icons(self):
        self.assertEqual(lcd_atlas.ICON_MMU_HOME_NORMAL, 0x0100)
        self.assertEqual(lcd_atlas.ICON_MMU_HOME_SELECTED, 0x0101)
        self.assertEqual(lcd_atlas.ICON_FOLDER, 0x0102)
        self.assertEqual(lcd_atlas.ICON_MCU, 0x0103)
        self.assertEqual(lcd_atlas.ICON_MACHINE, 0x0104)
        self.assertEqual(lcd_atlas.ICON_HOST, 0x0105)
        self.assertEqual(lcd_atlas.ICON_SOFTWARE, 0x0106)
        self.assertEqual(lcd_atlas.ICON_POWER, 0x0107)
        self.assertEqual(lcd_atlas.ICON_DISPLAY, 0x0108)
        self.assertEqual(
            lcd_atlas.ICON_COORDINATES,
            {
                0x0100: (0, 0, 0, 77, 47),
                0x0101: (0, 80, 0, 77, 47),
                0x0102: (0, 160, 0, 20, 18),
                0x0103: (0, 192, 0, 20, 20),
                0x0104: (0, 224, 0, 20, 20),
                0x0105: (0, 160, 32, 20, 20),
                0x0106: (0, 192, 32, 20, 20),
                0x0107: (0, 224, 32, 20, 20),
                0x0108: (0, 0, 48, 52, 64),
            },
        )
        self.assertEqual(
            lcd_atlas.ATLAS_FILES,
            {
                0: ("assets/klipperdwin_atlas_0.jpg", 14),
                1: ("assets/klipperdwin_atlas_1.jpg", 15),
            },
        )

    def test_coordinate_table_is_validated_once_at_driver_boundary(self):
        with self.assertRaises(ValueError):
            T5UIC1Display._build_atlas_config(
                {0: ("a.jpg", 14), 1: ("b.jpg", 14)}, {}
            )
        with self.assertRaises(ValueError):
            T5UIC1Display._build_atlas_config(
                {0: ("a.jpg", 14)}, {1: (0, 270, 0, 3, 3)}
            )
        with self.assertRaises(ValueError):
            T5UIC1Display._build_atlas_config(
                {0: ("a.jpg", 14)}, {1: (1, 0, 0, 1, 1)}
            )

    def test_load_atlases_restores_volatile_areas_without_flash_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.write_flash = Mock()
            lcd.store_sram_as_picture = Mock()
            lcd.load_atlases()

        self.assertEqual([frame[1] for frame in lcd.serial.frames], [0x22, 0x25])
        self.assertEqual(lcd._virtual_area_pictures, {0: 14, 1: 15})
        self.assertTrue(lcd._atlas_virtual_areas_loaded)
        lcd.write_flash.assert_not_called()
        lcd.store_sram_as_picture.assert_not_called()

    def test_boot_restore_works_when_cache_only_command_supports_area_one_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.load_atlases(preserve_boot_splash=True)
            lcd.update()

        # Model the observed panel: 0x25 is cache-1 only; 0x22 sets cache-0
        # and the frame buffer. A cache-1 copy restores pixels, not cache-0.
        areas = {0: 0}
        buffer = 0
        visible = []
        for frame in lcd.serial.frames:
            opcode = frame[1]
            if opcode == 0x25:
                self.assertEqual(frame[2], 1)
                areas[1] = frame[3]
            elif opcode == 0x22:
                areas[0] = buffer = frame[3]
            elif opcode == 0x26:
                buffer = areas[1]
            elif opcode == 0x3D:
                visible.append(buffer)
        self.assertEqual(areas, {0: 14, 1: 15})
        self.assertEqual(visible, [0])
        self.assertEqual(lcd._virtual_area_pictures, areas)
        opcodes = [f[1] for f in lcd.serial.frames]
        self.assertEqual(opcodes, [0x25, 0x22, 0x26, 0x25, 0x3D])
        self.assertFalse(set(opcodes) & {0x31, 0x32, 0x33})

    def test_cache_only_area_zero_is_rejected_without_false_cache_bookkeeping(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            with self.assertRaises(ValueError):
                lcd.cache_jpeg(14, area=0)
        self.assertEqual(lcd.serial.frames, [])
        self.assertNotIn(0, lcd._virtual_area_pictures)

    def test_draw_atlas_icon_resolves_area_and_source_rectangle(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd._virtual_area_pictures[1] = 15
            lcd._atlas_virtual_areas_loaded = True
            lcd.draw_atlas_icon(0x101, 100, 120)

        self.assertEqual(len(lcd.serial.frames), 1)
        self.assertEqual(
            lcd.serial.frames[0],
            bytes.fromhex(
                "AA 27 21 "
                "00 1E 00 28 00 24 00 2F "
                "00 64 00 78 "
                "CC 33 C3 3C"
            ),
        )

    def test_draw_atlas_icon_lazily_restores_overwritten_virtual_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.cache_jpeg(3)
            self.assertEqual(lcd._virtual_area_pictures[1], 3)
            lcd.serial.frames.clear()

            lcd.draw_atlas_icon(0x101, 0, 0)

        self.assertEqual([frame[1] for frame in lcd.serial.frames], [0x25, 0x27])
        self.assertEqual(lcd.serial.frames[0],
                         bytes.fromhex("AA 25 01 0F CC 33 C3 3C"))
        self.assertEqual(lcd._virtual_area_pictures[1], 15)

    def test_area_zero_is_loaded_from_reserved_picture_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.draw_atlas_icon(0x100, 50, 60)

        self.assertEqual([frame[1] for frame in lcd.serial.frames], [0x22, 0x27])
        self.assertEqual(lcd.serial.frames[0],
                         bytes.fromhex("AA 22 00 0E CC 33 C3 3C"))
        self.assertEqual(lcd._virtual_area_pictures[0], 14)

    def test_unknown_icon_and_destination_overflow_fail_without_uart(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            with self.assertRaises(ValueError):
                lcd.draw_atlas_icon(0x999, 0, 0)
            with self.assertRaises(ValueError):
                lcd.draw_atlas_icon(0x101, 270, 0)
        self.assertFalse(lcd.serial.frames)

    def test_sync_uploads_changed_atlases_then_commits_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.read_flash = Mock(return_value=b"\xFF" * lcd.ATLAS_METADATA_SIZE)
            order = []
            lcd.write_sram = Mock(
                side_effect=lambda address, data: order.append(("sram", data))
            )
            lcd.store_sram_as_picture = Mock(
                side_effect=lambda picture_id: order.append(("picture", picture_id))
            )
            def checkpoint(data):
                order.append(("metadata", data))
                return data
            lcd._commit_atlas_metadata = Mock(side_effect=checkpoint)

            changed = lcd.sync_atlases()

        self.assertTrue(changed)
        self.assertEqual(
            [item[0] for item in order],
            ["sram", "picture", "metadata", "sram", "picture", "metadata"],
        )
        self.assertEqual(order[1], ("picture", 14))
        self.assertEqual(order[4], ("picture", 15))

        first = lcd._unpack_atlas_metadata(order[2][1])
        final = lcd._unpack_atlas_metadata(order[5][1])
        self.assertEqual(first[0][0:2], (14, len(JPEG_A)))
        self.assertNotIn(1, first)
        self.assertEqual(final[0][0:2], (14, len(JPEG_A)))
        self.assertEqual(final[1][0:2], (15, len(JPEG_B)))
        self.assertEqual(len(final[0][2]), lcd.ATLAS_DIGEST_SIZE)

    def test_matching_persistent_versions_skip_picture_flash_rewrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            _, desired = lcd._atlas_payloads()
            metadata = lcd._pack_atlas_metadata(desired)
            lcd.read_flash = Mock(return_value=metadata)
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock()
            lcd._commit_atlas_metadata = Mock()

            changed = lcd.sync_atlases()

        self.assertFalse(changed)
        lcd.write_sram.assert_not_called()
        lcd.store_sram_as_picture.assert_not_called()
        lcd._commit_atlas_metadata.assert_not_called()

    def test_only_the_changed_atlas_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, path_a, _ = configured_driver(tmp)
            _, old_entries = lcd._atlas_payloads()
            old_metadata = lcd._pack_atlas_metadata(old_entries)
            path_a.write_bytes(b"\xFF\xD8atlas-a-v2\xFF\xD9")

            lcd.read_flash = Mock(return_value=old_metadata)
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock()
            lcd._commit_atlas_metadata = Mock(side_effect=lambda data: data)

            changed = lcd.sync_atlases()

        self.assertTrue(changed)
        lcd.store_sram_as_picture.assert_called_once_with(14)
        lcd._commit_atlas_metadata.assert_called_once()

    def test_metadata_is_not_advanced_when_picture_update_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.read_flash = Mock(return_value=b"\xFF" * lcd.ATLAS_METADATA_SIZE)
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock(side_effect=RuntimeError("write failed"))
            lcd._commit_atlas_metadata = Mock()

            with self.assertRaises(RuntimeError):
                lcd.sync_atlases()

        lcd._commit_atlas_metadata.assert_not_called()

    def test_invalid_or_oversized_atlas_is_rejected_before_flash_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, path_a, _ = configured_driver(tmp)
            lcd.read_flash = Mock()

            path_a.write_bytes(b"not-a-jpeg")
            with self.assertRaises(ValueError):
                lcd.sync_atlases()
            lcd.read_flash.assert_not_called()

            path_a.write_bytes(
                b"\xFF\xD8" + b"x" * T5UIC1Display.SRAM_SIZE + b"\xFF\xD9"
            )
            with self.assertRaises(ValueError):
                lcd.sync_atlases()
            lcd.read_flash.assert_not_called()

    def test_empty_coordinate_table_keeps_existing_startup_traffic_unchanged(self):
        lcd = driver()
        lcd._atlas_specs, lcd._atlas_icons = lcd._build_atlas_config(
            {0: ("missing-a.jpg", 14), 1: ("missing-b.jpg", 15)}, {}
        )
        lcd._atlas_synced = False
        lcd.read_flash = Mock()

        self.assertFalse(lcd.sync_atlases())
        self.assertTrue(lcd._atlas_synced)
        lcd.read_flash.assert_not_called()

    def test_sync_logs_upload_progress_and_persistent_metadata_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.read_flash = Mock(return_value=b"\xFF" * lcd.ATLAS_METADATA_SIZE)
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock()
            lcd._commit_atlas_metadata = Mock(side_effect=lambda data: data)

            with self.assertLogs(level="INFO") as captured:
                self.assertTrue(lcd.sync_atlases())

        output = "\n".join(captured.output)
        self.assertIn("Atlas sync: reading metadata @ 0x0000", output)
        self.assertIn("Atlas 0: changed -> upload required", output)
        self.assertIn("Atlas 0: SRAM upload complete", output)
        self.assertIn("Atlas 0: Picture Flash 14 write complete", output)
        self.assertIn("Atlas 1: Picture Flash 15 write complete", output)
        self.assertIn("Atlas sync complete: updated virtual area(s) 0,1", output)

    def test_sync_logs_unchanged_atlases_and_virtual_area_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            _, desired = lcd._atlas_payloads()
            lcd.read_flash = Mock(return_value=lcd._pack_atlas_metadata(desired))
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock()
            lcd._commit_atlas_metadata = Mock()

            with self.assertLogs(level="INFO") as captured:
                self.assertFalse(lcd.sync_atlases())
                lcd._virtual_area_pictures.clear()
                lcd._load_atlas_area(1)

        output = "\n".join(captured.output)
        self.assertIn("Atlas 0: unchanged -> skip", output)
        self.assertIn("Atlas 1: unchanged -> skip", output)
        self.assertIn("Atlas metadata: unchanged", output)
        self.assertIn("Atlas sync complete: no atlas uploads required", output)
        self.assertIn(
            "Atlas 1: loading Picture Flash 15 into virtual area 1", output
        )
        lcd.write_sram.assert_not_called()
        lcd.store_sram_as_picture.assert_not_called()
        lcd._commit_atlas_metadata.assert_not_called()

    def test_metadata_checkpoint_is_read_back_and_verified(self):
        lcd = driver()
        metadata = bytes(range(lcd.ATLAS_METADATA_SIZE))
        lcd.write_flash = Mock()
        lcd.read_flash = Mock(return_value=metadata)

        self.assertEqual(lcd._commit_atlas_metadata(metadata), metadata)
        lcd.write_flash.assert_called_once_with(lcd.ATLAS_METADATA_ADDRESS, metadata)
        lcd.read_flash.assert_called_once_with(
            lcd.ATLAS_METADATA_ADDRESS, lcd.ATLAS_METADATA_SIZE
        )

        lcd.read_flash = Mock(return_value=b"x" * lcd.ATLAS_METADATA_SIZE)
        with self.assertRaises(T5UIC1ProtocolError):
            lcd._commit_atlas_metadata(metadata)

    def test_render_path_never_triggers_persistent_flash_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd._atlas_synced = False
            lcd.sync_atlases = Mock()

            with self.assertRaises(T5UIC1ProtocolError):
                lcd.draw_atlas_icon(0x100, 0, 0)
            with self.assertRaises(T5UIC1ProtocolError):
                lcd.load_atlases()

        lcd.sync_atlases.assert_not_called()
        self.assertFalse(lcd.serial.frames)

    def test_startup_sync_failure_is_nonfatal_and_blocks_render_retry(self):
        lcd = driver()
        lcd._atlas_sync_blocked = False
        lcd.sync_atlases = Mock(side_effect=TimeoutError("metadata timeout"))

        with self.assertLogs(level="ERROR") as captured:
            self.assertFalse(lcd._startup_sync_atlases())

        self.assertTrue(lcd._atlas_sync_blocked)
        self.assertIn("automatic retries are blocked", "\n".join(captured.output))

    def test_automatic_wear_guard_blocks_same_picture_retry_in_process(self):
        T5UIC1Display._atlas_auto_picture_attempts.clear()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                first, _, _ = configured_driver(tmp)
                # Exercise only area 0 to make the retry target unambiguous.
                first._atlas_icons = {0x100: (0, 10, 20, 5, 6)}
                first.read_flash = Mock(
                    return_value=b"\xFF" * first.ATLAS_METADATA_SIZE
                )
                first.write_sram = Mock()
                first.store_sram_as_picture = Mock()
                first._commit_atlas_metadata = Mock(
                    side_effect=RuntimeError("metadata commit failed")
                )

                with self.assertRaises(RuntimeError):
                    first.sync_atlases(automatic=True)
                first.store_sram_as_picture.assert_called_once_with(14)

                second, _, _ = configured_driver(tmp)
                second._atlas_icons = {0x100: (0, 10, 20, 5, 6)}
                second.read_flash = Mock(
                    return_value=b"\xFF" * second.ATLAS_METADATA_SIZE
                )
                second.write_sram = Mock()
                second.store_sram_as_picture = Mock()
                second._commit_atlas_metadata = Mock()

                with self.assertRaises(T5UIC1ProtocolError):
                    second.sync_atlases(automatic=True)

                second.store_sram_as_picture.assert_not_called()
                second._commit_atlas_metadata.assert_not_called()
        finally:
            T5UIC1Display._atlas_auto_picture_attempts.clear()

    def test_first_successful_picture_is_checkpointed_before_second_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            lcd, _, _ = configured_driver(tmp)
            lcd.read_flash = Mock(
                return_value=b"\xFF" * lcd.ATLAS_METADATA_SIZE
            )
            lcd.write_sram = Mock()
            lcd.store_sram_as_picture = Mock(
                side_effect=[None, RuntimeError("picture 15 failed")]
            )
            checkpoints = []
            lcd._commit_atlas_metadata = Mock(
                side_effect=lambda data: checkpoints.append(data) or data
            )

            with self.assertRaises(RuntimeError):
                lcd.sync_atlases()

        self.assertEqual(len(checkpoints), 1)
        parsed = lcd._unpack_atlas_metadata(checkpoints[0])
        self.assertIn(0, parsed)
        self.assertNotIn(1, parsed)
        self.assertEqual(parsed[0][0], 14)

    def test_startup_can_defer_sync_until_binary_atlases_are_present(self):
        lcd = driver()
        lcd._atlas_specs, lcd._atlas_icons = lcd._build_atlas_config(
            {0: ("missing-a.jpg", 14), 1: ("missing-b.jpg", 15)},
            {0x100: (0, 0, 0, 10, 10)},
        )
        lcd._atlas_synced = False
        lcd.read_flash = Mock()

        self.assertFalse(lcd.sync_atlases(allow_missing=True))
        self.assertFalse(lcd._atlas_synced)
        lcd.read_flash.assert_not_called()
        with self.assertRaises(OSError):
            lcd.sync_atlases()

    def test_draw_is_strict_if_manifest_exists_but_jpeg_is_missing(self):
        lcd = driver()
        lcd._atlas_specs, lcd._atlas_icons = lcd._build_atlas_config(
            {0: ("missing-a.jpg", 14)},
            {0x100: (0, 0, 0, 10, 10)},
        )
        lcd._atlas_synced = False
        with self.assertRaises(T5UIC1ProtocolError):
            lcd.draw_atlas_icon(0x100, 0, 0)
        self.assertFalse(lcd.serial.frames)


if __name__ == "__main__":
    unittest.main()
