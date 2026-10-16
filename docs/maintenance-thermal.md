# Thermal Maintenance
H11 (reported duty), H14 (sensor temperature) and H16 (environment) are opt-in,
device-specific Diagnostics reads. They use the shared bounded worker and fresh
queue/session guards. Klipper eventtime is included; missing/nonfinite fields
are inconclusive. Duty is a reported fraction, not electrical power measurement.
No hardware PASS or physical acceptance is produced. No startup polling.
Physical H tests and calibration remain unavailable until their independent
thermal safety controller is installed. Existing acceptance is unchanged.

## Measurement contract
H01/H05/H06/H07/H08/H09/H13 have independent evaluators over at most 256
Klipper-eventtime samples. Duplicates, gaps over 5 s and nonfinite data fail
closed. H01/H13 require at least 5 C rise; H05 positive average heating slope;
H06 reaches target minus 1 C; H07 peak overshoot at most 5 C; H08 at least
30 s after 20 s settling, peak-to-peak at most 2 C; H09 at least 30 s of
negative cooling slope. These are bounded diagnostic criteria, not factory
performance specifications or proof of independent thermal safety.
Initial standard targets are 60 C hotend / 45 C bed, duration 120 s and a
target+10 C observation ceiling strictly below configured max_temp. Every
configured heater must start OFF with reported zero duty. Generic heaters
require an explicit application profile; no chamber temperature is guessed.
The pure compiler includes OFF after its finite dwell. No SAVE_CONFIG.
