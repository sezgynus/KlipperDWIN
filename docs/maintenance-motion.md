# Motion Maintenance
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

## Pure motion contract (not yet a production adapter)
Cartesian/CoreXY coordinated motion is bounded by actual XYZ homing, configured
limits, cold/OFF heaters, enabled primary motors and explicit clear-path consent.
M04 uses Klipper's 10-cycle 1 mm STEPPER_BUZZ only for primary Cartesian motors;
independent multi-Z and coupled-motor buzzing are not admitted. M05 compiles a
1 mm roundtrip at <=5 mm/s XY / <=1 mm/s Z. M06 compiles one 10 mm outbound
move; a separately consented return requires the same measured-stop coordinate.
No homing is silently added to a move. XYZ limits have 2 mm margins and XY
motion requires >=5 mm Z clearance. Loaded mesh/unknown transforms, carriage
configurations and overridden protocol commands block rather than get disabled.
Unique SAVE/RESTORE_GCODE_STATE with MOVE=0 preserves modal settings; M400
confirms move completion. No FORCE_MOVE, SET_KINEMATIC_POSITION or tuning writes.
M03 is explicit configured XYZ homing; homing_override/macro G28 is rejected.
M12 compiles only for configured physical endstop phase with real last_home
history and no pending config, producing pending trigger_phase without save.
Software readback is not physical position proof. These are pure contracts;
controller/UI registrations are delivered separately after CI.

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
the encoder (0.1 mm increments); the displayed 10 mm initial value is only an
editable suggestion, never accepted without explicit operator input/confirmation.
A fresh preflight and separate Return to start confirmation precede reversal.
The stationary measurement and return-consent screens are unlimited. Changed
position/modes, disabled motors or lost homing block a return rather than guess.
Cancel while stationary leaves the carriage at the measured stop, without an
automatic return, and reports restoration false. Error <=0.2 mm plus confirmed
return/user observation passes this limited diagnostic; rotation_distance is
never changed. This is user-reported measurement, not calibrated metrology.

M12 uses existing Klipper homing history for one configured physical endstop
stepper. It neither homes automatically nor invokes SAVE_CONFIG. Exact pending
trigger_phase and preserved modes/position are required, followed by user
observation. Outcome is OBSERVED_USER with restore_verified=false because
pending calibration config is intentionally not rolled back. Existing pending
config blocks admission. M01 and M12 catalog scopes now support device rows,
retaining legacy global informational fallback when no per-device evidence
exists. No physical acceptance is granted by implementation or CI.
