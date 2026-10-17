# Maintenance resonance

[Turkish](maintenance-resonance_TR.md)

R01 queries the exact discovered chip and validates its actual acceleration vector. R03 parses noise only for the chip's assigned axes. R02/R04 offer an explicit axis choice when one sensor serves several axes. Unsupported axes never appear.

R02 runs Klipper TEST_RESONANCES with a unique filename and parses the real PSD CSV on the existing worker. Same-host Moonraker access is required for this local result-file transport; unavailable, stale, malformed, unrelated or oversized files never produce PASS. R04 validates both the measured recommendation and matching pending input-shaper configuration. It may change live input shaping; it never sends SAVE_CONFIG.

Optional declarations: ~/.config/Petrel/maintenance-resonance.json:
```json
{"version":1,"mount_id":"toolhead-fixed-v1","belt_test":false}
```
After R02, explicitly save a mount baseline if wanted. R05 compares compatible frequency grids and peak shift against this reference; it does not diagnose a specific fault. Change mount_id after moving the sensor. Baselines are bounded, atomic, and configuration/firmware-specific. Discovery notices the saved capability at the next Klipper READY epoch.

With belt_test true and CoreXY/CoreXZ geometry, R06 performs two separately consented diagonal measurements and reports peak frequencies and their ratio, never belt tension in Newtons. Keep all configured resonance-test points and diagonal paths clear. Firmware limits and natural input-shaper restoration remain in force.

User choices never expire. Every dispatch refreshes queue/lifecycle safety; uncertain movement cancellation uses Klipper emergency_stop, without replay. No physical acceptance follows from CI.

## Missing homing preparation

A moving test no longer ends solely because XYZ is initially unhomed. Explicit `Home XYZ, then run test` consent starts shared guarded homing preparation; after two fresh XYZ/mode readbacks the same test automatically continues through fresh preflight. Failure/active cancellation never starts the original test. Read-only sensor/information tests do not home; excluded Leveling features remain excluded. Supported motion profiles, cold/OFF heaters, position/clearance and other safety conditions remain enforced.
