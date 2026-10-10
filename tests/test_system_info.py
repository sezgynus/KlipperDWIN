import socket
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import system_info


class SystemInfoTests(unittest.TestCase):
    @patch.object(system_info.subprocess, 'run')
    def test_wifi_association_and_fractional_signal(self, run):
        run.side_effect = [SimpleNamespace(stdout='Interface wlan0\n'),
                           SimpleNamespace(stdout='Connected to aa:bb\n\tSSID: My WiFi\n\tsignal: -64.50 dBm\n')]
        self.assertEqual(system_info.wifi_info(), ('My WiFi', -64.5))
        self.assertEqual(run.call_args.kwargs['timeout'], 1)
        self.assertEqual(run.call_args.args[0], ['iw', 'dev', 'wlan0', 'link'])

    @patch.object(system_info.subprocess, 'run')
    def test_wifi_disconnected_and_missing_signal(self, run):
        run.side_effect = [SimpleNamespace(stdout='Interface wlan0\n'), SimpleNamespace(stdout='Not connected.\n')]
        self.assertEqual(system_info.wifi_info(), ('Disconnected', None))
        run.side_effect = [SimpleNamespace(stdout='Interface wlan0\n'), SimpleNamespace(stdout='SSID: Office\n')]
        self.assertEqual(system_info.wifi_info(), ('Office', None))

    @patch.object(system_info.subprocess, 'run')
    def test_wifi_missing_tool_and_timeout(self, run):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('iw', 1)):
            run.side_effect = error
            self.assertEqual(system_info.wifi_info(), ('Unavailable', None))

    def test_signal_thresholds_and_column_width(self):
        for value, level in [(-30, 'Strong'), (-60, 'Strong'), (-61, 'Medium'),
                             (-70, 'Medium'), (-71, 'Poor'), (-100, 'Poor')]:
            text = system_info.wifi_signal_text(value)
            self.assertIn('({})'.format(level), text)
            self.assertIn('{} dBm'.format(value), text)
            self.assertLessEqual(len(text), 17)
        self.assertEqual(system_info.wifi_signal_text(None), 'N/A')

    def test_updater_version_prefers_full_git_description(self):
        versions = {'KlipperDWIN': {
            'version': 'v0.4.0-2',
            'full_version_string': 'v0.4.0-2-g1234abcd',
        }}
        self.assertEqual(
            system_info.updater_version(versions, 'KlipperDWIN', full=True),
            'v0.4.0-2-g1234abcd')

    def test_updater_version_handles_missing_component(self):
        self.assertEqual(system_info.updater_version({}, 'mainsail'), 'Unavailable')

    @patch.object(system_info.socket, 'if_nameindex', return_value=[(1, 'lo'), (2, 'eth0')])
    @patch.object(system_info.fcntl, 'ioctl')
    def test_network_info_selects_active_non_loopback_ipv4(self, ioctl, _interfaces):
        def response(_fd, request, packed):
            name = packed.rstrip(bytes([0])).decode('ascii')
            if request == system_info.SIOCGIFFLAGS:
                flags = (system_info.IFF_UP | system_info.IFF_LOOPBACK
                         if name == 'lo' else system_info.IFF_UP)
                return bytes(16) + flags.to_bytes(2, 'little') + bytes(238)
            if request == system_info.SIOCGIFADDR:
                return bytes(20) + socket.inet_aton('192.168.1.50') + bytes(232)
            raise AssertionError(request)
        ioctl.side_effect = response
        self.assertEqual(system_info.network_info(), ('Online', '192.168.1.50'))


if __name__ == '__main__':
    unittest.main()
