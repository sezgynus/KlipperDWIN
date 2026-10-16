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
