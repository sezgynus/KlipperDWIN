"""Info rendering and asynchronous refresh regression coverage."""
from concurrent.futures import Future
import unittest
from unittest.mock import Mock, patch

from test_capabilities import display, snapshot, printer, backend
from info_qr import extra_info_rows


class InfoIncrementalTests(unittest.TestCase):
    def view(self):
        view = display(snapshot())
        view.pd.refresh_system_info = Mock(return_value=False)
        return view

    def test_visible_value_only_clears_its_own_field(self):
        view = self.view()
        view.Draw_Info_Menu()
        view.lcd.reset_mock()
        view.pd.system_info['network'] = 'Offline'
        view.Draw_Info_Menu()
        view.lcd.move_area.assert_not_called()
        view.lcd.copy_cache1.assert_not_called()
        view.lcd.draw_text.assert_called_once()
        self.assertEqual(view.lcd.draw_text.call_args.args[-3:], (120, 140, 'Offline'))
        view.lcd.draw_rectangle.assert_called_once_with(
            1, view.lcd.Color_Bg_Black, 120, 140, 255, 155)

    def test_rounded_hidden_and_truncated_changes_send_no_drawing(self):
        view = self.view()
        view.pd.system_info.update(host_cpu=10.1, wifi_ssid='abcdefghijklmnopq-one')
        view.Draw_Info_Menu()
        view.lcd.reset_mock()
        view.pd.system_info.update(host_cpu=10.2, wifi_ssid='abcdefghijklmnopq-two',
                                   petrel='hidden new version')
        view.Draw_Info_Menu()
        view.lcd.draw_text.assert_not_called()
        view.lcd.draw_rectangle.assert_not_called()
        view.lcd.copy_cache1.assert_not_called()
        view.lcd.move_area.assert_not_called()

    def test_batched_scroll_moves_once_but_large_jumps_and_layout_changes_redraw(self):
        view = self.view()
        view.Draw_Info_Menu()
        view.lcd.reset_mock()
        view._info_scroll = 3
        view.Draw_Info_Menu()
        self.assertEqual(view.lcd.move_area.call_count, 1)
        self.assertEqual(view.lcd.move_area.call_args.args[2], 72)
        view.lcd.reset_mock()
        view._info_scroll = 0
        view.Draw_Info_Menu()
        self.assertEqual(view.lcd.move_area.call_count, 1)
        self.assertEqual(view.lcd.move_area.call_args.args[2], 72)
        view.lcd.reset_mock()
        view._info_scroll = len(view._info_items()) + extra_info_rows() - 11
        view.Draw_Info_Menu()
        view.lcd.move_area.assert_not_called()
        view.lcd.reset_mock()
        view.pd.system_info['mcus'] = ({'name': 'mcu extra'},)
        view.Draw_Info_Menu()
        view.lcd.move_area.assert_not_called()
        self.assertTrue(view.lcd.draw_rectangle.called)

    def test_batched_scroll_and_value_updates_match_full_render(self):
        from tools.render_docs_screenshots import canvas
        from PIL import ImageChops
        view, reference = canvas(), canvas()
        maximum = len(view._info_items()) + extra_info_rows() - 11
        sequence = [0, 3, 1, 7, 4, maximum, maximum-3, maximum,
                    maximum-2, maximum, 0, 2, 2]
        for step, scroll in enumerate(sequence):
            for panel in (view, reference):
                panel.pd.system_info.update(
                    host_cpu=10+step, host_ram=90-step,
                    network='Online' if step % 2 else 'Offline',
                    wifi_ssid='Long wireless name' if step % 2 else 'AP')
                panel._info_scroll = scroll
            reference._info_render_scroll = None
            view.Draw_Info_Menu(); view.lcd.update()
            reference.Draw_Info_Menu(); reference.lcd.update()
            actual = view.framebuffer.snapshot()[0].crop((0, 90, 256, 356))
            expected = reference.framebuffer.snapshot()[0].crop((0, 90, 256, 356))
            self.assertIsNone(ImageChops.difference(actual, expected).getbbox(),
                              (step, scroll))

    def test_new_lcd_forces_complete_render(self):
        view = self.view()
        view.Draw_Info_Menu()
        view.lcd = Mock(DWIN_WIDTH=272, DWIN_HEIGHT=480)
        view.Draw_Info_Menu()
        view.lcd.move_area.assert_not_called()
        self.assertTrue(view.lcd.draw_rectangle.called)


class InfoPendingReadTests(unittest.TestCase):
    def test_pending_reads_skip_local_metrics_and_snapshot_copies(self):
        data = printer(snapshot())
        future = Future()
        data._read_jobs.clear()
        data._read_worker = Mock()
        data._read_worker.submit.return_value = future
        data.subscription.lifecycle.return_value = {'epoch': 1}
        data.subscription.snapshot.reset_mock()
        data._system_info_refresh_at = 0
        with patch.object(backend, 'network_info', return_value=('Online', '1.2.3.4')) as network, \
                patch.object(backend, 'host_metrics', return_value=(12, 45)) as metrics, \
                patch.object(backend, 'host_memory_usage', return_value=30) as memory:
            for _ in range(4):
                self.assertFalse(data.refresh_system_info())
            network.assert_not_called()
            metrics.assert_not_called()
            memory.assert_not_called()
            data.subscription.snapshot.assert_not_called()
            data._read_worker.submit.assert_called_once()
            future.set_result((('AP', -50), {'result': {'version_info': {}}}, None))
            self.assertTrue(data.refresh_system_info())
            network.assert_called_once()
            metrics.assert_called_once()
            memory.assert_called_once()
            self.assertFalse(data.refresh_system_info())
            metrics.assert_called_once()

    def test_reconnect_discards_pending_info_read(self):
        data = printer(snapshot())
        old, new = Future(), Future()
        data._read_jobs.clear()
        data._read_worker = Mock()
        data._read_worker.submit.side_effect = [old, new]
        data._system_info_refresh_at = 0
        data.subscription.lifecycle.return_value = {'epoch': 1}
        self.assertFalse(data.refresh_system_info())
        data.subscription.lifecycle.return_value = {'epoch': 2}
        self.assertFalse(data.refresh_system_info())
        self.assertTrue(old.cancelled())
        self.assertEqual(data._read_worker.submit.call_count, 2)
