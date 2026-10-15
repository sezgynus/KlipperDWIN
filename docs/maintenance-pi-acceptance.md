# Maintenance Test Engine — real Raspberry Pi acceptance

[Türkçe](maintenance-pi-acceptance_TR.md) · [Backend integration](maintenance-backend.md)

**Status:** GitHub CI validates regression and simulated asynchronous flows, but does **not** establish real Pi device acceptance. This document and its opt-in smoke script are the field-test procedure, not evidence that tests already ran on the user's printer.

## 1. Preserve the working master and ensure the printer is idle

Do not deploy the branch or interrupt `Petrel.service` during a print, paused print, MMU operation, calibration, or unstable connection. Do not copy printer configuration, passwords, API keys or other secrets into GitHub artifacts. No test should power the printer on/off or issue G-code.

For a noninvasive preliminary read-only smoke while normal Petrel runs master, add a separate branch worktree on the Pi (do not switch the service's current repository):

```sh
cd ~/Petrel
git fetch origin feature/maintenance-test-engine
git worktree add --detach /tmp/petrel-maintenance-acceptance origin/feature/maintenance-test-engine
cd /tmp/petrel-maintenance-acceptance
/home/sezgynpi/petrel-env/bin/python tools/validate_maintenance_pi.py --output /tmp/petrel-maintenance-readonly.json
```

The Python path is the confirmed Petrel virtualenv on the accepted Pi. The direct script now resolves its repository imports without requiring PYTHONPATH. The script creates a **temporary second Petrel backend connection** solely for read-only checks; it does not display a DWIN UI or run heater/motion tests. It exits and closes all its connections. `READ_ONLY_SMOKE_OK` requires S01 and S08 to return fresh, valid information; this is NOT a physical hardware PASS. `INCOMPLETE` or `BLOCKED` is not a test success; inspect the reason. An active queue, print, manual probe, MMU, missing fields or connection changes should prevent a read, not be bypassed.

```sh
git -C ~/Petrel worktree remove /tmp/petrel-maintenance-acceptance
```

## 2. Memory and responsiveness: controlled actual-service A/B

Capture the **master** baseline while the same real printer and workload are used:

```sh
cd ~/Petrel
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 /tmp/petrel-maintenance-acceptance/tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-master.json
```

Only after a safe, idle service restart using the feature branch (never during printing), repeat the capture with the service running the feature code:

```sh
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-feature.json
python3 tools/measure_petrel_resources.py compare --baseline /tmp/petrel-master.json --candidate /tmp/petrel-feature.json --max-uss-kib 1024 --max-rss-kib 1024
```

Verify the running `Petrel.service` actually uses the expected branch checkout, not the temporary worktree, and return service to master after measurement. Do not run the temporary backend smoke **during** memory measurement. Compare matching idle states and, separately, matching printing workload. Observe DWIN encoder/scroll speed, UI redraw, opening/closing Maintenance, and whether unrelated menu navigation causes any queue GET. Observe startup peak, CPU, and disconnect/reconnect behavior; the benchmark compares only process medians and cannot prove all UI performance requirements.

## Acceptance gate

Record the device/OS/Python version, Petrel HEAD SHA, Moonraker/Klipper versions, whether a job queue is installed, the sanitized smoke JSON, master/feature resource deltas, and manual UI responsiveness notes. Keep secrets and printer configuration private. **Do not mark Pi acceptance complete until the commands are actually run on that device and the measured results pass.** The GitHub CI test `tests/test_maintenance_pi_acceptance.py` uses fakes only; it never probes the printer or substitutes for this acceptance test.
