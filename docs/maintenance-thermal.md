# Thermal Maintenance
H11 (reported duty), H14 (sensor temperature) and H16 (environment) are opt-in,
device-specific Diagnostics reads. They use the shared bounded worker and fresh
queue/session guards. Klipper eventtime is included; missing/nonfinite fields
are inconclusive. Duty is a reported fraction, not electrical power measurement.
No hardware PASS or physical acceptance is produced. No startup polling.
Physical H tests and calibration remain unavailable until their independent
thermal safety controller is installed. Existing acceptance is unchanged.
