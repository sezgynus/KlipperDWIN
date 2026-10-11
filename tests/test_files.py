from concurrent.futures import Future
import unittest
from unittest.mock import Mock, patch

from test_regressions import backend, ui
MoonrakerError = backend.MoonrakerError
from test_capabilities import snapshot, printer, display


class FileTests(unittest.TestCase):
    def backend(self, paths):
        result = printer(snapshot())
        result.getREST = Mock(return_value={'result': [{'path': path} for path in paths]})
        result.GetFiles()
        return result

    def display(self, paths):
        result = display(snapshot())
        result.pd = self.backend(paths)
        result.lcd.DWIN_WIDTH = 272
        result.pd.GetDirectory = lambda directory='': result.pd.GetFiles()
        result._refresh_file_snapshot()
        result._open_file_preview = lambda path: (setattr(result, '_preview_path', path), setattr(result, '_preview_epoch', result.pd.state.epoch), setattr(result, '_preview_choice', 0), result.HMI_File_Preview())
        result._show_message = Mock()
        result.Goto_PrintProcess = Mock()
        result.Goto_MainMenu = Mock()
        result.Draw_Status_Area = Mock()
        result._offline = False
        result.checkkey = result.SelectFile
        result.last_status = result.pd.status
        return result

    def test_empty_list_is_cached_and_navigation_does_not_fetch(self):
        result = self.display([])
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_CW)
        for _ in range(10):
            result.HMI_SelectFile()
        result.pd.getREST.assert_called_once()
        self.assertEqual(result.select_file.now, 0)

    def test_selection_survives_insert_and_returns_back_after_delete(self):
        result = self.display(['b.gcode', 'c.gcode'])
        result.select_file.set(2)
        result.pd.getREST.return_value = {'result': [{'path': 'a.gcode'}, {'path': 'c.gcode'}]}
        result.pd._files_loaded = False
        result._refresh_file_snapshot()
        self.assertEqual(result._file_paths[result.select_file.now - 1], 'c.gcode')
        result.pd.getREST.return_value = {'result': [{'path': 'a.gcode'}]}
        result.pd._files_loaded = False
        result._refresh_file_snapshot()
        self.assertEqual(result.select_file.now, 0)

    def test_failed_refresh_preserves_list_and_blocks_start(self):
        result = self.backend(['a.gcode'])
        result.getREST.side_effect = MoonrakerError('timeout')
        self.assertEqual(result.GetFiles(refresh=True), ('a.gcode',))
        self.assertIsNone(result.connection_error)
        result.postREST = Mock()
        with self.assertRaises(ValueError):
            result.openAndPrintFile('a.gcode')
        result.postREST.assert_not_called()

    def test_start_addresses_path_and_waits_for_result_and_status(self):
        result = self.display(['a.gcode'])
        future = Future()
        result.pd.postREST = Mock(return_value=future)
        result.select_file.set(1)
        result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
        result.HMI_SelectFile()
        result.HMI_SelectFile()
        result.pd.postREST.assert_called_once_with('/printer/print/start', json={'filename': 'a.gcode'})
        self.assertEqual(result.pd.file_name, '')
        result.Goto_PrintProcess.assert_not_called()
        future.set_result({'result': 'ok'})
        self.assertTrue(result._poll_print_start())
        result.pd.status = 'printing'
        result.pd.job_Info['print_stats'] = {'state': 'printing'}
        self.assertFalse(result._poll_print_start())
        result.Goto_PrintProcess.assert_called_once()

    def test_start_failure_cancel_and_epoch_change_are_not_retried(self):
        for outcome in ('failure', 'cancel', 'epoch'):
            result = self.display(['a.gcode'])
            future = Future()
            result.pd.postREST = Mock(return_value=future)
            result.select_file.set(1)
            result.get_encoder_state = Mock(return_value=result.ENCODER_DIFF_ENTER)
            result.HMI_SelectFile()
            if outcome == 'failure':
                future.set_exception(MoonrakerError('denied'))
            elif outcome == 'cancel':
                future.cancel()
            else:
                pending = result._pending_start
                result._pending_start = (pending[0], pending[1] - 1, pending[2])
            result._poll_print_start()
            result._poll_print_start()
            self.assertTrue(result._start_error_visible)
            self.assertIsNone(result._pending_start)
            result.Goto_PrintProcess.assert_not_called()
            result.pd.postREST.assert_called_once()

    def test_success_without_status_times_out_without_retry(self):
        result = self.display(['a.gcode'])
        future = Future()
        future.set_result({'result': 'ok'})
        result._pending_start = (future, result.pd.state.epoch, 0)
        with patch.object(ui.time, 'monotonic', return_value=31):
            result._poll_print_start()
        self.assertTrue(result._start_error_visible)
        result.Goto_PrintProcess.assert_not_called()

    def test_obsolete_index_and_unlisted_path_are_rejected(self):
        result = self.backend(['a.gcode'])
        for path in (0, 'deleted.gcode'):
            with self.assertRaises(ValueError):
                result.openAndPrintFile(path)

    def test_renderer_scrolls_only_snapshot_without_network(self):
        result = self.display([f'{i:02}.gcode' for i in range(12)])
        result.select_file.set(10)
        result.index_file = 10
        result.Draw_Menu_Line = Mock()
        result.Redraw_SD_List()
        self.assertEqual(result.Draw_Menu_Line.call_count, result.TROWS)
        self.assertEqual(result.Draw_Menu_Line.call_args.args[-1], '09.gcode')
        result.pd.getREST.assert_called_once()

    def test_reconnect_same_revision_invalidates_cache_and_refetches(self):
        result = self.backend(['old.gcode'])
        data = snapshot()
        data['epoch'] = 2
        result.subscription.snapshot.return_value = data
        result.update_variable()
        self.assertFalse(result._files_loaded)
        self.assertEqual(result.files, [])
        with self.assertRaises(ValueError):
            result.openAndPrintFile('old.gcode')
        result.getREST.return_value = {'result': [{'path': 'new.gcode'}]}
        self.assertEqual(result.GetFiles(), ('new.gcode',))
        self.assertEqual(result.getREST.call_count, 2)

    def test_offline_drops_start_authority_before_ready_snapshot(self):
        result = self.backend(['old.gcode'])
        data = snapshot()
        data.update(state='disconnected', epoch=2)
        result.subscription.snapshot.return_value = data
        result.update_variable()
        self.assertFalse(result._files_loaded)
        with self.assertRaises(ValueError):
            result.openAndPrintFile('old.gcode')

class MainsailFileSortTests(unittest.TestCase):
    def make(self, settings):
        result = printer(snapshot())
        result.client.get = Mock(return_value={'result': {'value': settings}})
        result.getREST = Mock(return_value={'result': [
            {'path': 'folder/b.gcode', 'modified': 10, 'size': 30},
            {'path': 'A.gcode', 'modified': 30, 'size': 10},
            {'path': 'c.gcode', 'modified': 20, 'size': 20},
        ]})
        return result

    def test_default_is_newest_first_and_cache_avoids_repeat_requests(self):
        result=self.make({})
        self.assertEqual(result.GetFiles(), ('A.gcode','c.gcode','folder/b.gcode'))
        result.GetFiles()
        result.getREST.assert_called_once()
        result.client.get.assert_called_once_with('/server/database/item?namespace=mainsail&key=view.gcodefiles')

    def test_saved_fields_and_both_directions(self):
        for field,ascending in [('filename',('A.gcode','folder/b.gcode','c.gcode')),
                                ('modified',('folder/b.gcode','c.gcode','A.gcode')),
                                ('size',('A.gcode','c.gcode','folder/b.gcode'))]:
            for desc in (False,True):
                result=self.make({'sortBy':field,'sortDesc':desc})
                self.assertEqual(result.GetFiles(),tuple(reversed(ascending)) if desc else ascending)

    def test_invalid_missing_or_failed_database_defaults_to_modified(self):
        for setting in (None,[],{'sortBy':'unknown','sortDesc':True},
                        {'sortBy':'filename','sortDesc':'false'}):
            result=self.make(setting)
            self.assertEqual(result.GetFiles(),('A.gcode','c.gcode','folder/b.gcode'))
        result=self.make({})
        result.client.get.side_effect=MoonrakerError('missing namespace')
        self.assertEqual(result.GetFiles(),('A.gcode','c.gcode','folder/b.gcode'))
        self.assertIsNone(result.file_error)

    def test_numeric_invalid_values_and_ties_are_deterministic(self):
        result=self.make({})
        result.getREST.return_value={'result':[
            {'path':'z.gcode','modified':float('nan')},
            {'path':'b.gcode','modified':20},
            {'path':'a.gcode','modified':20},
            {'path':'missing.gcode'},
            {'path':'bool.gcode','modified':True},
        ]}
        self.assertEqual(result.GetFiles(),('a.gcode','b.gcode','bool.gcode','missing.gcode','z.gcode'))

    def test_periodic_resort_preserves_selected_path_and_discards_old_enter(self):
        view=display(snapshot());view.pd=self.make({})
        view.pd.GetDirectory = lambda directory='': view.pd.GetFiles()
        view._refresh_file_snapshot();view.select_file.set(2)
        view.checkkey=view.SelectFile
        view.pd.client.get.return_value={'result':{'value':{'sortBy':'filename','sortDesc':False}}}
        view.pd._file_sort_refresh_at=0
        self.assertTrue(view.pd.refresh_file_sort())
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        view.pd.openAndPrintFile=Mock()
        view.HMI_SelectFile()
        self.assertEqual(view._file_paths[view.select_file.now-1],'c.gcode')
        self.assertEqual(view.select_file.now,3)
        view.pd.openAndPrintFile.assert_not_called()
        view.pd.getREST.assert_called_once()

    def test_poll_interval_and_unchanged_sort_do_not_bump_revision(self):
        result=self.make({'sortBy':'size','sortDesc':False});result.GetFiles()
        revision=result.file_sort_revision
        self.assertFalse(result.refresh_file_sort())
        result.client.get.assert_called_once()
        result._file_sort_refresh_at=0
        self.assertFalse(result.refresh_file_sort())
        self.assertEqual(result.file_sort_revision,revision)

class DirectoryBrowserTests(unittest.TestCase):
    def test_hidden_entries_and_non_gcode_files_are_filtered_at_every_level(self):
        view,tree=self.make()
        for directory in ('','parts'):
            tree[directory]['dirs'].extend([{'dirname':'.thumbnails'}, {'dirname':'.thumbnail'},
                                           {'dirname':'normal folder'}])
            tree[directory]['files'].extend([{'filename':'preview.png'}, {'filename':'notes.txt'},
                                            {'filename':'model.gcode.backup'}, {'filename':'.hidden.gcode'},
                                            {'filename':'UPPER.GCODE'}])
        view.pd._directory_cache.clear()
        for directory in ('','parts'):
            prefix=directory+'/' if directory else ''
            paths=view.pd.GetDirectory(directory)
            self.assertIn(prefix+'normal folder/',paths)
            self.assertIn(prefix+'UPPER.GCODE',paths)
            for hidden in ('.thumbnails/','.thumbnail/','preview.png','notes.txt','model.gcode.backup','.hidden.gcode'):
                self.assertNotIn(prefix+hidden,paths)
            # Cached resorting must preserve the filter.
            view.pd.file_sort=('filename',False)
            self.assertEqual(set(paths),set(view.pd.GetDirectory(directory)))

    def make(self):
        result=printer(snapshot())
        result.client.get=Mock(return_value={'result':{'value':{}}})
        tree={
            '':{'dirs':[{'dirname':'parts','modified':15,'size':40},{'dirname':'empty','modified':5,'size':0}],
                'files':[{'filename':'root.gcode','modified':30,'size':5}]},
            'parts':{'dirs':[{'dirname':'inner','modified':10,'size':0}],
                'files':[{'filename':'b.gcode','modified':20,'size':10},{'filename':'A.gcode','modified':30,'size':20}]},
            'parts/inner':{'dirs':[],'files':[{'filename':'deep.gcode','modified':1,'size':1}]},
            'empty':{'dirs':[],'files':[]},
        }
        from urllib.parse import unquote
        def get(path):
            if path=='/server/files/list':
                return {'result':[{'path':prefix+'/'+f['filename'] if prefix else f['filename'],**f}
                    for prefix,data in tree.items() for f in data['files']]}
            directory=unquote(path.split('path=')[1])[len('gcodes/'):]
            if directory not in tree:raise MoonrakerError('Directory missing')
            return {'result':tree[directory]}
        result.getREST=Mock(side_effect=get)
        view=display(snapshot());view.pd=result
        view.checkkey=view.SelectFile;view._file_directory=''
        view._refresh_file_snapshot()
        view.get_encoder_state=Mock(return_value=view.ENCODER_DIFF_ENTER)
        view._show_message=Mock();view.Goto_MainMenu=Mock()
        return view,tree

    def choose(self,view,path):
        view.select_file.set(view._file_paths.index(path)+1)
        view.HMI_SelectFile()

    def test_root_directories_first_including_empty_directory(self):
        view,_=self.make()
        self.assertEqual(view._file_paths,('parts/','empty/','root.gcode'))
        self.choose(view,'empty/')
        self.assertEqual(view._file_directory,'empty');self.assertEqual(view._file_paths,())
        self.assertIn('No files',[c.args[-1] for c in view.lcd.draw_text.call_args_list])
        view.HMI_SelectFile()
        self.assertEqual(view._file_directory,'')
        self.assertEqual(view._file_paths[view.select_file.now-1],'empty/')

    def test_nested_navigation_back_and_full_path_print_submission(self):
        view,_=self.make();view.pd.postREST=Mock(return_value=Future())
        self.choose(view,'parts/');self.choose(view,'parts/inner/')
        view._open_file_preview = lambda path: (setattr(view, '_preview_path', path), setattr(view, '_preview_epoch', view.pd.state.epoch), setattr(view, '_preview_choice', 0), view.HMI_File_Preview())
        self.choose(view,'parts/inner/deep.gcode')
        view.pd.postREST.assert_called_once_with('/printer/print/start',json={'filename':'parts/inner/deep.gcode'})
        view._pending_start=None;view.select_file.reset();view.HMI_SelectFile()
        self.assertEqual(view._file_directory,'parts')
        self.assertEqual(view._file_paths[view.select_file.now-1],'parts/inner/')
        view.select_file.reset();view.HMI_SelectFile()
        self.assertEqual(view._file_directory,'')
        view.select_file.reset();view.HMI_SelectFile();view.Goto_MainMenu.assert_called_once()

    def test_sort_fields_and_direction_apply_within_each_directory(self):
        view,_=self.make()
        for field,asc in [('filename',('parts/A.gcode','parts/b.gcode')),
                          ('modified',('parts/b.gcode','parts/A.gcode')),
                          ('size',('parts/b.gcode','parts/A.gcode'))]:
            for desc in (False,True):
                view.pd.client.get.return_value={'result':{'value':{'sortBy':field,'sortDesc':desc}}}
                view.pd.refresh_file_sort(force=True)
                paths=view.pd.GetDirectory('parts')
                self.assertEqual(paths,('parts/inner/',)+(tuple(reversed(asc)) if desc else asc))
        self.assertEqual(view.pd.GetDirectory(''),('parts/','empty/','root.gcode'))

    def test_cached_directory_resort_needs_no_file_request(self):
        view,_=self.make();self.choose(view,'parts/')
        requests=view.pd.getREST.call_count
        view.pd.client.get.return_value={'result':{'value':{'sortBy':'modified','sortDesc':False}}}
        view.pd.refresh_file_sort(force=True)
        view._refresh_file_snapshot()
        self.assertEqual(view.pd.getREST.call_count,requests)
        self.assertEqual(view._file_paths,('parts/inner/','parts/b.gcode','parts/A.gcode'))

    def test_removed_selected_file_discards_enter_and_returns_to_back(self):
        view,tree=self.make();self.choose(view,'parts/')
        view.select_file.set(view._file_paths.index('parts/A.gcode')+1)
        tree['parts']['files']=[f for f in tree['parts']['files'] if f['filename']!='A.gcode']
        data=snapshot();data['file_revision']=view.pd.state.file_revision+1
        view.pd.subscription.snapshot.return_value=data;view.pd.update_variable()
        view.pd.openAndPrintFile=Mock();view.HMI_SelectFile()
        self.assertEqual(view.select_file.now,0)
        view.pd.openAndPrintFile.assert_not_called()
        self.assertNotIn('parts/A.gcode',view._file_paths)

    def test_removed_directory_allows_parent_back_without_printing(self):
        view,tree=self.make();self.choose(view,'empty/');del tree['empty']
        data=snapshot();data['file_revision']=view.pd.state.file_revision+1
        view.pd.subscription.snapshot.return_value=data;view.pd.update_variable()
        self.assertFalse(view._refresh_file_snapshot())
        view.HMI_SelectFile();self.assertEqual(view._file_directory,'')
        view.pd.sendGCode.assert_not_called()

    def test_folder_icon_and_labels_show_only_basename(self):
        view,_=self.make();self.choose(view,'parts/')
        view.Draw_Menu_Line=Mock();view.lcd.reset_mock()
        view.Draw_SDItem(0,0)
        view.Draw_Menu_Line.assert_called_once_with(0,False,'inner')
        from lcd_resources import ICON_FOLDER
        view.lcd.show_icon.assert_called_once_with(
            7, ICON_FOLDER, 26, view.MBASE(0) - 7)
        view.lcd.draw_rectangle.assert_not_called()
        view.Draw_SDItem(1,1)
        self.assertEqual(view.Draw_Menu_Line.call_args.args,(1,view.ICON_File,'A.gcode'))

    def test_unsafe_directory_and_entry_names_are_rejected(self):
        view,_=self.make()
        for path in ('../secret','parts/../secret','/parts','parts//inner'):
            with self.assertRaises(ValueError):view.pd.GetDirectory(path)
        view.pd._directory_cache.clear()
        view.pd.getREST=Mock(return_value={'result':{'dirs':[{'dirname':'../secret'}],'files':[]}})
        self.assertEqual(view.pd.GetDirectory(''),())
        self.assertIsNotNone(view.pd.file_error)


class FilePrefetchTests(unittest.TestCase):
    def test_prefetch_populates_root_and_reuses_cache_then_refreshes_revision(self):
        result = printer(snapshot())
        def response(url):
            if url == '/server/files/list':
                return {'result': [{'path': 'part.gcode'}]}
            if url.startswith('/server/files/directory?'):
                return {'result': {'dirs': [{'dirname': 'empty'}],
                                   'files': [{'filename': 'part.gcode'}]}}
            return {'result': {}}
        result.getREST = Mock(side_effect=response)
        result.prefetch_files()
        calls = result.getREST.call_count
        self.assertEqual(result.GetDirectory(''), ('empty/', 'part.gcode'))
        result.prefetch_files()
        self.assertEqual(result.getREST.call_count, calls)
        changed = snapshot(); changed['file_revision'] = 1
        result.subscription.snapshot.return_value = changed
        result.update_variable()
        before = result.getREST.call_count
        result.prefetch_files()
        self.assertGreater(result.getREST.call_count, before)
        self.assertIn((1, 1, ''), result._directory_cache)

    def test_prefetch_does_not_fetch_when_printer_is_offline(self):
        result = printer(snapshot())
        from printer_state import PrinterState
        data = snapshot(); data['state'] = 'disconnected'
        result.state = PrinterState.from_snapshot(data)
        result.getREST = Mock()
        result.prefetch_files()
        result.getREST.assert_not_called()
