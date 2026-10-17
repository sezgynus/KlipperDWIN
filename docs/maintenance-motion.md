# Motion Maintenance

## Required homing inside the selected test

Trace `0f7da07e7fe6402985255baaeb09e8bf` on 17 October blocked M04/X before motion solely because the axes were unhomed. M04/M05/M06 and M12 now open homing preparation inside the same test owner when initial XYZ/phase history is missing. The UI explicitly asks `Home XYZ, then run test`, covering the clear path for both homing and the selected test. The existing guarded G28+M400 protocol and two fresh XYZ/mode readbacks finish before a new original-test preflight and dispatch guard continue without another start confirmation. Already-homed tests skip unnecessary homing. Preparation is attempted only once per test; failed motion is never replayed.

Failed/cancelled homing never starts the original test; active cancellation requests emergency stop. Cold/OFF heaters, supported kinematics/commands, position bounds, enabled motors, Z clearance, mesh and lifecycle checks still apply after homing. A safe interior test position or cleared mesh is never assumed. M06 measurement/return never rehome; return retains separate consent. Diagnostic reads never initiate homing. Recording preserves the selected feature identity, preparation substage, homing RPC/readbacks and continuation separately. Implementation/CI grants no new physical acceptance.

M07/M08/M09 (driver status/temperature/current), M11 (enable state),
M12 (last homing phase), M13 (angle-driver temperature telemetry only),
M14 (commanded toolhead state) and M16 (known carriage modes) are opt-in
Diagnostics. Existing queue/lifecycle/session guards and bounded read worker
apply. No motor is enabled, homed or moved. No registers/config are written.
Null driver monitor status is inconclusive; no temperature is synthesized.
Klipper reports only nonzero drv_status fields; an empty mapping is distinct
from null. Position is commanded state, not measured physical displacement.
M12 diagnostics never calibrates or saves. Angle status is not shaft angle.
No physical acceptance changes. M02/M17 remain deliberately hidden.

## M01 and M10
M01 is per physical primary-axis endstop: explicitly query released, held,
released through Moonraker's authoritative endstop endpoint. No motion or
last_query reuse. Each operator prompt is unlimited; mismatched state can be
explicitly retried. Virtual/sensorless endstops are excluded. Final observation
is separate from transitions; released readback is the restoration evidence.
M10 reads TMC2208's structured monitor without enabling motors or DUMP_TMC.
Null monitor is unknown; standstill/open-load indications are not fabricated
short/overtemperature faults. Valid empty nonzero-only status means no reported
critical/warning flags, not proven motor health. Final operator acknowledgment
is OBSERVED_USER, never automatic hardware PASS. Other chips need their own
fault schema. No existing F/H acceptance changes.

## Motion contracts
Cartesian/CoreXY coordinated motion is bounded by actual XYZ homing, configured
limits, cold/OFF heaters, enabled primary motors and explicit clear-path consent.
M04 uses Klipper's 10-cycle 1 mm STEPPER_BUZZ only for primary Cartesian motors;
independent multi-Z and coupled-motor buzzing are not admitted. M05 compiles a
1 mm roundtrip at <=5 mm/s XY / <=1 mm/s Z. M06 compiles one 10 mm outbound
move; a separately consented return requires the same measured-stop coordinate.
Missing homing is completed inside the test after explicit preparation consent. XYZ limits have 2 mm margins and XY
motion requires >=5 mm Z clearance. Loaded mesh/unknown transforms, carriage
configurations and overridden protocol commands block rather than get disabled.
Unique SAVE/RESTORE_GCODE_STATE with MOVE=0 preserves modal settings; M400
confirms move completion. No FORCE_MOVE, SET_KINEMATIC_POSITION or tuning writes.
M03 is explicit configured XYZ homing; homing_override/macro G28 is rejected.
M12 compiles only for configured physical endstop phase with real last_home
history and no pending config, producing pending trigger_phase without save.
Software readback is not physical position proof. The pure compiler is connected to the registered controller/UI described below.

## Registered physical controller
M03/M04/M05/M06 and per-stepper M12 now join the physical router. Selecting a
row queues read-only preflight; separate clear-path confirmation dispatches one
guarded completion RPC. Every active step refreshes bounded status/queue data.
Two fresh readbacks confirm expected commanded coordinates/modal settings;
operator observation is still mandatory. They do not measure actual travel.
Active cancel, unsafe lifecycle/queue/operation, ambiguous command or missing
restore proof requests emergency shutdown once; no retry or blind reversal.
The controller locks further motion after ambiguity. Ordinary finite protocols
restore modes in the script; firmware protections remain enabled.

M06 stops after a 10 mm outward move. Enter actual ruler/caliper travel using
the encoder (0.01 mm increments); the displayed 10 mm initial value is only an
editable suggestion, never accepted without explicit operator input/confirmation.
A fresh preflight and separate Return to start confirmation precede reversal.
The stationary measurement and return-consent screens are unlimited. Changed
position/modes, disabled motors or lost homing block a return rather than guess.
Cancel while stationary leaves the carriage at the measured stop, without an
automatic return, and reports restoration false. Error <=0.2 mm plus confirmed
return/user observation passes this limited diagnostic; rotation_distance is
never changed. This is user-reported measurement, not calibrated metrology.

M12 uses existing Klipper homing history for one configured physical endstop
stepper. Missing axes/history trigger consented preparatory homing; SAVE_CONFIG is never invoked. Exact pending
trigger_phase and preserved modes/position are required, followed by user
observation. Outcome is OBSERVED_USER with restore_verified=false because
pending calibration config is intentionally not rolled back. Existing pending
config blocks admission. M01 and M12 catalog scopes now support device rows,
retaining legacy global informational fallback when no per-device evidence
exists. No physical acceptance is granted by implementation or CI.

## Final scope and field sequence
| ID | Delivery |
|---|---|
| M01 | Physical primary-axis switch open/held/released, per target |
| M02 | Deliberately hidden virtual-endstop manual-press pseudo-test |
| M03 | Explicit supported configured XYZ homing with clear-path consent |
| M04 | Primary Cartesian motor buzz, no independent multi-Z/coupled buzzing |
| M05 | Supported coordinated XYZ 1 mm roundtrip |
| M06 | External actual 10 mm travel entry, separately consented return |
| M07 | Driver monitor INFORMATION only; null is unknown |
| M08 | Real reported driver temperature only, if discovered |
| M09 | Reported current settings, not measured winding current |
| M10 | TMC2208 exact-schema passive fault/warning check and user observation |
| M11 | Motor enable information |
| M12 | Per configured physical stepper pending phase calibration; last_home diagnostics |
| M13 | Available angle-driver temperature status only; no invented shaft angle |
| M14 | Commanded position/homing/max-velocity information |
| M15 | No generic manual-stepper motion adapter without an application-specific contract |
| M16 | Supported reported carriage mode fields; no carriage activation |
| M17 | Deliberately hidden raw force/register-write pseudo-test |

The 22 confirmed reference M ledger targets now have adapters; M07's four rows
are INFORMATION adapters, not functional motor tests. All remain physically
pending; no F/H acceptance was modified. Other driver fault schemas and generic
manual steppers are not exposed as physical tests just because discovered.

Field order: M01 X/Y with the printer stationary and switches accessible;
M03 after clearing the bed/homing path; then deliberately position the already
homed carriage at an interior, raised, clear location through normal printer
controls. M04/M05/M06 then run per X/Y/Z as supported, cooling heaters first.
Keep primary motors enabled and clear the bed mesh yourself if the contract
reports that requirement; the test does not clear compensation. Missing homing is a consented preparation step.
A mechanical clearance acknowledgment cannot prove geometry for arbitrary
objects on the bed. Do not start a queued print or issue external motion while
a test owns the printer. Local Petrel motion guards reject competing owned
operations; external clients cannot be locked by this software reservation.

Run M10 and M07 while driver monitor data actually exists; disabled/null is
inconclusive, not a clean bill of health and not a reason to auto-enable motors.
M12 last: obtain homing statistics through deliberate normal homing, select
the exact configured phase stepper, review and approve pending calibration,
record the result. Handle pending config explicitly before calibrating a
second axis. SAVE_CONFIG is never automatic. M12 user outcome remains
OBSERVED_USER with pending config not restored; no electrical/metrology claim.

No local tests/emulator or physical motion were run during development.
All checks run on GitHub Actions, on the bot-signed feature HEAD. The same
result-origin/selection preservation and unlimited operator prompts apply to M.

Final audit: M12 phase history is read on demand; it is not added to the global
subscription. Dispatch rechecks subscribed position/modes/homing/pending config.
Mesh preflight requests only profile and bounds, never a matrix. Unknown
TMC2208 register schemas remain inconclusive. Information source rejection
releases its reservation. Confirmation information rows are inert; the measured
distance editor redraws immediately and never dispatches the return itself.

## 17 October physical verification — pre-homing position

Physical X/Y M01 endstops passed with explicit operator observation.
The second trace session (`2de3566ce59d476cb020ad83dd5360bf`, 787 events, no drops)
blocked M03 and 11 subsequent attempts at the same geometry check before dispatch:
`homed_axes=""`, position `[0,0,0]`, minima `[1.5,7,-5]`.
These are not 12 separate motor faults.

M03 does not treat unhomed zero placeholders as measured physical positions.
Finite/ordered configured limits, cold/OFF heaters, modes, overrides, lifecycle and
separate user consent remain checked. Already-homed axes must remain in bounds.
All XYZ homing, position and modal readbacks are verified after completion.
In that historical build, unhomed M04/M05/M06 returned `home_xyz_before_motion_test`; current preparation converts this prerequisite into consented homing.
M12 retains its axis/last_home checks.

Retest M03 alone first. After completion, use the normal Move menu to place XYZ
at least 2 mm inside the bounds, with Z at least 5 mm above its minimum for XY motion
and a mechanically clear path; keep motors enabled.
Then run M04/M05/M06. If a mesh is active, use the existing normal mesh-clear flow
required by the test. Leave M12 until homing history exists and run it last;
new calibration is refused while config changes are pending.

## 17 October M03 active queue-evidence correction

Session `69bd4367df274301b8e2f3275b493378`, HEAD `b60d729`: 448 events,
no drops/write errors. M03 passed preflight and sent G28+M400; the active
safety check requested shutdown about 0.23 seconds later. No physical acceptance.

Last queue read: monotonic 580503.541; dispatch: 580506.430;
first active check: 580506.657. Evidence was about 2.89 seconds old at dispatch,
3.12 seconds at the first check. The controller applied the 3-second admission
age to the active command before collecting its first fresh read.

The first active read is now scheduled immediately. A completed worker result's
fresh queue evidence is consumed before the previous sample's age is judged.
Admission/dispatch stay at 3 seconds. Active commands use the existing 5-second
read-watchdog bound for queue freshness too, matching the thermal controller.
Print/SD/pause/MMU/other-owner and epoch checks remain live each tick.
Unknown or older-than-5-second evidence and real conflicts still emergency-stop.
Recording includes exact `safety_reason` and `queue_age_s`;
age is sampled once per second rather than creating a new stage every tick.

A second M03 start was rejected by the existing uncertainty lock; no replay.
After verifying safe/OFF hardware and restarting the updated Petrel service,
retest M03 alone.

## Confirmation-screen retry correction

The latest 17 October M03 trace returned the first two confirmations to preflight and Cancel selection after the 3-second evidence expired; only the third dispatched. This is a UI flow defect. Consent for the unchanged movement now survives a bounded 12-second read-only safety refresh. The screen shows Refreshing safety / Your confirmation is kept. Fresh queue, lifecycle, position, modes and the same program must pass before dispatch; changed context blocks. Cancel sends no motion. M06 outward and return still require separate consent. Failed commands are never replayed.

The temporary recorder includes confirm_attempts, refresh_reason and an explicit confirmation_safety_refresh flow event; leaving the test page while pending is additionally flagged as left_test_while_pending. M03 physical acceptance is retained; physical validation of this UI correction is pending.

## Cleared mesh and definitive pre-send rejection correction

Session `8bf95a8e7cc6431c99ede09170b26605` on 17 October completed preparatory homing for M04/X. HTTP preflight showed empty profile_name and zero mesh_min/mesh_max; the subscription dispatch guard rejected clear_mesh_before_motion_test (#295 rpc_guard_denied/guard_denied). Klipper represents a cleared mesh as [[]], which the old Python truthiness test mistook for an active matrix. Small HTTP status and frozen subscription now use the same rule: explicitly empty profile, zero bounds, and only []/[[]] or tuple equivalents when a matrix exists. Numeric flat meshes, active/unnamed meshes and missing/unknown data still fail closed. No additional matrix query or mesh-clear command is introduced.

Only a transport-confirmed guard_denied before socket send finishes with the specific BLOCKED reason, without shutdown or replay. Sent, server-failed, timed-out or otherwise ambiguous motion retains emergency-stop handling. Preparatory homing was verified in this trace; M04 physical acceptance remains pending.

## M10/M12 evidence before review

M10 and M12 no longer ask Observed before displaying their evidence. Read-only evidence rows appear first in the test screen, followed by review actions; clicking an evidence row does nothing. M10 shows the target driver, passive-read scope, fault count and a readable name for every active flag (or No fault flags reported), plus its motor-health limitation. M12 shows the target, actual trigger_phase fraction, Pending config: YES / Saved to file: NO and preserved position/modes, without a repeatability claim. The operator can read/scroll and select Result reviewed or reject with Not accepted. Review has no inactivity deadline and sends no new motion or SAVE_CONFIG. M10/M12 physical acceptance remains pending explicit informed operator approval.
