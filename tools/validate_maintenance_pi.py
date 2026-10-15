#!/usr/bin/env python3
"""Explicit, read-only Pi acceptance smoke for Petrel Maintenance.

Runs only when manually invoked on a stopped/idle printer, not from the
regular test suite or the Petrel service. No G-code, power, motion, heater,
fan, save-config, or actuator commands are issued by this script.
The check starts a temporary second Petrel backend client; close it promptly.
"""
import argparse
import json
import math
from pathlib import Path
import tempfile
import sys
from time import monotonic, sleep

# Executing tools/validate_maintenance_pi.py directly sets sys.path[0] to
# tools/, not the Petrel project root. Resolve imports from this script's
# checkout; never depend on cwd, PYTHONPATH, or the running service path.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


REQUIRED_FEATURES = ('S01', 'S08')
OPTIONAL_FEATURES = ('S02', 'S03', 'S05', 'S10')


def smoke(printer, seconds=40.0, clock=monotonic, nap=sleep):
    """Return a sanitized report; physical hardware PASS is never inferred."""
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 5:
        raise ValueError('seconds must be finite and at least five')
    deadline = clock() + seconds
    ready_until = min(deadline, clock() + 15)
    report = {'verdict': 'INCOMPLETE', 'ready': False, 'observations': {},
              'note': 'Information checks only; not physical hardware PASS.'}
    available = set()
    while clock() < ready_until:
        printer.update_variable()
        if printer.state.ready:
            available = {row.feature_id for row in printer.maintenance_read_plan()}
            if all(feature in available for feature in REQUIRED_FEATURES):
                report['ready'] = True
                break
        nap(.15)
    if not report['ready']:
        report['reason'] = 'ready_or_required_information_evidence_unavailable'
        return report

    for feature in REQUIRED_FEATURES + OPTIONAL_FEATURES:
        if feature not in available:
            if feature in REQUIRED_FEATURES:
                report['reason'] = feature + '_unavailable'
                return report
            report['observations'][feature] = {'status': 'UNAVAILABLE'}
            continue
        accepted, reason = printer.start_maintenance_read(
            feature, timeout=min(8, max(.1, deadline - clock())))
        if not accepted:
            report['observations'][feature] = {
                'status': 'BLOCKED', 'reason': reason}
            if feature in REQUIRED_FEATURES:
                report['reason'] = 'required_information_blocked'
                return report
            continue
        while clock() < deadline:
            printer.update_variable()
            result = printer.poll_maintenance_read()
            if result is not None:
                if result.status is None and result.evidence:
                    # Evidence was already whitelisted and bounded by executor.
                    report['observations'][feature] = {
                        'status': 'OBSERVED', 'fields': dict(result.evidence)}
                else:
                    report['observations'][feature] = {
                        'status': result.status or 'INCONCLUSIVE',
                        'reason': result.reason}
                break
            nap(.1)
        else:
            printer.cancel_maintenance_read()
            report['observations'][feature] = {
                'status': 'ERROR', 'reason': 'overall_deadline'}
        if (feature in REQUIRED_FEATURES and
                report['observations'][feature]['status'] != 'OBSERVED'):
            report['reason'] = 'required_information_not_observed'
            return report

    report['verdict'] = 'READ_ONLY_SMOKE_OK'
    report['reason'] = 'required_information_observed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--moonraker', default='http://127.0.0.1:7125')
    parser.add_argument('--seconds', type=float, default=40.0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    from printerInterface import PrinterData

    # No modification of the user's persistent Petrel preset files.
    with tempfile.TemporaryDirectory(prefix='petrel-readonly-') as scratch:
        printer = PrinterData(
            URL=args.moonraker,
            settings_path=str(Path(scratch) / 'presets.json'))
        try:
            result = smoke(printer, seconds=args.seconds)
        finally:
            printer.close()

    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result['verdict'] == 'READ_ONLY_SMOKE_OK' else 2


if __name__ == '__main__':
    raise SystemExit(main())
