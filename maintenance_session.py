"""Entry-only Maintenance capability lifecycle, independent of print telemetry.

The session retains a small immutable snapshot, never the source PrinterState,
Moonraker response bodies, HTTP client, or a worker. Optional service probes
run on an existing bounded read worker only while Maintenance is open.
"""
from maintenance_cache import MaintenanceCache


IDLE_STATES = frozenset(('standby', 'complete', 'cancelled', 'error'))


def idle(state):
    """Fail closed until current authoritative Klipper status is known idle."""
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


class MaintenanceDiscoverySession:
    __slots__ = ('cache', '_future', '_epoch', '_marker', '_stop')

    def __init__(self):
        self.cache = MaintenanceCache()
        self._future = None
        self._epoch = None
        self._marker = None
        self._stop = None

    @property
    def snapshot(self):
        return self.cache.snapshot

    def enter(self, state, client=None, worker=None):
        if not idle(state):
            self.cancel()
            return None
        previous = self.cache.snapshot
        changed = (previous is None or previous.epoch != state.epoch
                   or previous.config_marker != id(state.settings))
        if changed:
            self._stop_job()
            self._epoch, self._marker = state.epoch, id(state.settings)
            snapshot = self.cache.get(state)
            if client is not None and worker is not None:
                from maintenance_services import probe
                from threading import Event
                stop = self._stop = Event()
                # Closure exists only until the Future completes or is cancelled.
                self._future = worker.submit(lambda: probe(client, stop))
            return snapshot
        return previous

    def poll(self, state):
        """Consume optional evidence while Maintenance is open, never in print ticks."""
        job = self._future
        if job is None or not job.done():
            return False
        self._future = None
        self._stop = None
        if (not idle(state) or state.epoch != self._epoch
                or id(state.settings) != self._marker):
            self.cache.invalidate()
            return False
        try:
            services = job.result()
        except Exception:
            return False
        if services:
            self.cache.get(state, services)
            return True
        return False

    def _stop_job(self):
        if self._stop is not None:
            self._stop.set()
        if self._future is not None:
            self._future.cancel()
        self._future = None
        self._stop = None

    def cancel(self):
        self._stop_job()
        self.cache.invalidate()
        self._epoch = self._marker = None
