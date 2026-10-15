"""Compact Maintenance snapshot cache populated once per Klipper READY epoch.

No independent thread, subscription, network client or menu-entry discovery.
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

        The state is not retained. Services need positive API evidence.
        The caller invokes this once at Klipper READY, then once more when
        asynchronous service evidence arrives. Never on menu entry.
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
