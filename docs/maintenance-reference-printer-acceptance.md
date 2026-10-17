# Maintenance — reference printer physical acceptance tracker

[Türkçe](maintenance-reference-printer-acceptance_TR.md) · [JSON source of truth](maintenance-reference-printer-acceptance.json) · [Test catalog](maintenance-test-catalog.md)

> **PERSISTENT DEVELOPMENT / ACCEPTANCE RECORD.** Read this file and its JSON ledger at the start of the next Maintenance development session. It describes one sanitized reference printer, never a production Petrel hardware allowlist.

**Evidence boundary:** the independent 121-ID hardware reference from 15 Oct 2026, the 16 Oct 2026 discovery log and explicit user observations. The log confirms **54 discovered features**, but no serialized list of their exact IDs was preserved. Here, `confirmed` means confirmed by the independent capability reference, **not** an exact complete dump of the 54 currently observed IDs. `conditional` entries are not currently authorized, discoverable test commands.

**Strict separation:** installed hardware ≠ implemented adapter ≠ CI PASS ≠ real-printer user acceptance. **Forty-two** hardware checks have operator approval. Revised F02 (2,000 ms/stage), four-color O04 and adaptive five-stage F12 were accepted on 16 Oct 2026. Older outcomes remain in JSON history; latest LCD outcome and electronic restoration readback were not separately reported. One accepted device/axis never propagates PASS to another target with the same feature ID.

**Per-device tracking:** **62 rows / 46 IDs** — 42 ACCEPTED, 14 PENDING, 5 CONDITIONAL, 1 N/A. **F12 adaptive search and its reported LCD PASS were accepted on the real reference printer; an exact PWM threshold was not provided. F02/O04 latest restoration was not separately verified.**

**Acceptance semantics:** For grouped thermal characterization, acceptance certifies that the *test procedure* worked; it does not mean the printer met every thermal performance threshold. Extruder H07/H08 remain `FAILED_METRIC` and are never rewritten to PASS.

**Mandatory after each user-approved test:** set only that target's JSON `status` to `accepted`; record date, operator observation, controller outcome and `restore_verified` in `acceptance`; check only the corresponding target in both EN/TR tables in the same signed commit. Add relevant regressions; verify the full CI suite on the **bot-signed HEAD**. Never mark an item done because of a config line, HTTP success, G-code OK, simulated CI or an informational read. Never merge `master` without explicit request.

**Excluded:** informational-only S01/S02/S03/S05/S08/S10 and H11/H14/M09/P09 etc are not physical PASS. No RPM measurement without the part-fan tachometer. The Z endstop is virtual, not a pressable Z switch. Servo probe is not BLTouch. R02 maps X/Y only. The temporary PFAB percentage-display sensor is excluded from this *reference fixture*, never from generic discovery.

**17 Oct trace acceptance:** S15 physical encoder (both directions + click), S16 five colors and S17 10/50/100% backlight each have explicit `observe(true)`, `PASSED_USER` and controller restore evidence. Session `dec3042495ca4ab78b58b947e2b3c73a`. P03/P04 automatic measurements were also recorded; physical acceptance was not granted. [Detailed trace review](maintenance-acceptance-2026-10-17.md). The second session also accepted physical X/Y M01 endstops with `open → TRIGGERED → open` and explicit operator observation.

## User-approved physical checks

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [x] | F01 | `fan` | Part fan rotation | Available | **ACCEPTED** |
| [x] | F02 | `fan` | Part fan speed steps | Available | **ACCEPTED (2,000 ms/stage)** |
| [x] | F12 | `fan` | Adaptive five-step startup PWM threshold | Available | **ACCEPTED (iterative search / LCD PASS)** |
| [x] | S18 | `pwm_cycle_time Buzzer` | Audible output observation | Available | **ACCEPTED** |
| [x] | O03 | `output_pin case_light` | Safe auxiliary output | Available | **ACCEPTED** |
| [x] | O04 | `neopixel mmu_leds` | LED output observation | Available | **ACCEPTED (red → green → blue → white)** |
| [x] | S15 | `Petrel encoder` | Petrel encoder diagnostics | Operator observed; restore verified | **ACCEPTED** |
| [x] | S16 | `DWIN LCD` | Petrel LCD diagnostics | Operator observed; restore verified | **ACCEPTED** |
| [x] | S17 | `DWIN backlight` | Backlight observation | Operator observed; restore verified | **ACCEPTED** |
| [x] | M01 | `physical X endstop` | Physical endstop press/release | Operator observed; released state verified | **ACCEPTED** |
| [x] | M01 | `physical Y endstop` | Physical endstop press/release | Operator observed; released state verified | **ACCEPTED** |
| [x] | M03 | `Cartesian X/Y/Z homing` | Homing completion | Operator observed; restore verified | **ACCEPTED** |
| [x] | M04 | `stepper_x` | Stepper coarse movement | Operator observed; restore verified | **ACCEPTED** |
| [x] | M04 | `stepper_y` | Stepper coarse movement | Operator observed; restore verified | **ACCEPTED** |
| [x] | M04 | `stepper_z` | Stepper coarse movement | Operator observed; restore verified | **ACCEPTED** |
| [x] | M05 | `axis X` | Axis coarse travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M05 | `axis Y` | Axis coarse travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M05 | `axis Z` | Axis coarse travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M06 | `axis X` | Measured axis travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M06 | `axis Y` | Measured axis travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M06 | `axis Z` | Measured axis travel | Operator observed; restore verified | **ACCEPTED** |
| [x] | M12 | `endstop_phase X` | Endstop phase calibration | Ten homings, pending 49/64 | **ACCEPTED** |
| [x] | M12 | `endstop_phase Y` | Endstop phase calibration | Ten homings, pending 33/64 | **ACCEPTED** |
| [x] | H01 | `extruder` | Heater warmup | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H01 | `heater_bed` | Heater warmup | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H05 | `extruder` | Heating rate | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H05 | `heater_bed` | Heating rate | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H06 | `extruder` | Time to target | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H06 | `heater_bed` | Time to target | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H07 | `extruder` | Temperature overshoot | Single cycle; OFF verified | **ACCEPTED (procedure; FAILED_METRIC)** |
| [x] | H07 | `heater_bed` | Temperature overshoot | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H08 | `extruder` | Temperature stability | Single cycle; OFF verified | **ACCEPTED (procedure; FAILED_METRIC)** |
| [x] | H08 | `heater_bed` | Temperature stability | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H09 | `extruder` | Cooling rate | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H09 | `heater_bed` | Cooling rate | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H13 | `extruder` | Heater response warning | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H13 | `heater_bed` | Heater response warning | Single cycle; OFF verified | **ACCEPTED (procedure)** |
| [x] | H02 | `extruder` | Extruder PID calibration | Klipper PID, coefficients and OFF verified | **ACCEPTED** |
| [x] | H03 | `heater_bed` | Bed PID calibration | Klipper PID, coefficients and OFF verified | **ACCEPTED** |
| [x] | P01 | `probe` | Probe trigger response | Three fresh state readings; final stow finished | **ACCEPTED** |
| [x] | P03 | `probe` | Probe repeatability | 10 samples; range 0.0175 mm, σ=0.004644 mm | **ACCEPTED** |
| [x] | P04 | `probe` | Single probe measurement | Initial low-Z attempt BLOCKED; PASSED after manual Z lift | **ACCEPTED (measurement)** |

## Reference-confirmed hardware — adapter/acceptance pending

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | P05 | `probe Z-offset` | Probe Z-offset wizard | Existing Leveling; excluded here | **PENDING** |
| [ ] | P07 | `bed_mesh (probe)` | Automatic bed mesh | Existing Leveling; excluded here | **PENDING** |
| [ ] | P08 | `bed_mesh (manual)` | Manual bed mesh | Existing Leveling; excluded here | **PENDING** |
| [ ] | P11 | `screws_tilt_adjust` | Screws tilt adjustment | Existing Leveling; excluded here | **PENDING** |
| [ ] | R01 | `adxl345` | Accelerometer reading | Ready; physical acceptance pending | **PENDING** |
| [ ] | R02 | `resonance_tester X` | Axis resonance measurement | Ready; physical acceptance pending | **PENDING** |
| [ ] | R02 | `resonance_tester Y` | Axis resonance measurement | Ready; physical acceptance pending | **PENDING** |
| [ ] | R03 | `adxl345` | Accelerometer noise floor | Ready; physical acceptance pending | **PENDING** |
| [ ] | R04 | `input_shaper X/Y` | Input shaper calibration | Ready; physical acceptance pending | **PENDING** |
| [ ] | E01 | `extruder filament path` | Coarse filament extrusion | Ready; physical acceptance pending | **PENDING** |
| [ ] | E02 | `extruder measured length` | Measured extrusion distance | Ready; physical acceptance pending | **PENDING** |
| [ ] | E03 | `filament_switch_sensor mmu_gate_sensor` | Filament presence sensor | Ready; physical acceptance pending | **PENDING** |
| [ ] | E07 | `extruder + MMU filament path` | Filament path motion | Ready; physical acceptance pending | **PENDING** |
| [ ] | E11 | `Happy Hare MMU gate sensors (4 gates)` | MMU gate sensor diagnostics | Ready; physical acceptance pending | **PENDING** |

## Requires additional evidence or a safe integration

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | F13 | `guarded fan/heater comparison` | Fan thermal A/B comparison | Not built | **CONDITIONAL** |
| [ ] | H15 | `co-located calibrated sensor pair` | Paired temperature-sensor deviation | Not built | **CONDITIONAL** |
| [ ] | E12 | `Happy Hare gear and selector` | MMU mechanical diagnostics | Ready; physical acceptance pending | **CONDITIONAL** |
| [ ] | O02 | `approved servo and deploy/stow path` | Safe servo movement | Ready; physical acceptance pending | **CONDITIONAL** |
| [ ] | O06 | `user-defined physical servicing` | Guided servicing | Ready; physical acceptance pending | **CONDITIONAL** |

## Absent hardware

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | F04 | `fan_generic (not installed)` | Generic fan rotation | Available | **N/A** |

## Actual physical acceptance evidence

| ID / target | Human observation and outcome | Controller result | `restore_verified` |
|---|---|---|---|
| F01 / `fan` | Fan visibly rotated and recovered its original reported state | `PASSED_USER` | `true` |
| F02 / `fan` | Revised 2,000 ms stages accepted by operator; prior 800 ms acceptance and inconclusive run retained in JSON history. | `OBSERVED_USER` (latest LCD result not reported) | `false` (not separately verified) |
| F12 / `fan` | Real-printer five-stage adaptive PWM iterations functioned; after kick-start interference was addressed LCD reported PASS. Exact threshold unreported. | `PASSED_USER` (operator reported LCD PASS) | `true` (controller success path; not independently measured) |
| S18 / `pwm_cycle_time Buzzer` | Buzzer sound heard; no live readback from Klipper pwm_cycle_time | `OBSERVED_USER` | `false` |
| O03 / `output_pin case_light` | Case light changed and returned to original reported output | `PASSED_USER` | `true` |
| O04 / `neopixel mmu_leds` | Synchronized red → green → blue → white accepted by operator; prior skipped-blue and blocked runs retained in JSON history. | `OBSERVED_USER` (latest LCD result not reported) | `false` (not separately verified) |
| P01 / `probe` | Operator explicitly confirmed three state transitions and completed probe deactivation. | `PASSED` | `true` |
| P03 / `probe` | Operator explicitly accepted the ten-sample measurement; range 0.0175 mm, σ 0.004644 mm. | `PASSED` | `false` (no restoration claim) |
| P04 / `probe` | First attempt at Z=2.964 mm was BLOCKED; after moving Z to 52.964 mm the probe measured −0.025 mm. New automatic Z-lift preparation has not yet been physically retested. | `PASSED` | `false` (Z position is not restored) |

## Next implementation

**F12 implementation and operator acceptance are complete for the reference fan target.** Other pending tests require their own discovery, physical safety and restoration contracts. Do not infer measured RPM or electrical PWM from the accepted commanded threshold search. Merely conditional devices are **not automatically safe or runnable**.

**H implementation status:** All 16 reference physical H targets have adapters; none has physical acceptance yet. See the [thermal guide](maintenance-thermal.md) for final batch order and H01–H18 scope.

**M implementation status:** All 14 confirmed M physical targets have adapters and operator acceptance. The four M07 drivers are INFORMATION-only Diagnostics, excluded from physical acceptance. H acceptance states are unchanged by this development. [Motion guide](maintenance-motion.md).

**P/R/E/S/O implementation record (17 October 2026):** Group adapters and regressions were added; no new physical acceptance was granted. Probe Calibration, Bed Mesh and Screws Tilt remain in existing Leveling. Conditional profile/source requirements remain. Guides: [P](maintenance-probe.md), [R](maintenance-resonance.md), [E](maintenance-filament.md), [S](maintenance-system.md), [O](maintenance-auxiliary.md). Overall integration is outside this work.

**M03 physical acceptance (17 October):** session `a4ad65170ed04b649b0a1a58c9c55b53`, `observe(true)` #220, `PASSED_USER` #222 and `restore_verified=true`. Final readback: `homed_axes=xyz`, X=157.9, Y=141.5, Z=10 mm. All 274 events were retained without write errors; no safety shutdown or UI handler error was recorded.

**M03 UI flow defect:** confirmations #97/#114 returned to preflight after the 3-second safety evidence expired and reset selection to Cancel; only confirmation #129 dispatched. Physical homing acceptance does not accept that UI flow. Following the operator report, consent for the unchanged movement is retained through fresh safety checks and explicit flow diagnostics were added; the follow-up trace verified refresh and dispatch with one confirmation (below).

**Follow-up trace (17 October, `b04c94981b594e06b991b254996a34a0`):** 330 consecutive events, no drops/write errors; both rotated files reviewed together. M03 single confirmation #96 → safety refresh #102 → request #105 → explicit observation #191 → PASSED_USER #193, restoration verified. Back input returned the result to Self Tests at #197. M04 X also refreshed after one confirmation; request #231, generic Future error #233, Petrel-requested shutdown #235 and INCONCLUSIVE #241. The discarded original error prevents distinguishing pre-dispatch guard rejection from a wire/server failure; root cause remains unknown. M04 was not accepted. Diagnostics now retain dispatch stage, final guard reason, safe server error category/code, motor enables and bounded mesh/velocity evidence. No M04 runtime correction is claimed before further evidence.

**Automatic homing trace (17 October):** `8bf95a8e7cc6431c99ede09170b26605`, HEAD `4e2f713`, 448 events without drops/write errors. M04/X completed required homing after one confirmation #120 and continued to the original test. #295 definitively identified pre-send guard rejection and clear_mesh_before_motion_test; the test command was not written to the socket. Petrel unnecessarily requested shutdown #297, producing INCONCLUSIVE #303. Cleared [[]] mesh interpretation and shutdown for definitive pre-send rejection were corrected. M04 remains unaccepted; previous M03 acceptance is unchanged.

**Motion batch acceptance (17 October):** `3e8f0231f5a84e8eaeae6944aba6951d`, HEAD `537e037`: 2545 consecutive events without drops/write errors. M04/M05/M06 X/Y/Z (9 targets) have explicit observation, PASSED_USER and restoration readback. M06 records operator-entered 10 mm per axis and separate return consent, not independent metrology. M12/X is accepted as OBSERVED_USER; pending config intentionally remains unsaved and the numeric phase was omitted by the old sanitizer. M10 X/Y/Z are accepted as operator-observed passive checks with 0 reported faults, never motor-health PASS. The operator clarified that the first M04/X Not observed selection was accidental; it is excluded from physical failures. The two later explicit acceptances remain valid. One M05/Z was operator-cancelled before movement, followed by acceptance. M01/X reconfirmed its existing acceptance. M12/Y and M10/extruder remain unaccepted. No command error/shutdown occurred; every departure from the test page went to the result page.

Numeric trigger_phase logging is corrected: only fractions satisfying `0 <= phase < count <= 4096` are retained; file paths remain omitted. Previously omitted phase values are not reconstructed or invented.

**Operator acceptance correction (17 October):** The operator clarified that M10/M12 Observed was clicked without understanding the checks and withheld acceptance pending explanation. M10 X/Y/Z and M12/X are reverted to pending; earlier clicks remain invalidated acceptance history. M04/M05/M06 acceptances are unchanged. Current totals: 21 accepted, 43 pending, 5 conditional, 1 N/A.

M10 only reads TMC2208 drv_status fault/thermal warning flags; no motion, load test or setting write occurs. Faults: none reported means only no flags reported at that instant. M12 uses existing homing phase statistics via ENDSTOP_PHASE_CALIBRATE to create pending trigger_phase; exact pending result and preserved position/modes are checked. SAVE_CONFIG is never sent; Observed does not persist settings. This is not an independent homing repeatability measurement. M12/Y was blocked to preserve the earlier pending setting.

**Later M12 acceptance (17 October):** The operator explicitly accepted both ten-homing per-axis workflows. X session `2a74f7fe73914463b7798c7551b51c92`, run 1, phase `49/64`, `OBSERVED_USER` #1088; Y session `2fd812d7ffdb4c6e8b59275ef181b1b2`, run 2, phase `33/64`, `OBSERVED_USER` #771. The older invalidated X observation is preserved in JSON history. SAVE_CONFIG was not performed; accuracy has not been independently measured. The repeat-entry precheck issue was explicitly waived for acceptance. M10 remains pending. Updated totals: 23 accepted, 41 pending, 5 conditional, 1 N/A.

**M12/Y Diagnostics follow-up (17 October 2026, LCD 19:18):** User explicitly confirmed the read-only M12/Y information read succeeded after homing Y. The earlier `INCONCLUSIVE / no_valid_evidence` resulted from Y having no homing history in that session. Screenshot: `OBSERVED`, `observed information`, `stepper_y.phase: 58/64`. This is the current `last_home` diagnostic value, **not** a new ten-homing M12 calibration or a replacement for the previously accepted pending trigger phase `33/64`. Existing M12/Y physical acceptance remains intact; active ledger totals do not change. The screenshot-based result is recorded separately in the M12/Y JSON `diagnostic_observations` history.

**M10 reserved ID (17 October 2026):** M10 was misclassified as a Self Test and is now hidden and unused, without renumbering any other ID. Driver fault reporting is available as read-only M07 Diagnostics with no motor-health PASS. Prior invalidated M10 X/Y/Z observations and the pending extruder row are preserved in the JSON historical archive; no M10 rows remain in the active acceptance tracker. Current totals: 66 rows, 23 accepted, 37 pending, 5 conditional, 1 N/A.

**M07 removed from physical acceptance tracking (17 October 2026):** The four M07 X/Y/Z/Extruder entries are information-only Diagnostics, not physical Self Tests, and have been removed from the active hardware acceptance table. JSON `evidence.m07_informational_diagnostics` preserves the direct `DRV_STATUS` read evidence, user validation and the four historical pending entries. No new hardware PASS was awarded; all 23 existing acceptances and M12 evidence remain unchanged. Current total: **62 rows / 46 IDs — 23 ACCEPTED, 33 PENDING, 5 CONDITIONAL, 1 N/A.**

**Thermal characterization procedure acceptance (17 October 2026):** Session
`58240fb38284486dbb6cbdd3d45f6358`, signed HEAD `115e392`.
1,830 consecutive events, zero dropped/write errors/shutdowns.
Extruder single cycle run 1, observation #792, result #794; bed
single cycle run 2, observation #1660, result #1662. Both finished
with heater OFF/zero duty/cooling proof (`restore_verified=true`).
The operator explicitly approved **14 measurement procedures**
(H01/H05/H06/H07/H08/H09/H13 for each heater) from these two
physical runs. Extruder **H07 = 7.72 C overshoot** and
**H08 = 6.69 C stability fluctuation** remain `FAILED_METRIC`:
performance criteria were not met, while the procedures were
correctly exercised and accepted. Bed metrics were 7/7, extruder
metrics 5/7. H02/H03 PID remained pending at this stage; a subsequent standalone H02 run was accepted.
**Totals after this earlier thermal characterization: 62 rows / 46 IDs — 37 ACCEPTED, 19 PENDING,
5 CONDITIONAL, 1 N/A.**

**H02 extruder PID acceptance (17 October 2026):** Session
`31cd66be65bd4a3b88968c920adfe340`, tested signed HEAD
`1b6511d`; 1,720 consecutive events, zero dropped or write
errors, one file rotation. H02 run 1 at target 150 C;
Klipper `PID_CALIBRATE` completed (#1352). Petrel read
pending Kp=**14.738**, Ki=**0.558**, Kd=**97.273**.
OFF and cooling verified (`restore_verified=true`).
Operator `observe(true)` (#1595) and result #1597 was
`PASSED_USER`. **H02 physical procedure accepted.**
`SAVE_CONFIG` was not invoked; the coefficients have not been
verified persisted. H03 bed PID run 2 was `BLOCKED` before
dispatch (#1672) by H02's `existing_or_unknown_pending_config`;
H03 is not accepted.
**Totals after H02 acceptance: 62 rows / 46 IDs — 38 ACCEPTED,
18 PENDING, 5 CONDITIONAL, 1 N/A.**

**H03 bed PID physical acceptance (17 October 2026):**
Session `8fa2b04372d94b7ca60e6d443fc098a8`, tested signed HEAD
`1b6511d`; 2,671 events (#1721–4391), zero dropped/write
errors, one file rotation. H03 run 3 targeted **60 C**;
Klipper `PID_CALIBRATE` was sent at #1792 and completed
at #4118. The pending PID coefficients were read as
**Kp=72.339**, **Ki=1.502**, **Kd=870.785**. Heater OFF,
cooling and `restore_verified=true` were verified. Operator
`observe(true)` (#4288) confirmed the run, resulting in
`PASSED_USER` (#4290). **H03 physical procedure accepted.**
Petrel did not issue `SAVE_CONFIG`; coefficient persistence
is not claimed. The earlier H03 `BLOCKED` attempt is retained
in history and does not override the later successful run.
**All 16/16 H-group physical procedures on this reference printer
have operator acceptance. Current totals: 62 rows / 46 IDs —
42 ACCEPTED, 14 PENDING, 5 CONDITIONAL, 1 N/A.**

## P-group operator acceptance and P04 preparation (17 October 2026)

The operator explicitly reported real-printer PASS for P01, P03 and P04. Trace `2d899dbe5dcc42e6a5e6a020df941369` contains 693 events with no drops or write errors. P04's prior implementation BLOCKED the first preflight at Z=2.964 mm with `raise_z_before_probe_test`; after the operator manually raised Z to 52.964 mm the single probe reading completed successfully. Physical acceptance applies to the single-measurement procedure, **not yet** to the new automatic Z-lift preparation, which needs its own physical re-test.
