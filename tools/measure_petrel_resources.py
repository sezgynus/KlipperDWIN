#!/usr/bin/env python3
"""Measure the running Petrel process without instrumenting Petrel itself.

A measurement must compare master and the feature branch on the SAME Pi,
printer configuration and equivalent print/idle workload. This standalone
tool runs only when explicitly invoked and installs no service.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import time


MEMORY_KEYS = ('Rss', 'Pss', 'USS')


def parse_smaps(content):
    memory = {}
    for line in content.splitlines():
        parts = line.split(':', 1)
        if len(parts) != 2:
            continue
        name = parts[0]
        if name in ('Rss', 'Pss', 'Private_Clean', 'Private_Dirty'):
            memory[name] = int(parts[1].strip().split()[0])
    memory['USS'] = memory.get('Private_Clean', 0) + memory.get('Private_Dirty', 0)
    if not {'Rss', 'Pss', 'Private_Clean', 'Private_Dirty'}.issubset(memory):
        raise ValueError('Incomplete smaps_rollup data')
    return {key: memory[key] for key in MEMORY_KEYS}


def cpu_ticks(stat):
    # /proc/PID/stat field 2 (comm) can contain whitespace and parentheses.
    end = stat.rfind(')')
    if end < 0:
        raise ValueError('Malformed /proc/PID/stat')
    fields = stat[end + 1:].strip().split()
    if len(fields) < 13:
        raise ValueError('Missing CPU times in /proc/PID/stat')
    return int(fields[11]) + int(fields[12])  # utime + stime, fields 14 and 15


def take_sample(pid):
    root = Path('/proc') / str(pid)
    mem = parse_smaps((root / 'smaps_rollup').read_text(encoding='ascii'))
    ticks = cpu_ticks((root / 'stat').read_text(encoding='ascii'))
    return time.monotonic(), mem, ticks


def capture(pid, seconds, interval):
    if pid <= 0 or seconds < 2 or interval <= 0:
        raise ValueError('PID must be positive, seconds >= 2, interval > 0')
    beginning = time.monotonic()
    deadline = beginning + seconds
    readings = []
    while True:
        timestamp, mem, ticks = take_sample(pid)
        readings.append((timestamp, mem, ticks))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    clock = os.sysconf('SC_CLK_TCK')
    elapsed = readings[-1][0] - readings[0][0]
    cpu = 100 * ((readings[-1][2] - readings[0][2]) / clock) / elapsed
    return {
        'pid': pid, 'seconds': round(elapsed, 2), 'sample_count': len(readings),
        'cpu_percent_single_core': round(cpu, 3),
        'memory_kib': {
            key: {
                'median': statistics.median(row[1][key] for row in readings),
                'peak': max(row[1][key] for row in readings),
                'minimum': min(row[1][key] for row in readings)
            } for key in MEMORY_KEYS
        }
    }


def compare(baseline, candidate, max_uss_kib, max_rss_kib=1024):
    result = {
        key: round(candidate['memory_kib'][key]['median'] -
                   baseline['memory_kib'][key]['median'], 2)
        for key in MEMORY_KEYS
    }
    cpu_diff = round(candidate['cpu_percent_single_core'] -
                     baseline['cpu_percent_single_core'], 3)
    print('Median memory change (KiB):', json.dumps(result, sort_keys=True))
    print('Process CPU change (percentage points of one core):', cpu_diff)
    print('WARNING: Compare only equivalent workload and the same hardware.')
    violations = []
    if result['USS'] > max_uss_kib:
        violations.append('USS %+g KiB exceeds %g KiB' %
                          (result['USS'], max_uss_kib))
    if result['Rss'] > max_rss_kib:
        violations.append('RSS %+g KiB exceeds %g KiB' %
                          (result['Rss'], max_rss_kib))
    if violations:
        print('FAIL:', '; '.join(violations))
        return 1
    print('PASS: median USS and RSS deltas both within configured budgets')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    record = commands.add_parser('capture')
    record.add_argument('--pid', type=int, required=True)
    record.add_argument('--seconds', type=float, default=30)
    record.add_argument('--interval', type=float, default=1)
    record.add_argument('--output', required=True)
    diff = commands.add_parser('compare')
    diff.add_argument('--baseline', required=True)
    diff.add_argument('--candidate', required=True)
    diff.add_argument('--max-uss-kib', type=float, default=1024)
    diff.add_argument('--max-rss-kib', type=float, default=1024)
    args = parser.parse_args()
    if args.command == 'capture':
        report = capture(args.pid, args.seconds, args.interval)
        Path(args.output).write_text(json.dumps(report, indent=2) + '\n',
                                     encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 0
    return compare(
        json.loads(Path(args.baseline).read_text(encoding='utf-8')),
        json.loads(Path(args.candidate).read_text(encoding='utf-8')),
        args.max_uss_kib, args.max_rss_kib)


if __name__ == '__main__':
    raise SystemExit(main())
