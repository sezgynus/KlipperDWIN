"""Explicit recovery through Moonraker even while Klipper is not READY.

Small offline-only reads on the existing worker. No new threads/connections,
automatic restart, G-code, host reboot, or replay of interrupted operations.
"""
import logging
from dataclasses import dataclass
from collections.abc import Mapping
from time import monotonic


@dataclass(frozen=True, slots=True)
class RecoveryState:
    kind: str = 'checking'
    message: str = 'Checking Moonraker and Klipper...'
    actions: tuple = ()
    service: str | None = None

    @property
    def title(self):
        return {'checking': 'Printer connection', 'unavailable': 'Moonraker unavailable',
                'disconnected': 'Klipper disconnected', 'shutdown': 'Klipper shutdown',
                'error': 'Klipper error', 'startup': 'Klipper starting',
                'ready': 'Reconnecting printer'}.get(self.kind, 'Printer connection')


class KlipperRecovery:
    def __init__(self, client, worker, offline):
        self._client, self._worker, self._offline = client, worker, offline
        self.state = RecoveryState()
        self._read = self._command = None
        self._next = self._observed = 0.
        self._waiting_until = 0.
        self._active = self._closed = False
        self.notice = ''

    @property
    def busy(self):
        return self._command is not None or monotonic() < self._waiting_until

    def _probe(self):
        reply = self._client.get('/server/info')
        server = reply.get('result') if isinstance(reply, Mapping) else None
        if not isinstance(server, Mapping) or type(server.get('klippy_connected')) is not bool:
            raise ValueError('invalid_server_info')
        kind = server.get('klippy_state')
        if kind not in ('ready', 'startup', 'shutdown', 'error', 'disconnected'):
            raise ValueError('invalid_klippy_state')
        if server['klippy_connected'] is False:
            # Discover this Moonraker instance's service; never guess "klipper"
            # or pick the first service on a multi-printer host.
            service = None
            if 'machine' in server.get('components', ()):
                try:
                    system = self._client.get('/machine/system_info')['result']['system_info']
                    candidate = system.get('instance_ids', {}).get('klipper')
                    if (isinstance(candidate, str) and 0 < len(candidate) <= 128
                            and all(c.isascii() and (c.isalnum() or c in '_.@-') for c in candidate)
                            and candidate in system.get('available_services', ())
                            and system.get('provider') not in (None, 'none')):
                        service = candidate
                except Exception:
                    pass
            return RecoveryState('disconnected', 'Moonraker is reachable. Klipper is disconnected.',
                                 ('service',) if service else (), service)
        reply = self._client.get('/printer/info')
        info = reply.get('result') if isinstance(reply, Mapping) else None
        if not isinstance(info, Mapping) or info.get('state') not in ('ready', 'startup', 'error', 'shutdown'):
            raise ValueError('invalid_printer_info')
        kind = info['state']
        message = info.get('state_message')
        if not isinstance(message, str) or not message.strip():
            message = 'Klipper state: ' + kind
        # Bound retained error text; UI wraps and scrolls it without truncating
        # the important first line (including the MCU name).
        message = ''.join(c for c in message[:4096] if c in '\n\t' or c.isprintable())
        return RecoveryState(kind, message,
                             ('restart', 'firmware') if kind in ('error', 'shutdown') else ())

    def refresh(self):
        self._next = 0.

    def poll(self):
        if self._closed:
            return
        if not self._offline():
            if self._active:
                if self._read is not None:
                    self._read.cancel()
                self._read = self._command = None
                self._active = False
                self._waiting_until = 0.
                self.state = RecoveryState()
                self.notice = ''
            return
        self._active = True
        now = monotonic()
        if self._command is not None and self._command.done():
            command, self._command = self._command, None
            try:
                command.result()
                self.notice = 'Restart requested; waiting...'
                self._waiting_until = now + 15.
            except Exception as error:
                # A failed POST may have executed. Never retry automatically.
                from moonraker_client import MoonrakerError
                detail = str(error)[:100] if isinstance(error, MoonrakerError) else type(error).__name__
                self.notice = 'Restart failed: ' + detail
                logging.getLogger(__name__).warning('Recovery restart failed: %s', detail)
                self._waiting_until = 0.
            self._next = 0.
        if self._waiting_until and now >= self._waiting_until:
            self._waiting_until = 0.
            self.notice = 'Still not ready. Check error below.'
        if self._read is not None and self._read.done():
            read, self._read = self._read, None
            try:
                self.state = read.result()
                self._observed = now
            except Exception:
                self.state = RecoveryState('unavailable', 'Cannot reach Moonraker or read printer state. Retrying connection...')
                self._observed = 0.
            self._next = now + 2.
        if self._read is None and now >= self._next:
            try:
                self._read = self._worker.submit(self._probe, queue_timeout=3.)
            except Exception:
                self.state = RecoveryState('unavailable', 'Connection check unavailable. Retry.')
                self._next = now + 2.

    def request(self, action):
        if (self._closed or not self._offline() or self.busy
                or action not in self.state.actions):
            self.notice = 'State changed. Refresh and retry.'
            self.refresh()
            return False
        expected = self.state
        def guard():
            if self._closed or not self._offline():
                return False
            # Runs on the serialized command worker, never the UI owner.
            # A stale screen must not restart a now-ready/printing printer.
            live = self._probe()
            return (self._offline() and live.kind == expected.kind
                    and action in live.actions and live.service == expected.service)
        path, payload = {
            'restart': ('/printer/restart', {}),
            'firmware': ('/printer/firmware_restart', {}),
            'service': ('/machine/services/restart', {'service': expected.service})
        }[action]
        try:
            logging.getLogger(__name__).info('Recovery action requested: %s', action)
            self._command = self._client.post(path, payload, guard=guard,
                                               report_error=False, request_timeout=10.)
            self.notice = 'Sending restart request...'
            return True
        except Exception:
            self.notice = 'Restart not confirmed. Refresh state.'
            return False

    def close(self):
        self._closed = True
        if self._read is not None:
            self._read.cancel()
