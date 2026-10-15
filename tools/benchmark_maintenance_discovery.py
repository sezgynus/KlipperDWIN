#!/usr/bin/env python3
"""Offline Maintenance discovery footprint and time benchmark.

Use separate processes for uninstrumented RSS/PSS/USS and tracemalloc mode.
Tracemalloc itself retains trace metadata and changes the memory allocator;
its RSS must never be used as a Petrel production footprint claim.
"""
import argparse
import gc
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def linux_memory_kib():
    try:
        with open('/proc/self/smaps_rollup', encoding='ascii') as handle:
            lines = handle.readlines()
    except OSError:
        return {}
    result = {}
    for line in lines:
        field = line.split(':', 1)
        if len(field) != 2 or field[0] not in ('Rss', 'Pss', 'Private_Clean', 'Private_Dirty'):
            continue
        result[field[0]] = int(field[1].strip().split()[0])
    result['USS'] = result.get('Private_Clean', 0) + result.get('Private_Dirty', 0)
    return result


class SyntheticPrinter:
    ready = True
    epoch = 1

    def __init__(self, fans):
        self.objects = tuple('fan_generic f%d' % n for n in range(fans))
        self.settings = {name: {'max_power': 1., 'off_below': .1}
                         for name in self.objects}
        self.status = {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fans', type=int, default=150)
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--trace', action='store_true',
                        help='Track Python allocations (changes process RSS)')
    opts = parser.parse_args()
    if opts.fans < 1 or opts.runs < 1:
        parser.error('--fans and --runs must be positive')

    # These modules are already present in the actual Petrel backend.
    # Warming them prevents double-counting their dependencies as new
    # Maintenance allocations in this standalone synthetic process.
    import printer_state
    import maintenance_cache

    printer = SyntheticPrinter(opts.fans)
    tracer = None
    baseline = None
    if opts.trace:
        import tracemalloc
        tracer = tracemalloc
        tracer.start()
        baseline = tracer.take_snapshot()
    gc.collect()
    rss_start = linux_memory_kib()
    from maintenance_discovery import discover

    durations = []
    snapshot = None
    for _ in range(opts.runs):
        start = time.perf_counter()
        snapshot = discover(printer)
        durations.append((time.perf_counter() - start) * 1000)
    gc.collect()

    rss_end = linux_memory_kib()
    print('Mode:', 'tracemalloc (instrumented)' if opts.trace else 'uninstrumented')
    print('Devices:', len(snapshot.devices))
    print('Median discovery duration: %.3f ms' % sorted(durations)[len(durations) // 2])
    compact = (sys.getsizeof(snapshot) + sys.getsizeof(snapshot.devices)
               + sys.getsizeof(snapshot.global_modes) + sys.getsizeof(snapshot.service_key)
               + sum(sys.getsizeof(item) + sys.getsizeof(item.modes)
                     + sys.getsizeof(item.name) for item in snapshot.devices))
    print('Snapshot Python size estimate: %.2f KiB' % (compact / 1024))

    if tracer is not None:
        current, peak = tracer.get_traced_memory()
        allocations = tracer.take_snapshot().compare_to(baseline, 'filename')
        retained = sum(stat.size_diff for stat in allocations)
        print('Python retained allocation delta: %.2f KiB' % (retained / 1024))
        print('Python current/peak tracked: %.2f / %.2f KiB' %
              (current / 1024, peak / 1024))
        print('WARNING: Tracing overhead inflates RSS; do not use traced RSS for acceptance.')
        tracer.stop()

    if rss_start and rss_end:
        for key in ('Rss', 'Pss', 'USS'):
            print('%s before/after/delta: %s / %s / %+d KiB' %
                  (key, rss_start.get(key, 0), rss_end.get(key, 0),
                   rss_end.get(key, 0) - rss_start.get(key, 0)))
    print('NOTE: synthetic subprocess only. A real Pi Zero 2 W Petrel process '
          'before/after comparison is required for the production target.')


if __name__ == '__main__':
    main()
