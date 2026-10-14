import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.env_defaults import ensure_emulator_default

ROOT = Path(__file__).resolve().parents[1]


class InstallerDefaultsTests(unittest.TestCase):
    def test_existing_config_adds_default_once_and_preserves_enabled_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.env'
            for content in ('MOONRAKER_URL=http://localhost:7125',
                            'MOONRAKER_URL=http://localhost:7125\n'):
                path.write_text(content); path.chmod(0o600)
                self.assertTrue(ensure_emulator_default(path))
                self.assertTrue(path.read_text().startswith(content))
                self.assertFalse(ensure_emulator_default(path))
                self.assertEqual(path.read_text().count('PETREL_EMULATOR='), 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text('PETREL_EMULATOR=1\n')
            self.assertFalse(ensure_emulator_default(path))
            self.assertEqual(path.read_text(), 'PETREL_EMULATOR=1\n')

    def test_configurator_writes_off_and_preserves_existing_enabled_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); bin_dir = home / 'bin'; bin_dir.mkdir()
            commands = {
                'getent': f'#!/bin/sh\necho "user:x:1000:1000::${{TEST_HOME}}:/bin/bash"\n',
                'chown': '#!/bin/sh\nexit 0\n',
                'systemctl': '#!/bin/sh\nexit 1\n',
            }
            for name, content in commands.items():
                command = bin_dir / name; command.write_text(content); command.chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], TEST_HOME=tmp, USER='user', SUDO_USER='user')
            path = home / '.config/Petrel/Petrel.env'
            def configure():
                result = subprocess.run(['bash', str(ROOT / 'configure.sh')], input='\n' * 20,
                               text=True, env=env, capture_output=True)
                if result.returncode:
                    self.fail(result.stdout + result.stderr)
            configure()
            self.assertIn('PETREL_EMULATOR=0\n', path.read_text())
            path.write_text(path.read_text().replace('PETREL_EMULATOR=0', 'PETREL_EMULATOR=1'))
            configure()
            self.assertIn('PETREL_EMULATOR=1\n', path.read_text())

    @unittest.skipUnless(os.name == 'posix', 'Configurator integration needs POSIX shell paths')
    def test_configurator_preserves_custom_settings_and_literal_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); bin_dir = home / 'bin'; bin_dir.mkdir()
            commands = {
                'getent': '#!/bin/sh\necho "user:x:1000:1000::${TEST_HOME}:/bin/bash"\n',
                'chown': '#!/bin/sh\nexit 0\n',
                'systemctl': '#!/bin/sh\nexit 1\n',
            }
            for name, content in commands.items():
                command = bin_dir / name; command.write_text(content); command.chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'],
                       TEST_HOME=tmp, USER='user', SUDO_USER='user')
            path = home / '.config/Petrel/Petrel.env'; path.parent.mkdir(parents=True)
            literal = '$(touch ' + str(home / 'unexpected-evaluation') + ')'
            custom = [
                'PETREL_SETTINGS_FILE=' + str(home / 'custom-presets.json'),
                'PETREL_EMULATOR_FONT="/tmp/custom font.HZK"',
                'PETREL_EMULATOR_SOCKET=/tmp/custom-capture.sock',
                'PETREL_SCREENSHOT_DIRECTORY=/tmp/custom-shots',
                'FUTURE_OPTION=' + literal,
            ]
            path.write_text('PETREL_EMULATOR=1\n' + '\n'.join(custom) + '\n')
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'configure.sh')], input='\n' * 20,
                                        text=True, env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                lines = path.read_text().splitlines()
                for line in custom:
                    self.assertEqual(lines.count(line), 1)
                self.assertEqual(lines.count('PETREL_EMULATOR=1'), 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse((home / 'unexpected-evaluation').exists())
