# Maintenance Stage 8 — Real Raspberry Pi physical acceptance

[Türkçe](maintenance-stage8-acceptance_TR.md) · [Optional output profiles](maintenance-profiles.md) · [LCD user flow](maintenance-ui.md) · **[Live operator-accepted reference-printer checklist](maintenance-reference-printer-acceptance.md)**

> **Current acceptance status:** The initial-stage examples below are historical evidence. For the latest operator-confirmed device-level physical PASS/OBSERVED records, use the linked tracker and its JSON ledger.

## Scope and prerequisites

Stage 8 implementation has GitHub regression coverage, but mock CI does **not** prove real actuation, restored outputs, audible tones or LED light. These must be explicitly accepted on a real printer. The previous **Stage 7** read-only test was completed on a Raspberry Pi with six information sources observed; that does not cover Stage 8.

Verify printer standby, `virtual_sdcard.is_active=false`, `pause_resume.is_paused=false`, no queued jobs, no MMU/probe/calibration activity and no unresolved jog recovery. Keep an operator watching the printer throughout. Never perform an actuator test during a print or while relying on fan cooling for hot components. The case-light/buzzer/generic-fan/LED options are disabled until explicitly enabled with matching real hardware in `maintenance-test-profiles.json`. Part cooling fan F01 needs no extra profile.

## Deployment without merging into master

Use your existing `/tmp/petrel-maintenance-acceptance` detached worktree; fetch and update it to the latest **signed, CI-passing** `feature/maintenance-test-engine` HEAD. Never checkout the feature branch within the running `~/Petrel` master directory. For an interactive LCD test, the **actual Petrel.service** must be temporarily started with `WorkingDirectory` and `ExecStart` set to the detached feature worktree via a temporary systemd drop-in, as in the earlier successful Stage-7 A/B measurement. Keep a rollback trap and confirm the service is on that feature worktree before testing. Any service restart is forbidden while printing.

## On-device manual sequence

1. On LCD select **Maintenance → Self Tests**. Only exact discovered, explicitly safe choices may appear. Entry must not move the printer or change outputs.
2. Select **F01 fan** or one approved optional output. Wait for on-demand queue and original-state checks; if BLOCKED, do not circumvent the safety gate.
3. Rotate from the default **Cancel** to **Run short pulse**, press to confirm before the three-second expiration. The compiler produces one bounded script that attempts to restore the original output afterward.
4. Wait for the backend's post-command GET restoration verification. Never claim the hardware is restored merely because the G-code command was queued. If the result is INCONCLUSIVE, inspect the physical output and Klipper state before any new test.
5. The UI prompts for an explicit operator observation. Choose **Yes, observed** only if the brief physical response was seen/heard *and* the backend verified the original output. The status is `PASSED_USER` (human-observed), not automatic PASS or measured RPM. Otherwise choose **Not observed** (`FAILED_USER`).
6. Repeat independently for safe, actually installed devices. Confirm original fan speed, LED color and operator-declared visual-output value after each test. Validate cancellation, deny while queued/printing, missing profile, and disconnect with fakes/controlled conditions; never force a dangerous mid-actuation disconnect on valuable hardware.

Check **Diagnostics** independently. S01/S02/S03/S05/S08/S10 return only whitelisted scalar information. The resulting UI must not display Moonraker tokens or print filenames.

## Rollback and acceptance record

Remove the temporary systemd override, run `sudo systemctl daemon-reload` and `sudo systemctl restart Petrel.service`, and verify active service `ExecStart=/home/sezgynpi/petrel-env/bin/python /home/sezgynpi/Petrel/run.py`, `WorkingDirectory=/home/sezgynpi/Petrel`, with master clean. If power/connection problems or unresolved hardware state are observed, stop physical testing and inspect on the Pi. Record feature signed SHA, safe output profiles used, evidence for each device, restored value, result and operator response. Stage-8 real-hardware acceptance stays **PENDING** until this is actually performed.


## Role-based profiles (feature branch)

The current generic Maintenance branch accepts only version-2 `actuators` role mappings; old `case_light`/`buzzer_output` keys no longer grant permission. S18 is a device-scoped test, so select the **actual** `pwm_cycle_time <name>` row. O03 similarly operates on an explicitly approved `output_pin <name>`, not a fixed case-light name. See [profile migration](maintenance-profiles.md). Previous Pi observations below are historical diagnostic examples, **not embedded target names or pins**.

## F01 field finding and follow-up verification

During live Remote Display acceptance on 2026-10-16, the F01 part-cooling fan visibly pulsed through the camera, but the controller returned `INCONCLUSIVE / restore_not_verified`. A later independent `/printer/objects/query?fan&webhooks` check showed `fan.speed=0.0`, `fan.rpm=null`, and `webhooks.state=ready`. The initial physical attempt **is not a PASS**, as the immediate restore validation failed; the later read is not proof of the earlier restore timing. The verification-window/retry patch has CI fake coverage and needs a **new** real-Pi acceptance after updating the feature worktree. Confirm the printer is idle and the fan stopped before repeating any physical test.

## S18: field finding and separate pending readback acceptance

On the Pi, `configfile.settings['pwm_cycle_time buzzer']` had pin PB13, value=0, shutdown_value=0, scale=1, but `printer.objects.list` omitted the buzzer and `printer.objects.query` had no status. The updated S18 opt-in path uses configuration-only discovery and **human audible observation**; the result `OBSERVED_USER` does not indicate verified restoration. S18's telemetry-backed restoration acceptance is **not available** with this Klipper object. Enable `buzzer_output='buzzer'` only after checking the actual buzzer and observing it can be safely actuated when the printer is idle. Do not count a CI fake as a real test.

## S18 case-sensitive G-code field observation

On 2026-10-16 the new S18 entry appeared, but its first physical attempt failed with `INCONCLUSIVE / script_failed_or_restore_unknown`: Klipper listed valid mux option `Buzzer`, whereas Petrel generated `PIN=buzzer`. The pin was **not** confirmed actuated. The signed fix resolves the original case-sensitive section name during a read-only preflight. Stage 8 S18 stays **PENDING** until a new idle-printer physical test demonstrates a brief sound **and silence afterward**, recorded as `OBSERVED_USER` without claiming status-based restore verification.
