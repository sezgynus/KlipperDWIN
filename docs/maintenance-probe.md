# Maintenance probe workflows

[Turkish](maintenance-probe_TR.md)

P01/P02/P03/P04, P06, P12–P22 have concrete adapters. P05, P07–P11 remain exclusively in Leveling: probe-offset calibration, every bed-mesh operation and screws-tilt adjustment are deliberately not duplicated.

Each selection runs read-only preflight first, then requires explicit Start. Every later action refreshes queue and lifecycle evidence before dispatch. Homing is a prerequisite, not an automatically replayed command. Motion uses the configured firmware routines; clear their entire travel path. Cold, idle heaters and no pending configuration are required at entry. User questions never expire.

- P01 reads the exact plain G-code strings from Moonraker's current `configfile.settings.probe.activate_gcode` and `deactivate_gcode` (or the matching `bltouch` section) instead of assuming a servo name or angle. Upon operator Start, it sends the configured activation text verbatim followed by `QUERY_PROBE`; the operator then triggers/releases the probe and requests two further fresh `QUERY_PROBE` readings. Only after `open → TRIGGERED → open` does Petrel dispatch the configured deactivation text verbatim. PASS requires the deactivation RPC to finish; cancellation after activation also performs deactivation before ABORTED. No axes are moved by Petrel and no SAVE_CONFIG is sent. Configured hooks themselves are operator-controlled G-code and must not move the toolhead. Both hook fields must be defined together, or both absent. Jinja templates cannot be forwarded as plain G-code through Moonraker and are safely blocked rather than misexecuted. A failed/uncertain command cannot prove servo restoration and must not be treated as physical PASS.
- P02 captures one physical tap with LOAD_CELL_TEST_TAP. The 60-second firmware capture begins only after Start; the preceding question has no timeout.
- P03 records ten-sample min/max/range/average/median/stddev. P04 records measured XYZ. If a homed P04 start is below its safe Z threshold, operator Start includes a guarded Z-only lift toward 10 mm (or the highest allowed clearance below Z maximum). The lift uses saved/restored G-code modal state, a bounded slow relative Z move, a completed M400, and fresh XYZ/modal readback. Only after confirming the expected Z movement does Petrel issue PROBE through a new safety preflight, without re-homing XY/Z. Unexpected movement or mode mismatch prevents PROBE; uncertainty never counts as physical acceptance. If Z is already high enough, P04 sends PROBE directly. RPC success alone is not measurement evidence or PASS.
- P06/P12/P16/P17/P18 expose native interactive points with bounded TESTZ increments, Accept, and explicit abort. P12 also exposes Adjusted.
- P13/P14 verify firmware applied status. P15/P16/P17/P18 verify the corresponding pending configuration. No workflow sends SAVE_CONFIG.
- P19 explicitly deploys then stows the BLTouch pin; cancel requests stow before leaving the interaction.
- P20 records calibrated force and change between explicit captures; raw uncalibrated data is not grams.
- P21 requires explicit external AC, BD and AD measurements before CALC_MEASURED_SKEW. It does not apply a correction.
- P22 provides Next/Complete for firmware temperature-drift calibration. It never starts a heater; external warming remains operator-controlled.

Cancellation of an uncertain active movement requests Klipper emergency_stop. A firmware calibration may change live compensation or leave pending config; ending the workflow does not claim rollback. No physical acceptance is recorded by CI. Tests run only through Driver Branch Regression on the signed branch HEAD.

## Missing homing preparation

A moving test no longer ends solely because XYZ is initially unhomed. Explicit `Home XYZ, then run test` consent starts shared guarded homing preparation; after two fresh XYZ/mode readbacks the same test automatically continues through fresh preflight. Failure/active cancellation never starts the original test. Read-only sensor/information tests do not home; excluded Leveling features remain excluded. Supported motion profiles, cold/OFF heaters, position/clearance and other safety conditions remain enforced.
