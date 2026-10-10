from concurrent.futures import Future
from threading import Event
import unittest
from unittest.mock import Mock, patch
import background_reads as reads
import test_capabilities as fixtures
import test_files as files


class BackgroundReadTests(unittest.TestCase):
    def blocked(self, result):
        worker = reads.ReadWorker(timeout=.1)
        entered, release = Event(), Event()
        def work():
            entered.set()
            release.wait(2)
            return result
        self.addCleanup(worker.close)
        self.addCleanup(release.set)
        return worker, work, entered, release

    def test_ui_reads_deduplicate_and_discard_old_epoch(self):
        p = fixtures.printer(fixtures.snapshot())
        worker, work, entered, release = self.blocked('old')
        p._read_worker = worker
        with self.assertRaises(fixtures.backend.ReadPending):
            p._read('test', work, 1)
        self.assertTrue(entered.wait(1))
        with self.assertRaises(fixtures.backend.ReadPending):
            p._read('test', work, 1)
        self.assertEqual(worker._queue.qsize(), 0)
        with self.assertRaises(fixtures.backend.ReadPending):
            p._read('test', lambda: 'new', 2)
        release.set()
        self.assertEqual(p._read_jobs['test'][1].result(1), 'new')
        self.assertEqual(p._read('test', lambda: 'wrong', 2), 'new')

    def test_queue_is_bounded_and_close_cancels_pending(self):
        worker, work, entered, release = self.blocked(True)
        worker._queue.maxsize = 1
        first = worker.submit(work)
        self.assertTrue(entered.wait(1))
        queued = worker.submit(lambda: True)
        rejected = worker.submit(lambda: True)
        self.assertIsInstance(rejected.exception(), reads.MoonrakerError)
        release.set()
        worker.close()
        self.assertTrue(queued.done())
        self.assertTrue(worker.submit(lambda: True).done())

    def test_all_ui_http_reads_return_while_network_waits(self):
        for method in ('refresh_mainsail_presets', 'refresh_file_sort', 'refresh_system_info', 'GetFiles', 'GetDirectory'):
            with self.subTest(method=method):
                p = fixtures.printer(fixtures.snapshot())
                worker, work, entered, release = self.blocked({'result': {}})
                p._read_worker = worker
                p.client.get.side_effect = lambda *args: work()
                p.getREST = lambda *args: work()
                with patch.object(fixtures.backend, 'network_info', return_value=('online', '127.0.0.1')), patch.object(fixtures.backend, 'host_metrics', return_value=(0, 30)):
                    getattr(p, method)(**({'force': True} if method.startswith('refresh_') else {}))
                self.assertTrue(entered.wait(1))
                self.assertFalse(release.is_set())
                release.set()
                worker.close()

    def test_pending_file_validation_can_be_cancelled(self):
        d = files.FileTests().display(['a.gcode'])
        worker, work, entered, release = self.blocked({'result': [{'path': 'a.gcode'}]})
        d.pd._read_worker = worker
        d.pd.getREST = lambda *args: work()
        d._preview_epoch = d.pd.state.epoch
        d._preview_path = 'a.gcode'
        d._preview_choice = 0
        d.checkkey = d.FilePreview
        d.pd.postREST = Mock()
        d.get_encoder_state = Mock(return_value=d.ENCODER_DIFF_ENTER)
        d.HMI_File_Preview()
        self.assertTrue(entered.wait(1))
        d.HMI_File_Preview()
        d.pd.postREST.assert_not_called()
        d._preview_choice = 1
        d.HMI_File_Preview()
        release.set()
        d._poll_preview_validation()
        d.pd.postREST.assert_not_called()
        self.assertFalse(d._preview_validation)

    def test_pending_validation_rejects_connection_change(self):
        d = files.FileTests().display(['a.gcode'])
        d._preview_epoch = d.pd.state.epoch - 1
        d._preview_validation = True
        d.pd.postREST = Mock()
        d._poll_preview_validation()
        self.assertTrue(d._start_error_visible)
        d.pd.postREST.assert_not_called()

    def test_mainsail_save_runs_off_ui_and_uses_frozen_values(self):
        p = fixtures.printer(fixtures.snapshot())
        worker, work, entered, release = self.blocked({'result': 'ok'})
        p._read_worker = worker
        p.presets_from_mainsail = True
        preset = fixtures.backend.material_preset_t('PLA', 200, 60)
        preset.mainsail_id = 'one'
        preset.mainsail_raw = {'name': 'PLA', 'values': {'extruder': {'value': 200}}}
        p.material_preset = [preset]
        p.client.timeout = 5
        posted = []
        def post(path, payload):
            posted.append(payload)
            future = Future()
            future.set_result(work())
            return future
        p.client.post.side_effect = post
        future = p.save_settings()
        self.assertTrue(entered.wait(1))
        preset.hotend_temp = 250
        self.assertIs(p.save_settings(), future)
        release.set()
        self.assertTrue(future.result(1))
        self.assertEqual(posted[0]['value']['values']['extruder']['value'], 200)
