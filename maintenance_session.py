"""Maintenance capability lifecycle, driven only by Klipper READY events.

The owner retains a compact immutable capability snapshot, not source state,
HTTP replies, a client, worker, Future or a background polling task.
"""
import logging
from threading import Lock
from maintenance_cache import MaintenanceCache
from maintenance_profiles import read_profiles, approved_integrations

_log = logging.getLogger(__name__)

IDLE_STATES = frozenset(('standby', 'complete', 'cancelled', 'error'))


def idle(state):
    """Only the UI entry uses this print-state guard; discovery is passive."""
    if not state.ready:
        return False
    status = state.status
    print_stats = status.get('print_stats', {})
    sdcard = status.get('virtual_sdcard', {})
    paused = status.get('pause_resume', {})
    return (print_stats.get('state') in IDLE_STATES
            and sdcard.get('is_active') is not True
            and paused.get('is_paused') is not True
            and status.get('webhooks', {}).get('state', 'ready') == 'ready')


class MaintenanceDiscoveryManager:
    __slots__ = ('cache', '_lock', '_generation', '_profile_path')

    def __init__(self, profile_path=None):
        self.cache = MaintenanceCache()
        self._profile_path = profile_path
        self._lock = Lock()
        self._generation = 0

    @property
    def snapshot(self):
        with self._lock:
            return self.cache.snapshot

    def clear(self):
        with self._lock:
            previous = self.cache.snapshot
            self._generation += 1
            self.cache.invalidate()
        if previous is not None:
            _log.info('Maintenance discovery: CLEAR epoch=%d', previous.epoch)

    def ready(self, state, client=None, worker=None, latest=None, integrations=()):
        """Once per READY epoch: discover and optionally gather service evidence.

        Never called from Maintenance menu navigation. Future evidence is
        published only if this READY epoch and config are still current.
        """
        if not state.ready:
            self.clear()
            return None
        with self._lock:
            previous = self.cache.snapshot
            if (previous is not None and previous.epoch == state.epoch
                    and previous.config_marker == id(state.settings)):
                return previous
            self._generation += 1
            generation = self._generation
            local_services = approved_integrations(
                state, read_profiles(self._profile_path))
            local_services = tuple(set(local_services) | set(integrations))
            snapshot = self.cache.get(state, local_services)
        # One record per actual READY epoch, never per telemetry revision
        # or per UI navigation. Do not log config names, values or tokens.
        _log.info('Maintenance discovery: READY epoch=%d devices=%d features=%d',
                  state.epoch, len(snapshot.devices),
                  len(snapshot.available_features()))

        if client is None or worker is None or latest is None:
            return snapshot
        epoch, marker = state.epoch, id(state.settings)
        from maintenance_services import probe

        def work():
            try:
                services = tuple(set(probe(client)) | set(local_services))
                current = latest()
                if not current.ready or current.epoch != epoch or id(current.settings) != marker:
                    return
                with self._lock:
                    if generation != self._generation:
                        return
                    # This is the completion phase of the same startup
                    # discovery, not a new scan on entering Maintenance.
                    if services:
                        result = self.cache.get(current, services)
                    else:
                        result = self.cache.snapshot
                if result is not None:
                    _log.info(
                        'Maintenance discovery: EVIDENCE epoch=%d services=%d devices=%d features=%d',
                        epoch, len(services), len(result.devices),
                        len(result.available_features()))
            except Exception:
                # Optional service evidence must never disrupt printer work.
                return

        try:
            worker.submit(work)
        except Exception:
            pass
        return snapshot
