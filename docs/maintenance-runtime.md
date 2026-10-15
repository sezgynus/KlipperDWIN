# Live Maintenance safety evidence (development)

[Türkçe](maintenance-runtime_TR.md) · [Safety sessions](maintenance-safety.md)

**Stage 5:** On-demand live safety context for Petrel-owned operations and Moonraker job queue. This module has no hot-path polling, new worker, command or actuator.

`maintenance_runtime.read_queue_evidence(client, epoch, config_marker)` performs a small GET `/server/info` to positively identify whether the `job_queue` component exists. If present it reads `GET /server/job_queue/status`; only the known queue state and *empty/not empty* condition survive as immutable evidence. Filenames and IDs are discarded. A failed or malformed reply never means the queue is absent. Each observation has a monotonic timestamp and is accepted for at most three seconds, within the exact Klipper epoch/config.

`live_safety_context(printer, evidence)` obtains an on-demand subscription snapshot without copying the stable config tree, checks the running Petrel operation owners (jog/recovery, settings save, bed mesh, screws tilt, probe wizard, MMU) and produces a fresh `SafetyContext` for the existing fail-closed `precheck`. Missing print/pause/virtual SD/webhooks status is denied. Existing operations cannot be treated as idle simply because a UI menu is idle.

**Important:** Stage 5 only defines the provider. The next backend integration must perform queue GET work on Petrel's existing bounded worker (not on the UI thread), and must never call the queue endpoint from every telemetry update. External Moonraker clients can still change state between checks; physical commands will require additional dispatch-time safety checks.

Regression coverage: `tests/test_maintenance_runtime.py`; all tests run in GitHub Actions on push.
