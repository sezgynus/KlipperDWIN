# Maintenance Stage 8C — guarded physical pulse runner

[Türkçe](maintenance-physical_TR.md)

`MaintenancePulseController` is an on-demand backend state machine. The only supported physical actions are compiled `PulseProgram` scripts from Stage 8B, with a self-contained restore after a maximum 950-ms stimulus. It reuses the existing Petrel read worker, Moonraker HTTP client, `postREST` command queue, immutable discovery, fail-closed job queue/operation evidence and explicit `GuidedConsentGate`.

Two distinct UI actions are mandatory: first, select a discovered test (queues a read-only job-queue + target baseline GET); second, explicitly confirm whenever the operator is ready. **User choices never expire.** If the operator delays the start confirmation beyond the short lifetime of its queue/baseline proof, pressing confirm initiates a fresh **read-only** preflight, and the operator confirms again before any actuation. Nothing is sent on menu entry or discovery. A dispatch-time guard rejects changed Klipper epoch/config, print/paused/manual-probe/MMU operations, stale queue evidence and unknown status. `postREST` queues the short G-code script; after the command completes, a new bounded GET must confirm the original value was restored. Only then does the runner ask for the user's observation, and **only an explicit YES** returns `PASSED_USER`, never automatic PASS or RPM data.

IMPORTANT: a Moonraker timeout/connection interruption can leave a command's execution ambiguous even if the script includes a restore. The controller marks this `INCONCLUSIVE`; it never replays a timed-out command. An ambiguous command may continue executing after a cancel/timeout. The user must inspect the hardware; the local reservation is not a global lock against other Moonraker clients. This implementation cannot establish hard real-time fail-safe guarantees. In particular, an unverified original output, unknown queue, active template, or mismatching post-command readback **blocks** success.

The LCD interface and accepted real-Pi hardware stimuli require separate validation; CI fakes cannot prove any physical actuator works.

## F12 — guarded five-stage adaptive fan startup threshold

F12 finds the **minimum observed cold-start M106 command** (not measured RPM
or true electrical PWM). It begins with five ascending commanded duty steps
over 0–50%, each 2 seconds. Each stage is dispatched as an independently
bounded, OFF-restoring script. The LCD displays the actual dispatched stage.
Two separate Klipper status readbacks must report fan speed OFF between
stages; however, commanded OFF does not prove that the rotor has stopped
mechanically. The operator selects the first stage to start from rest, or
None; the next range is the preceding failed / first successful step.
Before another iteration, the operator confirms physical standstill.

**Required calibration configuration:** Klipper's `[fan]` object normally
defaults to `kick_start_time: 0.100`. Klipper sends *full power* briefly
when starting the fan from OFF, regardless of the low M106 duty request.
This invalidates a cold-start threshold measurement. F12 therefore
**fails closed before any G-code** unless the *effective* Klipper
`kick_start_time` value is explicitly verified to be **zero**. A missing
setting is interpreted as Klipper's nonzero default and blocks the test.
The LCD shows `Set kick_start_time: 0` and `RESTART Klipper`.

To perform a meaningful measurement, **only when safe to change fan
configuration and while the printer is idle**, temporarily put
`kick_start_time: 0` under the existing `[fan]` section of the Klipper
printer configuration and run `RESTART`. Repeat the F12 test, then
restore the original kick-start value and `RESTART` once calibration is
complete. **Petrel neither edits that configuration nor restarts Klipper.**
If you need a minimum *normal-operation* speed with kick-start enabled,
that is a different measurement, not the F12 cold-start threshold.
`off_below` and `max_power` still affect the observed M106 threshold;
no automatic PID, RPM, or independent electrical-power verification exists.

## User-paced interactive prompts

All guided Maintenance hardware tests share the same policy: **no timeout on
operator decisions**. Initial dispatch confirmation, post-stimulus observation
(including the configuration-only S18 sound test), and the F12 rotor-stopped
confirmation stay open until the operator answers or explicitly cancels. An
idle encoder never creates `ABORTED`, `INCONCLUSIVE`, `FAILED_USER`, or
`BLOCKED` solely because time passed. The existing three-second evidence
freshness is a **dispatch safety rule**, not a UI countdown: after waiting,
confirming re-reads live safety and asks for fresh consent. Bounded read,
hardware-command and restore-verification timeouts remain and can still
produce safety-related outcomes independently of any operator response.

## Delayed Moonraker restore telemetry (Stage 8 F01 acceptance)

Real Raspberry Pi acceptance exposed an F01 short fan pulse followed by `INCONCLUSIVE / restore_not_verified`; a later read-only Moonraker query reported `fan.speed=0.0`. The original single GET could race the G-code/telemetry update, but that observation alone cannot establish precisely where the delay occurred. The controller now waits at least the configured pulse duration plus a margin from G-code dispatch, and at least 250 ms after HTTP completion. It then schedules **two consecutive matching status GETs** at least 300 ms apart, with a **six-second bounded verification window**. All reads use the existing bounded worker on the UI tick, without sleep, new worker threads or repeated G-code dispatch.

Intermediate mismatch or transient read errors can recover; permanent mismatch becomes `restore_value_mismatch`, failed responses `restore_readback_unavailable`, incomplete agreement `restore_not_stable`, and a changed printer epoch/config `state_changed_during_restore_check`. On timeout or ambiguity the result remains **INCONCLUSIVE**, never an automatic PASS. Two matching samples are only reported state confirmation, not a hard guarantee about future queued G-code execution; physical observation and the explicit user YES remain mandatory. Do not retry an inconclusive physical pulse without inspecting the output.

## Config-only S18 physical observation

For S18, the explicit `maintenance.audible:pwm_cycle_time <name>` authorization is taken from the profile-backed capability snapshot, never the unrelated DWIN LCD buzzer setting. Because Klipper's `pwm_cycle_time` is not queryable, the controller does not invent a baseline or send a fictitious GET. The same idle/queue checks, second confirmation and guarded single POST remain mandatory. After the command reply and bounded pulse duration, the user is asked whether the short sound **occurred AND stopped**. A positive answer is recorded as `OBSERVED_USER` with `restore_verified=False`, not `PASSED_USER` or telemetry-backed restoration. Failure, cancellation and uncertain transport remain fail-closed; a visible user result cannot prove the real output was restored without instrumentation. Never force a physical test without listening for sound and confirming it ceased.

## Case-sensitive Klipper pin names (S18)

Klipper's `configfile.settings` normalizes section keys to lowercase, but its `configfile.config` preserves the original section spelling used by the `SET_PIN PIN=...` G-code mux. A real Pi exposed `pwm_cycle_time buzzer` in effective settings while Klipper accepted only `PIN=Buzzer`; sending lowercase caused `INCONCLUSIVE / script_failed_or_restore_unknown`. The S18 and O03 preflight now make a **read-only** `configfile.config` request, finds one unambiguous matching output section for the explicitly approved role, comparing names case-insensitively, validates its physical `pin` against effective settings, and compiles all OFF/pulse/OFF commands with the **original spelling**. Missing, conflicting, or malformed evidence is blocked before any G-code. No hardcoded pin name, no runtime-unknown restoration PASS, and no change to F01; O03 now also accepts generic role-approved output pins.

## O04: independent and extension-owned LED chains

Independent RGB/RGBW chains use indexed \`SET_LED\` pulse + per-pixel original color restoration, requiring two complete restored readbacks **and explicit visual user confirmation** before \`PASSED_USER\`. Command success or status color alone never proves real light output.

Standard Happy Hare \`[mmu_leds ...]\` controllers are recognized from effective Klipper mapping, not printer-specific profiles. All four \`exit\`, \`entry\`, \`status\` and \`logo\` segments are supported with arbitrary bounded nonoverlapping physical LED indices and multiple units. Only mapped segment pixels can be included; ambiguous targets are denied. HH-managed O04 uses an expiring, unit-scoped \`MMU_SET_LED ... DURATION=0.40\` command, **not** raw \`SET_LED\` and **not** \`MMU_LED ENABLE=0\`. Each unit must remain enabled and readable; the MMU must be idle; all usual double-consent and queue guards apply. Post-test control-policy checks cannot prove pixel color restoration, so the operator's positive observation yields \`OBSERVED_USER\` with \`restore_verified=False\`. No automatic hardware PASS. Physical acceptance remains pending until observed on a real machine.

**O04 Happy Hare numeric UNIT proof:** `[mmu_leds NAME]` section suffix and the potentially human-readable `mmu_machine.unit_N.name` are not automatically the same identity. Resolve numeric `UNIT` using an authoritative ordered config list, or a validated, uniquely owned single-unit case (live `num_units=1`, one `unit_0` record, exactly one MMU LED controller). The latter safely yields `UNIT=0` without a name match. For multi-unit printers, require verified canonical mapping; do not guess. On discovery and again immediately before dispatch, reject missing/ambiguous/contradictory evidence without touching LEDs.

### O04 full-brightness RGB observation

User-approved O04 now tests every mapped RGB LED through **red, blue, green and white**, each for 650 ms, then restores the previous state/policy. Independent chain scripts commit each indexed color frame once and restore all original pixel values. Happy Hare scripts use four separate 400 ms self-expiring effects, 650 ms apart, to avoid HH's deferred-timed-effect behavior; they do not disable HH control. Both paths require explicit operator confirmation that **all four colors** appeared on **all mapped LEDs**. Monochrome-only LED objects are not eligible for the RGB test. Full-scale white can increase peak power demand; operators must ensure the chain's power supply is adequate.

**Color-order preflight:** For Klipper RGB/RGBW outputs, effective config's color_order may be a list/tuple (the common config.getlist representation), not necessarily a string. Both encodings receive identical strict validation for each pixel. Invalid/mixed-color layouts BLOCK before G-code. The Petrel journal records a bounded diagnostic reason ("Maintenance physical preflight blocked") rather than hiding a recoverable capability-format error; the LCD still displays BLOCKED and no G-code is sent.
