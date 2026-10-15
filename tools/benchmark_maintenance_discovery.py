#!/usr/bin/env python3
"""Offline, repeatable Maintenance discovery memory/time benchmark.

Run on a Pi Zero 2 W as well as a desktop. These synthetic results do not
replace live printer RSS/PSS/USS comparisons before/after integration.
"""
import argparse
import gc
from pathlib import Path
import sys
import time
import tracemalloc

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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fans', type=int, default=150)
    p.add_argument('--runs', type=int, default=20)
    opts = p.parse_args()
    if opts.fans < 1 or opts.runs < 1:
        p.error('--fans and --runs must be positive')
    printer = SyntheticPrinter(opts.fans)
    gc.collect()
    rss_start = linux_memory_kib()
    tracemalloc.start()
    baseline = tracemalloc.take_snapshot()
    from maintenance_discovery import discover
    runs = []
    snapshot = None
    for _ in range(opts.runs):
        begin = time.perf_counter()
        snapshot = discover(printer)
        runs.append((time.perf_counter() - begin) * 1000)
    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    allocations = tracemalloc.take_snapshot().compare_to(baseline, 'filename')
    retained = sum(stat.size_diff for stat in allocations)
    rss_end = linux_memory_kib()
    tracemalloc.stop()
    print('Devices:', len(snapshot.devices))
    print('Median discovery duration: %.3f ms' % sorted(runs)[len(runs) // 2])
    print('Python retained allocation delta: %.2f KiB' % (retained / 1024))
    print('Python current/peak tracked: %.2f / %.2f KiB' %
          (current / 1024, peak / 1024))
    if rss_start and rss_end:
        for key in ('Rss', 'Pss', 'USS'):
            print('%s before/after/delta: %s / %s / %+d KiB' %
                  (key, rss_start.get(key, 0), rss_end.get(key, 0),
                   rss_end.get(key, 0) - rss_start.get(key, 0)))
    print('NOTE: This benchmark imports discovery after baseline. It does not '
          'represent the complete Petrel UI or a real print.')


if __name__ == '__main__':
    main()