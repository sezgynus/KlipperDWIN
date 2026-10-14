"""Immutable authoritative printer state, separate from editable UI values."""
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class PrinterState:
    connection: str = 'connecting'
    error: str = 'Moonraker subscription is connecting'
    epoch: int = 0
    revision: int = 0
    file_revision: int = 0
    software_version: str = 'unknown'
    objects: tuple = ()
    settings: Mapping = field(default_factory=lambda: MappingProxyType({}))
    status: Mapping = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_snapshot(cls, snapshot, reused_settings=None):
        return cls(connection=snapshot['state'], error=snapshot.get('error'),
                   epoch=snapshot.get('epoch', 0), revision=snapshot.get('revision', 0),
                   file_revision=snapshot.get('file_revision', 0),
                   software_version=snapshot.get('software_version', 'unknown'),
                   objects=tuple(snapshot.get('objects', ())),
                   settings=(reused_settings if reused_settings is not None
                             else freeze(snapshot.get('settings', {}))),
                   status=freeze(snapshot.get('status', {})))

    @property
    def ready(self):
        return self.connection == 'ready'
