# Maintenance resonance

[Turkish](maintenance-resonance_TR.md)

R01 queries the exact discovered chip and validates its actual acceleration vector. R03 parses noise only for the chip's assigned axes. R02/R04 offer an explicit axis choice when one sensor serves several axes. Unsupported axes never appear.

R02 runs Klipper TEST_RESONANCES with a unique filename and validates the real PSD CSV on the existing worker. Its result shows only that Klipper recorded the spectrum: Petrel does **not** rate the mechanical resonance or present an internal PSD peak as a shaper recommendation. An internal peak is retained solely for explicitly requested R05 trend/baseline comparisons. Same-host Moonraker access is required for local result files; unavailable, stale, malformed, unrelated or oversized files never produce PASS. To get an actual input-shaper recommendation, run **R04** separately with explicit motion consent: it invokes Klipper's native SHAPER_CALIBRATE and displays Klipper's shaper type and frequency, cross-checked against Klipper's pending configuration. Petrel never computes or chooses a shaper. SHAPER_CALIBRATE may immediately change live input shaping; Petrel never sends SAVE_CONFIG, so values are not persisted automatically.

Optional declarations: ~/.config/Petrel/maintenance-resonance.json:
```json
{"version":1,"mount_id":"toolhead-fixed-v1","belt_test":false}
```
After R02, explicitly save a mount baseline if wanted. R05 compares compatible frequency grids and peak shift against this reference; it does not diagnose a specific fault. Change mount_id after moving the sensor. Baselines are bounded, atomic, and configuration/firmware-specific. Discovery notices the saved capability at the next Klipper READY epoch.

With belt_test true and CoreXY/CoreXZ geometry, R06 performs two separately consented diagonal measurements and reports peak frequencies and their ratio, never belt tension in Newtons. Keep all configured resonance-test points and diagonal paths clear. Firmware limits and natural input-shaper restoration remain in force.

User choices never expire. Every dispatch refreshes queue/lifecycle safety; uncertain movement cancellation uses Klipper emergency_stop, without replay. No physical acceptance follows from CI.

## Missing homing preparation

A moving test no longer ends solely because XYZ is initially unhomed. Explicit `Home XYZ, then run test` consent starts shared guarded homing preparation; after two fresh XYZ/mode readbacks the same test automatically continues through fresh preflight. Failure/active cancellation never starts the original test. Read-only sensor/information tests do not home; excluded Leveling features remain excluded. Supported motion profiles, cold/OFF heaters, position/clearance and other safety conditions remain enforced.

## R02 live safety trace diagnosis (18 October 2026)

Physical R02/X session `e66bd3a0a19140a482d12a85b7e89c3e` submitted `TEST_RESONANCES` and later Petrel initiated `workflow_runtime_safety_unknown` emergency stop. The final job-queue read reported `paused`, with zero queued jobs, 21 ms before shutdown. That read alone does not identify which safety subcheck failed. A possible same-poll race existed: the running-phase guard checked the queue refresh future's completion a second time, even though a completed result had not yet been consumed into the safety snapshot. The second completion check is removed, with CI regression for the transition. Opt-in traces now include the exact `safety_reason`, queue age, and any `queue_refresh_unconsumed` exemption. Live print, lifecycle, other-operation and queue-state checks remain fail-closed. R02/X **is not physically accepted**; review the next trace before claiming a definitive root cause or measured resonance.

## Transient Moonraker read failure during R02/X (18 October 2026)

Trace session `001c0c5731db4ad9bc11b502534576e8` ran the signed `ad42ef5e` code. Homing completed and `TEST_RESONANCES` was submitted; after roughly 152 s, an HTTP safety read raised `MoonrakerError`. The latest successful job queue status was `paused`, empty. `read_queue_evidence` returned unknown, which the running workflow previously treated as `workflow_runtime_safety_changed` and sent `printer.emergency_stop`. The trace does not expose the network error subtype. A short, hard-bounded (20 s from last confirmed read) retry now tolerates an unknown **read result**, only while the original moving command is active and every live printer/print/pause/MMU/operation guard remains safe. Actually unsafe queue responses still stop immediately. Persistent read loss or live safety change still requires emergency stop. The opt-in trace records consecutive queue read failures and the retry/grace-expiry reason. No new dispatch uses cached queue data and no acceptance is inferred.
