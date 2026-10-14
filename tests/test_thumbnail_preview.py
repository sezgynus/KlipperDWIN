from io import BytesIO
from concurrent.futures import Future
from unittest.mock import Mock, patch
import unittest
from PIL import Image
from thumbnail_preview import image_jpeg, load_thumbnail, _protect_dark_foreground, MIN_FOREGROUND_LUMA
from dwin_emulator.assets import panel_colors
from test_capabilities import display, snapshot
import test_files


def png(size=(128,128), color='red'):
    stream=BytesIO();Image.new('RGBA',size,color).save(stream,format='PNG');return stream.getvalue()


class ThumbnailTests(unittest.TestCase):
    def test_corrupt_and_oversized_images_rejected(self):
        with self.assertRaises(Exception):image_jpeg(b'invalid')
        with self.assertRaises(ValueError):image_jpeg(png((2100,2100)))

    def test_thumbnail_parent_path_encoding_and_download_limit(self):
        client=Mock();client.get.return_value={'result':{'thumbnails':[
            {'relative_path':'.thumbs/model.png','width':128,'height':128}]}}
        client.get_bytes.return_value=png()
        self.assertTrue(load_thumbnail(client,'parts a/model.gcode').startswith(b'\xff\xd8'))
        client.get.assert_called_once_with('/server/files/metadata?filename=parts%20a%2Fmodel.gcode')
        client.get_bytes.assert_called_once_with('/server/files/gcodes/parts%20a/.thumbs/model.png',max_bytes=2_000_000)

    def test_missing_thumbnail_and_root_escape_rejected(self):
        for thumbs in ([],[{'relative_path':'../../secret','width':128,'height':128}]):
            client=Mock();client.get.return_value={'result':{'thumbnails':thumbs}}
            with self.assertRaises(ValueError):load_thumbnail(client,'parts/model.gcode')
            client.get_bytes.assert_not_called()

    def test_jpeg_is_baseline_bounded_rgb_and_letterboxed(self):
        jpeg = image_jpeg(png((256,128)))
        self.assertLessEqual(len(jpeg),32768)
        with Image.open(BytesIO(jpeg)) as image:
            self.assertEqual(image.size,(128,128))
            self.assertEqual(image.mode,'RGB')
            self.assertFalse(image.info.get('progressive',False))
            self.assertEqual(panel_colors(image).getpixel((64,0)), (0, 0, 0))
            self.assertGreater(image.getpixel((64,64))[0],240)
        with Image.open(BytesIO(image_jpeg(png(color=(255,0,0,0))))) as image:
            self.assertEqual(panel_colors(image).getpixel((64,64)), (0, 0, 0))
        for data in (b'corrupt',png((2100,2100))):
            with self.assertRaises(Exception):image_jpeg(data)

    def test_black_model_is_lifted_but_alpha_and_bright_colors_are_preserved(self):
        for color, expected in (((0,0,0,255),(48,48,48)),
                                ((255,0,0,128),(128,0,0)),
                                ((255,255,255,255),(255,255,255))):
            with self.subTest(color=color):
                with Image.open(BytesIO(image_jpeg(png(color=color)))) as image:
                    actual = image.getpixel((64,64))
                    self.assertTrue(all(abs(a-b) <= 3 for a,b in zip(actual, expected)),
                                    (actual, expected))
        for color in ((0,0,0,255),(20,0,0,255),(0,0,255,255),(5,5,5,128)):
            protected = _protect_dark_foreground(Image.new('RGBA',(1,1),color))
            r,g,b,alpha = protected.getpixel((0,0))
            self.assertEqual(alpha,color[3])
            self.assertGreaterEqual((299*r+587*g+114*b)//1000,MIN_FOREGROUND_LUMA)
        for color in ((255,0,0,255),(0,255,0,255),(255,255,255,128)):
            self.assertEqual(_protect_dark_foreground(Image.new('RGBA',(1,1),color)).getpixel((0,0)),color)

    def test_filtered_sram_preview_preserves_surface_and_lifted_black_details(self):
        from PIL import ImageDraw
        from test_t5uic1_driver import driver
        from dwin_emulator.assets import PanelAssets, rgb565
        from dwin_emulator.framebuffer import Framebuffer
        source = Image.new('RGBA',(128,128),(0,0,0,0))
        ImageDraw.Draw(source).rectangle((40,40,87,87),fill=(0,0,0,255))
        stream=BytesIO(); source.save(stream,'PNG')
        lcd=driver(); model=Framebuffer(PanelAssets()); lcd._packet_observer=model
        lcd.clear(0x2967)
        lcd.write_sram(0,image_jpeg(stream.getvalue()))
        lcd.show_sram_jpeg(8,68,0,background=False,enhanced=True)
        lcd.update(); image=model.snapshot()[0]
        self.assertEqual(image.getpixel((10,70)),rgb565(0x2967))
        self.assertNotEqual(image.getpixel((72,132)),rgb565(0x2967))
        self.assertGreaterEqual(min(image.getpixel((72,132))),40)

    def make(self):
        view=test_files.FileTests().display(['a.gcode','b.gcode'])
        # Restore production preview entry, replacing the original start-contract shortcut.
        del view._open_file_preview
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        view._preview_path='a.gcode';view._preview_epoch=view.pd.state.epoch
        view._preview_choice=1;view._preview_error=None
        view._preview_cache_key=view._thumbnail_keys['a.gcode']
        view._preview_shown=False;view._preview_cache_hit=False;view._preview_open_at=0
        view._preview_future=Future();view.checkkey=view.FilePreview
        view._thumbnail_cache.loader=Mock(return_value=view._preview_future)
        view._thumbnail_cache.job=(view._preview_cache_key,view._preview_future,view._thumbnail_cache.generation)
        view._loop=Mock()
        return view

    def test_selecting_file_opens_confirmation_without_print(self):
        view=self.make();view.checkkey=view.SelectFile;view.select_file.set(1)
        view.pd.openAndPrintFile=Mock()
        view._thumbnail_cache.job=None
        view.HMI_SelectFile()
        view._thumbnail_cache.loader.assert_called_once_with(view._thumbnail_keys['a.gcode'])
        self.assertEqual(view.checkkey,view.FilePreview)
        self.assertEqual(view._preview_choice,1)
        view.pd.openAndPrintFile.assert_not_called()

    def test_cancel_keeps_file_selection_without_command(self):
        view=self.make();view.select_file.set(1)
        view.HMI_File_Preview()
        self.assertEqual(view.checkkey,view.SelectFile)
        self.assertEqual(view._file_paths[view.select_file.now-1],'a.gcode')
        view.pd.sendGCode.assert_not_called()
        view._loop.set_interval.assert_called_with(.02)

    def test_redraw_uses_sram_and_uart_reconnect_invalidates_it(self):
        view=self.make();view._thumbnail_cache.job=None
        view._thumbnail_cache.entries[view._preview_cache_key]=(4096,2300)
        view.Draw_File_Preview();view.lcd.reset_mock()
        view._poll_file_preview()
        view.lcd.show_sram_jpeg.assert_called_once_with(8,68,4096,background=False,enhanced=True)
        view.lcd.write_sram.assert_not_called()
        view._uart_epoch=1;view.Draw_File_Preview();view._poll_file_preview()
        self.assertFalse(view._thumbnail_cache.entries)
        view._thumbnail_cache.loader.assert_called_once()

    def test_missing_thumbnail_leaves_buttons_usable(self):
        view=self.make();view.Draw_File_Preview();view._preview_future.set_exception(ValueError('No thumbnail'))
        view._poll_file_preview()
        self.assertEqual(view._preview_error,'No thumbnail')
        self.assertIn('Cancel',[c.args[-1] for c in view.lcd.draw_text.call_args_list])

    def test_jpeg_upload_is_chunked_and_displayed_only_once_after_completion(self):
        view=self.make();view._preview_future.set_result(b'x'*2300)
        view._poll_file_preview()
        self.assertEqual(view._thumbnail_cache.upload['index'],1024)
        self.assertEqual(view.lcd.write_sram.call_count,8)
        view.lcd.show_sram_jpeg.assert_not_called()
        view._poll_file_preview();view._poll_file_preview();view._poll_file_preview()
        view.lcd.show_sram_jpeg.assert_called_once_with(8,68,0,background=False,enhanced=True)
        calls=view.lcd.write_sram.call_args_list
        self.assertEqual(b''.join(c.args[1] for c in calls),b'x'*2300)
        self.assertEqual([c.args[0] for c in calls],list(range(0,2300,128)))
        self.assertTrue(all(1<=len(c.args[1])<=128 for c in calls))
        view.lcd.reset_mock();view.Draw_File_Preview();view._poll_file_preview()
        view.lcd.write_sram.assert_not_called()
        view.lcd.show_sram_jpeg.assert_called_once_with(8,68,0,background=False,enhanced=True)

    def test_cancel_or_changed_connection_stops_partial_jpeg_upload(self):
        for cancel in (True,False):
            view=self.make();view._preview_future.set_result(b'x'*2300)
            view._poll_file_preview();view.lcd.reset_mock()
            if cancel:view.HMI_File_Preview()
            else:view._preview_epoch-=1
            view._poll_file_preview()
            view.lcd.write_sram.assert_not_called()
            view.lcd.show_sram_jpeg.assert_not_called()

    def test_print_revalidates_file_and_duplicate_press_does_not_resubmit(self):
        view=self.make();view._preview_choice=0
        view.pd.postREST=Mock(return_value=Future())
        view.HMI_File_Preview();view.HMI_File_Preview()
        view.pd.postREST.assert_called_once_with('/printer/print/start',json={'filename':'a.gcode'})

    def test_deleted_file_or_epoch_change_blocks_print(self):
        for changed_epoch in (False,True):
            view=self.make();view._preview_choice=0
            view.pd.openAndPrintFile=Mock()
            if changed_epoch:view._preview_epoch-=1
            else:view.pd.getREST.return_value={'result':[{'path':'b.gcode'}]}
            view.HMI_File_Preview();view.pd.openAndPrintFile.assert_not_called()
            self.assertTrue(view._start_error_visible)

    def test_late_completion_after_cancel_does_not_draw(self):
        view=self.make();view.HMI_File_Preview();view.lcd.reset_mock()
        view._preview_future.set_result(image_jpeg(png()))
        view._poll_file_preview();view.lcd.draw_rectangle.assert_not_called()

    def test_large_source_preferred_over_tiny_icon(self):
        client=Mock();client.get.return_value={'result':{'thumbnails':[
            {'relative_path':'.thumbs/tiny.png','width':32,'height':32},
            {'relative_path':'.thumbs/large.png','width':400,'height':300}]}}
        client.get_bytes.return_value=png()
        load_thumbnail(client,'a.gcode')
        self.assertIn('large.png',client.get_bytes.call_args.args[0])

    def test_completed_sram_hit_needs_no_download_or_upload(self):
        view=self.make();view._thumbnail_cache.job=None
        view._thumbnail_cache.entries[view._thumbnail_keys['a.gcode']]=(3000,1200)
        view._open_file_preview('a.gcode')
        view._thumbnail_cache.loader.assert_not_called()
        view.lcd.write_sram.assert_not_called()
        view.lcd.show_sram_jpeg.assert_called_once_with(8,68,3000,background=False,enhanced=True)

    def test_replaced_file_cannot_print_from_old_preview(self):
        view=self.make();view._preview_choice=0
        view.pd.getREST.return_value={'result':[{'path':'a.gcode','modified':2,'size':500}]}
        view.pd.openAndPrintFile=Mock()
        view.HMI_File_Preview()
        view.pd.openAndPrintFile.assert_not_called()
        self.assertTrue(view._start_error_visible)

    def test_browser_tick_preloads_without_drawing_thumbnail_or_frequent_status_poll(self):
        view=self.make();view._preview_future.set_result(b'x'*2300)
        view.checkkey=view.SelectFile;view._uart_online=True
        view.EachMomentUpdate=Mock();view._file_status_at=0
        view.lcd.reset_mock()
        view._ui_tick();view._ui_tick()
        self.assertEqual(view.lcd.write_sram.call_count,4)
        view.lcd.show_sram_jpeg.assert_not_called()
        view.EachMomentUpdate.assert_called_once()

    def test_current_folder_first_five_follow_sort_and_file_replacement(self):
        view=self.make()
        view.pd.files=[{'path':name,'modified':1,'size':100} for name in
                       ('a.gcode','b.gcode','c.gcode','d.gcode','e.gcode','f.gcode','sub/x.gcode')]
        view._file_paths=('empty/', 'f.gcode','e.gcode','d.gcode','c.gcode','b.gcode','a.gcode')
        view._sync_thumbnail_cache()
        self.assertEqual([key[0] for key in view._thumbnail_cache.priority],
                         ['f.gcode','e.gcode','d.gcode','c.gcode','b.gcode'])
        key=view._thumbnail_keys['b.gcode'];view._thumbnail_cache.entries[key]=(0,1000)
        view._file_paths=tuple(reversed(view._file_paths));view.pd.file_sort_revision+=1
        view._sync_thumbnail_cache()
        self.assertEqual(view._thumbnail_cache.address(key),0)
        view.pd.files=[dict(item,modified=2) if item['path']=='b.gcode' else item for item in view.pd.files]
        view._sync_thumbnail_cache()
        self.assertIsNone(view._thumbnail_cache.address(key))
