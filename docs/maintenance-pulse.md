# Maintenance Stage 8B — bounded actuator program compilation

[Türkçe](maintenance-pulse_TR.md)

This is a **pure compiler**: no method here sends commands, starts tests, claims hardware PASS, or bypasses safety. Only exact USER-guided discovery rows can produce an immutable `PulseProgram`. The generated G-code has one allowlisted stimulus, a 150–950 ms `G4` delay and an explicit original-state restoration in **one bounded script**. Start is forbidden if original firmware status is missing or untrusted. External clients and Klipper restarts can still interrupt scripts: a subsequent executor MUST independently verify the restored output before reporting that restoration was observed.

Hardware profiles: F01 part fan uses M106 and restores prior commanded PWM, not RPM; F04 fan_generic uses exact SET_FAN_SPEED and refuses templates or unsafe names; O03 is only explicitly registered case_light PWM with scale 1 and known initial brightness; O04 is a single LED element with fully known color_data and exact SET_LED restore, not multi-pixel strips; S18 is an explicitly registered buzzer output that reports an OFF state and shutdown_value 0. Unsupported hardware remains blocked. Klipper's G-code command grammar is documented in its official [G-Codes reference](https://www.klipper3d.org/G-Codes.html).

The future executor must keep the printer idle, verify Moonraker job queue and other Petrel operations, guard the dispatch, avoid automatic execution on UI/menu entry, read the target again after completion, distinguish physical user-observed YES/NO from status values, and preserve INCONCLUSIVE if verification fails. All tests are run only in GitHub CI.

## S18 readback limitation

The opt-in `pwm_cycle_time` buzzer has no Klipper status readback. Its bounded script first commands OFF, waits 50 ms, sends a 150-ms tone, and commands OFF again. The 200-ms program **attempts** restoration but does not establish that it physically occurred; `restored()` deliberately never accepts S18 as telemetry-verified, even when handed a fabricated status value. Only the exact explicitly permitted, default-OFF effective configuration is admitted.
