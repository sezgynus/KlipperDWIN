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
