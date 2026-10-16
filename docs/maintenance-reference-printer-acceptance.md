# Maintenance — reference printer physical acceptance tracker

[Türkçe](maintenance-reference-printer-acceptance_TR.md) · [JSON source of truth](maintenance-reference-printer-acceptance.json) · [Test catalog](maintenance-test-catalog.md)

> **PERSISTENT DEVELOPMENT / ACCEPTANCE RECORD.** Read this file and its JSON ledger at the start of the next Maintenance development session. It describes one sanitized reference printer, never a production Petrel hardware allowlist.

**Evidence boundary:** the independent 121-ID hardware reference from 15 Oct 2026, the 16 Oct 2026 discovery log and explicit user observations. The log confirms **54 discovered features**, but no serialized list of their exact IDs was preserved. Here, `confirmed` means confirmed by the independent capability reference, **not** an exact complete dump of the 54 currently observed IDs. `conditional` entries are not currently authorized, discoverable test commands.

**Strict separation:** installed hardware ≠ implemented adapter ≠ CI PASS ≠ real-printer user acceptance. **Six** hardware checks have operator approval. Revised F02 (2,000 ms/stage), four-color O04 and adaptive five-stage F12 were accepted on 16 Oct 2026. Older outcomes remain in JSON history; latest LCD outcome and electronic restoration readback were not separately reported. One accepted device/axis never propagates PASS to another target with the same feature ID.

**Per-device tracking:** **70 rows / 48 IDs** — 6 ACCEPTED, 55 PENDING, 8 CONDITIONAL, 1 N/A. **F12 adaptive search and its reported LCD PASS were accepted on the real reference printer; an exact PWM threshold was not provided. F02/O04 latest restoration was not separately verified.**

**Mandatory after each user-approved test:** set only that target's JSON `status` to `accepted`; record date, operator observation, controller outcome and `restore_verified` in `acceptance`; check only the corresponding target in both EN/TR tables in the same signed commit. Add relevant regressions; verify the full CI suite on the **bot-signed HEAD**. Never mark an item done because of a config line, HTTP success, G-code OK, simulated CI or an informational read. Never merge `master` without explicit request.

**Excluded:** informational-only S01/S02/S03/S05/S08/S10 and H11/H14/M09/P09 etc are not physical PASS. No RPM measurement without the part-fan tachometer. The Z endstop is virtual, not a pressable Z switch. Servo probe is not BLTouch. R02 maps X/Y only. The temporary PFAB percentage-display sensor is excluded from this *reference fixture*, never from generic discovery.

## User-approved physical checks

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [x] | F01 | `fan` | Part fan rotation | Available | **ACCEPTED** |
| [x] | F02 | `fan` | Part fan speed steps | Available | **ACCEPTED (2,000 ms/stage)** |
| [x] | F12 | `fan` | Adaptive five-step startup PWM threshold | Available | **ACCEPTED (iterative search / LCD PASS)** |
| [x] | S18 | `pwm_cycle_time Buzzer` | Audible output observation | Available | **ACCEPTED** |
| [x] | O03 | `output_pin case_light` | Safe auxiliary output | Available | **ACCEPTED** |
| [x] | O04 | `neopixel mmu_leds` | LED output observation | Available | **ACCEPTED (red → green → blue → white)** |

## Reference-confirmed hardware — adapter/acceptance pending

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | H01 | `extruder` | Heater warmup | Not built | **PENDING** |
| [ ] | H01 | `heater_bed` | Heater warmup | Not built | **PENDING** |
| [ ] | H02 | `extruder` | Extruder PID calibration | Not built | **PENDING** |
| [ ] | H03 | `heater_bed` | Bed PID calibration | Not built | **PENDING** |
| [ ] | H05 | `extruder` | Heating rate | Not built | **PENDING** |
| [ ] | H05 | `heater_bed` | Heating rate | Not built | **PENDING** |
| [ ] | H06 | `extruder` | Time to target | Not built | **PENDING** |
| [ ] | H06 | `heater_bed` | Time to target | Not built | **PENDING** |
| [ ] | H07 | `extruder` | Temperature overshoot | Not built | **PENDING** |
| [ ] | H07 | `heater_bed` | Temperature overshoot | Not built | **PENDING** |
| [ ] | H08 | `extruder` | Temperature stability | Not built | **PENDING** |
| [ ] | H08 | `heater_bed` | Temperature stability | Not built | **PENDING** |
| [ ] | H09 | `extruder` | Cooling rate | Not built | **PENDING** |
| [ ] | H09 | `heater_bed` | Cooling rate | Not built | **PENDING** |
| [ ] | H13 | `extruder` | Heater response warning | Not built | **PENDING** |
| [ ] | H13 | `heater_bed` | Heater response warning | Not built | **PENDING** |
| [ ] | M01 | `physical X endstop` | Physical endstop press/release | Not built | **PENDING** |
| [ ] | M01 | `physical Y endstop` | Physical endstop press/release | Not built | **PENDING** |
| [ ] | M03 | `Cartesian X/Y/Z homing` | Homing completion | Not built | **PENDING** |
| [ ] | M04 | `stepper_x` | Stepper coarse movement | Not built | **PENDING** |
| [ ] | M04 | `stepper_y` | Stepper coarse movement | Not built | **PENDING** |
| [ ] | M04 | `stepper_z` | Stepper coarse movement | Not built | **PENDING** |
| [ ] | M05 | `axis X` | Axis coarse travel | Not built | **PENDING** |
| [ ] | M05 | `axis Y` | Axis coarse travel | Not built | **PENDING** |
| [ ] | M05 | `axis Z` | Axis coarse travel | Not built | **PENDING** |
| [ ] | M06 | `axis X` | Measured axis travel | Not built | **PENDING** |
| [ ] | M06 | `axis Y` | Measured axis travel | Not built | **PENDING** |
| [ ] | M06 | `axis Z` | Measured axis travel | Not built | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_x` | TMC driver status | Not built | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_y` | TMC driver status | Not built | **PENDING** |
| [ ] | M07 | `tmc2208 stepper_z` | TMC driver status | Not built | **PENDING** |
| [ ] | M07 | `tmc2208 extruder` | TMC driver status | Not built | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_x` | TMC driver fault diagnostics | Not built | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_y` | TMC driver fault diagnostics | Not built | **PENDING** |
| [ ] | M10 | `tmc2208 stepper_z` | TMC driver fault diagnostics | Not built | **PENDING** |
| [ ] | M10 | `tmc2208 extruder` | TMC driver fault diagnostics | Not built | **PENDING** |
| [ ] | M12 | `endstop_phase X` | Endstop phase calibration | Not built | **PENDING** |
| [ ] | M12 | `endstop_phase Y` | Endstop phase calibration | Not built | **PENDING** |
| [ ] | P01 | `probe` | Probe trigger response | Not built | **PENDING** |
| [ ] | P03 | `probe` | Probe repeatability | Not built | **PENDING** |
| [ ] | P04 | `probe` | Single probe measurement | Not built | **PENDING** |
| [ ] | P05 | `probe Z-offset` | Probe Z-offset wizard | Not built | **PENDING** |
| [ ] | P07 | `bed_mesh (probe)` | Automatic bed mesh | Not built | **PENDING** |
| [ ] | P08 | `bed_mesh (manual)` | Manual bed mesh | Not built | **PENDING** |
| [ ] | P11 | `screws_tilt_adjust` | Screws tilt adjustment | Not built | **PENDING** |
| [ ] | R01 | `adxl345` | Accelerometer reading | Not built | **PENDING** |
| [ ] | R02 | `resonance_tester X` | Axis resonance measurement | Not built | **PENDING** |
| [ ] | R02 | `resonance_tester Y` | Axis resonance measurement | Not built | **PENDING** |
| [ ] | R03 | `adxl345` | Accelerometer noise floor | Not built | **PENDING** |
| [ ] | R04 | `input_shaper X/Y` | Input shaper calibration | Not built | **PENDING** |
| [ ] | E01 | `extruder filament path` | Coarse filament extrusion | Not built | **PENDING** |
| [ ] | E02 | `extruder measured length` | Measured extrusion distance | Not built | **PENDING** |
| [ ] | E03 | `filament_switch_sensor mmu_gate_sensor` | Filament presence sensor | Not built | **PENDING** |
| [ ] | E07 | `extruder + MMU filament path` | Filament path motion | Not built | **PENDING** |
| [ ] | E11 | `Happy Hare MMU gate sensors (4 gates)` | MMU gate sensor diagnostics | Not built | **PENDING** |

## Requires additional evidence or a safe integration

| Done | ID | Target | Feature | Adapter | Status |
|---|---|---|---|---|---|
| [ ] | F13 | `guarded fan/heater comparison` | Fan thermal A/B comparison | Not built | **CONDITIONAL** |
| [ ] | H15 | `co-located calibrated sensor pair` | Paired temperature-sensor deviation | Not built | **CONDITIONAL** |
| [ ] | E12 | `Happy Hare gear and selector` | MMU mechanical diagnostics | Not built | **CONDITIONAL** |
| [ ] | S15 | `Petrel encoder` | Petrel encoder diagnostics | Not built | **CONDITIONAL** |
| [ ] | S16 | `DWIN LCD` | Petrel LCD diagnostics | Not built | **CONDITIONAL** |
| [ ] | S17 | `DWIN backlight` | Backlight observation | Not built | **CONDITIONAL** |
| [ ] | O02 | `approved servo and deploy/stow path` | Safe servo movement | Not built | **CONDITIONAL** |
| [ ] | O06 | `user-defined physical servicing` | Guided servicing | Not built | **CONDITIONAL** |

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
