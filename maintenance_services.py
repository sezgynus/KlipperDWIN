"""On-demand, read-only Moonraker evidence for Maintenance discovery.

No imports of Petrel UI, no background task, no persistent client/reference.
Call ``probe`` once per Klipper READY epoch using Petrel's existing worker.
Every evidence key reflects a *successful, structured* API response; missing or
invalid optional endpoints fail closed and never require issuing G-code.
"""
from collections.abc import Mapping


def _result(payload):
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get('result', {})
    return value if isinstance(value, Mapping) else {}


def parse_evidence(responses):
    """Convert transient Moonraker response mappings to a compact tuple.

    Keys are the exact REST endpoint paths. A missing response is not support.
    The caller owns and releases the response objects after this function.
    """
    keys = set()
    proc = _result(responses.get('/machine/proc_stats'))
    if isinstance(proc.get('system_cpu_usage'), Mapping) or isinstance(proc.get('system_memory'), Mapping):
        keys.add('machine.proc_stats')
    if isinstance(proc.get('cpu_temp'), (int, float)) and not isinstance(proc['cpu_temp'], bool):
        keys.add('machine.cpu_temp')
    if isinstance(proc.get('throttled_state'), Mapping):
        keys.add('machine.throttled_state')
    if isinstance(proc.get('network'), Mapping) and proc['network']:
        keys.add('machine.network')
    # Do not fetch machine/system_info at startup: it can be large and its
    # presence proves no testable feature. Storage capacity requires a
    # separate, on-demand disk_usage source with positive evidence.
    history = _result(responses.get('/server/history/totals'))
    if isinstance(history.get('job_totals'), Mapping):
        keys.add('history')
    info = _result(responses.get('/server/info'))
    components = info.get('components', ())
    if isinstance(components, (tuple, list)):
        components = frozenset(x for x in components if isinstance(x, str))
        if 'update_manager' in components:
            keys.add('update_manager')
        if 'gcode_store' in components or 'data_store' in components:
            keys.add('gcode_store')
    spool = _result(responses.get('/server/spoolman/spool_id'))
    if 'spool_id' in spool and (spool['spool_id'] is None or
            type(spool['spool_id']) is int and spool['spool_id']>0):
        keys.add('spoolman')
    # heaters.available_monitors is Klipper's authoritative list of driver
    # temperature monitors. A driver can be disabled and return null at READY
    # while still supporting temperature readout when enabled.
    monitor_reply = _result(responses.get('/printer/objects/query?heaters=available_monitors'))
    status = monitor_reply.get('status', {})
    heaters = status.get('heaters', {}) if isinstance(status, Mapping) else {}
    monitors = heaters.get('available_monitors', ()) if isinstance(heaters, Mapping) else ()
    if isinstance(monitors, (tuple, list)):
        for name in monitors[:64]:
            if (isinstance(name, str) and len(name) <= 96 and
                    name.startswith(('tmc2130 ', 'tmc2208 ', 'tmc2209 ',
                                     'tmc2240 ', 'tmc2660 ', 'tmc5160 ',
                                     'tmc5161 '))):
                keys.add('maintenance.driver_thermal_monitor:' + name)
    # A registered readable gcodes root proves Moonraker exposes its
    # directory-information API, whose on-demand reply contains disk_usage.
    # Reading roots is small; walking the potentially huge directory at
    # startup would violate the memory budget.
    root_reply = responses.get('/server/files/roots')
    root_items = root_reply.get('result') if isinstance(root_reply, Mapping) else None
    if isinstance(root_items, (tuple, list)):
        for item in root_items[:32]:
            if (isinstance(item, Mapping) and item.get('name') == 'gcodes'
                    and item.get('permissions') in ('r', 'rw')):
                keys.add('machine.disk')
                break
    # Do not infer access to database namespaces, Petrel diagnostics, or
    # records simply because a Moonraker component happens to be installed.
    return tuple(sorted(keys))


# Short read-only requests. G-code help/console and full histories are NEVER
# fetched during discovery; those may allocate substantial response bodies.
_ENDPOINTS = ('/server/info', '/machine/proc_stats', '/server/spoolman/spool_id',
              '/server/history/totals',
              '/printer/objects/query?heaters=available_monitors',
              '/server/files/roots')


def probe(client, cancelled=None):
    """Collect small READY-epoch API evidence, releasing every reply promptly.

    There is no response accumulator: one JSON reply is parsed and discarded
    before the next HTTP request. No new client, socket, subscriber or G-code.
    Optional endpoints fail closed without blocking other evidence.
    """
    evidence = set()
    for path in _ENDPOINTS:
        if cancelled is not None and cancelled.is_set():
            break
        try:
            # No long-lived response object: the temporary dict and reply
            # are eligible for collection before the next endpoint starts.
            evidence.update(parse_evidence({path: client.get(path)}))
        except (OSError, ValueError, RuntimeError):
            continue
    return tuple(sorted(evidence))
