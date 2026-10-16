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

## Physical controller
Self Tests now offers H01/H05/H06/H07/H08/H09/H13 per standard heater.
Selection is read-only preflight; a separate confirmation sends the exact
120 s heat/dwell/OFF script through the existing completion WebSocket RPC.
Status/queue reads use the existing bounded worker, approximately once per
second only while a test runs. Two OFF target/zero-duty samples and 32 s
cooling precede the unlimited user observation. Metric success alone is no PASS.

**Stopping an active thermal test requests Klipper emergency shutdown.**
This bypasses the G-code dwell; ordinary OFF could wait behind that dwell.
The confirmation screen discloses this behavior. Safety/telemetry ambiguity,
unexpected target, another heater, print/operation conflict or technical
deadline also requests shutdown once, locks further heating and reports
unconfirmed shutdown explicitly if acknowledgment is absent. No automatic
restart is issued. Acknowledged shutdown is not independent electrical OFF
proof. The finite script also ends OFF if Petrel exits; Klipper protections
are retained. Petrel is not a hardware safety controller.
Cold idle admission, configured limits, lifecycle/epoch identity and fresh
dispatch guard are mandatory. No heater target is restored to a nonzero
value. Physical acceptance remains pending for every H target until the
operator's final batch test. Generic/application-specific and advanced
calibration adapters remain unavailable at this stage.

## PID calibration
H02 hotend and H03 bed use separate calibration registrations and Klipper
PID_CALIBRATE, at 150 C / 60 C respectively. Admission requires cold idle
heaters and no existing pending config. The completion RPC has a bounded
900 s retention; telemetry, queue and lifecycle remain monitored during
autotune. Normal Klipper target oscillation (target or target minus 5 C) is
accepted; unrelated target changes are rejected. A script appends OFF.
Successful RPC, newly pending positive finite Kp/Ki/Kd for the exact heater,
two zero-target/zero-duty samples and explicit observation are all required.
PID coefficients remain pending in Klipper; Petrel never invokes SAVE_CONFIG.
Unlike the fixed dwell tests, PID duration is controlled by Klipper's autotune.
If Petrel exits, host monitoring is lost; do not leave calibration unattended.
Cancel or technical failure requests emergency shutdown; no automatic retry.
H04 generic heaters still require an application-specific safe profile.
