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
Initial standard targets are 60 C hotend / 45 C bed and duration 120 s.
No Petrel-specific target-relative temperature-overshoot ceiling is enforced
for any H test: H07 still measures overshoot and grades its diagnostic metric,
but overshoot alone does not request emergency shutdown. The configured
Klipper heater min_temp/max_temp limits are retained. Every configured heater
must start OFF with reported zero duty. Generic heaters
require an explicit application profile; no chamber temperature is guessed.
The pure compiler includes OFF after its finite dwell. No SAVE_CONFIG.

## Physical controller
Self Tests now offers one **Thermal Characterization** entry (H01) per standard
heater. One finite heating/dwell/OFF/cooling run produces separate H01/H05/H06/
H07/H08/H09/H13 metrics and operator-reviewed results. These seven identifiers
remain independent in the catalog, trace and history; only their physical
actuation is consolidated. H02/H03/H04 PID remain separate.
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
Petrel reads Klipper's case-sensitive `save_config_pending_items` entries
`pid_Kp`, `pid_Ki`, `pid_Kd` for that heater's full config section name
(`extruder`, `heater_bed`, or `heater_generic NAME`). LCD/history metric
labels stay `pid_kp`, `pid_ki`, `pid_kd` for compatibility. A successful
Klipper RPC without these three numeric values is still INCONCLUSIVE, not
PID failure. PID coefficients remain pending in Klipper; Petrel never invokes
SAVE_CONFIG. A later PID test remains BLOCKED with
`existing_or_unknown_pending_config` until the operator intentionally
saves or discards prior pending settings and restarts as appropriate; Petrel
must not silently overwrite those settings.
Unlike the fixed dwell tests, PID duration is controlled by Klipper's autotune.
If Petrel exits, host monitoring is lost; do not leave calibration unattended.
Cancel or technical failure requests emergency shutdown; no automatic retry.
H04 generic heaters still require an application-specific safe profile.

## Explicit generic applications (H04)
Optional ~/.config/Petrel/maintenance-thermal-profiles.json is read only at
READY. Version 1 supports {"version":1,"heaters":[{"object":"heater_generic dryer",
"target":45,"duration_s":120}]}.
The former numeric `ceiling` field is accepted for compatibility but ignored;
it no longer caps temperature or triggers shutdown. This is an application
declaration, not evidence the example is safe for your dryer. Choose the
target from the actual appliance. At most 8 exact discovered generic heaters,
4096 bytes; unknown fields/duplicates/nonfinite values block the whole
profile. Configured min_temp < target < max_temp and duration 30..120 s are
required. Frozen profile tokens join the same snapshot;
there is no file I/O on menu entry or encoder ticks. Runtime cold/OFF,
other-heater, safety and dispatch checks still apply. H04 uses the declared
target and the separate 900 s calibration limit. Missing profiles do not expose
generic tests. Standard extruder/bed tests need no profile file.

## H01–H18 coverage
| ID | Implementation / required evidence |
|---|---|
| H01 | Guarded warmup; separate heater targets |
| H02 / H03 | Monitored hotend / bed PID; no automatic save |
| H04 | Same monitored PID for explicitly profiled generic applications |
| H05 / H06 | Heating slope / target arrival, independent criteria |
| H07 / H08 | Overshoot / settled stability, independent windows |
| H09 | Zero-target cooling slope, >=30 s |
| H10 | Conditional: compatible measured baseline is absent; no runnable adapter |
| H11 | Device-specific reported duty Diagnostics |
| H12 | Conditional: no validated nominal wattage + duty history; no energy estimate |
| H13 | Normal safe heating response; never deliberate runaway |
| H14 | Timestamped temperature Diagnostics, including heaters |
| H15 | Conditional: no verified co-located calibrated pair; no runnable adapter |
| H16 | Diagnostics only when actual environmental fields are discovered |
| H17 | Conditional: probe drift calibration also moves/heats; dedicated motion/thermal contract absent, not exposed |
| H18 | Conditional: no repeatable authorized fan/heater A/B profile; not exposed |

**Scope boundary:** all 16 confirmed reference-printer physical H targets are
implemented and pending physical acceptance. H10/H12/H15/H17/H18 are not
implemented hardware adapters; discovery or a catalog row does not change
that. Additional evidence and independent contracts are required before those
optional tests can be enabled. This is not a claim that all 18 IDs are runnable.

## Final batch acceptance
No physical commands were sent during development. On the real idle printer,
verify checkout/service HEAD and effective heater limits first.
1. Inspect H11/H14 and any actually available H16 in Diagnostics.
2. Run H01 independently for hotend and bed. Read the target and shutdown
   notice before confirming. Confirm the observed heating and OFF behavior.
3. With heaters cooled to cold admission, run H05, H06, H07, H08, H09 and H13
   separately for each target. Each row is an independent trial and result;
   no acceptance propagates to adjacent rows.
4. Run H02 and H03 last, supervised, one heater at a time. Existing pending
   config blocks calibration; decide how to handle any previously pending PID
   result yourself. Petrel never saves/restarts Klipper automatically.
5. Record exact feature/device, LCD result, observations and restoration
   evidence. Only then update that target's canonical JSON and both trackers.
Active stop means Klipper shutdown and may require an operator-managed
firmware restart after checking the printer. A missing shutdown acknowledgment
requires checking physical heater power immediately. No automatic retries.
CI is not physical acceptance. No local tests or emulator were run.

PID additionally requires observed positive duty and measured arrival in the target-minus-5 C band. Heater reactivation during cooling requests shutdown. The selected test's primary metric appears first on the LCD result.

The heat script uses M400 after G4 to await actual dwell completion before OFF. Configurations overriding G4/M400 or thermal commands with macros are not admitted as this trusted protocol.

## **Single-consent thermal safety refresh (17 October 2026)**

The first selection of H01/H02/H03/H04/H05/H06/H07/H08/H09/H13
performs only a cold/idle preflight and displays the separate
`Run thermal test` (or `Run PID`) confirmation. The user's selection of
that action is a **single explicit authorization for that operation**, even
when the earlier read-only queue evidence has aged while the user reads
the screen. In that case, Petrel displays `Refreshing HEAT safety`,
takes a **new** bounded cold/idle/queue/other-heater preflight, and on
fresh positive evidence proceeds directly to the one guarded finite
heater script. The old evidence never authorizes the dispatch. Immediately
before socket send, the normal live safety, thermal contract and epoch
checks remain mandatory. Failed, stale or interrupted refreshed preflight
does not dispatch G-code, does not auto-retry, and reports a blocked
condition; cancellation before heating does not request emergency
shutdown. An active or ambiguously dispatched thermal command still
uses the existing shutdown policy. The user can wait as long as desired
before the initial action; no idle response timeout or repeated click
exists. Preheat status no longer displays an uninitialized elapsed timer.
All H features share this fix; no physical acceptance is inferred from CI.

**Maintenance thermal ceiling removal (17 October 2026):** The former
`target + 10 C` and generic-profile `ceiling` emergency-stop thresholds
are removed across H01–H13. H02 PID calibration may overshoot its target
while Klipper autotunes; such samples remain valid measurements. H07 still
reports measured overshoot and evaluates its 5 C criterion as a test metric,
not as a heater-stop threshold. This change does not alter Klipper firmware
limits, live print/operation guards, off verification, cancellation or
uncertain-operation shutdown behavior. CI is not physical acceptance.

## Grouped thermal characterization (17 October 2026)
A single H01 selection for each discovered heater captures one bounded
thermal trajectory and evaluates seven independent conditions. A user sees
one consent before heating and one physical-observation confirmation after
verified OFF/cooling. Each resulting feature has its own status and primary
numeric evidence. Missing measurement windows remain INCONCLUSIVE; measured
criterion failures are FAILED_METRIC, not a printer emergency stop. A negative
operator observation is FAILED_USER. The parent result reports an aggregate;
the history stores seven sibling feature records with one shared timestamp
and one bounded worker write. Trace emits one result event with seven
component identities and evidence; no acceptance JSON is updated by CI.
The LCD scrolls seven status/evidence pairs and returns to the original
Self Tests row. The existing 120 s dwell is not extended automatically.
