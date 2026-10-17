# Maintenance — reference printer physical acceptance tracker

[Türkçe](maintenance-reference-printer-acceptance_TR.md) · [JSON source of truth](maintenance-reference-printer-acceptance.json) · [Test catalog](maintenance-test-catalog.md)

> **PERSISTENT DEVELOPMENT / ACCEPTANCE RECORD.** Read this file and its JSON ledger at the start of the next Maintenance development session. It describes one sanitized reference printer, never a production Petrel hardware allowlist.

**Evidence boundary:** the independent 121-ID hardware reference from 15 Oct 2026, the 16 Oct 2026 discovery log and explicit user observations. The log confirms **54 discovered features**, but no serialized list of their exact IDs was preserved. Here, `confirmed` means confirmed by the independent capability reference, **not** an exact complete dump of the 54 currently observed IDs. `conditional` entries are not currently authorized, discoverable test commands.

**Strict separation:** installed hardware ≠ implemented adapter ≠ CI PASS ≠ real-printer user acceptance. **Eleven** hardware checks have operator approval. Revised F02 (2,000 ms/stage), four-color O04 and adaptive five-stage F12 were accepted on 16 Oct 2026. Older outcomes remain in JSON history; latest LCD outcome and electronic restoration readback were not separately reported. One accepted device/axis never propagates PASS to another target with the same feature ID.

**Per-device tracking:** **70 rows / 48 IDs** — 11 ACCEPTED, 53 PENDING, 5 CONDITIONAL, 1 N/A. **F12 adaptive search and its reported LCD PASS were accepted on the real reference printer; an exact PWM threshold was not provided. F02/O04 latest restoration was not separately verified.**

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

## Reference-confirmed hardware — adapter/acceptance pending

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | H01 | `extruder` | Heater warmup | Available; batch acceptance pending | **PENDING** |
| [ ] | H01 | `heater_bed` | Heater warmup | Available; batch acceptance pending | **PENDING** |
| [ ] | H02 | `extruder` | Extruder PID calibration | Available; batch acceptance pending | **PENDING** |
| [ ] | H03 | `heater_bed` | Bed PID calibration | Available; batch acceptance pending | **PENDING** |
| [ ] | H05 | `extruder` | Heating rate | Available; batch acceptance pending | **PENDING** |
| [ ] | H05 | `heater_bed` | Heating rate | Available; batch acceptance pending | **PENDING** |
| [ ] | H06 | `extruder` | Time to target | Available; batch acceptance pending | **PENDING** |
| [ ] | H06 | `heater_bed` | Time to target | Available; batch acceptance pending | **PENDING** |
| [ ] | H07 | `extruder` | Temperature overshoot | Available; batch acceptance pending | **PENDING** |
| [ ] | H07 | `heater_bed` | Temperature overshoot | Available; batch acceptance pending | **PENDING** |
| [ ] | H08 | `extruder` | Temperature stability | Available; batch acceptance pending | **PENDING** |
| [ ] | H08 | `heater_bed` | Temperature stability | Available; batch acceptance pending | **PENDING** |
| [ ] | H09 | `extruder` | Cooling rate | Available; batch acceptance pending | **PENDING** |
| [ ] | H09 | `heater_bed` | Cooling rate | Available; batch acceptance pending | **PENDING** |
| [ ] | H13 | `extruder` | Heater response warning | Available; batch acceptance pending | **PENDING** |
| [ ] | H13 | `heater_bed` | Heater response warning | Available; batch acceptance pending | **PENDING** |
| [ ] | M03 | `Cartesian X/Y/Z homing` | Homing completion | Available; physical acceptance pending | **PENDING** |
| [ ] | M04 | `stepper_x` | Stepper coarse movement | Available; physical acceptance pending | **PENDING** |
| [ ] | M04 | `stepper_y` | Stepper coarse movement | Available; physical acceptance pending | **PENDING** |
| [ ] | M04 | `stepper_z` | Stepper coarse movement | Available; physical acceptance pending | **PENDING** |
| [ ] | M05 | `axis X` | Axis coarse travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M05 | `axis Y` | Axis coarse travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M05 | `axis Z` | Axis coarse travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M06 | `axis X` | Measured axis travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M06 | `axis Y` | Measured axis travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M06 | `axis Z` | Measured axis travel | Available; physical acceptance pending | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_x` | TMC driver status | Available; physical acceptance pending | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_y` | TMC driver status | Available; physical acceptance pending | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_z` | TMC driver status | Available; physical acceptance pending | **PENDING** |
| [ ] | M07 | `tmc2208 extruder` | TMC driver status | Available; physical acceptance pending | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_x` | TMC driver fault diagnostics | Available; physical acceptance pending | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_y` | TMC driver fault diagnostics | Available; physical acceptance pending | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_z` | TMC driver fault diagnostics | Available; physical acceptance pending | **PENDING** |
| [ ] | M10 | `tmc2208 extruder` | TMC driver fault diagnostics | Available; physical acceptance pending | **PENDING** |
| [ ] | M12 | `endstop_phase X` | Endstop phase calibration | Available; physical acceptance pending | **PENDING** |
| [ ] | M12 | `endstop_phase Y` | Endstop phase calibration | Available; physical acceptance pending | **PENDING** |
| [ ] | P01 | `probe` | Probe trigger response | Ready; physical acceptance pending | **PENDING** |
| [ ] | P03 | `probe` | Probe repeatability | Ready; physical acceptance pending | **PENDING** |
| [ ] | P04 | `probe` | Single probe measurement | Ready; physical acceptance pending | **PENDING** |
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

## Next implementation

**F12 implementation and operator acceptance are complete for the reference fan target.** Other pending tests require their own discovery, physical safety and restoration contracts. Do not infer measured RPM or electrical PWM from the accepted commanded threshold search. Merely conditional devices are **not automatically safe or runnable**.

**H implementation status:** All 16 reference physical H targets have adapters; none has physical acceptance yet. See the [thermal guide](maintenance-thermal.md) for final batch order and H01–H18 scope.

**M implementation status:** Adapters exist for 22 confirmed M targets; no physical acceptance yet. M07 is INFORMATION only, not a motor-health PASS. H acceptance states are unchanged by this development. [Motion guide](maintenance-motion.md).

**P/R/E/S/O implementation record (17 October 2026):** Group adapters and regressions were added; no new physical acceptance was granted. Probe Calibration, Bed Mesh and Screws Tilt remain in existing Leveling. Conditional profile/source requirements remain. Guides: [P](maintenance-probe.md), [R](maintenance-resonance.md), [E](maintenance-filament.md), [S](maintenance-system.md), [O](maintenance-auxiliary.md). Overall integration is outside this work.
