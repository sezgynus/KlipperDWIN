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
    machine = _result(responses.get('/machine/system_info'))
    # Moonraker has no documented /machine/disk_usage. The file manager's
    # /server/files/directory?path=gcodes can expose disk_usage but might
    # return a huge file listing; never fetch it in global capability discovery.
    # The storage screen may query disk usage on demand separately.
    # machine/system_info is NOT proof of free disk space.
    if isinstance(machine.get('system_info'), Mapping):
        keys.add('machine.system_info')
    history = _result(responses.get('/server/history/totals'))
    if isinstance(history.get('job_totals'), Mapping):
        keys.add('history')
    info = _result(responses.get('/server/info'))
    components = info.get('components', ())
    if isinstance(components, (tuple, list)):
        components = frozenset(x for x in components if isinstance(x, str))
        if 'update_manager' in components:
            keys.add('update_manager')
        if 'gcode_store' in components:
            keys.add('gcode_store')
    # Do not infer access to database namespaces, Petrel diagnostics, or
    # records simply because a Moonraker component happens to be installed.
    return tuple(sorted(keys))


# Short read-only requests. G-code help/console and full histories are NEVER
# fetched during discovery; those may allocate substantial response bodies.
_ENDPOINTS = ('/server/info', '/machine/proc_stats', '/machine/system_info',
              '/server/history/totals')


def probe(client, cancelled=None):
    """Read minimal evidence synchronously on an existing off-UI read worker.

    ``client`` is Petrel's already-open MoonrakerClient, NOT a new connection.
    Individual unavailable optional endpoints are ignored. Errors do not
    fabricate support for missing services. An optional cancellation Event
    can terminate superseded startup discovery between requests.
    """
    responses = {}
    try:
        for path in _ENDPOINTS:
            if cancelled is not None and cancelled.is_set():
                break
            try:
                responses[path] = client.get(path)
            except (OSError, ValueError, RuntimeError):
                continue
        return parse_evidence(responses)
    finally:
        responses.clear()
