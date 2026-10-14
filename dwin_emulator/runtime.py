"""Opt-in lifecycle and private, on-demand screenshot service."""
from datetime import datetime
import json
import errno
import logging
import os
from pathlib import Path
import socket
import stat
from threading import RLock, Thread
from uuid import uuid4


def default_socket():
    # SSH login sessions and systemd services often have different XDG values.
    return Path.home() / '.cache' / 'Petrel-emulator' / 'control.sock'


class Emulator:
    """Future conditions call set_enabled; enabling requires a new panel baseline.

    No packet history is retained while disabled. The UI must reconnect/reset the
    panel after re-enabling before screenshots are allowed. No UART is owned here.
    """
    def __init__(self, enabled=False, factory=None, font_path=None):
        self.lock = RLock()
        self.factory = factory
        self.font_path = font_path
        self.model = None
        self.online = False
        self.baseline = False
        self.set_enabled(enabled)

    def set_enabled(self, enabled):
        with self.lock:
            if bool(enabled) == (self.model is not None):
                return
            if enabled:
                if self.factory is None:
                    from .framebuffer import Framebuffer
                    from .assets import PanelAssets
                    self.factory = lambda: Framebuffer(PanelAssets(font_path=self.font_path))
                self.model = self.factory()
            else:
                self.model = None
            self.baseline = False
            self.online = False

    def reset_panel(self):
        with self.lock:
            if self.model is not None:
                self.model.reset()
                self.baseline = True
                self.online = True

    def disconnect_panel(self):
        with self.lock:
            self.online = False

    def feed(self, frame):
        with self.lock:
            if self.model is None or not self.baseline:
                return
            try:
                self.model.feed(frame)
            except Exception as error:
                description = f'0x{frame[1]:02x}: {error}'
                if description not in self.model.errors:
                    logging.warning('Petrel emulator: %s', description)
                self.model.errors.add(description)

    def snapshot(self):
        with self.lock:
            if self.model is None:
                raise RuntimeError('Petrel emulator is disabled')
            if not self.online or not self.baseline:
                raise RuntimeError('LCD is disconnected or a fresh panel baseline is required')
            return self.model.snapshot()

    def close(self):
        self.set_enabled(False)


class ScreenshotServer:
    """Only Unix-domain IPC, no live view, TCP listener or automatic screenshots."""
    def __init__(self, emulator, socket_path=None, output=None):
        self.emulator = emulator
        self.path = Path(socket_path or default_socket()).expanduser()
        self.output = Path(output or Path.home() / 'Petrel-screenshots').expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = self.path.parent.stat()
        if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) & 0o077:
            raise ValueError('Screenshot socket directory must be owned by this user with mode 0700')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if self.path.exists():
                entry = self.path.lstat()
                if not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != os.getuid():
                    raise ValueError('Refusing to replace a non-owned screenshot socket')
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(.2)
                    try:
                        probe.connect(str(self.path))
                    except OSError as error:
                        if error.errno != errno.ECONNREFUSED:
                            raise
                        self.path.unlink()
                    else:
                        raise RuntimeError('A screenshot server already owns this socket')
            self.sock.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.sock.listen(2)
            self.sock.settimeout(.2)
        except BaseException:
            self.sock.close()
            raise
        self.closed = False
        self.thread = Thread(target=self._serve, name='Petrel-screenshot', daemon=True)
        self.thread.start()

    def _save(self, file_format, frame=False):
        if file_format not in ('png', 'bmp'):
            raise ValueError('Format must be png or bmp')
        image, sequence = self.emulator.snapshot()
        if not isinstance(frame, bool):
            raise ValueError("Frame must be a boolean")
        if frame:
            from .presentation import with_frame
            image = with_frame(image)
        self.output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S_%f')
        target = self.output / f'{stamp}_{uuid4().hex[:8]}.{file_format}'
        # Snapshot copying occurs under the renderer lock; disk I/O does not.
        temporary = target.with_suffix('.tmp')
        try:
            with temporary.open('xb') as stream:
                image.save(stream, format=file_format.upper(), **({'compress_level': 0} if file_format == 'png' else {}))
            temporary.rename(target)
        finally:
            temporary.unlink(missing_ok=True)
        return {'path': str(target.resolve()), 'sequence': sequence,
                'width': image.width, 'height': image.height}

    def _serve(self):
        while not self.closed:
            try:
                connection, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(2)
                try:
                    request = bytearray()
                    while not request.endswith(b'\n'):
                        chunk = connection.recv(512)
                        if not chunk or len(request) + len(chunk) > 1024:
                            raise ValueError('Invalid screenshot request')
                        request.extend(chunk)
                    data = json.loads(request)
                    if data.get('command') != 'screenshot':
                        raise ValueError('Only screenshot requests are supported')
                    result = dict(ok=True, **self._save(data.get('format', 'png'), data.get('frame', False)))
                except Exception as error:
                    result = {'ok': False, 'error': str(error)}
                try:
                    connection.sendall(json.dumps(result).encode() + b'\n')
                except OSError:
                    pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.sock.close()
        self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)
