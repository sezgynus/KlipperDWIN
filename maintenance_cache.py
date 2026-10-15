"""Lazy Maintenance-only snapshot owner.

No import of maintenance_discovery and no allocated snapshot until the caller
opens Maintenance. No background thread, timer, subscription, or API call.
"""


class MaintenanceCache:
    __slots__ = ('_result',)

    def __init__(self):
        self._result = None

    @property
    def snapshot(self):
        return self._result

    def invalidate(self):
        self._result = None

    def get(self, state, services=()):
        """Return a cached result for one authoritative Klipper config epoch.

        The state is not retained. The services input must reflect API-confirmed
        integrations, not desired or guessed capabilities. A caller should
        invoke this only while Maintenance is open, never in the print tick.
        """
        if not state.ready:
            self.invalidate()
            return None
        key = tuple(sorted(set(services)))
        cached = self._result
        if (cached is not None and cached.epoch == state.epoch and
                cached.config_marker == id(state.settings) and
                cached.service_key == key):
            return cached
        from maintenance_discovery import discover  # Load only on first use.
        result = discover(state, services=key)
        self._result = result
        return result
