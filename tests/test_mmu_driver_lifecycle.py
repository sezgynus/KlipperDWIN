"""New UART heartbeat, atlas ownership, input batching and popup lifecycle."""
import time
import unittest
from unittest.mock import Mock, patch
import test_mmu_driver as packets
import test_mmu_ui as fixtures
import test_mmu_power_integration as power
import test_regressions as application
from ui_events import InputEvent


class MMUDriverLifecycleTests(unittest.TestCase):
    def test_one_encoder_event_has_one_refresh_and_no_flash_or_cache_replacement(self):
        v, _ = fixtures.MMUUITests().make()
        v.lcd = packets.lcd()
        v._closed = False
        v._uart_online = True
        v._uart_epoch = 1
        v._encoder_event = v.ENCODER_DIFF_NO
        v.get_encoder_state = lambda: v._encoder_event
        v._process_input(InputEvent('press', 1, 1, 1))
        opcodes = [f[1] for f in v.lcd.serial.frames]
        self.assertEqual(v._mmu_page, 'gates')
        self.assertEqual(opcodes.count(0x3D), 1)
        self.assertEqual(v.lcd._virtual_area_pictures, {0: 14})
        self.assertFalse(set(opcodes) & {0x22, 0x25, 0x31, 0x32, 0x33})
        v.pd.subscription.request.assert_not_called()

    def test_heartbeat_reconnect_restores_atlas_and_mmu_without_replaying_operation(self):
        fixture = fixtures.MMUUITests()
        v, _ = fixture.make()
        fixture.press(v, 2)
        fixture.press(v, 2)
        v._mmu_page = 'status'
        v._mmu_canvas_page = None
        v.lcd = packets.lcd()
        old = v.lcd
        old.handshake = Mock(return_value=False)
        v._closed = False
        v._settings = ('/dev/fake',)
        v._uart_online = True
        v._uart_epoch = 1
        v._next_uart_probe = 0
        v._loop = Mock()
        v.last_status = v.pd.status
        now = time.monotonic()
        with patch.object(application.ui.time, 'monotonic', return_value=now):
            v._ui_tick()
        with patch.object(application.ui.time, 'monotonic', return_value=now + 3):
            v._ui_tick()
        self.assertFalse(v._uart_online)
        self.assertTrue(old._closed)
        restored = packets.lcd()
        restored._virtual_area_pictures = {}
        restored._atlas_virtual_areas_loaded = False
        # Constructor restores virtual areas before the UI draws its canvas.
        restored.load_atlases()
        with patch.object(application.ui, 'T5UIC1Display', return_value=restored), \
                patch.object(application.ui.time, 'monotonic', return_value=now + 9):
            v._ui_tick()
        self.assertTrue(v._uart_online)
        self.assertEqual(v._mmu_page, 'status')
        opcodes = [f[1] for f in restored.serial.frames]
        self.assertEqual(opcodes.count(0x22), 1)
        self.assertIn(0x27, opcodes)
        self.assertFalse(set(opcodes) & {0x25, 0x31, 0x32, 0x33})
        self.assertEqual(restored._virtual_area_pictures, {0: 14})
        self.assertEqual(v.pd.subscription.request.call_count, 1)
        self.assertIsNotNone(v.pd.mmu_session.pending)

    def test_connection_or_epoch_change_cancels_mmu_power_confirmation(self):
        fixture = power.MMUPowerIntegrationTests()
        for case in ('offline', 'epoch'):
            v, data = fixture.view()
            v._mmu_open('map')
            v._mmu_map_draft[0] = 3
            fixture.popup(v)
            if case == 'offline':
                data['state'] = 'disconnected'
                data['error'] = 'offline'
            else:
                data['epoch'] += 1
            v.pd.update_variable()
            v._poll_mmu()
            self.assertEqual(v.checkkey, v.MMUMenu)
            self.assertEqual(v._mmu_page, 'map')
            self.assertEqual(v._mmu_map_draft[0], 3)
            self.assertIsNone(v._power_origin)
            v.pd.power_off_if_on.assert_not_called()
            v.pd.subscription.request.assert_not_called()

    def test_panel_loss_cancels_popup_and_preserves_mmu_confirmation(self):
        fixture = power.MMUPowerIntegrationTests()
        v, _ = fixture.view()
        fixtures.MMUUITests().press(v, 2)
        op = v._mmu_confirmation
        fixture.popup(v)
        v._uart_epoch = 1
        v._uart_failed()
        self.assertEqual(v.checkkey, v.MMUMenu)
        self.assertIsNone(v._mmu_canvas_page)
        self.assertIs(v._mmu_confirmation, op)
        self.assertFalse(v._power_focus)
        v.pd.power_off_if_on.assert_not_called()
        v.pd.subscription.request.assert_not_called()

    def test_periodic_print_updates_do_not_overwrite_mmu_power_popup(self):
        fixture = power.MMUPowerIntegrationTests()
        v, _ = fixture.view()
        fixture.popup(v)
        v.pd.status = 'printing'
        v.Goto_PrintProcess = Mock()
        v._present_print_state()
        self.assertEqual(v.checkkey, v.PowerConfirm)
        v.Goto_PrintProcess.assert_not_called()

    def test_offline_tick_clears_power_focus_and_retains_read_only_mmu_back(self):
        fixture = power.MMUPowerIntegrationTests()
        v, data = fixture.view()
        v._mmu_selection = 0
        fixture.event(v, v.ENCODER_DIFF_CCW)
        data['state'], data['error'] = 'disconnected', 'offline'
        v.pd.update_variable()
        v._poll_mmu()
        self.assertFalse(v._power_focus)
        self.assertFalse(v._power_at_first_item())
        v.pd.power_off_if_on.assert_not_called()

    def test_fresh_input_after_epoch_change_cancels_popup_without_shutdown(self):
        fixture = power.MMUPowerIntegrationTests()
        v, data = fixture.view()
        fixture.popup(v)
        v._closed = False
        v._uart_online = True
        v._uart_epoch = 1
        v._encoder_event = v.ENCODER_DIFF_NO
        v.get_encoder_state = lambda: v._encoder_event
        data['epoch'] += 1
        v._process_input(InputEvent('press', 1, data['epoch'], 1))
        self.assertEqual(v.checkkey, v.MMUMenu)
        self.assertIsNone(v._power_origin)
        v.pd.power_off_if_on.assert_not_called()
        v.pd.subscription.request.assert_not_called()
